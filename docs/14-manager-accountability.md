# 14 — Manager accountability: what a supervising role is answerable for

The org can already *scale* a hierarchy — a role scales only within its `supervises:` closure
(docs/05 §4.1). But scaling is authority; this document is its counterpart, **accountability**:
when a manager spawns subordinates, reviews their work, integrates it, and reports it up, what is
it *answerable for*? A human org leaves this tacit ("of course the manager owns the result"); an AI
manager acts only on what is written down, so it must be **loaded as context at startup** — the
manager reads, before it acts, exactly what it will be held to.

**One category, not a rank ladder.** "Dept-head", "section-chief", "chief of staff" are not
different roles — they are the *same* supervising role at different `supervises:` scopes ("the same
authority, only the scope differs", docs/05 §4.1). So there is **one** manager accountability,
loaded by every role whose `supervises:` is non-empty; the four accountabilities below are that one
contract. A sub-supervisor minted by `add_layer` inherits it unchanged, scoped to its own closure.

## How this loads at startup (the goal)

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

## A1 — Attribution rolls up (immutable)

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

## A2 — Authority–responsibility parity (immutable)

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

## A3 — Intent-conformance review (doctrine, load-bearing)

**Because accountability is non-delegable, the manager actively verifies each subordinate's output
conforms to the intent it delegated** — before owning it upward. This is *verification* ("are we
building it right against my spec?"), and it is **categorically different** from the gate/skeptic's
independent admission (see §The honest distinction). *Anchor: Boehm 1979 (verification vs.
validation); Mintzberg 1973 (the Monitor role); Deming 1986 (push the acceptance-spec down at
delegation, don't inspect at the end); Graicunas 1937 (review bandwidth collapses with span).*

- **The record:** `conformance_reviewed { supervisor, subordinate, reviewed_ref,
  delegated_intent_ref, verdict: conforms|rework|reject, evidence_ref }` — the vertical analog of
  `admission_decided`. A manager's `report_up` (A4) for a subordinate's result is **invalid without
  a prior `conforms`** for it — reusing the ledger's `requires_prior` idiom (as `result_deployed`
  requires a skeptic `survives`) so the review is load-bearing, not a rubber stamp.
- **The visibility:** a derived view `pending_conformance_review` surfaces subordinate outputs a
  manager owns but has not reviewed — so an over-span manager's unreviewed backlog is a measurable
  fact (the rubber-stamp failure THEORY Organ 2 warns of, made visible). Bandwidth itself is already
  the span budget (O2); no new tooth needed for that.

## A4 — Honest roll-up (doctrine, load-bearing)

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

## The honest distinction — why A3 does not violate separation of duties

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

## §spec-driven — confirm the spec before building

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

## §granularity — how far to subdivide, and the budget that decides it

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
- **The specialization gate** (docs/05 §4) — spawn a specialist only when the work is recurring,
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

*Status: the four accountabilities are articulated here with their ledger events, views, and lint
teeth; A1/A2 project into the manager's Discipline preamble, A3/A4 into its doctrine, loaded at
startup (PROJECTION.md §1, the SessionStart hook). The classical parity/responsibility principles
are consensus in the management canon but are heuristics to verify (Simon 1946), so the lint checks
them as design priors, not proofs. The manager-review-is-not-SoD distinction is Boehm's
verification/validation split applied to the org; it is this repo's synthesis, to be verified
against a running system.*
