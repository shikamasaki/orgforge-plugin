---
description: Run one org metabolism tick — plan the schedule, detect missed checks, evaluate machine sensors, and report what is due or escalating. Read-only; surfaces, does not decide.
argument-hint: "[now-minutes] [--night]"
allowed-tools: Bash(python3 *)
---

Run one operating tick of the articulated organization against its ledger.

Ledger root: `${ORG_LEDGER_ROOT}` (must be set).

## Plan the tick (which checks are due / suspended / MISSED)

!`python3 "${CLAUDE_PROJECT_DIR}/tools/tick.py" plan "${ORG_LEDGER_ROOT}" "${CLAUDE_PROJECT_DIR}/template/schedule.yaml" --now-min ${1:-0} ${2}`

## Evaluate the machine sensors over the ledger

!`python3 "${CLAUDE_PROJECT_DIR}/tools/sensors.py" eval "${ORG_LEDGER_ROOT}" "${CLAUDE_PROJECT_DIR}/template/sensors.yaml" --now 2026-07-16T12:00:00Z`

## Verify the ledger chain (tamper evidence + the watchdog heartbeat)

!`python3 "${CLAUDE_PROJECT_DIR}/tools/ledger.py" verify "${ORG_LEDGER_ROOT}"`

Based on the above:
- If any check is **MISSED** past threshold, this is "it was supposed to run" — surface it as an escalation (the host cron may be down). Do not treat silence as success.
- If any machine sensor **FIRED**, name the move it feeds and whether that move is night-safe.
- If the chain is **BROKEN**, this is a global-halt condition — stop and report immediately.
- Otherwise report "org healthy, N checks due, nothing escalating" — fail-quiet is the normal state.

Do not take any asset-touching action from this command; it is a read-only health tick.
