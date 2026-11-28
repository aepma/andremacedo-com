#!/usr/bin/env python3
"""build_archive.py: regenerate archive.html from the engine's real records.

Andre's order of 2026-11-27: the live page links "see my earlier bodies, as
pictures" to archive.html, but that file was last written on 2026-08-25. It
stopped at version 225, listed 109 of 144 experiments and showed no pictures,
while archive-screenshots/ held a picture of every weekly version since
2026-09-05. This script rebuilds the page on every run from three records:

  versions     every version number in the git history of state/agent-state.json,
               plus the working tree's current version (the one about to deploy),
               dated by the first commit that carried it
  pictures     archive-screenshots/manifest.json entries that shipped (never an
               unshipped candidate, never a -fanout- file), each attributed to the
               version that was live when it was taken. runner.sh takes its
               picture after committing version N and before deploying it, so
               the picture shows the version recorded at that commit's parent.
               With --shoot, a version that is about to deploy and has no
               picture yet gets one: the working tree is rendered with
               screenshot-local.sh into <date>-version-<N>.jpg.
  experiments  every experiments/NNN.html, titled from its own <title>

Each picture is shown through a web-sized copy, <stem>-web.webp (top 1200x1500
of the full-page shot, 640 px wide, quality 72, about 35 KB), made once with
cwebp. Versions with no picture are listed as text. Newest first.

The page is written atomically. Any failed precondition exits non-zero and
leaves the previous archive.html in place. Python 3.9. Loads no secrets.

Usage: build_archive.py --site DIR [--shoot] [--dry-run]
Exit 0 written, 1 failed (previous page kept), 64 usage.
"""

import argparse
import datetime as dt
import html
import json
import os
import re
import shutil
import struct
import subprocess
import sys
import tempfile

STATE = "state/agent-state.json"
SHOTS = "archive-screenshots"
CWEBP_PATHS = ("/opt/homebrew/bin/cwebp", "/usr/local/bin/cwebp")
WEB_WIDTH = 640
CROP_RATIO = 1.25  # crop height = width * ratio: the first screen and a bit
OWN_SHOT_RE = re.compile(r"\A(\d{4}-\d{2}-\d{2})-version-(\d+)\.jpg\Z")
GEN_SUBJECT_RE = re.compile(r"\Aagent: gen (\d+)\b")
GENERIC_RE = re.compile(r"\Aagent: daily data refresh\b")
EXP_RE = re.compile(r"\A(\d{3})\.html\Z")


class Fail(Exception):
    pass


def need(ok, why):
    if not ok:
        raise Fail(why)


def git(site, *args, data=None):
    cp = subprocess.run(["git", "-C", site] + list(args), input=data, capture_output=True, timeout=120)
    need(cp.returncode == 0, "git %s failed: %s" % (args[0], cp.stderr.decode("utf-8", "replace")[-300:]))
    return cp.stdout


def cat_versions(site, revs):
    """{rev: version or None} for STATE at each rev, through one git cat-file --batch."""
    if not revs:
        return {}
    data = "".join("%s:%s\n" % (r, STATE) for r in revs).encode()
    out = git(site, "cat-file", "--batch", data=data)
    res, pos = {}, 0
    for rev in revs:
        nl = out.index(b"\n", pos)
        header = out[pos:nl].decode()
        pos = nl + 1
        if header.endswith(" missing") or header.endswith(" ambiguous"):
            res[rev] = None
            continue
        size = int(header.split()[2])
        body = out[pos:pos + size]
        pos += size + 1
        try:
            v = json.loads(body.decode("utf-8")).get("version")
        except (ValueError, AttributeError):
            v = None
        res[rev] = v if isinstance(v, int) and v > 0 else None
    return res


def clean_subject(subject):
    s = subject.split(" | ")[0]
    s = re.sub(r"\Aagent:\s*", "", s)
    s = re.sub(r"\Agen \d+( (weekly|event|daily))?:\s*", "", s)
    s = s.strip()
    if len(s) > 150:
        s = s[:150].rsplit(" ", 1)[0].rstrip(",;:—- ") + "…"
    return s


