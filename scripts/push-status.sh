#!/usr/bin/env bash
# push-status.sh — Collect OpenClaw agent states and push to Cloudflare KV
# Called every 5 minutes by launchd.
# Requires: CF_API_TOKEN, CF_ACCOUNT_ID, KV_NAMESPACE_ID
set -euo pipefail

LOG_FILE="$HOME/.openclaw/logs/push-status.log"
mkdir -p "$(dirname "$LOG_FILE")"

log() { echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] $*" >> "$LOG_FILE"; }

# ── Environment ──────────────────────────────────────────────────
# Source .zshrc for env vars if running from launchd
if [ -z "${CF_API_TOKEN:-}" ] && [ -f "$HOME/.zshrc" ]; then
  set +eu
  source "$HOME/.zshrc" 2>/dev/null || true
  set -eu
fi

CF_API_TOKEN="${CF_API_TOKEN:-}"
CF_ACCOUNT_ID="${CF_ACCOUNT_ID:-98a1dcdbeec2aa3aac24e49c22c652d2}"
KV_NAMESPACE_ID="${KV_NAMESPACE_ID:-TODO_REPLACE}"

if [ -z "$CF_API_TOKEN" ]; then
  log "ERROR: CF_API_TOKEN not set"
  exit 1
fi

# ── Collect agent data ───────────────────────────────────────���───
OPENCLAW_DIR="$HOME/.openclaw"
SITE_DIR="$HOME/andremacedo.com"

# TODO: Adjust these paths when OpenClaw session file format is confirmed
# Read agent configs
AGENTS_DIR="$OPENCLAW_DIR/agents"
SESSIONS_DIR="$OPENCLAW_DIR/sessions"
GATEWAY_LOG="$OPENCLAW_DIR/logs/gateway.log"

# Count agents
TOTAL_AGENTS=0
ACTIVE_NOW=0
AGENTS_JSON="[]"

if [ -d "$AGENTS_DIR" ]; then
  TOTAL_AGENTS=$(ls -d "$AGENTS_DIR"/*/ 2>/dev/null | wc -l | tr -d ' ')

  # Build agents array from agent directories
  AGENTS_JSON="$(python3 << 'PYEOF'
import os, json, glob
from datetime import datetime, timezone

agents_dir = os.path.expanduser("~/.openclaw/agents")
sessions_dir = os.path.expanduser("~/.openclaw/sessions")
logs_dir = os.path.expanduser("~/.openclaw/logs")

agents = []
active_count = 0

if os.path.isdir(agents_dir):
    for agent_name in sorted(os.listdir(agents_dir)):
        agent_path = os.path.join(agents_dir, agent_name)
        if not os.path.isdir(agent_path):
            continue

        agent = {
            "id": agent_name,
            "status": "idle",
            "last_action": "",
            "last_active": "",
            "model": "unknown",
            "tokens_today": 0
        }

        # TODO: Read agent config for model info
        config_path = os.path.join(agent_path, "config.json")
        if os.path.exists(config_path):
            try:
                with open(config_path) as f:
                    cfg = json.load(f)
                agent["model"] = cfg.get("model", "unknown")
            except:
                pass

        # TODO: Read session file for last action and status
        session_path = os.path.join(sessions_dir, f"{agent_name}.json")
        if os.path.exists(session_path):
            try:
                mtime = os.path.getmtime(session_path)
                last_active = datetime.fromtimestamp(mtime, tz=timezone.utc)
                agent["last_active"] = last_active.isoformat()
                # Consider active if modified in last 10 minutes
                age_seconds = (datetime.now(timezone.utc) - last_active).total_seconds()
                if age_seconds < 600:
                    agent["status"] = "active"
                    active_count += 1
            except:
                pass

        # TODO: Read recent log for last action description
        log_path = os.path.join(logs_dir, f"{agent_name}.log")
        if os.path.exists(log_path):
            try:
                with open(log_path, 'rb') as f:
                    f.seek(0, 2)
                    size = f.tell()
                    f.seek(max(0, size - 500))
                    last_lines = f.read().decode('utf-8', errors='ignore').strip().split('\n')
                    if last_lines:
                        agent["last_action"] = last_lines[-1][:120]
            except:
                pass

        agents.append(agent)

print(json.dumps({"agents": agents, "active": active_count}))
PYEOF
  )"

  ACTIVE_NOW=$(echo "$AGENTS_JSON" | python3 -c "import json,sys; print(json.load(sys.stdin)['active'])")
  AGENTS_ARRAY=$(echo "$AGENTS_JSON" | python3 -c "import json,sys; print(json.dumps(json.load(sys.stdin)['agents']))")
else
  AGENTS_ARRAY="[]"
fi

# Read site mood from agent-state.json
MOOD="unknown"
if [ -f "$SITE_DIR/state/agent-state.json" ]; then
  MOOD=$(python3 -c "import json; print(json.load(open('$SITE_DIR/state/agent-state.json')).get('current_mood','unknown'))")
fi

# Read gold price from external.json
GOLD_PRICE="null"
if [ -f "$SITE_DIR/data/external.json" ]; then
  GOLD_PRICE=$(python3 -c "import json; print(json.load(open('$SITE_DIR/data/external.json')).get('gold_price', 'null'))")
fi

# Calculate uptime from gateway log first line timestamp
UPTIME_HOURS=0
if [ -f "$GATEWAY_LOG" ]; then
  FIRST_LINE=$(head -1 "$GATEWAY_LOG" 2>/dev/null || echo "")
  if [ -n "$FIRST_LINE" ]; then
    UPTIME_HOURS=$(python3 -c "
from datetime import datetime, timezone
import re, sys
line = '''$FIRST_LINE'''
m = re.search(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}', line)
if m:
    start = datetime.fromisoformat(m.group(0)).replace(tzinfo=timezone.utc)
    now = datetime.now(timezone.utc)
    print(int((now - start).total_seconds() / 3600))
else:
    print(0)
" 2>/dev/null || echo "0")
  fi
fi

# TODO: Compute total_tokens_today from session logs
TOTAL_TOKENS_TODAY=0

# ── Build payload ────────────────────────────────────────────────
NOW="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

PAYLOAD=$(python3 -c "
import json
print(json.dumps({
    'timestamp': '$NOW',
    'agents': $AGENTS_ARRAY,
    'system': {
        'total_agents': $TOTAL_AGENTS,
        'active_now': $ACTIVE_NOW,
        'total_tokens_today': $TOTAL_TOKENS_TODAY,
        'uptime_hours': $UPTIME_HOURS
    },
    'gold_price': $GOLD_PRICE,
    'mood': '$MOOD'
}))
")

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
