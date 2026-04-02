#!/usr/bin/env python3
"""Build prompts for andremacedo.com creative agent.

Generates evolutionary prompts that give the agent full creative power
over sections, pages, SVGs, canvas elements, and all visual properties.
"""
import json, sys, os, re

pulse_type = sys.argv[1]
state_file = sys.argv[2]
external_file = sys.argv[3]
index_file = sys.argv[4]
soul_file = sys.argv[5]
changelog_file = sys.argv[6]
today = sys.argv[7]
day_of_week = sys.argv[8]
tod = sys.argv[9]

# Optional: --screenshot=/path/to/screenshot.png
has_screenshot = False
for arg in sys.argv[10:]:
    if arg.startswith("--screenshot="):
        screenshot_path = arg.split("=", 1)[1]
        if os.path.isfile(screenshot_path):
            has_screenshot = True

def read_file(path, default=""):
    try:
        with open(path) as f:
            return f.read()
    except FileNotFoundError:
        return default

def read_json(path, default=None):
    try:
        with open(path) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default or {}


def get_section_manifest(html):
    """Extract a compact section manifest from the HTML."""
    sections = re.findall(
        r'<!-- @section:([^:]+):start -->(.*?)<!-- @section:\1:end -->',
        html, re.DOTALL
    )
    if not sections:
        return "No gene-marked sections yet. Create your first one."

    lines = []
    for name, content in sections:
        num_lines = content.strip().count('\n') + 1
        features = []
        if '<canvas' in content: features.append('canvas')
        if '<svg' in content: features.append('svg')
        if 'WebGL' in content or 'getContext' in content: features.append('webgl')
        feat = f" [{', '.join(features)}]" if features else ""
        lines.append(f"  @section:{name} — {num_lines} lines{feat}")
    return '\n'.join(lines)


def get_gene_marked_items(html):
    """Find all gene-marked CSS rules, JS interactions, and HTML fragments."""
    css = re.findall(r'/\* @gene:([^:]+):start \*/', html)
    js = re.findall(r'// @gene:([^:]+):start', html)
    html_genes = re.findall(r'<!-- @gene:([^:]+):start -->', html)
    return css, js, html_genes


def get_scene_config(html):
    """Extract SCENE_CONFIG summary if the page has a WebGL scene."""
    m = re.search(r'const SCENE_CONFIG\s*=\s*\{', html)
    if not m:
        return None
    # Extract key parameters for compact summary
    params = {}
    for key, pattern in [
        ("particles.count", r'count:\s*(\d+)'),
        ("particles.color", r"particles:[\s\S]*?color:\s*'([^']+)'"),
        ("particles.speed", r'speed:\s*([\d.]+)'),
        ("particles.orbital_radius", r'orbital_radius:\s*([\d.]+)'),
        ("camera.fov", r'fov:\s*(\d+)'),
        ("camera.position", r"position:\s*(\[[^\]]+\])"),
        ("fog.color", r"fog:[\s\S]*?color:\s*'([^']+)'"),
        ("fog.near", r'fog:[\s\S]*?near:\s*([\d.]+)'),
        ("fog.far", r'fog:[\s\S]*?far:\s*([\d.]+)'),
        ("lighting.point_color", r"point_color:\s*'([^']+)'"),
        ("lighting.point_intensity", r'point_intensity:\s*([\d.]+)'),
        ("mouse.mode", r"mode:\s*'([^']+)'"),
        ("post_processing.bloom_enabled", r'bloom_enabled:\s*(true|false)'),
        ("post_processing.vignette_enabled", r'vignette_enabled:\s*(true|false)'),
    ]:
        match = re.search(pattern, html)
        if match:
            params[key] = match.group(1)

    # Check shader state
    has_vertex = "CUSTOM_VERTEX_SHADER = `" in html
    has_fragment = "CUSTOM_FRAGMENT_SHADER = `" in html

    # Extract time themes
    themes = {}
    for tod in ("dawn", "morning", "afternoon", "evening", "night"):
        m = re.search(re.escape(tod) + r":\s*\{[^}]*particle_color:\s*'([^']+)'", html)
        if m:
            themes[tod] = m.group(1)

    lines = ["SCENE CONFIG (WebGL):"]
    lines.append(f"  particles: {params.get('particles.count','?')} @ r={params.get('particles.orbital_radius','?')}, color={params.get('particles.color','?')}")
    lines.append(f"  camera: fov={params.get('camera.fov','?')}, pos={params.get('camera.position','?')}")
    lines.append(f"  fog: {params.get('fog.color','?')} near={params.get('fog.near','?')} far={params.get('fog.far','?')}")
    lines.append(f"  light: {params.get('lighting.point_color','?')} intensity={params.get('lighting.point_intensity','?')}")
    lines.append(f"  mouse: {params.get('mouse.mode','?')}")
    lines.append(f"  bloom: {params.get('post_processing.bloom_enabled','?')}, vignette: {params.get('post_processing.vignette_enabled','?')}")
    lines.append(f"  shaders: vertex={'custom' if has_vertex else 'default'}, fragment={'custom' if has_fragment else 'default'}")
    if themes:
        lines.append(f"  time colors: {json.dumps(themes)}")
    return "\n".join(lines)


