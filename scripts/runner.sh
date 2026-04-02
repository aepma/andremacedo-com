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

# launchd runs zsh -l -c which is non-interactive, so .zshrc is NOT sourced.
# Source it explicitly if ANTHROPIC_API_KEY is missing.
if [ -z "${ANTHROPIC_API_KEY:-}" ] && [ -f "$HOME/.zshrc" ]; then
  set +eu  # .zshrc may have unbound refs or failing interactive-only commands
  # shellcheck disable=SC1091
  source "$HOME/.zshrc" 2>/dev/null || true
  set -eu
fi

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

# ── Capture screenshot of current site ────────────────────────────
SCREENSHOT="/tmp/andremacedo-current.png"
log "Capturing screenshot..."
bash "$SCRIPT_DIR/screenshot.sh" >> "$LOG_FILE" 2>&1 || {
  log "WARNING: Screenshot capture failed, continuing without visual context"
  rm -f "$SCREENSHOT"
}

# ── Build prompt ───────────────────────────────────────────────────
PROMPT_FILE="$(mktemp)"
HTTP_RESPONSE_FILE="$(mktemp)"
trap 'rm -f "$PROMPT_FILE" "$HTTP_RESPONSE_FILE"' EXIT  # updated below if REQUEST_FILE created

SCREENSHOT_ARG=""
[ -f "$SCREENSHOT" ] && SCREENSHOT_ARG="--screenshot=$SCREENSHOT"

python3 "$SCRIPT_DIR/build_prompt.py" "$PULSE_TYPE" "$STATE_FILE" "$EXTERNAL_FILE" "$INDEX_FILE" "$SOUL_FILE" "$CHANGELOG" "$TODAY" "$DAY_OF_WEEK" "$TOD" $SCREENSHOT_ARG > "$PROMPT_FILE"

if [ "$PULSE_TYPE" = "weekly" ]; then MAX_TOKENS=16000
elif [ "$PULSE_TYPE" = "daily" ]; then MAX_TOKENS=12000
else MAX_TOKENS=10000
fi

# ── Call Anthropic API ─────────────────────────────────────────────
log "Starting $PULSE_TYPE pulse..."

REQUEST_FILE="$(mktemp)"
trap 'rm -f "$PROMPT_FILE" "$HTTP_RESPONSE_FILE" "$REQUEST_FILE"' EXIT
python3 "$SCRIPT_DIR/build_request.py" "$PROMPT_FILE" "$MODEL" "$MAX_TOKENS" "${SCREENSHOT:-}" > "$REQUEST_FILE"

