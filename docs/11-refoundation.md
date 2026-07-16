# 11 — Refoundation: What the Literature Actually Says, and What This Template Should Keep

> This document is a course-correction, written after actually reading the organizational,
> control, and multi-agent-systems literature deeply (not from the author model's memory —
> see the provenance note in docs/sources.md and the ✓-verified citations there). Three
> independent deep reads — of structure/contingency theory, of control/agency/cybernetics,
> and of the "is organization even the right frame" question — converged on the **same**
> correction. This file records that correction and what it means the template should
> keep, drop, and reframe. Where an earlier document contradicts this one, this one wins.

---

## 0. The one-sentence result

**The template's *instinct* is vindicated by the newest empirical evidence; its *derivation*
is not.** Multi-agent LLM systems really do fail primarily at coordination and reliability
— the "Why Do Multi-Agent LLM Systems Fail?" study (MASFT, arXiv:2503.13657) finds ~35% of
failures are specification/role, ~40% inter-agent misalignment, ~25% verification, "no
single category dominates," and calls them *fundamental design flaws, not implementation
gaps*. That is exactly the class of problem organizational theory addresses, and the MASFT
authors themselves reach for organizational theory (High-Reliability-Organization theory) to
fix it. So "structure matters, coordination failures are the real risk" is **correct**. But
the *specific* way this template derived its structure — top-down from classical human
management theory (Mintzberg configurations, Greiner growth-crises, span-of-control numbers),
treating those as a completeness-generating derivation — is the part the literature says to
reframe. The lens, the lineage, and several load-bearing citations were wrong or overstated.

---

## 1. The lens correction: dataflow + capabilities is primary; organization is a *governing* lens

The reviewer critique that "once AI removes headcount cost and reorg friction, organization
stops being the right primary lens" is **substantially correct**, and the literature is
specific about it:

- **Conway's law dissolves the org/architecture dichotomy for agents.** For humans, the org
  chart (who-talks-to-whom) and the system architecture are two objects you must fight to
  align (the inverse-Conway maneuver). For agents, you draw the communication graph directly
  and freely — so **the org chart *is* the dataflow graph.** There is no independent "organization"
  to design first; designing the graph *is* designing the org.
- **Builders and systems researchers already design from the graph.** Anthropic's production
  multi-agent system frames everything as orchestrator-worker dataflow and reports token usage
  alone explains ~80% of performance variance; the 2026 "Scheduler-Theoretic Framework for LLM
  Agent Execution" (arXiv:2604.11378) deliberately models coordination as task scheduling and
  *avoids* team/role metaphors. The primitive everyone actually builds on is **a permissioned
  computation graph**: nodes = agent/tool invocations, edges = context + control flow,
  capabilities = per-node tool/permission scope.
- **But the reviewer overshoots** by reducing the residual to "access control." MASFT's ~40%
  inter-agent-misalignment and ~25% verification failures are *not* solved by a permissioned
  dataflow graph plus access control — they are failures of **coordination under interdependence
  and of reliability**, which is precisely what organizational (and specifically HRO) theory is
  for. "The Organizational Behavior of Agentic AI" (arXiv:2606.30986) lands on the same both/and:
  agent collectives are "partial organisational analogues" sustained "not by motivation, identity,
  trust… but by **context architecture**," and finds shared-state forms *outperform* human-imitation
  hierarchies/committees.

**Reframed thesis.** *The primary lens is a permissioned dataflow graph (the substrate every
builder uses). Organization is a **governing lens over that graph** — and only its
coordination/reliability/normative content transfers, because that content is about
interdependence, which agents have, not about labor cost or careers, which they don't.*

## 2. The lineage correction: cite MAS-institutional theory, not (only) classical management theory

The template reached for 1937–1980 *human* management theory when a more precise, more
defensible, *computational* organizational theory already exists and already does what the
template needs:

- **MAS organizational models** (MOISE+, AGR/Agent-Group-Role, OperA, electronic institutions)
  treat organization as a first-class *computational* primitive with three independent
  dimensions: **structural** (roles, groups, links), **functional** (goal/mission decomposition),
  and **deontic** (permissions, obligations, norms). The deontic dimension *is* the access-control
  layer, already unified with structure — so "organization vs. access control" is a false split
  in the mature theory.
