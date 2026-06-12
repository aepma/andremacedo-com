#!/usr/bin/env python3
"""validate-build.py — static enforcement of INVARIANTS.md.

Usage: validate-build.py [INDEX_HTML]

Exits 0 if every statically checkable invariant in INVARIANTS.md (repo root)
holds. Exits 1 otherwise, with a per-invariant report. Exits 2 on usage error.

This is the build gate of the invariants contract: SOUL.md is the law,
INVARIANTS.md is the building code, this script is the inspector. runner.sh
invokes it after apply_changes.py and before `git commit`, so a violation
halts the run cleanly instead of landing in production.

Every check function here maps to an invariant in INVARIANTS.md (INV-N).
Invariants marked "prompt-level" there have no function here by design.
History that earned each check lives in INVARIANTS.md and in the docstrings
below; new checks are added by amendment (rule + why + enforcement in the
same commit), not by patching after an outage.
"""
import os
import re
import subprocess
import sys
import tempfile

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_HTML = os.path.join(REPO_ROOT, "index.html")

SCRIPT_OPEN_RE = re.compile(r"(?s)<script\b([^>]*)>")
SCRIPT_CLOSE = "</script>"
SRC_ATTR_RE = re.compile(r"\bsrc\s*=", re.IGNORECASE)

PAGE_WEIGHT_BUDGET_BYTES = 900_000  # INV-8: ~4s first paint at ~1.6 Mbps ≈ 800 KB

AUTOPLAY_ATTR_RE = re.compile(r"<(?:audio|video)\b[^>]*\bautoplay\b", re.IGNORECASE)
AUTOPLAY_JS_RE = re.compile(r"\.autoplay\s*=\s*true")
AUDIO_CONSTRUCT_RE = re.compile(
    r"new\s*\(?\s*(?:window\.)?(?:webkit)?AudioContext|new\s+Audio\s*\(")
GESTURE_LISTENER_RE = re.compile(
    r"addEventListener\s*\(\s*['\"](?:click|dblclick|pointerdown|pointerup|"
    r"touchstart|touchend|mousedown|mouseup|keydown|keyup|keypress)['\"]")

TRACKER_MARKERS = (
    "googletagmanager.com",
    "google-analytics.com",
    "connect.facebook.net",
    "gtag(",
    "fbq(",
    "hotjar",
    "clarity.ms",
)


def find_inline_scripts(html):
    """Yield (start_line, body) for every inline <script> block.

    Skips <script src="...">. Line numbers are 1-indexed against the source
    file. Bodies are returned verbatim, no whitespace trimming.
    """
    pos = 0
    while True:
        m = SCRIPT_OPEN_RE.search(html, pos)
        if not m:
            return
        attrs = m.group(1)
        if SRC_ATTR_RE.search(attrs):
            pos = m.end()
            continue
        body_start = m.end()
        close_idx = html.find(SCRIPT_CLOSE, body_start)
        if close_idx < 0:
            sys.stderr.write(
                "validate-build: unterminated <script> tag near offset "
                f"{m.start()}; aborting\n"
            )
            return
        body = html[body_start:close_idx]
        start_line = html.count("\n", 0, m.start()) + 1
        yield start_line, body
        pos = close_idx + len(SCRIPT_CLOSE)


def strip_nonrendered(html):
    """Remove script/style blocks and HTML comments — what's left is
    (approximately) markup a visitor can see."""
    html = re.sub(r"(?is)<script\b[^>]*>.*?</script>", "", html)
    html = re.sub(r"(?is)<style\b[^>]*>.*?</style>", "", html)
    html = re.sub(r"(?s)<!--.*?-->", "", html)
    return html


# ── INV-1: hero visible above the fold on load ─────────────────────


