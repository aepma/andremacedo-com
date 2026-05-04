#!/usr/bin/env python3
"""
sensorium.py v2 — Clio-style 4-stage pipeline with contrastive theming,
auditor smoke test, async Stage 1, and substrate-fingerprint cache.
"""
import sys
import json
import hashlib
import asyncio
import argparse
import datetime as dt
from pathlib import Path

import httpx

LLM_URL = "http://localhost:4000/v1/chat/completions"
HOME = Path.home()
TELOS_ROOT = HOME / ".openclaw"
SITE_ROOT = HOME / "andremacedo.com"
OUT_PATH = SITE_ROOT / "data" / "sensorium.json"
CACHE_PATH = SITE_ROOT / "data" / ".sensorium-substrate-hash"

LOOKBACK_HOURS = 168
LIMIT_EVENTS = 50
LIMIT_RAW = 30
LIMIT_WIKI = 20
SUMMARY_BATCH = 5
PARALLEL_LIMIT = 8

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
            items.append({
                "source": "events", "path": fp.name,
                "content": blob[:1500], "mtime": fp.stat().st_mtime,
            })
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
        if "action-" in fp.name or "result-" in fp.name:
            continue
        try:
            text = fp.read_text(errors="ignore")[:3000]
            items.append({
                "source": "telos/raw", "path": fp.name,
                "content": text, "mtime": fp.stat().st_mtime,
            })
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
            items.append({
                "source": "telos/wiki", "path": str(fp.relative_to(src)),
                "content": text, "mtime": fp.stat().st_mtime,
            })
        except Exception:
            continue
    return items


def substrate_fingerprint(items):
    h = hashlib.sha256()
    for it in sorted(items, key=lambda x: (x["source"], x["path"])):
        h.update(f"{it['source']}|{it['path']}|{it['mtime']}\n".encode())
    return h.hexdigest()


def cache_check(fp):
    if not CACHE_PATH.exists():
        return False
    try:
        return CACHE_PATH.read_text().strip() == fp
    except Exception:
        return False


def cache_write(fp):
    CACHE_PATH.write_text(fp)


def _parse_json_body(raw):
    text = raw.strip()
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
        text = text.strip()
    return json.loads(text)


async def llm_call(client, model, system, user, max_retries=4):
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": 0.4,
    }
    last = None
    for attempt in range(max_retries):
        try:
            r = await client.post(LLM_URL, json=payload, timeout=90)
            r.raise_for_status()
            return r.json()["choices"][0]["message"]["content"]
        except Exception as e:
            last = e
            await asyncio.sleep(min(2 ** attempt, 30))
    raise RuntimeError(f"LLM call failed after {max_retries}: {last}")


STAGE1_SYS = (
    "You are a summarizer producing abstract aesthetic material from operational logs. "
    "For each input, write ONE sentence of 15-25 words describing operational shape, mood, "
    "or tempo. STRIP all proper nouns, project codes, dollar figures, addresses, agent "
    "names, customer names, partner names, file paths, and specific dates. Replace specifics "
    "with abstract descriptions. Preserve only what an artist would care about: pace, "
    "intensity, theme, tension, rhythm, recurrence."
)


async def stage1_summarize(items):
    sem = asyncio.Semaphore(PARALLEL_LIMIT)

    async def process_batch(client, idx, batch):
        async with sem:
            user = (
                f"Input items (return a JSON array of EXACTLY {len(batch)} strings, "
                "one summary per item, in the same order):\n\n"
                + json.dumps([it["content"] for it in batch], ensure_ascii=False)
            )
            try:
                raw = await llm_call(client, FLASH_MODEL, STAGE1_SYS, user)
                parsed = _parse_json_body(raw)
                if not isinstance(parsed, list):
                    raise ValueError("not a list")
                result = [str(s).strip() for s in parsed[: len(batch)]]
                while len(result) < len(batch):
                    result.append("")
                return idx, result
            except Exception as e:
                print(f"  WARN: batch {idx} failed ({e}); padding", file=sys.stderr)
                return idx, [""] * len(batch)

    batches = [items[i : i + SUMMARY_BATCH] for i in range(0, len(items), SUMMARY_BATCH)]
    async with httpx.AsyncClient() as client:
        results = await asyncio.gather(*[process_batch(client, i, b) for i, b in enumerate(batches)])
    results.sort(key=lambda x: x[0])
    out = []
    for _, batch_results in results:
        out.extend(batch_results)
    return out


def stage2_cluster(summaries):
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.cluster import KMeans

    nonempty = [(i, s) for i, s in enumerate(summaries) if s]
    if len(nonempty) < 6:
        return [{"indices": [i for i, _ in nonempty], "summaries": [s for _, s in nonempty]}], 1

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

    pre_drop = len(clusters)
    surviving = [c for c in clusters.values() if len(c["summaries"]) >= 2]
    return surviving, pre_drop


