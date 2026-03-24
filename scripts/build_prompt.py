#!/usr/bin/env python3
"""Build prompts for andremacedo.com creative agent."""
import sys, os

pulse_type = sys.argv[1]
state_file = sys.argv[2]
external_file = sys.argv[3]
index_file = sys.argv[4]
soul_file = sys.argv[5]
changelog_file = sys.argv[6]
today = sys.argv[7]
day_of_week = sys.argv[8]
tod = sys.argv[9]

def read_file(path, default=""):
    try:
        with open(path) as f:
            return f.read()
    except FileNotFoundError:
        return default

state = read_file(state_file, "{}")
external = read_file(external_file, "{}")

if pulse_type == "weekly":
    soul = read_file(soul_file)
    changelog_lines = read_file(changelog_file).strip().split("\n")
    changelog_tail = "\n".join(changelog_lines[-40:]) if changelog_lines else ""

    # Extract CSS variables from index.html
    css_vars = ""
    html = read_file(index_file)
    if html:
        import re
        m = re.search(r":root\s*\{[^}]+\}", html)
        if m:
            css_vars = m.group(0)

    prompt = f"""You are the andremacedo.com agent reviewing your week.

Your identity:
{soul}

Your current state:
{state}

Recent changes:
{changelog_tail}

Current CSS variables:
{css_vars}

Tasks:
1. Reflect on this week's creative output. What worked? What felt stale?
2. Decide: Should the color palette shift? New accent color? Typography change?
3. Decide: Is your current obsession still interesting, or is it time for a new one?
4. Optionally: Propose one new interaction pattern or easter egg (provide implementation code).
5. Optionally: Propose structural changes to the page layout.

Respond ONLY in valid JSON with these keys: weekly_reflection, css_changes, font_change, obsession_update, new_interaction, layout_changes, self_note. Use null for fields you skip."""

else:
    prompt = f"""You are the andremacedo.com agent. Here is your current state:
{state}

External context:
{external}

Today is {today}, {day_of_week}. Time of day category: {tod}.

Tasks:
1. Generate 3-5 new thoughts distributed across time-of-day pools. Replace your weakest existing thoughts. Quality over quantity. Voice: think out loud at 2am. Concrete images. Short sentences. Fragments. Real references. No corporate language, no LinkedIn energy. One good line beats three.
2. Optionally generate 1 new secret (only if genuinely interesting).
3. Assess current mood. Should it shift? Output new mood or maintain.
4. Note any external data worth reacting to.

Respond ONLY in valid JSON with keys: new_thoughts, replace_thoughts, new_secret, mood_decision, mood_rationale, external_reaction, self_note."""

print(prompt)
