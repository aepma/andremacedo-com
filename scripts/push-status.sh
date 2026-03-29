#!/usr/bin/env bash
# push-status.sh — Collect OpenClaw agent states and push to Cloudflare KV
# Called every 5 minutes by launchd.
# Requires: CF_API_TOKEN, CF_ACCOUNT_ID, KV_NAMESPACE_ID
set -euo pipefail

LOG_FILE="$HOME/.openclaw/logs/push-status.log"
mkdir -p "$(dirname "$LOG_FILE")"

log() { echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] $*" >> "$LOG_FILE"; }

# ── Environment ──────────────────────────────────────────────────
# Source OpenClaw env and .zshrc for env vars if running from launchd
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

# ── Collect agent data ───────────────────────────────────────────
OPENCLAW_DIR="$HOME/.openclaw"
SITE_DIR="$HOME/andremacedo.com"
AGENTS_DIR="$OPENCLAW_DIR/agents"
GATEWAY_LOG="$OPENCLAW_DIR/logs/gateway.log"

# Build full payload in one Python script — reads real OpenClaw session data
PAYLOAD="$(python3 << 'PYEOF'
import os, json, glob, re
from datetime import datetime, timezone, timedelta

agents_dir = os.path.expanduser("~/.openclaw/agents")
site_dir = os.path.expanduser("~/andremacedo.com")
gateway_log = os.path.expanduser("~/.openclaw/logs/gateway.log")
now = datetime.now(timezone.utc)
today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

agents = []
active_count = 0
total_tokens_today = 0

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

        sessions_dir = os.path.join(agent_path, "sessions")

        # Read sessions.json for metadata (label, updatedAt)
        sessions_meta = os.path.join(sessions_dir, "sessions.json")
        latest_updated = 0
        latest_label = ""
        if os.path.exists(sessions_meta):
            try:
                with open(sessions_meta) as f:
                    meta = json.load(f)
                for key, val in meta.items():
                    updated = val.get("updatedAt", 0)
                    if isinstance(updated, (int, float)) and updated > latest_updated:
                        latest_updated = updated
                        latest_label = val.get("label", "")
            except:
                pass

        if latest_updated > 0:
            ts = datetime.fromtimestamp(latest_updated / 1000, tz=timezone.utc)
            agent["last_active"] = ts.isoformat()
            age_seconds = (now - ts).total_seconds()
            if age_seconds < 600:  # active if updated in last 10 minutes
                agent["status"] = "active"
                active_count += 1

        # Find the most recent session JSONL file
        jsonl_files = glob.glob(os.path.join(sessions_dir, "*.jsonl"))
        if jsonl_files:
            latest_jsonl = max(jsonl_files, key=os.path.getmtime)

            # Read last few lines for: model, last action text, token usage
            try:
                with open(latest_jsonl, 'rb') as f:
                    f.seek(0, 2)
                    size = f.tell()
                    # Read last 4KB for recent messages
                    f.seek(max(0, size - 4096))
                    chunk = f.read().decode('utf-8', errors='ignore')

                lines = chunk.strip().split('\n')
                for line in reversed(lines):
                    try:
                        entry = json.loads(line)
                        msg = entry.get("message", {})
                        if not msg:
                            continue

                        # Extract model from assistant messages
                        if msg.get("model") and agent["model"] == "unknown":
                            agent["model"] = msg["model"]

                        # Extract last action from assistant text content
                        if msg.get("role") == "assistant" and not agent["last_action"]:
                            content = msg.get("content", [])
                            for c in content:
                                if isinstance(c, dict) and c.get("type") == "text":
                                    text = c.get("text", "").strip()
                                    if text:
                                        # Take first sentence or first 100 chars
                                        first_line = text.split('\n')[0][:100]
                                        agent["last_action"] = first_line
                                        break
                                elif isinstance(c, str) and c.strip():
                                    agent["last_action"] = c.strip()[:100]
                                    break

                        # Sum tokens from today's messages
                        ts_str = entry.get("timestamp", "")
                        usage = msg.get("usage", {})
                        if ts_str and usage:
                            try:
                                entry_time = datetime.fromisoformat(ts_str.replace('Z', '+00:00'))
                                if entry_time >= today_start:
                                    agent["tokens_today"] += usage.get("totalTokens", 0)
                                    total_tokens_today += usage.get("totalTokens", 0)
                            except:
                                pass
                    except (json.JSONDecodeError, KeyError):
                        continue
            except:
                pass

        # Fallback: use label from sessions.json as last action
        if not agent["last_action"] and latest_label:
            agent["last_action"] = latest_label

        agents.append(agent)

total_agents = len(agents)

# Read site mood from agent-state.json
mood = "unknown"
state_path = os.path.join(site_dir, "state", "agent-state.json")
if os.path.exists(state_path):
    try:
        with open(state_path) as f:
            mood = json.load(f).get("current_mood", "unknown")
    except:
        pass

# Read gold price from external.json
gold_price = None
ext_path = os.path.join(site_dir, "data", "external.json")
if os.path.exists(ext_path):
    try:
        with open(ext_path) as f:
            gold_price = json.load(f).get("gold_price")
    except:
        pass

# Calculate gateway uptime from first log line timestamp
uptime_hours = 0
if os.path.exists(gateway_log):
    try:
        with open(gateway_log) as f:
            first_line = f.readline()
        m = re.search(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}', first_line)
        if m:
            start = datetime.fromisoformat(m.group(0)).replace(tzinfo=timezone.utc)
            uptime_hours = int((now - start).total_seconds() / 3600)
    except:
        pass

payload = {
    "timestamp": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
    "agents": agents,
    "system": {
        "total_agents": total_agents,
        "active_now": active_count,
        "total_tokens_today": total_tokens_today,
        "uptime_hours": uptime_hours
    },
    "gold_price": gold_price,
    "mood": mood
}

print(json.dumps(payload))
PYEOF
)"

# ── Extract summary for logging ──────────────────────────────────
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
