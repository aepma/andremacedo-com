#!/usr/bin/env bash
# telos-push-chat-context.sh — Collect public-safe chat context and push to Cloudflare KV.
# Outbound only. Runs the local collector, validates its JSON, PUTs it to the
# CHAT_KV namespace under key "chat-context" for the edge chat function to read.
# Intended to run every 5 minutes by launchd. Fail-closed: never push non-JSON.
# Requires: CF_API_TOKEN. Optional overrides: CF_ACCOUNT_ID, CHAT_KV_NAMESPACE_ID.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
LOG_FILE="$HOME/.openclaw/logs/telos-push-chat-context.log"
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
CHAT_KV_NAMESPACE_ID="${CHAT_KV_NAMESPACE_ID:-cdbb273a121f4b888f30345d0ccd0707}"

if [ -z "$CF_API_TOKEN" ]; then
  log "ERROR: CF_API_TOKEN not set"
  exit 1
fi

# ── Collect public-safe context via Python ───────────────────────
PAYLOAD="$(python3 "$SCRIPT_DIR/telos-collect-chat-context.py")"

# Fail-closed: never push anything that isn't valid JSON.
if ! printf '%s' "$PAYLOAD" | python3 -c "import json,sys; json.load(sys.stdin)" 2>/dev/null; then
  log "ERROR: collector output is not valid JSON; refusing to push"
  exit 1
fi

MOOD=$(printf '%s' "$PAYLOAD" | python3 -c "import json,sys; print(json.load(sys.stdin).get('mood'))" 2>/dev/null || echo "unknown")

# ── Push to KV (key: chat-context) ───────────────────────────────
HTTP_CODE=$(curl -s -o /dev/null -w '%{http_code}' \
  -X PUT \
  "https://api.cloudflare.com/client/v4/accounts/${CF_ACCOUNT_ID}/storage/kv/namespaces/${CHAT_KV_NAMESPACE_ID}/values/chat-context" \
  -H "Authorization: Bearer ${CF_API_TOKEN}" \
  -H "Content-Type: application/json" \
  -d "$PAYLOAD")

if [ "$HTTP_CODE" = "200" ]; then
  log "Pushed chat-context: mood=$MOOD"
else
  log "ERROR: chat-context push failed HTTP $HTTP_CODE"
  exit 1
fi
