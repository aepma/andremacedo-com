#!/usr/bin/env python3
"""site_pick.py: Andre picks the weekly andremacedo.com version (order 2026-11-27).

Why this exists: the site had no taste signal from Andre. The feedback ledger
was dark from 2026-09-16 and the engine read silence as approval, so every epoch
threw the last design away on its own judgement. Andre's order of 2026-11-27:
every weekly run builds three clearly different candidates, he sees them and
picks one or none, and only a picked candidate goes live.

The flow, end to end:
  1. epoch_fanout.py builds and gates the candidates, then calls offer(): each
     passing candidate's changed files, screenshots and result event are kept
     under PICKS/<run>/, one contact sheet (desktop and mobile of each) is
     rendered, and ONE Telegram photo goes to Andre through the shared outbound
     gate (scripts/lib/telegram-send.sh, kind requested, request ref
     andre-2026-11-27-site-picks). The pick buttons are attached to that same
     message by a markup edit, so it stays one message. Never a reminder.
  2. A button tap reaches the command bridge as "/sitepick RUN CHOICE" and the
     plug-in bridges/command-bridge/commands.d/sitepick runs `tap`. A pick is
     recorded once, its screenshots join references/picks/, and one site run is
     queued through the Creative run queue (agents_run.start_site_run). "None"
     records the answer and changes nothing.
  3. The queued run is runner.sh --weekly. Its fan-out step calls `install`
     first: a picked, uninstalled candidate is copied into the site and its
     result event is written for the runner, whose every gate then runs on it
     before the deploy. The next run evolves from that page.
  4. The daily pulse calls `daily`: an offer older than OFFER_HOURS with no
     answer expires (its buttons are removed, nothing deploys). The first pick
     run, and a pick that could not be queued at tap time, are queued by a
     detached `queue-when-idle` waiter once the daily runner has exited: the
     run queue and its launcher refuse a run while any runner.sh is alive.

Statuses: offered, held (the gate did not deliver it), picked, declined,
expired, installed. Exit codes: 0 ok; 3 nothing to install; 64 usage; 70 a
failed invariant. Python 3.9+. Loads no secrets: Telegram sends go through
telegram-send.sh, which resolves its own token.
"""
import argparse, fcntl, hashlib, json, os, shutil, subprocess, sys, time
from datetime import datetime, timezone

SITE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TELOS = os.path.join(os.path.expanduser("~"), ".telos")
PICKS = os.environ.get("ANDREMACEDO_PICKS_ROOT") or os.path.join(TELOS, "state", "andremacedo-picks")
OWNER_CHAT = "2040883772"
OFFER_HOURS = 48
PRODUCER = "telegram-gate:andremacedo-site-picks"
REQUEST_REF = "andre-2026-11-27-site-picks"
# Test seam only: the fixture test points this at a recording stub. Every real
# send still goes through the shared outbound primitive and its gate.
TG_SEND = os.environ.get("ANDREMACEDO_TG_SEND") or os.path.join(TELOS, "scripts", "lib", "telegram-send.sh")
SHEET_RENDER = os.path.join(SITE, "scripts", "screenshot-file.sh")
REQUIRED = ("index.html", os.path.join("state", "generation-meta.json"))
NO_INSTALL = 3
IDLE_WAIT_S = 3 * 3600
IDLE_POLL_S = 30


class PickError(Exception):
    pass


def check(cond, msg):
    if not cond:
        raise PickError(msg)


