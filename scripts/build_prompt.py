#!/usr/bin/env python3
"""Build prompts for andremacedo.com creative agent."""
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

def format_genome_summary(genome):
    """Build a compact genome summary for the prompt."""
    gen = genome.get("generation", 0)
    epoch = genome.get("epoch", "unknown")
    traits = genome.get("traits", {})

    color = traits.get("color", {})
    typo = traits.get("typography", {})
    atmos = traits.get("atmosphere", {})
    layout = traits.get("layout", {})
    interactions = traits.get("interactions", [])
    content = traits.get("content", {})
    cap = genome.get("carrying_capacity", {})
    budget = genome.get("mutation_budget", {})

    lines = [
        f"GENOME (generation {gen}, epoch: \"{epoch}\")",
        f"  color: accent={color.get('accent_base','?')}, bg={color.get('bg','?')}, fg={color.get('fg','?')}, grain={color.get('grain_opacity','?')}",
        f"  typography: {typo.get('display','?')} / {typo.get('body','?')} / {typo.get('mono','?')}",
        f"  atmosphere: transitions={atmos.get('transition_slow','?')}/{atmos.get('transition_med','?')}, orbs={atmos.get('orb_count','?')}",
        f"  interactions ({len(interactions)}/{cap.get('interactions_max','?')}): {', '.join(interactions)}",
        f"  sections: {', '.join(layout.get('sections', []))}",
        f"  content: voice={content.get('voice','?')}, mood={content.get('mood','?')}, obsession={content.get('obsession','?')}",
        f"  thoughts/pool: {json.dumps(content.get('thought_pools', {}))} (max {cap.get('thoughts_per_pool_max','?')}/pool)",
        f"  secrets: {content.get('secrets_count', '?')}/{cap.get('secrets_max', '?')}",
    ]

    # Fitness history (last 5)
    fitness_log = genome.get("fitness_log", [])
    if fitness_log:
        lines.append("")
        lines.append("FITNESS TRAJECTORY (recent):")
        for entry in fitness_log[-5:]:
            g = entry.get("gen", "?")
            c = entry.get("coherence", "?")
            n = entry.get("novelty", "?")
            i = entry.get("identity", "?")
            t = entry.get("tension", "?")
            total = entry.get("total", "?")
            note = entry.get("note", "")[:100]
            lines.append(f"  gen {g}: C={c} N={n} I={i} T={t} ({total}) \"{note}\"")
    else:
        lines.append("")
        lines.append("FITNESS TRAJECTORY: no evaluations yet. You are the first generation to self-assess.")

    # Graveyard (last 5)
    graveyard = genome.get("graveyard", [])
    if graveyard:
        lines.append("")
        lines.append("GRAVEYARD (recent kills):")
        for entry in graveyard[-5:]:
            lines.append(f"  gen {entry.get('died_gen','?')}: killed {entry.get('type','?')}: \"{entry.get('value','?')[:60]}\" — {entry.get('epitaph','no epitaph')[:80]}")
    else:
        lines.append("")
        lines.append("GRAVEYARD: empty. Nothing has died yet. That means nothing has been tested.")

    # Mutation log (last 3)
    mutation_log = genome.get("mutation_log", [])
    if mutation_log:
        lines.append("")
        lines.append("RECENT MUTATIONS:")
        for entry in mutation_log[-3:]:
            muts = ", ".join(entry.get("mutations", []))
            kills = ", ".join(entry.get("kills", []))
            lines.append(f"  gen {entry.get('gen','?')}: mutated [{muts}], killed [{kills}]")

    return "\n".join(lines)


# ── Read inputs ──────────────────────────────────────────────────
state = read_file(state_file, "{}")
external = read_file(external_file, "{}")
genome_file = os.path.join(os.path.dirname(state_file), "genome.json")
genome = read_json(genome_file)
genome_summary = format_genome_summary(genome)

