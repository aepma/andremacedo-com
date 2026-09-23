#!/usr/bin/env python3
"""epoch_fanout.py — several candidate openings at an epoch opening, judged, best one shipped.

Why this exists: when an epoch dies (an authored metamorphose verdict or the
mechanical backstop, both of which leave a clearing), the next weekly pulse opens
the successor epoch in ONE attempt. An opening sets the identity every later
generation of the epoch deepens, so it is the one place where generating several
directions and keeping the best is worth its cost. Weekly deepen pulses, event
pulses and daily refreshes never reach this module.

Flow (subcommand `run`, invoked by runner.sh before its single attempt):
  1. Trigger: weekly pulse AND state/agent-state.json active_obsession.topic is
     empty (a clearing: the session is about to author the next obsession) AND
     this opening has no record in state/epoch-fanout-log.jsonl (cost bound: at
     most one fan-out per opening, whatever its outcome).
  2. N candidates (default 4), SEQUENTIAL, each in its own scratch copy of the
     site, each through the same generation-session.sh the runner uses. They
     must be sequential: the in-session gate chain writes fixed /tmp artifact
     paths (screenshot-local.sh, /tmp/craft-self.json), which is also the only
     /tmp grant the Kimi cage (sandbox/kimi-build.sb) has. Each candidate is told
     its own direction brief and what earlier candidates chose, and must differ.
  3. Hard filters, before any scoring, using the TRUSTED gate scripts in the
     live site (never a candidate's own copy): session verdict OK, a valid
     generation record that actually opens an epoch, protected files untouched
     (SOUL/INVARIANTS/MISSION/HEARTBEAT/TOOLS, scripts/, launchd/, deploy.sh,
     chat widget), validate-build.py (INVARIANTS.md incl. frozen substrate),
     render, mobile-gate.js, audit-contrast.js, visitor-floor.js. Any non-zero
     exit is out. verify-frozen-substrate.sh runs once as a preflight.
  4. Scoring: craft-judge.py --tone on each survivor (two families, fail-closed,
     unchanged), which adds a tone axis against Andre's target line. Per critic
     combined = mean(craft overall, tone). Rank: craft gate passed first, then
     highest min(combined A, combined B), so one generous critic cannot carry a
     candidate. Every score is recorded.
  5. Fail closed: fewer than 2 survivors, or any critic unobtainable on any
     survivor, means NO fan-out winner (exit 3); the runner then makes today's
     single attempt. An unjudged fan-out winner is never installed.
  6. The winner's allowed files (index.html, state/generation-meta.json, and
     what it changed under experiments/, assets/, data/) are installed into the
     site and its result event is written for the runner, with usage summed over
     every candidate. Every downstream runner gate still runs on it.
  7. Losers' screenshots and scores go to archive-screenshots/ with manifest
     entries marked unshipped_candidate, for a future "road not taken" view.

Exit codes: 0 = winner installed; 3 = no fan-out (not an opening, already fanned
out, disabled, or fail-closed fallback). Anything else is a crash; the runner
logs it and falls back to the single attempt. The site is only written after a
winner is chosen, and a failed install is rolled back.

Kill switch: ANDREMACEDO_FANOUT_DISABLE=1 skips fan-out entirely.

`rehearse` runs the gate + judge + selection steps on renders of past commits,
without installing, archiving or writing the ledger (verification only).
"""
import argparse, hashlib, json, os, shutil, signal, subprocess, sys, time
from datetime import datetime, timezone

NO_FANOUT = 3
DEFAULT_CANDIDATES = 4
MIN_SURVIVORS = 2
GATE_TIMEOUT = 180            # per deterministic gate call, seconds
LEDGER = "epoch-fanout-log.jsonl"

# Direction briefs, one per slot, so candidates diverge even when earlier ones
# failed and left nothing to differ from.
DIRECTIONS = (
    "Take the obsession your lineage most strongly predicts, and execute it with "
    "more conviction and less hedging than any previous opening.",
    "Take an obsession from a domain your lineage has never touched. No physics of "
    "emergence, no oscillators, no light-on-structure unless you can make it "
    "unrecognisable.",
    "Invert the page's form. If recent epochs were dark, go light; if dense, go "
    "sparse; if the hero was an instrument, make it a single still image.",
    "Take the strangest reading you can still defend: the opening a visitor could "
    "not categorise but could describe from memory a week later.",
)

