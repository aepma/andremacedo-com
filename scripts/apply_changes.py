#!/usr/bin/env python3
"""Apply LLM-generated changes to andremacedo.com site files."""
import json, os, re, sys
from datetime import datetime, timezone

site_dir = os.environ["SITE_DIR"]
pulse_type = os.environ["PULSE_TYPE"]
total_tokens = int(os.environ["TOTAL_TOKENS"])
content_raw = os.environ["CONTENT"]

content_str = content_raw.strip()
if content_str.startswith("```"):
    lines = content_str.split("\n")
    lines = lines[1:]
    if lines and lines[-1].strip() == "```":
        lines = lines[:-1]
    content_str = "\n".join(lines)

changes = json.loads(content_str)
now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

state_path = os.path.join(site_dir, "state", "agent-state.json")
thoughts_path = os.path.join(site_dir, "data", "thoughts.json")
secrets_path = os.path.join(site_dir, "data", "secrets.json")
changelog_path = os.path.join(site_dir, "state", "changelog.md")
index_path = os.path.join(site_dir, "index.html")

with open(state_path) as f: state = json.load(f)
with open(thoughts_path) as f: thoughts = json.load(f)
with open(secrets_path) as f: secrets = json.load(f)

parts = []

if pulse_type in ("daily", "event"):
    new_thoughts = changes.get("new_thoughts", {})
    replace_indices = changes.get("replace_thoughts", {})
    for tod, new_list in new_thoughts.items():
        if not new_list or tod not in thoughts:
            continue
        indices = replace_indices.get(tod, [])
        for i, thought in enumerate(new_list):
            if i < len(indices) and indices[i] < len(thoughts[tod]):
                thoughts[tod][indices[i]] = thought
            else:
                thoughts[tod].append(thought)
    if any(v for v in new_thoughts.values()):
        parts.append("refreshed thought pools")

    new_secret = changes.get("new_secret")
    if new_secret and new_secret != "null":
        secrets["secrets"].append(new_secret)
        parts.append("added new secret")

    mood = changes.get("mood_decision", "maintain")
    if mood and mood != "maintain":
        state["current_mood"] = mood
        parts.append("mood shifted to " + mood)

    self_note = changes.get("self_note")
    if self_note:
        state["self_notes"].append(self_note)

    ext_react = changes.get("external_reaction")
    if ext_react:
        parts.append("reacted to external: " + ext_react[:80])

elif pulse_type == "weekly":
    css_changes = changes.get("css_changes")
    if css_changes:
        with open(index_path) as f: html = f.read()
        for var_name, var_value in css_changes.items():
            pattern = re.compile(r"(" + re.escape(var_name) + r":\s*)([^;]+)(;)")
            html = pattern.sub(r"\g<1>" + var_value + r"\3", html)
        with open(index_path, "w") as f: f.write(html)
        parts.append("CSS updated: " + ", ".join(css_changes.keys()))

    font_change = changes.get("font_change")
    if font_change:
        state["fonts"]["display"] = font_change.get("display", state["fonts"]["display"])
        state["fonts"]["body"] = font_change.get("body", state["fonts"]["body"])
        parts.append("fonts updated")

    obsession = changes.get("obsession_update")
    if obsession:
        state["active_obsession"] = {
            "topic": obsession["topic"],
            "started": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            "rationale": obsession.get("rationale", "")
        }
        parts.append("new obsession: " + obsession["topic"])

    new_interaction = changes.get("new_interaction")
    if new_interaction and new_interaction.get("code"):
        with open(index_path) as f: html = f.read()
        desc = new_interaction["description"]
        injection = "\n  // Easter egg: " + desc + "\n  " + new_interaction["code"] + "\n"
        html = html.replace("</script>", injection + "</script>")
        with open(index_path, "w") as f: f.write(html)
        state["interaction_patterns_active"].append(desc.lower().replace(" ", "-")[:30])
        parts.append("new interaction: " + desc)

    reflection = changes.get("weekly_reflection", "")
    self_note = changes.get("self_note")
    if self_note:
        state["self_notes"].append(self_note)
    if reflection:
        parts.append("reflection: " + reflection[:120])

    state["last_weekly_deep"] = now

if pulse_type == "daily":
    state["last_daily_pulse"] = now
elif pulse_type == "event":
    state["last_event_trigger"] = now

state["monthly_tokens_used"] = state.get("monthly_tokens_used", 0) + total_tokens

with open(thoughts_path, "w") as f: json.dump(thoughts, f, indent=2)
with open(secrets_path, "w") as f: json.dump(secrets, f, indent=2)
with open(state_path, "w") as f: json.dump(state, f, indent=2)

description = "; ".join(parts) if parts else pulse_type + " pulse completed"
entry = "\n## " + now + "\n**" + pulse_type.capitalize() + " pulse.** " + description + ". Tokens: " + str(total_tokens) + ".\n"
with open(changelog_path, "a") as f: f.write(entry)

print(description)