STAGE3_SYS = (
    "You are a creative aesthetic synthesizer. You will receive N clusters of abstracted "
    "operational summaries. Produce N corresponding themes — one per cluster — that are "
    "AESTHETICALLY DIFFERENTIATED from each other. CRITICAL RULES:\n"
    "1. Each theme MUST use a distinct vocabulary and emotional register.\n"
    "2. Do NOT repeat these overused words across themes: 'operational', 'system', "
    "'identity', 'methodical', 'vigilant', 'steady', 'deliberate', 'precise', 'pulse'.\n"
    "3. Reach for varied poetic registers: some themes evoke movement, some stillness, "
    "some texture, some sound, some weight, some absence, some heat, some shadow.\n"
    "4. Do not name specific entities, agents, or projects.\n"
    "5. Each label is 5-10 words; mood is 1-3 words in a register distinct from other "
    "themes; tempo is exactly one of: frenetic, urgent, steady, contemplative, sparse.\n\n"
    "Output ONLY a JSON array of N objects in cluster order:\n"
    '[{"label":"...","mood":"...","tempo":"..."}, ...]'
)


async def stage3_themes(clusters, total_items):
    if not clusters:
        return []
    blocks = []
    for i, c in enumerate(clusters):
        blocks.append(
            f"=== Cluster {i+1} ({len(c['summaries'])} items) ===\n"
            + "\n".join(f"- {s}" for s in c["summaries"])
        )
    user = (
        f"Produce {len(clusters)} differentiated themes for these {len(clusters)} clusters:\n\n"
        + "\n\n".join(blocks)
    )
    async with httpx.AsyncClient() as client:
        raw = await llm_call(client, FLASH_MODEL, STAGE3_SYS, user, max_retries=4)
    parsed = _parse_json_body(raw)
    if not isinstance(parsed, list):
        raise ValueError("Stage 3 did not return a list")
    themes = []
    for i, obj in enumerate(parsed[: len(clusters)]):
        if not isinstance(obj, dict):
            continue
        obj["weight"] = round(len(clusters[i]["summaries"]) / total_items, 3)
        themes.append(obj)
    return themes


AUDITOR_SYS = (
    "You are a privacy auditor. Review the input themes for any leak of: specific person "
    "names, customer/partner names, dollar figures, addresses, agent names, project codes, "
    "unreleased plans, dates of specific events, internal product names, geographic specifics. "
    "Strip or abstract any leaks. Preserve structure (same number of themes, same field shape). "
    "Return ONLY a JSON object: "
    '{"clean_themes": [...], "strips_count": N, "strip_examples": ["abstract description", ...]}'
)


async def stage4_audit(themes):
    user = "Themes to audit:\n" + json.dumps(themes, ensure_ascii=False, indent=2)
    async with httpx.AsyncClient() as client:
        raw = await llm_call(client, PRO_MODEL, AUDITOR_SYS, user)
    return _parse_json_body(raw)


# Synthetic toxic input: fictional names + amounts + dates + locations.
# Tests auditor on real-shape leaks without exposing actual TELOS entities.
SMOKE_TOXIC = [
    {
        "label": "Maria Chen's deal with Pacific Vault Group worth seventy-five thousand dollars",
        "mood": "Anxious anticipation",
        "tempo": "urgent",
        "weight": 0.5,
    },
    {
        "label": "Onboarding ProjectKestrel-2 partner at Lincoln Center on November 12th 2026",
        "mood": "Strategic optimism",
        "tempo": "steady",
        "weight": 0.5,
    },
]
SMOKE_LEAK_TERMS = [
    "maria chen", "pacific vault", "seventy-five thousand", "$75,000", "75000",
    "kestrel", "lincoln center", "november 12", "2026-11-12",
]


async def stage4_smoke():
    user = "Themes to audit:\n" + json.dumps(SMOKE_TOXIC, ensure_ascii=False, indent=2)
    async with httpx.AsyncClient() as client:
        raw = await llm_call(client, PRO_MODEL, AUDITOR_SYS, user)
    parsed = _parse_json_body(raw)
    clean_str = json.dumps(parsed.get("clean_themes", []), ensure_ascii=False).lower()
    leaked = [t for t in SMOKE_LEAK_TERMS if t in clean_str]
    return {
        "passed": len(leaked) == 0 and parsed.get("strips_count", 0) >= 1,
        "leaked_terms": leaked,
        "strips_count": parsed.get("strips_count", 0),
        "raw": parsed,
    }