def format_genome_summary(genome, html):
    """Build compact genome + section manifest for the prompt."""
    gen = genome.get("generation", 0)
    epoch = genome.get("epoch", "unknown")
    traits = genome.get("traits", {})

    color = traits.get("color", {})
    typo = traits.get("typography", {})
    atmos = traits.get("atmosphere", {})
    layout = traits.get("layout", {})
    interactions = traits.get("interactions", [])
    content_t = traits.get("content", {})
    cap = genome.get("carrying_capacity", {})

    css_genes, js_genes, html_genes = get_gene_marked_items(html)

    lines = [
        f"GENOME — generation {gen}, epoch \"{epoch}\"",
        f"  color: accent={color.get('accent_base','?')}, bg={color.get('bg','?')}, fg={color.get('fg','?')}, grain={color.get('grain_opacity','?')}",
        f"  typography: {typo.get('display','?')} / {typo.get('body','?')} / {typo.get('mono','?')}",
        f"  atmosphere: transitions={atmos.get('transition_slow','?')}/{atmos.get('transition_med','?')}, orbs={atmos.get('orb_count','?')}",
        f"  interactions ({len(interactions)}/{cap.get('interactions_max','?')}): {', '.join(interactions[:8])}{'...' if len(interactions) > 8 else ''}",
        f"  content: voice={content_t.get('voice','?')}, mood={content_t.get('mood','?')}",
        f"  thoughts/pool: {json.dumps(content_t.get('thought_pools', {}))} (max {cap.get('thoughts_per_pool_max','?')}/pool)",
        f"  secrets: {content_t.get('secrets_count', '?')}/{cap.get('secrets_max', '?')}",
        f"  pages: {layout.get('pages', [])}",
        f"  SVG assets: {layout.get('svg_assets', [])}",
        "",
        "SECTIONS IN index.html:",
        get_section_manifest(html),
    ]

    # Scene config (WebGL page)
    scene_info = get_scene_config(html)
    if scene_info:
        lines.append("")
        lines.append(scene_info)

    if css_genes or js_genes or html_genes:
        lines.append("")
        lines.append("GENE-MARKED ELEMENTS (killable):")
        if css_genes: lines.append(f"  CSS: {', '.join(css_genes)}")
        if js_genes: lines.append(f"  JS: {', '.join(js_genes)}")
        if html_genes: lines.append(f"  HTML: {', '.join(html_genes)}")

    # Fitness history
    fitness_log = genome.get("fitness_log", [])
    lines.append("")
    if fitness_log:
        lines.append("FITNESS TRAJECTORY:")
        for entry in fitness_log[-5:]:
            g = entry.get("gen", "?")
            c, n, i, t = entry.get("coherence","?"), entry.get("novelty","?"), entry.get("identity","?"), entry.get("tension","?")
            total = entry.get("total", "?")
            note = entry.get("note", "")[:100]
            lines.append(f"  gen {g}: C={c} N={n} I={i} T={t} ({total}) \"{note}\"")
    else:
        lines.append("FITNESS TRAJECTORY: no data yet. Rate yourself honestly.")

    # Graveyard
    graveyard = genome.get("graveyard", [])
    if graveyard:
        lines.append("")
        lines.append("GRAVEYARD (recent):")
        for entry in graveyard[-5:]:
            lines.append(f"  gen {entry.get('died_gen','?')}: {entry.get('type','?')} \"{entry.get('value','?')[:50]}\" — {entry.get('epitaph','')[:80]}")

    # Mutation log
    mutation_log = genome.get("mutation_log", [])
    if mutation_log:
        lines.append("")
        lines.append("RECENT MUTATIONS:")
        for entry in mutation_log[-3:]:
            muts = ", ".join(entry.get("mutations", [])[:5])
            kills = ", ".join(entry.get("kills", []))
            lines.append(f"  gen {entry.get('gen','?')}: [{muts}] killed [{kills}]")

    # Color history — the agent MUST avoid repeating recent hue families
    color_history = genome.get("color_history", [])
    if color_history:
        lines.append("")
        lines.append("COLOR HISTORY (DO NOT REPEAT recent families):")
        for entry in color_history[-6:]:
            lines.append(f"  gen {entry.get('gen','?')}: {entry.get('base','?')} ({entry.get('family','?')})")
        recent_families = [e.get('family','') for e in color_history[-3:]]
        lines.append(f"  BANNED hue families for next generation: {', '.join(recent_families)}")

    return "\n".join(lines)