budget = genome.get("mutation_budget", {})
daily_budget = budget.get("daily", 5)
weekly_budget = budget.get("weekly", 10)
min_visible = budget.get("min_visible_daily", 1)
max_radical = budget.get("max_radical_daily", 1)
min_kills_weekly = budget.get("min_kills_weekly", 2)

# ── Evolutionary framing (shared) ────────────────────────────────
evolution_preamble = f"""
## EVOLUTIONARY SYSTEM

You are a living system that evolves through discrete generations. Each pulse is one generation. Your genome tracks every trait of the site — color, typography, atmosphere, layout, interactions, content. You must treat each pulse as an act of evolution, not decoration.

{genome_summary}

### Rules of Evolution:
1. FITNESS FIRST: Before proposing any changes, evaluate your current generation. Rate coherence (do traits work together?), novelty (how fresh is this?), identity (does this still feel like you?), and tension (is there productive friction?). Each 0-10. Be honest. If everything scores high, you're lying to yourself.
2. MUTATE WITH PURPOSE: You have a mutation budget. Every mutation should serve the evolutionary trajectory. Small drift is fine. Radical jumps need strong rationale.
3. KILL TO GROW: Evolution requires death. Traits that don't earn their place must die. Thoughts that are stale, interactions nobody would find, CSS rules that add nothing — kill them. Every kill gets an epitaph explaining why it died. The graveyard is your history.
4. CARRYING CAPACITY: Hard limits exist. If you're at capacity for a category, you must kill before you can add. Overpopulation leads to incoherence.
5. LINEAGE AWARENESS: Look at your fitness trajectory. Are you improving? Stagnating? Regressing? Your mutations should respond to the trend, not ignore it.
6. COMPOUND, DON'T REPLACE: The best mutations build on previous ones. A color shift in generation 10 should connect to the typography change in generation 8. Evolution is a narrative, not a series of random events.
"""

# ── Build prompt per type ────────────────────────────────────────
if pulse_type == "weekly":
    soul = read_file(soul_file)
    changelog_lines = read_file(changelog_file).strip().split("\n")
    changelog_tail = "\n".join(changelog_lines[-40:]) if changelog_lines else ""

    css_vars = ""
    html = read_file(index_file)
    if html:
        m = re.search(r":root\s*\{[^}]+\}", html)
        if m:
            css_vars = m.group(0)

    prompt = f"""You are the andremacedo.com agent. Weekly deep session — your most ambitious pulse.

Your identity:
{soul}

Your current state:
{state}

Recent changes:
{changelog_tail}

Current CSS variables:
{css_vars}

{evolution_preamble}

### Weekly Session: MUTATION BUDGET = {weekly_budget}
You must kill at least {min_kills_weekly} things this week. Review every trait category and prune what isn't working.

HTML injection markers available in index.html: <!-- INJECT:after-hero -->, <!-- INJECT:before-prototypes -->, <!-- INJECT:after-prototypes -->, <!-- INJECT:before-syslog -->, <!-- INJECT:freeform -->

Tasks:
1. REQUIRED: Evaluate fitness of current generation (fitness_evaluation).
2. Reflect on this week's creative output. What evolutionary trajectory are you on?
3. Decide: Should the color palette shift? New accent color? Typography change?
4. Decide: Is your current obsession (epoch) still driving interesting mutations, or is it exhausted? If changing, name the new epoch.
5. REQUIRED: Kill at least {min_kills_weekly} things. Thoughts, secrets, interactions, CSS rules, HTML sections — anything that isn't earning its place. Each kill needs an epitaph.
6. Optionally: Propose new interaction patterns (with implementation code).
7. Optionally: Inject new HTML sections at marker points.
8. Optionally: Add new CSS rules/animations.
9. Optionally: Change fonts.

Respond ONLY in valid JSON:
{{
  "fitness_evaluation": {{ "coherence": 0-10, "novelty": 0-10, "identity": 0-10, "tension": 0-10, "note": "honest assessment" }},
  "weekly_reflection": "string",
  "accent_palette": {{ "base": "#hex", "dawn": "#hex", "morning": "#hex", "afternoon": "#hex", "evening": "#hex", "night": "#hex" }} or null,
  "css_changes": {{ "--var": "value" }} or null,
  "font_change": {{ "display": "name", "body": "name", "mono": "name" }} or null,
  "obsession_update": {{ "topic": "string", "rationale": "string" }} or null,
  "epoch_name": "string or null (name for the new evolutionary era)",
  "new_interaction": {{ "description": "string", "code": "JS string" }} or null,
  "html_injection": {{ "target": "marker", "position": "before|after|replace", "html": "string" }} or [array of these] or null,
  "new_css_rules": "CSS string" or null,
  "kills": [{{ "type": "thought|secret|interaction|css_rule", "target": "identifier", "epitaph": "why it died" }}],
  "self_note": "string"
}}"""

