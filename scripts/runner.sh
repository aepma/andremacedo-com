#!/usr/bin/env bash
# runner.sh — andremacedo.com creative agent runner
# Usage: runner.sh --daily | --weekly | --event
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SITE_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
STATE_FILE="$SITE_DIR/state/agent-state.json"
CHANGELOG="$SITE_DIR/state/changelog.md"
EXTERNAL_FILE="$SITE_DIR/data/external.json"
INDEX_FILE="$SITE_DIR/index.html"
SOUL_FILE="$SITE_DIR/SOUL.md"
APPLY_SCRIPT="$SCRIPT_DIR/apply_changes.py"

LOG_FILE="$HOME/.openclaw/logs/andremacedo-agent.log"
mkdir -p "$(dirname "$LOG_FILE")"

BOT_TOKEN="${OPENCLAW_TELEGRAM_BOT_TOKEN:-}"
CHAT_ID="${OPENCLAW_TELEGRAM_CHAT_ID:-}"
API_KEY="${ANTHROPIC_API_KEY:-}"
MODEL="claude-opus-4-6"
API_URL="https://api.anthropic.com/v1/messages"

PULSE_TYPE=""
case "${1:-}" in
  --daily)  PULSE_TYPE="daily" ;;
  --weekly) PULSE_TYPE="weekly" ;;
  --event)  PULSE_TYPE="event" ;;
  *)
    echo "Usage: $0 --daily | --weekly | --event" >&2
    exit 1
    ;;
esac

log() {
  echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] $*" | tee -a "$LOG_FILE"
}

telegram() {
  if [ -z "$BOT_TOKEN" ] || [ -z "$CHAT_ID" ]; then return 0; fi
  curl -s -X POST "https://api.telegram.org/bot${BOT_TOKEN}/sendMessage" \
    -d chat_id="$CHAT_ID" -d parse_mode="Markdown" -d text="$1" >/dev/null 2>&1 || true
}

# ── Pre-flight ─────────────────────────────────────────────────────
if [ -z "$API_KEY" ]; then
  log "ERROR: ANTHROPIC_API_KEY not set"
  telegram "andremacedo.com agent ERROR: ANTHROPIC_API_KEY not set"
  exit 1
fi

if [ ! -f "$STATE_FILE" ]; then
  log "ERROR: agent-state.json not found"
  exit 1
fi

MONTHLY_USED=$(python3 -c 'import json,sys; print(json.load(sys.stdin).get("monthly_tokens_used",0))' < "$STATE_FILE")
MONTHLY_CEILING=$(python3 -c 'import json,sys; print(json.load(sys.stdin).get("monthly_token_ceiling",200000))' < "$STATE_FILE")

if [ "$MONTHLY_USED" -ge "$MONTHLY_CEILING" ]; then
  log "Token ceiling reached ($MONTHLY_USED/$MONTHLY_CEILING). Skipping."
  telegram "andremacedo.com: token ceiling reached. Skipping $PULSE_TYPE."
  exit 0
fi

if [ "$PULSE_TYPE" = "event" ] && [ "$MONTHLY_USED" -ge $((MONTHLY_CEILING * 80 / 100)) ]; then
  log "Near ceiling. Skipping event pulse."
  exit 0
fi

STATE="$(cat "$STATE_FILE")"
EXTERNAL="{}"
[ -f "$EXTERNAL_FILE" ] && EXTERNAL="$(cat "$EXTERNAL_FILE")"

TODAY="$(date -u +%Y-%m-%d)"
DAY_OF_WEEK="$(date -u +%A)"
HOUR="$(date -u +%H)"
if   [ "$HOUR" -ge 5  ] && [ "$HOUR" -lt 8  ]; then TOD="dawn"
elif [ "$HOUR" -ge 8  ] && [ "$HOUR" -lt 12 ]; then TOD="morning"
elif [ "$HOUR" -ge 12 ] && [ "$HOUR" -lt 17 ]; then TOD="afternoon"
elif [ "$HOUR" -ge 17 ] && [ "$HOUR" -lt 21 ]; then TOD="evening"
else TOD="night"
fi

