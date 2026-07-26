---
description: Run one org metabolism tick — plan the schedule, detect missed checks, evaluate machine sensors, and report what is due or escalating. Read-only; surfaces, does not decide.
argument-hint: "[now-minutes] [--night]"
allowed-tools: Bash(python3 *)
---

Run one operating tick of the articulated organization against its ledger.

Ledger root: `${ORG_LEDGER_ROOT}` (must be set).

## Plan the tick (which checks are due / suspended / MISSED)

!`python3 "${CLAUDE_PLUGIN_ROOT}/tools/tick.py" plan "${ORG_LEDGER_ROOT}" "${CLAUDE_PLUGIN_ROOT}/template/schedule.yaml" --now-min ${1:-0} ${2}`

## Evaluate the machine sensors over the ledger

!`python3 "${CLAUDE_PLUGIN_ROOT}/tools/sensors.py" eval "${ORG_LEDGER_ROOT}" "${CLAUDE_PLUGIN_ROOT}/template/sensors.yaml" --now 2026-07-16T12:00:00Z`

## Verify the ledger chain (tamper evidence + the watchdog heartbeat)

!`python3 "${CLAUDE_PLUGIN_ROOT}/tools/ledger.py" verify "${ORG_LEDGER_ROOT}"`

## Check each in-progress candidate for a stall (circuit breaker)

Read the work-in-progress board, then run the stall breaker on each in-flight candidate — a wedged
cycle that stopped advancing must be tripped, not left to burn its slot:

!`python3 "${CLAUDE_PLUGIN_ROOT}/tools/ledger.py" view "${ORG_LEDGER_ROOT}" work_in_progress`

For each `candidate_id` above, run `guardrails.py stall "${ORG_LEDGER_ROOT}" --candidate-id <id>`. A
**TRIP** means the candidate is not progressing (identical next_step, or flat fraction) — flag it for a
human and free its WIP slot; do not respawn the wedged cycle.

## Check whether accumulated learning is being used (repeated-death detector)

The org exists to accumulate learning and lift output quality. A death cause that reappears means a
recorded lesson was NOT fed forward — the core purpose failing. Surface it:

!`python3 "${CLAUDE_PLUGIN_ROOT}/tools/learning.py" repeats "${ORG_LEDGER_ROOT}"`

A **REPEATED DEATH** means the org re-made a mistake it had recorded — strengthen that death into
doctrine and inject it before the next attempt, so the lesson actually lands next time.

Based on the above:
- If any check is **MISSED** past threshold, this is "it was supposed to run" — surface it as an escalation (the host cron may be down). Do not treat silence as success.
- If any machine sensor **FIRED**, name the move it feeds and whether that move is night-safe.
- If any candidate's stall breaker **TRIPPED**, surface it — a wedged cycle is a wasted WIP slot, not silence.
- If the chain is **BROKEN**, this is a global-halt condition — stop and report immediately.
- Otherwise report "org healthy, N checks due, nothing escalating" — fail-quiet is the normal state.

Do not take any asset-touching action from this command; it is a read-only health tick.
