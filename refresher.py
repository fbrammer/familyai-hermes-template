"""End-user refresher for FamilyAI Phase 3.

Installed by the onboarding wizard as a daily `hermes cron` no_agent job
on each onboarded user's machine. Every run: checks a local marker's age;
if >=7 days since the last successful apply, fetches manifest.json from
the public FamilyAI template repo, splices its sections into the user's
live config (preserving moa.active_preset), validates the candidate
against an isolated HERMES_HOME copy of `hermes config check`, and only
then atomically swaps it into place -- backing up the previous config
first. Every failure mode -- network, validation, a concurrent edit
detected at the last moment -- leaves the live config untouched and
retries tomorrow.

This script must always exit 0 and never print to stdout/stderr on the
real (non---dry-run) path, on every branch including failure -- Hermes's
no_agent cron delivers output/nonzero-exit to the user, which is the
opposite of the intended silence. The one exception is a single
diagnostic line written to a *file* (familyai-refresh.log) every 30
consecutive failures -- never to stdout.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from ruamel.yaml import YAML

import familyai_config_validate as fcv

MANAGED_SECTIONS = ("fallback_providers", "auxiliary", "delegation", "moa")
MARKER_FILENAME = ".familyai-template-synced-at"
LOCK_FILENAME = ".familyai-refresh.lock"
REFRESH_INTERVAL_DAYS = 7
ESCALATION_INTERVAL = 30
BACKUP_RETENTION = 4
DEFAULT_MARKER = {
    "last_applied_exported_at": "1970-01-01T00:00:00Z",
    "consecutive_failures": 0,
    "last_escalation_logged_at_failure_count": 0,
}


class Outcome:
    NOOP_LOCKED = "noop_locked"
    NOOP_NOT_DUE = "noop_not_due"
    NOOP_STALE_MANIFEST = "noop_stale_manifest"
    SUCCESS = "success"
    FAILURE = "failure"
    DRY_RUN_WOULD_APPLY = "dry_run_would_apply"


# ---------------------------------------------------------------------------
# Locking
# ---------------------------------------------------------------------------


def acquire_lock(lock_path: Path) -> bool:
    """Atomic, cross-platform lock acquisition via exclusive file creation."""
    try:
        fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.close(fd)
        return True
    except FileExistsError:
        return False


def release_lock(lock_path: Path) -> None:
    try:
        os.remove(str(lock_path))
    except FileNotFoundError:
        pass


# ---------------------------------------------------------------------------
# Marker
# ---------------------------------------------------------------------------


def load_marker(path: Path) -> dict:
    if not path.exists():
        return dict(DEFAULT_MARKER)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return {**DEFAULT_MARKER, **data}
    except (json.JSONDecodeError, OSError):
        return dict(DEFAULT_MARKER)


def save_marker(path: Path, marker: dict) -> None:
    path.write_text(json.dumps(marker), encoding="utf-8")


def _parse_iso(s: str) -> datetime:
    return datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def is_due(marker: dict, now: datetime) -> bool:
    return (now - _parse_iso(marker["last_applied_exported_at"])) >= timedelta(days=REFRESH_INTERVAL_DAYS)


def is_newer(candidate_exported_at: str, marker_exported_at: str) -> bool:
    return _parse_iso(candidate_exported_at) > _parse_iso(marker_exported_at)


# ---------------------------------------------------------------------------
# Fetch
# ---------------------------------------------------------------------------


def _default_http_get(url: str) -> bytes:  # pragma: no cover - real network
    req = urllib.request.Request(url, headers={"User-Agent": "familyai-refresher"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        return resp.read()


def fetch_manifest(manifest_url: str, http_get=None) -> bytes:
    http_get = http_get or _default_http_get
    return http_get(manifest_url)


# ---------------------------------------------------------------------------
# Skills pass (novice-UX foundation Task 6)
# ---------------------------------------------------------------------------

SKILLS_INSTALLED_FILENAME = "skills-installed.json"
SKILL_BACKUP_RETENTION = 3


def _load_skills_installed(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _save_skills_installed(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data), encoding="utf-8")


def install_skill(name: str, files: dict[str, bytes], skills_root: Path) -> None:
    """Atomically install one skill's files, backing up any prior version.

    Backup happens before any file is touched -- if a prior version
    exists, it's copied whole to skill-backups/<name>/<timestamp>/ (oldest
    beyond SKILL_BACKUP_RETENTION pruned) before the live directory is
    replaced. Each file is written via a same-directory temp file + os.replace.
    """
    target_dir = skills_root / name

    if target_dir.exists():
        backups_dir = skills_root.parent / "skill-backups" / name
        backups_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        shutil.copytree(target_dir, backups_dir / timestamp)

        existing_backups = sorted(backups_dir.iterdir())
        if len(existing_backups) > SKILL_BACKUP_RETENTION:
            for old in existing_backups[: len(existing_backups) - SKILL_BACKUP_RETENTION]:
                shutil.rmtree(old, ignore_errors=True)

        shutil.rmtree(target_dir)

    target_dir.mkdir(parents=True, exist_ok=True)
    for rel_path, content in files.items():
        dest = target_dir / rel_path
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.parent / f".{dest.name}.tmp"
        tmp.write_bytes(content)
        os.replace(tmp, dest)


def run_skills_pass(
    hermes_home: str,
    skills_manifest_url: str,
    base_raw_url: str,
    dry_run: bool = False,
    http_get=None,
) -> dict:
    """One skills-refresh cycle: fetch skills-manifest.json, install any changed
    skill whose files all pass validation, or reject the *whole* pass (no
    skill installed) if any changed skill fails validation -- matching the
    existing config-refresher's whole-candidate rejection policy.
    """
    home = Path(hermes_home)
    installed_path = home / SKILLS_INSTALLED_FILENAME
    skills_root = home / "skills"
    log_path = home / "logs" / "familyai-refresh.log"
    http_get = http_get or _default_http_get

    try:
        raw = http_get(skills_manifest_url)
        manifest = fcv.parse_manifest(raw)
    except Exception as e:  # noqa: BLE001 - fetch/parse failure is a normal failure path
        return {"outcome": Outcome.FAILURE, "reason": f"fetch/parse failed: {e!r}"}

    installed = _load_skills_installed(installed_path)

    changed: dict[str, dict] = {}
    for name, meta in manifest.get("skills", {}).items():
        prior = installed.get(name)
        if prior and prior.get("sha256") == meta.get("sha256"):
            continue
        changed[name] = meta

    if not changed:
        return {"outcome": Outcome.NOOP_STALE_MANIFEST}

    fetched: dict[str, dict[str, bytes]] = {}
    all_reasons: list[str] = []

    for name, meta in changed.items():
        files: dict[str, bytes] = {}
        try:
            for rel in meta.get("files", []):
                files[rel] = http_get(f"{base_raw_url.rstrip('/')}/skills/{name}/{rel}")
        except Exception as e:  # noqa: BLE001 - per-skill fetch failure
            all_reasons.append(f"{name}: fetch failed: {e!r}")
            continue

        ok, reasons = fcv.validate_skill_candidate(name, files, meta, installed.get(name))
        if not ok:
            all_reasons.extend(reasons)
        else:
            fetched[name] = files

    if all_reasons:
        reason = "; ".join(all_reasons)
        if not dry_run:
            _log(log_path, f"skills pass rejected: {reason}")
        return {"outcome": Outcome.FAILURE, "reason": reason}

    if dry_run:
        return {"outcome": Outcome.DRY_RUN_WOULD_APPLY, "skills": sorted(fetched)}

    for name, files in fetched.items():
        install_skill(name, files, skills_root)
        installed[name] = {
            "version": changed[name].get("version"),
            "sha256": changed[name].get("sha256"),
        }

    _save_skills_installed(installed_path, installed)
    return {"outcome": Outcome.SUCCESS, "updated": sorted(fetched)}


# ---------------------------------------------------------------------------
# Splice
# ---------------------------------------------------------------------------


def splice_candidate(user_config: Any, manifest_sections: dict) -> tuple[Any, list[str]]:
    """Splice fetched sections into a copy of the user's config.

    fallback_providers/auxiliary/delegation/moa.default_preset/moa.presets
    are replaced wholesale; moa.active_preset is preserved from the user's
    existing config. Returns (candidate, dangling_preset_reasons) -- a
    non-empty reasons list means the preserved active_preset doesn't exist
    in the newly-fetched presets and this candidate must be rejected.
    """
    reasons: list[str] = []

    for key in ("fallback_providers", "auxiliary", "delegation"):
        if key in manifest_sections:
            user_config[key] = manifest_sections[key]

    if "moa" in manifest_sections:
        fetched_moa = manifest_sections["moa"]
        existing_moa = user_config.get("moa")
        active_preset = existing_moa.get("active_preset") if isinstance(existing_moa, dict) else None

        new_moa = {
            "default_preset": fetched_moa.get("default_preset", ""),
            "presets": fetched_moa.get("presets", {}),
        }
        if active_preset:
            if active_preset not in new_moa["presets"]:
                reasons.append(
                    f"preserved moa.active_preset '{active_preset}' is not present in the fetched presets"
                )
            new_moa["active_preset"] = active_preset
        elif existing_moa is not None and "active_preset" in existing_moa:
            new_moa["active_preset"] = active_preset  # explicitly absent/empty, preserved as such

        user_config["moa"] = new_moa

    return user_config, reasons


# ---------------------------------------------------------------------------
# YAML round-trip
# ---------------------------------------------------------------------------


def load_ruamel(path: Path):
    yaml = YAML(typ="rt")
    with open(path, "r", encoding="utf-8") as f:
        return yaml.load(f)


def dump_ruamel(data: Any, path: Path) -> None:
    yaml = YAML(typ="rt")
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(data, f)


def _hash_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# ---------------------------------------------------------------------------
# Isolated HERMES_HOME validation
# ---------------------------------------------------------------------------


def build_scratch_hermes_home(real_hermes_home: Path, candidate_config_path: Path, scratch_dir: Path) -> Path:
    """Build a minimal scratch HERMES_HOME: copy (never symlink) .env, place the candidate config.

    Copy, not symlink -- os.symlink requires Developer Mode / elevation on
    Windows, which would reintroduce the OS branching this design avoids.
    skills/ and cron/ are deliberately omitted; `hermes config check`
    doesn't need them.
    """
    scratch_dir.mkdir(parents=True, exist_ok=True)
    env_src = real_hermes_home / ".env"
    if env_src.exists():
        shutil.copy2(env_src, scratch_dir / ".env")
    shutil.copy2(candidate_config_path, scratch_dir / "config.yaml")
    return scratch_dir


CONFIG_PARSE_FAILURE_MARKER = "Falling back to default config"


def real_config_check(scratch_home: Path) -> bool:
    """Real implementation: shells out to `hermes config check` against the scratch home.

    EMPIRICAL FINDING (verified against a real local Hermes v0.19.0
    install, see docs/deployment-notes.md): `hermes config check` always
    exits 0, even when config.yaml is completely unparseable -- it
    silently falls back to defaults and only warns on stderr. The exit
    code alone is therefore useless as a validity signal; this function
    additionally inspects stderr for Hermes's own fallback marker, which
    was confirmed present on a broken candidate and absent on a valid
    one. This only catches "Hermes couldn't parse this as a config file
    at all" -- it is not a substitute for validate_candidate(), which is
    still the primary content-safety and security gate; this check's
    remaining job is to catch a YAML-syntax-level break introduced by the
    splice/dump step that our own validator wouldn't see (it only
    inspects the parsed Python structure, not the serialized text).
    """
    env = dict(os.environ)
    env["HERMES_HOME"] = str(scratch_home)
    try:
        result = subprocess.run(
            ["hermes", "config", "check"], env=env, capture_output=True, timeout=10, text=True
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    if CONFIG_PARSE_FAILURE_MARKER in (result.stderr or ""):
        return False
    return result.returncode == 0


# ---------------------------------------------------------------------------
# Backup + atomic swap
# ---------------------------------------------------------------------------


def prune_backups(config_dir: Path, keep: int = BACKUP_RETENTION) -> None:
    backups = sorted(config_dir.glob("config.yaml.bak.*"))
    if len(backups) > keep:
        for old in backups[: len(backups) - keep]:
            old.unlink(missing_ok=True)


def backup_and_swap(live_config_path: Path, validated_temp_path: Path) -> None:
    """Only called after a successful validation AND a successful os.replace.

    Order matters: replace first, THEN back up + prune. os.replace is
    atomic -- if it fails, the live config is untouched regardless, so
    there is nothing to back up from a failed replace. Backing up before
    a possible failure would only risk wasting a good backup slot for
    nothing gained.
    """
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    pre_swap_bytes = live_config_path.read_bytes()
    os.replace(str(validated_temp_path), str(live_config_path))
    backup_path = live_config_path.parent / f"config.yaml.bak.{timestamp}"
    backup_path.write_bytes(pre_swap_bytes)
    prune_backups(live_config_path.parent)


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------


def _log(log_path: Path, message: str) -> None:
    """File-only logging -- never stdout/stderr, so cron delivery is never triggered."""
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(f"{datetime.now(timezone.utc).isoformat()} {message}\n")


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


def _record_failure(marker_path: Path, marker: dict, log_path: Path, reason: str) -> dict:
    marker["consecutive_failures"] += 1
    n = marker["consecutive_failures"]
    if n % ESCALATION_INTERVAL == 0 and n > marker["last_escalation_logged_at_failure_count"]:
        _log(log_path, f"refresher has failed {n} consecutive times; last reason: {reason}")
        marker["last_escalation_logged_at_failure_count"] = n
    save_marker(marker_path, marker)
    return {"outcome": Outcome.FAILURE, "reason": reason}


def run(
    hermes_home: str,
    manifest_url: str,
    dry_run: bool = False,
    http_get=None,
    config_checker=None,
    now: datetime | None = None,
) -> dict:
    home = Path(hermes_home)
    marker_path = home / MARKER_FILENAME
    lock_path = home / LOCK_FILENAME
    log_path = home / "logs" / "familyai-refresh.log"
    live_config_path = home / "config.yaml"
    now = now or datetime.now(timezone.utc)
    checker = config_checker or real_config_check

    if not acquire_lock(lock_path):
        return {"outcome": Outcome.NOOP_LOCKED}

    try:
        marker = load_marker(marker_path)

        if not is_due(marker, now):
            return {"outcome": Outcome.NOOP_NOT_DUE}

        try:
            raw = fetch_manifest(manifest_url, http_get=http_get)
            manifest = fcv.parse_manifest(raw)
        except Exception as e:  # noqa: BLE001 - fetch/parse failure is a normal failure path
            if dry_run:
                return {"outcome": Outcome.FAILURE, "reason": f"fetch/parse failed: {e!r}"}
            return _record_failure(marker_path, marker, log_path, f"fetch/parse failed: {e!r}")

        computed_hash = fcv.canonical_hash(manifest.get("sections", {}))
        if computed_hash != manifest.get("content_hash"):
            reason = "content_hash mismatch"
            if dry_run:
                return {"outcome": Outcome.FAILURE, "reason": reason}
            return _record_failure(marker_path, marker, log_path, reason)

        if not is_newer(manifest["exported_at"], marker["last_applied_exported_at"]):
            # Explicitly a no-op, not a failure -- the expected steady state
            # most days. Does not touch consecutive_failures.
            return {"outcome": Outcome.NOOP_STALE_MANIFEST}

        pre_splice_hash = _hash_file(live_config_path)
        user_config = load_ruamel(live_config_path)
        candidate, dangling_reasons = splice_candidate(user_config, manifest["sections"])
        if dangling_reasons:
            reason = "; ".join(dangling_reasons)
            if dry_run:
                return {"outcome": Outcome.FAILURE, "reason": reason}
            return _record_failure(marker_path, marker, log_path, reason)

        candidate_sections = {k: candidate[k] for k in MANAGED_SECTIONS if k in candidate}
        ok, reasons = fcv.validate_candidate(candidate_sections)
        if not ok:
            reason = "; ".join(reasons)
            if dry_run:
                return {"outcome": Outcome.FAILURE, "reason": reason}
            return _record_failure(marker_path, marker, log_path, reason)

        temp_path = live_config_path.parent / f".config.yaml.candidate.{os.getpid()}"
        dump_ruamel(candidate, temp_path)

        scratch_home = home / f".familyai-scratch-{os.getpid()}"
        try:
            build_scratch_hermes_home(home, temp_path, scratch_home)
            check_passed = checker(scratch_home)
        finally:
            shutil.rmtree(scratch_home, ignore_errors=True)

        if not check_passed:
            temp_path.unlink(missing_ok=True)
            reason = "hermes config check rejected the candidate"
            if dry_run:
                return {"outcome": Outcome.FAILURE, "reason": reason}
            return _record_failure(marker_path, marker, log_path, reason)

        if dry_run:
            temp_path.unlink(missing_ok=True)
            return {"outcome": Outcome.DRY_RUN_WOULD_APPLY, "manifest": manifest}

        if _hash_file(live_config_path) != pre_splice_hash:
            temp_path.unlink(missing_ok=True)
            return _record_failure(marker_path, marker, log_path, "live config changed concurrently")

        backup_and_swap(live_config_path, temp_path)

        marker["last_applied_exported_at"] = manifest["exported_at"]
        marker["consecutive_failures"] = 0
        marker["last_escalation_logged_at_failure_count"] = 0
        save_marker(marker_path, marker)
        return {"outcome": Outcome.SUCCESS}

    except Exception as e:  # noqa: BLE001 - absolute last resort, must never raise past run()
        if dry_run:
            return {"outcome": Outcome.FAILURE, "reason": f"unexpected error: {e!r}"}
        try:
            marker = load_marker(marker_path)
        except Exception:
            marker = dict(DEFAULT_MARKER)
        return _record_failure(marker_path, marker, log_path, f"unexpected error: {e!r}")
    finally:
        release_lock(lock_path)


def main() -> int:
    parser = argparse.ArgumentParser(description="FamilyAI Phase 3 end-user refresher")
    parser.add_argument("--hermes-home", required=True)
    parser.add_argument("--manifest-url", default=os.environ.get("FAMILYAI_MANIFEST_URL", ""))
    parser.add_argument("--skills-manifest-url", default=os.environ.get("FAMILYAI_SKILLS_MANIFEST_URL", ""))
    parser.add_argument("--skills-raw-base-url", default=os.environ.get("FAMILYAI_SKILLS_RAW_BASE_URL", ""))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    try:
        result = run(hermes_home=args.hermes_home, manifest_url=args.manifest_url, dry_run=args.dry_run)
    except Exception:  # noqa: BLE001 - never let anything escape to stdout/stderr on the real path
        result = {"outcome": Outcome.FAILURE, "reason": "unexpected error in config pass"}

    skills_result = None
    if args.skills_manifest_url and args.skills_raw_base_url:
        try:
            skills_result = run_skills_pass(
                hermes_home=args.hermes_home,
                skills_manifest_url=args.skills_manifest_url,
                base_raw_url=args.skills_raw_base_url,
                dry_run=args.dry_run,
            )
        except Exception:  # noqa: BLE001 - same silence contract as the config pass
            skills_result = {"outcome": Outcome.FAILURE, "reason": "unexpected error in skills pass"}

    if args.dry_run:
        print(json.dumps({"config": result, "skills": skills_result}, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
