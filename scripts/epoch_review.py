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


# ── the judge's exit code: the ONLY source of a craft verdict ────────
# craft-judge.py's own contract (see its module docstring): 0 = PASS,
# 1 = SLOP/below threshold, 2 = ERROR (a critic could not be obtained). Those
# three are the exits it produces itself, at its emit(), having just written its
# JSON. ANY other exit means it never got there: the wrapper killed it (124 from
# the timeout shim, 137/143 from a signal) or it crashed. Then the JSON sitting
# at --json-out is some EARLIER run's verdict, and reading scores out of it
# attributes another generation's craft to this one.
JUDGE_EXIT_VERDICT = {0: "PASS", 1: "SLOP", 2: "ERROR"}
JUDGE_KILLED_EXITS = frozenset((124, 137, 143))
CRAFT_STATUSES = ("scored", "unobtainable")
CORRECTION_RECORD = "correction"


def parse_exit(judge_exit):
    """The judge's exit code as an int, or None when absent or unusable.

    runner.sh passes it through the shell, so it arrives as a string. A value
    that is present but not an integer is a wiring defect; it reads as None and
    the caller fails closed on it, because an unreadable exit code is never
    evidence of a pass.
    """
    if judge_exit is None or isinstance(judge_exit, bool):
        return None
    if isinstance(judge_exit, int):
        return judge_exit
    text = str(judge_exit).strip()
    if not text:
        return None
    try:
        return int(text)
    except ValueError:
        return None


def judge_outcome(judge_exit):
    """(verdict, completed), derived ONLY from the judge's exit code.

    Never from the scores. On 2026-08-31 generation 240 was recorded as
    judge_verdict=PASS with two clean 8.0s while its judge_exit sat in the same
    record at 124: the run had been killed by the wrapper and the generation was
    reverted and never deployed. A non-zero exit is not a pass, and the craft
    series is the only measurement of design craft this system holds.

    completed=True means the judge reached its own emit() and therefore wrote
    the JSON this record describes. False means the JSON on disk belongs to an
    earlier run and its scores must not be attributed to this generation.
    """
    code = parse_exit(judge_exit)
    if code is None:
        return "UNKNOWN", False
    if code in JUDGE_EXIT_VERDICT:
        return JUDGE_EXIT_VERDICT[code], True
    if code in JUDGE_KILLED_EXITS:
        return "TIMEOUT", False
    return "CRASHED", False


def verdict_is_pass(verdict):
    return verdict == "PASS"


# ── corrections: the append-only way to fix a line already written ───
def is_correction(entry):
    return entry.get("record") == CORRECTION_RECORD


def apply_corrections(history):
    """Fold correction records onto the rows they correct.

    The craft series is append-only: a row recorded wrongly is never deleted or
    edited in place, because the provenance of a bad measurement is itself
    evidence. A correction is appended instead, naming the generation (and
    optionally the exact timestamp) it corrects and carrying the fields that
    replace the original's. Every read of the series for epoch health goes
    through here, so a corrected row cannot be read as its original self.

    Pure and idempotent: correction rows are consumed rather than emitted, so
    applying this to its own output is a no-op.
    """
    corrections = {}
    for e in history:
        if is_correction(e):
            corrections.setdefault(e.get("gen"), []).append(e)
    if not corrections:
        return list(history)
    out = []
    for e in history:
        if is_correction(e):
            continue
        applied = [c for c in corrections.get(e.get("gen"), [])
                   if not c.get("corrects") or c.get("corrects") == e.get("timestamp")]
        if not applied:
            out.append(e)
            continue
        fixed = dict(e)
        stamps = list(fixed.get("corrected_by") or [])
        for c in applied:
            for key, value in c.items():
                if key in ("record", "corrects", "gen", "timestamp", "note"):
                    continue
                fixed[key] = value
            if c.get("note"):
                fixed["correction_note"] = c["note"]
            stamps.append(c.get("timestamp"))
        fixed["corrected_by"] = stamps
        out.append(fixed)
    return out


# ── the craft series ─────────────────────────────────────────────────
def is_scored(entry):
    return (entry.get("status") == "scored"
            and isinstance(entry.get("min_overall"), (int, float)))


def scored_entries(history):
    return [e for e in apply_corrections(history) if is_scored(e)]


def entries_since(history, since):
    """Filter to entries at or after a day (epoch start). No filter when since is None.

    Corrections are applied first: no consumer of the series ever sees the
    uncorrected form of a row, and correction records never render as their own
    generation.
    """
    history = apply_corrections(history)
    day = parse_day(since)
    if day is None:
        return list(history)
    out = []
    for e in history:
        stamp = parse_day(e.get("timestamp"))
        if stamp is None or stamp >= day:
            out.append(e)
    return out


