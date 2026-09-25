#!/usr/bin/env python3
"""epoch-operator-clear.py — Andre ends the live epoch; the next weekly opens a clearing.

Why this exists: until 2026-09-25 an epoch could end only two ways, both on the
epoch's own clock: the agent's metamorphose verdict at its monthly review
(EPOCH_REVIEW_AGE_DAYS) or the mechanical backstop (EPOCH_BACKSTOP_AGE_DAYS).
That day Andre moved generation to a new model and wanted that model to author
its own epoch now, not after the live one aged out. This is the third way: an
operator decision, recorded as one.

It reuses the burial a metamorphose verdict uses (record-generation.bury_epoch),
so past_epochs, the graveyard, epoch_number and the emptied active_obsession look
exactly as they do after any other clearing. The next weekly pulse then sees the
clearing and epoch_fanout.py runs the candidate fan-out, as after any burial. The
epitaph says plainly that Andre ended the epoch to hand the site to a new model
and quotes his reason; it says nothing about the epoch's content.

Writes exactly four files in <site>/state and nothing else. It starts no
generation, deploys nothing and commits nothing: the next runner deploy commits
the state it finds.
  genome.json                    past_epochs + graveyard + epoch_number (bury_epoch)
  agent-state.json               active_obsession emptied (bury_epoch)
  epoch-review-log.jsonl         one entry, verdict "operator_clear", with the reason
  epoch-transition-latest.json   kind "operator"

Refuses, writing nothing, when:
  - the reason is missing, blank or longer than REASON_MAX characters (exit 2);
  - a runner.sh process for this site is going, or the process check cannot
    answer (exit 4);
  - there is no live epoch: active_obsession.topic is empty (exit 3).

Usage: epoch-operator-clear.py --reason TEXT [--site DIR]
  --reason is recorded as given, with runs of whitespace folded to one space so
  the epitaph stays one line in the prompt's lineage.
  --site defaults to the repo this script lives in, as runner.sh's SITE_DIR does.
Test seam: ANDREMACEDO_PGREP swaps the process check for a stub (fixtures only).
It decides only whether the command refuses; it cannot change what is written.
"""
import sys

sys.dont_write_bytecode = True  # "writes nothing else" includes __pycache__

import argparse, importlib.util, json, os, subprocess
from datetime import datetime, timezone

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)
import epoch_review as er
import epoch_fanout as ef

_spec = importlib.util.spec_from_file_location(
    "record_generation", os.path.join(SCRIPT_DIR, "record-generation.py"))
rg = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(rg)

REFUSED_USAGE = 2
REFUSED_NO_EPOCH = 3
REFUSED_RUNNER = 4
REASON_MAX = 600            # record-generation caps review reasoning at 600
TRANSITION = "epoch-transition-latest.json"
ERE_SPECIAL = set("^$*+?()[]{}|\\")


def refuse(code, msg):
    print(f"epoch-operator-clear: refused: {msg}", file=sys.stderr)
    return code


def runner_going(site):
    """(going: bool|None, detail). None means the check could not answer.

    Same check as ~/.telos/scripts/andremacedo-site-run.sh: pgrep -f on this
    site's runner path with its dots escaped. Exit 0 = a match, 1 = none, any
    other exit = no answer.
    """
    pgrep = os.environ.get("ANDREMACEDO_PGREP") or "/usr/bin/pgrep"
    paths = {os.path.join(os.path.abspath(site), "scripts", "runner.sh"),
             os.path.join(os.path.realpath(site), "scripts", "runner.sh")}
    for path in sorted(paths):
        if ERE_SPECIAL & set(path):
            return None, f"runner path {path!r} holds a regex metacharacter"
        try:
            rc = subprocess.run([pgrep, "-f", path.replace(".", "[.]")],
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                timeout=30).returncode
        except (OSError, subprocess.TimeoutExpired) as e:
            return None, f"process check could not run: {e}"
        if rc == 0:
            return True, f"a runner.sh process is going ({path})"
        if rc != 1:
            return None, f"process check failed (pgrep exit {rc})"
    return False, "no runner.sh process"


