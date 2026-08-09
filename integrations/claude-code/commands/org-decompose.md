---
description: Turn the approved founding design (coverage-manifest.md + ARCHITECTURE.md) into the atomic SPEC task Issues — one per independently-completable unit, each a native sub-issue of its objective, each carrying the full spec so any environment can pick it up. The bridge between /org-found (design) and /org-work (execution).
argument-hint: "[objective-id] [--dry-run]"
allowed-tools: Bash(*), Read, Write, Edit, Glob, Grep, Agent, Task, WebFetch, WebSearch
---

Decompose the **approved** founding design into the backlog: every must-have in the coverage manifest
becomes one or more **atomic task Issues**, written in the SPEC structure, hung under its objective
Issue. This is the step between `/org-found` (which designs and stops) and `/org-work` (which executes);
without it the design never becomes workable units, and the must-haves sit unowned.

This command projects onto GitHub Issues, so it needs an org to write into and a backlog repo to write
to. Both are **discovered** from the working directory (`tools/discover.py`) — no environment setup.
Check them up front, not one failing `create` at a time: with no repo, every Issue creation fails at
`gh` *after* you have drafted full SPEC bodies for the whole manifest.

!`D="${CLAUDE_PLUGIN_ROOT}/tools/discover.py"; LR="$(python3 "$D" ledger 2>/dev/null)"; GR="$(python3 "$D" repo 2>/dev/null)"; missing=""; [ -n "$LR" ] || missing="$missing ORG(ledger)"; [ -n "$GR" ] || missing="$missing GitHub-remote"; if [ -n "$missing" ]; then echo "STOP —$missing not discoverable from $(pwd). Run /org-init here first (and add a git remote if the backlog is missing)."; else echo "preconditions OK — ledger: $LR · backlog repo: $GR"; fi`

If that prints **STOP**, stop and tell the CEO. Do not proceed to draft specs against an unset repo.

**This command works against the org in the current directory at run time.** If the line above
points at a different org, the session is not in the intended repository — proceeding cuts Issues
into someone else's org. Stop and fix the location.

> **Output language:** read `output_language` from `constitution.yaml` (default `en`) and write
> Issue bodies, specs, and human-facing text in that language (code, ledger event names, paths, and
> the value of the `coverage_row:` trailer stay in their canonical English form — the trailer is a
> machine matching key and must not differ from the manifest by a single character).

## 0. Preconditions — read the FIXED founding artifacts (docs/11 §0a)

These filenames are fixed by rule, so this command addresses them by name rather than asking you where
they are. Read them now:

- **`coverage-manifest.md`** — the input. One row per must-have: `{rfp_capability, owning_role,
  deliverable, acceptance}`. This is the work list; nothing outside it is RFP-derived scope.
- **`ARCHITECTURE.md`** — the whole-system design. The layers/components and the **seam contracts**
  `{deliverable, standard, checker, depends_on}`. This is where each task's `provides` / `depends_on` /
  `owns` / boundary come from — do not re-derive them, *read* them.
- **`organization.yaml`** — which role owns what (the machine-checkable side of the manifest).
- **`REQUIREMENTS.md`** — for tracing intent when a manifest row is terse.

If `coverage-manifest.md` or `ARCHITECTURE.md` is missing, **STOP**: founding is incomplete, or it wrote
variant filenames. Run `/org-found` (or rename the artifacts to the canonical names) — do not improvise a
decomposition from the RFP alone, because then the coverage check below has nothing to verify against.

Also confirm the CEO **approved** the founding. Decomposition mints real Issues; doing it on an
unapproved draft floods the backlog with work the CEO may cut.

## 1. Carve each manifest row into ATOMIC units

