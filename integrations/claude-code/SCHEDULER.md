# Wiring the org's schedule onto Claude Code's own scheduler

`template/schedule.yaml` declares the org's cadences as **data** — it ships no scheduler, by design
(docs/08 R0: the loop/scheduler is the host's, not this repo's). docs/01 R2.3 and docs/08 §4 name the
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

## Firing the cadence: `/loop` by default, OS cron only when unattended

The drive is delegated to the harness (R0). Claude Code's **`/loop`** is the simplest driver and the
default; the OS cron is the heavier fallback for the one case `/loop` can't cover — running with no
session open. **Whichever drives, the org keeps the monitoring** (`tick.py`'s missed-check detection), so
"the loop stopped" is a detected fact, not silence (see the last section).

| | Runs when | Survives closing Claude Code? | Use for |
|---|---|---|---|
| **`/loop`** (default) | while THIS session is open | no | an attended or kept-open session — the everyday driver |
| **OS cron** (`scheduler-install.sh`) | always, headless (`claude -p`) | **yes** — true 24/7 unattended | the one case that needs no session open |

### `/loop` — the default (simplest)

`/loop <interval> <command>` fires a command on that interval within the session — no cron expressions,
no bookkeeping. `/org-start` prints these three for you:

```
/loop 15m /org-tick
/loop 60m /org-work <role>
/loop 6h  /org-discover <role>
```

That's the whole drive. Check on the org with `/org`; stop a cycle by ending its `/loop`. This replaced
the CronCreate registration the earlier design did by hand — the harness's `/loop` is the loop, so
orgforge no longer builds one.

### Getting notified the moment the org needs you (Monitor + PushNotification)

"Unattended" must not mean "unobservable." orgforge detects escalations but ships no notify transport
(R0 — the host delivers them); Claude Code *is* the host, so use its **Monitor** + **PushNotification**
to reach you. Arm a Monitor that streams only the RED signal:

```
# Never infer death from TaskList. This must print READY TO ARM before creating a Monitor:
python3 <plugin>/scripts/redline_monitor.py rearm-check "$ORG_LEDGER_ROOT" \
  --role <role> --instance redline-<role>

# redline_monitor retains the previous signal: first/changed RED only, quiet while unchanged or healthy
Monitor: python3 <plugin>/scripts/redline_monitor.py "$ORG_LEDGER_ROOT" \
  --role <role> --instance redline-<role>   (persistent)
```

The first RED and each changed RED become notifications — a wedged cycle, a repeated death, a broken
chain — while an unchanged RED stays quiet. GREEN resets the remembered signal, so a later recurrence
notifies again. `/org-tick` also sends a `PushNotification` on a genuine escalation when it runs.
Healthy ticks stay silent (fail-quiet); a notification you didn't need erodes trust.

The monitor updates an atomic heartbeat with PID, plugin version, role and instance after every
probe. `redline_monitor.py status "$ORG_LEDGER_ROOT"` distinguishes live, stale, dead, duplicate,
orphaned and old-version records without Claude's task metadata. Stop one exact record with
`redline_monitor.py stop <record-id> --root "$ORG_LEDGER_ROOT"`; the token-bound cooperative request
does not signal a reused PID or kill another session. Run `rearm-check` again before replacing it.

### OS cron — only for genuinely unattended (no session open)

`/loop` ends when Claude Code closes. To run 24/7 with no session, install the cadence on the OS cron:

```
integrations/claude-code/scheduler-install.sh --role <role> --tick-min 30 --work-min 60 --discover-hours 24
# preview:  add --dry-run   |   remove:  scheduler-uninstall.sh --role <role>
```

This writes crontab entries that run headless with the plugin attached; output streams to
`$ORG_LEDGER_ROOT/cron.log`, each tagged `# orgforge:<role>`. Use this only when you truly need the org
running while no session is open — for everything else, the three `/loop`s above are all you need.

## The stop/night discipline still holds

The scheduler fires the cadence; the **stop conditions remain the org's** (docs/08 §4): a check marked
`night_safe: false` in `schedule.yaml` suspends overnight, and the guardrail hook + the blast-radius
cap bound what any fired cycle may do. Scheduling more runs does not widen authority — it only changes
*when* the same gated cycle runs. Keep `/org-work`'s fan-out a judgment (parallelize genuinely
independent work, keep coupled work single-threaded — docs/03); the cadence decides *when* a cycle
runs, not *how finely* it splits.

## Why the missed-check detector survives the wiring

A natural question: if Claude Code's scheduler now fires the cadence reliably, why keep `tick.py`'s
MISS detection? Because a scheduler *can* be down, paused, rate-limited, or misconfigured, and the org
must not read silence as success. `tick.py` reads the ledger for the `verify_event` that proves a due
check actually ran; a due check with no such event is reported as a MISS. That safety net is
independent of who fires the cadence — it is the org checking its own heartbeat, not the host's.
