---
description: Drive one work cycle for a department — select from its backlog by situated attention, delegate the selected items to subordinates in parallel (one Task each, if the split is genuine), then record completion. This is the PM loop; it ACTS. Pair with /org-tick (read-only health) and /org-discover (backlog generation).
argument-hint: "<role> [wip-limit] [mandate-floor]"
allowed-tools: Bash(python3 *), Task
---

Drive one **work cycle** for role **$1** against its ledger — the PM loop that turns a backlog into
delegated, recorded work. Read-only health is `/org-tick`; this command acts.

Ledger root: `${ORG_LEDGER_ROOT}` (must be set).

## 1. Select what to work on next (situated attention over the backlog)

The backlog is one queue holding both **mandate** (top-down) and **self** (self-raised) items;
attention.py prioritizes them on one footing, floors an in-zone mandate (zone of acceptance), and
picks a prefix within the WIP limit.

!`python3 "${CLAUDE_PLUGIN_ROOT}/tools/attention.py" select "${ORG_LEDGER_ROOT}" --role "$1" --wip-limit ${2:-2} --mandate-floor ${3:-1.0}`

## 1.5 Learn from prior deaths BEFORE delegating — do not repeat a known failure

The org's accumulated failures are its most valuable context (docs/07). Before spawning, read what
already died near this work and what caused it, so a selected item that would repeat a known death is
reshaped or dropped — not re-attempted blindly. This is how accumulated learning lifts output quality
(the org's core purpose); skipping it is how the same mistake gets mass-produced.

!`python3 "${CLAUDE_PLUGIN_ROOT}/tools/ledger.py" view "${ORG_LEDGER_ROOT}" nearby_deaths`
!`python3 "${CLAUDE_PLUGIN_ROOT}/tools/ledger.py" view "${ORG_LEDGER_ROOT}" death_causes`

For each selected item, check it against the deaths above:
- If it matches a **prior death** (same approach that already failed/was refuted/retired), do NOT
  re-attempt it as-is — reshape it to avoid the known cause, or drop it and say why. Carry the relevant
  death cause into the child's seam contract so the worker starts knowing what to avoid.
- If it's genuinely new territory, proceed. Silence here (no relevant deaths) is fine.

## 2. Delegate the selected items — in parallel, but only where the split is genuine

Read the `selected[]` above. Then apply the **decomposition doctrine (docs/15)** before spawning:

- **One `Task` per selected item that is a genuinely independent unit.** Emit them in a SINGLE message
  (multiple Task calls) so they run concurrently — this is the parallel fan-out. Do NOT call them one
  at a time.
- **Do not fan out reciprocally-coupled work** (docs/15 §2.3, docs/14 §granularity): if two selected
  items must constantly adjust to each other, keep them in one Task. Fineness follows *independence*,
  bounded by coordination cost — not a target depth.
- **Each child Task MUST carry a seam contract** (its slice, inputs, outputs, and the files it `owns`
  vs `must-not-touch`) — the spawn guardrail blocks a contract-less spawn, and the `owns`/`forbid`
  fields are what stop two siblings from redoing each other's work (docs/07 §2.1.1, docs/04 §6).
- **Route by domain, don't swallow it** (docs/15 §3): an item whose domain belongs to a subordinate
  role goes to that role, so its knowledge accrues to that role's doctrine — never absorbed here.
- If an item is your OWN-domain tightly-coupled work, implementing it yourself is fine (docs/14).

## 3. Record work as you go — so nothing is lost to a context wipe

The backlog is the org's memory. Work that lives only in this session's context is **gone** on `/clear`
or a crash (docs/01 R−1: the org acts only on what is written). So a cycle records itself at three
points, keyed by `candidate_id`:

1. **On starting an item** — append `cycle_started {role, candidate_id, pack_manifest_id}`. This marks
   the item in-flight and ties every later record to it.
2. **At each milestone** (and before you might stop — end of a phase, hitting a blocker, low on budget)
   — append `progress_recorded {role, candidate_id, fraction, phase, done_so_far, next_step, blocked_by,
   artifacts}`. `next_step` is the load-bearing field: it is what a fresh session resumes from.
3. **On finishing** — append `cycle_completed {role, candidate_id, outputs, ...}` so the item drains
   from the backlog.

!`echo 'Record the cycle, keyed by candidate_id (never fabricate completion): python3 "'"${CLAUDE_PLUGIN_ROOT}"'/tools/ledger.py" append "'"${ORG_LEDGER_ROOT}"'" --actor "'"$1"'" --class cycle_started|progress_recorded|cycle_completed --payload {role,candidate_id,...}. Checkpoint BEFORE you risk stopping, so the next session resumes from next_step, not from zero.'`

## Discipline — work only from the backlog

**Always work an item that is on the backlog.** If you are about to implement something that is not a
`candidate_submitted` item, submit it first (as `/org-discover` does) — otherwise the work is invisible
to the org and unrecoverable after a wipe. Pull from the backlog, record as you go; do not do untracked
work on the side.

## Discipline

- **Parallelism is a judgment, not a mandate.** Fan out genuinely-parallel work; keep coupled work
  single-threaded. Over-fanning inflates your own conformance-review span toward rubber-stamping
  (docs/04 §1) — the opposite of the goal.
- If attention.py printed **ESCALATE** (backlog cannot serve the top objective, or WIP saturated by
  stalled work), do NOT spawn to paper over it — surface the escalation; it is coverage/stall, not a
  work item.
- Take no asset-touching action here beyond spawning the delegated cycles and recording their results.
