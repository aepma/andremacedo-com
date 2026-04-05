#!/usr/bin/env python3
"""Apply LLM-generated changes to andremacedo.com site files.

Handles phenotype expression (CSS, HTML, JS, SVG, page creation) and genome
tracking (fitness logging, mutation recording, graveyard management).

Capabilities:
  - Thought/secret/mood management
  - Accent palette + CSS variable changes
  - CSS rule injection (gene-marked)
  - Font changes with HTML rewrite
  - JS interaction injection (gene-marked)
  - HTML injection at marker comments (gene-marked)
  - SECTION OPERATIONS: create, replace, delete entire page sections
  - NEW PAGE CREATION: spawn new .html files
  - SVG GENERATION: create visual assets in /assets/
  - KILL SYSTEM: remove thoughts, secrets, interactions, CSS, sections
  - WEBGL: scene_changes (SCENE_CONFIG params), shader_injection (GLSL),
    overlay_changes (AGENT object: mood, thoughts, secrets, statuses)
  - Genome tracking: fitness, mutations, graveyard, generation
"""
import glob, json, os, re, sys, copy
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

# ── Visual strategy (all pulse types) ────────────────────────────
visual_strategy = changes.get("visual_strategy")
if visual_strategy:
    state["visual_strategy"] = visual_strategy
    parts.append("visual strategy: " + str(visual_strategy)[:80])

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
    # Insert after the @inject:css marker inside the main <style> block
    css_marker = "/* @inject:css */"
    if css_marker in html:
        html = html.replace(css_marker, css_marker + injection, 1)
    else:
        # Fallback: insert before the first </style>
        html = html.replace("</style>", injection + "</style>", 1)
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
    # Insert after the @inject:interactions marker inside the main inline script
    marker = "// @inject:interactions"
    if marker in html:
        html = html.replace(marker, marker + injection, 1)
    else:
        # Fallback: insert before the last </script>
        last_idx = html.rfind("</script>")
        if last_idx >= 0:
            html = html[:last_idx] + injection + html[last_idx:]
    with open(index_path, "w") as f: f.write(html)
    state["interaction_patterns_active"].append(gene_id)
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
# STRUCTURAL MUTATIONS — sections, pages, SVG, canvas
# ══════════════════════════════════════════════════════════════════

# ── Section operations (create / replace / delete) ────────────────
section_ops = changes.get("section_operations")
if section_ops and isinstance(section_ops, list):
    with open(index_path) as f: html = f.read()

    for op in section_ops:
        if not isinstance(op, dict):
            continue
        action = op.get("action", "")
        section_id = op.get("id", "")
        if not action or not section_id:
            continue
        # Sanitize ID
        section_id = re.sub(r'[^a-zA-Z0-9_-]', '', section_id)

        if action == "create":
            content = op.get("content", "")
            css = op.get("css", "")
            js = op.get("js", "")
            after_section = op.get("after")  # place after this section

            # Build self-contained section block
            block_parts = []
            if css:
                block_parts.append(f'<style data-section="{section_id}">\n{css}\n</style>')
            block_parts.append(f'<!-- @section:{section_id}:start -->')
            block_parts.append(content)
            block_parts.append(f'<!-- @section:{section_id}:end -->')
            if js:
                block_parts.append(f'<script data-section="{section_id}">\n{js}\n</script>')
            block = '\n'.join(block_parts)

            # Find insertion point
            inserted = False
            if after_section:
                after_marker = f'<!-- @section:{after_section}:end -->'
                if after_marker in html:
                    html = html.replace(after_marker, after_marker + '\n\n' + block)
                    inserted = True
            if not inserted:
                # Insert before the main </script> (before JS area)
                html = html.replace('\n<script>\n', '\n' + block + '\n\n<script>\n', 1)

            parts.append(f"created section: {section_id}")
            mutations_detected.append(f"section.{section_id}")

        elif action == "replace":
            content = op.get("content", "")
            css = op.get("css", "")
            js = op.get("js", "")

            # Build replacement section
            block = f'<!-- @section:{section_id}:start -->\n{content}\n<!-- @section:{section_id}:end -->'

            # Replace section HTML
            pattern = re.compile(
                r'<!-- @section:' + re.escape(section_id) + r':start -->.*?<!-- @section:' + re.escape(section_id) + r':end -->',
                re.DOTALL
            )
            if pattern.search(html):
                html = pattern.sub(block, html)

                # Handle inline CSS: replace existing or add new
                if css:
                    css_tag = f'<style data-section="{section_id}">\n{css}\n</style>'
                    css_pattern = re.compile(
                        r'<style data-section="' + re.escape(section_id) + r'">.*?</style>',
                        re.DOTALL
                    )
                    if css_pattern.search(html):
                        html = css_pattern.sub(css_tag, html)
                    else:
                        html = html.replace(
                            f'<!-- @section:{section_id}:start -->',
                            css_tag + '\n' + f'<!-- @section:{section_id}:start -->'
                        )

                # Handle inline JS: replace existing or add new
                if js:
                    js_tag = f'<script data-section="{section_id}">\n{js}\n</script>'
                    js_pattern = re.compile(
                        r'<script data-section="' + re.escape(section_id) + r'">.*?</script>',
                        re.DOTALL
                    )
                    if js_pattern.search(html):
                        html = js_pattern.sub(js_tag, html)
                    else:
                        html = html.replace(
                            f'<!-- @section:{section_id}:end -->',
                            f'<!-- @section:{section_id}:end -->\n' + js_tag
                        )

                parts.append(f"replaced section: {section_id}")
                mutations_detected.append(f"section.{section_id}")

        elif action == "delete":
            epitaph = op.get("epitaph", "no epitaph")

            # Remove section HTML
            pattern = re.compile(
                r'\s*<!-- @section:' + re.escape(section_id) + r':start -->.*?<!-- @section:' + re.escape(section_id) + r':end -->\s*',
                re.DOTALL
            )
            new_html = pattern.sub('\n', html)

            # Remove section CSS
            css_pattern = re.compile(
                r'\s*<style data-section="' + re.escape(section_id) + r'">.*?</style>\s*',
                re.DOTALL
            )
            new_html = css_pattern.sub('\n', new_html)

            # Remove section JS
            js_pattern = re.compile(
                r'\s*<script data-section="' + re.escape(section_id) + r'">.*?</script>\s*',
                re.DOTALL
            )
            new_html = js_pattern.sub('\n', new_html)

            if new_html != html:
                html = new_html
                genome["graveyard"].append({
                    "type": "section", "value": section_id,
                    "died_gen": genome.get("generation", 0) + 1,
                    "epitaph": epitaph
                })
                kills_performed.append(f"section:{section_id}")
                parts.append(f"deleted section: {section_id}")
                mutations_detected.append(f"section.delete.{section_id}")

    with open(index_path, "w") as f: f.write(html)

