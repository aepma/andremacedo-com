#!/usr/bin/env python3
"""Apply LLM-generated changes to andremacedo.com site files.

Handles phenotype expression (CSS, HTML, JS changes) and genome tracking
(fitness logging, mutation recording, graveyard management, carrying capacity).
"""
import json, os, re, sys, copy
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
genome_path = os.path.join(site_dir, "state", "genome.json")
index_path = os.path.join(site_dir, "index.html")

with open(state_path) as f: state = json.load(f)
with open(thoughts_path) as f: thoughts = json.load(f)
with open(secrets_path) as f: secrets = json.load(f)
with open(genome_path) as f: genome = json.load(f)

# Snapshot pre-mutation trait values for diff
pre_traits = copy.deepcopy(genome.get("traits", {}))

parts = []
mutations_detected = []
kills_performed = []

# ══════════════════════════════════════════════════════════════════
# PHENOTYPE EXPRESSION — actual site changes
# ══════════════════════════════════════════════════════════════════

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
        mutations_detected.append("content.thoughts")

    new_secret = changes.get("new_secret")
    if new_secret and new_secret != "null" and new_secret is not None:
        secrets["secrets"].append(str(new_secret))
        parts.append("added new secret")
        mutations_detected.append("content.secrets")

    mood = changes.get("mood_decision", "maintain")
    if isinstance(mood, dict):
        mood = mood.get("new_mood", mood.get("mood", str(mood)))
    mood = str(mood)
    if mood and mood != "maintain" and mood != "null":
        state["current_mood"] = mood
        parts.append("mood shifted to " + mood)
        mutations_detected.append("content.mood")

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
        mutations_detected.append("content.obsession")

    epoch_name = changes.get("epoch_name")
    if epoch_name and isinstance(epoch_name, str) and epoch_name != "null":
        genome["epoch"] = epoch_name
        genome["epoch_started"] = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        parts.append("new epoch: " + epoch_name)
        mutations_detected.append("epoch")

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

# ── Accent palette (all pulse types) ──────────────────────────────
accent_palette = changes.get("accent_palette")
if accent_palette and isinstance(accent_palette, dict) and accent_palette.get("base"):
    base = accent_palette["base"]
    with open(index_path) as f: html = f.read()
    html = re.sub(r"(--fg-accent:\s*)([^;]+)(;)", r"\g<1>" + base + r"\3", html)
    for tod_key in ("dawn", "morning", "afternoon", "evening", "night"):
        color = accent_palette.get(tod_key, base)
        html = re.sub(
            r"(" + tod_key + r":\s*\{[^}]*accent:\s*')[^']+(')",
            r"\g<1>" + color + r"\2",
            html
        )
    with open(index_path, "w") as f: f.write(html)
    state["mood_accent_color"] = base
    state["accent_palette"] = accent_palette
    parts.append("accent palette: " + base)
    mutations_detected.append("color.accent")

# ── CSS variable changes (all pulse types) ────────────────────────
css_changes = changes.get("css_changes")
if css_changes and isinstance(css_changes, dict):
    with open(index_path) as f: html = f.read()
    for var_name, var_value in css_changes.items():
        pattern = re.compile(r"(" + re.escape(var_name) + r":\s*)([^;]+)(;)")
        html = pattern.sub(r"\g<1>" + var_value + r"\3", html)
    with open(index_path, "w") as f: f.write(html)
    parts.append("CSS updated: " + ", ".join(css_changes.keys()))
    mutations_detected.append("color.css_vars")

# ── New CSS rules (all pulse types, gene-marked) ─────────────────
new_css_rules = changes.get("new_css_rules")
if new_css_rules and isinstance(new_css_rules, str) and new_css_rules.strip():
    with open(index_path) as f: html = f.read()
    gen = genome.get("generation", 0) + 1
    gene_id = f"gen{gen}-css"
    injection = f"\n  /* @gene:{gene_id}:start */\n  {new_css_rules.strip()}\n  /* @gene:{gene_id}:end */\n"
    html = html.replace("</style>", injection + "</style>")
    with open(index_path, "w") as f: f.write(html)
    parts.append("added new CSS rules")
    mutations_detected.append("atmosphere.css_rules")

