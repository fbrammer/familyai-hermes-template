#!/usr/bin/env bash
# FamilyAI: manually force a config refresh instead of waiting for the
# normal weekly cron gate. Useful right after the builder pushes an
# urgent fix and a family member's install hasn't hit its 7-day mark yet.
set -euo pipefail

HERMES_HOME="${1:-$HOME/.hermes}"
MANIFEST_URL="https://raw.githubusercontent.com/fbrammer/familyai-hermes-template/main/manifest.json"
SKILLS_MANIFEST_URL="https://raw.githubusercontent.com/fbrammer/familyai-hermes-template/main/skills-manifest.json"
SKILLS_RAW_BASE_URL="https://raw.githubusercontent.com/fbrammer/familyai-hermes-template/main"
MARKER_FILE="$HERMES_HOME/.familyai-template-synced-at"

if [ ! -f "$HERMES_HOME/scripts/refresher.py" ]; then
  echo "refresher.py not found at $HERMES_HOME/scripts/refresher.py -- is FamilyAI's auto-updater installed?" >&2
  exit 1
fi

echo "Forcing FamilyAI config refresh on $HERMES_HOME (bypassing the normal weekly wait)..."

echo '{"last_applied_exported_at": "1970-01-01T00:00:00Z", "consecutive_failures": 0, "last_escalation_logged_at_failure_count": 0}' > "$MARKER_FILE"

echo
echo "-- Dry run --"
python3 "$HERMES_HOME/scripts/refresher.py" --hermes-home "$HERMES_HOME" --manifest-url "$MANIFEST_URL" \
  --skills-manifest-url "$SKILLS_MANIFEST_URL" --skills-raw-base-url "$SKILLS_RAW_BASE_URL" --dry-run

echo
echo "-- Applying for real --"
python3 "$HERMES_HOME/scripts/refresher.py" --hermes-home "$HERMES_HOME" --manifest-url "$MANIFEST_URL" \
  --skills-manifest-url "$SKILLS_MANIFEST_URL" --skills-raw-base-url "$SKILLS_RAW_BASE_URL"

echo
echo "-- Verifying --"
if grep -q "provider: google" "$HERMES_HOME/config.yaml" 2>/dev/null; then
  echo "WARNING: config.yaml still contains 'provider: google' entries" >&2
else
  echo "OK: no leftover Gemini/Google provider entries in config.yaml"
fi

hermes config check || true

echo
echo "Done."
