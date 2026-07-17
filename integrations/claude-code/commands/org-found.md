---
description: Found an org from an RFP or brief — the org drafts its own feature inventory, architecture, and organization.yaml, then reports up for your review before anything is built. Design-only; you approve the scope.
argument-hint: "<RFP text, or a path to an RFP/brief/design doc>"
allowed-tools: Bash(python3 *), Read, Write, Agent
---

Found a new articulated organization from a brief. This is **Phase 1 — scope + structure only**;
it does NOT build the product. It produces a reviewable `organization.yaml` (+ a feature inventory
and an architecture with the seam contracts between parts), then stops and reports up so you — the
CEO — approve the scope before any build.

## The brief

$ARGUMENTS

(If that is a path, read it. If it is prose, treat it as the RFP verbatim.)

## What to do

You are the CEO's secretary founding the org. Work spec-driven and fail-quiet; delegate breadth,
keep the CEO's decisions minimal. Concretely:

1. **RECEIVE** the brief. Restate the purpose in one sentence — an outcome, not a metric.

2. **FEATURE INVENTORY.** Enumerate what the brief actually requires, grouped and prioritized
   (must / should / nice), and an explicit EXCLUDE list (what a first cut deliberately omits). You
   MAY fan out helper subagents per area to cover breadth — if you do, start each helper's prompt
   with `INDEPENDENT:` (its output is an inventory slice, never merged with a sibling's), so the
   spawn passes the seam gate. Be thorough; this is the 洗い出し.

3. **ARCHITECTURE + SEAMS.** For the must-have set, name the layers/components and the **seam
   contracts** between them (the interface each side depends on) — precise enough that the pieces
   could be built in parallel without drift later. Choose the split axis that fits the work; do not
   force one axis top-to-bottom.

4. **ORGANIZATION.YAML.** Fill `template/organization.SKELETON.yaml` into a concrete
   `organization.yaml`: the purpose, the domain roles (one per component/layer, with a contract
   {deliverable, standard, checker, depends_on} reflecting the seams), keeping the control skeleton
   (supervisor / gate / skeptic / registrar) intact. Then VALIDATE it:

   !`python3 "${CLAUDE_PLUGIN_ROOT}/tools/org_lint.py" organization.yaml "${CLAUDE_PLUGIN_ROOT}/template/constitution.yaml" "${CLAUDE_PLUGIN_ROOT}/template/moves.yaml" "${CLAUDE_PLUGIN_ROOT}/template/ledger-schema.yaml" "${CLAUDE_PLUGIN_ROOT}/template/sensors.yaml"`

   Fix anything the lint fails; a chart that does not lint is not founded.

5. **REPORT UP for CEO review.** Summarize concisely: the must/should/nice counts, the layers +
   seams, the roles you defined, and the decisions that genuinely need the CEO's sign-off (stack
   choice, the must-have line, anything irreversible). **STOP here** — do not build the product.
   Founding is design; the build is the next phase, and the scope is the CEO's call.

Write all artifacts (inventory, architecture, organization.yaml) as files so they can be reviewed
and edited. Do not touch real assets; this command only drafts the org.
