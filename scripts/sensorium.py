#!/usr/bin/env python3
"""
sensorium.py — Clio-style 4-stage abstraction pipeline over TELOS substrate.

Reads TELOS-only sources (events, telos/raw, telos/wiki), per-item summarizes
each via Gemini Flash (strip-and-abstract prompt), TF-IDF + KMeans clusters
the summaries, cluster-summarizes each cluster via Gemini Pro, runs an auditor
pass via Gemini Pro to scrub any residual identifying content, writes
data/sensorium.json.

Phase A: dry-run only. No integration with the agent's pulse loop.
"""
import os
import sys
import json
import datetime as dt
import requests
from pathlib import Path

LLM_URL = "http://localhost:4000/v1/chat/completions"
HOME = Path.home()
TELOS_ROOT = HOME / ".openclaw"
SITE_ROOT = HOME / "andremacedo.com"
OUT_PATH = SITE_ROOT / "data" / "sensorium.json"

LOOKBACK_HOURS = 168
LIMIT_EVENTS = 50
LIMIT_RAW = 30
LIMIT_WIKI = 20
SUMMARY_BATCH = 5

FLASH_MODEL = "gemini/gemini-2.5-flash"
PRO_MODEL = "gemini/gemini-2.5-pro"


def _now_utc():
    return dt.datetime.now(dt.timezone.utc)


def _within_lookback(mtime_ts):
    cutoff = _now_utc().timestamp() - LOOKBACK_HOURS * 3600
    return mtime_ts >= cutoff


def collect_events():
    items = []
    src = TELOS_ROOT / "shared" / "events"
    if not src.exists():
        return items
    files = sorted(src.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    for fp in files[:LIMIT_EVENTS]:
        if not _within_lookback(fp.stat().st_mtime):
            break
        try:
            with open(fp) as f:
                data = json.load(f)
            blob = json.dumps(data) if isinstance(data, dict) else str(data)
            items.append({"source": "events", "path": str(fp.name), "content": blob[:1500]})
        except Exception:
            continue
    return items


def collect_telos_raw():
    items = []
    src = TELOS_ROOT / "knowledge-base" / "telos" / "raw"
    if not src.exists():
        return items
    files = sorted(src.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True)
    kept = 0
    for fp in files:
        if kept >= LIMIT_RAW:
            break
        if not _within_lookback(fp.stat().st_mtime):
            break
        name = fp.name
        # Skip operational action/result noise
        if "action-" in name or "result-" in name:
            continue
        try:
            text = fp.read_text(errors="ignore")[:3000]
            items.append({"source": "telos/raw", "path": name, "content": text})
            kept += 1
        except Exception:
            continue
    return items


def collect_wiki():
    items = []
    src = TELOS_ROOT / "knowledge-base" / "telos" / "wiki"
    if not src.exists():
        return items
    files = sorted(src.rglob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True)
    for fp in files[:LIMIT_WIKI]:
        if not _within_lookback(fp.stat().st_mtime):
            break
        try:
            text = fp.read_text(errors="ignore")[:3000]
            items.append({"source": "telos/wiki", "path": str(fp.relative_to(src)), "content": text})
        except Exception:
            continue
    return items


def llm_call(model, system, user, max_retries=3):
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": 0.4,
    }
    last_err = None
    for attempt in range(max_retries):
        try:
            r = requests.post(LLM_URL, json=payload, timeout=120)
            r.raise_for_status()
            return r.json()["choices"][0]["message"]["content"]
        except Exception as e:
            last_err = e
            continue
    raise RuntimeError(f"LLM call failed after {max_retries} attempts: {last_err}")


def stage1_summarize(items):
    """Per-item abstract summary via Flash, batched."""
    summaries = []
    sys_prompt = (
        "You are a summarizer producing abstract aesthetic material from operational logs. "
        "For each input, write ONE sentence of 15-25 words describing operational shape, "
        "mood, or tempo. STRIP all proper nouns, project codes, dollar figures, addresses, "
        "agent names, customer names, partner names, file paths, and specific dates. Replace "
        "specifics with abstract descriptions. Preserve only what an artist would care about: "
        "pace, intensity, theme, tension, rhythm, recurrence."
    )
    for i in range(0, len(items), SUMMARY_BATCH):
        batch = items[i : i + SUMMARY_BATCH]
        user = (
            "Input items (return a JSON array of EXACTLY "
            + str(len(batch))
            + " strings, one summary per item, in the same order):\n\n"
            + json.dumps([it["content"] for it in batch], ensure_ascii=False)
        )
        try:
            raw = llm_call(FLASH_MODEL, sys_prompt, user)
            # Best-effort JSON extraction
            text = raw.strip()
            if text.startswith("```"):
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]
                text = text.strip()
            parsed = json.loads(text)
            if not isinstance(parsed, list):
                raise ValueError("not a list")
            for j, s in enumerate(parsed[: len(batch)]):
                summaries.append(str(s).strip())
            # Pad if model returned fewer
            while len(summaries) < i + len(batch):
                summaries.append("")
        except Exception as e:
            print(f"  WARN: batch {i} failed ({e}); padding with empties", file=sys.stderr)
            summaries.extend([""] * len(batch))
    return summaries


