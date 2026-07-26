---
description: Start the org's metabolism in THIS session by driving its cycles with /loop. Prints the exact /loop invocations to run (health tick, PM loop, discovery) so the org runs itself while the session is open. The drive is delegated to Claude Code's /loop; the org keeps only the monitoring (missed-tick detection) that /loop can't provide.
argument-hint: "[role] [tick-min] [work-min] [discover-hours]"
allowed-tools: Bash(echo *)
---

Bring the organization to its **running state** for this session. The drive — firing each cycle on a
cadence — is delegated to Claude Code's built-in **`/loop`** (R0: borrow the harness's loop, don't build
one). The org keeps only what `/loop` can't give it: the **missed-tick detection** in `/org-tick` that
notices when a cycle that was due did *not* run (docs/11 §5.2) — so "the loop stopped" is a detected fact,
not silence.

Role: **${1:-supervisor}** · tick every **${2:-15}** min · work every **${3:-60}** min · discover every
**${4:-6}** hours.

## Run these three `/loop` invocations to drive the org

`/loop <interval> <command>` runs a command on that interval within this session. Start the three cycles:

```
/loop ${2:-15}m /org-tick
/loop ${3:-60}m /org-work ${1:-supervisor}
/loop ${4:-6}h /org-discover ${1:-supervisor}
```

- **`/org-tick`** — read-only health: due/MISSED checks, stall breakers, repeated-death + domain-model
  growth. This is the **monitoring the org keeps** — it catches a cycle that was due but didn't fire.
- **`/org-work`** — the PM loop: select from the backlog, delegate in parallel, record.
- **`/org-discover`** — raise self-tasks from aspiration gaps.

Each `/loop` is session-scoped: it runs while this Claude Code session is open and stops when it closes.
Check on the org any time with **`/org`** (the status board). Stop a cycle by ending its `/loop`.

## For a genuinely 24/7 org (no session open)

`/loop` and the session end when Claude Code closes. To run unattended with no session, install the
cadence on the OS cron instead — `integrations/claude-code/scheduler-install.sh --role ${1:-supervisor}`
(see [SCHEDULER.md](../SCHEDULER.md)). That is the one case that needs the heavier setup; for an attended
or kept-open session, the three `/loop`s above are all you need.

## Why the monitoring stays with the org

`/loop` fires a command on a cadence, but it does **not** know whether a *due org check* actually ran —
that's an org-specific fact only `tick.py` can judge (a due check with no `verify_event` in the ledger is
a MISS). So the drive is delegated, the monitoring is not: `/org-tick` (driven by `/loop`) still detects a
missed cycle and surfaces it, exactly as before. Delegating the drive removed the CronCreate/OS-cron
bookkeeping; keeping the monitor preserved the "silence must not read as success" guarantee (docs/16).
