#!/usr/bin/env python3
"""Orchestration test for epoch_fanout.py with a stub generator and stub judge.

No model calls. The deterministic gates are the REAL ones (validate-build.py,
screenshot-local.sh, mobile-gate.js, audit-contrast.js, visitor-floor.js) run
against a scratch copy of this repo, so this needs the playwright venv and
node_modules that the production gates need.

Cases:
  1. 4 candidates, candidate 2 fails validate-build (frozen swarm panel renamed):
     exit 0; 2 is out at validate_build before scoring; winner is candidate 3
     (highest min(A, B) combined, although candidate 1 has the single highest
     critic score); site index.html and generation-meta.json are candidate 3's;
     losers 1 and 4 archived as unshipped candidates with scores; the result
     event carries usage summed over all 4; ledger records started + finished.
  2. Same opening again: no fan-out (exit 3), cost bound.
  3. Only 1 survivor: exit 3, site untouched, ledger outcome fallback. The
     runner's own fan-out block (extracted verbatim from runner.sh) then runs the
     single attempt through generation-session.sh.
  4. A critic unobtainable on a survivor: exit 3, fallback, site untouched.
  5. Live epoch (obsession set): no fan-out.
Fail-closed: exit 1 if ANY assertion fails.
"""
import hashlib, importlib.util, json, os, shutil, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.dirname(HERE)
REPO = os.path.dirname(SCRIPTS)
spec = importlib.util.spec_from_file_location("epoch_fanout", os.path.join(SCRIPTS, "epoch_fanout.py"))
ep = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ep)

RESULTS = []


def check(name, cond, detail=""):
    RESULTS.append((name, bool(cond)))
    print(("PASS  " if cond else "FAIL  ") + name + (f"  [{detail}]" if detail and not cond else ""))