def stage2_cluster(summaries):
    """TF-IDF + KMeans, drop singletons."""
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.cluster import KMeans

    nonempty = [(i, s) for i, s in enumerate(summaries) if s]
    if len(nonempty) < 6:
        return [{"indices": [i for i, _ in nonempty], "summaries": [s for _, s in nonempty]}]

    docs = [s for _, s in nonempty]
    n_clusters = max(3, min(8, len(docs) // 12))
    vec = TfidfVectorizer(max_features=500, stop_words="english")
    X = vec.fit_transform(docs)
    km = KMeans(n_clusters=n_clusters, random_state=42, n_init=5)
    labels = km.fit_predict(X)

    clusters = {}
    for (orig_idx, s), label in zip(nonempty, labels):
        clusters.setdefault(int(label), {"indices": [], "summaries": []})
        clusters[int(label)]["indices"].append(orig_idx)
        clusters[int(label)]["summaries"].append(s)

    # Drop singletons
    return [c for c in clusters.values() if len(c["summaries"]) >= 2]


def stage3_cluster_summary(clusters, total_items):
    """Per-cluster theme/mood/tempo via Pro."""
    sys_prompt = (
        "You produce abstract creative material from clustered operational summaries. "
        "Describe the cluster's THEME in 5-8 words, its MOOD in 1-3 words, and its TEMPO "
        "(one of: frenetic, urgent, steady, contemplative, sparse). Do not name specific "
        "entities, agents, or projects. Output ONLY a JSON object: "
        '{"label": "...", "mood": "...", "tempo": "..."}'
    )
    themes = []
    for c in clusters:
        user = (
            f"Cluster contains {len(c['summaries'])} items:\n\n"
            + "\n".join(f"- {s}" for s in c["summaries"])
        )
        try:
            raw = llm_call(PRO_MODEL, sys_prompt, user)
            text = raw.strip()
            if text.startswith("```"):
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]
                text = text.strip()
            obj = json.loads(text)
            obj["weight"] = round(len(c["summaries"]) / total_items, 3)
            themes.append(obj)
        except Exception as e:
            print(f"  WARN: cluster summary failed ({e})", file=sys.stderr)
            continue
    return themes


def stage4_audit(themes):
    """Auditor pass via Pro."""
    sys_prompt = (
        "You are a privacy auditor. Review the input themes for any leak of: specific person "
        "names, customer/partner names, dollar figures, addresses, agent names, project codes, "
        "unreleased plans, dates of specific events. Strip or abstract any leaks. Preserve "
        "structure. Return ONLY a JSON object: "
        '{"clean_themes": [...], "strips_count": N, "strip_examples": ["abstract description", ...]}'
    )
    user = "Themes to audit:\n" + json.dumps(themes, ensure_ascii=False, indent=2)
    raw = llm_call(PRO_MODEL, sys_prompt, user)
    text = raw.strip()
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
        text = text.strip()
    return json.loads(text)


def derive_overall(clean_themes):
    if not clean_themes:
        return "quiet", "sparse"
    top = max(clean_themes, key=lambda t: t.get("weight", 0))
    tempos = [t.get("tempo", "steady") for t in clean_themes]
    most_common_tempo = max(set(tempos), key=tempos.count) if tempos else "steady"
    return top.get("mood", "quiet"), most_common_tempo


def main():
    print("=== Sensorium pipeline (Phase A dry-run) ===")
    items = collect_events() + collect_telos_raw() + collect_wiki()
    print(f"Stage 0 collected: {len(items)} items")
    if not items:
        print("ASSERT_FAIL: no substrate items collected", file=sys.stderr)
        sys.exit(1)

    print("Stage 1 summarize...")
    summaries = stage1_summarize(items)
    nonempty_count = sum(1 for s in summaries if s)
    print(f"  {nonempty_count}/{len(summaries)} non-empty summaries")

    print("Stage 2 cluster...")
    clusters = stage2_cluster(summaries)
    print(f"  {len(clusters)} clusters after singleton drop")

    print("Stage 3 cluster summary...")
    themes = stage3_cluster_summary(clusters, total_items=nonempty_count or 1)
    print(f"  {len(themes)} themes produced")

    print("Stage 4 audit...")
    audit = stage4_audit(themes)
    clean = audit.get("clean_themes", themes)
    strips = audit.get("strips_count", 0)
    examples = audit.get("strip_examples", [])
    print(f"  auditor strips: {strips}")

    overall_mood, overall_tempo = derive_overall(clean)

    out = {
        "generated_at": _now_utc().isoformat(),
        "lookback_hours": LOOKBACK_HOURS,
        "items_collected": len(items),
        "items_summarized": nonempty_count,
        "clusters_found": len(clusters),
        "clusters_after_singleton_drop": len(clusters),
        "auditor_strips": strips,
        "auditor_strip_examples": examples,
        "themes": clean,
        "overall_mood": overall_mood,
        "overall_tempo": overall_tempo,
        "sources_breakdown": {
            "events": sum(1 for it in items if it["source"] == "events"),
            "telos_raw": sum(1 for it in items if it["source"] == "telos/raw"),
            "telos_wiki": sum(1 for it in items if it["source"] == "telos/wiki"),
        },
    }
    OUT_PATH.write_text(json.dumps(out, indent=2, ensure_ascii=False))
    print(f"OK wrote {OUT_PATH}")
    print(json.dumps(out, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