# ── Build prompt ───────────────────────────────────────────────────
PROMPT_FILE="$(mktemp)"
HTTP_RESPONSE_FILE="$(mktemp)"
trap 'rm -f "$PROMPT_FILE" "$HTTP_RESPONSE_FILE"' EXIT

python3 "$SCRIPT_DIR/build_prompt.py" "$PULSE_TYPE" "$STATE_FILE" "$EXTERNAL_FILE" "$INDEX_FILE" "$SOUL_FILE" "$CHANGELOG" "$TODAY" "$DAY_OF_WEEK" "$TOD" > "$PROMPT_FILE"

if [ "$PULSE_TYPE" = "weekly" ]; then MAX_TOKENS=2000
elif [ "$PULSE_TYPE" = "daily" ]; then MAX_TOKENS=800
else MAX_TOKENS=1000
fi

# ── Call Anthropic API ─────────────────────────────────────────────
log "Starting $PULSE_TYPE pulse..."

REQUEST_JSON="$(python3 -c 'import json,sys; f=open(sys.argv[1]); print(json.dumps({"model":sys.argv[2],"max_tokens":int(sys.argv[3]),"messages":[{"role":"user","content":f.read()}]}))' "$PROMPT_FILE" "$MODEL" "$MAX_TOKENS")"

HTTP_CODE=$(curl -s -o "$HTTP_RESPONSE_FILE" -w '%{http_code}' -X POST "$API_URL" \
  -H 'Content-Type: application/json' \
  -H "x-api-key: $API_KEY" \
  -H 'anthropic-version: 2023-06-01' \
  -d "$REQUEST_JSON") || {
  log "ERROR: API call failed"
  telegram "andremacedo.com: API call failed ($PULSE_TYPE)"
  exit 1
}

if [ "$HTTP_CODE" != "200" ]; then
  log "ERROR: HTTP $HTTP_CODE"
  telegram "andremacedo.com: API error HTTP $HTTP_CODE ($PULSE_TYPE)"
  exit 1
fi

export CONTENT
CONTENT="$(python3 -c 'import json,sys; print(json.load(sys.stdin)["content"][0]["text"])' < "$HTTP_RESPONSE_FILE")"
INPUT_TOKENS="$(python3 -c 'import json,sys; print(json.load(sys.stdin).get("usage",{}).get("input_tokens",0))' < "$HTTP_RESPONSE_FILE")"
OUTPUT_TOKENS="$(python3 -c 'import json,sys; print(json.load(sys.stdin).get("usage",{}).get("output_tokens",0))' < "$HTTP_RESPONSE_FILE")"
export TOTAL_TOKENS=$((INPUT_TOKENS + OUTPUT_TOKENS))

log "Tokens: $INPUT_TOKENS in + $OUTPUT_TOKENS out = $TOTAL_TOKENS"

# ── Apply changes ──────────────────────────────────────────────────
cd "$SITE_DIR"
export SITE_DIR PULSE_TYPE

SUMMARY="$(python3 "$APPLY_SCRIPT")" || {
  log "ERROR: Failed to apply changes"
  telegram "andremacedo.com: apply failed ($PULSE_TYPE)"
  exit 1
}

CURRENT_MOOD="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1])).get("current_mood","unknown"))' "$STATE_FILE")"

log "Applied: $SUMMARY"

# ── Git commit and push ───────────────────────────────────────────
git add -A
git commit -m "agent: ${SUMMARY} | mood: ${CURRENT_MOOD} | pulse: ${PULSE_TYPE}" || log "Nothing to commit"

git push origin main 2>&1 | tee -a "$LOG_FILE" || {
  log "ERROR: git push failed"
  telegram "andremacedo.com: deploy failed. Manual intervention needed."
  exit 1
}

log "Deployed."

# ── Notify ─────────────────────────────────────────────────────────
case "$PULSE_TYPE" in
  daily)  NEXT="daily ~06:00 UTC tomorrow" ;;
  weekly) NEXT="daily ~06:00 UTC tomorrow" ;;
  event)  NEXT="daily ~06:00 UTC" ;;
esac

telegram "andremacedo.com updated | ${SUMMARY} | mood: ${CURRENT_MOOD} | next: ${NEXT}"
log "$PULSE_TYPE complete. Tokens: $TOTAL_TOKENS"