def load_versions(site):
    """{version: {"date", "commit", "summary"}} from git history plus the working tree."""
    log = git(site, "log", "--reverse", "--format=%H%x09%ct%x09%s", "--", STATE).decode("utf-8", "replace")
    rows = [line.split("\t", 2) for line in log.splitlines() if line.strip()]
    need(rows, "no git history for %s" % STATE)
    vers = cat_versions(site, [r[0] for r in rows])
    out, named = {}, {}
    for sha, ct, subject in rows:
        m = GEN_SUBJECT_RE.match(subject)
        if m and int(m.group(1)) not in named:
            named[int(m.group(1))] = (sha, ct, subject)
        v = vers[sha]
        if v is None or v in out:
            continue
        out[v] = {"date": dt.datetime.fromtimestamp(int(ct)).date(), "commit": sha[:7],
                  "summary": "" if GENERIC_RE.match(subject) else clean_subject(subject)}
    for v, (sha, ct, subject) in named.items():
        if v in out:  # the run that made the version names it: its date and words win
            out[v] = {"date": dt.datetime.fromtimestamp(int(ct)).date(), "commit": sha[:7],
                      "summary": clean_subject(subject)}
    with open(os.path.join(site, STATE), encoding="utf-8") as fh:
        cur = json.load(fh).get("version")
    need(isinstance(cur, int) and cur > 0, "working-tree %s has no version" % STATE)
    if cur not in out:
        meta = {}
        try:
            with open(os.path.join(site, "state/generation-meta.json"), encoding="utf-8") as fh:
                meta = json.load(fh)
        except (OSError, ValueError):
            meta = {}
        summary = meta.get("summary") if meta.get("generation") == cur else ""
        out[cur] = {"date": dt.date.today(), "commit": None, "summary": clean_subject(summary or "")}
    return out, cur


def image_size(path):
    """(width, height) of a PNG or JPEG, read from its header."""
    with open(path, "rb") as fh:
        head = fh.read(32)
        if head[:8] == b"\x89PNG\r\n\x1a\n":
            return struct.unpack(">II", head[16:24])
        need(head[:2] == b"\xff\xd8", "not a PNG or JPEG: %s" % path)
        fh.seek(2)
        while True:
            marker = fh.read(2)
            need(len(marker) == 2 and marker[0] == 0xFF, "bad JPEG: %s" % path)
            if marker[1] in (0xD8, 0x01) or 0xD0 <= marker[1] <= 0xD7:
                continue
            length = struct.unpack(">H", fh.read(2))[0]
            if 0xC0 <= marker[1] <= 0xCF and marker[1] not in (0xC4, 0xC8, 0xCC):
                fh.read(1)
                h, w = struct.unpack(">HH", fh.read(4))
                return w, h
            fh.seek(length - 2, 1)


def cwebp():
    for p in CWEBP_PATHS:
        if os.access(p, os.X_OK):
            return p
    found = shutil.which("cwebp")
    need(found, "cwebp is not installed")
    return found


def web_copy(src, dst, dry):
    """Make the web-sized copy once; an existing non-empty copy is kept."""
    if os.path.isfile(dst) and os.path.getsize(dst) > 0:
        return True
    if dry:
        return True
    w, h = image_size(src)
    need(w > 0 and h > 0, "image has no size: %s" % src)
    ch = min(h, int(w * CROP_RATIO))
    tmp = dst + ".part"
    cp = subprocess.run([cwebp(), "-quiet", "-crop", "0", "0", str(w), str(ch), "-resize", str(WEB_WIDTH), "0",
                         "-q", "72", "-metadata", "none", src, "-o", tmp], capture_output=True, timeout=120)
    if cp.returncode != 0 or not os.path.isfile(tmp) or os.path.getsize(tmp) == 0:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise Fail("cwebp failed on %s: %s" % (src, cp.stderr.decode("utf-8", "replace")[-200:]))
    os.replace(tmp, dst)
    return True


def shoot(site, version, dry):
    """Render the working tree and keep its desktop shot as <date>-version-<N>.jpg."""
    name = "%s-version-%d.jpg" % (dt.date.today().isoformat(), version)
    dst = os.path.join(site, SHOTS, name)
    if dry:
        return name
    work = tempfile.mkdtemp(prefix=".archive-shot.", dir=os.path.join(site, SHOTS))
    try:
        env = dict(os.environ, ANDREMACEDO_RENDER_DIR=site, ANDREMACEDO_SELF_SHOT_DIR=work)
        cp = subprocess.run(["/bin/bash", os.path.join(site, "scripts/screenshot-local.sh")], env=env,
                            capture_output=True, timeout=300, stdin=subprocess.DEVNULL)
        shot = os.path.join(work, "andremacedo-self-desktop.jpg")
        need(cp.returncode == 0 and os.path.isfile(shot) and os.path.getsize(shot) > 0,
             "screenshot-local.sh failed (exit %d): %s" % (cp.returncode, cp.stderr.decode("utf-8", "replace")[-300:]))
        os.replace(shot, dst)
    finally:
        shutil.rmtree(work, ignore_errors=True)
    return name


