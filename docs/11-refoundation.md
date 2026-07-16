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

**The template's core thesis is vindicated by the newest empirical evidence; its
*derivation* was overbuilt and several load-bearing citations were mis-sourced.** The
thesis (THEORY.md, as re-anchored): designing an agent system that runs autonomously
reduces to **articulating, in machine-actionable form, the tacit organizational knowledge
a human company runs on** — the goal, the information flow, the division of labor, and the
decision line between what the human decides and what is delegated. The evidence backs this
directly: the "Why Do Multi-Agent LLM Systems Fail?" study (MASFT, arXiv:2503.13657) finds
multi-agent LLM failures are ~35% specification/role, ~40% inter-agent misalignment, ~25%
verification — "fundamental design flaws, not implementation gaps." **Every one of those is
a tacit organizational thing left un-articulated**: unclear roles, information that didn't
reach the right member, work no one verified. The MASFT authors themselves reach for
organizational theory (High-Reliability-Organization theory) to fix it. So the diagnosis
"put the organization into words or the output is coarse and mis-aligned" is *correct and
empirically supported*. What was wrong: the *claim to have derived seven organs top-down,
complete and ordered* (there is no such proof), and several classical citations (Burns &
Stalker, span numbers, SoD-as-universal) that were mis-remembered or over-applied. The
**instinct and the problem selection are right; the scaffolding around them was too heavy
and partly mis-sourced.**

---

## 1. The lens correction: articulation is primary; the dataflow graph is its *output form*

A reviewer argued that "once AI removes headcount cost and reorg friction, the primary lens
should be a permissioned dataflow graph, not organization." A previous version of this
document over-corrected toward that view. The correction to the correction, which is
faithful to the template's actual thesis:

- **The dataflow graph is real, but it is the *output* of articulation, not a rival to it.**
  Conway's law is the key: a system's structure mirrors the communication structure of
  whoever builds it. For agents, the communication graph you *write down* (who tells whom
  what, in what amount) simply *becomes* the dataflow graph the system runs. So "organization"
  and "dataflow graph" are **not two competing primary lenses — they are the same object seen
  twice**: the organization is the *intent* (why this member needs this information, why this
  is a separate role), the dataflow graph is the *rendered form*. You do not choose between
  them; you articulate the organization and the graph falls out. The reviewer's "graph is
  primary" mistakes the rendered artifact for the design act.
- **The design act everyone actually performs is articulation, whether or not they call it
  that.** Anthropic's production multi-agent system reports token usage explains ~80% of
  performance variance — i.e. *getting the right information in the right amount to each agent*
  dominates, which is precisely the information-flow articulation this template centers. When
  builders "design the graph," what they are doing *is* deciding who-knows-what and who-does-
  what — an organizational articulation wearing engineering clothes.
- **Access control alone is not enough — which is the point.** MASFT's ~40% inter-agent
  misalignment and ~25% verification failures are *not* fixed by a permissioned graph plus
  permissions. They are failures of **coordination under interdependence and of reliability** —
  exactly the tacit organizational content this template exists to make explicit. "The
  Organizational Behavior of Agentic AI" (arXiv:2606.30986) confirms the mechanism: agent
  collectives are sustained "not by motivation, identity, trust… but by **context
  architecture**" — i.e. by how well the organization has been put into words — and shared-state
  (well-articulated) forms *outperform* human-imitation hierarchies.

**Reframed thesis (kept, not demoted).** *The primary act is articulating the organization —
the goal, the information flow, the division of labor, the decision line — in a form an AI can
run. The permissioned dataflow graph is what that articulation renders to; it is the medium,
not the message. The parts of classical org theory that transfer are the ones about
**interdependence and coordination** (which agents have); the parts that don't are the ones
about labor cost, careers, and reorg friction (which agents don't). The MAS-institutional
tradition — MOISE+'s structural / functional / **deontic** dimensions — is the precise,
computational vocabulary for that articulation, and it already unifies "who does what" with
"who may do what," so access control is part of the articulation, not a rival to it.*

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
3. **Articulation-of-the-organization as the design act, and coordination/reliability as the real
   risk** — vindicated by MASFT; systems fail exactly where the organization was left tacit (roles,
   information flow, verification). Foreground this: the template's job is to make those explicit.
4. **The lint** — a runnable type-checker over the *articulated organization* (organization.yaml et al.)
   is genuinely useful and unique; it checks that the articulation is coherent (every maker routes to a
   distinct checker, no dormant control while exploring, no scope smuggling — i.e. the division of labor
   and decision line are consistent), which it already does.
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

> This template is **a way to articulate — in machine-actionable form — the tacit
> organizational knowledge an autonomous AI system must have to produce good work**: the goal
> (intent), who-knows-what (information flow), who-does-what-to-what-standard (division of
> labor), and the decision line between what the human at the top decides and what runs
> delegated and unattended. That articulation *renders to* a permissioned dataflow graph on an
> existing harness (the graph is the medium, not the message — Conway's law), and a **runnable
> lint** checks the articulation is coherent. Its truest claim is not the ontological "an agent
> system *is* an organization," but the operational one: **"in a world where AI runs the work
> around the clock with the human deciding only the essential things, designing the system
> reduces to putting the organization into words an AI can act on — and multi-agent systems
> fail precisely when that articulation is missing or coarse (unclear roles, information that
> didn't arrive, work no one verified)."** The classical org theory is the *source of hard-won
> vocabulary and failure modes* for doing that articulation well — used as re-parameterized
> heuristics for agents (interdependence transfers; labor cost and careers don't), best sourced
> from the MAS-institutional tradition (MOISE+'s structural/functional/deontic) with the classic
> management texts as illustration, not law.

*Status: this refoundation is itself a set of claims to test, but it is now grounded in an actual
literature read (sources in docs/sources.md, marked ✓ where verified). The honest through-line: the
template's problem selection and core thesis (articulate the organization for the AI) were right and
are empirically supported (MASFT); the earlier claim to a complete top-down *derivation* was
overbuilt, and several classical citations were mis-sourced — corrected here. The durable core is the
articulation itself, sharper and better-grounded than the original framing.*