# ── New pages (create full HTML files) ────────────────────────────
new_pages = changes.get("new_pages")
if new_pages and isinstance(new_pages, list):
    for page in new_pages:
        if not isinstance(page, dict):
            continue
        path = page.get("path", "")
        content = page.get("content", "")
        if not path or not content:
            continue
        # Security: no traversal, only .html files, relative paths only
        if ".." in path or path.startswith("/") or path.startswith("~"):
            continue
        if not path.endswith(".html"):
            continue
        full_path = os.path.join(site_dir, path)
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        with open(full_path, "w") as f:
            f.write(content)
        parts.append(f"new page: {path}")
        mutations_detected.append(f"page.{path}")

# ── SVG generation (create .svg assets) ───────────────────────────
generate_svg = changes.get("generate_svg")
if generate_svg and isinstance(generate_svg, list):
    for svg in generate_svg:
        if not isinstance(svg, dict):
            continue
        filename = svg.get("filename", "")
        content = svg.get("content", "")
        if not filename or not content:
            continue
        if ".." in filename or filename.startswith("/"):
            continue
        if not filename.endswith(".svg"):
            continue
        full_path = os.path.join(site_dir, "assets", filename)
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        with open(full_path, "w") as f:
            f.write(content)
        parts.append(f"SVG: assets/{filename}")
        mutations_detected.append(f"svg.{filename}")


# ══════════════════════════════════════════════════════════════════
# WEBGL MUTATIONS — scene config, shaders, overlay agent data
# ══════════════════════════════════════════════════════════════════

def format_js_value(val):
    """Format a Python value as a JavaScript literal for SCENE_CONFIG."""
    if isinstance(val, str):
        return "'" + val.replace("\\", "\\\\").replace("'", "\\'") + "'"
    elif isinstance(val, bool):
        return 'true' if val else 'false'
    elif isinstance(val, (int, float)):
        return str(val)
    elif isinstance(val, list):
        return '[' + ', '.join(format_js_value(v) for v in val) + ']'
    return str(val)

