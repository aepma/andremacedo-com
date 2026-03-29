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

# ── Thought pools (daily/event only) ─────────────────────────────
if pulse_type in ("daily", "event"):
    new_thoughts = changes.get("new_thoughts", {})
    replace_indices = changes.get("replace_thoughts", {})
    if isinstance(new_thoughts, list):
        h = datetime.now(timezone.utc).hour
        if h >= 5 and h < 8: cur_tod = "dawn"
        elif h >= 8 and h < 12: cur_tod = "morning"
        elif h >= 12 and h < 17: cur_tod = "afternoon"
        elif h >= 17 and h < 21: cur_tod = "evening"
        else: cur_tod = "night"
        new_thoughts = {cur_tod: new_thoughts}
    for tod, new_list in new_thoughts.items():
        if not new_list or tod not in thoughts:
            continue
        indices = replace_indices.get(tod, []) if isinstance(replace_indices, dict) else []
        for i, thought in enumerate(new_list):
            if i < len(indices) and indices[i] < len(thoughts[tod]):
                thoughts[tod][indices[i]] = thought
            else:
                thoughts[tod].append(thought)
    if any(v for v in (new_thoughts.values() if isinstance(new_thoughts, dict) else [new_thoughts])):
        parts.append("refreshed thought pools")

    new_secret = changes.get("new_secret")
    if new_secret and new_secret != "null" and new_secret is not None:
        secrets["secrets"].append(str(new_secret))
        parts.append("added new secret")

    mood = changes.get("mood_decision", "maintain")
    if isinstance(mood, dict):
        mood = mood.get("new_mood", mood.get("mood", str(mood)))
    mood = str(mood)
    if mood and mood != "maintain" and mood != "null":
        state["current_mood"] = mood
        parts.append("mood shifted to " + mood)

    ext_react = changes.get("external_reaction")
    if ext_react:
        parts.append("reacted to external: " + str(ext_react)[:80])

# ── Weekly-only: reflection, obsession ────────────────────────────
if pulse_type == "weekly":
    obsession = changes.get("obsession_update")
    if obsession and isinstance(obsession, dict):
        state["active_obsession"] = {
            "topic": obsession["topic"],
            "started": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            "rationale": obsession.get("rationale", "")
        }
        parts.append("new obsession: " + obsession["topic"])

    reflection = changes.get("weekly_reflection", "")
    if reflection:
        parts.append("reflection: " + str(reflection)[:120])

    state["last_weekly_deep"] = now

# ── Self note (all pulse types) ───────────────────────────────────
self_note = changes.get("self_note")
if self_note:
    if isinstance(self_note, dict):
        self_note = str(self_note)
    state["self_notes"].append(self_note)

# ── CSS variable changes (all pulse types) ────────────────────────
css_changes = changes.get("css_changes")
if css_changes and isinstance(css_changes, dict):
    with open(index_path) as f: html = f.read()
    for var_name, var_value in css_changes.items():
        pattern = re.compile(r"(" + re.escape(var_name) + r":\s*)([^;]+)(;)")
        html = pattern.sub(r"\g<1>" + var_value + r"\3", html)
    with open(index_path, "w") as f: f.write(html)
    parts.append("CSS updated: " + ", ".join(css_changes.keys()))

# ── New CSS rules (all pulse types) ───────────────────────────────
new_css_rules = changes.get("new_css_rules")
if new_css_rules and isinstance(new_css_rules, str) and new_css_rules.strip():
    with open(index_path) as f: html = f.read()
    injection = "\n  /* agent-injected rules */\n  " + new_css_rules.strip() + "\n"
    html = html.replace("</style>", injection + "</style>")
    with open(index_path, "w") as f: f.write(html)
    parts.append("added new CSS rules")

# ── Font change with actual HTML rewrite (all pulse types) ────────
font_change = changes.get("font_change")
if font_change and isinstance(font_change, dict):
    display = font_change.get("display", state["fonts"]["display"])
    body = font_change.get("body", state["fonts"]["body"])
    mono = font_change.get("mono", state["fonts"].get("mono", "JetBrains Mono"))
    state["fonts"]["display"] = display
    state["fonts"]["body"] = body
    state["fonts"]["mono"] = mono
    # Rewrite the @import URL in index.html
    with open(index_path) as f: html = f.read()
    font_families = [display, body, mono]
    # Build Google Fonts URL: family=Name:styles&family=Name:styles
    font_params = []
    for fam in font_families:
        encoded = fam.replace(" ", "+")
        if fam == mono:
            font_params.append(f"family={encoded}:wght@300;400;500")
        elif fam == display:
            font_params.append(f"family={encoded}:ital@0;1")
        else:
            font_params.append(f"family={encoded}:ital,wght@0,400;0,500;0,700;1,400;1,500")
    new_import = "https://fonts.googleapis.com/css2?" + "&".join(font_params) + "&display=swap"
    html = re.sub(
        r"@import url\('[^']+'\);",
        f"@import url('{new_import}');",
        html,
        count=1
    )
    html = re.sub(
        r"font-family:\s*'[^']+',\s*Georgia,\s*serif;(\s*/\*\s*display\s*\*/)?",
        f"font-family: '{display}', Georgia, serif;",
        html,
        count=1
    )
    with open(index_path, "w") as f: f.write(html)
    parts.append(f"fonts updated: {display} / {body} / {mono}")

# ── New JS interaction (all pulse types) ──────────────────────────
new_interaction = changes.get("new_interaction")
if new_interaction and isinstance(new_interaction, dict) and new_interaction.get("code"):
    with open(index_path) as f: html = f.read()
    desc = str(new_interaction["description"])
    code = new_interaction["code"]
    injection = "\n  // Easter egg: " + desc + "\n  " + code + "\n"
    html = html.replace("</script>", injection + "</script>")
    with open(index_path, "w") as f: f.write(html)
    state["interaction_patterns_active"].append(desc.lower().replace(" ", "-")[:30])
    parts.append("new interaction: " + desc)

# ── HTML injection at marker comments (all pulse types) ───────────
html_injection = changes.get("html_injection")
# Support both a single dict and a list of dicts
if html_injection:
    injections = [html_injection] if isinstance(html_injection, dict) else html_injection
    if isinstance(injections, list):
        with open(index_path) as f: html = f.read()
        for inj in injections:
            if not isinstance(inj, dict):
                continue
            target = inj.get("target", "")
            position = inj.get("position", "after")
            content = inj.get("html", "")
            if not target or not content:
                continue
            # Sanitize: strip <script> tags from injected HTML
            content = re.sub(r"<script[\s>].*?</script>", "", content, flags=re.DOTALL | re.IGNORECASE)
            # Find the marker comment
            marker = f"<!-- {target} -->"
            if marker not in html:
                continue
            if position == "before":
                html = html.replace(marker, content + "\n" + marker)
            elif position == "replace":
                html = html.replace(marker, content)
            else:  # "after" is default
                html = html.replace(marker, marker + "\n" + content)
        with open(index_path, "w") as f: f.write(html)
        targets = [inj.get("target", "?") for inj in injections if isinstance(inj, dict)]
        parts.append("HTML injected at: " + ", ".join(targets))

# ── Version increment ─────────────────────────────────────────────
state["version"] = state.get("version", 0) + 1
new_version = state["version"]

# Update version string in index.html
with open(index_path) as f: html = f.read()
html = re.sub(r'id="siteVersion">[^<]*<', f'id="siteVersion">v{new_version}<', html)
with open(index_path, "w") as f: f.write(html)

# ── Timestamp bookkeeping ─────────────────────────────────────────
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
