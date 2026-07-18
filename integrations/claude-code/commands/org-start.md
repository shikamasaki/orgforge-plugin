---
description: Start the org's metabolism in THIS session — register the recurring cycles (health tick, PM loop, issue discovery) as scheduled jobs so the org runs itself while this session is open. Idempotent — if the jobs are already registered, it does nothing. Run once per session (or let the SessionStart hook prompt you to).
argument-hint: "[role] [tick-min] [work-min] [discover-hours]"
allowed-tools: CronCreate, CronList, CronDelete, Bash(python3 *)
---

Bring the organization to its **running state** for this session: the metabolism cadences of
`schedule.yaml` (docs/09 §4), realized on this session's scheduler (`CronCreate`). While this session
stays open, the org drives itself; when it closes, the jobs end (session-scoped — see the note below).

Role: **${1:-supervisor}** · tick every **${2:-15}** min · work every **${3:-60}** min · discover every
**${4:-6}** hours.

## 1. Check what is already scheduled (idempotent — do not double-register)

First list the current jobs:

Use **CronList**. If jobs whose prompts are `/org-tick`, `/org-work ${1:-supervisor}`, and
`/org-discover ${1:-supervisor}` are ALREADY present, the org is already running — report that and
STOP. Do not register duplicates. Only register the ones that are missing.

## 2. Register the missing cycles

For each cycle not already present, call **CronCreate** (recurring). Pick off-:00/:30 minutes so fleets
don't all fire at once:

- **Health tick** — `/org-tick` — cron `*/${2:-15} * * * *` (read-only; surfaces due/missed checks).
- **PM loop** — `/org-work ${1:-supervisor}` — cron for every ${3:-60} min (an interval of 60 → `3 * * * *`;
  sub-60 → `*/${3:-60} * * * *`). Selects from the backlog and delegates in parallel.
- **Discovery** — `/org-discover ${1:-supervisor}` — cron `17 */${4:-6} * * *` (raises self-tasks from
  aspiration gaps).

## 3. Confirm and report

Call **CronList** again and report the running state: which cycles are now scheduled, at what cadence,
for role `${1:-supervisor}`. Tell the user plainly that these are **session-scoped** — they run while
this Claude Code session is open and stop when it closes (and auto-expire after 7 days); to run the org
genuinely 24/7 with no session open, an OS-level cron is needed (see SCHEDULER.md), which is a separate,
explicit setup.

## Notes

- **Idempotent**: safe to run more than once; it only adds cycles that are missing.
- **Stop the org**: `CronDelete` each job (or `/org-stop` if present), or just close the session.
- The `tick.py` missed-check detector still runs inside `/org-tick`, so a cycle that was due but did not
  fire is surfaced as a fact, not silently skipped (docs/11 §5.2).