HTTP_CODE=$(curl -s -o "$HTTP_RESPONSE_FILE" -w '%{http_code}' -X POST "$API_URL" \
  -H 'Content-Type: application/json' \
  -H "x-api-key: $API_KEY" \
  -H 'anthropic-version: 2023-06-01' \
  -d @"$REQUEST_FILE") || {
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
GENERATION="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1])).get("generation",0))' "$SITE_DIR/state/genome.json")"

log "Applied: $SUMMARY"

# ── Thought Stream: persist reasoning fragments ──────────────────
THOUGHT_STREAM_FILE="$SITE_DIR/state/thought-stream.json"

python3 -c "
import sys, json, os
from datetime import datetime, timezone

content_raw = os.environ['CONTENT']
content_str = content_raw.strip()
if content_str.startswith('\`\`\`'):
    lines = content_str.split('\n')
    lines = lines[1:]
    if lines and lines[-1].strip() == '\`\`\`':
        lines = lines[:-1]
    content_str = '\n'.join(lines)

data = json.loads(content_str)
gen = sys.argv[1]
stream_file = sys.argv[2]

self_note = data.get('self_note', '')
if isinstance(self_note, dict):
    self_note = str(self_note)
fitness = data.get('fitness_evaluation', {})
fitness_note = fitness.get('note', '') if isinstance(fitness, dict) else ''
weekly = data.get('weekly_reflection', '')

# Load existing stream or initialize
stream = []
if os.path.exists(stream_file):
    try:
        with open(stream_file) as f:
            stream = json.load(f)
    except (json.JSONDecodeError, IOError):
        stream = []

entry = {
    'timestamp': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
    'generation': gen,
    'fragments': []
}

if self_note:
    entry['fragments'].append({'type': 'self_note', 'text': self_note})
if fitness_note:
    entry['fragments'].append({'type': 'fitness_note', 'text': fitness_note})
if weekly:
    entry['fragments'].append({'type': 'weekly_reflection', 'text': weekly})

if entry['fragments']:
    stream.append(entry)
    stream = stream[-100:]
    with open(stream_file, 'w') as f:
        json.dump(stream, f, indent=2)
    print(f'Thought stream: {len(entry[\"fragments\"])} fragments for gen {gen}')
else:
    print('Thought stream: no fragments this pulse')
" "$GENERATION" "$THOUGHT_STREAM_FILE" 2>&1 | tee -a "$LOG_FILE"

# ── Portfolio: rebuild manifest from genome data ─────────────────
python3 -c "
import json, os, sys

site_dir = sys.argv[1]
genome_path = os.path.join(site_dir, 'state', 'genome.json')

with open(genome_path) as f:
    genome = json.load(f)

portfolio = {'epochs': []}

# Dead eras from graveyard
for entry in genome.get('graveyard', []):
    if entry.get('type') == 'era':
        portfolio['epochs'].append({
            'name': entry.get('name', 'unknown'),
            'status': 'archived',
            'generations': entry.get('generations', 0),
            'started': entry.get('started', ''),
            'ended': entry.get('died_date', ''),
            'epitaph': entry.get('epitaph', ''),
            'died_at_generation': entry.get('died_at_generation', 0),
            'artifacts': []
        })

# Current epoch
current_epoch = genome.get('epoch', 'unknown')
current_gen = genome.get('generation', 0)
epoch_started = genome.get('epoch_started', '')
portfolio['epochs'].append({
    'name': current_epoch,
    'status': 'active',
    'generations': current_gen,
    'started': epoch_started,
    'epitaph': None,
    'artifacts': []
})

# Attach dead artifacts to eras by generation range
for entry in genome.get('graveyard', []):
    if entry.get('type') == 'era':
        continue
    artifact = {
        'type': entry.get('type', 'unknown'),
        'name': entry.get('value', entry.get('name', 'unnamed')),
        'epitaph': entry.get('epitaph', ''),
        'died_at_generation': entry.get('died_gen', entry.get('died_at_generation', 0))
    }
    placed = False
    for epoch in portfolio['epochs']:
        if epoch['status'] == 'archived':
            max_gen = epoch.get('died_at_generation', 0)
            if artifact['died_at_generation'] <= max_gen:
                epoch['artifacts'].append(artifact)
                placed = True
                break
    if not placed and portfolio['epochs']:
        portfolio['epochs'][-1]['artifacts'].append(artifact)

portfolio['epochs'].reverse()
portfolio['fitness_trajectory'] = genome.get('fitness_log', [])[-20:]

portfolio_path = os.path.join(site_dir, 'state', 'portfolio.json')
with open(portfolio_path, 'w') as f:
    json.dump(portfolio, f, indent=2)
print(f'Portfolio: {len(portfolio[\"epochs\"])} epochs')
" "$SITE_DIR" 2>&1 | tee -a "$LOG_FILE"

# ── Git commit (for history) ──────────────────────────────────────
git add -A
git commit -m "agent: ${SUMMARY} | mood: ${CURRENT_MOOD} | pulse: ${PULSE_TYPE}" || log "Nothing to commit"

# ── Deploy to Cloudflare Pages ────────────────────────────────────
log "Deploying to Cloudflare Pages..."

export CLOUDFLARE_ACCOUNT_ID="98a1dcdbeec2aa3aac24e49c22c652d2"
npx wrangler pages deploy "$SITE_DIR" --project-name="andremacedo-com" --branch="main" --commit-dirty=true 2>&1 | tee -a "$LOG_FILE" || {
  log "ERROR: wrangler deploy failed"
  telegram "andremacedo.com: deploy failed. Check logs."
  exit 1
}

log "Deployed to andremacedo.com"

# ── Notify ─────────────────────────────────────────────────────────
case "$PULSE_TYPE" in
  daily)  NEXT="daily ~06:00 UTC tomorrow" ;;
  weekly) NEXT="daily ~06:00 UTC tomorrow" ;;
  event)  NEXT="daily ~06:00 UTC" ;;
esac

telegram "andremacedo.com updated | ${SUMMARY} | mood: ${CURRENT_MOOD} | next: ${NEXT}"
log "$PULSE_TYPE complete. Tokens: $TOTAL_TOKENS"
