#!/usr/bin/env python3
"""craft-judge.py — DUAL adversarial craft judge for andremacedo.com (taste layer).

Fresh-eyes verification of CRAFT, the external/adversarial counterpart to the
agent's (untrusted) self-reported craft_check. Two INDEPENDENT critics from
DIFFERENT model families judge the same rendered screenshot(s) against the same
rubric — the point is uncorrelated blind spots, not raw capability:

  Critic A = claude-opus-4-8-oauth
  Critic B = grok-4-1-fast-reasoning   (different family)
             fallback gemini-3.5-flash ONLY if B is slow/flaky (never gemini-2.5-pro)

Combination is fail-closed with a MARGIN RULE: SHIP if BOTH critics return
not-slop AND each clears the base threshold (both_passed), OR if exactly ONE
critic passes and its overall clears the higher --margin (margin_override — a
lone STRONG pass overrides the other critic's slop veto). It FAILS when both
flag slop, when the sole passing critic is below the margin, or when a critic
cannot be scored at all (ERROR is never overridden). A FAILED verdict at the
runner gate reverts the working tree and keeps the previous deploy live,
exactly like a contrast failure.

Both judge the SCREENSHOT — never the agent's stated intentions. Model IDs are
verified against the live proxy (curl localhost:4000/v1/models) before wiring,
never assumed from memory.

The two critics run CONCURRENTLY: they are independent by construction, and run
serially their budgets summed past any sane wrapper bound. The wall-clock bound a
wrapper must allow is derived here from the live budgets (--print-wall-budget)
and asserted here when the wrapper hands it back (--wall-budget), so the two
numbers can never drift apart again.

Exit codes:  0 = PASS (both critics cleared)
             1 = FAIL (either critic flagged slop or scored below threshold)
             2 = ERROR (a critic could not be obtained, or the wrapper's wall
                 bound is below this judge's worst case — fail-closed at the gate)

Any OTHER exit means this judge never reached emit(): it was killed or it
crashed, and --json-out was never written. epoch_review.py treats that as a run
that produced no verdict and no scores.
"""
import argparse, base64, concurrent.futures, json, math, os, sys, urllib.request

DEFAULT_URL = "http://localhost:4000/v1/chat/completions"

# Everything outside the per-request timeouts: interpreter start, reading and
# base64-encoding two screenshots, proxy connect, JSON parse, writing --json-out.
CRITIC_OVERHEAD_SECONDS = 30.0

# The per-critic budgets, in ONE place, because the wrapper's wall bound is
# derived from them (see wall_budget_seconds) and the two must never drift.
#
# Critic A's budget was 120s. Measured 2026-09-02, judging the known-good fixture
# through the local proxy, claude-opus-4-8-oauth took 152.4s to return: the
# budget had become smaller than the work, so critic A could only ever time out
# and the gate could only ever fail closed. Raised to 240s, which is headroom
# over that measurement rather than a fit to it. Read the latency again before
# tightening this: the failure mode of too-tight is a discarded weekly cycle,
# the failure mode of too-loose is a slower gate.
TIMEOUT_A_DEFAULT = 240.0
TIMEOUT_B_DEFAULT = 90.0        # grok reasoning can be slower; beyond this -> fallback
RETRIES_DEFAULT = 2             # attempts, not extra tries


def proxy_api_key():
    """Bearer key for the local litellm proxy (master-key auth activated
    2026-07-24, quota-governor phase 2). Prefer ~/.telos/.env (canonical,
    current) over the process env, which can carry a stale key."""
    env_file = os.path.expanduser("~/.telos/.env")
    try:
        with open(env_file) as f:
            for line in f:
                line = line.strip()
                if line.startswith("LITELLM_MASTER_KEY="):
                    return line.split("=", 1)[1].strip().strip('"').strip("'")
    except OSError:
        pass
    return os.environ.get("LITELLM_MASTER_KEY")
CRITIC_A = "claude-opus-4-8-oauth"
CRITIC_B = "grok-4-1-fast-reasoning"
CRITIC_B_FALLBACK = "gemini-3.5-flash"          # never gemini-2.5-pro (deprecated)
HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_RUBRIC = os.path.join(HERE, "craft-rubric.md")