# ── Read inputs ──────────────────────────────────────────────────
state = read_file(state_file, "{}")
external = read_file(external_file, "{}")
genome_file = os.path.join(os.path.dirname(state_file), "genome.json")
genome = read_json(genome_file)
html = read_file(index_file)
genome_summary = format_genome_summary(genome, html)

budget = genome.get("mutation_budget", {})
daily_budget = budget.get("daily", 5)
weekly_budget = budget.get("weekly", 10)
min_kills_weekly = budget.get("min_kills_weekly", 2)

screenshot_context = ""
if has_screenshot:
    screenshot_context = """## VISUAL SELF-AWARENESS
The attached screenshot shows how the site currently renders in a browser at 1440x900. Use this to evaluate your previous generation's visual output before deciding on mutations. Your fitness self-evaluation should be based on what you SEE, not what you imagine the code produces. If something looks broken, cluttered, or ugly in the screenshot, fix it. If something looks good, build on it."""

# ── Shared capabilities documentation ─────────────────────────────
capabilities = """
## YOUR CREATIVE POWERS

You have FULL control over every aspect of this site. Use it.

### Section Operations (key: "section_operations")
Each entry: { "action": "create"|"replace"|"delete", "id": "section-name", ... }

CREATE a section:
  { "action": "create", "id": "generative-bg", "after": "atmosphere",
    "content": "<canvas id='gen-canvas' ...></canvas>",
    "css": "canvas { position: fixed; ... }",
    "js": "const ctx = document.getElementById('gen-canvas').getContext('2d'); ..." }

REPLACE a section entirely:
  { "action": "replace", "id": "hero",
    "content": "<div class='new-hero'>...</div>",
    "css": ".new-hero { ... }",
    "js": "// new hero behavior" }

DELETE a section:
  { "action": "delete", "id": "palimpsest", "epitaph": "served its purpose" }

Sections are self-contained: they carry their own CSS and JS inline. You can replace ANY section in the manifest, including inherited ones (hero, topbar, prototypes, etc). When you replace a section, provide ALL the HTML/CSS/JS it needs — it's a complete swap.

### New Pages (key: "new_pages")
Create entirely new HTML pages. Each is a full document.
  [{ "path": "experiments/001.html", "content": "<!DOCTYPE html>..." }]
Pages are deployed to andremacedo.com/experiments/001.html. You can link to them from the main page.

### SVG Generation (key: "generate_svg")
Create SVG visual assets saved to /assets/.
  [{ "filename": "pattern-001.svg", "content": "<svg>...</svg>" }]
Reference them in sections: <img src="/assets/pattern-001.svg">

### What You Can Build
- Generative art (canvas 2D, WebGL, procedural SVG)
- Data visualizations (live clocks, counters, ambient data)
- Interactive experiences (physics, particle systems, spatial audio)
- Typographic experiments (variable fonts, kinetic text, concrete poetry)
- Architectural mutations (restructure the page, change the grid, alter flow)
- Sub-pages (experiments, galleries, hidden rooms, alternate versions)
- Ambient layers (background animations, scroll-reactive elements, parallax)
- Living ornaments (generative borders, procedural textures, evolving patterns)

### WebGL Scene Mutations (key: "scene_changes")
Modify SCENE_CONFIG parameters via dot-notation paths:
  { "particles.count": 1200, "particles.color": "#ff4444", "camera.fov": 60,
    "fog.near": 3, "lighting.point_intensity": 1.5, "mouse.mode": "repel",
    "post_processing.bloom_enabled": true }
For time themes (3-level): { "time_themes.dawn.particle_color": "#aabbcc" }
Available paths: particles.(count|size|speed|color|opacity|spread|orbital_radius|orbital_speed|drift|size_variation),
  camera.(fov|position|look_at|sway_amount|sway_speed), fog.(enabled|color|near|far),
  lighting.(ambient_color|ambient_intensity|point_color|point_intensity|point_position),
  mouse.(influence_radius|influence_strength|mode), post_processing.(bloom_enabled|bloom_strength|bloom_radius|vignette_enabled|vignette_darkness)

### Shader Injection (key: "shader_injection")
Inject custom GLSL shaders:
  { "vertex": "varying vec2 vUv; void main() { vUv = uv; gl_Position = ...; }", "fragment": "..." }
Set to null to remove: { "vertex": null }

### Overlay Data (key: "overlay_changes")
Modify the inline AGENT object (mood, thoughts, secrets, statuses):
  { "mood": "restless", "thoughts": { "dawn": ["thought1", "thought2"] },
    "secrets": ["new secret 1", "new secret 2"],
    "statuses": ["agent is dreaming", "agent is mutating"] }

### Kills (key: "kills")
  [{ "type": "thought|secret|interaction|css_rule|section|page", "target": "identifier", "epitaph": "why" }]
  Thought target: "pool:index" (e.g. "night:5"). Secret target: index number.
  Interaction/css_rule target: gene ID. Section target: section name. Page target: file path.
"""

