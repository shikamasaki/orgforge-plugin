---
description: How's my org? — one glanceable health board (GREEN / AMBER / RED) of what the org did, what's in progress, and what needs you. Read-only; the single status view. Speaks your language, not the organs'.
argument-hint: "[role]"
allowed-tools: Bash(python3 *)
---

The org's status at a glance — the one place to answer *"is my org healthy, what did it do, does it need
me?"* without reading the ledger.

!`python3 "${CLAUDE_PLUGIN_ROOT}/tools/status.py" status ${1:+--role "$1"}`

- **GREEN** — healthy; work draining, nothing escalating. Nothing for you to do.
- **AMBER** — running, something to watch (work in progress, a mandate queued). No action required yet.
- **RED** — needs you now. The board names exactly what: a halt, a repeated mistake, a wedged cycle, an
  unproven rollback. Handle those and the org keeps running.

To act on what you see: drop work on the backlog (or `/org-triage` a signal), start/keep the org running
with `/org-start`, or resolve a flagged exception. You should not need the internal commands
(`/org-work`, `/org-discover`, `/org-tick`) — those are the org's own metabolism, run on cadence.