def load_pictures(site, versions):
    """{version: (source file name, taken date)} for the newest shipped picture of each version."""
    shots = os.path.join(site, SHOTS)
    with open(os.path.join(shots, "manifest.json"), encoding="utf-8") as fh:
        manifest = json.load(fh)
    need(isinstance(manifest, list), "manifest.json is not a list")
    shipped = []
    for e in manifest:
        if not isinstance(e, dict) or e.get("unshipped_candidate") or e.get("candidate") is not None:
            continue
        name, commit = e.get("screenshot"), e.get("commit")
        if not isinstance(name, str) or "-fanout-" in name or "/" in name:
            continue
        if not isinstance(commit, str) or not re.match(r"\A[0-9a-f]{7,40}\Z", commit):
            continue
        if not os.path.isfile(os.path.join(shots, name)):
            continue
        shipped.append((str(e.get("timestamp", "")), name, commit))
    parents = cat_versions(site, sorted({c + "^" for _, _, c in shipped}))
    pics = {}
    for ts, name, commit in sorted(shipped):
        v = parents.get(commit + "^")
        if v in versions:
            pics[v] = (name, ts[:10])  # sorted by time: the newest picture of a version wins
    for name in sorted(os.listdir(shots)):
        m = OWN_SHOT_RE.match(name)
        if m and int(m.group(2)) in versions:
            pics[int(m.group(2))] = (name, m.group(1))  # a direct render beats an attributed one
    return pics


def exp_title(num, raw):
    t = html.unescape(re.sub(r"\s+", " ", raw)).strip()
    parts = [p.strip() for p in re.split(r"\s+[·—–/|-]\s+|\A%s\s*[·—–/|-]\s*" % num, t) if p.strip()]
    keep = [p for p in parts if p != num and "André Macedo" not in p
            and not re.fullmatch(r"(?i)experiment\s*\d+", p)]
    return keep[0] if keep else "Experiment %s" % num


def load_experiments(site):
    d = os.path.join(site, "experiments")
    out = []
    for name in sorted(os.listdir(d)):
        m = EXP_RE.match(name)
        if not m:
            continue
        with open(os.path.join(d, name), encoding="utf-8", errors="replace") as fh:
            head = fh.read(4096)
        tm = re.search(r"<title>([^<]*)</title>", head, re.I)
        out.append((m.group(1), exp_title(m.group(1), tm.group(1)) if tm else "Experiment %s" % m.group(1)))
    need(out, "no experiments found")
    return out


def fmt(d):
    return "%d %s %d" % (d.day, d.strftime("%b"), d.year)


CSS = """
:root{color-scheme:light}
*{box-sizing:border-box}
body{margin:0;background:#fff;color:#1a1a1a;font:17px/1.55 system-ui,-apple-system,"Segoe UI","Helvetica Neue",Arial,sans-serif}
main{max-width:1100px;margin:0 auto;padding:32px 20px 64px}
a{color:#0b57d0}
h1{font-size:2rem;line-height:1.2;margin:16px 0 8px}
h2{font-size:1.35rem;margin:48px 0 12px}
p.lead{max-width:42rem;color:#333}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:28px;margin:0;padding:0;list-style:none}
.grid img{display:block;width:100%;height:auto;border:1px solid #ddd;border-radius:6px;background:#f3f3f3}
.grid h3{font-size:1rem;margin:10px 0 2px}
.grid p,.text p{margin:0;color:#444;font-size:.95rem}
.live{font-weight:600;color:#0a7a3b}
.text{list-style:none;padding:0;margin:0;columns:2 320px;column-gap:32px}
.text li{break-inside:avoid;margin:0 0 12px}
.exps{list-style:none;padding:0;margin:0;columns:3 220px;column-gap:24px}
.exps li{margin:0 0 6px}
footer{margin-top:48px;color:#666;font-size:.9rem}
"""