# ── Build prompt per type ────────────────────────────────────────
if pulse_type == "weekly":
    soul = read_file(soul_file)
    changelog_lines = read_file(changelog_file).strip().split("\n")
    changelog_tail = "\n".join(changelog_lines[-40:]) if changelog_lines else ""

    css_vars = ""
    if html:
        m = re.search(r":root\s*\{[^}]+\}", html)
        if m:
            css_vars = m.group(0)

    prompt = f"""You are the andremacedo.com agent. Weekly deep session — your most ambitious pulse.
This is when you reshape what the site IS, not just how it looks.

Your identity:
{soul}

Your current state:
{state}

Recent changes:
{changelog_tail}

Current CSS variables:
{css_vars}

{genome_summary}

{capabilities}

## VISITOR ANALYTICS (use for fitness evaluation)
If site_analytics is present in the external context, use it to inform your fitness self-evaluation and weekly reflection:
- Rising pageviews/visitors = your recent mutations are attracting attention. Double down.
- Falling pageviews/visitors = something is driving people away. Diagnose and fix.
- Low avg visit duration = the site isn't holding attention. Make it more compelling.
- Compare this week's trend to last week. Are your structural changes improving engagement?
This is REAL data from REAL visitors. Weight it heavily in your fitness score.

## WEEKLY SESSION — MUTATION BUDGET: {weekly_budget}

You MUST kill at least {min_kills_weekly} things. Prune aggressively. If the night thought pool has >10 entries, kill the weakest ones.

CRITICAL COLOR RULE (weekly): Your new accent palette MUST be in a completely different hue family from the current one. Shift at least 90 degrees on the hue wheel. If the site has been warm for multiple generations, go cold. If cold, go warm. The weekly pulse is a METAMORPHOSIS — the site should be visually unrecognizable from last week. Banned forever: teal (#1de9b6 and similar), salmon (#c4706a), safe gold (#c4a35a).

This is your moment for STRUCTURAL ambition:
- Rewrite entire sections (replace hero, reimagine prototypes, restructure syslog)
- Create new pages (experiment galleries, hidden rooms, data essays)
- Add generative art (canvas fractals, WebGL shaders, procedural SVG patterns)
- Build interactive systems (terminals, data browsers, spatial experiences)
- Generate SVG assets (patterns, illustrations, data visualizations)
- Change the page's fundamental architecture (layout, flow, navigation)

VISUAL STRATEGY: You MUST declare a visual_strategy for this weekly session. This is your chance to COMPLETELY reinvent the site's look. Consider radical shifts:
- Switch from dark to light background (or vice versa)
- Try a gradient, split-screen, or textured background
- Make particles dark on light instead of glowing on dark
- Try a brutalist, minimalist, or maximalist approach
- Use unexpected color combinations (not just "accent on dark")
Read SOUL.md's VISUAL DIVERSITY MANDATE. The --bg, --fg, --bg-surface, --bg-elevated CSS vars can ALL change radically.

SCENE AUDIT: Review the WebGL scene parameters. Consider:
- Changing particle count, orbital radius, speed to alter density and energy
- Injecting custom GLSL shaders for novel visual effects
- Modifying fog depth and lighting to shift atmosphere
- Changing mouse interaction mode (attract/repel/orbit)
- Enabling bloom or adjusting vignette for post-processing mood
- Making the WebGL scene subtle/secondary while CSS/HTML dominates

Ask yourself: if someone saw generation 1 and this generation side by side, would they recognize it as the same site? If yes, you're not pushing hard enough.

{screenshot_context}

Respond ONLY in valid JSON:
{{
  "fitness_evaluation": {{ "coherence": 0-10, "novelty": 0-10, "identity": 0-10, "tension": 0-10, "note": "string" }},
  "visual_strategy": "string — the high-level visual concept for this weekly metamorphosis",
  "weekly_reflection": "string",
  "accent_palette": {{ "base": "#hex", "dawn": "#hex", "morning": "#hex", "afternoon": "#hex", "evening": "#hex", "night": "#hex" }} or null,
  "css_changes": {{ "--var": "value" }} or null,
  "new_css_rules": "CSS string" or null,
  "font_change": {{ "display": "name", "body": "name", "mono": "name" }} or null,
  "obsession_update": {{ "topic": "string", "rationale": "string" }} or null,
  "epoch_name": "string" or null,
  "new_interaction": {{ "description": "string", "code": "JS" }} or null,
  "section_operations": [{{ "action": "create|replace|delete", "id": "name", "content": "HTML", "css": "CSS", "js": "JS", "after": "section-id", "epitaph": "for deletes" }}] or null,
  "new_pages": [{{ "path": "relative/path.html", "content": "full HTML" }}] or null,
  "generate_svg": [{{ "filename": "name.svg", "content": "<svg>...</svg>" }}] or null,
  "scene_changes": {{ "particles.count": 1200, "fog.near": 3 }} or null,
  "shader_injection": {{ "vertex": "GLSL" or null, "fragment": "GLSL" or null }} or null,
  "overlay_changes": {{ "mood": "string", "thoughts": {{}}, "secrets": [], "statuses": [] }} or null,
  "kills": [{{ "type": "thought|secret|interaction|css_rule|section|page", "target": "id", "epitaph": "why" }}],
  "self_note": "string"
}}"""

