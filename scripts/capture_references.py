#!/usr/bin/env python3
"""capture_references.py — scene pictures of a directed piece, at desktop and phone size.

Andre's order of 2026-11-27 (the directed piece). Two uses, one capture path:

  references --site SITE
      For every note in SITE/references/ that names a public "Source:" link and
      has no pictures yet, open the link and save about six scenes at desktop
      1280x800 and phone 390x844 beside the note:
      NAME-desktop-1.jpg .. NAME-desktop-6.jpg, NAME-mobile-1.jpg .. NAME-mobile-6.jpg.
      Run by epoch_fanout.py before a weekly run builds, on the uncaged site run.
      A failed capture writes no picture and logs one plain line; the run goes on.
      A capture never invents a picture: it saves only what the browser showed,
      and refuses a page that is a bot check or empty.

  scenes --dir TREE --out DIR
      Serve TREE over loopback and save the same six scenes of its index.html into
      DIR (desktop-N.jpg, mobile-N.jpg). Each weekly candidate runs this on its own
      page every pass, to compare its scenes with the reference pictures.

Scenes: the first picture is taken once the page has settled. Before each next
one the capture taps the middle of the page (so a framed piece gets focus) on the
first step only, presses the right arrow key, scrolls one screen, and waits, so a
piece that plays itself, steps by key or steps by scroll all move on.

Uses the engine's existing Playwright virtualenv (the one screenshot-local.sh and
screenshot.sh use). Starts no lasting process: the loopback server is a thread
that dies with this process. Exit 0 = every requested capture saved or there was
nothing to capture; 1 = at least one capture failed (its line says why); 2 = usage.
"""
import argparse
import functools
import os
import re
import subprocess
import sys
import tempfile
import threading

sys.dont_write_bytecode = True

SCENES = 6
SIZES = (("desktop", {"width": 1280, "height": 800}, 1),
         ("mobile", {"width": 390, "height": 844}, 2))
SETTLE_MS = 4000
STEP_MS = 2600
VENV = os.path.expanduser("~/.telos/playwright-venv/bin/python3")
SOURCE_RE = re.compile(r"^Source:[\s\S]{0,300}?(https://[^\s)>\]]+)", re.M)
BLOCKED = ("verify you are human", "just a moment", "checking your browser",
           "enable javascript and cookies", "access denied")
MIN_BYTES = 4000


def log(msg):
    print(f"[capture-references] {msg}", flush=True)


def note_source(path):
    """The first public https link on the note's Source: line, or None."""
    with open(path, encoding="utf-8") as f:
        head = f.read(4000)
    m = SOURCE_RE.search(head)
    return m.group(1).rstrip(".,;") if m else None


def has_pictures(ref_dir, name):
    return any(f.startswith(name + "-") and f.lower().endswith((".jpg", ".jpeg", ".png"))
               for f in os.listdir(ref_dir))


def pending_notes(ref_dir):
    """[(name, url)] for notes that name a source and have no pictures yet."""
    out = []
    for fn in sorted(os.listdir(ref_dir)):
        if not fn.endswith(".md") or fn == "README.md":
            continue
        name = fn[:-3]
        url = note_source(os.path.join(ref_dir, fn))
        if url and not has_pictures(ref_dir, name):
            out.append((name, url))
    return out


# The capture itself runs inside the Playwright virtualenv, as screenshot-local.sh
# does. It prints one line per saved picture and exits non-zero on any refusal.
CAPTURE = r'''
import asyncio, json, sys
from playwright.async_api import async_playwright
url, out_dir, prefix, cfg = sys.argv[1], sys.argv[2], sys.argv[3], json.loads(sys.argv[4])

async def one(browser, kind, viewport, scale):
    page = await browser.new_page(viewport=viewport, device_scale_factor=scale)
    try:
        try:
            await page.goto(url, wait_until="load", timeout=45000)
        except Exception:
            await page.goto(url, wait_until="domcontentloaded", timeout=45000)
        await page.wait_for_timeout(cfg["settle"])
        text = ((await page.title()) + " " + (await page.evaluate(
            "document.body ? document.body.innerText.slice(0, 2000) : ''"))).lower()
        for word in cfg["blocked"]:
            if word in text:
                raise SystemExit(f"the page showed a bot check ({word!r}), not the piece")
        for n in range(1, cfg["scenes"] + 1):
            path = f"{out_dir}/{prefix}{kind}-{n}.jpg"
            await page.screenshot(path=path, type="jpeg", quality=80)
            print(path, flush=True)
            if n == cfg["scenes"]:
                break
            if n == 1:
                await page.mouse.click(viewport["width"] // 2, viewport["height"] // 2)
            await page.keyboard.press("ArrowRight")
            await page.mouse.wheel(0, viewport["height"])
            await page.wait_for_timeout(cfg["step"])
    finally:
        await page.close()

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        try:
            for kind, viewport, scale in cfg["sizes"]:
                await one(browser, kind, viewport, scale)
        finally:
            await browser.close()

asyncio.run(main())
'''


