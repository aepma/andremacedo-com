#!/usr/bin/env python3
"""epoch_fanout.py — three candidates every weekly run; Andre picks; only a pick ships.

Andre's order of 2026-11-27 (first-principles redesign). Until then the fan-out
ran only at an epoch opening and shipped whichever candidate the critics ranked
highest, so every epoch discarded the last design on the engine's own taste.
Now every weekly run (and every event run) goes through here, and nothing it
builds deploys on its own:

  1. A picked candidate waiting to go live is installed first (site_pick.py
     install): its files go into the site and its result event is written for
     the runner, whose gates all run on it before the deploy. Exit 0.
  2. Otherwise, while an earlier offer still waits for Andre's answer, nothing is
     built (one message per run, never a reminder). Exit 4.
  3. Otherwise CANDIDATES (3) candidates are built, SEQUENTIAL, each in its own
     scratch copy of the site, through the same generation-session.sh the runner
     uses. They must be sequential: the in-session gate chain writes fixed /tmp
     artifact paths. Each is given its own direction, the references folder as
     the target, and what earlier candidates chose, and must differ clearly.
     Until Andre has picked once (references/picks/picks.jsonl holds a pick;
     None is not a pick), no candidate inherits from the live page: each starts
     from its own idea, named in its record, without the live screenshots, and
     none uses knotted strings. After a first pick they evolve from the pick.
     Before building, reference notes that name a source and have no pictures
     get scene pictures (capture_references.py); a failed capture is one log
     line and the run goes on (directed piece, 2026-11-27).
  4. The existing gates run on each, using the TRUSTED scripts in the live site:
     session verdict OK, a valid generation record, protected files untouched,
     at least three recorded passes with scene pictures (build, compare with
     the references, name the weakest scene, rebuild it), and on a fresh start
     a named idea unlike the others and no knotted strings, then
     validate-build.py, render, mobile-gate.js, audit-contrast.js,
     visitor-floor.js, then craft-judge.py (both critics, fail-closed). A
     candidate passes only if every gate passes.
  5. Passing candidates go to site_pick.offer(): one Telegram message with a
     desktop and a mobile screenshot of each and buttons Pick 1..3 and None.
     No passing candidate means no message. Either way exit 4: nothing deploys.

Their tokens are added to the monthly budget here, because the runner stops
after an offer and never reads this run's usage.

Exit codes: 0 = a pick was installed (the runner gates and deploys it);
3 = not a weekly or event pulse, or disabled; 4 = nothing to install this run.
Anything else is a crash. The runner deploys only on 0.

Kill switch: ANDREMACEDO_FANOUT_DISABLE=1 builds nothing (a waiting pick still
installs).
"""
import argparse, hashlib, json, os, re, shutil, signal, subprocess, sys, time
from datetime import datetime, timezone

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import site_pick  # noqa: E402

NOT_A_PICK_PULSE = 3
NOTHING_TO_INSTALL = 4
CANDIDATES = 3
GATE_TIMEOUT = 180            # per deterministic gate call, seconds
LEDGER = "epoch-fanout-log.jsonl"

# One direction per slot, so the three candidates differ clearly even when an
# earlier one failed and left nothing to differ from.
DIRECTIONS = (
    "Refine. Keep the live page's idea and identity. Make it clearer and better made: "
    "who Andre is lands faster, the type and spacing are more disciplined, the motion "
    "has more intent.",
    "Evolve boldly. Keep what works in the live page, then push its idea much further: "
    "a stronger hero, a braver composition, one moment a visitor would describe later.",
    "Take a clearly different direction that still does the job: a new layout, palette "
    "and type, closer to a reference in references/ than to the live page.",
)

# Before Andre's first pick: three fresh ideas, one lens each (directed piece, 2026-11-27).
FRESH_DIRECTIONS = (
    "Lens: one visual object that changes from scene to scene and carries the story.",
    "Lens: type in motion. Words are few, and how they move, grow and break carries the meaning.",
    "Lens: a space the visitor travels through, one place per scene, drawn in code.",
)
MIN_PASSES = 3
PASSES_DIR = os.path.join("state", "passes")
# The live page's motif in 2026-11 (gen 267: the khipu). A fresh start may not use it.
BANNED_MOTIF = re.compile(r"khipu|quipu|knot", re.I)

PROTECTED_FILES = ("SOUL.md", "INVARIANTS.md", "MISSION.md", "HEARTBEAT.md",
                   "TOOLS.md", "deploy.sh", "chat-widget.js")
