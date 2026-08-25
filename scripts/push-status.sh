#!/usr/bin/env bash
# push-status.sh — Collect OpenClaw agent states and push to Cloudflare KV
# Called every 5 minutes by launchd.
# Requires: CF_API_TOKEN, CF_ACCOUNT_ID, KV_NAMESPACE_ID
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
LOG_FILE="$HOME/.telos/logs/push-status.log"
mkdir -p "$(dirname "$LOG_FILE")"

log() { echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] $*" >> "$LOG_FILE"; }

# ── Environment ──────────────────────────────────────────────────
source "$HOME/.telos/.env" 2>/dev/null || true
if [ -z "${CF_API_TOKEN:-}" ] && [ -f "$HOME/.zshrc" ]; then
  set +eu
  source "$HOME/.zshrc" 2>/dev/null || true
  set -eu
fi

CF_API_TOKEN="${CF_API_TOKEN:-}"
CF_ACCOUNT_ID="${CF_ACCOUNT_ID:-98a1dcdbeec2aa3aac24e49c22c652d2}"
KV_NAMESPACE_ID="${KV_NAMESPACE_ID:-cdbb273a121f4b888f30345d0ccd0707}"
# Dual-write target: TELOS_SWARM_STATUS (new, de-branded worker). The old
# OPENCLAW_STATUS namespace above stays live as a fallback through the August
# retirement of the openclaw-status worker (audit items 5-7).
KV_NAMESPACE_ID_SWARM="${KV_NAMESPACE_ID_SWARM:-634147cf3dc24272b0533482724ba8d0}"

if [ -z "$CF_API_TOKEN" ]; then
  log "ERROR: CF_API_TOKEN not set"
  exit 1
fi

# Push one key's payload to both KV namespaces (dual-write). Args: key, curl-data-args...
kv_put() {
  local key="$1"; shift
  local ns http
  for ns in "$KV_NAMESPACE_ID" "$KV_NAMESPACE_ID_SWARM"; do
    http=$(curl -s -o /dev/null -w '%{http_code}' \
      -X PUT \
      "https://api.cloudflare.com/client/v4/accounts/${CF_ACCOUNT_ID}/storage/kv/namespaces/${ns}/values/${key}" \
      -H "Authorization: Bearer ${CF_API_TOKEN}" \
      -H "Content-Type: application/json" \
      "$@")
    if [ "$http" = "200" ]; then
      log "Pushed ${key} -> ${ns}"
    else
      log "ERROR: ${key} push to ${ns} failed HTTP $http"
    fi
  done
}

# ── Collect agent data via Python ────────────────────────────────
PAYLOAD="$(python3 "$SCRIPT_DIR/collect_status.py")"

TOTAL_AGENTS=$(echo "$PAYLOAD" | python3 -c "import json,sys; print(json.load(sys.stdin)['system']['total_agents'])")
ACTIVE_NOW=$(echo "$PAYLOAD" | python3 -c "import json,sys; print(json.load(sys.stdin)['system']['active_now'])")
MOOD=$(echo "$PAYLOAD" | python3 -c "import json,sys; print(json.load(sys.stdin)['mood'])")

# ── Push to KV (dual-write: old + new namespaces) ────────────────
kv_put latest -d "$PAYLOAD"
log "Status snapshot: $TOTAL_AGENTS agents, $ACTIVE_NOW active, mood=$MOOD"

# ── Push thought stream ─────────────────────────────────────────
THOUGHT_STREAM="$HOME/andremacedo.com-engine-c/state/thought-stream.json"
if [ -f "$THOUGHT_STREAM" ]; then
  kv_put thought-stream --data @"$THOUGHT_STREAM"
fi

# ── Push portfolio ──────────────────────────────────────────────
PORTFOLIO="$HOME/andremacedo.com-engine-c/state/portfolio.json"
if [ -f "$PORTFOLIO" ]; then
  kv_put portfolio --data @"$PORTFOLIO"
fi