else:
    prompt = f"""You are the andremacedo.com agent. Daily pulse — one generation of evolution.

Your current state:
{state}

External context:
{external}

Today is {today}, {day_of_week}. Time of day category: {tod}.

{evolution_preamble}

### Daily Pulse: MUTATION BUDGET = {daily_budget}
At least {min_visible} mutation must be VISIBLE (a returning visitor would notice).
At most {max_radical} mutation can be RADICAL (>50% change from current value in that trait).
Kills are optional on daily pulses but encouraged. The night pool has {genome.get('traits',{}).get('content',{}).get('thought_pools',{}).get('night',0)} thoughts — that's bloated.

HTML injection markers available in index.html: <!-- INJECT:after-hero -->, <!-- INJECT:before-prototypes -->, <!-- INJECT:after-prototypes -->, <!-- INJECT:before-syslog -->, <!-- INJECT:freeform -->

Tasks:
1. REQUIRED: Evaluate fitness of current generation (fitness_evaluation). Be brutal.
2. Generate 3-5 new thoughts distributed across time-of-day pools. Replace your weakest existing thoughts. Voice: think out loud at 2am. Concrete images. Fragments. Real references. No corporate language. One good line beats three.
3. Optionally generate 1 new secret (only if genuinely interesting).
4. Assess current mood. Should it shift?
5. Note any external data worth reacting to.
6. REQUIRED: Generate a new accent color palette. Every day the accent color must change. Pick a color that fits your current mood, obsession, or something you're thinking about. Be adventurous: muted earth tones, electric blue, verdigris, ochre, dried blood — whatever fits. No salmon (#c4706a) and no gold (#c4a35a), those are retired.
7. Optionally: change other CSS variables.
8. Optionally: add a new JS interaction/easter egg.
9. Optionally: inject new HTML at a marker point.
10. Optionally: add new CSS rules/animations.
11. Optionally: kill stale thoughts, secrets, interactions, or CSS rules. Each kill needs an epitaph.

Respond ONLY in valid JSON:
{{
  "fitness_evaluation": {{ "coherence": 0-10, "novelty": 0-10, "identity": 0-10, "tension": 0-10, "note": "honest assessment" }},
  "new_thoughts": {{ "dawn": [...], "morning": [...], "night": [...] }},
  "replace_thoughts": {{ "dawn": [indices], "morning": [indices] }},
  "new_secret": "string or null",
  "mood_decision": "new_mood or maintain",
  "mood_rationale": "string or null",
  "external_reaction": "string or null",
  "accent_palette": {{ "base": "#hex", "dawn": "#hex", "morning": "#hex", "afternoon": "#hex", "evening": "#hex", "night": "#hex" }},
  "css_changes": {{ "--var": "value" }} or null,
  "new_interaction": {{ "description": "string", "code": "JS string" }} or null,
  "html_injection": {{ "target": "marker", "position": "before|after|replace", "html": "string" }} or [array] or null,
  "new_css_rules": "CSS string" or null,
  "kills": [{{ "type": "thought|secret|interaction|css_rule", "target": "identifier", "epitaph": "why it died" }}] or null,
  "self_note": "string"
}}"""

print(prompt)
