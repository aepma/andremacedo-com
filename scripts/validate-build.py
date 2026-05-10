#!/usr/bin/env python3
"""validate-build.py — syntax-validate every inline <script> in index.html.

Usage: validate-build.py [INDEX_HTML]

Exits 0 if every inline <script> block parses cleanly under `node --check`.
Exits 1 otherwise, with a per-block report (file line, diagnostic, preview).

Why this exists: the andremacedo-creative agent generates JS as minified
single-line IIFEs and the gene-injector in apply_changes.py writes them
verbatim into index.html, then runner.sh commits and deploys. There is no
syntax check anywhere on that path. On 2026-05-07 (gen 107) the LLM produced
a pluck IIFE with one trailing `}` too many; the resulting Uncaught
SyntaxError killed the entire main <script> block (lines 745-1224) for
about five hours.

This script is the load-bearing fix: runner.sh invokes it after
apply_changes.py and before `git commit`, so a parse error halts the run
cleanly instead of landing in production.

See knowledge-base/personal/raw/2026-05-07-issue-runner-gene-injector-no-js-validation.md.
"""
import os
import re
import subprocess
import sys
import tempfile

DEFAULT_HTML = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "index.html",
)

SCRIPT_OPEN_RE = re.compile(r"(?s)<script\b([^>]*)>")
SCRIPT_CLOSE = "</script>"
SRC_ATTR_RE = re.compile(r"\bsrc\s*=", re.IGNORECASE)


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


def check_mobile_scaffold(html):
    """Assert that the mobile scaffold style block is present and well-formed.

    Returns (ok, diagnostic). ok=True if the scaffold is intact.
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


def main(argv):
    path = argv[1] if len(argv) > 1 else DEFAULT_HTML
    if not os.path.isfile(path):
        sys.stderr.write(f"validate-build: file not found: {path}\n")
        return 2
    with open(path, encoding="utf-8") as f:
        html = f.read()

    # Static assertion: mobile scaffold must be present and well-formed
    scaffold_ok, scaffold_diag = check_mobile_scaffold(html)
    if not scaffold_ok:
        sys.stderr.write(f"validate-build: FAIL — {scaffold_diag}\n")
        return 1
    sys.stderr.write("validate-build: mobile-scaffold present\n")

    blocks = list(find_inline_scripts(html))
    if not blocks:
        sys.stderr.write(
            f"validate-build: WARN no inline <script> blocks found in {path}\n"
        )
        return 0

    failures = []
    for i, (start_line, body) in enumerate(blocks, 1):
        ok, diag = check_block(body)
        if not ok:
            preview = body.strip().splitlines()[0] if body.strip() else ""
            if len(preview) > 140:
                preview = preview[:137] + "..."
            failures.append(
                {
                    "index": i,
                    "preview": preview,
                    "diag": diag,
                    "html_line": start_line,
                }
            )

    if failures:
        sys.stderr.write(
            "validate-build: FAIL — inline <script> blocks did not parse:\n"
        )
        for f in failures:
            sys.stderr.write(
                f"\n  block #{f['index']} (starts at {path}:{f['html_line']}):\n"
            )
            sys.stderr.write("  diagnostic:\n")
            for line in f["diag"].splitlines():
                sys.stderr.write(f"    {line}\n")
            if f["preview"]:
                sys.stderr.write(f"  preview: {f['preview']}\n")
        sys.stderr.write(
            f"\nvalidate-build: {len(failures)} of {len(blocks)} block(s) failed\n"
        )
        return 1

    sys.stderr.write(
        f"validate-build: OK — mobile-scaffold present, {len(blocks)} inline <script> block(s) parsed\n"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