- Electronic institutions explicitly treat **"market" and "organization" as siblings** under a
  general "coordination regime" concept — exactly the generality the near-zero-coordination-cost
  regime demands (and which Coase/Williamson say governs the make-vs-buy boundary).

The classical management theorists (Mintzberg, Greiner, Burns & Stalker, Lawrence & Lorsch,
March) remain worth reading — but as a *source of hard-won coordination heuristics and failure
modes*, explicitly re-parameterized for agents, **not** as a top-down derivation whose human
numeric prescriptions and growth-sequences transfer intact.

## 3. The control correction: calibrate to risk/variety/transaction-type; do not universalize maker-checker

This is the sharpest and most consequential correction, because the template made SoD /
maker-checker its **non-negotiable core** — and *every control theory it cites contradicts a
blanket rule*:

- **COSO** (the actual internal-control framework): SoD is **one control activity inside one of
  five components**, selected via **risk assessment**, and explicitly **substitutable by
  compensating controls** (supervisory sign-off, independent review, dual authorization above a
  threshold) when full segregation isn't cost-effective. COSO is risk-*proportionate*. And SoD is
  centuries older than COSO/SOX (Roman finance, 1494 double-entry, Montgomery 1912, AICPA 1949) —
  so "SoD comes from SOX/COSO" is also a wrong lineage.
- **Agency theory** (Jensen–Meckling; Eisenhardt 1989): the core is **incentive design** and the
  **behavior-vs-outcome contract trade-off**, not "add a monitor." Monitoring is one lever that
  *raises* cost; when outcomes are measurable, **outcome-based contracting is often cheaper and
  better**. Agency cost has three parts (monitoring, bonding, residual loss) — a checker only
  touches one.
