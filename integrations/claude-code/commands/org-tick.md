---
description: Run one org metabolism tick — plan the schedule, detect missed checks, evaluate machine sensors, and report what is due or escalating. Read-only; surfaces, does not decide. Pushes a notification to the user only on a genuine escalation.
argument-hint: "[now-minutes] [--night]"
allowed-tools: Bash(*), Read, Write, Edit, Glob, Grep, Agent, Task, PushNotification, WebFetch, WebSearch
---

Run one operating tick of the articulated organization against its ledger.

The ledger root is **discovered** (`tools/discover.py`) — no environment variable to set.

## Plan the tick (which checks are due / suspended / MISSED)

!`python3 "${CLAUDE_PLUGIN_ROOT}/scripts/tick_host.py" "${CLAUDE_PLUGIN_ROOT}/template/schedule.yaml" --now-min ${1:-$(( $(date -u +%s) / 60 ))} ${2}`

## Evaluate the machine sensors over the ledger

!`python3 "${CLAUDE_PLUGIN_ROOT}/tools/sensors.py" eval "${CLAUDE_PLUGIN_ROOT}/template/sensors.yaml" --now $(date -u +%Y-%m-%dT%H:%M:%SZ)`

## Verify the ledger chain (tamper evidence + the watchdog heartbeat)

!`python3 "${CLAUDE_PLUGIN_ROOT}/tools/ledger.py" verify`

## Check each in-progress candidate for a stall (circuit breaker)

Read the work-in-progress board, then run the stall breaker on each in-flight candidate — a wedged
cycle that stopped advancing must be tripped, not left to burn its slot:

!`python3 "${CLAUDE_PLUGIN_ROOT}/tools/ledger.py" view work_in_progress`

For each `candidate_id` above, run `guardrails.py stall --candidate-id <id>`. A
**TRIP** means the candidate is not progressing (identical next_step, or flat fraction) — flag it for a
human and free its WIP slot; do not respawn the wedged cycle.

## Check whether accumulated learning is being used (repeated-death detector)

The org exists to accumulate learning and lift output quality. A death cause that reappears means a
recorded lesson was NOT fed forward — the core purpose failing. Surface it:

!`python3 "${CLAUDE_PLUGIN_ROOT}/tools/learning.py" repeats`

A **REPEATED DEATH** means the org re-made a mistake it had recorded — strengthen that death into
doctrine and inject it before the next attempt, so the lesson actually lands next time.

## Check the domain model is growing (SSoT inferability rising)

The SSoT/domain model must grow as the org runs (not stay a static founding artifact); a flat model
over many cycles means the org is amplifying a fixed ambiguity, not compounding clarity.

!`python3 "${CLAUDE_PLUGIN_ROOT}/tools/conventions.py" growth`

If the domain model is **EMPTY or flat** across many cycles, that is a signal — settle domain rules in
the work cycle (co-commit), so inferability rises over time.

Based on the above:
- If any check is **MISSED** past threshold, this is "it was supposed to run" — surface it as an escalation (the host cron may be down). Do not treat silence as success.
- If any machine sensor **FIRED**, name the move it feeds and whether that move is night-safe.
- If any candidate's stall breaker **TRIPPED**, surface it — a wedged cycle is a wasted WIP slot, not silence.
- If a **REPEATED DEATH** or an **unproven rollback** was found, surface it — accumulated learning isn't landing / a reversibility claim is untested.
- If the chain is **BROKEN**, this is a global-halt condition — stop and report immediately.
- Otherwise report "org healthy, N checks due, nothing escalating" — fail-quiet is the normal state.

## Reach the human on a real escalation (the missing transport, delegated to the harness)

orgforge detects escalations but ships no notify transport (R0 — the host delivers them). Claude Code
*is* the host, so use **PushNotification** to reach the user — this closes the "unattended ≠
unobservable" gap. **Only on a genuine escalation** (a MISS past threshold, a tripped stall, a repeated
death, an unproven rollback, a broken chain, or a fired night-unsafe move), send ONE concise push naming
what needs them — e.g. `PushNotification: "org: cycle X wedged (same next_step ×3) — needs you"` or
`"org: repeated death 'null not rejected' ×2 — learning isn't landing"`. Do **not** notify on a healthy
tick — fail-quiet stays silent; a notification the user didn't need erodes trust. One escalation → one
push; nothing escalating → no push.

Do not take any asset-touching action from this command; it is a read-only health tick.