# ── Font change with actual HTML rewrite (all pulse types) ────────
font_change = changes.get("font_change")
if font_change and isinstance(font_change, dict):
    display = font_change.get("display", state["fonts"]["display"])
    body = font_change.get("body", state["fonts"]["body"])
    mono = font_change.get("mono", state["fonts"].get("mono", "JetBrains Mono"))
    state["fonts"]["display"] = display
    state["fonts"]["body"] = body
    state["fonts"]["mono"] = mono
    with open(index_path) as f: html = f.read()
    font_families = [display, body, mono]
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
    html = re.sub(r"@import url\('[^']+'\);", f"@import url('{new_import}');", html, count=1)
    html = re.sub(
        r"font-family:\s*'[^']+',\s*Georgia,\s*serif;(\s*/\*\s*display\s*\*/)?",
        f"font-family: '{display}', Georgia, serif;",
        html, count=1
    )
    with open(index_path, "w") as f: f.write(html)
    parts.append(f"fonts updated: {display} / {body} / {mono}")
    mutations_detected.append("typography")

# ── New JS interaction (all pulse types, gene-marked) ─────────────
new_interaction = changes.get("new_interaction")
if new_interaction and isinstance(new_interaction, dict) and new_interaction.get("code"):
    with open(index_path) as f: html = f.read()
    desc = str(new_interaction["description"])
    code = new_interaction["code"]
    gene_id = desc.lower().replace(" ", "-")[:30]
    injection = f"\n  // @gene:{gene_id}:start\n  // Easter egg: {desc}\n  {code}\n  // @gene:{gene_id}:end\n"
    html = html.replace("</script>", injection + "</script>")
    with open(index_path, "w") as f: f.write(html)
    state["interaction_patterns_active"].append(desc.lower().replace(" ", "-")[:30])
    parts.append("new interaction: " + desc)
    mutations_detected.append("interaction." + gene_id)

# ── HTML injection at marker comments (all pulse types, gene-marked) ──
html_injection = changes.get("html_injection")
if html_injection:
    injections = [html_injection] if isinstance(html_injection, dict) else html_injection
    if isinstance(injections, list):
        with open(index_path) as f: html = f.read()
        gen = genome.get("generation", 0) + 1
        for idx, inj in enumerate(injections):
            if not isinstance(inj, dict):
                continue
            target = inj.get("target", "")
            position = inj.get("position", "after")
            content = inj.get("html", "")
            if not target or not content:
                continue
            content = re.sub(r"<script[\s>].*?</script>", "", content, flags=re.DOTALL | re.IGNORECASE)
            marker = f"<!-- {target} -->"
            if marker not in html:
                continue
            gene_id = f"gen{gen}-{target.replace('INJECT:', '').replace(':', '-')}"
            wrapped = f"<!-- @gene:{gene_id}:start -->\n{content}\n<!-- @gene:{gene_id}:end -->"
            if position == "before":
                html = html.replace(marker, wrapped + "\n" + marker)
            elif position == "replace":
                html = html.replace(marker, wrapped)
            else:
                html = html.replace(marker, marker + "\n" + wrapped)
        with open(index_path, "w") as f: f.write(html)
        targets = [inj.get("target", "?") for inj in injections if isinstance(inj, dict)]
        parts.append("HTML injected at: " + ", ".join(targets))
        mutations_detected.append("layout.html_injection")


# ══════════════════════════════════════════════════════════════════
# KILLS — removing things from the site
# ══════════════════════════════════════════════════════════════════