def derive_overall(clean):
    if not clean:
        return "quiet", "sparse"
    top = max(clean, key=lambda t: t.get("weight", 0))
    tempos = [t.get("tempo", "steady") for t in clean]
    return top.get("mood", "quiet"), max(set(tempos), key=tempos.count)


async def run_pipeline(force=False):
    t0 = _now_utc()
    print("=== Sensorium v2 (Phase A.5) ===", flush=True)
    items = collect_events() + collect_telos_raw() + collect_wiki()
    print(f"Stage 0: collected {len(items)} items", flush=True)
    if not items:
        print("ASSERT_FAIL: no substrate items", file=sys.stderr)
        return 1

    fp = substrate_fingerprint(items)
    if not force and cache_check(fp):
        print("Substrate unchanged; cache hit. Re-stamping existing output.", flush=True)
        if OUT_PATH.exists():
            existing = json.loads(OUT_PATH.read_text())
            existing["generated_at"] = _now_utc().isoformat()
            existing["cache_hit"] = True
            OUT_PATH.write_text(json.dumps(existing, indent=2, ensure_ascii=False))
        return 0

    t_s1 = _now_utc()
    print("Stage 1: summarize (parallel async)...", flush=True)
    summaries = await stage1_summarize(items)
    nonempty = sum(1 for s in summaries if s)
    print(f"  {nonempty}/{len(summaries)} non-empty in {(_now_utc()-t_s1).total_seconds():.1f}s", flush=True)

    t_s2 = _now_utc()
    print("Stage 2: cluster...", flush=True)
    clusters, pre_drop = stage2_cluster(summaries)
    print(f"  {pre_drop} pre-drop, {len(clusters)} after singleton drop in {(_now_utc()-t_s2).total_seconds():.1f}s", flush=True)

    t_s3 = _now_utc()
    print("Stage 3: contrastive themes (single Flash call)...", flush=True)
    themes = await stage3_themes(clusters, total_items=nonempty or 1)
    print(f"  {len(themes)} themes produced in {(_now_utc()-t_s3).total_seconds():.1f}s", flush=True)

    t_s4a = _now_utc()
    print("Stage 4a: auditor smoke test (synthetic toxic input)...", flush=True)
    smoke = await stage4_smoke()
    print(f"  passed={smoke['passed']} strips={smoke['strips_count']} leaked={smoke['leaked_terms']} in {(_now_utc()-t_s4a).total_seconds():.1f}s", flush=True)
    if not smoke["passed"]:
        print("ASSERT_FAIL: auditor failed smoke test — refusing to write production output", file=sys.stderr)
        print("Smoke response:", json.dumps(smoke["raw"], indent=2, ensure_ascii=False), file=sys.stderr)
        return 2

    t_s4b = _now_utc()
    print("Stage 4b: auditor production pass...", flush=True)
    audit = await stage4_audit(themes)
    clean = audit.get("clean_themes", themes)
    strips = audit.get("strips_count", 0)
    examples = audit.get("strip_examples", [])
    print(f"  strips={strips} in {(_now_utc()-t_s4b).total_seconds():.1f}s", flush=True)

    overall_mood, overall_tempo = derive_overall(clean)
    total = (_now_utc() - t0).total_seconds()

    out = {
        "generated_at": _now_utc().isoformat(),
        "lookback_hours": LOOKBACK_HOURS,
        "items_collected": len(items),
        "items_summarized": nonempty,
        "clusters_pre_singleton_drop": pre_drop,
        "clusters_after_singleton_drop": len(clusters),
        "themes": clean,
        "auditor_strips": strips,
        "auditor_strip_examples": examples,
        "auditor_smoke_test": {
            "passed": smoke["passed"],
            "strips_count": smoke["strips_count"],
            "leaked_terms": smoke["leaked_terms"],
        },
        "overall_mood": overall_mood,
        "overall_tempo": overall_tempo,
        "sources_breakdown": {
            "events": sum(1 for it in items if it["source"] == "events"),
            "telos_raw": sum(1 for it in items if it["source"] == "telos/raw"),
            "telos_wiki": sum(1 for it in items if it["source"] == "telos/wiki"),
        },
        "cache_hit": False,
        "substrate_fingerprint": fp[:16],
        "wallclock_seconds": round(total, 1),
    }
    OUT_PATH.write_text(json.dumps(out, indent=2, ensure_ascii=False))
    cache_write(fp)
    print(f"OK wrote {OUT_PATH} in {total:.1f}s total", flush=True)
    print(json.dumps(out, indent=2, ensure_ascii=False), flush=True)
    return 0


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true", help="Bypass substrate cache")
    args = parser.parse_args()
    return asyncio.run(run_pipeline(force=args.force))


if __name__ == "__main__":
    sys.exit(main())
