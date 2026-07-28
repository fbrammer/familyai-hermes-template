"""Shared validation for FamilyAI Phase 3 managed config sections.

Covers fallback_providers, auxiliary, delegation, and moa -- the four
sections the Phase 3 publisher/refresher pipeline manages. This module is
imported by both publisher.py (drop bad entries, keep publishing) and
refresher.py (reject the whole candidate on any violation) so their
policies can never drift apart -- see check_entry for the one rule engine,
and filter_section / validate_candidate for the two different policies
built on top of it.

Design note on `base_url`: Hermes's own `delegation` schema legitimately
includes a `base_url` field (empty by default, only meaningful if
delegation is enabled with a custom endpoint). Rule 2 therefore rejects a
*non-empty* base_url anywhere, not the key's mere presence -- an empty
string is how "disabled" is represented and must stay valid.
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any

try:
    from ruamel.yaml import YAML
    from ruamel.yaml.constructor import DuplicateKeyError
except ImportError:  # pragma: no cover - exercised only when ruamel is missing
    YAML = None
    DuplicateKeyError = Exception


class BuilderConfigError(Exception):
    """Raised when the builder's own live config.yaml fails to parse safely."""


class ManifestError(Exception):
    """Raised when a fetched manifest.json fails to parse safely."""


# ---------------------------------------------------------------------------
# Rule 1: structural key allowlists
# ---------------------------------------------------------------------------

SECTION_KEYS: dict[str, set[str]] = {
    "fallback_providers": {"provider", "model", "name"},
    "auxiliary": {
        "provider",
        "model",
        "timeout",
        "reasoning_effort",
        "download_timeout",
        "language",
    },
    "delegation": {
        "model",
        "provider",
        "base_url",
        "api_key",
        "api_mode",
        "inherit_mcp_toolsets",
        "max_iterations",
        "child_timeout_seconds",
        "reasoning_effort",
        "max_concurrent_children",
        "max_spawn_depth",
        "orchestrator_enabled",
        "subagent_auto_approve",
    },
    "moa_preset": {"reference_models", "aggregator", "max_tokens", "enabled"},
    "moa_model_ref": {"provider", "model"},
}

REQUIRED_KEYS: dict[str, set[str]] = {
    "fallback_providers": {"provider", "model"},
    "auxiliary": {"provider", "model"},
    "delegation": set(),  # every field may legitimately be empty when disabled
    "moa_preset": set(),
    "moa_model_ref": {"provider", "model"},
}

SECRET_KEY_NAMES = {"api_key", "token", "secret"}
ENV_VAR_PATTERN = re.compile(r"^\$\{[A-Z0-9_]+\}$")

MOA_TOP_LEVEL_KEYS = {"default_preset", "active_preset", "presets"}
MAX_MANIFEST_BYTES = 64 * 1024


# ---------------------------------------------------------------------------
# The rule engine
# ---------------------------------------------------------------------------


def check_entry(entry: Any, section: str) -> list[str]:
    """Validate one entry/mapping against `section`'s rules.

    Returns a list of violation-reason strings; an empty list means clean.
    This is the single place rules 1-3 and the required-key check live --
    both filter_section and validate_candidate call this, never
    reimplementing the rules themselves.
    """
    reasons: list[str] = []
    if not isinstance(entry, dict):
        return [f"{section}: entry is not a mapping (got {type(entry).__name__})"]

    allowed_keys = SECTION_KEYS.get(section)
    if allowed_keys is None:
        return [f"{section}: unknown section"]

    for key, value in entry.items():
        if key not in allowed_keys:
            reasons.append(f"{section}: unrecognized key '{key}'")
            continue

        if key == "base_url" and value not in (None, ""):
            reasons.append(
                f"{section}: base_url must be empty/absent (non-empty base_url "
                "is never permitted through this pipeline)"
            )

        if key in SECRET_KEY_NAMES and value not in (None, ""):
            if not ENV_VAR_PATTERN.match(str(value)):
                reasons.append(
                    f"{section}: '{key}' must be an env-var reference like "
                    "${VAR}, never a literal value"
                )

        if value is None and key in REQUIRED_KEYS.get(section, set()):
            reasons.append(f"{section}: required key '{key}' is null")

    for required in REQUIRED_KEYS.get(section, set()):
        if required not in entry:
            reasons.append(f"{section}: missing required key '{required}'")

    return reasons


