#!/usr/bin/env python3
"""Orchestration test for the weekly pick flow: epoch_fanout.py + site_pick.py.

Andre's order of 2026-11-27: every weekly run builds three candidates, Andre
gets one Telegram message with a desktop and a mobile screenshot of each passing
candidate and buttons Pick 1..3 and None, and only a pick deploys.

No model call and no real Telegram: a stub generator stands in for each
session, a stub judge for the two critics, and a recording stub for
telegram-send.sh. The deterministic gates are the REAL ones (validate-build.py,
screenshot-local.sh, mobile-gate.js, audit-contrast.js, visitor-floor.js) run
against a scratch copy of this repo, and the contact sheet is really rendered.

Cases:
  1. 3 candidates, 2 fails validate-build: exit 4 (nothing to install); one
     sendPhoto plus one button edit (Pick 1, Pick 2, None); offer holds
     candidates 1 and 3; the site is untouched; tokens counted; prompts carry
     the job, the references and what earlier candidates chose.
  2. Same site again while the offer waits: exit 4, no session, no message.
  3. Tap "2": picked once (second tap refused), screenshots in references/picks,
     one site run queued; the next run installs candidate 3 (exit 0) with a
     zero-usage OK result event; the offer reads installed.
  4. A craft-gate SLOP and a critic error both fail their candidate; zero
     passing means exit 4, no message, no offer.
  5. Expiry: an unanswered offer past 48 hours expires on the daily pass, its
     buttons are removed, and a late tap changes nothing.
  6. None: recorded, nothing to install.
  7. runner.sh: the weekly block deploys nothing on exit 4, and the daily pulse
     calls site_pick.py daily.
Fail-closed: exit 1 if ANY assertion fails.
"""
import hashlib, importlib.util, json, os, shutil, subprocess, sys, tempfile, time

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.dirname(HERE)
REPO = os.path.dirname(SCRIPTS)
sys.dont_write_bytecode = True
sys.path.insert(0, SCRIPTS)
import epoch_fanout as ep  # noqa: E402
import site_pick as sp  # noqa: E402

RESULTS = []


def check(name, cond, detail=""):
    RESULTS.append((name, bool(cond)))
    print(("PASS  " if cond else "FAIL  ") + name + (f"  [{detail}]" if detail and not cond else ""))