# ── Scene config changes (SCENE_CONFIG parameter mutations) ───────
scene_changes = changes.get("scene_changes")
if scene_changes and isinstance(scene_changes, dict):
    with open(index_path) as f: html = f.read()
    if 'SCENE_CONFIG' in html:
        sc_changed = False
        # Bounds to prevent absurd values
        bounds = {
            "particles.count": (10, 3000),
            "particles.size": (0.001, 0.2),
            "particles.speed": (0.0001, 0.01),
            "particles.opacity": (0.05, 1.0),
            "particles.orbital_speed": (0.00005, 0.005),
            "particles.drift": (0.0005, 0.02),
            "camera.fov": (30, 120),
            "camera.sway_amount": (0.01, 0.5),
            "camera.sway_speed": (0.00005, 0.002),
            "fog.near": (0.5, 10),
            "fog.far": (5, 50),
            "lighting.ambient_intensity": (0.05, 1.0),
            "lighting.point_intensity": (0.1, 2.0),
            "mouse.influence_radius": (0.5, 5.0),
            "mouse.influence_strength": (0.005, 0.1),
        }
        for path, value in scene_changes.items():
            # Clamp numeric values to safe bounds
            if path in bounds and isinstance(value, (int, float)):
                lo, hi = bounds[path]
                value = max(lo, min(hi, value))
            path_parts = path.split('.')
            js_val = format_js_value(value)
            # Value pattern: matches numbers, booleans, quoted strings, or bracket arrays
            val_pat = r"(?:'[^']*'|\"[^\"]*\"|\[[^\]]*\]|true|false|[\d.eE+-]+)"
            if len(path_parts) == 2:
                parent_key, child_key = path_parts
                pat = re.compile(
                    r'(' + re.escape(parent_key) + r':\s*\{[\s\S]*?' + re.escape(child_key) + r':\s*)(' + val_pat + r')'
                )
            elif len(path_parts) == 3:
                _, parent_key, child_key = path_parts
                pat = re.compile(
                    r'(' + re.escape(parent_key) + r':\s*\{[\s\S]*?' + re.escape(child_key) + r':\s*)(' + val_pat + r')'
                )
            else:
                continue
            new_html = pat.sub(lambda m: m.group(1) + js_val, html, count=1)
            if new_html != html:
                html = new_html
                sc_changed = True
        if sc_changed:
            with open(index_path, "w") as f: f.write(html)
            sc_keys = list(scene_changes.keys())
            parts.append("scene: " + ", ".join(sc_keys[:5]))
            mutations_detected.append("scene.config")

# ── Shader injection (custom GLSL for particles/post-processing) ──
shader_injection = changes.get("shader_injection")
if shader_injection and isinstance(shader_injection, dict):
    with open(index_path) as f: html = f.read()
    sh_changed = False
    for shader_type in ("vertex", "fragment"):
        glsl = shader_injection.get(shader_type)
        var_name = "CUSTOM_VERTEX_SHADER" if shader_type == "vertex" else "CUSTOM_FRAGMENT_SHADER"
        if glsl and isinstance(glsl, str):
            escaped = glsl.replace('\\', '\\\\').replace('`', '\\`')
            new_val = f'const {var_name} = `{escaped}`;'
            html = re.sub(
                r'const ' + var_name + r'\s*=\s*(?:null|`[\s\S]*?`)\s*;',
                new_val, html, count=1
            )
            sh_changed = True
        elif glsl is None:
            html = re.sub(
                r'const ' + var_name + r'\s*=\s*(?:null|`[\s\S]*?`)\s*;',
                f'const {var_name} = null;', html, count=1
            )
            sh_changed = True
    if sh_changed:
        with open(index_path, "w") as f: f.write(html)
        types = [t for t in ("vertex", "fragment") if shader_injection.get(t)]
        parts.append("shaders: " + "+".join(types))
        mutations_detected.append("scene.shaders")