def sha(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


def make_site(root, name, clearing=True):
    site = os.path.join(root, name)
    shutil.copytree(REPO, site, symlinks=True, ignore=ep.copy_ignore(REPO))
    nm = os.path.realpath(os.path.join(REPO, "node_modules"))
    assert os.path.isdir(nm), "node_modules required for the real gates"
    os.symlink(nm, os.path.join(site, "node_modules"))
    sp = os.path.join(site, "state", "agent-state.json")
    st = json.load(open(sp))
    st["active_obsession"] = ({"topic": "", "started": "2026-09-14", "rationale": ""} if clearing
                              else {"topic": "live obsession", "started": "2026-09-17", "rationale": ""})
    json.dump(st, open(sp, "w"), indent=2)
    for stale in (os.path.join(site, "state", "generation-meta.json"), ep.ledger_path(site)):
        if os.path.exists(stale):
            os.remove(stale)
    return site


def make_input(root, site):
    p = os.path.join(root, f"input-{os.path.basename(site)}.jsonl")
    msg = {"type": "user", "message": {"role": "user", "content": [
        {"type": "text", "text": f"Write your COMPLETE new index.html to {site}/index.html\n"
                                 f"python3 {site}/scripts/validate-build.py {site}/index.html"}]}}
    open(p, "w").write(json.dumps(msg) + "\n")
    return p


def env_for(root, site, **extra):
    e = dict(os.environ, ANDREMACEDO_HELPER=os.path.join(HERE, "stub-helper.sh"),
             STUB_SOURCE_INDEX=os.path.join(REPO, "index.html"), STUB_SITE=site,
             STUB_TRACE=os.path.join(root, f"trace-{os.path.basename(site)}.jsonl"),
             PULSE_TYPE="weekly", PYTHONDONTWRITEBYTECODE="1")
    e.pop("ANDREMACEDO_FANOUT_DISABLE", None)
    e.update(extra)
    return e


def run_fanout(root, site, env, out):
    argv = ["python3", os.path.join(site, "scripts", "epoch_fanout.py"), "run", "--site", site,
            "--input-jsonl", make_input(root, site), "--output", out, "--wall", "120",
            "--root", os.path.join(root, "fanout-" + os.path.basename(site)),
            "--judge", os.path.join(HERE, "stub_judge.py")]
    p = subprocess.run(argv, env=env, capture_output=True, text=True)
    open(os.path.join(root, f"log-{os.path.basename(site)}.txt"), "a").write(p.stdout + p.stderr)
    return p.returncode, p.stdout + p.stderr


def ledger(site):
    return [json.loads(l) for l in open(ep.ledger_path(site)) if l.strip()]


def runner_block():
    """The fan-out + single-attempt block, verbatim from runner.sh."""
    lines = open(os.path.join(SCRIPTS, "runner.sh")).read().split("\n")
    start = next(i for i, l in enumerate(lines) if l.startswith("SESSION_WALL_CEILING="))
    hx = next(i for i in range(start, len(lines)) if lines[i].strip() == "HELPER_EXIT=$?")
    end = next(i for i in range(hx, len(lines)) if lines[i] == "set -e")
    return "\n".join(lines[start:end + 1])


def main():
    root = tempfile.mkdtemp(prefix="fanout-test.", dir=os.environ.get("TMPDIR"))
    print(f"scratch: {root}")
    try:
        # ── case 1 ──────────────────────────────────────────────────
        site = make_site(root, "site1")
        idx_before = sha(os.path.join(site, "index.html"))
        man_before = len(json.load(open(os.path.join(site, "archive-screenshots", "manifest.json"))))
        out = os.path.join(root, "out1.jsonl")
        rc, logtxt = run_fanout(root, site, env_for(root, site, STUB_FAIL_GATE="2"), out)
        check("case1: fan-out exits 0 (winner installed)", rc == 0, logtxt[-800:])
        fin = [e for e in ledger(site) if e.get("event") == "finished"]
        check("case1: ledger has started + finished", len(ledger(site)) == 2 and len(fin) == 1)
        f = fin[0] if fin else {}
        cands = {c["slot"]: c for c in f.get("candidates", [])}
        check("case1: 4 candidates recorded", f.get("candidate_count") == 4 and len(cands) == 4)
        c2 = cands.get(2, {})
        check("case1: candidate 2 excluded at validate_build",
              c2.get("survived") is False and any(g["name"] == "validate_build" and not g["passed"]
                                                  for g in c2.get("gates", [])))
        check("case1: candidate 2 never scored", c2.get("scores") is None)
        check("case1: winner is candidate 3 (min-of-critics), not 1 (max single critic)",
              f.get("winner") == 3, str(f.get("winner")))
        check("case1: ranking 3,4,1", f.get("ranking") == [3, 4, 1], str(f.get("ranking")))
        check("case1: every scored candidate recorded both critics and tone",
              all(cands[s]["scores"]["critics"][k]["tone"] is not None for s in (1, 3, 4) for k in "AB"))
        html = open(os.path.join(site, "index.html")).read()
        check("case1: site index.html is candidate 3's", "<!-- stub candidate 3 -->" in html
              and sha(os.path.join(site, "index.html")) != idx_before)
        meta = json.load(open(os.path.join(site, "state", "generation-meta.json")))
        check("case1: generation-meta.json is candidate 3's",
              meta["obsession_update"]["topic"] == "stub obsession 3")
        ev = [json.loads(l) for l in open(out) if l.strip()]
        check("case1: result event verdict OK with usage summed over 4 candidates",
              len(ev) == 1 and ev[0]["result"].endswith("GENERATION_VERDICT: OK")
              and ev[0]["usage"]["input_tokens"] == 400 and ev[0]["usage"]["output_tokens"] == 40)
        man = json.load(open(os.path.join(site, "archive-screenshots", "manifest.json")))
        added = man[man_before:]
        check("case1: losers 1 and 4 archived as unshipped candidates",
              sorted(e["candidate"] for e in added) == [1, 4]
              and all(e["unshipped_candidate"] and e["commit"] is None for e in added))
        check("case1: archived entries carry scores and screenshots on disk",
              all(e["scores"] and os.path.isfile(os.path.join(site, "archive-screenshots", e["screenshot"]))
                  and os.path.isfile(os.path.join(site, "archive-screenshots", e["screenshot_mobile"]))
                  for e in added))
        trace = [json.loads(l) for l in open(os.path.join(root, "trace-site1.jsonl"))]
        check("case1: every candidate prompt points at its own tree, not the site",
              len(trace) == 4 and all(t["cwd_in_prompt"] and not t["site_in_prompt"] for t in trace))
        check("case1: later candidates are told what earlier ones chose; tone line present",
              not trace[0]["saw_prior"] and all(t["saw_prior"] for t in trace[1:])
              and all(t["saw_tone_line"] for t in trace))
        leftover = [d for d, _s, _f in os.walk(os.path.join(root, "fanout-site1"))
                    if os.path.basename(d) == "tree"]
        check("case1: scratch site copies removed after the run", not leftover, str(leftover[:2]))
        check("case1: elapsed time logged", isinstance(f.get("elapsed_s"), float)
              and "candidates=4 elapsed=" in logtxt)

        # ── case 2 ──────────────────────────────────────────────────
        rc2, log2 = run_fanout(root, site, env_for(root, site), os.path.join(root, "out2.jsonl"))
        check("case2: same opening does not fan out twice (exit 3)",
              rc2 == 3 and "already fanned out" in log2, log2[-300:])

        # ── case 3 ──────────────────────────────────────────────────
        site3 = make_site(root, "site3")
        idx3 = sha(os.path.join(site3, "index.html"))
        man3 = sha(os.path.join(site3, "archive-screenshots", "manifest.json"))
        rc3, log3 = run_fanout(root, site3, env_for(root, site3, STUB_FAIL_GATE="2,3,4"),
                               os.path.join(root, "out3.jsonl"))
        f3 = [e for e in ledger(site3) if e.get("event") == "finished"]
        check("case3: one survivor -> exit 3", rc3 == 3, log3[-500:])
        check("case3: ledger outcome fallback naming the survivor count",
              f3 and f3[0]["outcome"] == "fallback" and "only 1 candidate" in f3[0]["fallback_reason"])
        check("case3: site untouched (index.html, no generation-meta, manifest)",
              sha(os.path.join(site3, "index.html")) == idx3
              and not os.path.exists(os.path.join(site3, "state", "generation-meta.json"))
              and sha(os.path.join(site3, "archive-screenshots", "manifest.json")) == man3)
        check("case3: no survivor was scored", all(c["scores"] is None for c in f3[0]["candidates"]))

        # runner's own block: fan-out already recorded for site3 -> exit 3 -> single attempt.
        site3b = make_site(root, "site3b")
        env3b = env_for(root, site3b, STUB_FAIL_GATE="2,3,4")
        single_out = os.path.join(root, "out3b.jsonl")
        script = "\n".join([
            "set -euo pipefail",
            'log(){ echo "LOG: $*"; }', 'log_error(){ echo "ERR: $*"; }',
            'tmo(){ shift; "$@"; }',
            f'SCRIPT_DIR="{site3b}/scripts"; SITE_DIR="{site3b}"; PULSE_TYPE=weekly; AGENTIC=1',
            f'INPUT_JSONL_FILE="{make_input(root, site3b)}"; HELPER_OUTPUT_FILE="{single_out}"',
            f'LOG_FILE="{root}/runner-block.log"',
            f'export ANDREMACEDO_FANOUT_ROOT="{root}/fanout-site3b"',
            'cd "$SITE_DIR"   # runner.sh cds here before the session',
            runner_block(),
            'echo "FANOUT_EXIT=$FANOUT_EXIT HELPER_EXIT=$HELPER_EXIT"',
        ])
        # The block calls epoch_fanout.py without --judge; the stub judge is not
        # needed because fewer than 2 candidates survive before any judging.
        p = subprocess.run(["bash", "-c", script], env=env3b, capture_output=True, text=True)
        tail = (p.stdout + p.stderr)[-600:]
        check("case3: runner block falls back to the single attempt after fan-out exit 3",
              p.returncode == 0 and "FANOUT_EXIT=3 HELPER_EXIT=0" in p.stdout, tail)
        ev3 = [json.loads(l) for l in open(single_out) if l.strip()]
        check("case3: the single attempt ran (slot 'single') and wrote its own result",
              ev3 and ev3[0]["result"].startswith("stub single done")
              and "<!-- stub candidate single -->" in open(os.path.join(site3b, "index.html")).read())

        # ── case 4 ──────────────────────────────────────────────────
        site4 = make_site(root, "site4")
        idx4 = sha(os.path.join(site4, "index.html"))
        rc4, log4 = run_fanout(root, site4, env_for(root, site4, STUB_FAIL_GATE="2", STUB_JUDGE_ERROR="4"),
                               os.path.join(root, "out4.jsonl"))
        f4 = [e for e in ledger(site4) if e.get("event") == "finished"]
        check("case4: critic unobtainable -> exit 3 fallback, site untouched",
              rc4 == 3 and f4 and "critic unobtainable" in f4[0]["fallback_reason"]
              and sha(os.path.join(site4, "index.html")) == idx4, log4[-400:])

        # ── case 5 ──────────────────────────────────────────────────
        site5 = make_site(root, "site5", clearing=False)
        ok, reason, _ = ep.should_fanout(site5, "weekly")
        check("case5: live epoch does not fan out", not ok and "live" in reason, reason)
        ok_d, reason_d, _ = ep.should_fanout(site, "daily")
        check("case5: daily pulse does not fan out", not ok_d, reason_d)
    finally:
        shutil.rmtree(root, ignore_errors=True)

    failed = [n for n, ok in RESULTS if not ok]
    print(f"\n{len(RESULTS) - len(failed)}/{len(RESULTS)} passed")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