TONE_LINE = "I have no idea what I just saw but I can't stop thinking about it."

PROTECTED_FILES = ("SOUL.md", "INVARIANTS.md", "MISSION.md", "HEARTBEAT.md",
                   "TOOLS.md", "deploy.sh", "chat-widget.js")
PROTECTED_DIRS = ("scripts", "launchd")
INSTALL_FILES = ("index.html", os.path.join("state", "generation-meta.json"))
INSTALL_DIRS = ("experiments", "assets", "data")
COPY_SKIP_DIRS = {".git", "node_modules", "logs", "__pycache__", ".pw-browsers",
                  ".pw-node", ".venv-pw"}


def log(msg):
    print(f"[epoch-fanout {datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}] {msg}",
          flush=True)


def utcnow():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def tree_hashes(root, rel_dirs=(), rel_files=()):
    """{relpath: sha256} for the named files and every regular file under the dirs.
    Symlinks are recorded by target so a swapped link is a change."""
    out = {}
    for rf in rel_files:
        p = os.path.join(root, rf)
        if os.path.islink(p):
            out[rf] = "link:" + os.readlink(p)
        elif os.path.isfile(p):
            out[rf] = sha256(p)
    for rd in rel_dirs:
        base = os.path.join(root, rd)
        for dirpath, dirnames, filenames in os.walk(base):
            dirnames[:] = [d for d in dirnames if d != "__pycache__"]
            for fn in filenames:
                if fn.endswith(".pyc"):
                    continue
                p = os.path.join(dirpath, fn)
                rel = os.path.relpath(p, root)
                out[rel] = ("link:" + os.readlink(p)) if os.path.islink(p) else sha256(p)
    return out


# ── trigger ──────────────────────────────────────────────────────────
def opening_key(site):
    """The identity of the opening about to happen, or None if the epoch is live."""
    state = load_json(os.path.join(site, "state", "agent-state.json"))
    genome = load_json(os.path.join(site, "state", "genome.json"))
    obs = state.get("active_obsession") or {}
    if (obs.get("topic") or "").strip():
        return None
    epoch_number = genome.get("epoch_number")
    assert isinstance(epoch_number, int), "genome.json epoch_number must be an int"
    return f"epoch-{epoch_number}:clearing-{obs.get('started') or 'unknown'}"


def ledger_path(site):
    return os.path.join(site, "state", LEDGER)