AXES = ["type_scale", "spacing_system", "focal_hierarchy", "restraint",
        "hero", "composition", "type_craft", "color"]

SYSTEM = (
    "You are an adversarial design-engineering critic with fresh eyes and zero "
    "stake in this page. Assume it is mediocre, default-grade AI slop until the "
    "pixels prove otherwise. Your job is to find what is generic, safe, "
    "derivative, or template-grade and name it specifically. You judge ONLY the "
    "rendered screenshot — never any stated intent, caption, or description. "
    "Vague praise is worthless. 'Clean and inoffensive' is itself the slop and "
    "must FAIL. Be stingy: a high score must be earned by a visible, decisive "
    "aesthetic move a templated generator would not make. Output JSON only — no "
    "prose before or after, no code fences."
)


def wall_budget_seconds(timeout_a, timeout_b, retries, overhead=CRITIC_OVERHEAD_SECONDS):
    """The wall-clock bound a wrapper must allow this judge, derived from the same
    numbers the judge actually runs on.

    Worst case per critic, with every retry exhausted:

        critic A : retries * timeout_a
        critic B : retries * timeout_b            (grok)
                 + retries * timeout_a            (fallback, run at A's budget)

    The two critics run CONCURRENTLY (see main), so the pair costs max(A, B),
    not their sum, plus `overhead`.

    This function exists because the relationship was previously a hardcoded 240
    in runner.sh against per-critic budgets summing to 660, and on 2026-08-31 it
    killed the weekly run at 240s before the judge reached a verdict. The wrapper
    now reads this number at runtime (--print-wall-budget) and hands it back
    (--wall-budget) so the judge asserts the relationship instead of trusting it.
    """
    assert timeout_a > 0, "critic A budget must be positive"
    assert timeout_b > 0, "critic B budget must be positive"
    assert retries >= 1, "retries is an attempt count and must be at least 1"
    assert overhead >= 0, "overhead must not be negative"
    a_path = retries * timeout_a
    b_path = retries * timeout_b + retries * timeout_a
    return int(math.ceil(max(a_path, b_path) + overhead))


def wall_budget_derivation(timeout_a, timeout_b, retries, overhead=CRITIC_OVERHEAD_SECONDS):
    """Human-readable arithmetic behind wall_budget_seconds, for stderr and logs."""
    a_path = retries * timeout_a
    b_path = retries * timeout_b + retries * timeout_a
    return ("critic A worst case {r}x{ta}s = {a}s; critic B worst case {r}x{tb}s + "
            "fallback {r}x{ta}s = {b}s; critics run concurrently so the pair costs "
            "max({a}, {b}) = {m}s; + {o}s overhead = {total}s".format(
                r=retries, ta=timeout_a, tb=timeout_b, a=a_path, b=b_path,
                m=max(a_path, b_path), o=overhead,
                total=wall_budget_seconds(timeout_a, timeout_b, retries, overhead)))


def b64_data_url(path):
    with open(path, "rb") as f:
        raw = f.read()
    ext = os.path.splitext(path)[1].lower()
    mime = "image/png" if ext == ".png" else "image/jpeg"
    return f"data:{mime};base64," + base64.b64encode(raw).decode("ascii")


def build_user_content(rubric, desktop, mobile):
    parts = [{
        "type": "text",
        "text": (
            "Judge this andremacedo.com generation against the rubric below. "
            "andremacedo.com is a living art organism that an AI rebuilds — it is "
            "NOT a SaaS landing page; SaaS-landing shapes are slop here. Primary "
            "judgment is the DESKTOP render. If a mobile render follows, confirm "
            "the craft holds responsively (do not let mobile alone rescue a weak "
            "desktop).\n\nScore every axis 0-10, be stingy, and set is_slop=true "
            "if ANY cardinal slop state in the rubric is present. Return JSON "
            "EXACTLY matching the output contract — keys: axes (the 8 named axes), "
            "overall (number), is_slop (boolean), findings (array of specific "
            "strings), what_works (array, may be empty), reasoning (string).\n\n"
            "===== RUBRIC =====\n" + rubric + "\n===== END RUBRIC =====\n\n"
            "DESKTOP render follows:"
        ),
    }]
    parts.append({"type": "image_url", "image_url": {"url": b64_data_url(desktop)}})
    if mobile and os.path.isfile(mobile):
        parts.append({"type": "text", "text": "MOBILE render follows:"})
        parts.append({"type": "image_url", "image_url": {"url": b64_data_url(mobile)}})
    return parts