PROTECTED_DIRS = ("scripts", "launchd", "references")
INSTALL_FILES = ("index.html", os.path.join("state", "generation-meta.json"))
INSTALL_DIRS = ("experiments", "assets", "data")
COPY_SKIP_DIRS = {".git", "node_modules", "logs", "__pycache__", ".pw-browsers",
                  ".pw-node", ".venv-pw"}


def log(msg):
    print(f"[epoch-fanout {utcnow()}] {msg}", flush=True)


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


def opening_key(site):
    """The clearing an operator burial leaves, or None while an epoch is live.
    Read by epoch-operator-clear.py; the weekly candidates no longer depend on it."""
    state = load_json(os.path.join(site, "state", "agent-state.json"))
    genome = load_json(os.path.join(site, "state", "genome.json"))
    obs = state.get("active_obsession") or {}
    if (obs.get("topic") or "").strip():
        return None
    assert isinstance(genome.get("epoch_number"), int), "genome.json epoch_number must be an int"
    return f"epoch-{genome['epoch_number']}:clearing-{obs.get('started') or 'unknown'}"


def first_pick(site):
    """Andre's newest pick from references/picks/picks.jsonl, or None. No file,
    no line, or only None answers mean no pick. An unreadable line raises."""
    path = os.path.join(site, "references", "picks", "picks.jsonl")
    if not os.path.isfile(path):
        return None
    pick = None
    with open(path, encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            row = json.loads(line)
            assert isinstance(row, dict), "picks.jsonl line is not an object"
            slot = row.get("slot")
            if isinstance(slot, int) and not isinstance(slot, bool) and slot >= 1 \
                    and str(row.get("choice", "")).lower() != "none":
                pick = row
    return pick


def capture_reference_pictures(site):
    """Scene pictures for reference notes that have none. Never stops the run."""
    if os.environ.get("ANDREMACEDO_CAPTURE_DISABLE") == "1":
        log("reference picture capture disabled by ANDREMACEDO_CAPTURE_DISABLE=1")
        return
    try:
        import capture_references
        capture_references.capture_missing(site, log)
    except Exception as e:  # noqa: BLE001 — one plain line, the run goes on
        log(f"could not capture reference pictures: {e}; the run goes on without them")


def append_ledger(site, entry):
    with open(os.path.join(site, "state", LEDGER), "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


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
    # validate-build (INV-18) checks the experiment pages that differ from git HEAD
    # and refuses a tree that is not its own git top level, so each candidate tree
    # gets a baseline commit of the live site; only its own new pages count.
    for argv in (["init", "-q"], ["add", "-A"],
                 ["-c", "user.name=epoch-fanout", "-c", "user.email=epoch-fanout@localhost",
                  "commit", "-q", "--no-verify", "-m", "candidate baseline"]):
        subprocess.run(["git", "-C", dest] + argv, check=True, capture_output=True, timeout=300)
    nm = os.path.join(site, "node_modules")
    if os.path.isdir(nm):
        os.symlink(nm, os.path.join(dest, "node_modules"))
    gm = os.path.join(dest, "state", "generation-meta.json")
    if os.path.exists(gm):
        os.remove(gm)       # a stale record must never satisfy a candidate's gate
    return tree_hashes(dest, INSTALL_DIRS, INSTALL_FILES)


def fanout_brief(slot, total, prior, tree, fresh=False):
    refs = os.path.join(tree, "references")
    passes = os.path.join(tree, PASSES_DIR)
    lines = ["", "", f"## WEEKLY CANDIDATE {slot} OF {total}", "",
             f"This run builds {total} clearly different versions of the page. Andre sees "
             "a desktop and a phone screenshot of each version that passes the gates, and "
             "picks one or none. Only his pick goes live.",
             "", "The job, from SOUL.md: within 10 seconds a stranger understands who Andre "
             "is and what he does, and wants to contact him. The self-rebuilding AI is the "
             "twist, not the subject.",
             ""] + (fresh_lines(slot) if fresh else [
             "Start from the live index.html in your tree. It is Andre's last pick. Evolve "
             "it; do not start over."]) + [
             "", f"The target: read {refs}/README.md and every note in {refs}/, and look at "
             f"the screenshots in {refs}/ and {refs}/picks/. Both critics score your page "
             "against them. Learn their techniques; copy nothing.",
             "", "Your direction for this candidate: " + (FRESH_DIRECTIONS if fresh else DIRECTIONS)[
                 (slot - 1) % len(FRESH_DIRECTIONS if fresh else DIRECTIONS)],
             "", "THE FORM (SOUL.md, The form) supersedes every instruction above about "
             "sections, bands, the hero-then-sections layout, the archive or experiments grid, "
             "the Consciousness Stream, scroll hints and the visit counter. The home page is "
             "one full-screen directed piece: a short run of scenes, one idea per scene, very "
             "few words, designed transitions, it plays itself, and scroll, arrow keys or a tap "
             "step through it. The first scene says who Andre is and what his two companies do. "
             "Name, role and email (the data-floor elements) stay on screen in every scene. "
             "Experiments and other bands sit behind one link in the last scene. The swarm "
             "blocks of the frozen substrate are optional: leave them out unless the piece "
             "uses them. Type stays sans-serif or monospace only; ignore any advice above to "
             "pair a serif.",
             "", f"PASSES (at least {MIN_PASSES}, each one recorded, or the candidate is not "
             "offered). Pass 1: build the piece and pass the gates. Then, for every pass N "
             f"from 1: render your scenes with `python3 {tree}/scripts/capture_references.py "
             f"scenes --dir {tree} --out {passes}/pass-N`, Read those pictures beside the "
             f"reference pictures in {refs}/ (when there are some), name your weakest scene "
             "and why, and rebuild that scene in the next pass. Re-run the gates after the "
             f"last rebuild. Record every pass in generation-meta.json `passes`: a list of "
             '{"pass": N, "weakest_scene": "...", "fix": "..."}, one entry per rendered '
             "pass folder.",
             "", "Write a one-line plain summary of your version in generation-meta.json "
             "`summary`: Andre reads it next to the screenshot.",
             "", "Everything in the protocol above still binds you: gates, craft judge, "
             "the verdict line, the files you may write."]
    if prior:
        lines += ["", "Earlier candidates in this run already chose the following. Make "
                  "yours CLEARLY different from them:"]
        for p in prior:
            lines.append(f"- candidate {p['slot']}: idea {p.get('idea')!r}; {p.get('summary')!r}; "
                         f"visual strategy {p.get('visual_strategy')!r}")
    return "\n".join(lines)


def fresh_lines(slot):
    return [
        "FRESH START. Andre has not picked a version yet, so nothing comes from the live "
        "page: not its concept, palette, layout or motif. Ignore the epoch, obsession, "
        "palette, section manifest and live index.html described above, and do not reuse "
        "them. Keep only the frozen substrate, the visitor floor and the rules in SOUL.md. "
        "Write a new index.html from a blank page. Knotted strings (khipu, knots, cords) "
        "are banned in every form. The live screenshots are left out on purpose; skip the "
        "mobile sub-gate on them.",
        "",
        "Name your idea before you build: your first action is to write "
        "state/generation-meta.json with one field `idea`, one plain line saying what the "
        "piece is. Keep that `idea` in the full record you write later. It must differ "
        "from every earlier candidate's idea listed below."]


def candidate_input(input_jsonl, out_path, site, cand, brief, fresh=False):
    """Rewrite the runner's stream-json message for one candidate: every site path
    in the text points at the candidate tree, the brief is appended. Images are
    kept, except on a fresh start, which must not see the live page."""
    site_real = os.path.realpath(site)
    with open(input_jsonl, encoding="utf-8") as f:
        msg = json.loads(f.readline())
    content = msg["message"]["content"]
    if fresh:
        content[:] = [p for p in content if p.get("type") != "image"]
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


def last_result(out_path):
    last = None
    try:
        with open(out_path, errors="replace") as f:
            for line in f:
                try:
                    o = json.loads(line)
                except ValueError:
                    continue
                if isinstance(o, dict) and o.get("type") == "result":
                    last = o
    except FileNotFoundError:
        return None
    return last


def parse_result(out_path):
    """(event|None, usage, verdict) from the last result event, as runner.sh parses it."""
    last = last_result(out_path)
    if not last or last.get("is_error"):
        return None, (last or {}).get("usage") or {}, ""
    text = (last.get("result") or "").strip()
    verdict = ""
    for line in reversed([l.strip() for l in text.splitlines() if l.strip()]):
        if line.startswith("GENERATION_VERDICT:"):
            verdict = line
            break
    return last, last.get("usage") or {}, verdict


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
    the candidate's index.html; stops at the first failure. Returns (gates, shots)."""
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
    for name, argv in (("mobile_gate", ["node", os.path.join(sd, "mobile-gate.js"), index]),
                       ("contrast", ["node", os.path.join(sd, "audit-contrast.js"), "local", index]),
                       ("visitor_floor", ["node", os.path.join(sd, "visitor-floor.js"), index])):
        gates.append(run_gate(name, argv, env, log_path))
        if not gates[-1]["passed"]:
            return gates, None
    return gates, (desk, mob)


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
    return gate("generation_meta", True, str(meta.get("summary") or "")[:120]), meta


def passes_gate(cand, meta):
    """At least MIN_PASSES recorded passes, each with a weakest scene, a fix and its
    own folder of scene pictures under state/passes/pass-N."""
    passes = meta.get("passes")
    if not isinstance(passes, list) or len(passes) < MIN_PASSES:
        n = len(passes) if isinstance(passes, list) else 0
        return gate("passes", False, f"{n} recorded passes, need {MIN_PASSES}")
    for i, p in enumerate(passes, 1):
        if not (isinstance(p, dict) and str(p.get("weakest_scene") or "").strip()
                and str(p.get("fix") or "").strip()):
            return gate("passes", False, f"pass {i} names no weakest scene and fix")
        shots = os.path.join(cand, PASSES_DIR, f"pass-{i}")
        if not (os.path.isdir(shots) and any(f.endswith(".jpg") and os.path.getsize(os.path.join(shots, f)) > 0
                                             for f in os.listdir(shots))):
            return gate("passes", False, f"pass {i} has no scene pictures in {PASSES_DIR}/pass-{i}")
    return gate("passes", True, f"{len(passes)} passes")


def fresh_gate(cand, meta, prior_ideas):
    """Before a first pick: a named idea unlike earlier candidates', no knotted strings."""
    idea = str(meta.get("idea") or "").strip()
    if not idea:
        return gate("fresh_start", False, "no idea named in generation-meta.json")
    if idea.lower() in {str(i).strip().lower() for i in prior_ideas if i}:
        return gate("fresh_start", False, f"same idea as an earlier candidate: {idea!r}")
    with open(os.path.join(cand, "index.html"), encoding="utf-8", errors="replace") as f:
        hit = BANNED_MOTIF.search(f.read())
    if hit or BANNED_MOTIF.search(idea):
        return gate("fresh_start", False, f"uses the banned knotted-string motif ({(hit or BANNED_MOTIF.search(idea)).group(0)!r})")
    return gate("fresh_start", True, idea[:120])


def judge(site, desk, mob, json_out, judge_path=None):
    """craft-judge.py, both critics, fail-closed. Returns (gate, scores|None)."""
    judge_path = judge_path or os.path.join(site, "scripts", "craft-judge.py")
    try:
        wall = int(subprocess.run(["python3", judge_path, "--print-wall-budget"],
                                  capture_output=True, text=True, timeout=30,
                                  check=True).stdout.strip())
    except Exception as e:  # noqa: BLE001 — unreadable budget is fail-closed
        return gate("craft_judge", False, f"judge wall budget unreadable: {e}"), None
    assert wall > 0, "judge wall budget must be positive"
    argv = ["python3", judge_path, "--desktop", desk, "--mobile", mob, "--margin", "7.3",
            "--wall-budget", str(wall), "--json-out", json_out, "--quiet"]
    if os.path.exists(json_out):
        os.remove(json_out)
    rc = run_bounded(argv, None, dict(os.environ), wall + 30,
                     subprocess.DEVNULL, subprocess.DEVNULL)
    try:
        v = load_json(json_out)
    except (OSError, ValueError):
        return gate("craft_judge", False, f"judge exit {rc}, no verdict", rc), None
    crit = v.get("critics") or {}
    if rc not in (0, 1) or not all("overall" in (crit.get(k) or {}) for k in ("A", "B")):
        return gate("craft_judge", False, f"judge exit {rc}: {str(v.get('error', ''))[:300]}", rc), None
    scores = {"verdict": v.get("verdict"), "gate_rule": v.get("gate_rule"), "reason": v.get("reason"),
              "craft_min": min(float(crit["A"]["overall"]), float(crit["B"]["overall"])),
              "critics": {k: {"model": crit[k].get("model"), "overall": crit[k].get("overall"),
                              "findings": (crit[k].get("findings") or [])[:5]} for k in ("A", "B")}}
    return gate("craft_judge", rc == 0, f"{v.get('verdict')} ({v.get('reason')})", rc), scores


def gate_candidate(site, cand, shots, helper_exit, verdict, log_path, rundir, slot, judge_path,
                   fresh=False, prior_ideas=()):
    """Every gate in order, first failure wins. Returns (gates, shots|None, meta, scores)."""
    gates = [gate("session_verdict",
                  helper_exit == 0 and verdict.startswith("GENERATION_VERDICT: OK"),
                  f"helper exit {helper_exit}; {verdict or 'no verdict'}", helper_exit)]
    if not gates[-1]["passed"]:
        return gates, None, None, None
    g, meta = meta_gate(cand)
    gates.append(g)
    if not g["passed"]:
        return gates, None, meta, None
    gates.append(passes_gate(cand, meta))
    if not gates[-1]["passed"]:
        return gates, None, meta, None
    if fresh:
        gates.append(fresh_gate(cand, meta, prior_ideas))
        if not gates[-1]["passed"]:
            return gates, None, meta, None
    gates.append(protected_gate(site, cand))
    if not gates[-1]["passed"]:
        return gates, None, meta, None
    more, shot_paths = deterministic_gates(site, cand, shots, log_path)
    gates += more
    if shot_paths is None:
        return gates, None, meta, None
    g, scores = judge(site, shot_paths[0], shot_paths[1],
                      os.path.join(rundir, f"judge-cand{slot}.json"), judge_path)
    gates.append(g)
    return gates, (shot_paths if g["passed"] else None), meta, scores


def count_tokens(site, usage):
    """The runner stops after an offer, so the monthly budget is charged here."""
    path = os.path.join(site, "state", "agent-state.json")
    s = load_json(path)
    s["monthly_tokens_used"] = int(s.get("monthly_tokens_used", 0)) + sum(
        int(usage.get(k) or 0) for k in ("input_tokens", "cache_creation_input_tokens", "output_tokens"))
    tmp = path + ".fanout-tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(s, f, indent=2, ensure_ascii=False)
    os.replace(tmp, path)


def candidate_record(c):
    return {k: c.get(k) for k in ("slot", "helper_exit", "verdict", "summary", "idea", "passes", "topic",
                                  "visual_strategy", "passed", "gates", "scores", "elapsed_s")}


# ── run ──────────────────────────────────────────────────────────────
def cmd_run(args):
    site = os.path.abspath(args.site)
    pulse = os.environ.get("PULSE_TYPE", args.pulse)
    if pulse not in ("weekly", "event"):
        log(f"pulse {pulse!r} is not a pick pulse")
        return NOT_A_PICK_PULSE
    if site_pick.install(site, args.output) == 0:
        return 0
    if os.environ.get("ANDREMACEDO_FANOUT_DISABLE") == "1":
        log("disabled by ANDREMACEDO_FANOUT_DISABLE=1")
        return NOT_A_PICK_PULSE
    waiting = site_pick.open_offer()
    if waiting is not None:
        log(f"offer {waiting['run_id']} still waits for Andre (until {waiting['expires_at']}); "
            "nothing built")
        return NOTHING_TO_INSTALL
    assert args.wall > 0, "per-candidate wall must be positive"
    t0 = time.time()
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    rundir = os.path.join(os.path.abspath(os.path.expanduser(args.root)), run_id)
    os.makedirs(rundir)
    append_ledger(site, {"run_id": run_id, "event": "started", "at": utcnow(),
                         "candidates_planned": CANDIDATES, "rundir": rundir})
    log(f"weekly candidates start: {CANDIDATES}; rundir {rundir}")
    cands, usage_total = [], {"input_tokens": 0, "cache_creation_input_tokens": 0,
                              "cache_read_input_tokens": 0, "output_tokens": 0}

    def finish(outcome, **extra):
        count_tokens(site, usage_total)
        append_ledger(site, {"run_id": run_id, "event": "finished", "at": utcnow(), "outcome": outcome,
                             "elapsed_s": round(time.time() - t0, 1), "usage_total": usage_total,
                             "candidates": [candidate_record(c) for c in cands], **extra})
        for c in cands:
            shutil.rmtree(c["tree"], ignore_errors=True)
        log(f"weekly candidates {outcome}: " + " ".join(f"{k}={v}" for k, v in extra.items()))

    pre = subprocess.run(["bash", os.path.join(site, "scripts", "verify-frozen-substrate.sh")],
                         capture_output=True, text=True)
    if pre.returncode != 0:
        tail = pre.stdout.strip().splitlines()[-1] if pre.stdout.strip() else "no output"
        finish("not_built", reason=f"verify-frozen-substrate.sh exit {pre.returncode}: {tail}")
        return NOTHING_TO_INSTALL

    pick = first_pick(site)
    fresh = pick is None
    log("no pick yet: every candidate starts from its own idea" if fresh
        else f"evolving from Andre's pick of run {pick.get('run_id')}")
    capture_reference_pictures(site)
    session = os.path.join(site, "scripts", "generation-session.sh")
    prior = []
    for slot in range(1, CANDIDATES + 1):
        ct = time.time()
        cdir = os.path.join(rundir, f"cand{slot}")
        tree = os.path.join(cdir, "tree")
        os.makedirs(cdir)
        baseline = make_candidate_tree(site, tree)
        jsonl = os.path.join(cdir, "input.jsonl")
        out = os.path.join(cdir, "helper-output.jsonl")
        candidate_input(args.input_jsonl, jsonl, site, tree, fanout_brief(slot, CANDIDATES, prior, tree, fresh),
                        fresh)
        env = dict(os.environ, INPUT_JSONL=jsonl, OUTPUT_FILE=out, BUILD_TREE=tree,
                   PULSE_TYPE=pulse, TELOS_AGENT=f"andremacedo-creative:weekly-c{slot}")
        with open(os.path.join(cdir, "session.log"), "w") as sl:
            hexit = run_bounded(["bash", session, "agentic"], tree, env, args.wall, sl, sl)
        event, usage, verdict = parse_result(out)
        for k in usage_total:
            usage_total[k] += int(usage.get(k) or 0)
        gates, shots, meta, scores = gate_candidate(
            site, tree, os.path.join(cdir, "shots"), hexit, verdict,
            os.path.join(cdir, "gates.log"), rundir, slot, args.judge,
            fresh, [p.get("idea") for p in prior])
        meta = meta or {}
        c = {"slot": slot, "tree": tree, "baseline": baseline,
             "now": tree_hashes(tree, INSTALL_DIRS, INSTALL_FILES),
             "helper_exit": hexit, "verdict": verdict, "gates": gates, "shots": shots,
             "scores": scores, "result_event": event,
             "passed": shots is not None and all(g["passed"] for g in gates),
             "summary": str(meta.get("summary") or "")[:200] or None,
             "idea": str(meta.get("idea") or "")[:200] or None,
             "passes": len(meta.get("passes") or []) if isinstance(meta.get("passes"), list) else 0,
             "topic": (meta.get("obsession_update") or {}).get("topic"),
             "visual_strategy": meta.get("visual_strategy"),
             "elapsed_s": round(time.time() - ct, 1)}
        cands.append(c)
        if c["summary"] or c["visual_strategy"] or c["idea"]:
            prior.append({"slot": slot, "idea": c["idea"], "summary": c["summary"],
                          "visual_strategy": c["visual_strategy"]})
        failed = next((g for g in gates if not g["passed"]), None)
        log(f"candidate {slot}: " + ("passed" if c["passed"] else
            f"out at {failed['name']} ({failed['detail']})") + f" in {c['elapsed_s']}s")

    passing = [c for c in cands if c["passed"]]
    if not passing:
        finish("none_passed")
        return NOTHING_TO_INSTALL
    o = site_pick.offer(site, run_id, passing)
    finish("offered", offer_status=o["status"], offered=[c["slot"] for c in passing], fresh_start=fresh)
    return NOTHING_TO_INSTALL


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    rp = sub.add_parser("run")
    rp.add_argument("--site", required=True)
    rp.add_argument("--input-jsonl", required=True)
    rp.add_argument("--output", required=True)
    rp.add_argument("--wall", type=int, required=True, help="per-candidate session wall, seconds")
    rp.add_argument("--pulse", default="weekly")
    rp.add_argument("--root", default=os.environ.get("ANDREMACEDO_FANOUT_ROOT",
                                                     "~/.telos/tmp/andremacedo-fanout"))
    rp.add_argument("--judge", default=None, help="craft judge path (test seam)")
    args = ap.parse_args(argv)
    return cmd_run(args)


if __name__ == "__main__":
    sys.exit(main())
