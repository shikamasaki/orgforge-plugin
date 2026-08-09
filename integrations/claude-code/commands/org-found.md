---
description: Found an org from an RFP or brief — the org drafts its own feature inventory, architecture, and organization.yaml, then reports up for your review before anything is built. Design-only; you approve the scope.
argument-hint: "<RFP text, or a path to an RFP/brief/design doc>"
allowed-tools: Bash(*), Read, Write, Edit, Glob, Grep, Agent, Task, WebFetch, WebSearch
---

Found a new articulated organization from a brief. This is **Phase 1 — scope + structure only**;
it does NOT build the product. It produces a reviewable `organization.yaml` (+ a feature inventory
and an architecture with the seam contracts between parts), then stops and reports up so you — the
CEO — approve the scope before any build.


> **Output language:** read `output_language` from `constitution.yaml` (default `en`) and write
> Issues, specs, and human-facing text in that language (code, ledger event names, and paths stay
> in their canonical English form).

## The brief

$ARGUMENTS

(If that is a path, read it. If it is prose, treat it as the RFP verbatim.)

## What to do

You are the CEO's secretary founding the org. Work spec-driven and fail-quiet; delegate breadth,
keep the CEO's decisions minimal. Concretely:

> **FIXED FILENAMES (docs/11 §0a — a rule, not a suggestion).** Founding writes exactly these files, at
> the org root, under exactly these names, because downstream commands (`/org-decompose`, `/org-init`)
> address them **by name** rather than by search, and a stranger opening any orgforge org must find the
> design in the same place:
> `REQUIREMENTS.md` · `FEATURE-INVENTORY.md` · **`ARCHITECTURE.md` (= the whole-system design)** · `coverage-manifest.md` ·
> `organization.yaml`. Do not invent a variant name (`design.md`, `architecture-overview.md`, `.yaml`
> instead of `.md`); a renamed artifact is an unfindable one.

