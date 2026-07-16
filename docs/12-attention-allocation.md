# 12 — Attention allocation: how a department decides what to work on next

The org-wide priority ranking (docs/11 §3, `resource.py rank`) says which **objectives** matter.
Nothing said how a single department, handed its own backlog, decides **what to work on next**.
That decision was left implicit — the department's LLM just picked, unrecorded and unaudited, and
with no connection to the org-wide ranking. That is precisely the failure this whole repo exists
to remove: **an AI department can only act on what is written down, so its internal triage must be
articulated, not left tacit.** A human unit's manager can hold the triage in their head; an AI unit
cannot. This is the intra-unit attention organ.

## §1 It is not a new invention — it is the Carnegie School, applied inside the unit

This gap was missed for a revealing reason: every prior discovery lens looked at the org from
*outside* the department — inter-department coordination, org-wide priority — never at the
department's *internal* granularity. But the organizational theory here is old and central, and
the repo already cites its founders (Simon) without having drawn the organ out of them. The
anchor is **attention allocation under bounded rationality** (docs/sources.md):

- **Attention is the scarce resource** (Simon, *Administrative Behavior*, 1947): because cognition
  is bounded, a unit cannot attend to everything and must **select**; it **satisfices** rather than
  optimizes. This is *why* internal triage exists at all.
- **Sequential attention to goals** (March & Simon, *Organizations*, 1958): a unit resolves
  competing goals by attending to them **one at a time, in order**, not by jointly optimizing. The
  selected set is a *prefix* of a ranking, not a solved allocation problem.
- **Problemistic search** (Cyert & March, *A Behavioral Theory of the Firm*, 1963): effort is
  **triggered by a problem** — a unit works on what is *failing against its aspiration level*, near
  the problem, rather than on whatever is merely salient. This is the guard against the garbage-can
  pathology (Cohen–March–Olsen 1972: work drifts to whatever is temporally salient).
- **Situated attention** (Ocasio, "Towards an Attention-Based View of the Firm," *SMJ*, 1997): what
  a decision-locus focuses on depends on the *situation* it is in — the rules, resources, and
  channels that route issues to it. Applied here: the department's local choice must be **anchored
  to the org-wide ranking**, so a local optimum cannot silently drift from the telos.
- **WIP limit** (Theory of Constraints, Goldratt 1984; Kanban, Anderson 2010) — the
  operations-management complement: a unit **pulls** the next item only when in-flight capacity
  frees, never pushing more concurrent work than it can finish. This is *how* selection is bounded,
  mechanically.

Honest framing (docs/sources.md discipline): these theories were built at the level of the
*decision-maker* and the *firm*, not a single department's private backlog. Applying them at
intra-unit granularity is a **sound down-scaling synthesis**, not a claim any one author made
verbatim — and there is **no single named theory** called "intra-department prioritization"; it is
assembled from the attention tradition (org side) and flow control (ops side). The repo is
synthesizing, and says so.

## §2 The four decisions, made explicit (running code: `tools/attention.py`)

`attention.py select` makes a department's internal triage an auditable ledger fact. Given the
role's backlog (the `open_experiments`/`candidate_submitted` view) it applies all four mechanisms
at once:

1. **Situated attention** — each backlog item is scored by the rank and weight of the objective it
   serves in the current `priority_ranking_set`. An item whose objective is **not in the ranking**
   scores zero on alignment and is **flagged as a drift signal** (⚠ NOT IN ORG RANKING): a local
   optimum diverging from the global priority, now visible instead of silent.
2. **Problemistic search** — an item whose objective recently under-performed aspiration (a negative
   `outcome_delta`, or an observed outcome below the aspiration level) gets a search boost: the
   department is pulled toward what is *failing*, not what is *shiny*.
3. **Sequential attention** — items are taken in rank order, one line at a time; the chosen set is a
   **prefix**, and the reason each item was picked or deferred is recorded.
4. **WIP limit** — never select more concurrent work than the limit; work already in flight
   (started-not-completed) is subtracted first. Pull, don't push.

It emits `attention_allocated {role, wip_limit, in_flight, ranking_id, selected[], deferred[],
reason}` — so "**why did this department do X before Y**" is a ledger fact, traceable to the exact
org ranking that drove it, and a choice that ignored the ranking is an auditable drift signal, not
a silent local optimum.

**Fail-quiet like the rest** (docs/11 §0). A normal selection is a silent breadcrumb (exit 0). It
**escalates** (exit 10) only when the department *cannot serve the org's top objective from its
backlog at all* — a coverage gap only the registrar/CEO can close (activate work or re-scope the
department) — or when WIP is saturated by stalled work that never completes (which routes to
`reconcile.py stall`). Verified: a WIP-limited select picks the org-ranking-ordered prefix and
defers the rest; an off-ranking backlog item is flagged as drift; a backlog that can't serve the
top objective escalates.

## §3 Where this sits among the organs

This is not an eighth organ so much as the **missing interior of Organ 6 (the decision line) and
Organ 2 (division of labor)**: the decision line said what escalates to the human vs. runs
delegated, and org-wide ranking said which objectives matter — but the step *between* them, how a
delegated department turns "these objectives matter" into "this is the task I run now," was the
tacit gap. It reads the org-wide ranking (Organ 6/7) as its reference and writes its choice to the
ledger (Organ 5), so the org-wide ranking finally *reaches* the work, and the work's ordering is
finally *auditable*.

*Status: §2 is running, verified code (`tools/attention.py`). The organizational-theory anchors in
§1 are consensus ideas (Simon, March & Simon, Cyert & March, Ocasio) applied at intra-unit
granularity as an explicit synthesis — flagged as a down-scaling, not a verbatim citation, per the
docs/sources.md discipline. The scoring formula (align + rank + problemistic boost) is this repo's
concrete rendering of situated-attention-plus-problemistic-search, to be tuned against a running
system, not a theorem.*