def call_proxy(url, model, system, user_content, timeout, retries):
    payload = json.dumps({
        "model": model,
        "messages": [{"role": "system", "content": system},
                     {"role": "user", "content": user_content}],
        "temperature": 0.2,
    }).encode("utf-8")
    last = None
    for _ in range(retries):
        try:
            headers = {"Content-Type": "application/json"}
            key = proxy_api_key()
            if key:
                headers["Authorization"] = f"Bearer {key}"
            req = urllib.request.Request(
                url, data=payload, headers=headers)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                body = json.loads(r.read().decode("utf-8"))
            return body["choices"][0]["message"]["content"]
        except Exception as e:  # noqa: BLE001 — proxy/network/parse all fail-closed
            last = e
    raise RuntimeError(f"{model}: proxy call failed after {retries} attempt(s): {last}")


def extract_json(text):
    t = text.strip()
    if t.startswith("```"):
        t = t.split("```", 2)[1]
        if t.lstrip().lower().startswith("json"):
            t = t.lstrip()[4:]
    try:
        return json.loads(t)
    except Exception:
        pass
    start = t.find("{")
    if start < 0:
        raise ValueError("no JSON object in model output")
    depth = 0
    for i in range(start, len(t)):
        if t[i] == "{":
            depth += 1
        elif t[i] == "}":
            depth -= 1
            if depth == 0:
                return json.loads(t[start:i + 1])
    raise ValueError("unbalanced JSON in model output")


def normalize(v):
    axes = {a: float(v.get("axes", {}).get(a, 0) or 0) for a in AXES}
    overall = v.get("overall")
    overall = float(overall) if overall is not None else round(sum(axes.values()) / len(axes), 2)
    return {
        "axes": axes,
        "overall": overall,
        "is_slop": bool(v.get("is_slop", True)),  # default-slop if model omits it
        "findings": [str(x) for x in (v.get("findings") or [])],
        "what_works": [str(x) for x in (v.get("what_works") or [])],
        "reasoning": str(v.get("reasoning", "")),
    }


def judge_one(url, model, content, timeout, retries):
    """Run a single critic; returns a normalized verdict or raises."""
    return normalize(extract_json(call_proxy(url, model, SYSTEM, content, timeout, retries)))


def critic_passed(v, threshold):
    """A critic passes iff it did NOT flag slop AND cleared the base threshold."""
    return (not v["is_slop"]) and v["overall"] >= threshold


