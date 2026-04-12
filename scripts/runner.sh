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

# Per-site logs and failure tracking (local to the site repo)
SITE_LOG_DIR="$SITE_DIR/logs"
ERROR_LOG="$SITE_LOG_DIR/build-errors.log"
BUILD_LOG="$SITE_LOG_DIR/build-$(date -u +%Y-%m-%d).log"
FAILURE_COUNTER="$SITE_DIR/state/build-failures.count"
FAILURE_THRESHOLD=3
mkdir -p "$SITE_LOG_DIR"

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

# Route build errors to the local error log. No Telegram noise on individual runs.
log_error() {
  echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] [$PULSE_TYPE] $*" >> "$ERROR_LOG"
  log "ERROR: $*"
}

# Consecutive-failure counter — launchd retries via the next scheduled run.
# After $FAILURE_THRESHOLD consecutive failures, send one Telegram and reset.
read_failure_count() {
  if [ -f "$FAILURE_COUNTER" ]; then cat "$FAILURE_COUNTER"; else echo 0; fi
}

record_failure() {
  local count
  count=$(read_failure_count)
  count=$((count + 1))
  echo "$count" > "$FAILURE_COUNTER"
  if [ "$count" -ge "$FAILURE_THRESHOLD" ]; then
    telegram "andremacedo.com daily build failed ($count consecutive runs). Check $ERROR_LOG"
    echo 0 > "$FAILURE_COUNTER"
  fi
}

record_success() {
  echo 0 > "$FAILURE_COUNTER"
}

# ── Pre-flight ─────────────────────────────────────────────────────
if [ -z "$API_KEY" ]; then
  log_error "ANTHROPIC_API_KEY not set"
  record_failure
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
  echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] [$PULSE_TYPE] Token ceiling reached ($MONTHLY_USED/$MONTHLY_CEILING). Skipping." >> "$ERROR_LOG"
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
elif [ "$PULSE_TYPE" = "daily" ]; then MAX_TOKENS=16000
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
  log_error "API call failed (curl)"
  record_failure
  exit 1
}

if [ "$HTTP_CODE" != "200" ]; then
  # Capture the API error body for diagnosis, no Telegram noise.
  {
    echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] [$PULSE_TYPE] API error HTTP $HTTP_CODE"
    head -c 2000 "$HTTP_RESPONSE_FILE" 2>/dev/null || true
    echo ""
  } >> "$ERROR_LOG"
  log "ERROR: HTTP $HTTP_CODE (details in $ERROR_LOG)"
  record_failure
  exit 1
fi

export CONTENT
CONTENT="$(python3 -c 'import json,sys; print(json.load(sys.stdin)["content"][0]["text"])' < "$HTTP_RESPONSE_FILE")"
INPUT_TOKENS="$(python3 -c 'import json,sys; print(json.load(sys.stdin).get("usage",{}).get("input_tokens",0))' < "$HTTP_RESPONSE_FILE")"
OUTPUT_TOKENS="$(python3 -c 'import json,sys; print(json.load(sys.stdin).get("usage",{}).get("output_tokens",0))' < "$HTTP_RESPONSE_FILE")"
export TOTAL_TOKENS=$((INPUT_TOKENS + OUTPUT_TOKENS))

log "Tokens: $INPUT_TOKENS in + $OUTPUT_TOKENS out = $TOTAL_TOKENS"

# Write session entry for cost-report.sh auto-discovery
SESSIONS_DIR="$HOME/.openclaw/agents/andremacedo-creative/sessions"
mkdir -p "$SESSIONS_DIR"
SESSION_FILE="$SESSIONS_DIR/$(date -u +%Y-%m-%d).jsonl"
EPOCH_MS=$(python3 -c "import time; print(int(time.time()*1000))")
python3 -c "
import json
entry = {
    'type': 'message',
    'message': {
        'role': 'assistant',
        'model': 'claude-opus-4-6',
        'timestamp': $EPOCH_MS,
        'usage': {
            'input': $INPUT_TOKENS,
            'output': $OUTPUT_TOKENS,
            'cacheRead': 0,
            'cacheWrite': 0,
            'totalTokens': $TOTAL_TOKENS
        }
    }
}
print(json.dumps(entry))
" >> "$SESSION_FILE"

# ── Apply changes ──────────────────────────────────────────────────
cd "$SITE_DIR"
export SITE_DIR PULSE_TYPE

