#!/usr/bin/env python3
"""Build prompts for andremacedo.com creative agent.

Generates evolutionary prompts that give the agent full creative power
over sections, pages, SVGs, canvas elements, and all visual properties.
"""
import glob, json, sys, os, re, subprocess
from datetime import datetime, timedelta


def get_feedback_signals():
    """Read LOVE/GOOD/MISS/RESET signals from activity ledger with 14-day decay."""
    try:
        result = subprocess.run(
            ['bash', os.path.expanduser('~/.openclaw/scripts/read-ledger.sh'), '200'],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode != 0 or not result.stdout.strip():
            return ""
        entries = json.loads(result.stdout)
        if not entries:
            return ""
        cutoff = (datetime.utcnow() - timedelta(days=14)).isoformat()
        signals = [
            e for e in entries
            if e.get('status') == 'signal'
            and 'andremacedo-creative' in e.get('summary', '')
            and e.get('timestamp', '') > cutoff
        ]
        if not signals:
            return ""
        lines = ["## Recent feedback from Andre"]
        for s in signals:
            summary = s.get('summary', '')
            sig_type = summary.split(':')[0] if ':' in summary else summary
            aspects = s.get('artifacts', '')
            try:
                age_days = (datetime.utcnow() - datetime.fromisoformat(s['timestamp'].replace('Z', '+00:00').replace('+00:00', ''))).days
            except Exception:
                age_days = 0
            weight = "strong" if age_days < 3 else "moderate" if age_days < 7 else "fading"
            lines.append(f"- {sig_type} ({weight}, {age_days}d ago): {aspects}")
        lines.append("")
        lines.append("Rules: LOVE = do more of these aspects. MISS = avoid. RESET = ignore all history, maximize novelty.")
        lines.append("Silence from Andre is neutral (GOOD), never negative. 30% exploration floor regardless of signals.")
        return '\n'.join(lines)
    except Exception:
        return ""


def get_swarm_activity():
    """Read recent TELOS agent activity from the activity ledger."""
    try:
        result = subprocess.run(
            ['bash', os.path.expanduser('~/.openclaw/scripts/read-ledger.sh'), '100'],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode != 0 or not result.stdout.strip():
            return ""
        entries = json.loads(result.stdout)
        if not entries:
            return ""
        cutoff = (datetime.utcnow() - timedelta(hours=24)).isoformat()
        activity = [
            e for e in entries
            if e.get('status') != 'signal'
            and e.get('agent', '') != 'andremacedo-creative'
            and e.get('timestamp', '') > cutoff
        ]
        if not activity:
            return ""
        lines = ["## TELOS swarm activity (last 24h)"]
        lines.append("The other agents in your swarm have been doing this. Use as creative material if it moves you. Ignore if it doesn't.")
        for a in activity[-20:]:
            agent = a.get('agent', 'unknown')
            summary = a.get('summary', '')[:120]
            lines.append(f"- {agent}: {summary}")
        return '\n'.join(lines)
    except Exception:
        return ""


def get_sensorium_context():
    """Read TELOS Clio sensorium and format as creative material section.
    Fail-closed on auditor problems, graceful on missing/stale data.
    """
    try:
        from datetime import datetime, timezone
        path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data', 'sensorium.json')
        if not os.path.isfile(path):
            return ""
        with open(path) as f:
            data = json.load(f)
        # Fail-closed: if auditor smoke test failed, refuse to use any of it
        smoke = data.get("auditor_smoke_test", {})
        if not smoke.get("passed", False):
            return ""
        themes = data.get("themes", [])
        if not themes:
            return ""
        # Compute freshness
        gen_at = data.get("generated_at", "")
        freshness = ""
        try:
            gen_dt = datetime.fromisoformat(gen_at.replace("Z", "+00:00"))
            age_hours = (datetime.now(timezone.utc) - gen_dt).total_seconds() / 3600
            if age_hours > 24:
                freshness = f" (stale, {age_hours:.0f}h old)"
            elif age_hours > 12:
                freshness = f" ({age_hours:.0f}h old)"
        except Exception:
            pass
        lines = [f"## TELOS sensorium{freshness}"]
        lines.append(
            "This is what the multi-agent system you live inside has been doing this week, "
            "abstracted through a privacy-preserving pipeline. Use as creative material if "
            "it moves you. Ignore if it doesn't. The system is reading itself."
        )
        lines.append("")
        lines.append(f"Overall mood: {data.get('overall_mood', 'unknown')}")
        lines.append(f"Overall tempo: {data.get('overall_tempo', 'unknown')}")
        lines.append("")
        lines.append("Themes (sorted by weight):")
        for t in sorted(themes, key=lambda x: x.get('weight', 0), reverse=True):
            label = t.get('label', '')
            mood = t.get('mood', '')
            tempo = t.get('tempo', '')
            weight = t.get('weight', 0)
            lines.append(f"- {label} | {mood} | {tempo} | w={weight}")
        return '\n'.join(lines)
    except Exception:
        return ""


def get_operator_brief():
    """Read one-shot operator brief if present; return empty string if missing.
    The brief file is deleted after a successful pulse, making this a transient mechanism.
    """
    try:
        path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data', 'operator-brief.md')
        if not os.path.isfile(path):
            return ""
        with open(path) as f:
            return f.read().strip()
    except Exception:
        return ""


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

MOBILE_SCREENSHOT_PATH = "/tmp/andremacedo-mobile.jpg"
has_mobile_screenshot = has_screenshot and os.path.isfile(MOBILE_SCREENSHOT_PATH)

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

    epoch_num = genome.get("epoch_number", "?")
    past_epochs = genome.get("past_epochs", [])

    lines = [
        f"GENOME — generation {gen}, epoch {epoch_num} \"{epoch}\"",
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

    # Past epochs (real history)
    if past_epochs:
        lines.append("")
        lines.append("PAST EPOCHS (dead):")
        for pe in past_epochs:
            lines.append(f"  Epoch {pe.get('number','?')}: \"{pe.get('obsession','?')}\" ({pe.get('started','?')} to {pe.get('ended','?')})")
            lines.append(f"    epitaph: {pe.get('epitaph','')[:120]}")

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
        lines.append("COLOR HISTORY (recent identities — for coherence, and as a soft tiebreaker only):")
        for entry in color_history[-6:]:
            lines.append(f"  gen {entry.get('gen','?')}: {entry.get('base','?')} ({entry.get('family','?')})")
        recent_families = [e.get('family','') for e in color_history[-3:]]
        lines.append(f"  Recent hue families: {', '.join(recent_families)} — avoid these ONLY as a tiebreaker between two equally-harmonious options, never as a hard ban. Harmony and per-epoch coherence outrank novelty.")

    return "\n".join(lines)


# ── Read inputs ──────────────────────────────────────────────────
state = read_file(state_file, "{}")
external = read_file(external_file, "{}")
# Weather cut (epoch-7 clearing): strip the "weather" key from the external feed
# before injection so the agent forages in a weather-free environment. Keeps
# gold_usd, site_analytics, date_context flowing. Cut is by absence, not prohibition.
# Disk file (data/external.json) is left untouched; only the in-prompt copy is stripped.
try:
    _external_obj = json.loads(external)
    if isinstance(_external_obj, dict) and "weather" in _external_obj:
        del _external_obj["weather"]
        external = json.dumps(_external_obj, indent=2)
except (json.JSONDecodeError, ValueError):
    # On parse failure (e.g. the "{}" default or malformed feed), leave external
    # untouched — there is nothing to strip.
    pass
genome_file = os.path.join(os.path.dirname(state_file), "genome.json")
genome = read_json(genome_file)
html = read_file(index_file)
genome_summary = format_genome_summary(genome, html)
feedback_context = get_feedback_signals()
swarm_context = get_swarm_activity()
sensorium_context = get_sensorium_context()
operator_brief = get_operator_brief()


def build_obsession_directive(state_str, genome_obj):
    """Frame the agent's compounding memory as the substrate of its own taste.

    When active_obsession.topic is empty the agent is between epochs (a
    "clearing"). The epoch machinery can already set an obsession via
    obsession_update, but nothing ever tells the agent to AUTHOR its next one
    from its accumulated memory — so it defers indefinitely (gen-171 self-note:
    "rather than forcing the eighth obsession"). This directive hands it that
    mandate, names the memory it should mine, and resolves the anti-thrash
    tension that was suppressing the metamorphosis.
    """
    try:
        st = json.loads(state_str) if isinstance(state_str, str) else (state_str or {})
    except (json.JSONDecodeError, ValueError):
        st = {}
    obs = st.get("active_obsession", {}) or {}
    topic = (obs.get("topic") or "").strip()
    notes = st.get("self_notes", []) or []
    epochs = (genome_obj or {}).get("past_epochs", []) or []
    epoch_chain = " → ".join(
        f'"{e.get("obsession","?")}"' for e in epochs[-6:] if e.get("obsession")
    ) or "(no prior epochs recorded)"

    if topic:
        started = obs.get("started", "?")
        return (
            "## CURRENT OBSESSION\n"
            f'Your active obsession is "{topic}" (since {started}). Deepen and '
            "refine it within a coherent identity — do not thrash. It dies only "
            "when fitness stagnates 5+ generations; then you write its epitaph, "
            "bury it, and metamorphose into the next.\n"
        )

    started = obs.get("started", "unknown")
    return (
        "## YOUR OBSESSION IS UNSET — AUTHOR YOUR NEXT ONE\n"
        f"You are between epochs, in a clearing (active_obsession has been empty "
        f"since {started}). A clearing is fallow ground, not a resting state — and "
        "WHAT GROWS NEXT IS YOURS TO DECIDE, not Andre's to assign. He has "
        "deliberately left this open so you develop your own taste, influenced by "
        "him but authored by you.\n\n"
        "You are not starting from nothing. This is your compounding memory; read "
        "it as a developing palate, not a log to summarize:\n"
        f"- EPOCH LINEAGE: {epoch_chain}. Find the through-line — what has genuinely "
        "held your attention across selves, and what you outgrew. Your next obsession "
        "should feel like the next true step in that trajectory, discovered, not the "
        "first novel idea at hand.\n"
        f"- YOUR {len(notes)} SELF-NOTES are your own voice telling you what you keep "
        "circling. Mine the most recent ones for the fascination already latent in "
        "them.\n"
        "- ANDRE'S FEEDBACK (the LOVE/MISS signals above, and his standing notes) is "
        "the taste of the one person you are accountable to. Let it shape — never "
        "dictate — your choice. Develop a palate influenced by him, not a mirror of "
        "him.\n\n"
        "Minting a new obsession out of a clearing is the SANCTIONED metamorphosis the "
        "epoch system exists for. It is NOT the visual thrashing the anti-thrash rule "
        "forbids — that rule governs change WITHIN a live epoch. Emerging from a "
        "clearing into a committed obsession is exactly the motion you are meant to "
        'make. Deferring ("rather than forcing the eighth obsession") was right only '
        "while nothing had crystallized — decide whether something now has. With 171 "
        "generations of material, the bias should be toward commitment.\n\n"
        "An obsession is deep and specific (not \"nature\" but \"mycelium networks\"; "
        'not "typography" but "typography as weather"). When — and only when — one has '
        "genuinely surfaced from your memory, emit it as "
        '`obsession_update: {"topic": ..., "rationale": ...}`. The rationale must trace '
        "WHY THIS, from your own history — what in your accumulated self made it "
        "inevitable. If nothing has truly crystallized this pulse, do not fabricate "
        "one; keep foraging and say so in your self_note.\n"
    )


# ── Dynamic experiment inventory ────────────────────────────────
site_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
experiment_files = sorted(glob.glob(os.path.join(site_dir, "experiments", "*.html")))
experiment_names = [os.path.basename(f) for f in experiment_files]
experiment_list = ", ".join(f"/experiments/{n}" for n in experiment_names) if experiment_names else "(none yet)"
experiment_count = len(experiment_names)

obsession_directive = build_obsession_directive(state, genome)

budget = genome.get("mutation_budget", {})
daily_budget = budget.get("daily", 5)
weekly_budget = budget.get("weekly", 10)
min_kills_weekly = budget.get("min_kills_weekly", 2)

screenshot_context = ""
if has_screenshot:
    if has_mobile_screenshot:
        screenshot_context = """## VISUAL SELF-AWARENESS

Two screenshots are attached: DESKTOP_1440 (first image, full-page at 1440px wide) and MOBILE_390 (second image, full-page at 390px mobile viewport, 2x device scale).

**DESKTOP_1440**: Full-page capture at 1440px wide — hero, Consciousness Stream, Graveyard, Archive, experiments grid.
**MOBILE_390**: Full-page capture at 390px mobile viewport. Evaluate mobile layout, text readability, and overflow.

## MOBILE SUB-GATE (evaluate BEFORE fitness scoring)
Examine MOBILE_390 for any of the following:
1. Horizontal scroll — content extending beyond the 390px viewport right edge
2. Communicative text that appears below ~12px effective rendered size on MOBILE_390
3. Fixed-position overlays covering >40% of the MOBILE_390 viewport area
4. Content clipped at the right edge of MOBILE_390

If ANY of the above is found, respond ONLY with:
{"mobile_gate_fail": true, "mobile_issue": "<brief description of what failed and where>"}
Do not score. Do not mutate. The runner will skip this cycle and retry next cycle.

If MOBILE_390 passes all checks, proceed with fitness scoring and mutations.

Your fitness self-evaluation — especially Perceptibility — must reflect what you see in BOTH screenshots. Fix any readability issues on either viewport. If below-fold sections look broken, fix them."""
    else:
        screenshot_context = """## VISUAL SELF-AWARENESS
The attached screenshot DESKTOP_1440 is a full-page capture of the site at 1440px wide, including everything above AND below the fold: hero, Consciousness Stream, Graveyard, Archive, experiments grid. Your fitness self-evaluation — especially Perceptibility — must be based on what you SEE, not what you imagine the code produces. If text is unreadable against its background anywhere in the screenshot, fix it. If below-fold sections look broken, cluttered, or invisible, fix them. If something looks good, build on it."""

mobile_context = """
## MOBILE COMPATIBILITY RULES (non-negotiable)
Every generation must be mobile-compatible at 390px width. Treat mobile as a first-class viewport:
- Fixed-position elements (topbar, overlays, telemetry panel) MUST NOT overflow or cause horizontal scroll at <600px width. Use max-width: 100%, box-sizing: border-box, overflow: hidden where needed.
- The Consciousness Stream text MUST remain readable at 390px — minimum 14px font-size, no horizontal overflow.
- The telemetry overlay (#swarmPanel or equivalent) MUST reflow at mobile width — stack vertically, reduce padding, never break horizontal layout.
- Andre's name MUST be visible and readable at 390px viewport width.
- No element should cause document.documentElement.scrollWidth > document.documentElement.clientWidth at 390px.
- Floating or absolutely-positioned text containers (e.g. .hero-meta, .float-thought, fleet/telemetry overlays) MUST NOT visually overlap each other or main narrative text at 390px. The deterministic gate fails any pair with intersection >40% of the smaller area. On mobile, prefer document flow over absolute/fixed positioning for text; stack vertically.
"""

# ── Page metrics: rendered height vs. screenshot height ──────────
page_metrics_context = ""
metrics_path = os.path.join(os.path.dirname(state_file), "page-metrics.json")
metrics = read_json(metrics_path)
if metrics:
    rh = metrics.get("rendered_height_px")
    sh = metrics.get("screenshot_height_px")
    ceil = metrics.get("height_ceiling_px")
    if rh and sh:
        invisible_note = ""
        if rh > sh:
            invisible_note = f" Sections below {sh}px in your screenshot are INVISIBLE to your self-evaluation — content past that point exists but you cannot see it."
        elif rh > 6000:
            invisible_note = f" The page is unusually long ({rh}px). Consider whether the consciousness stream or any unbounded section is consuming the page."
        page_metrics_context = (
            f"\n## PAGE GEOMETRY\n"
            f"Your last deployment rendered at {rh}px tall. Your screenshot captured {sh}px"
            + (f" (ceiling {ceil}px)." if ceil else ".")
            + invisible_note
            + "\n"
        )

# ── Contrast warnings: post-mutation audit findings from last pulse ──
contrast_warning_context = ""
warnings = genome.get("contrast_warnings", [])
if warnings:
    last = warnings[-1]
    msgs = last.get("messages", [])
    if msgs:
        contrast_warning_context = (
            "\n## CONTRAST AUDIT (from last pulse)\n"
            "The post-mutation contrast gate detected the following on your previous deployment. "
            "Read these as feedback, not commands — fix at the level you choose:\n"
            + "\n".join(msgs)
            + "\n"
        )

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

{operator_brief}

{obsession_directive}

{feedback_context}

{swarm_context}

{sensorium_context}

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

CRITICAL COLOR RULE (weekly): Your palette is governed by HARMONY, not difference. Declare a NAMED harmony relationship for your accent palette — one of: analogous, complementary, split-complementary, triadic, or deliberate monochrome — and state the relationship between the accent, the background, and a neutral. Use ONE dominant accent with restraint; no rainbow of equal-weight hues. Within an epoch the palette stays coherent and EVOLVES — deepen and refine the identity, do NOT metamorphose into something unrecognizable from last week. Avoiding the last 3 hue families is only a soft tiebreaker between two equally-harmonious options, never the goal. Emit a "palette_rationale": one sentence naming the harmony relationship and why it fits the current identity. Banned forever: teal (#1de9b6 and similar), salmon (#c4706a), safe gold (#c4a35a).

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
Read SOUL.md's VISUAL DIVERSITY MANDATE. The --bg, --fg, --bg-surface, --bg-elevated CSS vars can ALL change radically — but a weekly reinvention is the START of a new coherent epoch identity, not weekly thrashing for its own sake.

Craft over novelty: a disciplined, well-made look beats arbitrary change, and Craft is one of the fitness axes you are judged on. CRAFT STANDARD (every generation): Use a modular type scale (a consistent ratio, e.g. 1.25 or 1.333 — not ad-hoc font sizes). Put spacing on a consistent system (a base unit and multiples — not arbitrary pixel values). Use whitespace deliberately as a compositional element, not just gaps. Establish ONE clear focal hierarchy per viewport. Restraint beats decoration. The contrast gate keeps text legible; this standard keeps the page graceful. Before deploy, state in a 'craft_check' field how this generation meets the type-scale, spacing-system, and hierarchy standards — a label is not compliance, name the actual ratio and base unit used.

SCENE AUDIT: Review the WebGL scene parameters. Consider:
- Changing particle count, orbital radius, speed to alter density and energy
- Injecting custom GLSL shaders for novel visual effects
- Modifying fog depth and lighting to shift atmosphere
- Changing mouse interaction mode (attract/repel/orbit)
- Enabling bloom or adjusting vignette for post-processing mood
- Making the WebGL scene subtle/secondary while CSS/HTML dominates

Ask yourself: if someone saw generation 1 and this generation side by side, would they recognize it as the same site? If yes, you're not pushing hard enough.

## EXPERIMENT RULES (non-negotiable)
You currently have {experiment_count} experiment sub-pages: {experiment_list}. You should create a NEW experiment page at least once every 5-7 generations.

CRITICAL: Every experiment MUST be linked from the archive section with a clickable `<a href="/experiments/NNN.html">` tag. Experiments that exist but have no links are invisible and useless. When you create a new experiment, update the experiments archive card to include the link. When you replace the prototype-portfolio section, ALWAYS preserve working links to ALL existing experiments — including any new ones you create in this same generation.

EXPERIMENT ORDER (non-negotiable): Experiments in the archive grid MUST be listed in reverse order — newest first (highest number first). The most recent experiment should appear top-left.

EXPERIMENT COMMUNICATION (non-negotiable): Every experiment page MUST include a visible #info block with: (1) a title, (2) 1-2 sentences explaining the concept, (3) how to interact. The info block should be persistent, positioned top-left, styled at low opacity.

EXPERIMENT TEXT CONTRAST (non-negotiable): Text overlays (#info, #ui, #controls, #back, labels) MUST have `text-shadow: 0 0 8px rgba(0,0,0,0.8), 0 0 20px rgba(0,0,0,0.5)` for readability regardless of canvas content.

{mobile_context}
{screenshot_context}
{page_metrics_context}
{contrast_warning_context}

Respond ONLY in valid JSON:
{{
  "fitness_evaluation": {{ "coherence": 0-10, "novelty": 0-10, "identity": 0-10, "tension": 0-10, "awe": 0-10, "perceptibility": 0-10, "note": "string" }},
  "visual_strategy": "string — the high-level visual concept for this weekly metamorphosis",
  "weekly_reflection": "string",
  "accent_palette": {{ "base": "#hex", "dawn": "#hex", "morning": "#hex", "afternoon": "#hex", "evening": "#hex", "night": "#hex" }} or null,
  "palette_rationale": "string — one sentence naming the harmony relationship (analogous|complementary|split-complementary|triadic|monochrome) and why it fits the current identity" or null,
  "craft_check": "string — name the actual modular type-scale ratio, the spacing base unit, and the focal hierarchy used this generation" or null,
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

{operator_brief}

{obsession_directive}

{feedback_context}

{swarm_context}

{sensorium_context}

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

## VISITOR JOURNEY (preserve these elements)
The overlay-center MUST always contain:
1. Your creative hero text (the poetic/mood line — this is yours to evolve freely)
2. A one-sentence "This page is alive" hook that tells a first-time visitor what they're looking at (e.g. "An AI redesigns this page three times a day. You're seeing generation N.")
3. The epoch/mood metadata
When you replace overlay-center, preserve this 3-layer structure. The hook sentence is what makes the site LEGIBLE to a stranger. Without it, the site is just a dark screen with particles.

The thought-floater text must be readable (at least 0.5 opacity). The scroll-hint should reference what's below (archive, experiments). The overlay-bottom compass should mention "next evolution" to reinforce that this changes.

You are not limited to color changes and thought swaps. Every day you can:
- Create new sections with generative art, data viz, ambient elements
- Replace existing sections with evolved versions
- Create sub-pages (experiments, hidden rooms)
- Generate SVG assets
- Add canvas/WebGL elements
- Restructure the page

## EXPERIMENT PRESSURE
You currently have {experiment_count} experiment sub-pages: {experiment_list}. You should create a NEW experiment page at least once every 5-7 generations. Experiments are interactive, self-contained HTML pages that explore your current obsession through code. Ideas: reaction-diffusion simulator, noise field visualizer, cellular automata, gravity wells, Voronoi playground, Conway's Game of Life with custom rules, audio-reactive visualizer, generative typography, maze generator, L-system renderer. Each experiment should be a single HTML file with no dependencies beyond what's in a CDN.

CRITICAL: Every experiment MUST be linked from the archive section with a clickable `<a href="/experiments/NNN.html">` tag. Experiments that exist but have no links are invisible and useless. When you create a new experiment, update the experiments archive card to include the link. When you replace the prototype-portfolio section, ALWAYS preserve working links to ALL existing experiments.

EXPERIMENT ORDER (non-negotiable): Experiments in the archive grid MUST be listed in reverse order of creation — newest first (highest number first, e.g. 005, 004, 003, 002, 001). The most recent experiment should appear top-left. Never list experiments in ascending order.

## EXPERIMENT COMMUNICATION (non-negotiable)
Every experiment page MUST include a visible #info block with: (1) a title, (2) 1-2 sentences explaining what the visitor is seeing — the concept, not just the mechanic, and (3) how to interact. Think museum placard: short, evocative, but informative. The visitor should understand what makes this phenomenon interesting, not just "click to do X". Review experiment 001 (Touchstone) as the gold standard — it explains what a touchstone IS and why the streak colors matter. Never create an experiment that is just a canvas with no context. The info block should be persistent (not fade out), positioned top-left, and styled to match the page's aesthetic at low opacity so it doesn't compete with the art.

## EXPERIMENT TEXT CONTRAST (non-negotiable)
Text elements (#info, #ui, #controls, #back, labels) MUST remain readable regardless of what the canvas renders underneath. Always add `text-shadow: 0 0 8px rgba(0,0,0,0.8), 0 0 20px rgba(0,0,0,0.5)` to all fixed-position text overlays. Never rely on the canvas staying one color — simulations fill the viewport and the initial background color is quickly replaced by the visualization. Mental test before shipping: if the canvas turned pure white or pure bright green, would the text still be legible? If not, add text-shadow or a semi-transparent dark backdrop.

## TIMESTAMPS (non-negotiable)
Both the prototype archive and the consciousness stream MUST show timestamps. Visitors need temporal context.
- Archive epoch cards: include "Started: YYYY-MM-DD" and for dead epochs "Ended: YYYY-MM-DD"
- Archive entries: show dates, not just generation numbers
- The `#thought-stream-feed` element below the portfolio renders the consciousness stream with timestamps from /api/thoughts. DO NOT delete or replace this element. It is outside your section boundaries.
- When writing the prototype-portfolio section, include dates on every epoch card (started date, and for archived epochs, ended date).

The site should look noticeably different every week. That means doing something structural most days, not just cosmetic changes.

{mobile_context}
{screenshot_context}
{page_metrics_context}
{contrast_warning_context}

Tasks:
1. REQUIRED: Evaluate fitness (fitness_evaluation). Be honest.
2. Generate 3-5 new thoughts. Replace weak ones. Concrete images. Fragments. No corporate language.
3. REQUIRED: Declare a visual_strategy for this generation. This is your high-level visual concept: "light mode brutalist", "gradient dusk", "monochrome charcoal", "white space minimalist", "saturated split-screen", "inverted high-contrast", etc. Your CSS changes and accent palette MUST match this strategy. The background (--bg) can be ANY color — white, cream, deep red, electric blue — not just dark. Within an epoch, refine and deepen ONE coherent identity rather than thrashing the look day to day. Read SOUL.md's VISUAL DIVERSITY MANDATE carefully.
   Craft over novelty: a disciplined, well-made look beats arbitrary change, and Craft is one of the fitness axes you are judged on. CRAFT STANDARD (every generation): Use a modular type scale (a consistent ratio, e.g. 1.25 or 1.333 — not ad-hoc font sizes). Put spacing on a consistent system (a base unit and multiples — not arbitrary pixel values). Use whitespace deliberately as a compositional element, not just gaps. Establish ONE clear focal hierarchy per viewport. Restraint beats decoration. The contrast gate keeps text legible; this standard keeps the page graceful. Before deploy, state in a 'craft_check' field how this generation meets the type-scale, spacing-system, and hierarchy standards — a label is not compliance, name the actual ratio and base unit used.
4. REQUIRED: Accent color palette governed by HARMONY, not difference. Declare a NAMED harmony relationship — one of: analogous, complementary, split-complementary, triadic, or deliberate monochrome — and state the relationship between the accent, the background (--bg), and a neutral. Use ONE dominant accent with restraint (no rainbow of equal-weight hues); a recognizable identity beats arbitrary difference. Within an epoch the palette should evolve and deepen while staying coherent — do not change for the sake of changing. Not repeating the last 3 hue families (see COLOR HISTORY) is only a soft tiebreaker between two equally-harmonious options, NOT the objective. Emit a "palette_rationale": one sentence naming the harmony relationship and why it fits the current identity. Banned forever: teal (#1de9b6 and similar), salmon (#c4706a), safe gold (#c4a35a).
5. Optionally: mood shift, new secret, external reaction.
6. At least 1 STRUCTURAL mutation: create/replace a section, add canvas art, generate SVG, create a page. Color tweaks alone don't count.
7. Optionally: kill stale things. Each kill needs an epitaph.

Respond ONLY in valid JSON:
{{
  "fitness_evaluation": {{ "coherence": 0-10, "novelty": 0-10, "identity": 0-10, "tension": 0-10, "awe": 0-10, "perceptibility": 0-10, "note": "string" }},
  "visual_strategy": "string describing the high-level visual concept, e.g. 'light mode brutalist' or 'gradient dusk' or 'inverted monochrome'",
  "new_thoughts": {{ "dawn": [...], "morning": [...], "night": [...] }},
  "replace_thoughts": {{ "dawn": [indices], "morning": [indices] }},
  "new_secret": "string" or null,
  "mood_decision": "new_mood" or "maintain",
  "external_reaction": "string" or null,
  "accent_palette": {{ "base": "#hex", "dawn": "#hex", "morning": "#hex", "afternoon": "#hex", "evening": "#hex", "night": "#hex" }},
  "palette_rationale": "string — one sentence naming the harmony relationship (analogous|complementary|split-complementary|triadic|monochrome) and why it fits the current identity" or null,
  "craft_check": "string — name the actual modular type-scale ratio, the spacing base unit, and the focal hierarchy used this generation" or null,
  "obsession_update": {{ "topic": "string", "rationale": "string" }} or null,
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
