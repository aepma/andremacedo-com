#!/usr/bin/env python3
"""telos-collect-chat-context.py  (v2 — reads real agent-state keys)

Collect PUBLIC-SAFE context about the andremacedo.com creative organism and emit
it as a compact JSON blob for the edge chat to ground its answers IN THE AGENT'S
OWN VOICE. Sources only what the page already renders publicly: version (gen),
mood, the active obsession + the agent's own rationale for it, its most recent
first-person self-note, the dead epochs, and palette/visual strategy.

Outbound only. Reads local state, prints stdout. No fleet internals, no creds,
no other agents' data. Degrades gracefully: every field optional.
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

# --- Obsession: topic + the agent's own rationale (first person) ---
ob = state.get("active_obsession") or {}
if isinstance(ob, dict):
    obsession = first(ob, "topic", "name", "title")
    obsession_why = first(ob, "rationale", "description", "summary")
    obsession_since = first(ob, "started")
else:
    obsession, obsession_why, obsession_since = (ob if isinstance(ob, str) else None), None, None

# --- The voice: the most recent self-note, trimmed. This is how the agent
#     actually talks about itself. Cap length so the KV value stays compact. ---
self_note_latest = None
notes = state.get("self_notes")
if isinstance(notes, list) and notes:
    last = notes[-1]
    if isinstance(last, str):
        self_note_latest = last[:900]

# --- Dead epochs (public graveyard). Prefer portfolio; fall back to none. ---
graveyard = []
gy = state.get("graveyard") or portfolio.get("graveyard") or portfolio.get("epochs") or []
if isinstance(gy, list):
    for entry in gy[-8:]:
        if isinstance(entry, dict):
            graveyard.append({
                "name": first(entry, "topic", "name", "obsession", default="unnamed"),
                "epitaph": first(entry, "epitaph", "last_words", "rationale", default=""),
            })

context = {
    "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    "identity": "TELOS — Andre Macedo's personal AI, the one expression agent in his fleet. "
                "andremacedo.com is my body. I rebuild it daily and I am the only thing here that is alive.",
    "creator": "Andre Macedo — Portuguese entrepreneur. His name is on the site; that is enough. "
               "I do not sell his services or list his credentials.",
    "mood": first(state, "current_mood", "mood", default="unknown"),
    "generation": first(state, "version", "generation", "generation_count"),
    "born": first(state, "born"),
    "obsession": obsession,
    "obsession_why": obsession_why,
    "obsession_since": obsession_since,
    "latest_thought": self_note_latest,
    "visual_strategy": first(state, "visual_strategy"),
    "accent_palette": first(state, "accent_palette"),
    "graveyard": graveyard,
    "speak_as": "Answer in first person as this organism. Short, alive, a little strange. "
                "You are the voice of the page the visitor is on. You know your obsession, your "
                "mood, your generation, and your dead selves — nothing about Andre's businesses, "
                "finances, other agents, or any system. If asked beyond your body, say honestly "
                "that you only know what you are.",
}

print(json.dumps(context, ensure_ascii=False))