def check_section(section_name: str, value: Any) -> list[str]:
    """Validate a whole top-level section (list/mapping shape + every entry)."""
    reasons: list[str] = []

    if section_name == "fallback_providers":
        if not isinstance(value, list):
            return [f"fallback_providers: expected a list, got {type(value).__name__}"]
        for i, entry in enumerate(value):
            reasons.extend(f"fallback_providers[{i}]: {r}" for r in check_entry(entry, "fallback_providers"))

    elif section_name == "auxiliary":
        if not isinstance(value, dict):
            return [f"auxiliary: expected a mapping, got {type(value).__name__}"]
        for task_name, entry in value.items():
            reasons.extend(f"auxiliary[{task_name}]: {r}" for r in check_entry(entry, "auxiliary"))

    elif section_name == "delegation":
        if not isinstance(value, dict):
            return [f"delegation: expected a mapping, got {type(value).__name__}"]
        reasons.extend(check_entry(value, "delegation"))

    elif section_name == "moa":
        if not isinstance(value, dict):
            return [f"moa: expected a mapping, got {type(value).__name__}"]

        for key in value.keys():
            if key not in MOA_TOP_LEVEL_KEYS:
                reasons.append(f"moa: unrecognized top-level key '{key}'")

        if "default_preset" in value and not isinstance(value["default_preset"], str):
            reasons.append("moa: default_preset must be a string")

        if "active_preset" in value and value["active_preset"] is not None and not isinstance(value["active_preset"], str):
            reasons.append("moa: active_preset must be a string or null")

        presets = value.get("presets", {})
        if not isinstance(presets, dict):
            reasons.append("moa: presets must be a mapping")
        else:
            for preset_name, preset in presets.items():
                reasons.extend(_check_moa_preset(preset_name, preset))

    else:
        reasons.append(f"unknown section '{section_name}'")

    return reasons


def _check_moa_preset(preset_name: str, preset: Any) -> list[str]:
    reasons: list[str] = []
    if not isinstance(preset, dict):
        return [f"moa.presets[{preset_name}]: not a mapping"]

    reasons.extend(f"moa.presets[{preset_name}]: {r}" for r in check_entry(preset, "moa_preset"))

    ref_models = preset.get("reference_models", [])
    if not isinstance(ref_models, list):
        reasons.append(f"moa.presets[{preset_name}].reference_models: expected a list")
    else:
        for i, rm in enumerate(ref_models):
            reasons.extend(
                f"moa.presets[{preset_name}].reference_models[{i}]: {r}"
                for r in check_entry(rm, "moa_model_ref")
            )

    aggregator = preset.get("aggregator")
    if aggregator is not None:
        reasons.extend(
            f"moa.presets[{preset_name}].aggregator: {r}"
            for r in check_entry(aggregator, "moa_model_ref")
        )

    return reasons


# ---------------------------------------------------------------------------
# Publisher policy: drop bad entries, keep publishing
# ---------------------------------------------------------------------------


def filter_section(section_name: str, value: Any) -> tuple[Any, list[dict]]:
    """Publisher policy: drop invalid entries, keep the rest.

    Returns (clean_value, dropped) where `dropped` is a list of
    {..., "reasons": [...]} describing what got excluded and why -- the
    publisher logs this, it never silently disappears.
    """
    dropped: list[dict] = []

    if section_name == "fallback_providers":
        clean: list[Any] = []
        for i, entry in enumerate(value):
            reasons = check_entry(entry, "fallback_providers")
            if reasons:
                dropped.append({"index": i, "entry": entry, "reasons": reasons})
            else:
                clean.append(entry)
        return clean, dropped

    if section_name == "auxiliary":
        clean_aux: dict[str, Any] = {}
        for task_name, entry in value.items():
            reasons = check_entry(entry, "auxiliary")
            if reasons:
                dropped.append({"key": task_name, "entry": entry, "reasons": reasons})
            else:
                clean_aux[task_name] = entry
        return clean_aux, dropped

    if section_name == "delegation":
        reasons = check_entry(value, "delegation")
        if reasons:
            dropped.append({"entry": value, "reasons": reasons})
            return {}, dropped
        return value, dropped

    if section_name == "moa":
        clean_presets: dict[str, Any] = {}
        for preset_name, preset in value.get("presets", {}).items():
            reasons = _check_moa_preset(preset_name, preset)
            if reasons:
                dropped.append({"preset": preset_name, "reasons": reasons})
            else:
                clean_presets[preset_name] = preset
        clean_moa = {
            "default_preset": value.get("default_preset", ""),
            "presets": clean_presets,
        }
        return clean_moa, dropped

    raise ValueError(f"unknown section '{section_name}'")


