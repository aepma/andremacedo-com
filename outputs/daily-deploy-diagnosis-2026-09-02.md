# daily-deploy: diagnosis and failure-record fix

Run date: 2026-09-02 (UTC). Repository: `~/andremacedo.com-engine-c`, branch `engine-c`.
Commit: `f1c5528` — `daily-deploy: record the cause when the daily publish fails`.
Rollback: `git -C ~/andremacedo.com-engine-c revert f1c5528`.

## Headline

The live site was **not** stale. `andremacedo.com` served the local `index.html`
byte-for-byte before I changed anything. The three logged failures were real but
already resolved: the cause was a Playwright browser cache inside the site
directory that broke Cloudflare Pages' 25 MiB per-file limit, and a fix landed on
2026-09-01 at 18:54 local, about five hours after the last failure. Deploys have
succeeded on every run since. `build-errors.log` records failures and never
records recoveries, which is why an closed incident still reads as an open one.

The second defect was real and was still unfixed: the daily failure path wrote a
bare sentence with no cause. That is what I fixed and committed.

## Files read

- `logs/build-errors.log`
- `scripts/runner.sh` (deploy block, logging helpers, exit trap, header)
- `launchd/telos.andremacedo.daily.plist`
- `.cfignore`, `.wranglerignore`, `.assetsignore`, `.gitignore`
- `~/.telos/logs/andremacedo-agent.log` (read-only; wrangler's own output from the three failing runs)
- `index.html` (compared only, never modified)

Credentials were never read, printed, or committed. The Cloudflare token is loaded
by `runner.sh` from `~/.telos/.env` at runtime; I reproduced the deploy using that
same mechanism without ever rendering the value.

---

## C1 — Establish the drift. PASS, no drift.

```
curl -s -o /tmp/live-index-c1.html -w "http_code=%{http_code} size=%{size_download}\n" https://andremacedo.com/
http_code=200 size=69731
CURL_EXIT:0

LOCAL :    69731 bytes  sha=f04996c437b1823747a9935f9cc1e3ace256ce7a4a7f555b6d655b5db717d547
LIVE  :    69731 bytes  sha=f04996c437b1823747a9935f9cc1e3ace256ce7a4a7f555b6d655b5db717d547
MATCH: identical
CMP_EXIT:0
```

**Answer: yes, they match — byte-identical, same SHA-256.** The deploy failures
caused no user-visible drift. Blast radius at the time of this build: zero.

## C2 — Locate the publish step. PASS.

The emitting line is `scripts/runner.sh:206` (pre-change numbering):

```
scripts/runner.sh:206:    log_error "daily wrangler deploy failed"
EXIT:0
```

In context, `scripts/runner.sh:200-212` before my change:

```
200	bash "$SCRIPT_DIR/refresh.sh" >> "$LOG_FILE" 2>&1 || log "WARN: refresh.sh failed; deploying with prior data"
201	cd "$SITE_DIR"
202	git add -A
203	git commit -m "agent: daily data refresh | pulse: daily" >> "$LOG_FILE" 2>&1 || log "daily: nothing to commit"
204	purge_local_caches
205	if ! npx wrangler pages deploy "$SITE_DIR" --project-name="andremacedo-com" --branch="main" --commit-dirty=true >> "$LOG_FILE" 2>&1; then
206	    log_error "daily wrangler deploy failed"
207	    record_failure
208	    exit 1
209	fi
210	tmo 30 git -C "$SITE_DIR" push origin HEAD 2>/dev/null || log "WARN: daily git push failed/timed out (non-fatal)"
211	log "daily pulse complete (data refreshed + deployed; no LLM spend)"
212	record_success
```

Note the exact message is `daily wrangler deploy failed`, not `daily deploy failed`
as the deposit quoted. The structural defect is on line 205: wrangler's stdout and
stderr go to `$LOG_FILE` (`~/.telos/logs/andremacedo-agent.log`), while line 206
writes to a *different* file, `$ERROR_LOG` (`logs/build-errors.log`), carrying no
command, no exit code and no stderr. The evidence and the alarm were in two places,
and the error log did not point at the other one.

## C3 — Reproduce. Deploy SUCCEEDS now; the failure does not reproduce.

Ran the publish step in the foreground, using the same credential-loading logic
as `runner.sh`:

```
zsh -l -c '/tmp/repro-deploy.sh'
IMMEDIATE_EXIT_CODE=0

 ⛅️ wrangler 4.125.0
✨ Compiled Worker successfully
Uploading... (391/391)
✨ Success! Uploaded 1 files (390 already uploaded) (1.13 sec)
✨ Uploading Functions bundle
🌎 Deploying...
✨ Deployment complete! Take a peek over at https://4e444e18.andremacedo-com.pages.dev
WRANGLER_RC=0
STDERR: (empty)
```

**What differs between my invocation and the scheduled one — the difference is
time, not environment.** Checked all three axes the deposit named:

- **Working directory:** identical. The loaded launchd job runs
  `/Users/andrepiresmacedo/andremacedo.com-engine-c/scripts/runner.sh`, and
  `SITE_DIR` resolves to that same repo root, which is what I deployed.
- **Environment:** identical. Same `~/.telos/.env` Cloudflare vars, same
  `wrangler 4.125.0`, same `node v22.22.3`, same `zsh -l` login shell.
- **Branch:** identical. `--branch=main` is passed literally in both cases; the
  local git branch (`engine-c`) does not feed that flag.

The variable that actually changed is the **contents of the site directory**. The
three failing runs had a 149 MiB Playwright browser cache (`.pw-browsers`) inside
it. A `purge_local_caches` step was added to `runner.sh` on 2026-09-01 at 14:54
local (18:54Z) and the very next run purged the cache and deployed cleanly:

```
[2026-09-01T18:55:12Z] purging non-deployable local cache .pw-browsers from site dir before deploy
[2026-09-01T18:55:21Z] daily pulse complete (data refreshed + deployed; no LLM spend)
[2026-09-01T19:32:04Z] daily pulse complete (data refreshed + deployed; no LLM spend)
```

Confirmed no oversized file remains: `find . -type f -size +25M -not -path "./.git/*"`
returned nothing, exit 0, and `.pw-browsers`, `.pw-node`, `.venv-pw` are all absent.

So this was not a transient failure. It was a persistent failure with a real cause
that was diagnosed and fixed roughly five hours after the third occurrence, before
this build started.

## C4 — Name the cause. PASS, from captured output, and independently reproduced.

**Cause: a file larger than 25 MiB inside the deployed site directory — a 149 MiB
Playwright browser cache at `.pw-browsers` — made Cloudflare Pages reject the whole
deploy, and wrangler reported it only on its own stderr, which the daily path
routed to the agent log rather than the error log.**

Supporting line, captured verbatim at the time of each of the three failures
(`~/.telos/logs/andremacedo-agent.log` lines 1394, 1433, 1473):

```
✘ [ERROR] Error: Pages only supports files up to 25 MiB in size
```

Immediately followed in each case by:

```
[2026-08-31T14:00:10Z] ERROR: daily wrangler deploy failed
[2026-08-31T19:18:21Z] ERROR: daily wrangler deploy failed
[2026-09-01T14:00:13Z] ERROR: daily wrangler deploy failed
```

I did not stop at the historical record. I reproduced the mechanism directly by
planting a 26 MiB file in the site directory and re-running the real publish step:

```
dd if=/dev/zero of=.c4probe/oversize.bin bs=1m count=26   →  26M
zsh -l -c '/tmp/repro-deploy.sh'
IMMEDIATE_EXIT_CODE=1
STDERR:
✘ [ERROR] Error: Pages only supports files up to 25 MiB in size
  .c4probe/oversize.bin is 26 MiB in size
```

Same exit code and same error string as the three historical failures. The probe
file was deleted immediately afterwards; `git status --porcelain` returned only the
pre-existing ` M data/external.json`.

This reproduction also settles something the ignore files imply but do not deliver:
`.pw-browsers/` is listed in `.cfignore`, `.wranglerignore` **and** `.assetsignore`,
and the deploy failed anyway. Wrangler's size check walks the directory regardless
of those files, so an ignore entry is not protection against this failure class.

## C5 — Apply the fix, re-run. PASS, exit 0.

The *cause* fix (`purge_local_caches`) was already in the checkout when this build
started; I did not re-author it. My change is the failure-record fix (C7) plus two
guards. After committing it, I re-ran the publish step:

```
zsh -l -c '/tmp/repro-deploy.sh'
C5_IMMEDIATE_EXIT_CODE=0

✨ Success! Uploaded 1 files (390 already uploaded) (1.01 sec)
✨ Deployment complete! Take a peek over at https://221c0e42.andremacedo-com.pages.dev
WRANGLER_RC=0
```

## C6 — Verify the fix reached the live site. PASS.

Not just a clean exit — the published bytes were re-fetched:

```
curl -s -D /tmp/c6.headers -o /tmp/live-index-c6.html https://andremacedo.com/
http_code=200 size=69731
CURL_EXIT:0

LOCAL: 69731 bytes sha=f04996c437b1823747a9935f9cc1e3ace256ce7a4a7f555b6d655b5db717d547
LIVE : 69731 bytes sha=f04996c437b1823747a9935f9cc1e3ace256ce7a4a7f555b6d655b5db717d547
MATCH: byte-identical
CMP_EXIT:0

date: Wed, 02 Sep 2026 10:31:59 GMT
cf-ray: a34bd9235dfc887e-MIA
```

Freshness marker tying the live bytes to *this* deployment: the deployment-specific
URL created by the C5 run serves the same content.

```
curl https://221c0e42.andremacedo-com.pages.dev/   →  http_code=200 size=69731
DEPLOYMENT 221c0e42 sha=f04996c437b1823747a9935f9cc1e3ace256ce7a4a7f555b6d655b5db717d547
MATCH: deployment 221c0e42 == local index.html
CMP_EXIT:0
```

The deployment created at 10:31Z, the apex domain, and the local file are all the
same SHA-256.

## C7 — Improve the failure record. PASS, proven by forced failure.

Committed in `f1c5528`. Four changes, all in `scripts/runner.sh`:

1. **`log_command_failure()`** — records the label, exit code, the exact command,
   and an ANSI-stripped, blank-line-stripped, byte-capped tail of the failing
   command's output, into `build-errors.log` itself.
2. **Daily deploy rewired** — wrangler's output is captured to a temp file, the
   full transcript is still appended to the agent log exactly as before, and on
   failure the tail is handed to `log_command_failure`. The temp file is removed on
   both the success and failure paths and is registered with the existing `EXIT`
   trap so an unexpected exit cannot leak it.
3. **`require_deploy_toolchain()`** — resolves `node` and `npx`/wrangler at runtime,
   logs the versions that actually ran, and fails loudly naming the missing binary
   and `PATH` if one is absent. No version string is pinned anywhere.
4. **`warn_oversized_deploy_files()`** — before deploying, names any file over the
   25 MiB per-file limit. `purge_local_caches` only clears three caches it knows by
   name, so this covers the general class rather than the three known instances. It
   warns and lets wrangler remain the authority on failing, so deploy behaviour is
   unchanged.

**Proof — forced failure through the real code path** in a throwaway copy at
`/tmp/c7-runner`, pointed at a deliberately invalid project name so it could never
publish over the live site, with a 26 MiB file planted to match the historical
shape. Runner exit code 1. The resulting `build-errors.log` line:

```
[2026-09-02T10:30:50Z] [daily] daily wrangler deploy failed | exit=1 | cmd=npx wrangler pages deploy /tmp/c7-runner --project-name=c7-nonexistent-project-do-not-create --branch=main --commit-dirty=true | output_tail: ───|✘ [ERROR] The Pages project "c7-nonexistent-project-do-not-create" does not exist.|  Maybe you intended to deploy a Worker project instead? ...|  If you are targeting an existing Pages project, verify that the project name is correct and that it exists in your account (the account in use has id 98a1...).|  Otherwise, if you are trying to create a new Pages project, start by running: `wrangler pages project create` ...|🪵  Logs were written to ".../wrangler-2026-09-02_10-30-49_803.log"
```

Compare with what the same failure used to produce: `[daily] daily wrangler deploy failed`.
A reader now gets the command, the exit code, the cause in the operator's own words,
and a pointer to wrangler's full log, without access to the machine.

The two guards fired in the same run:

```
[2026-09-02T10:30:49Z] deploy toolchain: node v22.22.3, wrangler 4.125.0
[2026-09-02T10:30:49Z] WARN: files over the Cloudflare Pages 25 MiB per-file limit are present in the site dir: .c7probe/oversize.bin
```

That WARN line names the exact culprit — precisely the signal that was missing on
2026-08-31 and 2026-09-01.

**Success path also verified** (throwaway at `/tmp/c7ok-runner`, deploy command
swapped for one that succeeds): runner exit 0, no `build-errors.log` created at all,
deploy output still appended to the agent log, temp file cleaned up, failure counter
left at 0.

Both throwaway trees were deleted; no stray processes or temp files remain.

## C8 — Liveness. PASS. Schedule not modified.

The registration that actually fires the daily lane, read live from launchd:

```
launchctl list telos.andremacedo.daily
{
	"Label" = "telos.andremacedo.daily";
	"LastExitStatus" = 0;
	"Program" = "/bin/zsh";
	"ProgramArguments" = ( "/bin/zsh"; "-l"; "-c";
		"/Users/andrepiresmacedo/andremacedo.com-engine-c/scripts/runner.sh --daily"; );
	"StandardOutPath" = "/Users/andrepiresmacedo/.telos/logs/andremacedo-daily.stdout.log";
	"StandardErrorPath" = "/Users/andrepiresmacedo/.telos/logs/andremacedo-daily.stderr.log";
};
EXIT_IMMEDIATE:0
```

It runs the engine-c checkout, so the committed fix reaches the real run. Fire time
is 14:00Z daily (10:00 America/New_York), confirmed by six consecutive observed
fires:

```
[2026-08-27T14:00:05Z] daily cheap pulse
[2026-08-28T14:00:05Z] daily cheap pulse
[2026-08-29T14:00:04Z] daily cheap pulse
[2026-08-30T14:00:05Z] daily cheap pulse
[2026-08-31T14:00:05Z] daily cheap pulse
[2026-09-01T14:00:05Z] daily cheap pulse
```

Current time `2026-09-02T10:32:35Z`. **Next fire: 2026-09-02T14:00Z**, about three
and a half hours after this build finished.

---

## Declared success check

Re-runnable. Asserts the end state, not that the run finished: runner parses, the
daily failure path emits cause plus exit code plus command under a forced failure,
and the live site serves the local `index.html` byte-for-byte.

```
[1] syntax: exit=0
[2] forced-failure runner exit=1
    logged: [2026-09-02T10:33:07Z] [daily] daily wrangler deploy failed | exit=1 | cmd=npx wrangler pages deploy ...
    contains 'exit=': yes
    contains 'cmd=npx wrangler pages deploy': yes
    contains 'output_tail:': yes
    contains 'does not exist': yes
[3] live fetch exit=0
    live == local index.html (69731 bytes): yes
RESULT: PASS
SUCCESS_CHECK_IMMEDIATE_EXIT_CODE=0
```

---

## Things I observed that contradict the evidence stated in the deposit

1. **"The live site is drifting behind the repository."** Not true at any point I
   could measure. Live and local `index.html` were byte-identical before I touched
   anything (C1), with matching SHA-256. There was no user-visible drift to repair.

2. **"Three consecutive failures, the most recent today."** The most recent failure
   was 2026-09-01T14:00Z — yesterday, not today. More importantly the incident was
   already closed before this build was dispatched: `purge_local_caches` was added
   at 18:54Z on 2026-09-01 and the deploys at 18:55:21Z and 19:32:04Z both succeeded.
   `build-errors.log` only ever appends failures, so a resolved incident stays
   visually open forever. That reporting asymmetry is itself worth fixing, and is
   why this build was dispatched against an already-fixed cause.

3. **The log line quoted in the deposit was `daily deploy failed`.** The actual
   string is `daily wrangler deploy failed`. Minor, but it matters for grepping.

4. **`git log` "three times on 2026-09-01"** checks out, and the pattern is not
   1-per-day: 3 commits on 08-28, 3 on 08-29, 1 on 08-30, 2 on 08-31, 3 on 09-01.
   The daily lane is being invoked manually as well as on schedule.

5. **New defect found, reported not fixed** (the deposit forbade modifying the
   schedule): the plist checked into the repo,
   `launchd/telos.andremacedo.daily.plist`, points `ProgramArguments` at
   `/Users/andrepiresmacedo/andremacedo.com/scripts/runner.sh`. That file does not
   exist — `~/andremacedo.com` is a near-empty directory containing only
   `state/page-metrics.json`. The *loaded* job correctly targets the engine-c
   checkout, so the lane works today, but anyone who reloads the daily job from the
   checked-in plist will silently break it. This needs Andre's call, since fixing it
   means editing a scheduler registration.

## Left undone, deliberately

The weekly/event deploy path (`scripts/runner.sh`, the second
`npx wrangler pages deploy` call) still logs the bare string
`log_error "wrangler deploy failed"` with no cause. It has exactly the defect I just
fixed on the daily path and `log_command_failure` is already available to it. I left
it alone because the deposit scoped this build to the daily failure path and warned
that two sibling builds are working in the weekly craft-judge area. It is a
one-line-shaped follow-up.

## Untouched, as instructed

`index.html`, the genome, agent state, the archive and all site content were read
or compared but never modified, and the site was not regenerated. The craft judge,
craft rubric, pass threshold and margin were not opened. Nothing under `~/.telos`
or `~/openclaw` was modified; the agent log there was read only. No credential was
read, printed, logged or committed. The schedule was not modified.

## Outcome

The daily publish is healthy and verified live. The real remaining defect — a
failure path that reported a confident sentence carrying none of its evidence — is
fixed, committed, and proven by a forced failure. One commit, `f1c5528`,
`scripts/runner.sh` only; the pre-existing dirty `data/external.json` was preserved
untouched. Rollback is a single revert.