def check_hero_visibility(html, path):
    """INV-1: the overlay-center hero is visible at parse time.

    Three failure classes, all static (no browser):

    1. Stacking lift (the gen-187 lesson, 2026-06-12): #overlay hosts
       fixed-position canvases at z-index:0 (bench-canvas, sed-fall) that
       paint ABOVE static siblings; bench-canvas accumulates rgba black per
       frame and blacks out anything under it within ~0.5s. The hero
       container therefore MUST carry position:relative|absolute|sticky and
       z-index >= 1. Gen 187 dropped exactly this and the hero "faded out
       instantly" behind the canvas.

    2. Opacity at parse time (regression class, never yet observed): the
       hero rule, the hero inline style, or the #overlay base rule must not
       set opacity < 1, and must not reference an @keyframes animation whose
       body touches opacity. Initial visibility belongs to CSS; only the
       scroll handler may fade the overlay at runtime.

    3. Empty hero: the overlay-center section must contain readable text —
       a structurally present but textless hero fails INV-1/INV-2 just as
       hard as an occluded one.
    """
    sec = re.search(
        r"<!--\s*@section:overlay-center:start\s*-->(.*?)<!--\s*@section:overlay-center:end\s*-->",
        html, re.S)
    if not sec:
        return False, "hero-visibility: overlay-center section markers not found"
    markup = sec.group(1)

    text = re.sub(r"<[^>]+>", " ", strip_nonrendered(markup)).strip()
    if not text:
        return False, ("hero-visibility: overlay-center section contains no readable text; "
                       "the hero/self-intro must be present, not just the section markers")

    el = re.search(r"<(\w+)\b([^>]*)>", markup)
    if not el:
        return False, "hero-visibility: no element found inside overlay-center section"
    attrs = el.group(2)

    style_attr = re.search(r"style\s*=\s*['\"]([^'\"]*)['\"]", attrs)
    if style_attr and re.search(r"opacity\s*:\s*0(?:\.\d+)?(?![\d.])", style_attr.group(1)):
        return False, ("hero-visibility: hero element inline style sets opacity < 1 "
                       f"({style_attr.group(1)!r}); hero must be fully visible at parse time")

    cls = re.search(r"class\s*=\s*['\"]([^'\"]+)['\"]", attrs)
    if not cls:
        return False, "hero-visibility: overlay-center first element has no class; cannot locate its CSS rule"
    hero_classes = cls.group(1).split()

    rule_body = None
    rule_class = None
    for c in hero_classes:
        m = re.search(r"\." + re.escape(c) + r"\s*{([^}]*)}", html)
        if m:
            rule_body, rule_class = m.group(1), c
            break
    if rule_body is None:
        return False, ("hero-visibility: no CSS rule found for hero classes "
                       f"{hero_classes}; the hero container must declare "
                       "position:relative and z-index >= 1")

    pos = re.search(r"position\s*:\s*(relative|absolute|sticky|fixed)", rule_body)
    z = re.search(r"z-index\s*:\s*(-?\d+)", rule_body)
    if not pos or not z or int(z.group(1)) < 1:
        return False, (f"hero-visibility: .{rule_class} must carry position:relative "
                       "(or absolute/sticky) AND z-index >= 1 so the hero paints above "
                       "the fixed z-index:0 canvases inside #overlay (bench-canvas "
                       "accumulates black and occludes static siblings — gen-187 "
                       f"instant-fade regression). Current rule: {rule_body.strip()!r}")

    op = re.search(r"opacity\s*:\s*(0(?:\.\d+)?)(?![\d.])", rule_body)
    if op:
        return False, (f"hero-visibility: .{rule_class} sets initial opacity {op.group(1)}; "
                       "hero must be fully visible at parse time")

    overlay_rules = re.findall(r"#overlay\s*{([^}]*)}", html)
    for body in overlay_rules:
        if re.search(r"opacity\s*:\s*0(?:\.\d+)?(?![\d.])", body):
            return False, "hero-visibility: #overlay base rule sets initial opacity < 1"

    anim_sources = [("hero rule .%s" % rule_class, rule_body)] + [
        ("#overlay rule", b) for b in overlay_rules]
    for label, body in anim_sources:
        anim = re.search(r"animation(?:-name)?\s*:\s*([^;}]+)", body)
        if not anim:
            continue
        for token in re.split(r"[\s,]+", anim.group(1).strip()):
            kf = re.search(r"@keyframes\s+" + re.escape(token) + r"\s*{(.*?)}\s*}", html, re.S)
            if kf and "opacity" in kf.group(1):
                return False, (f"hero-visibility: {label} runs animation {token!r} whose "
                               "@keyframes touch opacity; the hero/overlay must not fade on load")

    return True, ""


# ── INV-3: Andre's name visible ────────────────────────────────────


