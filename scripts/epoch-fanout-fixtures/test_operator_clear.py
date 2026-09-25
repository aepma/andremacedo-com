#!/usr/bin/env python3
"""Fixture test for epoch-operator-clear.py and the fan-out trigger it opens.

No model calls and no process listing: the runner check goes through
stub-pgrep.sh. Each case runs the command on a scratch site holding a copy of
this repo's state files; when that state is already a clearing, the copy is
given a live obsession first, as test_orchestration.py does.

Cases:
  1. Before: the fan-out trigger is false on a live epoch.
  2. Refusals write nothing: missing, blank and over-long reason; a runner.sh
     going; a process check that cannot answer. The check targets this site's
     runner path with its dots escaped.
  3. The clear: exit 0; the epoch is buried through bury_epoch (past_epochs,
     graveyard, epoch_number + 1, active_obsession.topic empty) with transition
     "operator"; the epitaph says Andre ended it for a new model and quotes the
     reason; one review-log entry with verdict operator_clear and the reason;
     the transition file has kind operator; genome epoch/epoch_started and the
     generation counter are untouched; exactly those four files changed.
  4. After: the fan-out trigger is true for opening epoch-(N+1):clearing-<today>,
     false for a daily pulse, and false once that opening is in the ledger.
  5. A second clear refuses (no live epoch, exit 3) and writes nothing.
Fail-closed: exit 1 if ANY assertion fails.
"""
import hashlib, importlib.util, json, os, shutil, subprocess, sys, tempfile
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.dirname(HERE)
REPO = os.path.dirname(SCRIPTS)
spec = importlib.util.spec_from_file_location("epoch_fanout", os.path.join(SCRIPTS, "epoch_fanout.py"))
ep = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ep)

COMMAND = os.path.join(SCRIPTS, "epoch-operator-clear.py")
STATE_FILES = ("agent-state.json", "genome.json", "craft-history.jsonl",
               "epoch-review-log.jsonl", "epoch-transition-latest.json")
WRITTEN = {"agent-state.json", "genome.json", "epoch-review-log.jsonl",
           "epoch-transition-latest.json"}
REASON = "Handing andremacedo.com to a new generation model; let it author its own epoch."
RESULTS = []


def check(name, cond, detail=""):
    RESULTS.append((name, bool(cond)))
    print(("PASS  " if cond else "FAIL  ") + name + (f"  [{detail}]" if detail and not cond else ""))


def snapshot(site):
    """{relpath: sha256} of every file under the site."""
    out = {}
    for dirpath, _dirs, files in os.walk(site):
        for fn in files:
            p = os.path.join(dirpath, fn)
            out[os.path.relpath(p, site)] = hashlib.sha256(open(p, "rb").read()).hexdigest()
    return out


def changed(before, after):
    return sorted(k for k in set(before) | set(after) if before.get(k) != after.get(k))


def make_site(root, name):
    site = os.path.join(root, name)
    os.makedirs(os.path.join(site, "state"))
    for fn in STATE_FILES:
        src = os.path.join(REPO, "state", fn)
        if os.path.isfile(src):
            shutil.copy2(src, os.path.join(site, "state", fn))
    sp = os.path.join(site, "state", "agent-state.json")
    st = json.load(open(sp, encoding="utf-8"))
    if not ((st.get("active_obsession") or {}).get("topic") or "").strip():
        st["active_obsession"] = {"topic": "fixture live obsession", "started": "2026-09-17",
                                  "rationale": "fixture"}
        json.dump(st, open(sp, "w", encoding="utf-8"), indent=2, ensure_ascii=False)
    return site


def run(site, root, *args, pgrep_exit="1", reason=REASON):
    env = dict(os.environ, ANDREMACEDO_PGREP=os.path.join(HERE, "stub-pgrep.sh"),
               STUB_PGREP_EXIT=pgrep_exit, STUB_PGREP_TRACE=os.path.join(root, "pgrep-trace.txt"),
               PYTHONDONTWRITEBYTECODE="1")
    argv = ["python3", COMMAND, "--site", site] + ([] if reason is None else ["--reason", reason])
    p = subprocess.run(argv + list(args), env=env, capture_output=True, text=True)
    return p.returncode, p.stdout + p.stderr