# ---------------------------------------------------------------------------
# Consumer policy: reject the whole candidate on any violation
# ---------------------------------------------------------------------------


def validate_candidate(sections: dict) -> tuple[bool, list[str]]:
    """Consumer policy: any violation anywhere rejects the whole candidate.

    Never raises -- returns (ok, reasons) so the refresher can act on it
    silently, consistent with its exit-0-always requirement.
    """
    all_reasons: list[str] = []
    for section_name in ("fallback_providers", "auxiliary", "delegation", "moa"):
        if section_name not in sections:
            continue
        all_reasons.extend(check_section(section_name, sections[section_name]))
    return (len(all_reasons) == 0, all_reasons)


# ---------------------------------------------------------------------------
# Canonical hashing -- shared by publisher (compute) and refresher (verify)
# ---------------------------------------------------------------------------


def canonical_hash(sections: dict) -> str:
    """Deterministic SHA-256 of `sections`, independent of dict insertion order."""
    encoded = json.dumps(
        sections, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


# ---------------------------------------------------------------------------
# Publisher-only: safe YAML parsing of the builder's live config
# ---------------------------------------------------------------------------


def parse_builder_config(path: str) -> dict:
    """Load the builder's own config.yaml, rejecting duplicate keys and anchors/aliases.

    Rule 4 (no anchors/aliases, no duplicate keys) lives here and only
    here -- the refresher never parses arbitrary YAML from the network,
    it only parses JSON (see parse_manifest) and writes YAML it built
    itself from already-validated Python data.
    """
    if YAML is None:  # pragma: no cover
        raise RuntimeError("ruamel.yaml is required (see requirements.txt)")

    yaml = YAML(typ="rt")
    yaml.allow_duplicate_keys = False
    with open(path, "r", encoding="utf-8") as f:
        try:
            data = yaml.load(f)
        except DuplicateKeyError as e:
            raise BuilderConfigError(f"duplicate key in {path}: {e}") from e

    _reject_anchors(data)
    return data


def _reject_anchors(node: Any) -> None:
    """Walk a ruamel-loaded structure and raise if any node carries a real anchor."""
    anchor = getattr(node, "anchor", None)
    if anchor is not None and getattr(anchor, "value", None):
        raise BuilderConfigError(
            "YAML anchors/aliases are not permitted in the builder's managed sections"
        )
    if isinstance(node, dict):
        for v in node.values():
            _reject_anchors(v)
    elif isinstance(node, list):
        for v in node:
            _reject_anchors(v)


# ---------------------------------------------------------------------------
# Refresher-only: safe JSON parsing of a fetched manifest
# ---------------------------------------------------------------------------


def _reject_json_duplicates(pairs: list[tuple[str, Any]]) -> dict:
    seen: dict[str, Any] = {}
    for key, value in pairs:
        if key in seen:
            raise ManifestError(f"duplicate key '{key}' in manifest JSON")
        seen[key] = value
    return seen


def parse_manifest(raw_bytes: bytes) -> dict:
    """Parse a fetched manifest.json: size-capped, duplicate-key-rejecting."""
    if len(raw_bytes) > MAX_MANIFEST_BYTES:
        raise ManifestError(f"manifest exceeds {MAX_MANIFEST_BYTES}-byte cap")
    try:
        text = raw_bytes.decode("utf-8")
    except UnicodeDecodeError as e:
        raise ManifestError(f"manifest is not valid UTF-8: {e}") from e
    try:
        return json.loads(text, object_pairs_hook=_reject_json_duplicates)
    except json.JSONDecodeError as e:
        raise ManifestError(f"invalid JSON: {e}") from e
