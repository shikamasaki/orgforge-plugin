# Wiring the org's schedule onto Claude Code's own scheduler

`template/schedule.yaml` declares the org's cadences as **data** — it ships no scheduler, by design
(docs/09 R0: the loop/scheduler is the host's, not this repo's). docs/01 R2.3 and docs/09 §4 name the
valid realizations verbatim: *"a cron, the harness's own loop, a CI trigger."* **Claude Code's built-in
scheduler is exactly "the harness's own loop."** So realizing the schedule on Claude Code is the
R0-conformant path — nothing about R0 changes, and none of this wiring belongs in the neutral skeleton;
it lives here, in the Claude Code integration layer, and only here (R2.4: the projection is the one
place harness-specific knowledge lives).

## What drives what

Three commands make up the metabolism; the scheduler fires them on cadence:

| Command | What it does | Suggested cadence |
|---|---|---|
| `/org-tick` | Read-only health tick: which checks are due / MISSED, sensors, chain integrity. Surfaces, never acts. | the base interval (e.g. every 30 min) |
| `/org-work <role>` | The PM loop: select from the backlog (attention), delegate selected items in parallel, record completion. Acts. | per role's `loop.cadence` |
| `/org-discover <role>` | Problemistic search: raise `source: self` backlog items from aspiration gaps. Adds to backlog. | slower than `/org-work` (e.g. daily) |
| `/org-triage <signal>` | The **front door**: turn an external signal (issue/bug/feedback) into a backlog item. | on the intake source's cadence (see below) |

The base interval must be **≤ the smallest cadence** in `schedule.yaml` (its own header rule), so
`tick.py`'s missed-check detection stays meaningful.

### Wiring the external front door (the factory intake)

To make the org a factory that work flows *into* (not a workshop a human types tasks into), feed
`/org-triage` from an issue tracker. The org ships no ingestion service (R0) — the host feeds it. E.g. a
cron that lists newly-labeled issues and pipes each to a headless triage:

```
*/10 * * * *  gh issue list --label 'orgforge:ready' --state open --json number,title,body \
  | jq -c '.[]' | while read -r issue; do \
      claude -p "/org-triage $issue" --plugin-dir <plugin> ; done
```

The human's whole input is then **applying one label** to an issue. orgforge supplies the triage; the
host supplies the feed.

## Two ways to fire the cadence — pick by how unattended you need it

Claude Code's in-session scheduler and the OS cron differ in ONE decisive way — session-only vs.
survives-the-REPL-closing — so choose by whether the org must run with no session open.

| | Runs when | Survives closing Claude Code? | Use for |
|---|---|---|---|
| **OS cron** (`scheduler-install.sh`) | always, headless (`claude -p`) | **yes** — true 24/7 unattended | the real always-on org |
| **`/schedule`** (in-session cron) | only while THIS session is open | no — session-only, in-memory, 7-day cap | pacing a session you keep open |
| **`/loop`** | only while THIS session is open | no | an attended run you watch |

**For a genuinely 24/7 org, use the OS cron** — the in-session schedulers stop the moment Claude Code
exits, which is not "unattended." `docs/09 §4` names "a cron" first for exactly this reason.

### The one-command install (OS cron — recommended)

With `ORG_LEDGER_ROOT` (and usually `ORG_ROLE`/`ORG_DOCTRINE_ROOT`) set in your environment:

```
integrations/claude-code/scheduler-install.sh --role <role> --tick-min 30 --work-min 60 --discover-hours 24
# preview without installing:  add --dry-run
# remove:                      integrations/claude-code/scheduler-uninstall.sh --role <role>
```

This writes crontab entries that run, headless with the plugin attached (so hooks + doctrine injection
fire), one per driven command:

1. `/org-tick` at `--tick-min` — the watchdog. A reported **MISS** means the cron itself may be down:
   `tick.py` turns "it was supposed to run" into an escalated fact, never a silent skip (docs/11 §5.2).
2. `/org-work <role>` at `--work-min` — the work cycle.
3. `/org-discover <role>` every `--discover-hours` — self-improvement.

Output streams to `$ORG_LEDGER_ROOT/cron.log`. Each entry is tagged `# orgforge:<role>` so the
uninstaller can find and remove exactly this role's lines.

### In-session alternative (when you keep a session open)

`/schedule` registers the same commands on a cron expression *within the current session* (gone when
it closes, auto-expires after 7 days); `/loop` runs one command on a fixed interval you watch. Use
these to pace or observe a session — not as the unattended driver.

## The stop/night discipline still holds

The scheduler fires the cadence; the **stop conditions remain the org's** (docs/09 §4): a check marked
`night_safe: false` in `schedule.yaml` suspends overnight, and the guardrail hook + the blast-radius
cap bound what any fired cycle may do. Scheduling more runs does not widen authority — it only changes
*when* the same gated cycle runs. Keep `/org-work`'s fan-out a judgment (parallelize genuinely
independent work, keep coupled work single-threaded — docs/15); the cadence decides *when* a cycle
runs, not *how finely* it splits.

## Why the missed-check detector survives the wiring

A natural question: if Claude Code's scheduler now fires the cadence reliably, why keep `tick.py`'s
MISS detection? Because a scheduler *can* be down, paused, rate-limited, or misconfigured, and the org
must not read silence as success. `tick.py` reads the ledger for the `verify_event` that proves a due
check actually ran; a due check with no such event is reported as a MISS. That safety net is
independent of who fires the cadence — it is the org checking its own heartbeat, not the host's.
