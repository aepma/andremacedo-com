#!/usr/bin/env python3
"""epoch_review.py — the outside evidence an epoch is judged on, and the machinery
that forces a verdict on it at a monthly cadence.

Why this exists: epoch death was discretionary and self-graded. record-generation.py
transitioned an epoch only when the agent volunteered an obsession_update with a
different topic, and the only stagnation signal in the prompt was the agent's OWN
fitness score — which he held at 8.2-8.7 through gens 225-237 while the two
independent craft critics went flat near 7.5/8.0 and then printed 7.3/7.0 at gen
237. The outside signal existed and nobody read it: it lived in a log line.

Three jobs, all consumed elsewhere:
  1. state/craft-history.jsonl — the append-only craft-judge series. runner.sh
     appends one line per agentic generation, in BOTH outcomes.
  2. the plateau detector — reads that series, EXCLUDING "unobtainable" entries.
     On 2026-07-26 and 2026-07-29 the judge could not reach its local proxy (401)
     and returned nothing. A dark judge must never be readable as a flat score
     series, because the backstop would then kill a healthy epoch.
  3. state/epoch-review-log.jsonl — every monthly verdict, so consecutive "deepen"
     deferrals are countable and the mechanical backstop can fire.

CLI (used by runner.sh and by verification):
  epoch_review.py append-craft --history P --craft-json P --gen N [--judge-exit E]
  epoch_review.py plateau --history P [--since YYYY-MM-DD] [--window N] [--threshold F]
"""
import argparse, json, os, sys
from datetime import datetime, date, timezone

# ── Constants: the cadence the epoch is judged on ────────────────────
EPOCH_REVIEW_AGE_DAYS = 28      # a live epoch older than this is on trial every weekly
EPOCH_BACKSTOP_AGE_DAYS = 45    # ...and is cleared mechanically past this
PLATEAU_WINDOW = 4              # scored entries the flatness test looks at
PLATEAU_SPREAD = 0.5            # max(min_overall) - min(min_overall) below this = flat
DEEPEN_STREAK_LIMIT = 4         # consecutive "deepen" verdicts the backstop tolerates
LEDGER_STALE_HOURS = 72         # TELOS activity feed older than this is reported as dark

CRAFT_HISTORY = "craft-history.jsonl"
REVIEW_LOG = "epoch-review-log.jsonl"


# ── paths / io ───────────────────────────────────────────────────────
def craft_history_path(state_dir):
    return os.path.join(state_dir, CRAFT_HISTORY)


def review_log_path(state_dir):
    return os.path.join(state_dir, REVIEW_LOG)


def load_jsonl(path):
    """Read an append-only jsonl file, dropping unparseable lines rather than dying."""
    out = []
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except ValueError:
                    continue
                if isinstance(obj, dict):
                    out.append(obj)
    except FileNotFoundError:
        return []
    except OSError:
        return []
    return out


def append_jsonl(path, obj):
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False) + "\n")


