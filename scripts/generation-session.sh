#!/usr/bin/env bash
# generation-session.sh — ONE creative generation session through the executor helper.
#
# Extracted from runner.sh (2026-09-23) so the runner's single attempt and each
# epoch_fanout.py candidate invoke the helper with identical flags; two copies of
# this call would drift. The caller owns the wall-clock bound (runner.sh wraps
# this in tmo; epoch_fanout.py uses a subprocess timeout on its own process group)
# and the cwd, which the agentic session inherits as its repo.
#
# Usage: generation-session.sh agentic|single
# Env in : INPUT_JSONL  stream-json user message (image blocks + prompt text)
#          OUTPUT_FILE  where the helper writes its stream-json output
# Env opt: ANDREMACEDO_HELPER  executor helper (test seam; production sets it in
#                              ~/.telos/andremacedo-executor.env)
#          TELOS_AGENT         audit-log caller id
#          PULSE_TYPE          carried into the default TELOS_AGENT
# Exit   : the helper's exit code; 2 on a usage error.
set -euo pipefail

MODE="${1:-}"
case "$MODE" in
  agentic|single) ;;
  *) echo "Usage: $0 agentic|single" >&2; exit 2 ;;
esac
[ -n "${INPUT_JSONL:-}" ] && [ -s "$INPUT_JSONL" ] || { echo "generation-session: INPUT_JSONL missing or empty" >&2; exit 2; }
[ -n "${OUTPUT_FILE:-}" ] || { echo "generation-session: OUTPUT_FILE required" >&2; exit 2; }

# ANDREMACEDO_HELPER is a test seam (forced-failure dry runs); production
# default is the canonical subscription helper.
HELPER_SCRIPT="${ANDREMACEDO_HELPER:-$HOME/.telos/scripts/claude-subscription-exec.sh}"
# TELOS_AGENT is the helper's audit-log caller id. Unset, every row this
# runner writes lands as the literal "unknown" and the shared executor log
# cannot be grouped by job. Pulse type is carried so the agentic build and
# the single-turn pulse below stay distinguishable in the log.
export TELOS_AGENT="${TELOS_AGENT:-andremacedo-creative:${PULSE_TYPE:-runner.sh}}"
export INPUT_JSONL OUTPUT_FILE

if [ "$MODE" = "agentic" ]; then
  # Bounded agentic session: tool allowlist is exactly file read/write/edit +
  # shell; stream-json + tail-aware failure logging kept (f328732).
  # Caps calibrated from the two 2026-06-12 smoke runs (both verified-good
  # work killed by single-turn-era caps): run 1 finished all gates + verdict
  # OK in 12 turns but died at $6.24 vs the $6 budget (error_max_budget_usd);
  # run 2 (budget 10) died at the 12-turn cap mid-fix-iteration at $8.43
  # (error_max_turns), ~$0.65/turn observed.
  # UNCAPPED (Andre directive 2026-06-24): turn cap and dollar budget removed
  # — the last 3 daily builds (06-20/06-23/06-24) died at error_max_turns mid-
  # Edit, verified-good work killed by the 20-turn ceiling. The caller's wall
  # bound is now the SOLE backstop.
  # NOTE: the helper (claude-subscription-exec.sh:44) defaults CLAUDE_MAX_BUDGET_USD
  # to $1.00 when UNSET and always forwards --max-budget-usd. Simply deleting the
  # env var (the 2026-06-24 first uncap attempt) therefore did NOT uncap — it
  # dropped the ceiling to $1 and killed the build in ~1 turn (44s). To make the
  # wall the sole binding backstop, we must SET a budget high enough that the
  # wall trips first.
  # 2026-06-27 (Andre): doubled per-generation budget — dollar floor 50→100.
  CLAUDE_MAX_BUDGET_USD=100.00 exec bash "$HELPER_SCRIPT" \
    --model claude-fable-5-1 \
    --input-format stream-json --output-format stream-json \
    --verbose \
    --tools "Bash,Read,Write,Edit" \
    --permission-mode bypassPermissions \
    --strict-mcp-config --mcp-config "$HOME/.telos/andremacedo-runner-mcp.json" \
    --no-session-persistence
fi

# Event pulse keeps the single-turn blind-shot path (f328732).
CLAUDE_MAX_BUDGET_USD=12.00 exec bash "$HELPER_SCRIPT" \
  --model claude-fable-5-1 \
  --input-format stream-json --output-format stream-json \
  --max-turns 1 --verbose \
  --tools "" \
  --strict-mcp-config --mcp-config "$HOME/.telos/andremacedo-runner-mcp.json" \
  --no-session-persistence