def check_name_visible(html, path):
    """INV-3: the literal text "Andre Macedo" appears in rendered markup
    (outside scripts, styles, and comments)."""
    if "Andre Macedo" in strip_nonrendered(html):
        return True, ""
    return False, ('name-visible: "Andre Macedo" not found in rendered markup '
                   "(scripts/styles/comments excluded); SOUL.md requires the name "
                   "always visible")


# ── INV-4: single HTML file, no build step ─────────────────────────


def check_single_file(html, path):
    """INV-4: complete self-contained HTML document, no bundler output
    references, no build script in package.json."""
    if not re.match(r"\s*<!doctype\s+html", html, re.IGNORECASE):
        return False, "single-file: index.html does not start with <!DOCTYPE html>"
    if "</html>" not in html.lower():
        return False, "single-file: no closing </html>; document is truncated or partial"

    bundler_src = re.search(
        r"""(?:src|href)\s*=\s*["'](?:\.?/)?(?:dist|build|node_modules|src)/[^"']*["']""",
        html, re.IGNORECASE)
    if bundler_src:
        return False, (f"single-file: reference to bundler output {bundler_src.group(0)!r}; "
                       "the site must remain a single HTML file with no build step")

    pkg_path = os.path.join(REPO_ROOT, "package.json")
    if os.path.isfile(pkg_path):
        import json
        try:
            with open(pkg_path, encoding="utf-8") as f:
                pkg = json.load(f)
        except (OSError, ValueError) as e:
            return False, f"single-file: package.json unreadable ({e})"
        if "build" in (pkg.get("scripts") or {}):
            return False, ("single-file: package.json defines a build script; "
                           "no build step is permitted")
    return True, ""


# ── INV-5: mobile scaffold + interaction invariants intact ─────────


def check_mobile_scaffold(html, path):
    """INV-5a: the mobile scaffold style block is present and well-formed.

    Requirements:
      - '<style id="mobile-scaffold">' must be present
      - a matching '</style>' must follow
      - the block must contain at least one @media rule with max-width <= 600
    """
    start_tag = '<style id="mobile-scaffold">'
    if start_tag not in html:
        return False, "mobile-scaffold missing or malformed: <style id=\"mobile-scaffold\"> not found"

    start_idx = html.index(start_tag) + len(start_tag)
    end_idx = html.find('</style>', start_idx)
    if end_idx < 0:
        return False, "mobile-scaffold missing or malformed: no closing </style> after scaffold open tag"

    block = html[start_idx:end_idx]

    # Must contain @media with max-width and a value <= 600
    media_match = re.search(r'@media[^{]*max-width\s*:\s*(\d+)', block)
    if not media_match:
        return False, "mobile-scaffold missing or malformed: no @media max-width rule found in scaffold block"

    width_val = int(media_match.group(1))
    if width_val > 600:
        return False, f"mobile-scaffold missing or malformed: @media max-width is {width_val}px (must be <= 600)"

    return True, ""


def check_mobile_interaction_invariants(html, path):
    """INV-5b: the mobile-interaction-invariants script block is present and intact.

    Requirements:
      - '<script id="mobile-interaction-invariants">' must be present
      - a matching '</script>' must follow
      - the block must contain markers for all three components
    """
    open_tag = '<script id="mobile-interaction-invariants">'
    if open_tag not in html:
        return False, 'mobile-interaction-invariants missing: <script id="mobile-interaction-invariants"> not found'

    start_idx = html.index(open_tag) + len(open_tag)
    end_idx = html.find('</script>', start_idx)
    if end_idx < 0:
        return False, 'mobile-interaction-invariants missing: no closing </script> after open tag'

    block = html[start_idx:end_idx]
    for component in ('COMPONENT 1', 'COMPONENT 2', 'COMPONENT 3'):
        if component not in block:
            return False, f'mobile-interaction-invariants incomplete: {component!r} marker missing from block'

    return True, ""


# ── INV-6: WebGL swarm panel present and alive ─────────────────────


def check_swarm_panel(html, path):
    """INV-6: an element with id="swarmPanel" exists AND is referenced from
    inline JS (the static proxy for "alive" — a dead unreferenced div fails)."""
    if not re.search(r"""<\w+\b[^>]*\bid\s*=\s*["']swarmPanel["']""", html):
        return False, ('swarm-panel: no element with id="swarmPanel"; the WebGL swarm '
                       "panel is the nervous system and persists across generations")
    for _, body in find_inline_scripts(html):
        if "swarmPanel" in body:
            return True, ""
    return False, ("swarm-panel: #swarmPanel element exists but no inline script "
                   "references it; the panel must be driven, not a dead div")