def iso(ts=None):
    return datetime.fromtimestamp(time.time() if ts is None else ts, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def log(msg):
    print(f"[site-pick {iso()}] {msg}", flush=True)


def offer_dir(run_id):
    check(run_id.replace("-", "").replace("T", "").replace("Z", "").isdigit(), f"bad run id {run_id!r}")
    return os.path.join(PICKS, run_id)


def read_offer(run_id):
    path = os.path.join(offer_dir(run_id), "offer.json")
    with open(path, encoding="utf-8") as f:
        offer = json.load(f)
    check(offer.get("run_id") == run_id, f"offer {run_id} names another run")
    return offer


def write_offer(offer):
    path = os.path.join(offer_dir(offer["run_id"]), "offer.json")
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(offer, f, indent=2, ensure_ascii=False)
    os.replace(tmp, path)


def offers():
    try:
        names = sorted(os.listdir(PICKS))
    except FileNotFoundError:
        return []
    out = []
    for n in names:
        if os.path.isfile(os.path.join(PICKS, n, "offer.json")):
            out.append(read_offer(n))
    return out


class locked:
    """One writer at a time across the bridge plug-in, the runner and the daily pulse."""
    def __enter__(self):
        os.makedirs(PICKS, exist_ok=True)
        self.fh = open(os.path.join(PICKS, ".lock"), "w")
        fcntl.flock(self.fh, fcntl.LOCK_EX)
        return self

    def __exit__(self, *exc):
        fcntl.flock(self.fh, fcntl.LOCK_UN)
        self.fh.close()


def open_offer(now=None):
    """The offer still waiting for Andre's answer, or None. While one is open no
    new candidates are built: one message per run, never a second one on top."""
    now = time.time() if now is None else now
    for o in reversed(offers()):
        if o["status"] == "offered" and now < o["expires_at_s"]:
            return o
    return None


# ── 1. offer ─────────────────────────────────────────────────────────
def keep_candidate(site, run_id, c):
    """Copy what one passing candidate changed (inside the install scope) into the
    offer, so its scratch tree can be deleted. Returns its offer entry."""
    cdir = os.path.join(offer_dir(run_id), f"cand{c['slot']}")
    files = os.path.join(cdir, "files")
    os.makedirs(files)
    changes, deleted = [], []
    for rel in sorted(set(c["baseline"]) | set(c["now"])):
        if c["baseline"].get(rel) == c["now"].get(rel):
            continue
        if rel in c["now"]:
            dst = os.path.join(files, rel)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copy2(os.path.join(c["tree"], rel), dst, follow_symlinks=False)
            changes.append(rel)
        else:
            deleted.append(rel)
    for rel in REQUIRED:
        check(rel in changes, f"candidate {c['slot']} did not write {rel}")
    for kind, src in zip(("desktop", "mobile"), c["shots"]):
        shutil.copy2(src, os.path.join(cdir, f"{kind}.jpg"))
    with open(os.path.join(cdir, "result.json"), "w", encoding="utf-8") as f:
        json.dump(c["result_event"], f)
    scores = c.get("scores") or {}
    return {"slot": c["slot"], "topic": c.get("topic"), "visual_strategy": c.get("visual_strategy"),
            "summary": c.get("summary"), "changes": changes, "deleted": deleted,
            "craft_min": scores.get("craft_min")}


def sheet_html(offer):
    cols = []
    for i, c in enumerate(offer["candidates"], start=1):
        d = f"cand{c['slot']}"
        cols.append(
            f'<div class="col"><div class="n">{i}</div>'
            f'<div class="d"><img src="{d}/desktop.jpg"></div>'
            f'<div class="m"><img src="{d}/mobile.jpg"></div></div>')
    return ("<!doctype html><meta charset=utf-8><style>"
            "body{margin:0;background:#111;font:600 40px/1 Helvetica,Arial,sans-serif;color:#fff}"
            ".row{display:flex;gap:24px;padding:24px}.col{flex:1;display:flex;flex-direction:column;gap:16px}"
            ".n{font-size:56px}.d{height:520px;overflow:hidden;border-radius:8px}"
            ".m{height:640px;width:300px;overflow:hidden;border-radius:8px}"
            "img{width:100%;display:block}</style><div class=row>" + "".join(cols) + "</div>")


def render_sheet(offer):
    od = offer_dir(offer["run_id"])
    html = os.path.join(od, "sheet.html")
    with open(html, "w", encoding="utf-8") as f:
        f.write(sheet_html(offer))
    out = os.path.join(od, "sheet.jpg")
    cp = subprocess.run(["bash", SHEET_RENDER, html, out], capture_output=True, text=True, timeout=180)
    check(cp.returncode == 0 and os.path.getsize(out) > 0,
          f"contact sheet render failed (exit {cp.returncode}): {cp.stderr.strip()[-200:]}")
    return out


def caption(offer):
    n = len(offer["candidates"])
    head = ("Three new versions of andremacedo.com are ready." if n == 3 else
            f"{n} new version{'s' if n != 1 else ''} of andremacedo.com passed the checks.")
    lines = [head, "Each shows the desktop page on top and the phone page below.", ""]
    for i, c in enumerate(offer["candidates"], start=1):
        lines.append(f"{i}. {(c.get('summary') or c.get('topic') or 'untitled')[:150]}")
    lines += ["", "Tap a number to put that version live, or None to keep today's page. "
              f"Nothing changes without your pick. This stays open for {OFFER_HOURS} hours."]
    return "\n".join(lines)[:1020]


def markup(offer):
    row = [{"text": f"Pick {i}", "callback_data": f"/sitepick {offer['run_id']} {i}"}
           for i in range(1, len(offer["candidates"]) + 1)]
    row.append({"text": "None", "callback_data": f"/sitepick {offer['run_id']} none"})
    for b in row:
        check(len(b["callback_data"].encode()) <= 64, "callback data too long")
    return {"inline_keyboard": [row]}


def tg_json(stdout):
    for line in reversed(stdout.splitlines()):
        try:
            o = json.loads(line)
        except ValueError:
            continue
        if isinstance(o, dict):
            return o
    return {}


def telegram_photo(offer, sheet):
    env = dict(os.environ, TG_INTERVENTION_PRODUCER=PRODUCER, TG_INTERVENTION_KIND="requested",
               TG_INTERVENTION_REQUEST_REF=REQUEST_REF,
               TG_INTERVENTION_SUBJECT="andremacedo-site-pick-" + offer["run_id"].lower(),
               TG_INTERVENTION_EVIDENCE=os.path.join(offer_dir(offer["run_id"]), "offer.json"),
               TELEGRAM_SEND_HISTORY_TEXT=caption(offer))
    cp = subprocess.run(["/bin/bash", TG_SEND, "file", "sendPhoto", OWNER_CHAT, "photo", sheet,
                         caption(offer)], capture_output=True, text=True, timeout=120, env=env)
    resp = tg_json(cp.stdout)
    if resp.get("ok") is True:
        return {"status": "offered", "message_id": (resp.get("result") or {}).get("message_id")}
    return {"status": "held", "detail": (resp.get("status") or cp.stderr.strip()[-200:] or "no response")}


def telegram_markup(message_id, mk):
    cp = subprocess.run(["/bin/bash", TG_SEND, "markup", OWNER_CHAT, str(message_id), json.dumps(mk)],
                        capture_output=True, text=True, timeout=60)
    return cp.returncode == 0


def offer(site, run_id, cands, send_photo=None, send_markup=None):
    """Keep every passing candidate, then send the one pick message. Returns the offer."""
    check(cands, "offer needs at least one passing candidate")
    check(len(cands) <= 3, "at most three candidates per offer")
    os.makedirs(offer_dir(run_id))
    entries = [keep_candidate(site, run_id, c) for c in cands]
    now = time.time()
    o = {"run_id": run_id, "created_at": iso(now), "expires_at": iso(now + OFFER_HOURS * 3600),
         "expires_at_s": now + OFFER_HOURS * 3600, "status": "building", "candidates": entries,
         "choice": None, "message_id": None}
    write_offer(o)
    sheet = render_sheet(o)
    sent = (send_photo or telegram_photo)(o, sheet)
    o["status"] = sent["status"]
    o["message_id"] = sent.get("message_id")
    o["send_detail"] = sent.get("detail")
    if o["status"] == "offered":
        check(o["message_id"], "delivered pick message has no message id")
        o["buttons"] = bool((send_markup or telegram_markup)(o["message_id"], markup(o)))
    write_offer(o)
    log(f"offer {run_id}: {len(entries)} candidate(s), status {o['status']}, buttons {o.get('buttons')}")
    return o


# ── 2. tap ───────────────────────────────────────────────────────────
def save_reference(site, o, entry):
    """Every pick joins references/picks/, the target the next run studies."""
    pdir = os.path.join(site, "references", "picks")
    os.makedirs(pdir, exist_ok=True)
    names = {}
    for kind in ("desktop", "mobile"):
        name = f"{o['run_id']}-cand{entry['slot']}-{kind}.jpg"
        shutil.copy2(os.path.join(offer_dir(o["run_id"]), f"cand{entry['slot']}", f"{kind}.jpg"),
                     os.path.join(pdir, name))
        names[kind] = name
    with open(os.path.join(pdir, "picks.jsonl"), "a", encoding="utf-8") as f:
        f.write(json.dumps({"run_id": o["run_id"], "picked_at": o["picked_at"], "slot": entry["slot"],
                            "topic": entry.get("topic"), "visual_strategy": entry.get("visual_strategy"),
                            "summary": entry.get("summary"), **names}, ensure_ascii=False) + "\n")


def queue_site_run():
    """One run through the Creative run queue. Returns None, or why it waits."""
    sys.path.insert(0, os.path.join(TELOS, "scripts", "lib"))
    import agents_run

    class Refused(Exception):
        def __init__(self, msg, *_a, **_k):
            super().__init__(msg)

    try:
        agents_run.start_site_run(Refused, Refused)
    except Refused as e:
        return str(e)
    return None


def tap(run_id, choice, site=SITE, now=None, queue=queue_site_run, edit=telegram_markup):
    """Andre's answer. Returns the one-line reply. Records at most one answer."""
    now = time.time() if now is None else now
    with locked():
        try:
            o = read_offer(run_id)
        except (OSError, ValueError, PickError):
            return "I do not know that set of site versions. Nothing changed."
        if o["status"] in ("picked", "installed"):
            return f"You already picked version {o['choice']}. Nothing changed."
        if o["status"] == "declined":
            return "You already chose None. The live page stays as it is."
        if o["status"] == "expired" or now >= o["expires_at_s"]:
            if o["status"] != "expired":
                o["status"] = "expired"
                write_offer(o)
            return f"This choice closed after {OFFER_HOURS} hours. The live page stayed as it is."
        if choice == "none":
            o.update(status="declined", choice="none", answered_at=iso(now))
            write_offer(o)
            if o.get("message_id"):
                edit(o["message_id"], {"inline_keyboard": [[{"text": "None chosen", "callback_data": "/sitepick done"}]]})
            return "Kept the live page as it is. The next run starts from it."
        check(choice.isdigit() and 1 <= int(choice) <= len(o["candidates"]), f"no version {choice}")
        entry = o["candidates"][int(choice) - 1]
        o.update(status="picked", choice=int(choice), slot=entry["slot"], picked_at=iso(now))
        write_offer(o)
        save_reference(site, o, entry)
        if o.get("message_id"):
            edit(o["message_id"], {"inline_keyboard": [[{"text": f"Picked {choice}", "callback_data": "/sitepick done"}]]})
        waits = queue()
        o["queued"] = waits is None
        o["queue_detail"] = waits
        write_offer(o)
    if waits is None:
        return f"Version {choice} picked. It goes live after the usual checks, in about 20 minutes."
    return f"Version {choice} picked. Another site run is going, so it goes live right after it."


# ── 3. install ───────────────────────────────────────────────────────
def pending_pick():
    for o in reversed(offers()):
        if o["status"] == "picked":
            return o
    return None


def install(site, output):
    """Copy the picked candidate into the site and write its result event for the
    runner. 0 installed, NO_INSTALL when no pick waits. Rolls back on failure."""
    with locked():
        o = pending_pick()
        if o is None:
            return NO_INSTALL
        entry = o["candidates"][o["choice"] - 1]
        cdir = os.path.join(offer_dir(o["run_id"]), f"cand{entry['slot']}")
        backup = os.path.join(cdir, "install-backup")
        shutil.rmtree(backup, ignore_errors=True)
        done = []
        try:
            for rel in entry["changes"] + entry["deleted"]:
                dst = os.path.join(site, rel)
                existed = os.path.lexists(dst)
                if existed:
                    os.makedirs(os.path.dirname(os.path.join(backup, rel)), exist_ok=True)
                    shutil.copy2(dst, os.path.join(backup, rel), follow_symlinks=False)
                done.append((rel, existed))
                if os.path.lexists(dst):
                    os.remove(dst)
                if rel in entry["changes"]:
                    os.makedirs(os.path.dirname(dst), exist_ok=True)
                    shutil.copy2(os.path.join(cdir, "files", rel), dst, follow_symlinks=False)
        except Exception:
            for rel, existed in reversed(done):
                dst = os.path.join(site, rel)
                if os.path.lexists(dst):
                    os.remove(dst)
                if existed:
                    shutil.copy2(os.path.join(backup, rel), dst, follow_symlinks=False)
            raise
        with open(os.path.join(cdir, "result.json"), encoding="utf-8") as f:
            event = json.load(f)
        # The offer run already counted these tokens; the install spends none.
        event["usage"] = {"input_tokens": 0, "cache_creation_input_tokens": 0,
                          "cache_read_input_tokens": 0, "output_tokens": 0}
        with open(output, "w", encoding="utf-8") as f:
            f.write(json.dumps(event) + "\n")
        o.update(status="installed", installed_at=iso())
        write_offer(o)
    log(f"installed pick {o['run_id']} version {o['choice']} (candidate {entry['slot']}): "
        f"{len(entry['changes'])} file(s) written, {len(entry['deleted'])} removed")
    return 0


# ── 4. daily ─────────────────────────────────────────────────────────
def first_run(queue):
    """Andre's order: once this flow is installed, queue one site run so the first
    three candidates reach him without waiting for the weekly schedule. Once only."""
    marker = os.path.join(PICKS, "first-run.json")
    if os.path.exists(marker) or offers():
        return
    waits = queue()
    if waits is None:
        os.makedirs(PICKS, exist_ok=True)
        with open(marker, "w", encoding="utf-8") as f:
            json.dump({"queued_at": iso()}, f)
    log(f"first pick run queued: {waits or 'yes'}")


def queue_due(queue):
    """Queue the first pick run, and a pick that could not be queued at tap time."""
    first_run(queue)
    with locked():
        o = pending_pick()
    if o is not None and not o.get("queued"):
        waits = queue()
        with locked():
            o = read_offer(o["run_id"])
            o["queued"] = waits is None
            o["queue_detail"] = waits
            write_offer(o)
        log(f"pick {o['run_id']} queued: {waits or 'yes'}")


def queue_is_due():
    if not os.path.exists(os.path.join(PICKS, "first-run.json")) and not offers():
        return True
    o = pending_pick()
    return o is not None and not o.get("queued")


def spawn_idle_waiter():
    """The daily pulse runs inside runner.sh, and both the run queue and its
    launcher refuse a new run while any runner.sh is alive (a request made now
    would be refused and used up). So hand the queueing to one detached waiter
    that queues once the runner has exited. It is bounded to IDLE_WAIT_S."""
    os.makedirs(PICKS, exist_ok=True)
    with open(os.path.join(PICKS, "waiter.log"), "a", encoding="utf-8") as lf:
        subprocess.Popen([sys.executable, os.path.abspath(__file__), "queue-when-idle"],
                         stdin=subprocess.DEVNULL, stdout=lf, stderr=lf, start_new_session=True,
                         close_fds=True)
    log("queueing handed to a waiter that starts once this runner has exited")


def queue_when_idle(runner_running=None, sleep=time.sleep, deadline_s=None):
    """Wait until no runner.sh is alive, then queue what is due. 0 queued or nothing
    due; 75 the runner never went idle inside the bound (the next daily retries)."""
    if runner_running is None:
        sys.path.insert(0, os.path.join(TELOS, "scripts", "lib"))
        import agents_run
        runner_running = agents_run.runner_running
    end = time.time() + (IDLE_WAIT_S if deadline_s is None else deadline_s)
    while runner_running():
        if time.time() >= end:
            log("the site runner stayed busy; nothing queued, the next daily pulse retries")
            return 75
        sleep(IDLE_POLL_S)
    queue_due(queue_site_run)
    return 0


def daily(now=None, queue=None, edit=telegram_markup):
    """Expire unanswered offers. With a queue (tests, the idle waiter) queue what
    is due at once; inside runner.sh hand it to the idle waiter."""
    now = time.time() if now is None else now
    if queue is not None:
        first_run(queue)
    with locked():
        for o in offers():
            if o["status"] == "offered" and now >= o["expires_at_s"]:
                o.update(status="expired", expired_at=iso(now))
                write_offer(o)
                if o.get("message_id"):
                    edit(o["message_id"], {"inline_keyboard": []})
                log(f"offer {o['run_id']} expired with no pick; the live page stays")
    if queue is not None:
        queue_due(queue)
    elif queue_is_due():
        spawn_idle_waiter()
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    t = sub.add_parser("tap"); t.add_argument("run_id"); t.add_argument("choice")
    i = sub.add_parser("install"); i.add_argument("--site", default=SITE); i.add_argument("--output", required=True)
    sub.add_parser("daily")
    sub.add_parser("queue-when-idle")
    sub.add_parser("status")
    a = ap.parse_args(argv)
    try:
        if a.cmd == "tap":
            print(tap(a.run_id, a.choice.lower()))
            return 0
        if a.cmd == "install":
            return install(os.path.abspath(a.site), a.output)
        if a.cmd == "daily":
            return daily()
        if a.cmd == "queue-when-idle":
            return queue_when_idle()
        print(json.dumps([{k: o.get(k) for k in ("run_id", "status", "choice", "created_at", "expires_at")}
                          for o in offers()], indent=2))
        return 0
    except PickError as e:
        print(f"site-pick: {e}", file=sys.stderr)
        return 70


if __name__ == "__main__":
    sys.exit(main())