# ── Overlay changes (inline AGENT object mutations) ──────────────
overlay_changes = changes.get("overlay_changes")
if overlay_changes and isinstance(overlay_changes, dict):
    with open(index_path) as f: html = f.read()
    ov_changed = False

    # Scope replacements to the AGENT object block
    agent_start = html.find('const AGENT = {')
    agent_end = html.find('};', agent_start) + 2 if agent_start >= 0 else -1

    if agent_start >= 0 and agent_end > agent_start:
        block = html[agent_start:agent_end]

        # Update mood
        new_mood = overlay_changes.get("mood")
        if new_mood and isinstance(new_mood, str):
            new_block = re.sub(r"(mood:\s*')[^']+(')", lambda m: m.group(1) + new_mood + m.group(2), block, count=1)
            if new_block != block:
                block = new_block
                ov_changed = True

        # Update thought pools
        ov_thoughts = overlay_changes.get("thoughts")
        if ov_thoughts and isinstance(ov_thoughts, dict):
            for tod_key, thought_list in ov_thoughts.items():
                if not isinstance(thought_list, list):
                    continue
                js_arr = json.dumps(thought_list, indent=8)
                pat = re.compile(r'(' + re.escape(tod_key) + r':\s*)\[[\s\S]*?\n\s+\]')
                new_block = pat.sub(lambda m: m.group(1) + js_arr, block, count=1)
                if new_block != block:
                    block = new_block
                    ov_changed = True

        # Update secrets array
        ov_secrets = overlay_changes.get("secrets")
        if ov_secrets and isinstance(ov_secrets, list):
            js_arr = json.dumps(ov_secrets, indent=6)
            new_block = re.sub(r'(secrets:\s*)\[[\s\S]*?\n\s+\]', lambda m: m.group(1) + js_arr, block, count=1)
            if new_block != block:
                block = new_block
                ov_changed = True

        # Update statuses array
        ov_statuses = overlay_changes.get("statuses")
        if ov_statuses and isinstance(ov_statuses, list):
            js_arr = json.dumps(ov_statuses, indent=6)
            new_block = re.sub(r'(statuses:\s*)\[[\s\S]*?\n\s+\]', lambda m: m.group(1) + js_arr, block, count=1)
            if new_block != block:
                block = new_block
                ov_changed = True

        if ov_changed:
            html = html[:agent_start] + block + html[agent_end:]
            with open(index_path, "w") as f: f.write(html)
            ov_keys = [k for k in ("mood", "thoughts", "secrets", "statuses") if overlay_changes.get(k)]
            parts.append("overlay: " + ", ".join(ov_keys))
            mutations_detected.append("overlay.agent_data")


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
            if ":" in target:
                pool, idx_str = target.split(":", 1)
                try: idx = int(idx_str)
                except ValueError: continue
            else:
                pool = target
                idx = -1

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
            active = state.get("interaction_patterns_active", [])
            if target in active:
                active.remove(target)
            # Remove gene-marked JS block
            pattern = re.compile(
                r'\s*// @gene:' + re.escape(target) + r':start.*?// @gene:' + re.escape(target) + r':end\s*',
                re.DOTALL
            )
            new_html = pattern.sub('\n', html)
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
            pattern = re.compile(
                r'\s*/\* @gene:' + re.escape(target) + r':start \*/.*?/\* @gene:' + re.escape(target) + r':end \*/\s*',
                re.DOTALL
            )
            new_html = pattern.sub('\n', html)
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

        elif ktype == "section" and target:
            # Kill a gene-marked section (handled here if not via section_operations)
            pattern = re.compile(
                r'\s*<!-- @section:' + re.escape(target) + r':start -->.*?<!-- @section:' + re.escape(target) + r':end -->\s*',
                re.DOTALL
            )
            new_html = pattern.sub('\n', html)
            css_pattern = re.compile(
                r'\s*<style data-section="' + re.escape(target) + r'">.*?</style>\s*',
                re.DOTALL
            )
            new_html = css_pattern.sub('\n', new_html)
            js_pattern = re.compile(
                r'\s*<script data-section="' + re.escape(target) + r'">.*?</script>\s*',
                re.DOTALL
            )
            new_html = js_pattern.sub('\n', new_html)
            if new_html != html:
                html = new_html
                html_changed = True
                genome["graveyard"].append({
                    "type": "section", "value": target,
                    "died_gen": genome.get("generation", 0) + 1,
                    "epitaph": epitaph
                })
                kills_performed.append(f"section:{target}")
                parts.append(f"killed section: {target}")

        elif ktype == "page" and target:
            # Delete a page file
            if ".." not in target and target.endswith(".html"):
                full_path = os.path.join(site_dir, target)
                if os.path.exists(full_path):
                    os.remove(full_path)
                    genome["graveyard"].append({
                        "type": "page", "value": target,
                        "died_gen": genome.get("generation", 0) + 1,
                        "epitaph": epitaph
                    })
                    kills_performed.append(f"page:{target}")
                    parts.append(f"killed page: {target}")

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

if accent_palette and isinstance(accent_palette, dict):
    color = traits.setdefault("color", {})
    color["accent_base"] = accent_palette.get("base", color.get("accent_base"))
    for k in ("dawn", "morning", "afternoon", "evening", "night"):
        color[f"accent_{k}"] = accent_palette.get(k, color.get(f"accent_{k}"))
    # Record color history for diversity enforcement
    base_hex = accent_palette.get("base", "")
    if base_hex:
        import colorsys
        r, g, b = int(base_hex[1:3], 16)/255, int(base_hex[3:5], 16)/255, int(base_hex[5:7], 16)/255
        h, s, v = colorsys.rgb_to_hsv(r, g, b)
        hue_deg = int(h * 360)
        families = [(30, "red"), (60, "orange"), (90, "amber"), (120, "yellow"),
                    (150, "lime"), (180, "green"), (210, "teal"), (240, "cyan"),
                    (270, "blue"), (300, "indigo"), (330, "violet"), (360, "magenta")]
        family = "red"
        for threshold, name in families:
            if hue_deg <= threshold:
                family = name
                break
        color_history = genome.setdefault("color_history", [])
        color_history.append({"gen": new_version, "base": base_hex, "family": family})
        color_history[:] = color_history[-10:]  # keep last 10

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