def sha(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


def make_site(root, name):
    site = os.path.join(root, name)
    shutil.copytree(REPO, site, symlinks=True, ignore=ep.copy_ignore(REPO))
    nm = os.path.realpath(os.path.join(REPO, "node_modules"))
    assert os.path.isdir(nm), "node_modules required for the real gates"
    os.symlink(nm, os.path.join(site, "node_modules"))
    for stale in (os.path.join(site, "state", "generation-meta.json"),
                  os.path.join(site, "state", ep.LEDGER)):
        if os.path.exists(stale):
            os.remove(stale)
    # validate-build reads experiment pages left uncommitted; commit the copy.
    subprocess.run(["git", "init", "-q", site], check=True)
    subprocess.run(["git", "-C", site, "add", "-A"], check=True, capture_output=True)
    subprocess.run(["git", "-C", site, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm",
                    "base"], check=True, capture_output=True)
    return site


def make_input(root, site):
    p = os.path.join(root, f"input-{os.path.basename(site)}.jsonl")
    msg = {"type": "user", "message": {"role": "user", "content": [
        {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": "AA=="}},
        {"type": "text", "text": f"Write your COMPLETE new index.html to {site}/index.html\n"
                                 f"python3 {site}/scripts/validate-build.py {site}/index.html"}]}}
    open(p, "w").write(json.dumps(msg) + "\n")
    return p


def tg_stub(root):
    path = os.path.join(root, "stub-telegram-send.sh")
    open(path, "w").write(
        "#!/bin/bash\n"
        "python3 -c 'import json,sys; open(sys.argv[1],\"a\").write(json.dumps(sys.argv[2:])+\"\\n\")' "
        "\"$STUB_TG_LOG\" \"$@\"\n"
        "echo '{\"ok\":true,\"result\":{\"message_id\":42}}'\n")
    os.chmod(path, 0o755)
    return path


def env_for(root, site, **extra):
    e = dict(os.environ, ANDREMACEDO_HELPER=os.path.join(HERE, "stub-helper.sh"),
             STUB_SOURCE_INDEX=os.path.join(REPO, "index.html"), STUB_SITE=site,
             STUB_TRACE=os.path.join(root, f"trace-{os.path.basename(site)}.jsonl"),
             ANDREMACEDO_PICKS_ROOT=os.path.join(root, "picks-" + os.path.basename(site)),
             ANDREMACEDO_TG_SEND=tg_stub(root), STUB_TG_LOG=os.path.join(root, f"tg-{os.path.basename(site)}.jsonl"),
             PULSE_TYPE="weekly", PYTHONDONTWRITEBYTECODE="1", ANDREMACEDO_CAPTURE_DISABLE="1")
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


def lines(path):
    return [json.loads(l) for l in open(path) if l.strip()] if os.path.exists(path) else []


def tokens(site):
    return json.load(open(os.path.join(site, "state", "agent-state.json"))).get("monthly_tokens_used", 0)


def runner_block():
    """The weekly fan-out block, verbatim from runner.sh."""
    src = open(os.path.join(SCRIPTS, "runner.sh")).read().split("\n")
    start = next(i for i, l in enumerate(src) if l.startswith("PULSE_TYPE=\"$PULSE_TYPE\" python3 \"$SCRIPT_DIR/epoch_fanout.py\""))
    end = next(i for i in range(start, len(src)) if src[i] == "HELPER_EXIT=0")
    return "\n".join(src[start - 1:end + 1])


def main():
    root = tempfile.mkdtemp(prefix="pick-test.", dir=os.environ.get("TMPDIR"))
    print(f"scratch: {root}")
    try:
        # ── case 1 ──────────────────────────────────────────────────
        site = make_site(root, "site1")
        env = env_for(root, site, STUB_FAIL_GATE="2")
        sp.PICKS = env["ANDREMACEDO_PICKS_ROOT"]
        idx_before = sha(os.path.join(site, "index.html"))
        tok_before = tokens(site)
        rc, logtxt = run_fanout(root, site, env, os.path.join(root, "out1.jsonl"))
        check("case1: exit 4, nothing to install", rc == 4, logtxt[-800:])
        offers = sp.offers()
        o = offers[0] if offers else {}
        check("case1: one offer, status offered, message 42",
              len(offers) == 1 and o.get("status") == "offered" and o.get("message_id") == 42, str(o)[:300])
        check("case1: offer holds candidates 1 and 3 with index.html and the record",
              [c["slot"] for c in o.get("candidates", [])] == [1, 3]
              and all(set(sp.REQUIRED) <= set(c["changes"]) for c in o["candidates"]))
        tg = lines(env["STUB_TG_LOG"])
        check("case1: exactly one photo and one button edit", len(tg) == 2
              and tg[0][:3] == ["file", "sendPhoto", "2040883772"] and tg[1][0] == "markup", str(tg)[:300])
        mk = json.loads(tg[1][3]) if len(tg) == 2 else {}
        check("case1: buttons Pick 1, Pick 2, None",
              [b["text"] for b in mk.get("inline_keyboard", [[]])[0]] == ["Pick 1", "Pick 2", "None"])
        check("case1: the photo is the rendered contact sheet",
              len(tg) == 2 and tg[0][4].endswith("sheet.jpg") and os.path.getsize(tg[0][4]) > 0
              and "Nothing changes without your pick" in tg[0][5])
        check("case1: site untouched", sha(os.path.join(site, "index.html")) == idx_before
              and not os.path.exists(os.path.join(site, "state", "generation-meta.json")))
        check("case1: tokens of all three sessions counted", tokens(site) - tok_before == 330,
              str(tokens(site) - tok_before))
        trace = lines(env["STUB_TRACE"])
        check("case1: every prompt points at its own tree, carries the job and the references",
              len(trace) == 3 and all(t["cwd_in_prompt"] and not t["site_in_prompt"] and t["saw_job"]
                                      and t["saw_references"] for t in trace))
        check("case1: no pick yet -> every prompt is a fresh start under The form, without the live screenshots",
              len(trace) == 3 and all(t["saw_fresh"] and t["saw_form"] and not t["saw_images"] for t in trace))
        check("case1: candidates record their idea and three passes",
              all(c.get("idea") and c.get("passes") == 3 for c in (lines(os.path.join(site, "state", ep.LEDGER))
                                                                   or [{}])[-1].get("candidates", [{}])))
        check("case1: later candidates are told what earlier ones chose",
              not trace[0]["saw_prior"] and all(t["saw_prior"] for t in trace[1:]))
        led = lines(os.path.join(site, "state", ep.LEDGER))
        check("case1: ledger started + finished offered [1, 3]", len(led) == 2
              and led[1]["outcome"] == "offered" and led[1]["offered"] == [1, 3])
        left = [d for d, _s, _f in os.walk(os.path.join(root, "fanout-site1")) if os.path.basename(d) == "tree"]
        check("case1: scratch site copies removed", not left, str(left[:2]))

        # ── case 2 ──────────────────────────────────────────────────
        rc2, log2 = run_fanout(root, site, env, os.path.join(root, "out2.jsonl"))
        check("case2: open offer -> exit 4, nothing built, nothing sent",
              rc2 == 4 and "still waits" in log2 and len(lines(env["STUB_TRACE"])) == 3
              and len(lines(env["STUB_TG_LOG"])) == 2, log2[-300:])

        # ── case 3 ──────────────────────────────────────────────────
        queued, edits = [], []
        reply = sp.tap(o["run_id"], "2", site=site, queue=lambda: queued.append(1), edit=lambda m, k: edits.append(k))
        check("case3: tap 2 picks version 2 and queues one run",
              reply.startswith("Version 2 picked") and queued == [1], reply)
        o3 = sp.read_offer(o["run_id"])
        check("case3: offer picked, slot 3", o3["status"] == "picked" and o3["slot"] == 3 and o3["queued"] is True)
        pk = lines(os.path.join(site, "references", "picks", "picks.jsonl"))
        check("case3: the pick joins references/picks with both screenshots",
              len(pk) == 1 and pk[0]["slot"] == 3 and all(
                  os.path.getsize(os.path.join(site, "references", "picks", pk[0][k])) > 0 for k in ("desktop", "mobile")))
        check("case3: the buttons now read Picked 2", edits and edits[0]["inline_keyboard"][0][0]["text"] == "Picked 2")
        again = sp.tap(o["run_id"], "1", site=site, queue=lambda: queued.append(1), edit=lambda m, k: None)
        check("case3: a second tap changes nothing", again.startswith("You already picked") and queued == [1], again)
        out3 = os.path.join(root, "out3.jsonl")
        rc3, log3 = run_fanout(root, site, env, out3)
        html = open(os.path.join(site, "index.html")).read()
        check("case3: the next run installs the pick (exit 0)", rc3 == 0 and "<!-- stub candidate 3 -->" in html, log3[-400:])
        meta = json.load(open(os.path.join(site, "state", "generation-meta.json")))
        ev = lines(out3)
        check("case3: record and result event are candidate 3's, usage zero",
              meta["summary"] == "stub summary 3" and len(ev) == 1
              and ev[0]["result"].endswith("GENERATION_VERDICT: OK") and ev[0]["usage"]["output_tokens"] == 0)
        check("case3: offer reads installed, no session ran", sp.read_offer(o["run_id"])["status"] == "installed"
              and len(lines(env["STUB_TRACE"])) == 3)

        # ── case 4 ──────────────────────────────────────────────────
        site4 = make_site(root, "site4")
        env4 = env_for(root, site4, STUB_FAIL_GATE="1", STUB_JUDGE_SLOP="2", STUB_JUDGE_ERROR="3")
        idx4 = sha(os.path.join(site4, "index.html"))
        rc4, log4 = run_fanout(root, site4, env4, os.path.join(root, "out4.jsonl"))
        led4 = lines(os.path.join(site4, "state", ep.LEDGER))
        c4 = {c["slot"]: c for c in led4[-1]["candidates"]} if led4 else {}
        check("case4: zero passing -> exit 4, no message, no offer, site untouched",
              rc4 == 4 and not lines(env4["STUB_TG_LOG"]) and not os.path.exists(env4["ANDREMACEDO_PICKS_ROOT"] + "/x")
              and led4[-1]["outcome"] == "none_passed" and sha(os.path.join(site4, "index.html")) == idx4, log4[-400:])
        check("case4: SLOP and critic error both fail at craft_judge",
              all(any(g["name"] == "craft_judge" and not g["passed"] for g in c4[s]["gates"]) for s in (2, 3)))

        # ── case 5 ──────────────────────────────────────────────────
        def clone_offer(src, new_id):
            shutil.copytree(sp.offer_dir(src), sp.offer_dir(new_id))
            path = os.path.join(sp.offer_dir(new_id), "offer.json")
            d = json.load(open(path))
            d.update(run_id=new_id, status="offered", choice=None, queued=None)
            json.dump(d, open(path, "w"))
            return d
        o5 = clone_offer(o["run_id"], "20261127T000005Z")
        edits5 = []
        sp.daily(now=time.time() + 49 * 3600, queue=lambda: None, edit=lambda m, k: edits5.append(k))
        check("case5: daily pass expires the unanswered offer and drops its buttons",
              sp.read_offer(o5["run_id"])["status"] == "expired" and edits5 == [{"inline_keyboard": []}])
        late = sp.tap(o5["run_id"], "1", site=site, queue=lambda: None, edit=lambda m, k: None)
        check("case5: a late tap changes nothing", "closed" in late and sp.pending_pick() is None, late)

        # ── case 6 ──────────────────────────────────────────────────
        o6 = clone_offer(o["run_id"], "20261127T000006Z")
        none = sp.tap(o6["run_id"], "none", site=site, queue=lambda: None, edit=lambda m, k: None)
        check("case6: None keeps the live page and leaves nothing to install",
              none.startswith("Kept the live page") and sp.read_offer(o6["run_id"])["status"] == "declined"
              and sp.pending_pick() is None and sp.install(site, os.path.join(root, "o6.jsonl")) == sp.NO_INSTALL)

        # ── case 7 ──────────────────────────────────────────────────
        site7 = make_site(root, "site7")
        env7 = env_for(root, site7)
        os.makedirs(env7["ANDREMACEDO_PICKS_ROOT"])
        shutil.copytree(sp.offer_dir(o6["run_id"]), os.path.join(env7["ANDREMACEDO_PICKS_ROOT"], "20261127T000007Z"))
        p7 = os.path.join(env7["ANDREMACEDO_PICKS_ROOT"], "20261127T000007Z", "offer.json")
        d7 = json.load(open(p7)); d7.update(run_id="20261127T000007Z", status="offered",
                                            expires_at_s=time.time() + 3600); json.dump(d7, open(p7, "w"))
        script = "\n".join([
            "set -euo pipefail", 'log(){ echo "LOG: $*"; }', 'log_error(){ echo "ERR: $*"; }',
            f'SCRIPT_DIR="{site7}/scripts"; SITE_DIR="{site7}"; PULSE_TYPE=weekly',
            f'INPUT_JSONL_FILE="{make_input(root, site7)}"; HELPER_OUTPUT_FILE="{root}/out7.jsonl"',
            f'LOG_FILE="{root}/runner-block.log"; SESSION_WALL_CEILING=120',
            runner_block(), 'echo "REACHED THE DEPLOY PATH"'])
        p = subprocess.run(["bash", "-c", script], env=env7, capture_output=True, text=True)
        check("case7: runner block exits 0 without reaching the deploy path on exit 4",
              p.returncode == 0 and "the live page stays" in p.stdout and "REACHED" not in p.stdout
              and "ERR:" not in p.stdout, (p.stdout + p.stderr)[-400:])
        daily = open(os.path.join(SCRIPTS, "runner.sh")).read().split('if [ "$PULSE_TYPE" = "daily" ]; then', 1)[1].split("\nfi\n", 1)[0]
        check("case7: the daily pulse runs site_pick.py daily", 'site_pick.py" daily' in daily)
    finally:
        shutil.rmtree(root, ignore_errors=True)

    failed = [n for n, ok in RESULTS if not ok]
    print(f"\n{len(RESULTS) - len(failed)}/{len(RESULTS)} passed")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