- **Goodhart** (Manheim & Garrabrant's four variants): "keep the proxy out of the reward" defends
  against **adversarial Goodhart only** (1 of 4). Regressional, extremal, and causal Goodhart occur
  with **no adversary and no proxy-reward at all** — they are statistical consequences of optimizing
  a lossy proxy. The template's anti-gaming framing under-covers three-quarters of the failure surface.
- **Ashby / Beer**: "a checker's variety must match the maker's" is a loose analogy. Requisite
  variety bounds a regulator against the **disturbance/outcome-relevant state space**, not another
  agent's repertoire. And Beer's Viable System Model says the *fix* for a high-variety maker is to
  **attenuate maker variety** and **embed recursive self-regulation** (each unit self-checks) plus a
  dedicated adaptation channel — **not** to bolt on a matching external checker tier. VSM argues
  *against* the flat maker/checker frame.
- **Williamson (TCE)**: hierarchy and its control apparatus are a cost justified only for
  high-asset-specificity, high-uncertainty transactions; for **generic, low-uncertainty** work,
  blanket hierarchical control is **over-governance** and a market/simple-contract solution is cheaper.

**All five converge on one rule:** *control should be calibrated to the risk / variety /
transaction-type of each unit of work, not applied uniformly.* The template's own two-tier threat
model (docs/01 §5) already points this way — it should be promoted from a footnote to the **governing
principle of the control layer**: full SoD/adversarial review is for the high-risk, asset-touching,
hard-to-verify work; low-risk, cheaply-verifiable, reversible work gets a **compensating control**
(a single reviewer, a forward test, an outcome contract), not the full apparatus. The founding
rehearsal (docs/10) accidentally illustrated the cost: four agents (~15× tokens) to produce a
slugify function, and the gate's admission was itself wrong — over-governance that still failed.

## 4. The specific citation corrections (structure theory)

- **Burns & Stalker do NOT license "run organic exploration + mechanistic control inside one org."**
  They studied whole-firm fit along a mechanistic↔organic *continuum* and found most mechanistic
  firms **failed** to go organic under change — for **political/status** reasons — producing three
  **pathological forms** (figure-head bottleneck, "mechanical jungle" of proliferating rules,
  committee-on-top). Their lesson is a *warning about botched hybridization*, close to the opposite
  of what the template cited them for.
- **The correct citation for "different subunits, different regimes" is Lawrence & Lorsch (1967)**
  differentiation–integration — and its real lesson is that **integration cost rises with
  differentiation**: separating an organic exploration regime from a mechanistic control regime
  **requires proportional investment in explicit integrating machinery** (integrator roles, shared
  cadences, liaison). The template separated the regimes and hand-waved integration — exactly L&L's
  named failure mode.
- **Structural ambidexterity (March 1991; Tushman & O'Reilly)** is the theory for explore/exploit
  in separated-but-integrated units — but the literature is emphatic that the tension is *managed,
  not dissolved*, that **integration is the hard costly leadership-borne part**, and that the payoff
  is **contingent** (small/young systems may do better with focus). March's core is a *resource
  tension* with a self-destructive pull toward exploitation — not a clean cheap split.
- **Mintzberg's configurations are situational fits, not a maturation ladder; and they are not
  Greiner's growth-crisis stages** — grafting Greiner's phases onto Mintzberg's types is a category
  error (two different theories, different mechanisms). Contingency theory itself is **contested**
  (equifinality: many structures achieve fit; modest fit–performance evidence) — present it as a
  heuristic under dispute, not a law.
- **Span-of-control numbers (Graicunas ~4–5, Urwick 5) are discredited universals.** CEO spans
  widened secularly (~4.4→8.2 direct reports, 1986–1998); optimal span is contingent on task
  standardization/interdependence; and "flat" is not "decentralized" (the flattening paradox often
  *re-centralizes* decisions). For forkable agents the human span *number* is doubly irrelevant —
  what transfers is the **verification-bandwidth / requisite-variety** constraint, not the number.

## 5. What the template should KEEP (the durable core)

After all corrections, a real, defensible core survives — and it is worth shipping:

1. **The maker/checker structural insight** (an independent verifier catches what a producer's own
   model cannot) — but as a **risk-calibrated control**, applied in proportion to the stakes and the
   verifiability of the work, per §3, not as a universal.
2. **The two-layer instinct** (self-organize exploration, design the control skeleton) — reframed via
   **Lawrence & Lorsch + ambidexterity** (differentiate regimes *and pay the integration cost*), not
   Burns & Stalker, and supported by the counter-paper (arXiv 2603.28990), which actually found a
   **hybrid** protocol wins — mildly *strengthening* the two-layer stance.
3. **Coordination-and-reliability as the real risk** — vindicated by MASFT; this is the template's
   truest contribution and should be foregrounded.
4. **The lint** — a runnable type-checker over the graph manifest is genuinely useful and unique; it
   should check *graph/coordination* invariants (every maker routes to a distinct checker, no dormant
   control while exploring, no scope smuggling), which it already does.
5. **Harness delegation** (docs/09) — correct and important.
6. **The failure-mode catalog** (docs/04) — the single most practically useful artifact, and now
   cross-validated against MASFT's empirical taxonomy.

## 6. What the template should DROP or DEMOTE

- **The "seven organs derived top-down from a definition, complete and ordered" claim** → demote to
  "a checklist of coordination concerns distilled from a century of institutional failure," which is
  what it actually is. No completeness result exists; the derivation is retrofitted (the definition
  was pre-loaded with the clauses needed to emit the desired organs).
- **Span-of-control numbers and Greiner-as-a-finding** → drop the numbers; keep growth-stage *thinking*
  only as a lens, explicitly re-parameterized for agents.
- **SoD/maker-checker as a universal non-negotiable** → recast as risk-calibrated (§3).
- **Burns & Stalker as the two-layer citation** → replace with Lawrence & Lorsch + ambidexterity.
- **Team of Teams cited beside peer-reviewed theory** → flag as an n=1, self-authored, elite-selected
  business book; use as illustration only.

## 7. The net reframing (what this template *is*, honestly)

> A **permissioned dataflow graph** for LLM agents (nodes, edges, context, capabilities) —
> that is the substrate — **plus a risk-calibrated coordination-and-reliability layer** whose
> design heuristics are drawn from organizational theory (best sourced from MAS-institutional
> theory + HRO, with classical management theory as re-parameterized heuristics, not law) —
> **plus a runnable lint** that checks the graph's coordination invariants — **run on existing
> harnesses**. Its truest claim is not "an agent system is an organization" (a metaphor that
> holds only in the coordination subspace) but "**agent systems fail at coordination and
> reliability, and here is a risk-calibrated, lint-checkable way to design against those
> failures on top of the dataflow graph you were already building.**"

*Status: this refoundation is itself a set of claims to test, but it is now grounded in an actual
literature read (sources in docs/sources.md, marked ✓ where verified). The honest through-line: the
template's problem selection was right, its theoretical derivation was overbuilt and mis-sourced, and
the durable core is smaller, sharper, and more defensible than the original framing claimed.*