def generation_model():
    """The model the next epoch opens on, read where the engine defines it."""
    out = subprocess.run(["bash", os.path.join(SCRIPT_DIR, "generation-session.sh"), "model"],
                         capture_output=True, text=True, timeout=30, check=True).stdout.strip()
    assert out and len(out.split()) == 1, f"generation-session.sh model printed {out!r}"
    return out


def load_obj(path):
    with open(path, encoding="utf-8") as f:
        obj = json.load(f)
    assert isinstance(obj, dict), f"{path} is not a JSON object"
    return obj


def write_json(path, obj):
    tmp = path + ".operator-tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(obj, f, indent=2, ensure_ascii=False)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--reason", required=True, help="why Andre is ending the epoch")
    ap.add_argument("--site", default=os.path.dirname(SCRIPT_DIR))
    args = ap.parse_args(argv)

    reason = " ".join((args.reason or "").split())
    if not reason:
        return refuse(REFUSED_USAGE, "--reason is blank")
    if len(reason) > REASON_MAX:
        return refuse(REFUSED_USAGE, f"--reason is {len(reason)} characters (max {REASON_MAX})")

    site = os.path.abspath(args.site)
    state_dir = os.path.join(site, "state")
    genome_path = os.path.join(state_dir, "genome.json")
    state_path = os.path.join(state_dir, "agent-state.json")
    assert os.path.isfile(genome_path) and os.path.isfile(state_path), \
        f"no genome.json / agent-state.json under {state_dir}"

    going, detail = runner_going(site)
    if going is not False:
        return refuse(REFUSED_RUNNER, detail)

    genome, state = load_obj(genome_path), load_obj(state_path)
    obs = state.get("active_obsession") or {}
    topic = (obs.get("topic") or "").strip()
    if not topic:
        return refuse(REFUSED_NO_EPOCH, "there is no live epoch (active_obsession.topic is "
                      f"empty since {obs.get('started') or 'unknown'}); nothing to end")
    epoch_num = genome.get("epoch_number")
    gen = genome.get("generation")
    assert isinstance(epoch_num, int) and not isinstance(epoch_num, bool), \
        "genome.json epoch_number must be an int"
    assert isinstance(gen, int) and not isinstance(gen, bool), \
        "genome.json generation must be an int"

    model = generation_model()
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    today = now[:10]
    started = obs.get("started", "")
    age = er.epoch_age_days(started, today)
    ran = (f"ran {started or 'unknown'} to {today}"
           + (f" ({age} days)" if age is not None else ""))
    epitaph = (f"Andre ended this epoch by operator decision, to hand the site to a new "
               f"generation model ({model}), which opens the next one. Epoch {epoch_num}, "
               f"\"{topic}\", {ran}. It was not ended by the agent's verdict or by the "
               f"backstop, and no eulogy was written for it. Andre's reason: {reason}")

    # The burial a metamorphose verdict uses. died_gen is the dead epoch's last
    # generation: no generation is minted here.
    dead = rg.bury_epoch(genome, state, epoch_num, topic, started, epitaph, gen, now, today)
    dead["transition"] = "operator"
    dead["transition_reason"] = reason

    pl = er.plateau(er.load_craft_history(er.craft_history_path(state_dir)), since=started)
    write_json(genome_path, genome)
    write_json(state_path, state)
    er.record_review(state_dir, {
        "gen": gen, "date": today, "epoch_number": epoch_num, "epoch_topic": topic,
        "age_days": age, "verdict": "operator_clear", "agent_verdict": None,
        "deepen_streak": 0, "craft_spread": pl.get("spread"), "craft_flat": pl.get("flat"),
        "reasoning": reason, "operator": "andre", "model_after": model,
    })
    write_json(os.path.join(state_dir, TRANSITION), {
        "gen": gen, "date": today, "epoch_number": epoch_num, "topic": topic,
        "kind": "operator", "age_days": age, "reason": reason, "operator": "andre",
        "model_after": model, "craft_plateau": pl})

    key = ef.opening_key(site)
    assert key is not None, "the burial left no clearing for the fan-out trigger"
    print(f"Epoch {epoch_num} buried by operator decision; it {ran}. Clearing opens {today}. "
          f"The next weekly pulse fans out opening {key} on {model}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
