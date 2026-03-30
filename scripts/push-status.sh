#!/usr/bin/env bash
# push-status.sh — Collect OpenClaw agent states and push to Cloudflare KV
# Called every 5 minutes by launchd.
# Requires: CF_API_TOKEN, CF_ACCOUNT_ID, KV_NAMESPACE_ID
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
LOG_FILE="$HOME/.openclaw/logs/push-status.log"
mkdir -p "$(dirname "$LOG_FILE")"

log() { echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] $*" >> "$LOG_FILE"; }

# ── Environment ──────────────────────────────────────────────────
source "$HOME/.openclaw/.env" 2>/dev/null || true
if [ -z "${CF_API_TOKEN:-}" ] && [ -f "$HOME/.zshrc" ]; then
  set +eu
  source "$HOME/.zshrc" 2>/dev/null || true
  set -eu
fi

CF_API_TOKEN="${CF_API_TOKEN:-}"
CF_ACCOUNT_ID="${CF_ACCOUNT_ID:-98a1dcdbeec2aa3aac24e49c22c652d2}"
KV_NAMESPACE_ID="${KV_NAMESPACE_ID:-cdbb273a121f4b888f30345d0ccd0707}"

if [ -z "$CF_API_TOKEN" ]; then
  log "ERROR: CF_API_TOKEN not set"
  exit 1
fi

# ── Collect agent data via Python ────────────────────────────────
PAYLOAD="$(python3 "$SCRIPT_DIR/collect_status.py")"

TOTAL_AGENTS=$(echo "$PAYLOAD" | python3 -c "import json,sys; print(json.load(sys.stdin)['system']['total_agents'])")
ACTIVE_NOW=$(echo "$PAYLOAD" | python3 -c "import json,sys; print(json.load(sys.stdin)['system']['active_now'])")
MOOD=$(echo "$PAYLOAD" | python3 -c "import json,sys; print(json.load(sys.stdin)['mood'])")

# ── Push to KV ───────────────────────────────────────────────────
HTTP_CODE=$(curl -s -o /dev/null -w '%{http_code}' \
  -X PUT \
  "https://api.cloudflare.com/client/v4/accounts/${CF_ACCOUNT_ID}/storage/kv/namespaces/${KV_NAMESPACE_ID}/values/latest" \
  -H "Authorization: Bearer ${CF_API_TOKEN}" \
  -H "Content-Type: application/json" \
  -d "$PAYLOAD")

if [ "$HTTP_CODE" = "200" ]; then
  log "Pushed status: $TOTAL_AGENTS agents, $ACTIVE_NOW active, mood=$MOOD"
else
  log "ERROR: KV push failed HTTP $HTTP_CODE"
fi

# ── Push thought stream ─────────────────────────────────────────
THOUGHT_STREAM="$HOME/andremacedo.com/state/thought-stream.json"
if [ -f "$THOUGHT_STREAM" ]; then
  TS_CODE=$(curl -s -o /dev/null -w '%{http_code}' \
    -X PUT \
    "https://api.cloudflare.com/client/v4/accounts/${CF_ACCOUNT_ID}/storage/kv/namespaces/${KV_NAMESPACE_ID}/values/thought-stream" \
    -H "Authorization: Bearer ${CF_API_TOKEN}" \
    -H "Content-Type: application/json" \
    --data @"$THOUGHT_STREAM")
  if [ "$TS_CODE" = "200" ]; then
    log "Pushed thought-stream"
  else
    log "ERROR: thought-stream push failed HTTP $TS_CODE"
  fi
fi

# ── Push portfolio ──────────────────────────────────────────────
PORTFOLIO="$HOME/andremacedo.com/state/portfolio.json"
if [ -f "$PORTFOLIO" ]; then
  PF_CODE=$(curl -s -o /dev/null -w '%{http_code}' \
    -X PUT \
    "https://api.cloudflare.com/client/v4/accounts/${CF_ACCOUNT_ID}/storage/kv/namespaces/${KV_NAMESPACE_ID}/values/portfolio" \
    -H "Authorization: Bearer ${CF_API_TOKEN}" \
    -H "Content-Type: application/json" \
    --data @"$PORTFOLIO")
  if [ "$PF_CODE" = "200" ]; then
    log "Pushed portfolio"
  else
    log "ERROR: portfolio push failed HTTP $PF_CODE"
  fi
fi
