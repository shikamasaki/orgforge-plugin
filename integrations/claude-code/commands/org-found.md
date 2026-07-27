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
   force one axis top-to-bottom. Every seam contract MUST carry the normalized shape
   **{deliverable, standard, checker, depends_on}** — `deliverable` = what one side owes, `standard`
   = the acceptance criterion the other side can check it against (a bar, not a vibe), `checker` =
   who admits it (a role DISTINCT from the deliverable's maker — usually the gate), `depends_on` =
   the roles whose output it consumes. A seam with no `standard` or no distinct `checker` is not a
   contract; it is a hope. This normalized shape is what makes two foundings CONVERGE: the pieces
   satisfy the SAME contracts even when the role names differ (docs/11 §0).

4. **ORGANIZATION.YAML + COVERAGE MANIFEST.** Fill `template/organization.SKELETON.yaml` into a
   concrete `organization.yaml`: the purpose, the domain roles (one per component/layer, each with a
   contract {deliverable, standard, checker, depends_on} in the normalized shape from step 3),
   keeping the control skeleton (supervisor / gate / skeptic / registrar) intact.

   Alongside it, emit a normalized **coverage manifest** as `coverage-manifest.md` (or `.yaml`). For
   EVERY must-have capability/deliverable the RFP names, one row: `{ rfp_capability, owning_role,
   deliverable, acceptance }` — mapping each required must-have onto the SINGLE role that owns it and
   the acceptance criterion its output must meet. The rules the manifest must satisfy (these are what
   make two foundings from the same RFP converge on the SAME contracts, docs/11 §0):
   - every must-have RFP capability appears in exactly one row (nothing required is unowned);
   - each `owning_role` and `deliverable` matches a role + contract in organization.yaml;
   - no deliverable is owned by two rows (exactly-one ownership);
   - each row has a non-empty `acceptance` and a checker distinct from the maker.
   The manifest is the RFP→contract coverage map; organization.yaml is its machine-checkable side.

   Then VALIDATE the chart (O10 mechanically gates coverage: each declared deliverable has a
   non-empty standard, exactly one owner, and a checker != maker):

   !`python3 "${CLAUDE_PLUGIN_ROOT}/tools/org_lint.py" organization.yaml "${CLAUDE_PLUGIN_ROOT}/template/constitution.yaml" "${CLAUDE_PLUGIN_ROOT}/template/moves.yaml" "${CLAUDE_PLUGIN_ROOT}/template/ledger-schema.yaml" "${CLAUDE_PLUGIN_ROOT}/template/sensors.yaml"`

   Fix anything the lint fails; a chart that does not lint is not founded. If O10 fires, a
   deliverable is missing its standard, owned twice, or self-checked — fix the contract, not the
   check. Cross-check the manifest against the chart: any must-have with no owning contract is a
   coverage GAP the founding must close before reporting up.

5. **REPORT UP for CEO review.** Summarize concisely: the must/should/nice counts, the layers +
   seams, the roles you defined, the **coverage manifest** (every must-have → its one owning role +
   acceptance, with any gaps called out), and the decisions that genuinely need the CEO's sign-off
   (stack choice, the must-have line, anything irreversible). **STOP here** — do not build the
   product. Founding is design; the build is the next phase, and the scope is the CEO's call.

Write all artifacts (inventory, architecture, organization.yaml, coverage-manifest) as files so they
can be reviewed and edited. Do not touch real assets; this command only drafts the org.

## Project the objectives onto GitHub (only if `ORG_GITHUB_REPO` is set)

If this org is steered through GitHub Issues (the web harness, or a laptop-free workflow), project each
**objective** the founding defined onto a big-picture **objective Issue** — the parent that its
department tasks will hang under. Do this *after* CEO sign-off (the Issue is the projection of an
approved objective, not of a draft), one per objective in the priority ranking:

!`echo 'For each approved objective: python3 "'"${CLAUDE_PLUGIN_ROOT}"'/tools/github_sync.py" create --repo "$ORG_GITHUB_REPO" --kind objective --objective <objective-id> --title "<objective name>" --body "<the acceptance / coverage summary>". This mints the parent Issue (orgforge:kind:objective). Department tasks are created later by /org-discover as native sub-issues under it (--kind task --parent <this#>). Skip silently if ORG_GITHUB_REPO is unset — a ledger-only org.'`

The objective Issue is a **projection of the ledger objective** (SSoT unchanged); the sub-issue tree of
department tasks that grows under it is the backlog window, regenerated — never a second source of truth.
