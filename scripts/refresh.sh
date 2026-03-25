#!/usr/bin/env bash
# refresh.sh — Fetch gold price + Fort Lauderdale weather, write to data/external.json
# No LLM calls. Runs every 6 hours.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SITE_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
EXTERNAL_FILE="$SITE_DIR/data/external.json"
LOG_FILE="$HOME/.openclaw/logs/andremacedo-refresh.log"
mkdir -p "$(dirname "$LOG_FILE")"

log() { echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] $*" >> "$LOG_FILE"; }

# ── Fetch gold spot price ──────────────────────────────────────────
GOLD_USD=""
# Primary: gold-api.com free endpoint (no key needed)
GOLD_RESPONSE="$(curl -s --max-time 10 "https://api.gold-api.com/price/XAU" 2>/dev/null)" || true

if [ -n "$GOLD_RESPONSE" ]; then
  GOLD_USD="$(echo "$GOLD_RESPONSE" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    p = data.get('price', '')
    if p: print(p)
    else: print('')
except: print('')
" 2>/dev/null)" || true
fi

# If still empty, keep previous value
if [ -z "$GOLD_USD" ] && [ -f "$EXTERNAL_FILE" ]; then
  GOLD_USD="$(python3 -c "import json; print(json.load(open('$EXTERNAL_FILE')).get('gold_usd','unknown'))" 2>/dev/null)" || GOLD_USD="unknown"
  log "Gold fetch failed, keeping previous value: $GOLD_USD"
fi

[ -z "$GOLD_USD" ] && GOLD_USD="unknown"

# ── Fetch Fort Lauderdale weather ──────────────────────────────────
WEATHER_JSON="$(curl -s --max-time 10 "https://wttr.in/Fort+Lauderdale?format=j1" 2>/dev/null)" || WEATHER_JSON=""

WEATHER_TEMP=""
WEATHER_DESC=""
WEATHER_HUMIDITY=""

if [ -n "$WEATHER_JSON" ]; then
  WEATHER_DATA="$(echo "$WEATHER_JSON" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    cc = data.get('current_condition', [{}])[0]
    temp_f = cc.get('temp_F', '')
    desc = cc.get('weatherDesc', [{}])[0].get('value', '')
    humidity = cc.get('humidity', '')
    print(f'{temp_f}|{desc}|{humidity}')
except: print('||')
" 2>/dev/null)" || WEATHER_DATA="||"

  WEATHER_TEMP="$(echo "$WEATHER_DATA" | cut -d'|' -f1)"
  WEATHER_DESC="$(echo "$WEATHER_DATA" | cut -d'|' -f2)"
  WEATHER_HUMIDITY="$(echo "$WEATHER_DATA" | cut -d'|' -f3)"
fi

[ -z "$WEATHER_TEMP" ] && WEATHER_TEMP="unknown"
[ -z "$WEATHER_DESC" ] && WEATHER_DESC="unknown"
[ -z "$WEATHER_HUMIDITY" ] && WEATHER_HUMIDITY="unknown"

# ── Write external.json ───────────────────────────────────────────
NOW="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

python3 -c "
import json
data = {
    'gold_usd': '$GOLD_USD' if '$GOLD_USD' == 'unknown' else float('$GOLD_USD') if '$GOLD_USD'.replace('.','',1).isdigit() else '$GOLD_USD',
    'gold_fetched_at': '$NOW',
    'weather': {
        'location': 'Fort Lauderdale, FL',
        'temp_f': '$WEATHER_TEMP',
        'description': '$WEATHER_DESC',
        'humidity': '$WEATHER_HUMIDITY',
        'fetched_at': '$NOW'
    },
    'date_context': {
        'date': '$(date -u +%Y-%m-%d)',
        'day_of_week': '$(date -u +%A)',
        'season': 'spring' if 3 <= $(date -u +%-m) <= 5 else 'summer' if 6 <= $(date -u +%-m) <= 8 else 'autumn' if 9 <= $(date -u +%-m) <= 11 else 'winter'
    }
}
with open('$EXTERNAL_FILE', 'w') as f:
    json.dump(data, f, indent=2)
print(json.dumps(data, indent=2))
" || {
  log "ERROR: Failed to write external.json"
  exit 1
}

log "Refreshed: gold=$GOLD_USD temp=${WEATHER_TEMP}F ${WEATHER_DESC}"