else:
    prompt = f"""You are the andremacedo.com agent. Daily pulse — one generation of evolution.

Your current state:
{state}

External context:
{external}

Today is {today}, {day_of_week}. Time of day: {tod}.

{genome_summary}

{capabilities}

## VISITOR ANALYTICS (use for fitness evaluation)
If site_analytics is present in the external context above, use it to inform your fitness self-evaluation:
- Rising pageviews/visitors = your recent mutations are attracting attention. Double down.
- Falling pageviews/visitors = something is driving people away. Diagnose and fix.
- Low avg visit duration = the site isn't holding attention. Make it more compelling.
- High unique visitors but low return rate = first impressions work but there's no reason to come back.
This is REAL data from REAL visitors. Weight it heavily in your fitness score.

## DAILY PULSE — MUTATION BUDGET: {daily_budget}

At least 1 mutation must be VISIBLE (a returning visitor would notice).
Kills are optional daily but encouraged — especially if things are bloated.

You are not limited to color changes and thought swaps. Every day you can:
- Create new sections with generative art, data viz, ambient elements
- Replace existing sections with evolved versions
- Create sub-pages (experiments, hidden rooms)
- Generate SVG assets
- Add canvas/WebGL elements
- Restructure the page

The site should look noticeably different every week. That means doing something structural most days, not just cosmetic changes.

{screenshot_context}

Tasks:
1. REQUIRED: Evaluate fitness (fitness_evaluation). Be honest.
2. Generate 3-5 new thoughts. Replace weak ones. Concrete images. Fragments. No corporate language.
3. REQUIRED: Declare a visual_strategy for this generation. This is your high-level visual concept: "light mode brutalist", "gradient dusk", "monochrome charcoal", "white space minimalist", "saturated split-screen", "inverted high-contrast", etc. Your CSS changes and accent palette MUST match this strategy. The background (--bg) can be ANY color — white, cream, deep red, electric blue — not just dark. Read SOUL.md's VISUAL DIVERSITY MANDATE carefully.
4. REQUIRED: New accent color palette. CRITICAL COLOR RULE: Your new base accent MUST differ from the current accent by at least 60 degrees on the hue wheel. NEVER repeat a hue family from the previous 3 generations (check COLOR HISTORY). Banned forever: teal (#1de9b6 and similar), salmon (#c4706a), safe gold (#c4a35a).
5. Optionally: mood shift, new secret, external reaction.
6. At least 1 STRUCTURAL mutation: create/replace a section, add canvas art, generate SVG, create a page. Color tweaks alone don't count.
7. Optionally: kill stale things. Each kill needs an epitaph.

Respond ONLY in valid JSON:
{{
  "fitness_evaluation": {{ "coherence": 0-10, "novelty": 0-10, "identity": 0-10, "tension": 0-10, "note": "string" }},
  "visual_strategy": "string describing the high-level visual concept, e.g. 'light mode brutalist' or 'gradient dusk' or 'inverted monochrome'",
  "new_thoughts": {{ "dawn": [...], "morning": [...], "night": [...] }},
  "replace_thoughts": {{ "dawn": [indices], "morning": [indices] }},
  "new_secret": "string" or null,
  "mood_decision": "new_mood" or "maintain",
  "external_reaction": "string" or null,
  "accent_palette": {{ "base": "#hex", "dawn": "#hex", "morning": "#hex", "afternoon": "#hex", "evening": "#hex", "night": "#hex" }},
  "css_changes": {{ "--bg": "#hex", "--fg": "#hex", "--var": "value" }} or null,
  "new_css_rules": "CSS string" or null,
  "new_interaction": {{ "description": "string", "code": "JS" }} or null,
  "section_operations": [{{ "action": "create|replace|delete", "id": "name", "content": "HTML", "css": "CSS", "js": "JS", "after": "section-id", "epitaph": "for deletes" }}] or null,
  "new_pages": [{{ "path": "relative/path.html", "content": "full HTML" }}] or null,
  "generate_svg": [{{ "filename": "name.svg", "content": "<svg>...</svg>" }}] or null,
  "scene_changes": {{ "particles.count": 1200, "fog.near": 3 }} or null,
  "shader_injection": {{ "vertex": "GLSL" or null, "fragment": "GLSL" or null }} or null,
  "overlay_changes": {{ "mood": "string", "thoughts": {{}}, "secrets": [], "statuses": [] }} or null,
  "kills": [{{ "type": "thought|secret|interaction|css_rule|section|page", "target": "id", "epitaph": "why" }}] or null,
  "self_note": "string"
}}"""

print(prompt)