# ── INV-7: all inline JavaScript parses ────────────────────────────


def check_block(body):
    """Return (ok, diagnostic). ok=True if `node --check` accepts the body."""
    if not body.strip():
        return True, ""
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".js", delete=False, encoding="utf-8"
    ) as tf:
        tf.write(body)
        tmp = tf.name
    try:
        proc = subprocess.run(
            ["node", "--check", tmp],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if proc.returncode == 0:
            return True, ""
        return False, proc.stderr.strip() or proc.stdout.strip()
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass


def check_inline_scripts(html, path):
    """INV-7: every inline <script> block parses under `node --check`.

    Gen 107 (2026-05-07): one trailing `}` too many in a generated IIFE killed
    the entire main <script> block (lines 745-1224) for about five hours.
    See knowledge-base/personal/raw/2026-05-07-issue-runner-gene-injector-no-js-validation.md.
    """
    blocks = list(find_inline_scripts(html))
    if not blocks:
        return True, f"WARN no inline <script> blocks found in {path}"

    failures = []
    for i, (start_line, body) in enumerate(blocks, 1):
        ok, diag = check_block(body)
        if not ok:
            preview = body.strip().splitlines()[0] if body.strip() else ""
            if len(preview) > 140:
                preview = preview[:137] + "..."
            failures.append((i, start_line, diag, preview))

    if failures:
        lines = [f"{len(failures)} of {len(blocks)} inline <script> block(s) failed to parse:"]
        for idx, start_line, diag, preview in failures:
            lines.append(f"  block #{idx} (starts at {path}:{start_line}):")
            for d in diag.splitlines():
                lines.append(f"    {d}")
            if preview:
                lines.append(f"    preview: {preview}")
        return False, "\n".join(lines)

    return True, f"{len(blocks)} inline <script> block(s) parsed"


# ── INV-8: first-paint budget (page-weight proxy) ──────────────────


def check_page_weight(html, path):
    """INV-8: index.html stays at or under the byte budget — the static proxy
    for SOUL.md's "under 4 seconds to first paint"."""
    size = len(html.encode("utf-8"))
    if size > PAGE_WEIGHT_BUDGET_BYTES:
        return False, (f"page-weight: {size:,} bytes exceeds the "
                       f"{PAGE_WEIGHT_BUDGET_BYTES:,}-byte budget (first-paint proxy); "
                       "kill something before growing")
    return True, f"{size:,} / {PAGE_WEIGHT_BUDGET_BYTES:,} bytes"


# ── INV-10: deploys go to production branch main only ──────────────


def check_deploy_branch(html, path):
    """INV-10: every --branch flag in deploy.sh and scripts/runner.sh says
    `main`. Cloudflare Pages silently creates a preview URL for any other
    branch (including `production`) instead of deploying to production."""
    candidates = [
        os.path.join(REPO_ROOT, "deploy.sh"),
        os.path.join(REPO_ROOT, "scripts", "runner.sh"),
    ]
    found_any = False
    for script in candidates:
        if not os.path.isfile(script):
            continue
        with open(script, encoding="utf-8") as f:
            content = f.read()
        for m in re.finditer(r"--branch[= ]+[\"']?([\w./-]+)[\"']?", content):
            found_any = True
            if m.group(1) != "main":
                return False, (f"deploy-branch: {os.path.basename(script)} deploys with "
                               f"--branch {m.group(1)!r}; only 'main' deploys to "
                               "production (anything else is a silent preview URL)")
    if not found_any:
        return False, ("deploy-branch: no --branch flag found in deploy.sh or "
                       "scripts/runner.sh; the production deploy path must pin "
                       "--branch main explicitly")
    return True, ""


# ── INV-11: no commercial surface ──────────────────────────────────


def check_no_commercial_surface(html, path):
    """INV-11: no forms, no known tracker scripts. SOUL.md: no commercial
    content, no ads, no tracking, no data collection."""
    if re.search(r"<form\b", html, re.IGNORECASE):
        return False, "no-commercial-surface: <form> element found; no forms, no data collection"
    lowered = html.lower()
    for marker in TRACKER_MARKERS:
        if marker in lowered:
            return False, f"no-commercial-surface: tracker marker {marker!r} found; no tracking"
    return True, ""


# ── INV-12: sound is opt-in — never autoplay, audio behind gesture ─


def check_no_autoplay(html, path):
    """INV-12a: no autoplay. Neither an `autoplay` attribute on <audio>/<video>
    nor a script assignment `.autoplay = true` may appear. SOUL.md (2026-06-12
    sound-organ amendment): sound is always opt-in — a visitor gesture starts
    it, never autoplay — always stoppable, and silent by default."""
    m = AUTOPLAY_ATTR_RE.search(html)
    if m:
        line = html.count("\n", 0, m.start()) + 1
        return False, (f"no-autoplay: autoplay attribute found at {path}:{line}; "
                       "sound is opt-in behind a visitor gesture, never autoplay")
    for start_line, body in find_inline_scripts(html):
        am = AUTOPLAY_JS_RE.search(body)
        if am:
            line = start_line + body.count("\n", 0, am.start())
            return False, (f"no-autoplay: script sets .autoplay = true near {path}:{line}; "
                           "sound is opt-in behind a visitor gesture, never autoplay")
    return True, ""


def check_audio_behind_gesture(html, path):
    """INV-12b: every inline <script> block that constructs an audio source
    (AudioContext / webkitAudioContext / new Audio) must also wire at least one
    visitor-gesture listener (click/pointer/touch/key). Static proxy for
    "audio starts only on gesture": a block that builds audio with no gesture
    wiring at all has no opt-in path. The protected
    mobile-interaction-invariants block (INV-5, COMPONENT 2) provides the
    fleet-wide gesture-resume substrate; creative audio must still carry its
    own gesture gate."""
    offenders = []
    for start_line, body in find_inline_scripts(html):
        if AUDIO_CONSTRUCT_RE.search(body) and not GESTURE_LISTENER_RE.search(body):
            offenders.append(start_line)
    if offenders:
        where = ", ".join(f"{path}:{n}" for n in offenders)
        return False, ("audio-behind-gesture: inline script block(s) starting at "
                       f"{where} construct audio but register no visitor-gesture "
                       "listener; audio must start behind a gesture, lazy-loaded "
                       "on first gesture")
    return True, ""


# ── The contract registry: INVARIANTS.md ←→ enforcement ───────────
# One row per statically checkable invariant. INV-2 (self-intro wording),
# INV-9 (legibility in context), and INV-13 (scene as full instrument within
# the perf law — aliveness via INV-6, budget via INV-8) are prompt-level /
# runtime-gated — see INVARIANTS.md for their enforcement story.
CHECKS = [
    ("INV-1", "hero-visibility", check_hero_visibility),
    ("INV-3", "name-visible", check_name_visible),
    ("INV-4", "single-file", check_single_file),
    ("INV-5", "mobile-scaffold", check_mobile_scaffold),
    ("INV-5", "mobile-interaction-invariants", check_mobile_interaction_invariants),
    ("INV-6", "swarm-panel", check_swarm_panel),
    ("INV-7", "inline-js-parse", check_inline_scripts),
    ("INV-8", "page-weight", check_page_weight),
    ("INV-10", "deploy-branch", check_deploy_branch),
    ("INV-11", "no-commercial-surface", check_no_commercial_surface),
    ("INV-12", "no-autoplay", check_no_autoplay),
    ("INV-12", "audio-behind-gesture", check_audio_behind_gesture),
]


def main(argv):
    path = argv[1] if len(argv) > 1 else DEFAULT_HTML
    if not os.path.isfile(path):
        sys.stderr.write(f"validate-build: file not found: {path}\n")
        return 2
    with open(path, encoding="utf-8") as f:
        html = f.read()

    failures = 0
    for inv_id, name, fn in CHECKS:
        ok, diag = fn(html, path)
        if ok:
            note = f" ({diag})" if diag else ""
            sys.stderr.write(f"validate-build: {inv_id} {name} OK{note}\n")
        else:
            failures += 1
            sys.stderr.write(f"validate-build: FAIL {inv_id} {name} — {diag}\n")

    if failures:
        sys.stderr.write(
            f"\nvalidate-build: {failures} invariant check(s) FAILED — see INVARIANTS.md\n"
        )
        return 1

    sys.stderr.write("validate-build: OK — all static invariants hold (INVARIANTS.md)\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