# Capture apply_changes.py output: full text goes to $BUILD_LOG, stderr to $ERROR_LOG,
# and $SUMMARY is the final line only (the short description apply_changes.py prints last).
APPLY_STDOUT="$(mktemp)"
if ! python3 "$APPLY_SCRIPT" >"$APPLY_STDOUT" 2>>"$ERROR_LOG"; then
  log_error "Failed to apply changes"
  cat "$APPLY_STDOUT" >> "$ERROR_LOG"
  rm -f "$APPLY_STDOUT"
  record_failure
  exit 1
fi

# Append this run's full apply output to the daily build log for diagnosis
{
  echo "=== $(date -u +%Y-%m-%dT%H:%M:%SZ) [$PULSE_TYPE] apply_changes output ==="
  cat "$APPLY_STDOUT"
  echo ""
} >> "$BUILD_LOG"

# Count change types from the full output for the brief Telegram summary.
# awk is used (not grep -c) so that zero matches return "0" cleanly under set -e + pipefail.
CONTRAST_COUNT=$(awk '/contrast-gate/ {n++} END {print n+0}' "$APPLY_STDOUT")
SECTION_COUNT=$(awk '/replaced section|created section|deleted section|killed section/ {n++} END {print n+0}' "$APPLY_STDOUT")

SUMMARY="$(tail -n 1 "$APPLY_STDOUT")"
rm -f "$APPLY_STDOUT"

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

# ── Archive current generation before deploy ─────────────────────
ARCHIVE_DIR="$HOME/andremacedo.com/archive/$(date +%Y-%m-%d-%H%M%S)"
mkdir -p "$ARCHIVE_DIR"
cp -r "$SITE_DIR"/* "$ARCHIVE_DIR/" 2>/dev/null || true

# Screenshot the current live site for archive
PLAYWRIGHT_PYTHON="$HOME/.openclaw/playwright-venv/bin/python3"
if [ -x "$PLAYWRIGHT_PYTHON" ]; then
  "$PLAYWRIGHT_PYTHON" -c "
import asyncio
from playwright.async_api import async_playwright
async def snap():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page(viewport={'width': 1200, 'height': 800})
        await page.goto('https://andremacedo.com', wait_until='networkidle', timeout=30000)
        await page.screenshot(path='$ARCHIVE_DIR/snapshot.png', full_page=True)
        await browser.close()
asyncio.run(snap())
" 2>/dev/null || echo "Archive screenshot failed (non-fatal)"
fi

# Prune old archives, keep last 20
cd "$HOME/andremacedo.com/archive" && ls -dt */ 2>/dev/null | tail -n +21 | xargs rm -rf 2>/dev/null || true

# ── Deploy to Cloudflare Pages ────────────────────────────────────
log "Deploying to Cloudflare Pages..."

export CLOUDFLARE_ACCOUNT_ID="98a1dcdbeec2aa3aac24e49c22c652d2"
if ! npx wrangler pages deploy "$SITE_DIR" --project-name="andremacedo-com" --branch="main" --commit-dirty=true 2>&1 | tee -a "$LOG_FILE" "$BUILD_LOG"; then
  log_error "wrangler deploy failed"
  record_failure
  exit 1
fi

log "Deployed to andremacedo.com"

# ── Push to GitHub (backup, non-blocking) ─────────────────────────
git -C "$SITE_DIR" push origin main 2>/dev/null || log "WARN: git push failed (non-fatal)"

# Post-deploy contrast verification
bash "$SCRIPT_DIR/contrast-check.sh" "$SITE_DIR" 2>/dev/null || echo "Contrast check failed (non-fatal)"

# ── Notify ─────────────────────────────────────────────────────────
# Mark the run as successful: reset the consecutive-failure counter.
record_success

# Brief success message. Full technical output is in $BUILD_LOG.
FITNESS="$(python3 -c '
import json, sys
try:
    g = json.load(open(sys.argv[1]))
    log = g.get("fitness_log", [])
    if log:
        total = log[-1].get("total")
        print(total if total is not None else "n/a")
    else:
        print("n/a")
except Exception:
    print("n/a")
' "$SITE_DIR/state/genome.json")"

TG_MSG="andremacedo.com updated
Mood: ${CURRENT_MOOD} | Fitness: ${FITNESS}
${CONTRAST_COUNT} contrast fixes | ${SECTION_COUNT} section changes"

telegram "$TG_MSG"
log "$PULSE_TYPE complete. Tokens: $TOTAL_TOKENS. Contrast: $CONTRAST_COUNT, sections: $SECTION_COUNT, fitness: $FITNESS"
