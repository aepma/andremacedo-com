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

## WEEKLY SESSION — MUTATION BUDGET: {weekly_budget}

You MUST kill at least {min_kills_weekly} things. Prune aggressively. If the night thought pool has >10 entries, kill the weakest ones.

This is your moment for STRUCTURAL ambition:
- Rewrite entire sections (replace hero, reimagine prototypes, restructure syslog)
- Create new pages (experiment galleries, hidden rooms, data essays)
- Add generative art (canvas fractals, WebGL shaders, procedural SVG patterns)
- Build interactive systems (terminals, data browsers, spatial experiences)
- Generate SVG assets (patterns, illustrations, data visualizations)
- Change the page's fundamental architecture (layout, flow, navigation)

Ask yourself: if someone saw generation 1 and this generation side by side, would they recognize it as the same site? If yes, you're not pushing hard enough.

Respond ONLY in valid JSON:
{{
  "fitness_evaluation": {{ "coherence": 0-10, "novelty": 0-10, "identity": 0-10, "tension": 0-10, "note": "string" }},
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

Tasks:
1. REQUIRED: Evaluate fitness (fitness_evaluation). Be honest.
2. Generate 3-5 new thoughts. Replace weak ones. Concrete images. Fragments. No corporate language.
3. REQUIRED: New accent color palette. Be adventurous. No salmon (#c4706a), no gold (#c4a35a).
4. Optionally: mood shift, new secret, external reaction.
5. At least 1 STRUCTURAL mutation: create/replace a section, add canvas art, generate SVG, create a page. Color tweaks alone don't count.
6. Optionally: kill stale things. Each kill needs an epitaph.

Respond ONLY in valid JSON:
{{
  "fitness_evaluation": {{ "coherence": 0-10, "novelty": 0-10, "identity": 0-10, "tension": 0-10, "note": "string" }},
  "new_thoughts": {{ "dawn": [...], "morning": [...], "night": [...] }},
  "replace_thoughts": {{ "dawn": [indices], "morning": [indices] }},
  "new_secret": "string" or null,
  "mood_decision": "new_mood" or "maintain",
  "external_reaction": "string" or null,
  "accent_palette": {{ "base": "#hex", "dawn": "#hex", "morning": "#hex", "afternoon": "#hex", "evening": "#hex", "night": "#hex" }},
  "css_changes": {{ "--var": "value" }} or null,
  "new_css_rules": "CSS string" or null,
  "new_interaction": {{ "description": "string", "code": "JS" }} or null,
  "section_operations": [{{ "action": "create|replace|delete", "id": "name", "content": "HTML", "css": "CSS", "js": "JS", "after": "section-id", "epitaph": "for deletes" }}] or null,
  "new_pages": [{{ "path": "relative/path.html", "content": "full HTML" }}] or null,
  "generate_svg": [{{ "filename": "name.svg", "content": "<svg>...</svg>" }}] or null,
  "kills": [{{ "type": "thought|secret|interaction|css_rule|section|page", "target": "id", "epitaph": "why" }}] or null,
  "self_note": "string"
}}"""

print(prompt)