def utcnow_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ── dates ────────────────────────────────────────────────────────────
def parse_day(value):
    """Accept 'YYYY-MM-DD' or a full ISO timestamp; return a date or None."""
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    try:
        return datetime.strptime(text[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def epoch_age_days(started, today=None):
    """Age in days of an epoch that began on `started`. None if unparseable."""
    start = parse_day(started)
    if start is None:
        return None
    ref = parse_day(today) or datetime.now(timezone.utc).date()
    return (ref - start).days


# ── the craft series ─────────────────────────────────────────────────
def is_scored(entry):
    return (entry.get("status") == "scored"
            and isinstance(entry.get("min_overall"), (int, float)))


def scored_entries(history):
    return [e for e in history if is_scored(e)]


def entries_since(history, since):
    """Filter to entries at or after a day (epoch start). No filter when since is None."""
    day = parse_day(since)
    if day is None:
        return list(history)
    out = []
    for e in history:
        stamp = parse_day(e.get("timestamp"))
        if stamp is None or stamp >= day:
            out.append(e)
    return out


def plateau(history, since=None, window=PLATEAU_WINDOW, threshold=PLATEAU_SPREAD):
    """Is the OUTSIDE craft signal flat over the last `window` SCORED generations?

    Unobtainable entries are excluded outright: a judge that could not run carries
    no evidence either way, and counting it as a repeat score would read a proxy
    outage as calcification.
    """
    considered = entries_since(history, since)
    scored = scored_entries(considered)
    excluded = len(considered) - len(scored)
    used = scored[-window:]
    values = [float(e["min_overall"]) for e in used]
    result = {
        "window": window,
        "threshold": threshold,
        "since": parse_day(since).isoformat() if parse_day(since) else None,
        "scored_available": len(scored),
        "excluded_unobtainable": excluded,
        "series": [{"gen": e.get("gen"), "min_overall": e.get("min_overall")} for e in used],
        "spread": None,
        "flat": False,
        "verdict": "INSUFFICIENT_DATA",
    }
    if len(values) < window:
        return result
    spread = round(max(values) - min(values), 3)
    result["spread"] = spread
    result["flat"] = spread < threshold
    result["verdict"] = "PLATEAU" if result["flat"] else "NOT_FLAT"
    return result


def craft_entry_from_judge(craft_json_path, gen, judge_exit=None):
    """One craft-history line from a craft-judge run. Never raises.

    status is "scored" only when BOTH critics returned a numeric overall; anything
    else (missing file, unparseable json, a critic unobtainable, timeout) is
    "unobtainable" and carries no scores.
    """
    entry = {
        "gen": int(gen) if str(gen).strip().lstrip("-").isdigit() else gen,
        "timestamp": utcnow_iso(),
        "critic_a": None,
        "critic_b": None,
        "min_overall": None,
        "status": "unobtainable",
    }
    if judge_exit is not None:
        entry["judge_exit"] = judge_exit
    data = None
    try:
        with open(craft_json_path, encoding="utf-8") as f:
            data = json.load(f)
    except Exception as exc:  # missing / truncated / not json
        entry["note"] = f"craft judge output unreadable: {type(exc).__name__}"
        return entry
    critics = (data or {}).get("critics") or {}
    a = (critics.get("A") or {}).get("overall")
    b = (critics.get("B") or {}).get("overall")
    if isinstance(a, (int, float)):
        entry["critic_a"] = float(a)
    if isinstance(b, (int, float)):
        entry["critic_b"] = float(b)
    if entry["critic_a"] is not None and entry["critic_b"] is not None:
        entry["min_overall"] = min(entry["critic_a"], entry["critic_b"])
        entry["status"] = "scored"
    else:
        missing = [k for k, v in (("A", entry["critic_a"]), ("B", entry["critic_b"])) if v is None]
        reason = (data or {}).get("reason") or (data or {}).get("error") or ""
        entry["note"] = (f"critic {'/'.join(missing)} returned no score"
                         + (f"; judge reason: {reason}" if reason else ""))
    verdict = (data or {}).get("verdict")
    if verdict:
        entry["judge_verdict"] = verdict
    return entry


def latest_findings(craft_json_path, per_critic=3):
    """The critics' most recent named findings — the concrete half of the evidence."""
    try:
        with open(craft_json_path, encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return []
    out = []
    for key in ("A", "B"):
        critic = ((data or {}).get("critics") or {}).get(key) or {}
        for finding in (critic.get("findings") or [])[:per_critic]:
            out.append(f"critic {key}: {str(finding)[:180]}")
    return out


# ── the verdict log ──────────────────────────────────────────────────
def parse_review(review):
    """(verdict, reasoning) from a meta epoch_review, or (None, why-it-is-invalid)."""
    if not isinstance(review, dict):
        return None, "epoch_review is missing or is not an object"
    verdict = review.get("verdict")
    if not isinstance(verdict, str):
        return None, "epoch_review.verdict is missing or not a string"
    verdict = verdict.strip().lower()
    if verdict not in ("deepen", "metamorphose"):
        return None, f"epoch_review.verdict must be 'deepen' or 'metamorphose', got {verdict!r}"
    reasoning = review.get("reasoning") or review.get("reason") or ""
    if not isinstance(reasoning, str) or len(reasoning.strip()) < 40:
        return None, "epoch_review.reasoning is missing or too thin to cite the evidence"
    return verdict, reasoning.strip()


def deepen_streak(state_dir, epoch_number=None):
    """Consecutive trailing 'deepen' verdicts for this epoch (deferrals in a row)."""
    log = load_jsonl(review_log_path(state_dir))
    if epoch_number is not None:
        log = [e for e in log if e.get("epoch_number") == epoch_number]
    streak = 0
    for entry in reversed(log):
        if entry.get("verdict") == "deepen":
            streak += 1
        else:
            break
    return streak


def record_review(state_dir, entry):
    entry.setdefault("timestamp", utcnow_iso())
    append_jsonl(review_log_path(state_dir), entry)
    return entry


# ── CLI ──────────────────────────────────────────────────────────────
def _cmd_append_craft(args):
    entry = craft_entry_from_judge(args.craft_json, args.gen, args.judge_exit)
    append_jsonl(args.history, entry)
    print(json.dumps(entry, ensure_ascii=False))
    return 0


def _cmd_plateau(args):
    history = load_jsonl(args.history)
    result = plateau(history, since=args.since, window=args.window, threshold=args.threshold)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="cmd", required=True)

    ap = sub.add_parser("append-craft", help="append one craft-judge result to the series")
    ap.add_argument("--history", required=True)
    ap.add_argument("--craft-json", required=True)
    ap.add_argument("--gen", required=True)
    ap.add_argument("--judge-exit", default=None)
    ap.set_defaults(func=_cmd_append_craft)

    pp = sub.add_parser("plateau", help="run the plateau detector over a craft series")
    pp.add_argument("--history", required=True)
    pp.add_argument("--since", default=None, help="epoch start day; entries before it are ignored")
    pp.add_argument("--window", type=int, default=PLATEAU_WINDOW)
    pp.add_argument("--threshold", type=float, default=PLATEAU_SPREAD)
    pp.set_defaults(func=_cmd_plateau)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