def load_craft_history(path):
    """The craft series as epoch health must read it, corrections applied."""
    return apply_corrections(load_jsonl(path))


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

    judge_verdict comes from the judge's EXIT CODE and from nothing else. The
    scores never imply a verdict: a run can produce two clean 8.0s and still be
    killed before it ships anything.

    status is "scored" only when the judge COMPLETED and both critics returned a
    numeric overall. A judge that did not complete carries no scores at all,
    even when a JSON file is sitting at the output path, because that file is
    the previous run's. Everything else (missing file, unparseable json, a
    critic unobtainable, a kill) is "unobtainable".
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
    verdict, completed = judge_outcome(judge_exit)
    entry["judge_verdict"] = verdict
    if not completed:
        entry["note"] = (
            f"judge did not complete (exit {judge_exit!r}); no verdict and no scores "
            "recorded — any JSON at the output path belongs to an earlier run")
        return entry
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
    # The judge's own self-reported verdict is recorded only when it DISAGREES
    # with the exit code, and only as an audit field. It never becomes
    # judge_verdict: a disagreement is a defect to look at, not a tie to break.
    self_reported = (data or {}).get("verdict")
    if self_reported and str(self_reported).strip().upper() != entry["judge_verdict"]:
        entry["judge_json_verdict"] = self_reported
        entry["verdict_mismatch"] = True
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


def _cmd_correct_craft(args):
    """Append a correction for a craft row already written. Fails closed.

    Append-only: the original line is left exactly where it is. Readers fold the
    correction over it (see apply_corrections), so the corrected row can never be
    read as its original self while its provenance stays on disk.
    """
    if args.status not in CRAFT_STATUSES:
        print(f"correct-craft: --status must be one of {CRAFT_STATUSES}, got "
              f"{args.status!r}", file=sys.stderr)
        return 2
    note = (args.note or "").strip()
    if len(note) < 20:
        print("correct-craft: --note must say why the original row was wrong "
              "(at least 20 characters)", file=sys.stderr)
        return 2
    verdict, _completed = judge_outcome(args.judge_exit)
    if args.judge_verdict:
        verdict = args.judge_verdict.strip().upper()
    if verdict_is_pass(verdict) and parse_exit(args.judge_exit) != 0:
        print(f"correct-craft: refusing to record PASS against judge exit "
              f"{args.judge_exit!r} — a non-zero exit is never a pass",
              file=sys.stderr)
        return 2
    if args.status == "scored":
        print("correct-craft: this command only demotes a row to 'unobtainable'; "
              "promoting a row to 'scored' would need the scores themselves",
              file=sys.stderr)
        return 2

    raw = load_jsonl(args.history)
    targets = [e for e in raw
               if not is_correction(e) and str(e.get("gen")) == str(args.gen)
               and (not args.corrects or e.get("timestamp") == args.corrects)]
    if not targets:
        where = f" at {args.corrects}" if args.corrects else ""
        print(f"correct-craft: no craft row for gen {args.gen}{where} in "
              f"{args.history} — nothing to correct", file=sys.stderr)
        return 2

    entry = {
        "record": CORRECTION_RECORD,
        "gen": int(args.gen) if str(args.gen).strip().lstrip("-").isdigit() else args.gen,
        "timestamp": utcnow_iso(),
        "corrects": args.corrects or targets[-1].get("timestamp"),
        "status": args.status,
        "critic_a": None,
        "critic_b": None,
        "min_overall": None,
        "judge_verdict": verdict,
        "note": note,
    }
    if args.judge_exit is not None:
        entry["judge_exit"] = args.judge_exit
    append_jsonl(args.history, entry)
    print(json.dumps(entry, ensure_ascii=False))
    return 0


def _cmd_plateau(args):
    history = load_craft_history(args.history)
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

    cp = sub.add_parser("correct-craft",
                        help="append a correction for a craft row already written")
    cp.add_argument("--history", required=True)
    cp.add_argument("--gen", required=True)
    cp.add_argument("--corrects", default=None,
                    help="timestamp of the exact row being corrected")
    cp.add_argument("--status", default="unobtainable")
    cp.add_argument("--judge-exit", default=None)
    cp.add_argument("--judge-verdict", default=None)
    cp.add_argument("--note", required=True)
    cp.set_defaults(func=_cmd_correct_craft)

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