def main():
    root = tempfile.mkdtemp(prefix="operator-clear-test.", dir=os.environ.get("TMPDIR"))
    print(f"scratch: {root}")
    try:
        site = make_site(root, "site")
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        g0 = json.load(open(os.path.join(site, "state", "genome.json"), encoding="utf-8"))
        s0 = json.load(open(os.path.join(site, "state", "agent-state.json"), encoding="utf-8"))
        n, topic = g0["epoch_number"], s0["active_obsession"]["topic"].strip()
        model = subprocess.run(["bash", os.path.join(SCRIPTS, "generation-session.sh"), "model"],
                               capture_output=True, text=True, check=True).stdout.strip()

        # ── case 1: before ─────────────────────────────────────────
        ok, reason, _ = ep.should_fanout(site, "weekly")
        check("case1: trigger false on the live epoch", not ok and "live" in reason, reason)

        # ── case 2: refusals write nothing ─────────────────────────
        before = snapshot(site)
        for label, kwargs, want in (
                ("missing reason", {"reason": None}, 2),
                ("blank reason", {"reason": "  \n\t "}, 2),
                ("reason over 600 characters", {"reason": "x" * 601}, 2),
                ("runner.sh going", {"pgrep_exit": "0"}, 4),
                ("process check cannot answer", {"pgrep_exit": "2"}, 4)):
            rc, out = run(site, root, **kwargs)
            check(f"case2: {label} -> exit {want}, nothing written",
                  rc == want and snapshot(site) == before, f"exit {rc}: {out[-300:]}")
        trace = open(os.path.join(root, "pgrep-trace.txt")).read().splitlines()
        want_pat = os.path.join(site, "scripts", "runner.sh").replace(".", "[.]")
        check("case2: the process check targets this site's runner.sh, dots escaped",
              trace and all(t == f"-f {want_pat}" for t in trace), str(trace[:2]))

        # ── case 3: the clear ──────────────────────────────────────
        rc, out = run(site, root)
        check("case3: operator clear exits 0", rc == 0, out[-600:])
        after = snapshot(site)
        check("case3: exactly the four state files changed",
              {os.path.basename(k) for k in changed(before, after)} == WRITTEN
              and set(before) <= set(after)
              and set(after) - set(before) <= {os.path.join("state", f) for f in WRITTEN},
              str(changed(before, after)))
        g1 = json.load(open(os.path.join(site, "state", "genome.json"), encoding="utf-8"))
        s1 = json.load(open(os.path.join(site, "state", "agent-state.json"), encoding="utf-8"))
        dead = (g1.get("past_epochs") or [{}])[-1]
        check("case3: epoch_number advanced by one", g1["epoch_number"] == n + 1)
        check("case3: active_obsession.topic emptied, clearing started today",
              s1["active_obsession"] == {"topic": "", "started": today, "rationale": ""},
              str(s1["active_obsession"]))
        check("case3: past_epochs records the dead epoch with transition operator",
              dead.get("number") == n and dead.get("obsession") == topic
              and dead.get("transition") == "operator" and dead.get("transition_reason") == REASON
              and dead.get("started") == s0["active_obsession"]["started"], str(dead)[:300])
        ep_text = dead.get("epitaph") or ""
        check("case3: epitaph says Andre ended it for a new model and quotes the reason",
              ep_text.startswith("Andre ended this epoch by operator decision, to hand the site "
                                 "to a new generation model")
              and f"({model})" in ep_text and ep_text.endswith(f"Andre's reason: {REASON}")
              and f'"{topic}"' in ep_text, ep_text[:300])
        grave = (g1.get("graveyard") or [{}])[-1]
        check("case3: graveyard entry for the epoch",
              grave.get("type") == "epoch" and grave.get("value") == f"Epoch {n}: {topic}"
              and grave.get("died_gen") == g0["generation"] and grave.get("epitaph") == ep_text)
        check("case3: genome epoch/epoch_started/generation and state version untouched",
              g1.get("epoch") == g0.get("epoch") and g1.get("epoch_started") == g0.get("epoch_started")
              and g1.get("generation") == g0.get("generation") and s1.get("version") == s0.get("version"))
        check("case3: nothing else in agent-state.json changed",
              {k: v for k, v in s1.items() if k != "active_obsession"}
              == {k: v for k, v in s0.items() if k != "active_obsession"})
        log = [json.loads(l) for l in open(os.path.join(site, "state", "epoch-review-log.jsonl"))
               if l.strip()]
        check("case3: review-log entry verdict operator_clear with the reason",
              log[-1].get("verdict") == "operator_clear" and log[-1].get("reasoning") == REASON
              and log[-1].get("epoch_number") == n and log[-1].get("epoch_topic") == topic,
              str(log[-1])[:300])
        tr = json.load(open(os.path.join(site, "state", "epoch-transition-latest.json"),
                            encoding="utf-8"))
        check("case3: transition file kind operator",
              tr.get("kind") == "operator" and tr.get("epoch_number") == n
              and tr.get("topic") == topic and tr.get("reason") == REASON, str(tr)[:300])

        # ── case 4: after ──────────────────────────────────────────
        ok, reason, key = ep.should_fanout(site, "weekly")
        check("case4: trigger true on the state the operator command produced",
              ok and key == f"epoch-{n + 1}:clearing-{today}", f"{ok} {reason}")
        ok_d, reason_d, _ = ep.should_fanout(site, "daily")
        check("case4: daily pulse still does not fan out", not ok_d, reason_d)
        ledger_site = os.path.join(root, "ledger-site")
        shutil.copytree(site, ledger_site)
        ep.append_ledger(ledger_site, {"opening_key": key, "event": "started"})
        ok_l, reason_l, _ = ep.should_fanout(ledger_site, "weekly")
        check("case4: cost bound holds: once fanned out, the opening does not fan out again",
              not ok_l and "already fanned out" in reason_l, reason_l)

        # ── case 5: second clear ───────────────────────────────────
        before2 = snapshot(site)
        rc2, out2 = run(site, root)
        check("case5: second clear refuses (no live epoch, exit 3), nothing written",
              rc2 == 3 and "no live epoch" in out2 and snapshot(site) == before2,
              f"exit {rc2}: {out2[-300:]}")
    finally:
        shutil.rmtree(root, ignore_errors=True)

    failed = [n for n, ok in RESULTS if not ok]
    print(f"\n{len(RESULTS) - len(failed)}/{len(RESULTS)} passed")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
