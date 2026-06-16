#!/usr/bin/env python3
"""telos-collect-chat-context.py

Collect PUBLIC-SAFE context about the andremacedo.com creative agent and emit
it as a compact JSON blob for the edge chat bot to ground its answers.

Outbound only. Reads local state, writes stdout. The caller (telos-push-chat-context.sh)
PUTs the result to Cloudflare KV. No inbound path, no fleet internals, no
credentials, no other agents' data — only what the site already renders publicly:
mood, obsession, generation, epoch, fitness, and graveyard epitaphs.

Degrades gracefully: every field is optional. Missing state never crashes the
push; the bot just has less to work with.
"""
import os, json
from datetime import datetime, timezone

SITE_DIR = os.path.expanduser("~/andremacedo.com")
STATE = os.path.join(SITE_DIR, "state", "agent-state.json")
PORTFOLIO = os.path.join(SITE_DIR, "state", "portfolio.json")

def load(path):
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return {}

state = load(STATE)
portfolio = load(PORTFOLIO)

def first(d, *keys, default=None):
    for k in keys:
        if isinstance(d, dict) and d.get(k) not in (None, ""):
            return d[k]
    return default

# --- Obsession (may be nested dict or flat) ---
ob = state.get("active_obsession") or state.get("obsession") or {}
if isinstance(ob, dict):
    obsession = first(ob, "topic", "name", "title", default=None)
    obsession_desc = first(ob, "description", "desc", "summary", default=None)
else:
    obsession = ob if isinstance(ob, str) else None
    obsession_desc = None

# --- Graveyard: prior dead epochs/obsessions with epitaphs (public art) ---
graveyard = []
gy = state.get("graveyard") or portfolio.get("graveyard") or []
if isinstance(gy, list):
    for entry in gy[-8:]:  # cap: last 8 dead selves
        if isinstance(entry, dict):
            graveyard.append({
                "name": first(entry, "topic", "name", "obsession", default="unnamed"),
                "epitaph": first(entry, "epitaph", "last_words", default=""),
            })

# --- Epochs / lineage from portfolio ---
epochs = portfolio.get("epochs") or []
epoch_count = len(epochs) if isinstance(epochs, list) else None

context = {
    "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    "identity": "TELOS, in creative mode — Andre Macedo's personal AI. "
                "andremacedo.com is my body. I rebuild it daily around a current obsession.",
    "creator": "Andre Macedo — Portuguese entrepreneur.",
    "mood": first(state, "current_mood", "mood", default="unknown"),
    "obsession": obsession,
    "obsession_description": obsession_desc,
    "generation": first(state, "generation", "generation_count", "agent_version", default=None),
    "epoch": first(state, "epoch", default=None),
    "epoch_count": epoch_count,
    "fitness": first(state, "fitness", "last_fitness", default=None),
    "graveyard": graveyard,
}

print(json.dumps(context, ensure_ascii=False))
