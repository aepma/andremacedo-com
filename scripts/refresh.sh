#!/usr/bin/env bash
# refresh.sh — Fetch gold price, Fort Lauderdale weather, and Cloudflare analytics, write to data/external.json
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

# ── Fetch Cloudflare Analytics ────────────────────────────────────
CF_ZONE_ID="c0dca0430bf27fa780aa443e7a56b974"
CF_OAUTH_TOKEN=""
WRANGLER_CONFIG="$HOME/.wrangler/config/default.toml"

if [ -f "$WRANGLER_CONFIG" ]; then
  CF_OAUTH_TOKEN="$(python3 -c "
import re
with open('$WRANGLER_CONFIG') as f:
    for line in f:
        m = re.match(r'oauth_token\s*=\s*\"(.+?)\"', line)
        if m:
            print(m.group(1))
            break
" 2>/dev/null)" || CF_OAUTH_TOKEN=""
fi

ANALYTICS_PAGEVIEWS_7D="unknown"
ANALYTICS_VISITORS_7D="unknown"
ANALYTICS_PAGEVIEWS_YESTERDAY="unknown"
ANALYTICS_AVG_DAILY="unknown"
ANALYTICS_TREND="unknown"

if [ -n "$CF_OAUTH_TOKEN" ]; then
  DATE_END="$(date -u +%Y-%m-%d)"
  DATE_START="$(date -u -v-7d +%Y-%m-%d 2>/dev/null || date -u -d '7 days ago' +%Y-%m-%d 2>/dev/null)" || DATE_START=""
  DATE_YESTERDAY="$(date -u -v-1d +%Y-%m-%d 2>/dev/null || date -u -d 'yesterday' +%Y-%m-%d 2>/dev/null)" || DATE_YESTERDAY=""

  if [ -n "$DATE_START" ] && [ -n "$DATE_YESTERDAY" ]; then
    CF_GQL_QUERY='{ "query": "{ viewer { zones(filter: {zoneTag: \"'"$CF_ZONE_ID"'\"}) { httpRequests1dGroups(limit: 7, filter: {date_geq: \"'"$DATE_START"'\", date_leq: \"'"$DATE_END"'\"}, orderBy: [date_ASC]) { dimensions { date } sum { pageViews } uniq { uniques } } } } }" }'

    CF_RESPONSE="$(curl -s --max-time 15 "https://api.cloudflare.com/client/v4/graphql" \
      -H "Authorization: Bearer $CF_OAUTH_TOKEN" \
      -H "Content-Type: application/json" \
      --data "$CF_GQL_QUERY" 2>/dev/null)" || CF_RESPONSE=""

    if [ -n "$CF_RESPONSE" ]; then
      ANALYTICS_DATA="$(echo "$CF_RESPONSE" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    groups = data['data']['viewer']['zones'][0]['httpRequests1dGroups']
    total_pv = sum(g['sum']['pageViews'] for g in groups)
    total_uv = sum(g['uniq']['uniques'] for g in groups)
    n = len(groups)
    avg_daily = round(total_pv / n) if n > 0 else 0
    # Yesterday's pageviews (last entry)
    yesterday_pv = groups[-1]['sum']['pageViews'] if groups else 0
    # Trend: compare yesterday to 7-day average
    if avg_daily == 0:
        trend = 'flat'
    elif yesterday_pv > avg_daily * 1.1:
        trend = 'up'
    elif yesterday_pv < avg_daily * 0.9:
        trend = 'down'
    else:
        trend = 'flat'
    print(f'{total_pv}|{total_uv}|{yesterday_pv}|{avg_daily}|{trend}')
except Exception as e:
    print('||||')
" 2>/dev/null)" || ANALYTICS_DATA="||||"

      A_PV="$(echo "$ANALYTICS_DATA" | cut -d'|' -f1)"
      A_UV="$(echo "$ANALYTICS_DATA" | cut -d'|' -f2)"
      A_YPV="$(echo "$ANALYTICS_DATA" | cut -d'|' -f3)"
      A_AVG="$(echo "$ANALYTICS_DATA" | cut -d'|' -f4)"
      A_TREND="$(echo "$ANALYTICS_DATA" | cut -d'|' -f5)"

      [ -n "$A_PV" ] && ANALYTICS_PAGEVIEWS_7D="$A_PV"
      [ -n "$A_UV" ] && ANALYTICS_VISITORS_7D="$A_UV"
      [ -n "$A_YPV" ] && ANALYTICS_PAGEVIEWS_YESTERDAY="$A_YPV"
      [ -n "$A_AVG" ] && ANALYTICS_AVG_DAILY="$A_AVG"
      [ -n "$A_TREND" ] && ANALYTICS_TREND="$A_TREND"
    fi
  fi
fi

# If analytics fetch failed, try to keep previous values
if [ "$ANALYTICS_PAGEVIEWS_7D" = "unknown" ] && [ -f "$EXTERNAL_FILE" ]; then
  log "Analytics fetch failed, keeping previous values"
  ANALYTICS_PAGEVIEWS_7D="$(python3 -c "import json; print(json.load(open('$EXTERNAL_FILE')).get('site_analytics',{}).get('pageviews_7d','unknown'))" 2>/dev/null)" || ANALYTICS_PAGEVIEWS_7D="unknown"
  ANALYTICS_VISITORS_7D="$(python3 -c "import json; print(json.load(open('$EXTERNAL_FILE')).get('site_analytics',{}).get('unique_visitors_7d','unknown'))" 2>/dev/null)" || ANALYTICS_VISITORS_7D="unknown"
  ANALYTICS_PAGEVIEWS_YESTERDAY="$(python3 -c "import json; print(json.load(open('$EXTERNAL_FILE')).get('site_analytics',{}).get('pageviews_yesterday','unknown'))" 2>/dev/null)" || ANALYTICS_PAGEVIEWS_YESTERDAY="unknown"
  ANALYTICS_AVG_DAILY="$(python3 -c "import json; print(json.load(open('$EXTERNAL_FILE')).get('site_analytics',{}).get('avg_daily_pageviews','unknown'))" 2>/dev/null)" || ANALYTICS_AVG_DAILY="unknown"
  ANALYTICS_TREND="$(python3 -c "import json; print(json.load(open('$EXTERNAL_FILE')).get('site_analytics',{}).get('trend','unknown'))" 2>/dev/null)" || ANALYTICS_TREND="unknown"
fi

# ── Write external.json ───────────────────────────────────────────
NOW="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

python3 -c "
import json

def safe_int(v):
    try: return int(v)
    except: return v

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
    'site_analytics': {
        'pageviews_7d': safe_int('$ANALYTICS_PAGEVIEWS_7D'),
        'unique_visitors_7d': safe_int('$ANALYTICS_VISITORS_7D'),
        'pageviews_yesterday': safe_int('$ANALYTICS_PAGEVIEWS_YESTERDAY'),
        'avg_daily_pageviews': safe_int('$ANALYTICS_AVG_DAILY'),
        'trend': '$ANALYTICS_TREND',
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

log "Refreshed: gold=$GOLD_USD temp=${WEATHER_TEMP}F ${WEATHER_DESC} pv_7d=$ANALYTICS_PAGEVIEWS_7D"
