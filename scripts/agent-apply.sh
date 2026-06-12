#!/usr/bin/env bash
# agent-apply.sh — deterministic wrapper for the creative session to apply its
# mutation JSON through the existing apply_changes.py machinery (protected
# mobile blocks, contrast clamps, genome bookkeeping all preserved).
#
# Usage: agent-apply.sh <daily|weekly|event>
# Reads:  state/pending-mutation.json (written by the session, JSON only)
# Writes: state/apply-output.log (full apply_changes.py output; the runner
#         reads it for the commit summary and Telegram counts)
# Exit:   apply_changes.py's exit code; non-zero = mutation NOT applied cleanly.
#
# TOTAL_TOKENS is 0 here on purpose: token accounting moved to the runner,
# which knows the real session usage from the stream-json result event.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SITE_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
MUTATION="$SITE_DIR/state/pending-mutation.json"
OUT="$SITE_DIR/state/apply-output.log"

PULSE="${1:-}"
case "$PULSE" in
  daily|weekly|event) ;;
  *) echo "Usage: $0 <daily|weekly|event>" >&2; exit 2 ;;
esac

[ -s "$MUTATION" ] || { echo "FAIL: $MUTATION missing or empty — write your mutation JSON there first" >&2; exit 1; }
if ! python3 -c 'import json,sys; json.load(open(sys.argv[1]))' "$MUTATION" 2>/dev/null; then
  echo "FAIL: $MUTATION is not valid JSON — fix it and re-run" >&2
  exit 1
fi

cd "$SITE_DIR"
SITE_DIR="$SITE_DIR" PULSE_TYPE="$PULSE" TOTAL_TOKENS=0 CONTENT="$(cat "$MUTATION")" \
  python3 "$SCRIPT_DIR/apply_changes.py" > "$OUT" 2>&1
rc=$?
cat "$OUT"
if [ "$rc" -ne 0 ]; then
  echo "FAIL: apply_changes.py exit=$rc (output above and in $OUT)" >&2
fi
exit "$rc"
