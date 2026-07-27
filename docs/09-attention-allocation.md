# 09 — The supervising role: allocating attention and being accountable

*Part III · Operate — see [the four-part map](README.md).*

A supervising role — any role whose `supervises:` is non-empty — does two things a human manager does
tacitly and an AI manager must do from what is written down. It **allocates attention** (decides what
its unit works on next), and it is **accountable** (answerable for the work it spawned, reviewed,
integrated, and reported up). These are the two halves of the managing role: what to attend to, and
what you answer for. A human unit's manager holds both in their head; an AI unit cannot — so its
triage must be **articulated, not left tacit**, and its accountability must be **loaded as context at
startup**, read before it acts. This document is the intra-unit managing organ, in two parts:
**Part A — attention allocation** (§1–§3), **Part B — accountability** (§4–§7).

**One category, not a rank ladder.** "Dept-head", "section-chief", "chief of staff" are not different
roles — they are the *same* supervising role at different `supervises:` scopes ("the same authority,
only the scope differs", docs/02 §8.1). So there is **one** managing contract, loaded by every role
whose `supervises:` is non-empty: it owns its unit's attention allocation (Part A) and holds the four
accountabilities (Part B). A sub-supervisor minted by `add_layer` inherits it unchanged, scoped to its
own closure. Minting a separate priority/PM role would violate this — priority ownership is an existing
duty at two altitudes (§3.1), not a new rank.

---

# Part A — Attention allocation: how a department decides what to work on next

The org-wide priority ranking (docs/05 §5.4, `resource.py rank`) says which **objectives** matter.
Nothing said how a single department, handed its own backlog, decides **what to work on next**.
That decision was left implicit — the department's LLM just picked, unrecorded and unaudited, and
with no connection to the org-wide ranking. That is precisely the failure this whole repo exists
to remove: **an AI department can only act on what is written down, so its internal triage must be
articulated, not left tacit.**

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

### §2.1 Backlog items are typed by SDLC phase

A backlog item is never phase-less: under the forced SDLC mold (docs/11) every work item **sits at
some phase** of the mold — a requirement to settle, a design to draw, an implementation to build, a
test to admit, a deploy to fire, an operate-phase fix. Situated attention (mechanism 1) therefore
scores not only *which objective* an item serves but *which phase it is at*, because the two are
different questions: an objective can be the org's #1 while its next actionable item is stuck one
phase back. Typing the item by phase is what lets the amplifier correction (docs/04, docs/12 §3)
actually bite at triage — when the moving bottleneck is downstream, the department pulls the
`test`/`deploy`-phase items that clear the constraint ahead of yet another `implement`-phase item
that only deepens the pile. The phase is recorded on selection, so "we kept generating while the
test queue starved" becomes a visible, auditable pattern rather than a silent local optimum.

### §2.2 Problemistic search reads reliability and DORA, not only outcome_delta

Mechanism 2 (problemistic search) is triggered by an item *failing against its aspiration level* —
and an IT company's aspiration levels are **broader than a single `outcome_delta`**. A department
is also failing when it is **burning its reliability/error budget** (docs/05 §reliability-budget) or
when a **DORA key has regressed** (docs/05 §DORA) — lead time climbing, change-fail rate rising,
deploys frozen. These are first-class aspiration levels the search boost reads alongside
`outcome_delta`: an item that would restore a spent error budget, or relieve the stage a shifted
DORA key has named as the bottleneck, is pulled toward *because the org is failing there*, exactly
as a negative `outcome_delta` pulls. This keeps problemistic search honest under the company scope —
the department is drawn to what is *failing on any of its watched aspirations* (outcome, reliability,
delivery health), not only to a bad outcome after the fact and never to what is merely shiny.

### §2.3 The business-upstream is where backlog items enter

The four mechanisms decide *what to pull next*; they presume items are already in the queue. Under
the company scope, **where items enter** has a definite home: the **business-upstream** — the
customer, the RFP, the human's declared priority — is Organ 1's telos (THEORY.md §1b), and it is the
front door through which work becomes a backlog item at all (the triage path, docs/05's org-wide
backlog). Attention allocation is strictly *downstream* of that entry: it never invents work, it
sequences work that the business-upstream admitted. Naming this boundary keeps the two roles
distinct — Organ 1 decides *what is worth building as a business* and enqueues it; this organ decides
*what the department runs next* from what was enqueued. A department that finds its backlog cannot
serve the top objective does not fabricate an item; it escalates the coverage gap (below) so the
business-upstream can enqueue the missing work.

**Fail-quiet like the rest** (docs/05 §5.0). A normal selection is a silent breadcrumb (exit 0). It
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

### §3.1 The two-level backlog (why there is no separate "backlog store")

Stated as a pair, the priority story is **two levels, one ledger**: the **org-wide backlog** is the
ranked objective list (docs/05 §5.4, `resource.py rank`, re-emitted only when the order changes); the
**per-department backlog** is each unit's own queue of pulled work, and *what it runs next from that
queue* is exactly the §2 decision. These are not two stores — both are **projections of the one
ledger** (the objective ranking, and the department's `open_experiments`/`candidate_submitted`
view), so "single custody" (docs/05) is never fragmented into private per-department queues. A
department **owns the sequencing** of its own backlog (autonomy) but **ranks against the shared
objective order** (so a local optimum cannot drift from the telos, §2's align+rank score). Priority
ownership is therefore not a new "PM" rank — it is an existing duty at two altitudes: the
**registrar** recomputes the org-wide ranking (docs/05 §2.6), and the **department's supervising
manager** owns intra-unit triage (Part A here, answerable per §6/§7 below).

When the org-wide ranking **changes**, the propagation is already covered, not a new mechanism: the
revised priority is broadcast as an intent-block revision (docs/07 §2.1), and **STALE-REFERENCE**
(docs/05 §5.1.3) re-checks the departments still bound to the *old* order and nudges them to
re-derive — so a central re-prioritization reaches every department's next-task choice without a
meeting, and without any department silently working yesterday's #1.

A backlog item in one department that waits on another department's output is a
cross-department dependency, and it too has an existing home, not a new one:
**DEPENDENCY-STALL** (docs/05 §5.2) is exactly the blocked-on edge plus aging alarm — a
freshness window on the `depends_on` edge turns a silently-blocked item into an explicit
`dependency.stall.raised`, routed to the lowest common owner, so a cross-department block
surfaces as data instead of a silent deadlock no meeting is there to catch.

---

# Part B — Accountability: what a supervising role is answerable for

The org can already *scale* a hierarchy — a role scales only within its `supervises:` closure
(docs/02 §8.1). Scaling is authority; accountability is its counterpart: when a manager spawns
subordinates, reviews their work, integrates it, and reports it up, what is it *answerable for*? A
human org leaves this tacit ("of course the manager owns the result"); an AI manager acts only on
what is written down, so it must be **loaded as context at startup** — the manager reads, before it
acts, exactly what it will be held to. The four accountabilities below are that one contract (the
same one-category rule as the intro: loaded by every role whose `supervises:` is non-empty, inherited
unchanged by any sub-supervisor `add_layer` mints).

## §4 How the four accountabilities load at startup (the goal)

The four accountabilities split by mutability, and land in the two startup-context slots
(PROJECTION.md §1) accordingly:

- **A1, A2 are immutable — they go in the manager's Discipline preamble** (ROLE.md's
  charter-protected block, item 5 of the projected instruction file). "Responsibility is absolute"
  and "authority must match responsibility" are not coaching-tunable; a supervisor may not edit them
  out of a subordinate manager overnight (the same guard that stops honesty being coached away).
- **A3, A4 are operational norms — they go in the manager's doctrine** (item 3), injected every
  cycle by the SessionStart hook, and are backed by ledger events + a lint tooth so they are
  load-bearing, not advisory.

So a manager agent starts each cycle already holding: *you own your subordinates' output as your
own (A1); you were given the authority to make that fair (A2); verify their work conforms to the
intent you delegated before you own it up (A3); and report it up completely, without distortion,
by exception (A4).*

## §5 A1 — Attribution rolls up (immutable)

**The manager owns its subordinates' output as its own result.** Delegating work down does not
transfer answerability up: a subordinate's failure is the manager's failure to scope, spawn, or
review adequately — never disclaimed. There is exactly **one** accountable owner per deliverable
(distinct from the possibly-many who did the work). *Anchor: Urwick 1943 (responsibility is
absolute); Koontz & O'Donnell 1955 (absoluteness of responsibility); the RACI single-Accountable
rule.*

- **Already in the repo:** `candidate_submitted.maker` attributes finished work horizontally;
  `move_executed.initiated_by_supervisor` traces scale acts. What was missing was the *vertical*
  edge: which manager is answerable for a result up the chain.
- **The tooth (`O2d — attribution closure`):** every active non-supervisor role is in **exactly
  one** supervisor's `supervises:` list — no orphan whose result nobody owns, no two managers
  claiming the same subordinate. This is the single-Accountable invariant over the existing
  `supervises:` graph.
- **The record:** `cycle_completed` carries `accountable_supervisor`, set from the runtime
  supervision edge (never the payload — a manager cannot forge who owns a result, mirroring the
  ledger's `actor_identity_source: runtime_session`).

## §5a A2 — Authority–responsibility parity (immutable)

**No manager is accountable for what it could not control.** A manager may be held to a result only
if it held the authority to achieve it — to spawn/scale subordinates, direct their work, and reject
their output before integrating. Accountability without matching authority is a *mis-designed job*,
catchable at founding time, not a failure to punish later. *Anchor: Fayol 1916; Urwick 1943
(correspondence); Koontz & O'Donnell 1955 (parity). Honesty: Simon 1946 — these are proverbs to
verify, not laws; Simons 2013 — a bounded gap is a deliberate lever, an unbounded one is a defect.*

- **Already in the repo:** O2c bounds scale authority to the `supervises:` closure; O2 bounds review
  bandwidth (span); scopes bound what a role may read. The repo already models *authority*.
- **The tooth (`O2e — parity gate`):** a role held to a `contract.deliverable` must hold the
  authority to produce it — its named `checker` is reachable, and any subordinate whose output it
  must integrate is in its `supervises:` closure. A contract-bearing role accountable for a result
  wholly determined by a seam it neither owns nor is granted fails the gate: that is accountability
  without authority. (The bounded-gap allowance stays a deliberate design toggle, not a default.)

## §6 A3 — Intent-conformance review (doctrine, load-bearing)

**Because accountability is non-delegable, the manager actively verifies each subordinate's output
conforms to the intent it delegated** — before owning it upward. This is *verification* ("are we
building it right against my spec?"), and it is **categorically different** from the gate/skeptic's
independent admission (see §6b). *Anchor: Boehm 1979 (verification vs. validation); Mintzberg 1973
(the Monitor role); Deming 1986 (push the acceptance-spec down at delegation, don't inspect at the
end); Graicunas 1937 (review bandwidth collapses with span).*

- **The record:** `conformance_reviewed { supervisor, subordinate, reviewed_ref,
  delegated_intent_ref, verdict: conforms|rework|reject, evidence_ref }` — the vertical analog of
  `admission_decided`. A manager's `report_up` (A4) for a subordinate's result is **invalid without
  a prior `conforms`** for it — reusing the ledger's `requires_prior` idiom (as `result_deployed`
  requires a skeptic `survives`) so the review is load-bearing, not a rubber stamp. This
  conformance-before-roll-up is itself **one instance of the SDLC phase gate** (docs/11): the
  design→implement conformance is the same `requires_prior` predicate applied at a phase boundary
  rather than a reporting boundary — the manager verifying "built right against my spec" is the
  design phase admitting the implement phase.
- **The visibility:** a derived view `pending_conformance_review` surfaces subordinate outputs a
  manager owns but has not reviewed — so an over-span manager's unreviewed backlog is a measurable
  fact (the rubber-stamp failure THEORY Organ 2 warns of, made visible). Bandwidth itself is already
  the span budget (O2); no new tooth needed for that.

### §6a spec-driven — confirm the spec before building

A3 is intent-conformance review. Run *early*, before the work exists, it is **spec-driven
delegation**: the manager writes the per-task intent as an explicit **spec** and pushes it *down*
at delegation, and the supervising manager **confirms the spec conforms to the intent it holds
before implementation proceeds** — the acceptance criterion is set at hand-off, not inspected at
the end of the line (Deming). The spec is the artifact `conformance_reviewed.delegated_intent_ref`
points at; `spec_delegated` is its producer (`confirmed: bool` is the down-front A3, the same
positive-claim discipline as `exceptions_none_asserted`).

This does not duplicate the admission standard or the contract: those sit on the *admission* axis
(the bar a **finished result is judged against**, upward, independent). A spec is the opposite
direction — intent pushed **down at delegation, before work starts**. It earns its own event only
when the per-task intent is richer than the standing contract; a spec that merely restates
`contract.deliverable` should stay in the context pack. The confirm-before-build is the supervising
manager's own vertical A3, run earlier in time — not the independent gate/skeptic, which still
admits the finished result exactly as before.

### §6b The honest distinction — why A3 does not violate separation of duties

The repo already has the gate/skeptic **independent admission** with separate lineage (O6c). Adding
the manager's conformance review does **not** collapse SoD, because the two are different controls
against different threats:

| | **Manager review (A3, new)** | **Gate / skeptic admission (existing)** |
|---|---|---|
| Question | "Does this conform to the intent *I delegated*?" (Boehm **verification**) | "Should this enter trusted state against the *purpose*?" (**validation** + adversarial refutation) |
| Independence | **Not** independent — the manager authored the intent and is accountable for the result | Independent by construction — separate lineage, may not share it with makers (O6c) |
| Threat | The manager owning *unverified* work up the chain (honest conformance loss) | Self-dealing, gaming, a maker stamping its own high-stakes work valid (fraud) |
| Axis | **Vertical** — down the supervision edge (Organ 6, the decision line) | **Cross-cutting** — the purpose-grounded gate, separate from all supervision |

> **The manager's conformance review is additive, never substitutive.** A subordinate result still
> passes the gate and the skeptic exactly as before; the manager's `conforms` verdict is a
> *precondition for reporting it up as its own*, not an admission ticket. Because the manager is
> *not* independent (it authored the intent, it is accountable — A1+A2), the architecture, not the
> manager's good intentions, contains its self-interest: the unchanged independent gate/skeptic, and
> the new `report_fidelity` audit. The existing SoD skeleton is untouched — A3 adds a vertical
> verification lane; "enters trusted state" remains the gate's sole authority.

## §7 A4 — Honest roll-up (doctrine, load-bearing)

**A manager compressing subordinate work upward is answerable for three testable properties:**
**completeness** (no load-bearing detail silently dropped), **non-distortion** (emphasis matches the
evidence), and **escalation** (every exception above threshold surfaces). *Anchor: March & Simon
1958 (uncertainty absorption — the inference travels up, the basis is lost); Rosen & Tesser 1970
(the MUM effect — reluctance to pass bad news up); Read 1962 / O'Reilly 1978 (upward distortion is
intentional, tracks incentives). Constructive: mission command / report-by-exception (already
cited).*

- **The record:** `report_up { supervisor, parent, window, basis_refs: [ref], intent_status:
  met|at_risk|missed, exceptions: [ref], exceptions_none_asserted: bool, decisions_needed: [ref] }`.
  Three design points, each grounded:
  - `basis_refs` makes uncertainty absorption **reversible** — the inference goes up in the
    manager's own words, the evidence is one dereference away (March & Simon).
  - `exceptions_none_asserted` defeats the MUM effect **structurally**: silence becomes a positive
    claim ("I assert there are none"), never a quiet omission.
  - the roll-up is authored *in the manager's own words* (not a raw pass-through) but stays
    auditable against `basis_refs`.
- **The audit (`tools/*.py`, the OUTCOME-DELTA idiom) — `report_fidelity`:** a pure function that
  spot-checks a `report_up` against its `basis_refs` — did every subordinate rejection /
  non-conformance / escalation in the window appear in the manager's `exceptions`? A surfaced-vs-
  detected mismatch escalates (a manager gatekeeping bad news — the Read/O'Reilly distortion,
  caught). Fail-quiet / exit-10, like the other organs.

## §8 granularity — how far to subdivide, and the budget that decides it

When a manager may spawn a subordinate to help (write a spec facet, review from a needed expert
angle, take a parallel sub-task), the question is **how fine to cut**. The control is not a
depth/width knob — it is a **token budget carved down at delegation**. A manager passes each
subordinate a `spec_delegated.token_budget` from its own share; the sum of a manager's outgoing
budgets may not exceed its own. Since one subagent costs on the order of tens of thousands of
tokens to stand up (its own context, mostly cached), the budget — not a headcount — sets how deep
and wide the sub-tree grows: a subordinate spawns within its budget, and when the budget is spent
it cannot subdivide further. This is the machine form of "you delegate within your budget," and it
aligns with A1/A2: a manager is accountable for its subordinates' spend (A1) and holds the budget
authority to bound it (A2).

Three limits compose to set the natural ceiling, so no arbitrary cap is needed:
- **The host's hard limit** — nesting is bounded by the harness (on the harness this was verified
  against, a subagent five levels below the top holds no spawn tool and is a leaf). Depth is
  capped by construction, not by this repo.