For each must-have row (filter to `$1`'s objective if an objective-id was given), decide how many task
Issues it becomes. The doctrine (docs/11 §4b, docs/03 §6.2):

- **One task = one independently-completable unit** — one endpoint, one function, one screen, one
  migration. Not a domain, not "the auth system". INVEST's *Small* says the same thing, and its
  grounds are not estimation accuracy — *"Above this size, and it seems to be too hard to know
  what's in the story's scope"* (Wake 2003). **The boundary of the scope stops being
  recognisable**, and that is the reason to split; #11 in the field was exactly that, changing
  scope five times.
- **Do not split by layer or by file.** One for the UI and one for the DB is neither independent
  nor valuable (the anti-pattern Humanizing Work names outright). A unit is *"a valuable change in
  system behavior such that you'll probably have to touch multiple architectural layers"* —
  **touching several layers is normal**. On top of that, `owns` is a constraint for **avoiding
  collisions**, not the judgment about splitting itself.
- **Split at every seam where sibling `owns` sets are disjoint.** Disjoint `owns` ⇒ the two units are
  `[P]` parallel-safe ⇒ they are separate Issues. This is the same decision as Spec Kit's `[P]`
  ("different files, no dependencies").
- **Even with the same `owns`, a different way of breaking and a different means of verification
  make it a different Issue.** This is an axis the intersection of `owns` does not capture, and it
  was the most expensive one in the field (below). What to ask is:

  > When this deliverable breaks, **is there one way it breaks**? Does verifying it need **one
  > means**?

  Two or more makes it a candidate for splitting. #11 in the field (the core schema and RLS) was
  closed under `supabase/` and so was not split by the `owns` criterion, while its content held
  **two things differing in both how they break and how they are verified**: "the shape of the
  schema (guarded by types and constraints)" and "authorization (guarded by attack scenarios)".
  As a result the gate began every round by searching for where to look, five migrations
  interfered with each other (0010 broke what 0009 fixed, and 0011 turned two others RED), and
  **twelve rounds did not finish it**. On the same day #8 (one function) and #10 (a CI setting)
  passed in one or two rounds.

  Kiro's norm says the same thing another way — a task is *"Implement X function" rather than
  "Support X feature"*. Bring it down not to a unit of feature but to **a unit answering one way
  of breaking**.
- **Do NOT split reciprocally-coupled work.** If two candidate units must constantly adjust to each
  other, they are ONE Issue — over-splitting coupled work costs far more than it saves (docs/12 §6).
- **Order by dependency.** A unit that consumes another's seam records `depends_on: #<issue>` and the
  state it needs (`merged to develop`). Create the depended-upon Issue first so the number exists.

**Before cutting, look at whether the requirements themselves are thin.** A failed split often
shows up as a missing requirement. #11 in the field had four of its twelve EARS items setting
authorization, and not one of them set "what can be done once inside" (the only inside thing
touched was the nickname — a decorative text column). **The amount, the payer, the direction of
the debt, and group ownership were undefended**, and the last six rounds of rework became work
answering no MUST on the Issue at all. Against the assets this deliverable handles, do the MUSTs
set **whom they protect from whom** — where only one side is set, write the requirement in before
cutting. `github_sync split-check` runs the same check after filing, but **noticing it at filing
time is cheaper**.

Lean toward **finer** splits when in doubt about independent units (a coarse task produces coarse
output),
and toward **keeping together** when the coupling is genuine. You MAY fan out helper subagents to draft
several rows' task-sets concurrently — prefix each with `INDEPENDENT:` so the spawn passes the seam gate,
and give each helper one row (never two helpers on the same row, or they mint duplicate Issues).

## 2. Derive each task's `candidate_id` deterministically (reproducibility F4)

Same rule as `/org-discover`: the id is a function of *what the task is*, never of when it was minted, so
re-running decomposition on the same manifest is idempotent rather than duplicating the backlog.

Derive it with the organ — **do not hand-compute it or paste a shell one-liner**; the fields are joined
on a unit separator that a shell `echo` silently eats, and losing it makes different tasks collide onto
one id (whereupon the second task's ledger append is swallowed as a "replay" and it never enters the
backlog at all):

!`echo 'Per task: python3 "'"${CLAUDE_PLUGIN_ROOT}"'/tools/github_sync.py" candidate-id --role "<owning_role>" --contract "<objective-id>" --gap "<one-line task title>"'`

Append each as a backlog candidate, using the derived id as the natural key (a replay is a ledger-layer
no-op):

!`echo 'Per task: python3 "'"${CLAUDE_PLUGIN_ROOT}"'/tools/ledger.py" append --actor supervisor --class candidate_submitted --natural-key "<cand-id>" --payload '"'"'{"maker":"<owning_role>","candidate_id":"<cand-id>","contract_ref":"<objective-id>","source":"mandate","evidence":["coverage-manifest.md:<rfp_capability>"]}'"'"''`

`source: mandate` — an RFP-derived task is top-down scope, unlike `/org-discover`'s self-raised items, so
attention.py floors it correctly against self-items.

## 3. Write the FULL SPEC into each Issue body — this is what makes it environment-independent

Read `${CLAUDE_PLUGIN_ROOT}/template/SPEC.md` and fill **every** section for this task. The Issue body is
the *only* context a maker in another environment gets — a web session, a different machine, a fresh
agent with none of this conversation. A body that is a bare id or a one-line title is an empty shell.

The sections that carry the environment-independence (do not skimp on these):

- **Working context** — the clone URL, the exact `feat/issue-<N>-<slug>` branch (from
  `github_sync branch --issue <N>`), the literal one-command setup + test commands *and the directory to
  run them in*, and the 1–3 entry files. A stranger pastes these and is running.
- **MUST in EARS** — every acceptance criterion as WHEN/WHILE/IF/WHERE…SHALL. Carry the manifest row's
  `acceptance` in verbatim as one of them; prose like "auth works" is not a bar.
- **Seam contract** — `provides` (the named output shape), one worked `example` (input → output),
  `depends_on` (#Issue + required state + the exact seam consumed), `owns` (disjoint from siblings),
  `boundary` (the adjacent work that is NOT this task's), `tools/sources`. Take these from
  `ARCHITECTURE.md`'s seam contracts.
- **Verification** — the exact DoD command whose green output means done (the same command the gate runs)、
  and **the judgment of done**: "done once the MUSTs above go RED→GREEN. A defect found after
  starting that falls outside the scope is not fixed in this Issue but becomes another one".
  **Without that one line an Issue does not converge** — in the field, every finding from the
  fourth round onward of an Issue that reworked eight times was absent from its MUSTs.
  It is written on the spec side so that maker, gate, and skeptic all read the same completion
  condition.
- **Out of scope** — including prior deaths, so a fresh maker does not re-derive a known dead end:

!`python3 "${CLAUDE_PLUGIN_ROOT}/tools/ledger.py" view nearby_deaths 2>/dev/null || echo "(no death recorded yet — normal at a first founding)"`

Two trailers at the bottom of every body, for machine traceability:

```
candidate_id: <cand-id>
coverage_row: <rfp_capability verbatim from coverage-manifest.md>
```

The **`coverage_row:` trailer is load-bearing** — step 5's coverage gate matches on it exactly. Copy the
capability cell character-for-character; a paraphrase reads as an orphan and fails the gate. Do not
translate it, even when the rest of the body is in the org's `output_language`: it is a machine key, not
prose. Markdown decoration around the label (`**coverage_row:**`, `` `coverage_row:` ``, a list bullet)
is tolerated by the parser, but the **value** must be the bare capability text.

Every RFP-derived task must carry one: an `orgforge:mandate` task with no trailer now fails the gate
(it would otherwise float unattached to any requirement while the manifest still reads green).

## 4. Create the Issues — as native sub-issues of their objective

!`echo 'Per task: python3 "'"${CLAUDE_PLUGIN_ROOT}"'/tools/github_sync.py" create --repo "$ORG_GITHUB_REPO" --kind task --parent <objective-issue-#> --dept "<owning_role>" --objective "<objective-id>" --source mandate --title "<one-line task title>" --depends "<dep issue numbers, comma-separated>" --body "<the FILLED SPEC.md + the two trailers>"'`

`create` is idempotent on (title, objective) across **open and closed** Issues: re-running decomposition
returns the existing Issue rather than minting a duplicate, and re-asserts the parent link. Closed
counts too — a delivered task is closed, and re-minting it would duplicate finished work and re-open
settled scope. This is what makes the re-run safe as a repair step after a manifest amendment.

**Pass `--depends` AND write the SPEC's `depends_on:` line — they are not redundant.** `--depends`
appends a `Depends on: #N` line that `github_sync ready` parses to decide whether a task is *workable*
(it withholds an Issue whose dependency is still open). The SPEC's `- **depends_on:**` bullet is the
*human/maker-facing* contract — which seam is consumed and in what state — and is what `split-check`
reads. Omit `--depends` and a blocked task will be handed to a maker as ready; omit the SPEC line and the
maker gets no idea what they're waiting on.

The literal `ready` accepts is **`Depends on: #N[, #M]`** (the orthography `--depends` and
`--carved-from` write).
Reading is generous: markdown decoration on the heading (`**Depends on:**`, lists, quotes),
`Depends-on`/`depends_on`, a space before the colon, and **an annotation after the reference**
(e.g. `Depends on: #63 (not yet integrated into main)`) are all allowed.
`Depends on: none` is an explicit declaration of "no dependencies". A dependency must always be
written in the `#number` form, though — a dependency in prose alone is invisible to `ready`
(Issue #103 / OBS-051).

**When splitting "this is outside #N's scope" out into an Issue mid-rework, use
`create --carved-from <the original Issue number>`.** A carve-out depends on its original —
without exception (the parts exist only in the original worktree).
`--carved-from` adds `Depends on: #N` automatically, and `ready` does not hand it to a maker until
the original closes.

Then shape-check each new Issue — it warns (exit 10) when a task is too coarse (`owns` spanning
territories), depends on something still open, or has non-EARS acceptance:

!`echo 'Per created issue: python3 "'"${CLAUDE_PLUGIN_ROOT}"'/tools/github_sync.py" split-check --repo "$ORG_GITHUB_REPO" --issue <N>'`

Fix what it flags by **re-splitting the Issue**, not by loosening the spec.

## 4b. File the prerequisites only a human can carry out as Issues (docs/11 §0c) — do not skip this

**An org must not file only the work it can do itself and let what it needs from a human fall into
prose.**
This includes anything you noticed while drafting as "outside #N's scope". In a founding in the
field, three of them (creating the Supabase project, registering the Google OAuth client,
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

## 5. The coverage gate — prove no must-have was dropped

This is the check that makes decomposition trustworthy: `/org-found`'s O10 proved every must-have has one
owning *contract*; this proves every must-have reached at least one *task Issue*. A must-have that never
became an Issue is silently unbuilt, and nothing downstream would ever notice.

**After you finish creating the task Issues, run this yourself through Bash** (the automatic `!`
execution runs while there is not one Issue yet, and every row comes out as a GAP):

```
python3 "${CLAUDE_PLUGIN_ROOT}/tools/github_sync.py" coverage-check --manifest coverage-manifest.md
```

**Exit 10 = a gap.** Decompose the listed must-haves and re-run until it exits 0. Do not report the
decomposition complete while a GAP line is printed — an uncovered must-have is the one failure this whole
command exists to prevent. (Orphan-trailer warnings mean a typo'd `coverage_row:`; fix the trailer.)

## 6. Report up

Summarize for the CEO: how many task Issues per objective, which manifest rows fanned into several units
and why, which were deliberately kept as one (the coupled ones), the dependency order (what must land
first), and the coverage-check result — **`N/N` rows covered**, or the remaining gaps.

Then tell them the next step: the backlog is now workable from anywhere —
`/org-work <role>` locally, or claiming an Issue from any other environment
(`github_sync claim --issue N --agent <you>`), because each Issue carries its own full spec.

## Discipline

- **Decompose from the manifest, not from imagination.** Every RFP-derived task traces to a
  `coverage_row`. Work that has no manifest row is either a `/org-discover` self-item or scope creep.
- **This command creates and records; it does not build.** No implementation here — `/org-work` executes.
- **Re-running is safe.** Deterministic ids + idempotent `create` mean a second pass fills gaps rather
  than duplicating the backlog. That is what makes it usable as a repair step after a manifest amendment.