1. **RECEIVE → `REQUIREMENTS.md` (follow the template's format; do not invent a structure of your own)**

   Write the brief you received **shaped onto the skeleton of
   `${CLAUDE_PLUGIN_ROOT}/template/REQUIREMENTS.md`**.
   Do not devise a structure on the spot — a document of different structure per founding breaks
   the central claim, "same spec ⇒ same process", at the layer where requirements are written
   (docs/11 §0b).

   Conformance: **tailored conformance to ISO/IEC/IEEE 29148:2018** (the form §4.5.2 recognises) +
   **EARS**.
   Number requirements `FR-001` and write them in the six EARS patterns. Acceptance criteria go in
   Given-When-Then. Number success criteria `SC-001` and make them **technology-independent and
   quantitative**. **Do not fill an ambiguity with a guess — state it as
   `[NEEDS CLARIFICATION: what is unclear]`** — an agent implementing on a guess is the largest
   failure mode, and the lint below fails on any that remain.

   Once written, **always check it** (missing required sections, EARS violations, §5.2.7's banned
   words, unresolved markers, TBDs).
   **After writing the file, run this yourself through Bash**:

   ```
   python3 "${CLAUDE_PLUGIN_ROOT}/tools/req_lint.py" check REQUIREMENTS.md
   ```

   > Do not make this an automatic `!` execution. `!` blocks all expand **before** you begin work,
   > so it would try to check a file you have not written yet and fail every time (found in the
   > field).
   > A procedure needing the order "write, then check" is one you run in order yourself.

   If it fails, fix it and **run it again**. **Do not proceed on requirements that do not pass the
   check** — entering design with an ambiguity intact propagates that ambiguity into the
   implementation, where it surfaces for the first time.

2. **FEATURE INVENTORY → `FEATURE-INVENTORY.md`.** Enumerate what the brief actually requires, grouped
   and prioritized
   (must / should / nice), and an explicit EXCLUDE list (what a first cut deliberately omits). You
   MAY fan out helper subagents per area to cover breadth — if you do, start each helper's prompt
   with `INDEPENDENT:` (its output is an inventory slice, never merged with a sibling's), so the
   spawn passes the seam gate. Be thorough; this is the full sweep.

3. **ARCHITECTURE + SEAMS → `ARCHITECTURE.md` (the whole-system design).** This file is the **whole-system
   design**, and it is deliberately NOT an SDD artifact: SDD's spec/plan/tasks live in the Issue
   hierarchy (docs/11 §4b) and are per-objective/per-task, while this sits *above* all of them as the
   standing shape of the system — authored once here, amended at reorg. For the must-have set, name the layers/components and the **seam
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

   Alongside it, emit a normalized **coverage manifest** as **`coverage-manifest.md`** (that exact
   name — `/org-decompose` reads it as its input). For
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

   Lint the **org's own** spec files, falling back to the plugin templates only for files this org has
   not installed. Linting the pristine templates instead would make the check meaningless: `/org-init`
   copies those four in as the org's editable copies and the CEO edits `constitution.yaml` (purpose,
   `output_language`, clearing `SET_ME`) — so a template-based lint would pass a `SET_ME` the real org
   still carries, and would check O6/O6c/MV cross-references against the *template's* role names rather
   than the ones you just wrote.

   Keep `enforcement.judges.integration_ref` in the adopted constitution (the template defaults to
   `origin/main`). It is a governance declaration, not a branch-name convenience; removing it makes
   the first `org_cycle begin` fail closed until an explicit `--base` is supplied.

   **After writing `organization.yaml`, run this yourself through Bash** (the automatic `!`
   execution would check a file that does not exist yet):

   ```
   set -- organization.yaml
   for f in constitution.yaml moves.yaml ledger-schema.yaml sensors.yaml; do
     if [ -f "$f" ]; then set -- "$@" "$f"; else set -- "$@" "${CLAUDE_PLUGIN_ROOT}/template/$f"; fi
   done
   python3 "${CLAUDE_PLUGIN_ROOT}/tools/org_lint.py" "$@"
   ```

   > Use `set --`'s positional parameters. Building a string as `A="$A $f"` and passing `$A`
   > means **zsh does not word-split**, so the whole thing arrives as one argument and usage is
   > printed for too few arguments (found in the field).

   Fix anything the lint fails; a chart that does not lint is not founded. If O10 fires, a
   deliverable is missing its standard, owned twice, or self-checked — fix the contract, not the
   check. Cross-check the manifest against the chart: any must-have with no owning contract is a
   coverage GAP the founding must close before reporting up.

## File the prerequisites only a human can carry out as Issues (docs/11 §0c) — do not skip this

**An org must not file only the work it can do itself and let what it needs from a human fall into
prose.**
In a founding in the field, three of them (creating the Supabase project, registering the Google
OAuth client,
setting GitHub branch protection) survived only in the session's text and entered neither an Issue
nor the ledger.
The result was the gap where `/org` displayed GREEN while work could not actually be started.

**A request to a human is exactly what stops things longest when it is forgotten.** Always give it
a structure.

The sources to extract from are already at hand:

- the **Open Questions** section of `REQUIREMENTS.md` — what you yourself wrote as "decide before
  implementing"
- its **Assumptions** section — what you wrote as "the CEO provides this" or "an account is
  needed"
- among `ARCHITECTURE.md`'s technology choices, those needing **an external service registration
  or a key to be issued**
- everything you noticed while drafting as "I cannot do this myself"

The test is simple: **does it complete within the org's tools?** Creating an account, billing,
registering an OAuth client, acquiring a domain, store review, and GitHub's administrative
settings (branch protection and the like) can none of them be done by anyone but a human.

File each one that qualifies as its own Issue:

```
python3 "${CLAUDE_PLUGIN_ROOT}/tools/github_sync.py" needs-human \
  --title "<the work a human does (one line)>" \
  --body "<where, what to do, and what to hand back. Write the steps out>" \
  --objective "<the related objective id>" --parent <the objective Issue number> \
  --blocks "<the Issue numbers that cannot start until this is done>"
```

Once you write `--blocks`, **append `Depends on: #<this Issue's number>` to the body of each
downstream Issue** (the orthography is that literal — an annotation after the reference is allowed,
but a dependency always takes the `#number` form; a dependency in prose alone is invisible to
`ready`, Issue #103). Only then does `ready` read "waiting on a human" as a dependency and stop
handing the blocked task to a maker.

5. **REPORT UP for CEO review.** Summarize concisely: the must/should/nice counts, the layers +
   seams, the roles you defined, the **coverage manifest** (every must-have → its one owning role +
   acceptance, with any gaps called out), and the decisions that genuinely need the CEO's sign-off
   (stack choice, the must-have line, anything irreversible), and
   **the list of needs-human Issues you filed** (this becomes the CEO's task list). **STOP here** — do not build the
   product, and do not mint task Issues. Founding is design; the scope is the CEO's call. Once the CEO
   signs off, the next step is **`/org-decompose`**, which turns `coverage-manifest.md` +
   `ARCHITECTURE.md` into the atomic task Issues — tell the CEO that in your report.

Write all five artifacts — `REQUIREMENTS.md`, `FEATURE-INVENTORY.md`, `ARCHITECTURE.md`, `coverage-manifest.md`,
`organization.yaml` — as files under those exact names (docs/11 §0a) so they can be reviewed, edited,
and addressed by name downstream. Do not touch real assets; this command only drafts the org.

## Record the CEO's approval in the ledger — do not let it end as spoken words

Even with the instruction "create the objective Issue after approval", **there was no means of
recording the approval itself**, so the fact of it was left nowhere (found in the field). A
founding is a charter-tier decision, and docs/05 §1 states outright that it needs a human's
approval. With that absent from the ledger, "who approved what, and when" cannot be traced later.

Once you have the CEO's approval, record it **before creating any Issue**:

```
python3 "${CLAUDE_PLUGIN_ROOT}/tools/ledger.py" append --actor ceo \
  --class proposal_adjudicated \
  --payload '{"proposal_id":"founding","decision":"approve","human":"<CEO>"}'
```

Where something was not approved, use `decision: amend` and leave in the payload what you were told
to change.
**If you do not have approval, do not proceed past this point** — creating the objective Issue is a
projection of the approval, not a substitute for it.

## Project the objectives onto GitHub (only if `ORG_GITHUB_REPO` is set)

If this org is steered through GitHub Issues (the web harness, or a laptop-free workflow), project each
**objective** the founding defined onto a big-picture **objective Issue** — the parent that its
department tasks will hang under. Do this *after* CEO sign-off (the Issue is the projection of an
approved objective, not of a draft), one per objective in the priority ranking:

!`echo 'For each approved objective: python3 "'"${CLAUDE_PLUGIN_ROOT}"'/tools/github_sync.py" create --repo "$ORG_GITHUB_REPO" --kind objective --objective <objective-id> --title "<objective name>" --body "<the acceptance / coverage summary>". This mints the parent Issue (orgforge:kind:objective). Department tasks are created next by /org-decompose as native sub-issues under it (--kind task --parent <this#>), carrying source=mandate and a coverage_row trailer. (/org-discover only adds SELF-raised items later, which are source=self and carry no trailer — it is not the RFP decomposition step.) Skip silently if ORG_GITHUB_REPO is unset — a ledger-only org.'`

The objective Issue is a **projection of the ledger objective** (SSoT unchanged); the sub-issue tree of
department tasks that grows under it is the backlog window, regenerated — never a second source of truth.

## Close the requirements and design phases — or the first task cannot start

**This step is not optional, and skipping it stops the org before it builds anything.** The SDLC mold
(docs/11 §2) rejects `phase_started{implement}` unless `design` was admitted, and `design` unless
`requirements` was. `/org-work` fires `phase_started{implement}` at delegation — so with no phase
history, **task #1 is rejected at the ledger** with a message naming a predecessor that nobody was ever
told to write. Founding is where those two phases genuinely happen, and where their evidence exists:

- **requirements** — the artifact is `REQUIREMENTS.md` + `FEATURE-INVENTORY.md` (what must be built, with the
  must/should/nice line and the explicit EXCLUDE list).
- **design** — the artifact is `ARCHITECTURE.md` + `coverage-manifest.md` + the linted
  `organization.yaml` (the whole-system design and its seam contracts, each must-have owned once).

So after CEO sign-off, walk each objective's deliverable through both phases — **entered, then
admitted** (an admission with no matching start is rejected; a phase cannot be admitted without having
been entered). The `deliverable` must be the SAME identifier `/org-work` will later use — the objective
Issue number if you minted one, otherwise the objective id — written consistently, since the chain keys
on it:

!`echo 'Per objective deliverable D, in this order: for PHASE in requirements design; do python3 "'"${CLAUDE_PLUGIN_ROOT}"'/tools/ledger.py" append --actor supervisor --class phase_started --payload '"'"'{"deliverable":"<D>","phase":"<PHASE>","role":"supervisor"}'"'"'; python3 "'"${CLAUDE_PLUGIN_ROOT}"'/tools/ledger.py" append --actor gate --class phase_admitted --payload '"'"'{"deliverable":"<D>","phase":"<PHASE>","verdict":"pass","admitter":"gate","evidence_ref":"<REQUIREMENTS.md+FEATURE-INVENTORY.md for requirements; ARCHITECTURE.md+coverage-manifest.md+organization.yaml for design>"}'"'"'; done'`

Note the **actors differ**: the supervisor enters the phase, the gate admits it. The ledger enforces
that separation at write time for admissions (docs/11 §4f.1) — the same actor cannot both do the work
and sign it off. Record the admission's reasoning on the objective Issue too (`github_sync decide
--event phase_admitted --verdict pass --why … --evidence "<the artifacts>"`), since no human reviews it.

Where no org can be discovered (neither `.orgforge/` nor `organization.yaml`), say so and stop.
`/org-init` has to be run in this directory first.
