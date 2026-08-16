#!/usr/bin/env python3
"""record-generation.py — genome lineage bookkeeping for regenerate-from-intent.

Direction C retires the old mutation engine (the ~1400-line string-replacement
machinery): the agent now writes a COMPLETE index.html directly. But the genome
LINEAGE that engine also maintained — generation count, fitness_log,
color_history, epoch transitions, graveyard, mood — must survive, because
build_prompt.format_genome_summary and the runner's portfolio rebuild read it,
and the coherence teeth depend on it.

This step reads the agent's generation METADATA json (the record fields only:
fitness, palette, epoch, mood, kills, summary — never apply-this-diff fields) and
updates state/genome.json + state/agent-state.json to MATCH the existing schema.
It touches index.html ONLY to stamp the hidden version chip. It is not a mutation
engine and has no contract with index.html content.

Usage: record-generation.py <metadata.json> <daily|weekly|event> <site_dir>
Prints a one-line summary (used as the commit subject). Exit 0 on success.
"""
import json, os, re, sys, colorsys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import epoch_review as er


def load(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def hue_family(base_hex):
    """Map an accent base hex to a coarse hue family (preserves the prior mapping)."""
    try:
        r = int(base_hex[1:3], 16) / 255
        g = int(base_hex[3:5], 16) / 255
        b = int(base_hex[5:7], 16) / 255
    except Exception:
        return None
    h, _, _ = colorsys.rgb_to_hsv(r, g, b)
    hue = int(h * 360)
    for threshold, name in [(30, "red"), (60, "orange"), (90, "amber"), (120, "yellow"),
                            (150, "lime"), (180, "green"), (210, "teal"), (240, "cyan"),
                            (270, "blue"), (300, "indigo"), (330, "violet"), (360, "magenta")]:
        if hue <= threshold:
            return name
    return "red"


def bury_epoch(genome, state, epoch_num, topic, started, epitaph, gen, now, today,
               mechanical_reason=None):
    """Kill the live epoch and leave a clearing behind it.

    Mirrors the obsession-swap burial (past_epochs + graveyard + epoch_number++)
    but does NOT mint a successor: the clearing is the point — the next weekly
    enters build_obsession_directive's clearing branch and the agent authors his
    own next obsession there. genome["epoch"]/["epoch_started"] are deliberately
    left alone, exactly as the 2026-08-16 hand-clearing left them; the next
    obsession birth sets both.
    """
    dead = {"number": epoch_num, "obsession": topic,
            "started": started or genome.get("epoch_started", "unknown"),
            "ended": now, "epitaph": epitaph}
    if mechanical_reason:
        dead["transition"] = "mechanical"
        dead["transition_reason"] = mechanical_reason
    else:
        dead["transition"] = "authored"
    genome.setdefault("past_epochs", []).append(dead)
    genome.setdefault("graveyard", []).append(
        {"type": "epoch", "value": f"Epoch {epoch_num}: {topic}",
         "died_gen": gen, "epitaph": epitaph})
    genome["epoch_number"] = epoch_num + 1
    state["active_obsession"] = {"topic": "", "started": today, "rationale": ""}
    return dead


def main():
    if len(sys.argv) < 4:
        print("usage: record-generation.py <metadata.json> <daily|weekly|event> <site_dir>", file=sys.stderr)
        sys.exit(2)
    meta_path, pulse_type, site_dir = sys.argv[1], sys.argv[2], sys.argv[3]

    meta = load(meta_path, None)
    if not isinstance(meta, dict):
        print(f"record-generation: metadata missing/invalid at {meta_path}", file=sys.stderr)
        sys.exit(1)

    genome_path = os.path.join(site_dir, "state", "genome.json")
    state_path = os.path.join(site_dir, "state", "agent-state.json")
    index_path = os.path.join(site_dir, "index.html")
    changelog_path = os.path.join(site_dir, "state", "changelog.md")

    genome = load(genome_path, {})
    state = load(state_path, {})
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    parts = []

    # ── version / generation increment ────────────────────────────────
    state["version"] = state.get("version", 0) + 1
    new_version = state["version"]
    genome["generation"] = new_version

    # stamp the hidden version chip into the regenerated page (best-effort)
    try:
        html = open(index_path, encoding="utf-8").read()
        if re.search(r'id="siteVersion"', html):
            html = re.sub(r'id="siteVersion"[^>]*>[^<]*<',
                          f'id="siteVersion" style="display:none">v{new_version}<', html)
            open(index_path, "w", encoding="utf-8").write(html)
    except Exception:
        html = ""

    # ── mood (all pulses) ─────────────────────────────────────────────
    mood = meta.get("mood") or meta.get("mood_decision")
    if mood and isinstance(mood, str) and mood not in ("maintain", "null"):
        state["current_mood"] = mood
        parts.append(f"mood: {mood}")

    genome.setdefault("graveyard", [])

    # ── Epoch review: the monthly pivot decision ──────────────────────
    # A live epoch past EPOCH_REVIEW_AGE_DAYS is on trial at every weekly pulse.
    # The verdict is the agent's — except when the backstop fires, because an epoch
    # that can only be ended by its own author's permission never ends. Runs before
    # any state is mutated: a rejection here leaves both files untouched.
    state_dir = os.path.join(site_dir, "state")
    obs_live = state.get("active_obsession", {}) or {}
    live_topic = (obs_live.get("topic") or "").strip()
    live_started = obs_live.get("started", "")
    live_age = er.epoch_age_days(live_started, today)
    epoch_num = genome.get("epoch_number", 1)
    review_due = (pulse_type == "weekly" and bool(live_topic)
                  and live_age is not None and live_age >= er.EPOCH_REVIEW_AGE_DAYS)
    cleared_this_pulse = False

    if review_due:
        verdict, reasoning = er.parse_review(meta.get("epoch_review"))
        if verdict is None:
            print(f"record-generation: an epoch review was REQUIRED this pulse (epoch "
                  f"{epoch_num} is {live_age} days old) but {reasoning}. Rejecting the "
                  "generation.", file=sys.stderr)
            sys.exit(1)

        history = er.load_jsonl(er.craft_history_path(state_dir))
        pl = er.plateau(history, since=live_started)
        streak = er.deepen_streak(state_dir, epoch_num) + (1 if verdict == "deepen" else 0)
        mechanical = None
        if live_age > er.EPOCH_BACKSTOP_AGE_DAYS:
            mechanical = (f"epoch age {live_age}d exceeded the "
                          f"{er.EPOCH_BACKSTOP_AGE_DAYS}-day ceiling")
        elif verdict == "deepen" and streak >= er.DEEPEN_STREAK_LIMIT and pl["flat"]:
            mechanical = (f"{streak} consecutive 'deepen' verdicts against a flat craft series "
                          f"(spread {pl['spread']} across the last {pl['window']} scored "
                          "generations)")

        if mechanical or verdict == "metamorphose":
            if mechanical:
                epitaph = (f"Epoch {epoch_num}, \"{live_topic}\", ran {live_started} to {today} "
                           f"({live_age} days). It was not ended by a decision: the backstop "
                           f"cleared it because {mechanical}. No authored eulogy exists for this "
                           "epoch — it outlived the point at which one was owed.")
            else:
                # Provenance fix: the epitaph is the dying epoch's own, never the
                # successor's rationale. Falls back to a neutral generated line.
                epitaph = (str(meta.get("epoch_epitaph") or "").strip()
                           or reasoning
                           or f"Epoch {epoch_num}, \"{live_topic}\", ran {live_started} to "
                              f"{today} ({live_age} days). No epitaph was written.")
            bury_epoch(genome, state, epoch_num, live_topic, live_started, epitaph,
                       new_version, now, today, mechanical_reason=mechanical)
            cleared_this_pulse = True
            kind = "mechanical" if mechanical else "authored"
            parts.append(f"epoch review: Epoch {epoch_num} buried ({kind}), clearing opens")
            try:
                with open(os.path.join(state_dir, "epoch-transition-latest.json"), "w",
                          encoding="utf-8") as f:
                    json.dump({"gen": new_version, "date": today, "epoch_number": epoch_num,
                               "topic": live_topic, "kind": kind, "age_days": live_age,
                               "reason": mechanical or "authored metamorphose verdict",
                               "craft_plateau": pl}, f, indent=2, ensure_ascii=False)
            except OSError:
                pass
        else:
            parts.append(f"epoch review: deepen (deferral {streak}/{er.DEEPEN_STREAK_LIMIT})")

        er.record_review(state_dir, {
            "gen": new_version, "date": today, "epoch_number": epoch_num,
            "epoch_topic": live_topic, "age_days": live_age,
            "verdict": "mechanical_clear" if mechanical else verdict,
            "agent_verdict": verdict,
            "deepen_streak": streak if verdict == "deepen" else 0,
            "craft_spread": pl.get("spread"), "craft_flat": pl.get("flat"),
            "reasoning": reasoning[:600],
        })

    # ── obsession birth/transition (preserves the prior epoch semantics) ───
    obsession = meta.get("obsession_update")
    if cleared_this_pulse and isinstance(obsession, dict) and (obsession.get("topic") or "").strip():
        # A clearing is not a swap: the successor is authored NEXT weekly, from the
        # clearing, with the whole lineage in front of him. Never in the same breath.
        print(f"  [epoch] obsession_update {obsession['topic']!r} ignored — the epoch was "
              "cleared this pulse and the clearing is the point", file=sys.stderr)
        obsession = None
    if isinstance(obsession, dict) and (obsession.get("topic") or "").strip():
        old = state.get("active_obsession", {})
        old_topic = (old.get("topic") or "").strip()
        new_topic = obsession["topic"].strip()
        is_swap = bool(old_topic) and old_topic != new_topic
        if old_topic == new_topic:
            pass
        elif is_swap and pulse_type != "weekly":
            print(f"  [obsession] swap {old_topic!r}->{new_topic!r} deferred (weekly-only)", file=sys.stderr)
        else:
            if is_swap:
                epoch_num = genome.get("epoch_number", 1)
                # The epitaph is the DYING epoch's eulogy. Until 2026-08-16 this line
                # took the INCOMING obsession's rationale, so every entry in
                # past_epochs was the successor's birth statement (epoch 8's stored
                # epitaph is verbatim the rationale for resonance) and the lineage the
                # agent mines was corrupt. Never fall back to the rationale.
                epitaph = str(meta.get("epoch_epitaph") or "").strip() or (
                    f"Epoch {epoch_num}, \"{old_topic}\", ran "
                    f"{old.get('started', genome.get('epoch_started', 'unknown'))} to {today}. "
                    "No epitaph was written for it.")
                dead = {"number": epoch_num, "obsession": old_topic,
                        "started": old.get("started", genome.get("epoch_started", "unknown")),
                        "ended": now, "epitaph": epitaph, "transition": "swap"}
                genome.setdefault("past_epochs", []).append(dead)
                genome["graveyard"].append({"type": "epoch", "value": f"Epoch {epoch_num}: {old_topic}",
                                            "died_gen": new_version, "epitaph": dead["epitaph"]})
                genome["epoch_number"] = epoch_num + 1
                genome["epoch_started"] = today
                parts.append(f"epoch transition: Epoch {epoch_num} died, Epoch {epoch_num + 1} begins")
            else:
                genome["epoch"] = new_topic
                genome["epoch_started"] = today
                parts.append(f"obsession born: {new_topic}")
            state["active_obsession"] = {"topic": new_topic, "started": today,
                                         "rationale": obsession.get("rationale", "")}

    # ── weekly manual epoch override + reflection ─────────────────────
    if pulse_type == "weekly":
        epoch_name = meta.get("epoch_name")
        if epoch_name and isinstance(epoch_name, str) and epoch_name not in ("null", ""):
            genome["epoch"] = epoch_name
            genome["epoch_started"] = today
            parts.append(f"epoch: {epoch_name}")
        if meta.get("weekly_reflection"):
            parts.append("reflection: " + str(meta["weekly_reflection"])[:120])
        state["last_weekly_deep"] = now

    # ── accent palette -> traits.color + color_history ────────────────
    traits = genome.setdefault("traits", {})
    palette = meta.get("accent_palette")
    if isinstance(palette, dict):
        color = traits.setdefault("color", {})
        color["accent_base"] = palette.get("base", color.get("accent_base"))
        for k in ("dawn", "morning", "afternoon", "evening", "night"):
            color[f"accent_{k}"] = palette.get(k, color.get(f"accent_{k}"))
        base_hex = palette.get("base", "")
        fam = hue_family(base_hex) if base_hex else None
        if fam:
            hist = genome.setdefault("color_history", [])
            hist.append({"gen": new_version, "base": base_hex, "family": fam})
            hist[:] = hist[-10:]
            parts.append(f"palette: {base_hex} ({fam})")

    # ── traits lineage from disk (sections/pages/svgs) ────────────────
    if html:
        secs = re.findall(r'<!-- @section:([^:]+):start -->', html)
        if secs:
            traits.setdefault("layout", {})["sections"] = secs
    pages = []
    for root, _dirs, files in os.walk(site_dir):
        if any(seg in root for seg in (os.sep + "node_modules", os.sep + ".git", os.sep + "archive-screenshots")):
            continue
        for f in files:
            if f.endswith(".html") and f != "index.html":
                pages.append(os.path.relpath(os.path.join(root, f), site_dir))
    traits.setdefault("layout", {})["pages"] = sorted(pages)
    assets_dir = os.path.join(site_dir, "assets")
    if os.path.isdir(assets_dir):
        traits.setdefault("layout", {})["svg_assets"] = sorted(f for f in os.listdir(assets_dir) if f.endswith(".svg"))
    content = traits.setdefault("content", {})
    content["mood"] = state.get("current_mood", content.get("mood"))
    content["obsession"] = state.get("active_obsession", {}).get("topic", content.get("obsession"))

    # ── fitness_log (drives coherence teeth + genome_summary) ─────────
    fit = meta.get("fitness_evaluation")
    if isinstance(fit, dict):
        scores = {"gen": new_version}
        for axis in ("coherence", "novelty", "identity", "tension", "awe", "perceptibility"):
            scores[axis] = fit.get(axis)
        scores["note"] = str(fit.get("note", ""))[:150]
        numeric = [v for k, v in scores.items() if k not in ("gen", "note") and isinstance(v, (int, float))]
        scores["total"] = round(sum(numeric) / len(numeric), 1) if numeric else None
        genome.setdefault("fitness_log", []).append(scores)
        genome["fitness_log"] = genome["fitness_log"][-20:]
        parts.append(f"fitness: {scores['total']}")

    # ── kills -> graveyard ────────────────────────────────────────────
    kills = meta.get("kills") if isinstance(meta.get("kills"), list) else []
    kills_recorded = []
    for k in kills:
        if isinstance(k, dict) and k.get("target"):
            genome["graveyard"].append({"type": k.get("type", "element"), "value": k.get("target"),
                                        "died_gen": new_version, "epitaph": k.get("epitaph", "")})
            kills_recorded.append(k.get("target"))

    # ── mutation_log: regenerate-from-intent records ONE regenerate event
    genome.setdefault("mutation_log", []).append({
        "gen": new_version, "mutations": ["regenerate"], "kills": kills_recorded,
        "strategy": str(meta.get("visual_strategy", ""))[:160], "timestamp": now})
    genome["mutation_log"] = genome["mutation_log"][-20:]
    genome["graveyard"] = genome["graveyard"][-50:]

    # ── self note (lineage) + timestamps ──────────────────────────────
    if meta.get("self_note"):
        state["last_self_note"] = str(meta["self_note"])[:300]
    if pulse_type == "daily":
        state["last_daily_pulse"] = now
    elif pulse_type == "event":
        state["last_event_pulse"] = now

    # ── write back ────────────────────────────────────────────────────
    with open(state_path, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)
    with open(genome_path, "w", encoding="utf-8") as f:
        json.dump(genome, f, indent=2, ensure_ascii=False)

    summary = (meta.get("summary") or "; ".join(parts) or f"regenerate gen {new_version}").strip()
    summary = summary.replace("\n", " ")[:300]
    try:
        with open(changelog_path, "a", encoding="utf-8") as f:
            f.write(f"\n## gen {new_version} ({pulse_type}, {today})\n{summary}\n")
    except Exception:
        pass
    print(summary)


if __name__ == "__main__":
    main()