def capture(url, out_dir, prefix, venv=VENV, timeout=300):
    """Save the scenes of url into out_dir. Returns the saved paths. Raises
    RuntimeError with a plain reason; on failure nothing it wrote is kept."""
    if not os.path.isfile(venv):
        raise RuntimeError(f"the browser toolkit is missing ({venv})")
    os.makedirs(out_dir, exist_ok=True)
    cfg = {"scenes": SCENES, "settle": SETTLE_MS, "step": STEP_MS, "blocked": list(BLOCKED),
           "sizes": [[k, v, s] for k, v, s in SIZES]}
    import json
    try:
        cp = subprocess.run([venv, "-c", CAPTURE, url, out_dir, prefix, json.dumps(cfg)],
                            capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        cp = None
    saved = [l.strip() for l in (cp.stdout if cp else "").splitlines() if l.strip().endswith(".jpg")]
    want = SCENES * len(SIZES)
    bad = [p for p in saved if not os.path.isfile(p) or os.path.getsize(p) < MIN_BYTES]
    if cp is None or cp.returncode != 0 or len(saved) != want or bad:
        for p in saved:
            if os.path.isfile(p):
                os.remove(p)
        if cp is None:
            raise RuntimeError(f"the capture took longer than {timeout} seconds")
        why = (cp.stderr.strip().splitlines() or ["no detail"])[-1][:200]
        if cp.returncode == 0:
            why = f"{len(saved)} of {want} pictures, {len(bad)} empty"
        raise RuntimeError(why)
    return saved


def capture_missing(site, logger=log, capture_fn=capture):
    """Pictures for every reference note that names a source and has none.
    Never raises: each failure is one plain line. Returns (saved, failed) counts."""
    ref_dir = os.path.join(site, "references")
    if not os.path.isdir(ref_dir):
        logger("no references folder; nothing to capture")
        return 0, 0
    saved = failed = 0
    for name, url in pending_notes(ref_dir):
        try:
            paths = capture_fn(url, ref_dir, name + "-")
            saved += len(paths)
            logger(f"saved {len(paths)} pictures of {name} from {url}")
        except Exception as e:  # noqa: BLE001 — one plain line, then the run goes on
            failed += 1
            logger(f"could not capture pictures of {name} from {url}: {e}; the run goes on without them")
    return saved, failed


def serve(tree):
    from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

    class Quiet(SimpleHTTPRequestHandler):
        def log_message(self, *a, **k):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Quiet, directory=tree))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def capture_tree(tree, out_dir, capture_fn=capture):
    index = os.path.join(tree, "index.html")
    if not os.path.isfile(index):
        raise RuntimeError(f"no index.html in {tree}")
    server = serve(tree)
    try:
        return capture_fn(f"http://127.0.0.1:{server.server_address[1]}/index.html", out_dir, "")
    finally:
        server.shutdown()
        server.server_close()


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("references")
    r.add_argument("--site", required=True)
    s = sub.add_parser("scenes")
    s.add_argument("--dir", required=True)
    s.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    if a.cmd == "references":
        _, failed = capture_missing(os.path.abspath(a.site))
        return 1 if failed else 0
    try:
        for p in capture_tree(os.path.abspath(a.dir), os.path.abspath(a.out)):
            print(p)
    except RuntimeError as e:
        log(f"could not capture the scenes: {e}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