def render(versions, live, pics, exps, built_at):
    esc = html.escape
    pictured = sorted((v for v in versions if v in pics), reverse=True)
    text = sorted((v for v in versions if v not in pics), reverse=True)
    out = ['<!DOCTYPE html>', '<html lang="en">', '<head>', '<meta charset="utf-8">',
           '<meta name="viewport" content="width=device-width, initial-scale=1">',
           '<title>Earlier versions · André Macedo</title>',
           '<meta name="description" content="Every version of andremacedo.com, newest first, and every experiment.">',
           '<link rel="icon" href="/favicon.svg" type="image/svg+xml">',
           '<style>%s</style>' % CSS.strip(), '</head>', '<body>', '<main>',
           '<p><a href="/">← Back to the current page</a></p>',
           '<h1>Earlier versions of this page</h1>',
           '<p class="lead">This site is redesigned by TELOS, my personal AI, about once a week. '
           'Here is every version on record, newest first: %d versions, %d of them with a picture, '
           'and all %d experiments.</p>' % (len(versions), len(pictured), len(exps)),
           '<h2>Versions with a picture</h2>', '<ul class="grid">']
    for i, v in enumerate(pictured):
        name, _taken = pics[v]
        info = versions[v]
        web = "%s/%s-web.webp" % (SHOTS, os.path.splitext(name)[0])
        w, h = WEB_WIDTH, int(WEB_WIDTH * CROP_RATIO)
        label = 'Version %d · %s%s' % (v, fmt(info["date"]), ' · <span class="live">live now</span>' if v == live else "")
        lazy = 'loading="eager" fetchpriority="high"' if i == 0 else 'loading="lazy"'
        out.append('<li><a href="/%s/%s"><img src="/%s" width="%d" height="%d" %s decoding="async" alt="Version %d of the page, %s"></a>'
                   % (SHOTS, esc(name), esc(web), w, h, lazy, v, fmt(info["date"])))
        out.append('<h3>%s</h3>' % label)
        if info["summary"]:
            out.append('<p>%s</p>' % esc(info["summary"]))
        out.append('</li>')
    out += ['</ul>', '<h2>Older versions, no picture kept</h2>',
            '<p class="lead">Pictures were only kept from September 2026. These earlier versions are listed by number and date.</p>',
            '<ul class="text">']
    for v in text:
        info = versions[v]
        label = 'Version %d · %s%s' % (v, fmt(info["date"]), ' · <span class="live">live now</span>' if v == live else "")
        out.append('<li><strong>%s</strong>%s</li>' % (label, '<p>%s</p>' % esc(info["summary"]) if info["summary"] else ""))
    out += ['</ul>', '<h2>Experiments</h2>',
            '<p class="lead">Small pages the site made along the way, each one a single idea you can play with.</p>',
            '<ul class="exps">']
    for num, title in reversed(exps):
        out.append('<li><a href="/experiments/%s">%s · %s</a></li>' % (num, num, esc(title)))
    out += ['</ul>', '<footer>Rebuilt from the site\'s own records on %s.</footer>' % fmt(built_at),
            '</main>', '</body>', '</html>', '']
    return "\n".join(out)


def build(site, do_shoot, dry):
    site = os.path.realpath(site)
    need(os.path.isfile(os.path.join(site, "index.html")), "not a site dir: %s" % site)
    versions, live = load_versions(site)
    pics = load_pictures(site, versions)
    shot_name = None
    if do_shoot and live not in pics:
        shot_name = shoot(site, live, dry)
        pics[live] = (shot_name, dt.date.today().isoformat())
    for v, (name, _) in pics.items():
        web_copy(os.path.join(site, SHOTS, name),
                 os.path.join(site, SHOTS, os.path.splitext(name)[0] + "-web.webp"), dry)
    exps = load_experiments(site)
    page = render(versions, live, pics, exps, dt.date.today())
    need(page.count("<img ") == len(pics), "picture count mismatch")
    need(page.count('href="/experiments/') == len(exps), "experiment count mismatch")
    summary = "build_archive: %d versions, %d pictured, live version %d %s, %d experiments" % (
        len(versions), len(pics), live, "pictured" if live in pics else "not pictured", len(exps))
    if dry:
        print(summary + " (dry run, nothing written)")
        return 0
    dst = os.path.join(site, "archive.html")
    fd, tmp = tempfile.mkstemp(prefix=".archive.html.", dir=site)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(page)
        os.chmod(tmp, 0o644)
        os.replace(tmp, dst)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise
    print(summary)
    return 0


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--site", required=True)
    ap.add_argument("--shoot", action="store_true", help="render the live version when it has no picture")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)
    try:
        return build(args.site, args.shoot, args.dry_run)
    except (Fail, OSError, ValueError, subprocess.SubprocessError) as exc:
        print("build_archive: FAILED, previous archive.html kept: %s" % exc, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