kills = changes.get("kills")
if kills and isinstance(kills, list):
    with open(index_path) as f: html = f.read()
    html_changed = False

    for kill in kills:
        if not isinstance(kill, dict):
            continue
        ktype = kill.get("type", "")
        target = kill.get("target", "")
        epitaph = kill.get("epitaph", "no epitaph")

        if ktype == "thought" and target:
            # target format: "pool:index" e.g. "night:5" or "night" (kills last)
            if ":" in target:
                pool, idx_str = target.split(":", 1)
                try: idx = int(idx_str)
                except ValueError: continue
            else:
                pool = target
                idx = -1  # last item

            if pool in thoughts and thoughts[pool]:
                if idx == -1:
                    idx = len(thoughts[pool]) - 1
                if 0 <= idx < len(thoughts[pool]):
                    dead = thoughts[pool].pop(idx)
                    dead_str = dead if isinstance(dead, str) else str(dead.get("text", dead))[:80]
                    genome["graveyard"].append({
                        "type": "thought", "value": dead_str,
                        "died_gen": genome.get("generation", 0) + 1,
                        "epitaph": epitaph
                    })
                    kills_performed.append(f"thought:{pool}[{idx}]")
                    parts.append(f"killed thought from {pool}[{idx}]")

        elif ktype == "secret" and target:
            try: idx = int(target)
            except ValueError: continue
            if 0 <= idx < len(secrets["secrets"]):
                dead = secrets["secrets"].pop(idx)
                genome["graveyard"].append({
                    "type": "secret", "value": str(dead)[:80],
                    "died_gen": genome.get("generation", 0) + 1,
                    "epitaph": epitaph
                })
                kills_performed.append(f"secret[{idx}]")
                parts.append(f"killed secret[{idx}]")

        elif ktype == "interaction" and target:
            # Remove from active list
            active = state.get("interaction_patterns_active", [])
            if target in active:
                active.remove(target)
            # Try to remove gene-marked JS block
            pattern = re.compile(
                r'\s*// @gene:' + re.escape(target) + r':start.*?// @gene:' + re.escape(target) + r':end\s*',
                re.DOTALL
            )
            new_html = pattern.sub('', html)
            if new_html != html:
                html = new_html
                html_changed = True
            genome["graveyard"].append({
                "type": "interaction", "value": target,
                "died_gen": genome.get("generation", 0) + 1,
                "epitaph": epitaph
            })
            kills_performed.append(f"interaction:{target}")
            parts.append(f"killed interaction: {target}")

        elif ktype == "css_rule" and target:
            # Remove gene-marked CSS block
            pattern = re.compile(
                r'\s*/\* @gene:' + re.escape(target) + r':start \*/.*?/\* @gene:' + re.escape(target) + r':end \*/\s*',
                re.DOTALL
            )
            new_html = pattern.sub('', html)
            if new_html != html:
                html = new_html
                html_changed = True
                genome["graveyard"].append({
                    "type": "css_rule", "value": target,
                    "died_gen": genome.get("generation", 0) + 1,
                    "epitaph": epitaph
                })
                kills_performed.append(f"css_rule:{target}")
                parts.append(f"killed CSS rule: {target}")

        elif ktype == "html_section" and target:
            # Remove gene-marked HTML block
            pattern = re.compile(
                r'\s*<!-- @gene:' + re.escape(target) + r':start -->.*?<!-- @gene:' + re.escape(target) + r':end -->\s*',
                re.DOTALL
            )
            new_html = pattern.sub('', html)
            if new_html != html:
                html = new_html
                html_changed = True
                genome["graveyard"].append({
                    "type": "html_section", "value": target,
                    "died_gen": genome.get("generation", 0) + 1,
                    "epitaph": epitaph
                })
                kills_performed.append(f"html_section:{target}")
                parts.append(f"killed HTML section: {target}")

    if html_changed:
        with open(index_path, "w") as f: f.write(html)


# ══════════════════════════════════════════════════════════════════
# GENOME TRACKING — record this generation
# ══════════════════════════════════════════════════════════════════

# ── Version increment ─────────────────────────────────────────────
state["version"] = state.get("version", 0) + 1
new_version = state["version"]

with open(index_path) as f: html = f.read()
html = re.sub(r'id="siteVersion"[^>]*>[^<]*<', f'id="siteVersion" style="display:none">v{new_version}<', html)
with open(index_path, "w") as f: f.write(html)

# ── Update genome generation ──────────────────────────────────────
genome["generation"] = new_version

# Update genome traits from current state
traits = genome.get("traits", {})

