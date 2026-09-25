#!/usr/bin/env bash
# Stub ANDREMACEDO_PGREP for test_operator_clear.py: no process listing. Exits
# STUB_PGREP_EXIT (default 1, "no runner.sh going") and, when STUB_PGREP_TRACE
# is set, appends its arguments there so the test can see what was matched.
set -euo pipefail
if [ -n "${STUB_PGREP_TRACE:-}" ]; then
  printf '%s\n' "$*" >> "$STUB_PGREP_TRACE"
fi
exit "${STUB_PGREP_EXIT:-1}"