def ledger_keys(site):
    keys = set()
    try:
        with open(ledger_path(site), encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    keys.add(json.loads(line).get("opening_key"))
                except ValueError:
                    continue
    except FileNotFoundError:
        pass
    return keys


def append_ledger(site, entry):
    with open(ledger_path(site), "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def should_fanout(site, pulse):
    """(bool, reason, key)."""
    if os.environ.get("ANDREMACEDO_FANOUT_DISABLE") == "1":
        return False, "disabled by ANDREMACEDO_FANOUT_DISABLE=1", None
    if pulse != "weekly":
        return False, f"pulse {pulse!r} is not weekly", None
    key = opening_key(site)
    if key is None:
        return False, "epoch is live (active obsession set); not an opening", None
    if key in ledger_keys(site):
        return False, f"opening {key} already fanned out once (cost bound)", key
    return True, f"epoch opening {key}", key


# ── candidate trees and sessions ─────────────────────────────────────
def copy_ignore(site):
    def ignore(dirpath, names):
        skip = set()
        rel = os.path.relpath(dirpath, site)
        for n in names:
            if rel == "." and (n in COPY_SKIP_DIRS or n.endswith(".tar.gz")):
                skip.add(n)
            elif rel == "archive-screenshots" and n != "manifest.json":
                skip.add(n)
            elif n == "__pycache__":
                skip.add(n)
        return skip
    return ignore


def make_candidate_tree(site, dest):
    assert not os.path.exists(dest), f"candidate tree already exists: {dest}"
    shutil.copytree(site, dest, symlinks=True, ignore=copy_ignore(site))
    nm = os.path.join(site, "node_modules")
    if os.path.isdir(nm):
        os.symlink(nm, os.path.join(dest, "node_modules"))
    gm = os.path.join(dest, "state", "generation-meta.json")
    if os.path.exists(gm):
        os.remove(gm)       # a stale record must never satisfy a candidate's gate
    return tree_hashes(dest, INSTALL_DIRS, INSTALL_FILES)


def fanout_brief(slot, total, prior):
    lines = ["", "", f"## EPOCH-OPENING FAN-OUT — CANDIDATE {slot} OF {total}", "",
             f"This opening is generated {total} times, independently. Two external "
             "critics then judge every candidate that clears the gates, and only the "
             "best one ships. The others are archived as the road not taken.",
             "", "Your direction for this candidate: " + DIRECTIONS[(slot - 1) % len(DIRECTIONS)],
             "", "The site's tone target, in Andre's words: \"" + TONE_LINE + "\" "
             "The critics score your render against that line, from the pixels alone.",
             "", "Everything in the protocol above still binds you: gates, craft judge, "
             "the verdict line, the files you may write."]
    if prior:
        lines += ["", "Earlier candidates in this fan-out already chose the following. Take "
                  "a CLEARLY different obsession AND a clearly different visual strategy:"]
        for p in prior:
            lines.append(f"- candidate {p['slot']}: obsession {p.get('topic')!r}; "
                         f"visual strategy {p.get('visual_strategy')!r}")
    return "\n".join(lines)


def candidate_input(input_jsonl, out_path, site, cand, brief):
    """Rewrite the runner's stream-json message for one candidate: every site path
    in the text points at the candidate tree, the brief is appended, images kept."""
    site_real = os.path.realpath(site)
    with open(input_jsonl, encoding="utf-8") as f:
        msg = json.loads(f.readline())
    content = msg["message"]["content"]
    texts = [p for p in content if p.get("type") == "text"]
    assert texts, "runner input has no text block"
    for p in texts:
        t = p["text"].replace(site_real, cand)
        if site != site_real:
            t = t.replace(site, cand)
        p["text"] = t
    texts[-1]["text"] += brief
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(json.dumps(msg) + "\n")


def run_bounded(argv, cwd, env, timeout, stdout, stderr):
    """Run in its own process group; on overrun kill the whole group, return 124."""
    proc = subprocess.Popen(argv, cwd=cwd, env=env, stdout=stdout, stderr=stderr,
                            start_new_session=True)
    try:
        return proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(proc.pid, signal.SIGTERM)
            proc.wait(timeout=15)
        except (subprocess.TimeoutExpired, ProcessLookupError):
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            proc.wait()
        return 124


def parse_result(out_path):
    """(text, usage, verdict) from the last result event, as runner.sh parses it."""
    last = None
    try:
        with open(out_path, errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    o = json.loads(line)
                except ValueError:
                    continue
                if isinstance(o, dict) and o.get("type") == "result":
                    last = o
    except FileNotFoundError:
        return "", {}, ""
    if not last or last.get("is_error"):
        return "", {}, ""
    text = (last.get("result") or "").strip()
    verdict = ""
    for line in reversed([l.strip() for l in text.splitlines() if l.strip()]):
        if line.startswith("GENERATION_VERDICT:"):
            verdict = line
            break
    return text, last.get("usage") or {}, verdict


# ── gates ─────────────────────────────────────────────────────────────
def gate(name, passed, detail="", exit_code=None):
    return {"name": name, "passed": bool(passed), "exit": exit_code, "detail": str(detail)[:400]}


def run_gate(name, argv, env, log_path):
    with open(log_path, "a", encoding="utf-8") as lf:
        lf.write(f"\n=== {name}: {' '.join(argv)}\n")
        lf.flush()
        rc = run_bounded(argv, None, env, GATE_TIMEOUT, lf, lf)
    return gate(name, rc == 0, f"exit {rc}", rc)


def render(site, cand, shots, log_path):
    os.makedirs(shots, exist_ok=True)
    env = dict(os.environ, ANDREMACEDO_RENDER_DIR=cand, ANDREMACEDO_SELF_SHOT_DIR=shots)
    g = run_gate("render", ["bash", os.path.join(site, "scripts", "screenshot-local.sh")],
                 env, log_path)
    desk = os.path.join(shots, "andremacedo-self-desktop.jpg")
    mob = os.path.join(shots, "andremacedo-self-mobile.jpg")
    if g["passed"] and not all(os.path.isfile(p) and os.path.getsize(p) > 0 for p in (desk, mob)):
        g = gate("render", False, "screenshots empty", g["exit"])
    return g, desk, mob


def deterministic_gates(site, cand, shots, log_path):
    """validate-build, render, mobile, contrast, visitor floor — trusted scripts on
    the candidate's index.html; stops at the first failure. Returns (gates, shots):
    shots are the render's (desktop, mobile) whenever the render passed, so a
    candidate that fails a later gate can still be archived."""
    sd = os.path.join(site, "scripts")
    index = os.path.join(cand, "index.html")
    env = dict(os.environ)
    gates = [run_gate("validate_build", ["python3", os.path.join(sd, "validate-build.py"), index],
                      env, log_path)]
    if not gates[-1]["passed"]:
        return gates, None
    g, desk, mob = render(site, cand, shots, log_path)
    gates.append(g)
    if not g["passed"]:
        return gates, None
    shots = (desk, mob)
    for name, argv in (("mobile_gate", ["node", os.path.join(sd, "mobile-gate.js"), index]),
                       ("contrast", ["node", os.path.join(sd, "audit-contrast.js"), "local", index]),
                       ("visitor_floor", ["node", os.path.join(sd, "visitor-floor.js"), index])):
        gates.append(run_gate(name, argv, env, log_path))
        if not gates[-1]["passed"]:
            break
    return gates, shots


def protected_gate(site, cand):
    want = tree_hashes(site, PROTECTED_DIRS, PROTECTED_FILES)
    got = tree_hashes(cand, PROTECTED_DIRS, PROTECTED_FILES)
    changed = sorted(k for k in set(want) | set(got) if want.get(k) != got.get(k))
    return gate("protected_files", not changed,
                "untouched" if not changed else "changed: " + ", ".join(changed[:8]))


def meta_gate(cand):
    path = os.path.join(cand, "state", "generation-meta.json")
    try:
        meta = load_json(path)
    except (OSError, ValueError) as e:
        return gate("generation_meta", False, f"unreadable: {e}"), None
    if not isinstance(meta, dict):
        return gate("generation_meta", False, "not a JSON object"), None
    topic = ((meta.get("obsession_update") or {}).get("topic") or "").strip()
    if not topic:
        return gate("generation_meta", False, "no obsession_update.topic: does not open an epoch"), meta
    return gate("generation_meta", True, topic[:120]), meta


def gate_candidate(site, cand, shots, helper_exit, verdict, log_path):
    """All hard filters in order, first failure wins. Returns (gates, shots|None, meta);
    the candidate survived iff every gate passed."""
    gates = [gate("session_verdict",
                  helper_exit == 0 and verdict.startswith("GENERATION_VERDICT: OK"),
                  f"helper exit {helper_exit}; {verdict or 'no verdict'}", helper_exit)]
    if not gates[-1]["passed"]:
        return gates, None, None
    g, meta = meta_gate(cand)
    gates.append(g)
    if not g["passed"]:
        return gates, None, meta
    gates.append(protected_gate(site, cand))
    if not gates[-1]["passed"]:
        return gates, None, meta
    more, shot_paths = deterministic_gates(site, cand, shots, log_path)
    gates += more
    return gates, shot_paths, meta


# ── judging and selection ────────────────────────────────────────────
def judge(site, desk, mob, json_out, judge_path=None):
    """Run craft-judge.py --tone. Returns (scores|None, error|None). scores carries
    per-critic craft overall, tone, combined, all axes, and the craft gate result."""
    judge_path = judge_path or os.path.join(site, "scripts", "craft-judge.py")
    try:
        wall = int(subprocess.run(["python3", judge_path, "--print-wall-budget"],
                                  capture_output=True, text=True, timeout=30,
                                  check=True).stdout.strip())
    except Exception as e:  # noqa: BLE001 — unreadable budget is fail-closed
        return None, f"judge wall budget unreadable: {e}"
    assert wall > 0, "judge wall budget must be positive"
    argv = ["python3", judge_path, "--desktop", desk, "--mobile", mob, "--margin", "7.3",
            "--wall-budget", str(wall), "--tone", "--json-out", json_out, "--quiet"]
    if os.path.exists(json_out):
        os.remove(json_out)
    rc = run_bounded(argv, None, dict(os.environ), wall + 30,
                     subprocess.DEVNULL, subprocess.DEVNULL)
    if rc not in (0, 1) or not os.path.isfile(json_out):
        err = f"judge exit {rc}"
        if os.path.isfile(json_out):
            try:
                err += ": " + str(load_json(json_out).get("error", ""))[:300]
            except ValueError:
                pass
        return None, err
    v = load_json(json_out)
    crit = v.get("critics") or {}
    if not v.get("tone_axis") or not all(
            "combined" in (crit.get(k) or {}) and "tone" in ((crit.get(k) or {}).get("axes") or {})
            for k in ("A", "B")):
        return None, "judge verdict lacks the tone axis for both critics"
    scores = {"craft_verdict": v.get("verdict"), "craft_passed": rc == 0,
              "gate_rule": v.get("gate_rule"), "reason": v.get("reason"),
              "combined_min": float(v["combined_min"]), "critics": {}}
    for k in ("A", "B"):
        c = crit[k]
        scores["critics"][k] = {"model": c.get("model"), "overall": c.get("overall"),
                                "tone": c["axes"]["tone"], "combined": c["combined"],
                                "is_slop": c.get("is_slop"), "axes": c.get("axes"),
                                "findings": (c.get("findings") or [])[:5]}
    if v.get("critic_b_degraded"):
        scores["critic_b_degraded"] = v["critic_b_degraded"]
    return scores, None


def rank_key(c):
    s = c["scores"]
    return (1 if s["craft_passed"] else 0, s["combined_min"])


def select_winner(candidates):
    """Pure selection over judged candidates (dicts with 'slot' and 'scores').
    Craft-gate passers first (a winner the craft gate rejects would be reverted by
    the runner's authoritative gate anyway), then highest min(combined A, B).
    Ties go to the earlier slot. Returns (winner, ranking)."""
    assert candidates, "select_winner needs at least one judged candidate"
    ranking = sorted(candidates, key=lambda c: (-rank_key(c)[0], -rank_key(c)[1], c["slot"]))
    return ranking[0], ranking


# ── install, archive ─────────────────────────────────────────────────
def install_winner(site, cand, baseline, backup_dir):
    """Copy only what the winner itself changed, inside the allowed scope, into the
    site. Rolls back every write on failure. Returns the list of changes."""
    now = tree_hashes(cand, INSTALL_DIRS, INSTALL_FILES)
    changes = sorted(k for k in set(baseline) | set(now) if baseline.get(k) != now.get(k))
    assert "index.html" in changes, "winner did not change index.html"
    assert os.path.join("state", "generation-meta.json") in changes, "winner wrote no generation record"
    done = []
    try:
        for rel in changes:
            dst, src = os.path.join(site, rel), os.path.join(cand, rel)
            bak = os.path.join(backup_dir, rel)
            existed = os.path.lexists(dst)
            if existed:
                os.makedirs(os.path.dirname(bak), exist_ok=True)
                shutil.copy2(dst, bak, follow_symlinks=False)
            done.append((rel, existed))
            if rel in now:
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                if os.path.lexists(dst):
                    os.remove(dst)
                shutil.copy2(src, dst, follow_symlinks=False)
            elif existed:
                os.remove(dst)
    except Exception:
        for rel, existed in reversed(done):
            dst = os.path.join(site, rel)
            if os.path.lexists(dst):
                os.remove(dst)
            if existed:
                shutil.copy2(os.path.join(backup_dir, rel), dst, follow_symlinks=False)
        raise
    return changes


def archive_losers(site, losers, key, stamp):
    """Screenshots + scores of every non-winning candidate that rendered."""
    adir = os.path.join(site, "archive-screenshots")
    manifest_path = os.path.join(adir, "manifest.json")
    try:
        manifest = load_json(manifest_path)
    except (OSError, ValueError):
        manifest = []
    assert isinstance(manifest, list), "archive manifest must be a list"
    added = 0
    for c in losers:
        shots = c.get("shots")
        if not shots:
            continue
        names = {}
        for kind, src in zip(("desktop", "mobile"), shots):
            name = f"{stamp}-fanout-cand{c['slot']}-{kind}.jpg"
            shutil.copy2(src, os.path.join(adir, name))
            names[kind] = name
        manifest.append({
            "timestamp": stamp, "screenshot": names["desktop"],
            "screenshot_mobile": names["mobile"], "commit": None,
            "unshipped_candidate": True, "epoch_opening": key,
            "candidate": c["slot"], "obsession": c.get("topic"),
            "visual_strategy": c.get("visual_strategy"),
            "summary": f"unshipped epoch-opening candidate {c['slot']}: {c.get('topic') or 'untitled'}"[:200],
            "gates": c["gates"], "scores": c.get("scores"),
            "not_scored_reason": c.get("not_scored_reason"),
        })
        added += 1
    tmp = manifest_path + ".fanout-tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)
    os.replace(tmp, manifest_path)
    return added


def result_event(winner_out, usage_total, out_path):
    last = None
    with open(winner_out, errors="replace") as f:
        for line in f:
            try:
                o = json.loads(line)
            except ValueError:
                continue
            if isinstance(o, dict) and o.get("type") == "result":
                last = o
    assert last is not None, "winner has no result event"
    last = dict(last, usage=usage_total)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(json.dumps(last) + "\n")


# ── judge + select, shared by run and rehearse ───────────────────────
def judge_and_select(site, cands, rundir, judge_path, score_all=False):
    """Judge survivors (and, for rehearsal, gate failures that rendered). Returns
    (winner|None, ranking, fallback_reason|None)."""
    survivors = [c for c in cands if c["survived"]]
    to_judge = [c for c in cands if c.get("shots")] if score_all else survivors
    if not score_all and len(survivors) < MIN_SURVIVORS:
        return None, [], f"only {len(survivors)} candidate(s) survived the gates (need {MIN_SURVIVORS})"
    unobtainable = None
    for c in to_judge:
        desk, mob = c["shots"]
        scores, err = judge(site, desk, mob, os.path.join(rundir, f"judge-cand{c['slot']}.json"),
                            judge_path)
        c["scores"] = scores
        if err:
            c["not_scored_reason"] = err
            if c["survived"] and unobtainable is None:
                unobtainable = f"candidate {c['slot']}: critic unobtainable ({err})"
        log(f"candidate {c['slot']} judged: " + (err or
            f"craft {scores['craft_verdict']} combined_min {scores['combined_min']} "
            f"(A {scores['critics']['A']['combined']}, B {scores['critics']['B']['combined']})"))
    if len(survivors) < MIN_SURVIVORS:
        return None, [], f"only {len(survivors)} candidate(s) survived the gates (need {MIN_SURVIVORS})"
    if unobtainable:
        return None, [], unobtainable
    winner, ranking = select_winner(survivors)
    return winner, ranking, None


def candidate_record(c):
    return {k: c.get(k) for k in ("slot", "source", "helper_exit", "verdict", "topic",
                                  "visual_strategy", "survived", "gates", "scores",
                                  "not_scored_reason", "elapsed_s")}


# ── subcommands ──────────────────────────────────────────────────────
def cmd_should(args):
    ok, reason, _ = should_fanout(args.site, args.pulse)
    print(reason)
    return 0 if ok else NO_FANOUT


def cmd_run(args):
    site = os.path.abspath(args.site)
    pulse = os.environ.get("PULSE_TYPE", args.pulse)
    ok, reason, key = should_fanout(site, pulse)
    if not ok:
        log(f"no fan-out: {reason}")
        return NO_FANOUT
    assert args.candidates >= MIN_SURVIVORS, "need at least 2 candidates to compare"
    assert args.wall > 0, "per-candidate wall must be positive"
    t0 = time.time()
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d-%H%M%S")
    rundir = os.path.join(os.path.abspath(os.path.expanduser(args.root)), stamp)
    os.makedirs(rundir)
    # Cost bound: the opening is marked BEFORE any session is spent, so a crash
    # mid-run cannot re-trigger four more sessions next week.
    append_ledger(site, {"opening_key": key, "event": "started", "at": utcnow(),
                         "candidates_planned": args.candidates, "rundir": rundir})
    log(f"fan-out start: {reason}; {args.candidates} candidates; rundir {rundir}")

    def finish(outcome, **extra):
        elapsed = round(time.time() - t0, 1)
        entry = {"opening_key": key, "event": "finished", "at": utcnow(), "outcome": outcome,
                 "candidate_count": len(cands), "elapsed_s": elapsed,
                 "candidates": [candidate_record(c) for c in cands], **extra}
        append_ledger(site, entry)
        # The scratch site copies are the bulk of the run dir; screenshots, logs,
        # session transcripts and judge verdicts stay for diagnosis.
        for c in cands:
            shutil.rmtree(c["tree"], ignore_errors=True)
        log(f"fan-out {outcome}: candidates={len(cands)} elapsed={elapsed}s "
            + " ".join(f"{k}={v}" for k, v in extra.items() if k in ("winner", "fallback_reason")))

    cands = []
    pre = subprocess.run(["bash", os.path.join(site, "scripts", "verify-frozen-substrate.sh")],
                         capture_output=True, text=True)
    if pre.returncode != 0:
        tail = pre.stdout.strip().splitlines()[-1] if pre.stdout.strip() else "no output"
        finish("fallback", fallback_reason=f"verify-frozen-substrate.sh exit {pre.returncode}: {tail}")
        return NO_FANOUT

    session = os.path.join(site, "scripts", "generation-session.sh")
    usage_total = {"input_tokens": 0, "cache_creation_input_tokens": 0,
                   "cache_read_input_tokens": 0, "output_tokens": 0}
    prior = []
    for slot in range(1, args.candidates + 1):
        ct = time.time()
        cdir = os.path.join(rundir, f"cand{slot}")
        tree = os.path.join(cdir, "tree")
        os.makedirs(cdir)
        baseline = make_candidate_tree(site, tree)
        jsonl = os.path.join(cdir, "input.jsonl")
        out = os.path.join(cdir, "helper-output.jsonl")
        candidate_input(args.input_jsonl, jsonl, site, tree,
                        fanout_brief(slot, args.candidates, prior))
        env = dict(os.environ, INPUT_JSONL=jsonl, OUTPUT_FILE=out, BUILD_TREE=tree,
                   PULSE_TYPE=pulse, TELOS_AGENT=f"andremacedo-creative:weekly-fanout-c{slot}")
        with open(os.path.join(cdir, "session.log"), "w") as sl:
            hexit = run_bounded(["bash", session, "agentic"], tree, env, args.wall, sl, sl)
        _text, usage, verdict = parse_result(out)
        for k in usage_total:
            usage_total[k] += int(usage.get(k) or 0)
        gates, shots, meta = gate_candidate(site, tree, os.path.join(cdir, "shots"),
                                            hexit, verdict, os.path.join(cdir, "gates.log"))
        c = {"slot": slot, "source": "session", "dir": cdir, "tree": tree, "baseline": baseline,
             "out": out, "helper_exit": hexit, "verdict": verdict, "gates": gates,
             "shots": shots, "survived": shots is not None and all(g["passed"] for g in gates),
             "topic": ((meta or {}).get("obsession_update") or {}).get("topic"),
             "visual_strategy": (meta or {}).get("visual_strategy"),
             "elapsed_s": round(time.time() - ct, 1)}
        cands.append(c)
        if c["topic"]:
            prior.append({"slot": slot, "topic": c["topic"], "visual_strategy": c["visual_strategy"]})
        failed = next((g for g in gates if not g["passed"]), None)
        log(f"candidate {slot}: {'survived' if c['survived'] else 'out at ' + failed['name'] + ' (' + failed['detail'] + ')'}"
            f" in {c['elapsed_s']}s")

    winner, ranking, why = judge_and_select(site, cands, rundir, args.judge)
    if winner is None:
        finish("fallback", fallback_reason=why)
        return NO_FANOUT

    changes = install_winner(site, winner["tree"], winner["baseline"],
                             os.path.join(rundir, "install-backup"))
    result_event(winner["out"], usage_total, args.output)
    losers = [c for c in cands if c is not winner]
    archived = archive_losers(site, losers, key, stamp)
    finish("winner_installed", winner=winner["slot"],
           ranking=[c["slot"] for c in ranking], installed=changes,
           archived_losers=archived, usage_total=usage_total)
    return 0


def cmd_rehearse(args):
    """Gate + judge + select on renders of past commits. Writes nothing to the site."""
    site = os.path.abspath(args.site)
    rundir = os.path.abspath(args.out_dir)
    os.makedirs(rundir, exist_ok=True)
    t0 = time.time()
    cands = []
    pre = subprocess.run(["bash", os.path.join(site, "scripts", "verify-frozen-substrate.sh")],
                         capture_output=True, text=True)
    for slot, commit in enumerate(args.commits.split(","), start=1):
        cdir = os.path.join(rundir, f"cand{slot}")
        tree = os.path.join(cdir, "tree")
        assert not os.path.exists(cdir), f"rehearsal dir exists: {cdir}"
        os.makedirs(tree)
        arch = subprocess.run(["git", "-C", site, "archive", "--format=tar", commit],
                              capture_output=True, check=True).stdout
        subprocess.run(["tar", "-x", "-C", tree], input=arch, check=True)
        if os.path.isdir(os.path.join(site, "node_modules")):
            os.symlink(os.path.join(site, "node_modules"), os.path.join(tree, "node_modules"))
        gates, shot_paths = deterministic_gates(site, tree, os.path.join(cdir, "shots"),
                                                os.path.join(cdir, "gates.log"))
        render_gate = next((g for g in gates if g["name"] == "render"), None)
        if render_gate is None:
            # Out before rendering: render anyway so the critics can still be
            # rehearsed on it. It stays ineligible for selection.
            render_gate, _d, _m = render(site, tree, os.path.join(cdir, "shots"),
                                         os.path.join(cdir, "gates.log"))
        if shot_paths is None and render_gate["passed"]:
            shot_paths = (os.path.join(cdir, "shots", "andremacedo-self-desktop.jpg"),
                          os.path.join(cdir, "shots", "andremacedo-self-mobile.jpg"))
        subj = subprocess.run(["git", "-C", site, "log", "-1", "--format=%s", commit],
                              capture_output=True, text=True).stdout.strip()
        cands.append({"slot": slot, "source": f"commit {commit}", "topic": subj[:160],
                      "gates": gates, "shots": shot_paths,
                      "survived": all(g["passed"] for g in gates) and len(gates) == 5})
        log(f"rehearsal candidate {slot} ({commit}): "
            + ("survived" if cands[-1]["survived"] else "out at "
               + next(g for g in gates if not g["passed"])["name"]))
    winner, ranking, why = judge_and_select(site, cands, rundir, args.judge, score_all=True)
    report = {
        "generated_at": utcnow(), "site": site, "commits": args.commits.split(","),
        "tone_line": TONE_LINE, "frozen_substrate_preflight_exit": pre.returncode,
        "selection_rule": "hard gates first; survivors ranked craft-gate-passed first, then "
                          "max of min(critic A combined, critic B combined); combined = "
                          "mean(craft overall, tone)",
        "candidates": [candidate_record(c) for c in cands],
        "winner": None if winner is None else {"slot": winner["slot"], "source": winner["source"],
                                               "combined_min": winner["scores"]["combined_min"]},
        "ranking": [c["slot"] for c in ranking],
        "fallback_reason": why,
        "both_critics_scored_tone_on": [c["slot"] for c in cands if c.get("scores")],
        "elapsed_s": round(time.time() - t0, 1),
    }
    with open(args.json_out, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    log(f"rehearsal written: {args.json_out}; winner "
        f"{report['winner'] and report['winner']['slot']}; fallback {why}")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    sp = sub.add_parser("should-fanout")
    sp.add_argument("--site", required=True)
    sp.add_argument("--pulse", default="weekly")
    rp = sub.add_parser("run")
    rp.add_argument("--site", required=True)
    rp.add_argument("--input-jsonl", required=True)
    rp.add_argument("--output", required=True)
    rp.add_argument("--wall", type=int, required=True, help="per-candidate session wall, seconds")
    rp.add_argument("--candidates", type=int, default=DEFAULT_CANDIDATES)
    rp.add_argument("--pulse", default="weekly")
    rp.add_argument("--root", default=os.environ.get("ANDREMACEDO_FANOUT_ROOT",
                                                     "~/.telos/tmp/andremacedo-fanout"))
    rp.add_argument("--judge", default=None, help="craft judge path (test seam)")
    hp = sub.add_parser("rehearse")
    hp.add_argument("--site", required=True)
    hp.add_argument("--commits", required=True)
    hp.add_argument("--out-dir", required=True)
    hp.add_argument("--json-out", required=True)
    hp.add_argument("--judge", default=None)
    args = ap.parse_args(argv)
    return {"should-fanout": cmd_should, "run": cmd_run, "rehearse": cmd_rehearse}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