# Color traits
if accent_palette and isinstance(accent_palette, dict):
    color = traits.setdefault("color", {})
    color["accent_base"] = accent_palette.get("base", color.get("accent_base"))
    for k in ("dawn", "morning", "afternoon", "evening", "night"):
        color[f"accent_{k}"] = accent_palette.get(k, color.get(f"accent_{k}"))

if css_changes and isinstance(css_changes, dict):
    color = traits.setdefault("color", {})
    var_to_trait = {
        "--bg": "bg", "--bg-surface": "bg_surface", "--bg-elevated": "bg_elevated",
        "--fg": "fg", "--fg-dim": "fg_dim", "--grain-opacity": "grain_opacity"
    }
    atmos = traits.setdefault("atmosphere", {})
    atmos_vars = {"--transition-slow": "transition_slow", "--transition-med": "transition_med"}
    for var_name, var_value in css_changes.items():
        if var_name in var_to_trait:
            color[var_to_trait[var_name]] = var_value
        elif var_name in atmos_vars:
            atmos[atmos_vars[var_name]] = var_value

# Typography traits
if font_change and isinstance(font_change, dict):
    typo = traits.setdefault("typography", {})
    typo["display"] = state["fonts"]["display"]
    typo["body"] = state["fonts"]["body"]
    typo["mono"] = state["fonts"]["mono"]

# Content traits
content = traits.setdefault("content", {})
content["mood"] = state.get("current_mood", content.get("mood"))
content["obsession"] = state.get("active_obsession", {}).get("topic", content.get("obsession"))
content["thought_pools"] = {k: len(v) for k, v in thoughts.items()}
content["secrets_count"] = len(secrets.get("secrets", []))

# Interaction traits
traits["interactions"] = state.get("interaction_patterns_active", [])

genome["traits"] = traits

# ── Record fitness evaluation ─────────────────────────────────────
fitness = changes.get("fitness_evaluation")
if fitness and isinstance(fitness, dict):
    scores = {
        "gen": new_version,
        "coherence": fitness.get("coherence"),
        "novelty": fitness.get("novelty"),
        "identity": fitness.get("identity"),
        "tension": fitness.get("tension"),
        "note": str(fitness.get("note", ""))[:150]
    }
    # Compute total as average of non-null scores
    numeric = [v for k, v in scores.items() if k not in ("gen", "note") and isinstance(v, (int, float))]
    scores["total"] = round(sum(numeric) / len(numeric), 1) if numeric else None
    genome.setdefault("fitness_log", []).append(scores)
    # Keep last 20 entries
    genome["fitness_log"] = genome["fitness_log"][-20:]
    parts.append(f"fitness: {scores['total']}")

# ── Record mutation log entry ─────────────────────────────────────
if mutations_detected or kills_performed:
    genome.setdefault("mutation_log", []).append({
        "gen": new_version,
        "mutations": mutations_detected,
        "kills": kills_performed,
        "timestamp": now
    })
    # Keep last 20 entries
    genome["mutation_log"] = genome["mutation_log"][-20:]

# Keep graveyard manageable (last 50 entries)
genome["graveyard"] = genome.get("graveyard", [])[-50:]

# ── Timestamp bookkeeping ─────────────────────────────────────────
if pulse_type == "daily":
    state["last_daily_pulse"] = now
elif pulse_type == "event":
    state["last_event_trigger"] = now

state["monthly_tokens_used"] = state.get("monthly_tokens_used", 0) + total_tokens

# ── Save everything ───────────────────────────────────────────────
with open(thoughts_path, "w") as f: json.dump(thoughts, f, indent=2)
with open(secrets_path, "w") as f: json.dump(secrets, f, indent=2)
with open(state_path, "w") as f: json.dump(state, f, indent=2)
with open(genome_path, "w") as f: json.dump(genome, f, indent=2)

description = "; ".join(parts) if parts else pulse_type + " pulse completed"
entry = "\n## " + now + "\n**" + pulse_type.capitalize() + " pulse.** " + description + ". Tokens: " + str(total_tokens) + ".\n"
with open(changelog_path, "a") as f: f.write(entry)

print(description)
