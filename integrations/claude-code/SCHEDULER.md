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

The base interval must be **≤ the smallest cadence** in `schedule.yaml` (its own header rule), so
`tick.py`'s missed-check detection stays meaningful.

## Realizing it with Claude Code's scheduler

Claude Code exposes scheduling two ways; either realizes `schedule.yaml`:

- **`/schedule`** (cron cloud agents / routines) — register a recurring run of a command on a cron
  expression. Use this for the unattended, always-on cadence (the "24/7 org" of docs/09 §4). One
  routine per driven command, at the cadence its `schedule.yaml` check declares.
- **`/loop`** — run a command on a fixed interval (or self-paced) within a session. Use this for an
  attended run you want to watch, or to pace a single role's cycles.

Concretely, per active role, register:

1. `/org-tick` at the base interval — the watchdog. If it reports a **MISS**, the scheduler itself may
   be down: `tick.py` turns "it was supposed to run" into an escalated fact, never a silent skip
   (docs/11 §5.2). This is why the missed-check detector stays even though the host now owns firing.
2. `/org-work <role>` at that role's `loop.cadence` — the work cycle.
3. `/org-discover <role>` at a slower cadence — self-improvement.

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