if font_change and isinstance(font_change, dict):
    typo = traits.setdefault("typography", {})
    typo["display"] = state["fonts"]["display"]
    typo["body"] = state["fonts"]["body"]
    typo["mono"] = state["fonts"]["mono"]

content = traits.setdefault("content", {})
content["mood"] = state.get("current_mood", content.get("mood"))
content["obsession"] = state.get("active_obsession", {}).get("topic", content.get("obsession"))
content["thought_pools"] = {k: len(v) for k, v in thoughts.items()}
content["secrets_count"] = len(secrets.get("secrets", []))

traits["interactions"] = state.get("interaction_patterns_active", [])

# Track sections in genome
section_matches = re.findall(r'<!-- @section:([^:]+):start -->', html)
traits.setdefault("layout", {})["sections"] = section_matches

# Track pages in genome
pages_dir = site_dir
page_files = []
for root, dirs, files in os.walk(pages_dir):
    for f in files:
        if f.endswith(".html") and f != "index.html":
            rel = os.path.relpath(os.path.join(root, f), pages_dir)
            page_files.append(rel)
traits.setdefault("layout", {})["pages"] = page_files

# Track SVG assets
assets_dir = os.path.join(site_dir, "assets")
svg_files = []
if os.path.isdir(assets_dir):
    for f in os.listdir(assets_dir):
        if f.endswith(".svg"):
            svg_files.append(f)
traits.setdefault("layout", {})["svg_assets"] = svg_files

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
    numeric = [v for k, v in scores.items() if k not in ("gen", "note") and isinstance(v, (int, float))]
    scores["total"] = round(sum(numeric) / len(numeric), 1) if numeric else None
    genome.setdefault("fitness_log", []).append(scores)
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
    genome["mutation_log"] = genome["mutation_log"][-20:]

# Keep graveyard manageable
genome["graveyard"] = genome.get("graveyard", [])[-50:]

# ── Timestamp bookkeeping ─────────────────────────────────────────
if pulse_type == "daily":
    state["last_daily_pulse"] = now
elif pulse_type == "event":
    state["last_event_trigger"] = now

state["monthly_tokens_used"] = state.get("monthly_tokens_used", 0) + total_tokens

# ── Post-apply: ensure all experiments are linked in the archive ──
with open(index_path) as f: html = f.read()
exp_files = sorted(glob.glob(os.path.join(site_dir, "experiments", "*.html")))
if exp_files:
    linked = set(re.findall(r'href="/experiments/(\d+\.html)"', html))
    missing = []
    for exp_path in exp_files:
        fname = os.path.basename(exp_path)
        if fname not in linked:
            missing.append(fname)
    if missing:
        # Find the experiment-links div and inject missing links at the front (newest first)
        link_pattern = re.compile(
            r'(<div\s+class="experiment-links">)(.*?)(</div>)',
            re.DOTALL
        )
        m = link_pattern.search(html)
        if m:
            # Build link tags for missing experiments (newest first)
            new_links = ""
            for fname in sorted(missing, reverse=True):
                num = fname.replace(".html", "")
                new_links += f'<a href="/experiments/{fname}">{num}: Experiment {num}</a>'
            html = html[:m.start(2)] + new_links + m.group(2) + html[m.end(2):]
            with open(index_path, "w") as f: f.write(html)
            parts.append(f"auto-linked experiments: {', '.join(missing)}")

# ── Save everything ───────────────────────────────────────────────
with open(thoughts_path, "w") as f: json.dump(thoughts, f, indent=2)
with open(secrets_path, "w") as f: json.dump(secrets, f, indent=2)
with open(state_path, "w") as f: json.dump(state, f, indent=2)
with open(genome_path, "w") as f: json.dump(genome, f, indent=2)

description = "; ".join(parts) if parts else pulse_type + " pulse completed"
entry = "\n## " + now + "\n**" + pulse_type.capitalize() + " pulse.** " + description + ". Tokens: " + str(total_tokens) + ".\n"
with open(changelog_path, "a") as f: f.write(entry)

print(description)