def decide_gate(a, b, threshold, margin):
    """Pure, testable combination rule (the 'margin rule').

    a / b are normalized critic verdicts, or None if a critic could not be
    obtained. Returns a dict: {passed, gate_rule[, override_label, override_overall]}.

      - both_passed    : both critics pass (unchanged happy path)      -> SHIP
      - margin_override: exactly one critic passed AND its overall is   -> SHIP
                         at/above the margin (a lone STRONG pass beats
                         the other critic's slop veto)
      - failed         : anything else                                 -> FAIL

    Fail-closed: if EITHER critic is unobtainable (None), the gate fails and is
    NEVER overridden by the other critic's pass — an ERROR is not a veto that a
    margin can beat, it is an inability to verify craft at all.
    """
    if a is None or b is None:
        return {"passed": False, "gate_rule": "failed"}
    a_pass = critic_passed(a, threshold)
    b_pass = critic_passed(b, threshold)
    if a_pass and b_pass:
        return {"passed": True, "gate_rule": "both_passed"}
    if a_pass ^ b_pass:  # exactly one passed
        label, v = ("A", a) if a_pass else ("B", b)
        if v["overall"] >= margin:
            return {"passed": True, "gate_rule": "margin_override",
                    "override_label": label, "override_overall": v["overall"]}
    return {"passed": False, "gate_rule": "failed"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--desktop")
    ap.add_argument("--mobile")
    ap.add_argument("--rubric", default=DEFAULT_RUBRIC)
    ap.add_argument("--url", default=DEFAULT_URL)
    ap.add_argument("--critic-a", default=CRITIC_A)
    ap.add_argument("--critic-b", default=CRITIC_B)
    ap.add_argument("--critic-b-fallback", default=CRITIC_B_FALLBACK)
    ap.add_argument("--threshold", type=float, default=7.0)
    ap.add_argument("--margin", type=float, default=7.3,
                    help="a lone passing critic must clear this (> threshold) to "
                         "override the other critic's slop veto and ship")
    ap.add_argument("--timeout-a", type=float, default=TIMEOUT_A_DEFAULT)
    ap.add_argument("--timeout-b", type=float, default=TIMEOUT_B_DEFAULT)
    ap.add_argument("--retries", type=int, default=RETRIES_DEFAULT)
    ap.add_argument("--wall-budget", type=float, default=None,
                    help="the wrapper's wall-clock bound in seconds; the judge "
                         "refuses to start if it is below its own worst case")
    ap.add_argument("--print-wall-budget", action="store_true",
                    help="print the required wall bound (integer seconds) to "
                         "stdout, the arithmetic to stderr, and exit")
    ap.add_argument("--json-out")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    # The wrapper bound and the per-critic budgets are reconciled HERE, from the
    # live arguments, so the relationship survives anyone editing either number.
    required_wall = wall_budget_seconds(args.timeout_a, args.timeout_b, args.retries)
    if args.print_wall_budget:
        print(required_wall)
        print(wall_budget_derivation(args.timeout_a, args.timeout_b, args.retries),
              file=sys.stderr)
        sys.exit(0)

    def emit(verdict, code):
        if args.json_out:
            with open(args.json_out, "w", encoding="utf-8") as f:
                json.dump(verdict, f, indent=2, ensure_ascii=False)
        if not args.quiet:
            print(json.dumps(verdict, indent=2, ensure_ascii=False))
        sys.exit(code)

    # Fail closed BEFORE spending a critic call: a bound below the worst case
    # means a run where both critics answer inside their own budgets can still be
    # killed, which is how a passing weekly generation was discarded on
    # 2026-08-31. Refusing to start reverts and skips the deploy, which is the
    # same outcome as the kill, but it says why.
    if args.wall_budget is not None and args.wall_budget < required_wall:
        emit({"verdict": "ERROR", "is_slop": True,
              "error": (f"wrapper wall budget {args.wall_budget:g}s is below this "
                        f"judge's worst case {required_wall}s — "
                        + wall_budget_derivation(args.timeout_a, args.timeout_b,
                                                 args.retries))}, 2)

    if not args.desktop:
        emit({"verdict": "ERROR", "is_slop": True,
              "error": "--desktop is required for every path that judges a render"}, 2)
    if not os.path.isfile(args.desktop):
        emit({"verdict": "ERROR", "is_slop": True, "error": f"desktop screenshot missing: {args.desktop}"}, 2)
    try:
        rubric = open(args.rubric, encoding="utf-8").read()
    except Exception as e:
        emit({"verdict": "ERROR", "is_slop": True, "error": f"rubric unreadable: {e}"}, 2)

    content = build_user_content(rubric, args.desktop, args.mobile)

    # The two critics are INDEPENDENT — that is the whole point of using two
    # model families — so they run concurrently. Serially their budgets summed to
    # 660s worst case against a 240s wrapper bound; concurrently the pair costs
    # the slower path, which is what wall_budget_seconds() bounds. Both calls are
    # blocking socket I/O, so threads are the right shape here.

    # Critic A — no fallback; if it cannot be obtained, we cannot verify craft.
    def run_critic_a():
        return judge_one(args.url, args.critic_a, content, args.timeout_a, args.retries)

    # Critic B — grok; fall back to gemini-3.5-flash ONLY if grok is slow/flaky.
    # The fallback runs INSIDE this worker so the pair stays bounded by one path.
    def run_critic_b():
        try:
            v = judge_one(args.url, args.critic_b, content, args.timeout_b, args.retries)
            return v, args.critic_b, None
        except Exception as e_b:  # noqa: BLE001
            try:
                v = judge_one(args.url, args.critic_b_fallback, content,
                              args.timeout_a, args.retries)
                return v, args.critic_b_fallback, f"{args.critic_b} ({e_b})"
            except Exception as e_fb:  # noqa: BLE001
                raise RuntimeError(
                    f"{args.critic_b} -> {e_b}; "
                    f"fallback {args.critic_b_fallback} -> {e_fb}") from e_fb

    a = b = None
    a_error = b_error = None
    b_model, b_fell_back_from = None, None
    with concurrent.futures.ThreadPoolExecutor(max_workers=2,
                                               thread_name_prefix="critic") as pool:
        future_a = pool.submit(run_critic_a)
        future_b = pool.submit(run_critic_b)
        try:
            a = future_a.result()
        except Exception as exc:  # noqa: BLE001
            a_error = exc
        try:
            b, b_model, b_fell_back_from = future_b.result()
        except Exception as exc:  # noqa: BLE001
            b_error = exc

    # Emitted only after the pool has closed, so no critic thread outlives the
    # process. ERROR is fail-closed and is never overridden by the other critic.
    a_model = args.critic_a
    if a_error is not None:
        emit({"verdict": "ERROR", "is_slop": True,
              "error": f"critic A ({args.critic_a}) unobtainable: {a_error}"}, 2)
    if b_error is not None:
        emit({"verdict": "ERROR", "is_slop": True,
              "error": f"critic B unobtainable: {b_error}"}, 2)

    a_pass, b_pass = critic_passed(a, args.threshold), critic_passed(b, args.threshold)
    # MARGIN RULE: ship if BOTH clear, OR exactly one clears at/above --margin.
    decision = decide_gate(a, b, args.threshold, args.margin)
    passed = decision["passed"]
    gate_rule = decision["gate_rule"]

    def fail_desc(label, model, v):
        why = "slop" if v["is_slop"] else "{}<{}".format(v["overall"], args.threshold)
        return "{}/{}({})".format(label, model, why)

    failers = []
    if not a_pass:
        failers.append(fail_desc("A", a_model, a))
    if not b_pass:
        failers.append(fail_desc("B", b_model, b))

    if gate_rule == "both_passed":
        reason = "both critics cleared"
    elif gate_rule == "margin_override":
        ov_label = decision["override_label"]
        ov_model = a_model if ov_label == "A" else b_model
        reason = ("margin override: critic {}/{} overall {} >= margin {} ships "
                  "despite the other critic's veto ({})".format(
                      ov_label, ov_model, decision["override_overall"],
                      args.margin, ", ".join(failers)))
    else:
        reason = "failed: " + ", ".join(failers)

    verdict = {
        "verdict": "PASS" if passed else "SLOP",
        "gate_rule": gate_rule,
        "is_slop": a["is_slop"] or b["is_slop"],
        "threshold": args.threshold,
        "margin": args.margin,
        "overall_min": min(a["overall"], b["overall"]),
        "reason": reason,
        "critics": {
            "A": {"model": a_model, "passed": a_pass, **a},
            "B": {"model": b_model, "fell_back_from": b_fell_back_from, "passed": b_pass, **b},
        },
    }
    if gate_rule == "margin_override":
        # Audit trail: make it obvious to a human why a slop-flagged page shipped.
        verdict["margin_override"] = {
            "critic": decision["override_label"],
            "model": a_model if decision["override_label"] == "A" else b_model,
            "overall": decision["override_overall"],
            "margin": args.margin,
        }
    emit(verdict, 0 if passed else 1)


if __name__ == "__main__":
    main()
