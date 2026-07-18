---
description: Generate self-raised backlog items for a department from its own aspiration gaps (problemistic search), and append them to the SAME backlog as source=self. This is how a department improves itself unprompted; it feeds /org-work, it does not execute work.
argument-hint: "<role> [aspiration]"
allowed-tools: Bash(python3 *)
---

Run one **issue-discovery** pass for role **$1** — the problemistic-search half of the department's
autonomy (Cyert & March, docs/12): surface where the role is falling short of its aspiration, and
raise those as **self** backlog items. It only ADDS to the backlog; `/org-work` executes it.

Ledger root: `${ORG_LEDGER_ROOT}` (must be set).

## 1. Surface the gaps (where is this role under-performing its aspiration?)

Attention names two machine signals: a backlog that cannot serve the org's top objective (a coverage
gap), and items whose latest outcome fell below aspiration. Read them:

!`python3 "${CLAUDE_PLUGIN_ROOT}/tools/attention.py" select "${ORG_LEDGER_ROOT}" --role "$1" --aspiration ${2:-0.5}`

Also read the role's recent outcomes and any negative outcome deltas for this department:

!`python3 "${CLAUDE_PLUGIN_ROOT}/tools/ledger.py" census "${ORG_LEDGER_ROOT}"`

## 2. Raise self-items — scoped to THIS role's domain, deduped against the open backlog

From the gaps above, propose backlog items that are **this role's own domain** to improve. For each:

- It must be **within $1's mission/domain** — do not raise work that belongs to another role's domain
  (that is a coverage gap for the registrar/CEO to route, not a self-item to grab; docs/15 §3).
- It must **not duplicate an open backlog item** — check the `selected[]`/`deferred[]` above first.
- Keep it small and independent enough that `/org-work` could later delegate it under one seam
  contract (docs/15 §2).

Append each as a `candidate_submitted` with **source: self** so it lands in the same backlog and
attention.py will prioritize it against mandates on one footing:

!`echo 'For each self-item, append: python3 "'"${CLAUDE_PLUGIN_ROOT}"'/tools/ledger.py" append "'"${ORG_LEDGER_ROOT}"'" --actor "'"$1"'" --class candidate_submitted --payload {"maker":"'"$1"'","candidate_id":"<id>","contract_ref":"<objective>","source":"self","evidence":[<gap-refs>]}'`

## Discipline

- **Discovery is bounded, not a fountain.** Raise items that close a real, evidenced gap; do not
  manufacture work to look busy. An empty pass (no gap → no item) is the normal, healthy outcome —
  fail-quiet, exactly like /org-tick.
- Self-items compete with mandates in the SAME backlog; a mandate carries a floor (zone of
  acceptance), so a self-item never starves a live instruction — the PM (attention.py) arbitrates.
- Append only. This command never spawns or executes; it feeds `/org-work`.
