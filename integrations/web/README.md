# The web-harness projection — run orgforge from claude.ai/code and GitHub, phone-friendly

This is orgforge's third harness projection, beside `claude-code/` (CLI/desktop) and `codex/`. It runs
the **same neutral core** (`tools/`, `integrations/common/`) on **Claude Code on the web** (claude.ai/code)
against a GitHub repository, so an org can be driven and observed from a phone with no laptop open. It
changes **where state lives and how the human steers**, not what the org is.

## The one thing that changes: state lives in the repo, steered through GitHub

Claude Code on the web runs in a **stateless cloud VM** — a fresh clone of the repo each session, no
persistent local filesystem (verified against the Claude Code docs). Two consequences fix the whole design:

1. **The ledger is committed to the repo.** The append-only, hash-chained ledger (the audit record of "what
   happened") lives at a repo path (e.g. `.orgforge/ledger/ledger.jsonl`), committed like any file. A
   fresh cloud session reads it to recover org state; each cycle appends and commits. This is exactly the
   pattern the Claude Code web docs recommend for carrying state. **The SSoT does not change** — it is
   still code + the domain model (conventions + org spec); the committed ledger is the audit record that
   lets a stateless VM recover process state (and the human's phone reach it).

2. **The human steers through GitHub, compressed to a label.** The backlog is *projected* to GitHub
   Issues (a view, not a source of truth). The human's whole input is applying a label to an Issue from
   their phone. This is the y-hirakaw "instruction compressed to one label," and the docs/12 §5 front
   door, realized on GitHub.

**What a GitHub Issue IS here — a disposable work window, never a source of truth (docs/12 §6).** A
task Issue is a *disposable prompt*: it holds the task's spec (the SPEC structure) and its work-log so a
human can steer and watch from a phone. But **the Issue is not the SSoT and neither is the ledger** —
the SSoT is **code + the domain model** (conventions + org spec). The Issue drives the work; the *result*
of the work (the code, and any settled decision co-committed to conventions) is what survives and is
re-inferable. Close an Issue, delete it, lose it — the truth is intact, because the decisions landed in
the code and the domain model, not in the Issue. So do **not** treat an Issue (or a work-log comment, or
a ledger event) as the place a decision lives: those are the *window and the receipt*; the decision lives
in the co-committed artifact. This is the same lesson as SPEC-is-not-an-SSoT-file: a task-scoped record
(Issue, Spec, event) is a fragment that must never become the source of truth (the fragment-rot trap).

The plugin itself works unchanged: Claude Code on the web loads repo-committed `.claude/settings.json`
hooks (PreToolUse / SessionStart fire) and plugin commands — so the guardrails, the doctrine injection,
`/org-tick`, `/org-work` all run identically to the CLI. **Same plugin, both harnesses;** only the state
location and the steering surface differ.

## Labels: work-lock, state, priority, dependency

The Issue label system carries five orthogonal things the org already tracks internally:

### 0. Kind & hierarchy — the big-picture objective vs. a department's task
The org has two levels: an **objective** (the RFP / business goal) and the **department tasks** that
decompose it. Both project onto GitHub Issues, and the two are kept distinct so a phone view — and a
web or local session picking work — never confuses "the goal" with "a unit of work":

- `orgforge:kind:objective` — the **big-picture Issue** (a projection of an org objective). It is a
  *parent / roll-up*, not something an agent claims and works directly.
- `orgforge:kind:task` — a **department's unit of work** (a projection of a `candidate_submitted`).
  This is the workable item: it is claimed, staged, and closed.
- A task is attached to its objective as a **native GitHub sub-issue** (`github_sync create --kind task
  --parent <objective#>` → the REST `sub_issues` API), so GitHub itself shows the objective's sub-issue
  list and progress roll-up — R0: we borrow GitHub's own parent/child primitive rather than invent a
  link. `orgforge:dept:<name>` tags which department owns the task.
- `github_sync ready` lists **tasks** by default (objectives are parents, not claimable work); pass
  `--kind objective` to see objectives or `--kind any` for both. **SSoT is unchanged:** the objective
  Issue projects an org objective, the task Issue projects a candidate — the ledger stays authoritative,
  the two-level Issue tree is its regenerated window.

### 1. Work-lock (prevent concurrent work — the user's requirement)
GitHub's atomic label operation IS the exclusion lock (R0: borrow the host's primitive; the org does not
build a lease). The truth of "who is working this" is the label; the ledger records the claim as an
audited fact but does not arbitrate the race.

- `orgforge:claimed:<agent>` — an agent (a web session, a local session) claims an Issue by adding this
  label. **Before starting work on an Issue, an agent checks it carries no other `claimed:*` label; if it
  does, it does not touch it** — this is the GitHub projection of the 0.7.2 concurrent-write prevention
  (seam-gate owns-collision), so a web Claude and a local Claude never work the same Issue at once.
- The claim is released (label removed) on completion or abandonment; a stale claim past a TTL is a
  reclaim signal (the registrar sweeps it).

### 2. State (the backlog stage — the label-machine)
The Issue's lifecycle label mirrors the ledger stage (docs/09), so the board is legible on a phone:

- `orgforge:ready` — a triaged backlog item, available to claim. *The human applies this to steer.*
- `orgforge:in-progress` — a cycle is working it (`cycle_started`).
- `orgforge:blocked` — waiting on a dependency (see below).
- `orgforge:needs-human` — escalation; the human decides (mandate clash, irreversible action).
- `orgforge:done` — completed (`cycle_completed`); the Issue closes.

### 2b. Work-log — the Issue is the MAIN running record (so work isn't terminal-bound)
The stage label is the *coarse* state; the **work-log** is the fine-grained running record, and on the
web harness **the Issue comment thread is its primary home**, not the ledger. The reason is the whole
point of this projection: the ledger is a local file a phone or a fresh cloud session can't see, but the
Issue is reachable from anywhere — so the record a human and the next session read to know "where does
this stand" must be on the Issue. On each milestone the cycle **posts a comment to the task Issue**
(`github_sync log --issue N --event … --event-id <id>`) — the main work-log — and writes the ledger a
**receipt** of the same milestone for audit / `requires_prior` / crash-safe resume. Neither is the SSoT
(that's the code + domain model); the Issue is the *work surface*, the ledger is the *audit record*. It
is **idempotent** — each comment carries a hidden `orgforge:event:<id>` marker, so a replayed cycle logs
each milestone exactly once (docs/11 §0). A ledger-only run (no `ORG_GITHUB_REPO`) keeps the work-log in
the ledger instead — but the moment GitHub is the steering surface, the Issue leads.

### 3. Priority (measured, not guessed — the user's requirement)
Priority is not a raw label the human sets by feel; it is **`attention.py`'s situated-attention score**
(alignment to the org-wide `priority_ranking_set` + problemistic-search boost + mandate floor) projected
onto the Issue, so the phone view shows *why* something is ranked, auditable:

- `orgforge:objective:<id>` — which org objective this Issue serves (the `contract_ref` attention scores
  against the ranking). This is what makes priority a *derived, org-anchored* number, not a hunch.
- `orgforge:mandate` vs `orgforge:self` — the intake source (mandate rides the zone-of-acceptance floor).
- The computed rank is written to the Issue (a comment or a `priority: N` line) by the tick, regenerated
  from `attention.py` — a projection, never hand-edited. An Issue whose objective is **off** the org
  ranking is flagged (the drift signal attention already emits), visible as `orgforge:off-ranking`.

### 4. Dependency (measured — the user's requirement)
Dependency uses GitHub's native "blocked by" plus the org's seam model:

- A body line `Depends on: #<n>, #<m>` (GitHub renders the linkage) mirrors the seam-contract
  `depends_on` (organization.yaml) and the ledger's `work_claimed.depends_on`. An Issue is not
  `ready` while any Issue it depends on is open — the tick sets `orgforge:blocked` and, past a
  threshold, raises `dependency_stall_raised` (today's schema) so a stuck dependency escalates rather
  than silently waits.
- Cross-Issue dependency is thus *machine-read*: the tick computes the ready-set (no open dependency),
  attention ranks within it, and the top item is claimed — the same pipeline as the local backlog, over
  Issues.

## The metabolism, on the web (Routines)

The drive is delegated to **Routines** (Claude Code's scheduled cloud agents), the web analogue of
`/loop` / cron. A routine triggers on:

- **a schedule** (the `/org-tick` cadence — health, missed-check, stall, repeated-death),
- **a GitHub event** (an Issue gets `orgforge:ready` → `/org-triage`/`/org-work` picks it up; the label
  IS the trigger), or
- **an API call** (a phone shortcut → run a cycle).

The routine runs the same commands (`/org-tick`, `/org-work`, `/org-discover`), reads/writes the
committed ledger, syncs Issue labels, and opens a PR for asset-touching work — all with the guardrails
firing. Escalations reach the phone via the Issue (`orgforge:needs-human`) and PushNotification.

## The sync contract (ledger ⇄ Issues) — one direction is authoritative

To honor "the SSoT does not change," the sync is deliberately asymmetric:

- **ledger → Issues (projection, regenerated):** stage, computed priority, dependency/blocked, done —
  written *from* the ledger onto Issues. Never hand-edited; the Issue is a view.
- **Issues → ledger (intake, gated):** the human's label actions (`ready`, `needs-human` resolution) and
  new Issues enter the ledger through `/org-triage` (a `candidate_submitted`), exactly as an external
  signal does today. A label is a steering input; the ledger records it as the fact.

So there is no dual-management ambiguity (the user's own "avoid dual management" rule): the ledger is the
authoritative record of what happened, the Issue board is its regenerated window plus a gated intake — the same discipline as doctrine's per-harness
files (spec is canonical, projections regenerate).

*Status: this document is the design for the web-harness projection. The neutral core (tools/, hooks) is
unchanged and already web-compatible (repo-committed plugin config works on claude.ai/code, per the Claude
Code docs). What this projection adds — the ledger-in-repo path, the label system, the ledger⇄Issue sync,
and the Routines wiring — is specified here and built in this folder; it introduces no new SSoT and no
runtime the host doesn't already provide (GitHub labels = the lock, Routines = the scheduler).*