- **The specialization gate** (docs/02 §8) — spawn a specialist only when the work is recurring,
  or would dilute a generalist's context, or needs independent lineage; the degree of subdivision
  is bounded by coordination cost (Becker & Murphy), not by how finely one *could* cut.
- **The budget** — the token allowance runs out.

**And the load-bearing judgment about *when* subdivision pays at all:** subdividing into a
sub-tree of agents costs multiples of a single agent doing the work — each agent re-reads its own
context, and a multi-turn loop's cost grows with the *square* of its turns (the whole history is
re-sent each turn). That extra spend buys real value only for work that is **genuinely parallel,
breadth-first, exceeds one context window, or spans many independent tools**. For **dependency-heavy
work that needs one shared context — most implementation and coding — a single agent given the same
budget usually does as well or better**, and subdivision spends the multiple for little gain. So a
manager's default is: subdivide for parallel/breadth-first work; keep tightly-coupled work single-
threaded. This is why `spec_delegated` carries a budget and not a mandate to fan out — the manager
decides per task whether fanning out is worth its own multiplier, and is accountable (A1) for that call.

---

*Status. **Part A** — §2 is running, verified code (`tools/attention.py`). The organizational-theory
anchors in §1 are consensus ideas (Simon, March & Simon, Cyert & March, Ocasio) applied at intra-unit
granularity as an explicit synthesis — flagged as a down-scaling, not a verbatim citation, per the
docs/sources.md discipline. The scoring formula (align + rank + problemistic boost) is this repo's
concrete rendering of situated-attention-plus-problemistic-search, to be tuned against a running
system, not a theorem. The company-scope extensions (§2.1 phase-typing, §2.2 reliability/DORA
aspiration levels, §2.3 the business-upstream entry point) fold the SDLC mold (docs/11) and the
operate-phase instruments (docs/05 §reliability-budget, §DORA) into the same four mechanisms — an
extension of the existing organ, not a fifth mechanism. **Part B** — the four accountabilities are
articulated with their ledger events, views, and lint teeth; A1/A2 project into the manager's
Discipline preamble, A3/A4 into its doctrine, loaded at startup (PROJECTION.md §1, the SessionStart
hook). The classical parity/responsibility principles are consensus in the management canon but are
heuristics to verify (Simon 1946), so the lint checks them as design priors, not proofs. The
manager-review-is-not-SoD distinction is Boehm's verification/validation split applied to the org; it
is this repo's synthesis, to be verified against a running system.*
