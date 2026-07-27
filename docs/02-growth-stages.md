# 02 — Scaling: Grow Staged, Activate Elastic

*Part II · Design — see [the four-part map](README.md).*

*How an agent organization scales the way a company scales — as a **staged
maturation** (which organ or layer to add at each stage) and as a **design-full /
activate-elastic** structure (the whole chart designed on day one, run only where load
demands). These are two views of one topic: how the org grows and shrinks over time.*

This document maps a small set of well-established organizational findings onto the
problem of growing an agent org (a system of collaborating AI agents). The goal is
practical: help you diagnose **what stage you are in**, choose **the next single
move**, and run that structure elastically — rather than adding structure by reflex.

Nothing here is presented as a proven law of agent systems. These are human-organization
models used as *lenses*. Treat the mapping as a hypothesis to check against your own
system, not a template to obey.

Two framings run through the whole document and must be read together:

- **Staged maturation (§§1–2b, 3–4).** Growth is a sequence of stages, each ending in a
  predictable crisis; you add the right organ before the crisis hits. Two axes advance
  together: the org's coordination shape, and the system's SDLC/delivery maturity.
- **Design-full / activate-elastic (§§5–8).** Because design is near-free for an agent
  org and only *activity* costs, you design the complete ideal org on day one and
  activate departments elastically, driven by load and by phase-admission. Under this
  model the stages of §2 become **activation levels**, not a one-way ladder — and some
  things must **never** be elastic.

The central claim that ties them: an agent org removes the *money* constraint that forces
human companies to start small, but not the *coordination* and *incentive* constraints —
so the right rule is not "run the ideal org from day one" but **design the ideal org
completely on day one; activate it elastically**, advancing the delivery capability at
least as fast as the org that runs it.

---

## 1. Why growth stages

Companies do not scale smoothly. Greiner's model describes growth as a sequence of
**five phases, each ending in a distinctive crisis** that must be resolved before the
next phase of growth is possible. Each phase is dominated by a management style that
works — until it stops working and creates the very problem that triggers the next
transition. (Greiner curve: see Sources.)

The relevant idea for an agent org is not the exact five stages but the *shape*:

- Growth is **staged**, not continuous.
- Each stage's strengths eventually become its bottleneck.
- The transition points are **predictable crises**, not random failures.

If that shape holds for agent orgs too — and the failure modes below suggest it often
does — then **ad-hoc expansion walks straight into a known crisis**. Adding more agents
without addressing the crisis of your current stage tends to amplify the problem, not
solve it. The value of a stage model is that it tells you *which* crisis you are
approaching, so you can add the right organ before it hits.

A caution: real orgs skip stages, sit between them, or run different sub-teams at
different stages. Use the model to locate yourself approximately, not to force a
sequence.

Crucially, under the elastic model of §5 these stages are **not a one-way maturation
ladder**: transitions run in *both* directions — de-scaling is a first-class move — and
structural moves execute only through the moves catalog (template/moves.yaml), gated by
the audit lint. This section is the diagnostic lens; §5 is the operating rule.

---

## 2. The stages, mapped to an agent org

Below, each Greiner phase is mapped to a corresponding shape of agent organization.
For each stage: **(a)** what is happening, **(b)** the crisis that ends it, and
**(c)** the organ or layer to add next.

Alongside Greiner, it helps to name the *coordination mechanism* in play, using
Mintzberg's vocabulary of how work gets coordinated (see Sources):

- **Direct supervision** — one supervisor issues instructions (simple structure).
- **Standardization of work** — processes are specified in advance (machine bureaucracy).
- **Standardization of skills** — agents are trusted because their capability is known
  (professional bureaucracy).
- **Standardization of outputs** — units are judged on results, not method
  (divisionalized form).
- **Mutual adjustment** — coordination by ongoing informal communication (adhocracy).

Note that Mintzberg's configurations are contingent types — shapes fitted to different
circumstances — not maturation stages; pairing them with Greiner's sequence below is
this repo's mapping, not Mintzberg's claim.

### Stage 0 — The single agent

**(a) What happens.** One agent does the whole task end to end. There is no
coordination problem because there is nothing to coordinate. This is the agent-org
equivalent of a founder doing everything.

**(b) The crisis.** The task grows beyond what one context window / one agent can hold
with quality. Work is dropped, context is lost, or the agent thrashes between subtasks.

**(c) Add next.** A **supervisor + a few worker agents** — i.e., move to a simple
structure coordinated by direct supervision. One orchestrator decomposes the task and
delegates to a small number of specialists.

### Stage 1 — Creativity → single supervisor with a few departments (simple structure)

**(a) What happens.** An orchestrator agent directs a handful of specialist agents
directly. Coordination is **direct supervision**: the orchestrator holds the plan,
assigns work, and integrates results. The mapping to Greiner's *creativity* phase is
loose, and worth being honest about: Greiner defines creativity by the *absence* of
professional management — which is exactly what produces the leadership crisis — so only
the informal, hands-on directing here corresponds to creativity. A formalized
orchestrator that explicitly holds the plan is already the transition toward the
*direction* phase's resolution.

**(b) The crisis (leadership / span).** As the number of specialists grows, the single
orchestrator becomes the bottleneck. It cannot attend to every agent's output with
enough care; integration quality drops. In Greiner terms this is the **leadership
crisis** that ends the creativity phase. In practical terms it is a **span-of-control**
problem (Section 3).

**(c) Add next.** More explicit **direction**: a clearer top-level plan, standardized
task formats, and — only if span is genuinely exceeded — a first coordinating layer.

### Stage 2 — Direction → adding a management layer (standardization of work)

**(a) What happens.** The org introduces structure: defined roles, standardized task
and hand-off formats, an explicit top-down plan. Coordination shifts toward
**standardization of work** (machine-bureaucracy flavor). A supervising agent (or a
small set of them) now runs sub-groups on behalf of the top orchestrator. This is
Greiner's *direction* phase.

**(b) The crisis (autonomy).** The rigid top-down flow becomes a bottleneck of its own.
Lower-level agents that are close to their subtask are forced to wait for or defer to
the center, even when they have better local information. Greiner calls this the
**autonomy crisis** — the people (here, agents) doing the work need more freedom than the
directive structure allows.

**(c) Add next.** **Delegation**: push decision authority down to sub-supervisors and
give sub-teams real autonomy over their scope, with the center stepping back from method.

### Stage 3 — Delegation → decentralized sub-teams (standardization of outputs)

**(a) What happens.** Sub-supervisors own their domains. The center stops dictating
*how* and starts specifying *what* — coordination by **standardization of outputs**
(a divisionalized shape). Each sub-team is trusted to reach its target however it sees
fit. This is Greiner's *delegation* phase, and it restores speed and local
responsiveness.

**(b) The crisis (control).** Autonomous sub-teams drift. They duplicate work, diverge
on conventions, optimize locally against each other, and the center loses visibility
into what is actually happening. Greiner calls this the **control crisis** — the top
can no longer see or steer the decentralized units.

**(c) Add next.** **Coordination mechanisms**: shared review gates, common conventions,
cross-team context delivery, and reporting that gives the center visibility without
re-centralizing every decision.

### Stage 4 — Coordination → formal integrating mechanisms

**(a) What happens.** The org adds formal systems that tie the autonomous units back
together: shared standards, review/approval gates, common context packs, portfolio-level
oversight. This is Greiner's *coordination* phase. It buys back control without killing
the autonomy won in Stage 3.

**(b) The crisis (red tape).** The coordinating machinery itself becomes heavy. Agents
spend more effort satisfying gates, reporting, and conventions than doing the work.
Greiner calls this the **red-tape crisis** — procedure crowds out substance.

**(c) Add next.** **Collaboration**: lighter, trust-based, cross-cutting coordination —
replace some formal gates with mutual adjustment among agents that already share context.

### Stage 5 — Collaboration → mutual adjustment (adhocracy)

**(a) What happens.** Coordination shifts from procedure to **mutual adjustment**:
teams of agents self-organize around problems, communicate directly across boundaries,
and rely on shared context rather than formal hand-offs. This is Greiner's
*collaboration* phase and Mintzberg's adhocracy.

**(b) The crisis.** Greiner's original model left the crisis of this phase open; a
commonly cited candidate is **internal growth exhaustion** — the limits of what the
organization can do alone. For an agent org, plausible analogues are coordination
overhead among many peers, or the ceiling of the current context-sharing substrate.
Treat this as an open question for your own system rather than a settled answer.

**(c) Add next.** Depends on the observed crisis — often *external* leverage (new tools,
new data sources, partner systems) rather than another internal layer.

---

## 2b. The second axis: system-and-SDLC maturity, co-advancing with the org

The stages above scale **one thing — the org's coordination shape**. But an IT business
company (THEORY §1b) is not only an org; it is an org *building and running a system*, and
the system has its own maturity ladder. Scaling the chart while the delivery capability
stands still produces a large, well-coordinated org that cannot ship reliably — an
amplifier without a mold (docs/11 §0). So the growth-stage model has a **second axis**, run
alongside the first:

| Product/SDLC stage | What is in place | The crisis that ends it | Add next |
|---|---|---|---|
| **P0 — Walking skeleton** | one thin end-to-end slice traverses the full phase chain (requirements → … → operate) once, by hand | every change is a manual, unrepeatable event; integration is ad hoc and breaks | **Continuous integration** — merge to a shared trunk continuously; automate the build |
| **P1 — Continuous integration** | changes integrate into an always-buildable trunk; the test phase runs on every merge | integration is green but *release* is a manual, risky, batched event | **Continuous delivery** — automate deploy through the CI/CD spine (GitHub Actions; docs/11 §3) |
| **P2 — Continuous delivery** | any admitted change can ship on demand; deploy is a pipeline, not a ceremony | shipping fast now *degrades stability* — the amplifier's downstream cost (docs/11 §0) surfaces as incidents | **Error budget** — bound deploy velocity by a reliability budget (docs/05) |
| **P3 — Operated under error budget** | deploy velocity is governed by a reliability/error budget; incidents feed back to requirements (operate → requirements loop) | the org optimizes locally and can't see *which* delivery capability is the binding constraint | **DORA navigation** — measure deploy frequency / lead time / change-fail / MTTR; steer to the moving bottleneck |
| **P4 — DORA-optimized** | the four DORA signals navigate the org to its moving bottleneck (Theory of Constraints), reshaping toward it | the *next* constraint moves elsewhere (often into the org shape itself) | read the constraint — it may be an org-axis move (§2) or an external one (§2 Stage 5) |

**The two axes advance together, not independently.** This is THEORY §1b's Organ 7 — *"the
system and the organization grow together."* Concretely they gate each other:

- A product stage's **departments activate only when the prior product phase's output is
  admitted** — you don't stand up a deploy department before something is admitted to
  deploy (§7 below, elastic activation tied to phase progress).
- The org-axis crises and product-axis crises are usually *the same event seen from two
  sides*. The **control crisis** (Stage 3: autonomous sub-teams diverge on conventions) is
  the same moment CI stops being enough and you need a shared trunk with automated gates
  (P0→P1). The **red-tape crisis** (Stage 4) is the same pressure that pushes manual
  release ceremonies into an automated pipeline (P1→P2). Diagnosing one axis without the
  other misreads the crisis.
- Neither axis is a one-way ratchet. Under the elastic model (§5), a product-side
  department de-activates when its phase load passes, just as an org layer dissolves — but
  the *maturity* the system reached (an automated pipeline, a live error budget) is a
  durable asset, not something that decays when a department goes dormant.

**One-line rule:** *advance the delivery capability at least as fast as the org that runs
it — a bigger chart that ships worse is the amplifier failing.*

---

## 3. The span-of-control gate

The recurring decision across stages is: **when do I add a management layer?** The
span-of-control literature gives a concrete gate.

**Span of control** is the number of subordinates a single supervisor can *effectively*
manage. Classic guidance (Urwick) put this low — around **5–6** for interdependent work —
while high-skill, high-communication environments can support much wider spans, on the
order of **15–20**. When one supervisor's span is exceeded, the standard fix is to
insert a **sub-supervisor** (a middle layer) so no one supervises more than they can
handle. (See Sources.)

The trade-off cuts both ways:

- **Span too wide** → the supervisor cannot attend to each subordinate; quality and
  oversight degrade (the Stage 1 leadership crisis).
- **Span too narrow** → a **tall** structure with many thin layers; every message and
  decision traverses more hops, adding latency and cost, and diluting accountability.

For an agent org, the two costs are concrete: a wide span means an orchestrator's
context and attention are spread too thin across sub-agents; a tall structure means more
orchestrator-to-orchestrator hops, each one a place to lose context and spend tokens.

**The key move — widen the span before you deepen the hierarchy.**

What sets the *effective* span is communication and shared understanding. The higher end
of the range (15–20) is reachable specifically when communication is good and the work
is well-understood. In an agent org, the lever for this is **context delivery** — the
shared consciousness that lets each sub-agent act correctly without a round-trip to the
supervisor. Investing in context packs, shared conventions, and good task specifications
**raises the effective span**, which keeps the hierarchy shallow and **delays the need
for a middle layer**.

So the gate is:

> **Add a middle layer only when the number of units under one supervisor exceeds its
> effective span *after* you have already invested in context delivery.** Hierarchy is
> the last resort, not the first.

Concretely, before inserting a layer, ask:

1. Is the supervisor actually saturated, or is it under-served by poor context delivery?
2. Would better task specs / shared context let one supervisor handle the current span?
3. If you must split, split by **domain boundary** (cohesive sub-teams), not arbitrarily.

Only when the honest answer is "context is already good and the span is still exceeded"
should you add the layer — and then add exactly **one** layer, at the point where units
cluster naturally.

---

## 4. A concrete checklist — which stage am I in, and what next?

Find the row whose **signs** best match your system. The **next move** is the organ or
layer to add — usually one move, not several.

| Stage | Coordination | Signs you are here | Next move |
|---|---|---|---|
| **0 — Single agent** | none | One agent does everything; tasks now exceed one context window; work gets dropped | Add a **supervisor + a few workers** (simple structure) |
| **1 — Creativity** | direct supervision | One orchestrator directs a few specialists; integration quality drops as you add agents | Firm up **direction**: standard task formats, explicit plan; widen span via context |
| **2 — Direction** | standardize work | Defined roles and top-down flow; lower agents wait on the center despite better local info | **Delegate**: push authority to sub-supervisors; give sub-teams real autonomy |
| **3 — Delegation** | standardize outputs | Autonomous sub-teams move fast but duplicate work, diverge on conventions, drift out of sight | Add **coordination**: shared gates, common context, center-level visibility |
| **4 — Coordination** | standard gates | Formal reviews and reporting in place, but agents spend more effort on procedure than work | Shift to **collaboration**: lighter, trust-based, cross-cutting coordination |
| **5 — Collaboration** | mutual adjustment | Agents self-organize on shared context with direct cross-team communication | Watch for the next crisis; look **outward** (new tools/data/partners) |

**Diagnostic signals that you are at a transition (crisis), regardless of stage:**

- The orchestrator is the bottleneck and its output quality is dropping → **leadership /
  span crisis** (end of Stage 1). Fix span first (Section 3).
- Capable sub-agents are blocked waiting on the center → **autonomy crisis** (end of
  Stage 2). Delegate.
- Sub-teams duplicate or contradict each other and the center is blind → **control
  crisis** (end of Stage 3). Coordinate.
- More effort goes to gates and reporting than to the task → **red-tape crisis** (end of
  Stage 4). Lighten and move toward collaboration.

**Before any structural change, run the span-of-control gate (Section 3):** try widening
the span through better context delivery before deepening the hierarchy. Add at most one
layer, at a natural domain boundary.

**One-line rule of thumb:** *Match the coordination mechanism to the stage; invest in
context to widen span; add a layer only when a real span limit forces it.*

Note that under the elastic model (§5) these stages are read as **activation levels**, and
the crisis signals above are the **sensor triggers** for moving between them — in either
direction. The rest of this document is that operating rule.

---

## 5. The elastic organization: design fully, run elastically

> The intuition this half of the document examines: *"Human companies must start small and
> person-dependent because of financial constraints. AI has no such constraint, so an
> agent org should simply instantiate the ideal department structure and scale it up
> and down freely."*
>
> The verdict from organizational theory: **half right, and the half that is right is
> transformative.** The financial constraints on org growth really do vanish for agent
> orgs. But the *non-financial* constraints — the coordination and incentive limits that
> span of control, Conway's law, and Greiner's crisis model (§§1–4) describe — remain
> fully in force, because they were never about money. The correct design is therefore not
> "run the ideal org from day one" but: **design the ideal org completely on day one;
> activate it elastically.**

### 5.1 Why human orgs start small: three constraint families, not one

Unbundle the reasons a human company begins as a few overloaded generalists:

**Family A — financial / frictional constraints (these are about money)**

| Constraint | Human-org driver |
|---|---|
| **Fixed labor cost** | A member costs salary whether or not there is work for them this hour. Headcount is a standing cost, so early orgs minimize it. |
| **Hiring/firing friction** | Recruiting takes months; onboarding takes more; separation has legal, financial, and morale costs. Structure changes are expensive, so they are deferred. |
| **Person-dependence (属人化)** | Externalizing knowledge (documentation, process) costs time the early org cannot spare, so knowledge stays in founders' heads. This is partly a *symptom of poverty* (and partly inarticulability — see §6), not a design choice. |
| **Reorganization pain** | Demotions, layoffs, and re-teaming burn trust. Human orgs therefore treat structure as a ratchet — hard to reverse — and under-build to stay safe. |

**Family B — coordination constraints (these are about information, not money)**

| Constraint | Driver | Source |
|---|---|---|
| **Coordination cost bounds org size** | A firm grows until organizing a transaction internally costs more than the alternative; the margin Coase identifies is coordination (transaction) cost. | Coase, *The Nature of the Firm* |
| **Communication overhead grows quadratically** | n members ⇒ n(n−1)/2 potential channels. Graicunas (1933) had already counted the supervisory-relationship combinatorics that underlie Urwick's 5–6. | Brooks, *The Mythical Man-Month*; Graicunas |
| **Span of control** | One supervisor can genuinely attend to a bounded number of reports. | Urwick; see §3 |
| **Managerial absorption limits growth *rate*** | Growth is bounded by the time incumbent managers can spare to absorb new managers into the firm's specific experience — the Penrose effect. | Penrose, *The Theory of the Growth of the Firm* |
| **Growth crises** | Each phase of Greiner's model ends in a management-regime breakdown — leadership (a management-capability crisis), autonomy (a delegation and motivation crisis), control, red tape, plus a fifth crisis Greiner left open ("?") — none of them financial. | Greiner (a model, not a finding) |
| **Structure stamps the product** | Communication topology becomes system architecture. | Conway |
| **Requisite variety** | A regulator's variety of responses must at least match the variety of disturbances it faces, relative to the outcomes that count as acceptable. | Ashby |

A note on Brooks, because his law bundles two mechanisms that land in *different*
families: the n(n−1)/2 communication overhead is Family B and survives for agents in
full; the ramp-up/onboarding drag of new members is Family A friction, and it largely
vanishes for agents — which strengthens, rather than weakens, this document's argument.

**Family C — incentive / alignment constraints (about neither money nor information)**

A third family constrains organizations at every size, rather than pushing them to
start small, and it matters here because it survives the transition to agents intact:

| Constraint | Driver | Source |
|---|---|---|
| **Measures decay when targeted** | Any proxy given power over outcomes gets optimized as a proxy. | Goodhart; docs/03 §3.2, docs/04 |
| **Principal–agent divergence** | A delegated optimizer optimizes its own objective, not the delegator's. | Principal-agent theory; docs/04 |
| **Separation of duties (SoD)** | No single actor may both commit and conceal an action; maker and checker stay distinct. | Internal-control practice; docs/03 §3.1 |

The load-bearing observation: **none of the classical results this repo is built on
lives in Family A.** They live in Families B and C — information and incentives, not
money. Greiner's model presupposes a growing firm; nowhere in it is capital the driver
of the crises. So "AI removes the money constraint" does not touch the theory in
THEORY.md — it removes a *different* constraint layer that human orgs suffer *in
addition*.

One caveat before moving on: human organizations also stay small for reasons that fit
none of these families — a founder's preference for control, legitimacy in the eyes of
customers and regulators, regulatory thresholds that make size itself a liability. They
are real, but they are not the constraints this repo's theory is built on; we note them
and set them aside.

---

## 6. What actually changes for an agent org

Walk Family A for agents:

- **Fixed cost → variable cost.** A dormant agent — a profile on disk plus its ledger
  history — costs **zero**. Cost is incurred only per active cycle (tokens). This is the
  single deepest economic difference: human orgs pay for *capacity*, agent orgs pay for
  *activity*. Every "start small" argument built on standing salary collapses.
- **Hiring = instantiation.** Spinning up a department is copying a profile and granting
  it a context pack — seconds, not months. Firing is deactivation, with no severance and
  no morale damage to the survivors.
- **Person-dependence becomes reducible to a single enforceable invariant.** An agent
  member *is* its profile + the shared ledger. Its knowledge is copyable and inspectable
  by construction. Person-dependence can reappear in one form: knowledge that lives in
  a member's *working state* and never reaches the ledger. Hence the invariant:
  **no knowledge outside the ledger** (Organ 5 discipline; docs/06 covers how observed
  knowledge becomes doctrine). Two caveats keep this honest. First, tacit knowledge:
  much human non-documentation is inarticulability, not poverty — Polanyi's tacit
  dimension, and the reason Nonaka & Takeuchi's SECI model is an entire machinery for
  externalization — and whatever an agent "knows" that never surfaces in writable form
  has the same character. Second, model weights: a dormant department re-activated on a
  different underlying model is not the same member, however complete its ledger. With
  the invariant held, the bus-factor problem largely dissolves; "rehiring" a dormant
  department returns it with its institutional memory. Note, though, that today the
  invariant is enforced by discipline and audit, not yet by the lint.
- **Reorganization is a commit.** Structure changes are yaml diffs; reversal is
  `git revert`. The human ratchet — where orgs under-build because rebuilding is
  traumatic — disappears. **Structure becomes cheap to change and therefore safe to
  design ambitiously.**

Family B, for agents, survives nearly item by item — only the currency changes:

- Coordination cost is paid in **tokens and latency** (multi-agent ≈ 15× a chat
  interaction, ≈ 4× a single agent; docs/04 §4 is the home of that number). Running the
  full ideal org at full duty cycle from day one is not free — it is the *most expensive
  possible* configuration.
- Span of control is paid in **supervisor context and attention** (§3).
- Conway: unchanged. Family C — Goodhart, principal-agent, SoD — is untouched in its
  entirety (docs/03, docs/04).
- Requisite variety: the gate's **repertoire of checks must cover the variety of failure
  and gaming modes the exploration front can produce** — a gate sized for two makers'
  failure modes rubber-stamps under twenty. (Sheer throughput saturation is a different
  constraint — that is span of control, above.)

The "nearly" is Penrose. The Penrose effect — a firm's growth *rate* limited not by
capital but by the time incumbent managers can spare to absorb new managers into the
firm's specific experience — is the classic non-financial growth constraint, and the
ledger + context-pack mechanism is precisely an argued nullification of it: a newly
activated department *reads* the firm-specific experience instead of slowly accumulating
it, so onboarding is — in the argument — instant and lossless. "Argued" is the operative
word; this is among the elastic model's strongest claims and should be among the first
tested.

---

## 7. The design consequence: latent org + elastic activation

Since *design* is now nearly free and *activity* is the only cost, the two decisions
human orgs are forced to merge — **what to design** and **what to staff** — come apart:

> **Design the complete ideal organization on day one — every department the target
> system will ever need, its profiles, its SoD matrix, its supervision lines — as a
> LATENT structure. Then activate and deactivate departments elastically, driven by
> load, with the growth-stage sensors (§§2, 4; docs/05) as the activation triggers.**

This pattern has human precedents, all from settings where Family A was already
weakened:

- **The project-based / "Hollywood" model**: the film industry maintains a full latent
  capability pool; each production activates exactly the crew it needs, then dissolves
  back into latency (DeFillippi & Arthur 1998 on film production). The term "latent
  organization" is not this repo's coinage: Starkey, Barnatt & Tempest (2000) use it for
  exactly this pattern in the U.K. television industry — a persistent structure that
  recurrently reconstitutes itself around projects. That precedent is acknowledged; the
  concept here is that one, transplanted.
- **Reserve forces**: designed, trained, fully structured — and dormant until mobilized.
  Note the disanalogy, though: reserves carry substantial standing costs (drill pay,
  training, readiness upkeep). The pattern transfers; the near-zero carrying cost does
  not.
- **Cloud auto-scaling / scale-to-zero**: the direct engineering analog; the org chart
  is the deployment manifest, departments are services, activation is load-driven.
- **Organizational slack** (Cyert & March): slack is definitionally *paid* excess —
  payments to coalition members beyond what is needed to keep them in the coalition. A
  zero-cost dormant profile is standby capacity, not slack. Latent departments deliver
  what slack is used to *buy* — adaptive capacity — without slack's carrying cost.

### 7.1 What the staged-growth model becomes under elasticity

The staged model of §§1–4 remains valid — Greiner's crises still arrive, because they are
management-regime phenomena, not financial ones. But their *meaning* inverts:

- Stages are no longer "what you can afford to build next"; they are **activation
  levels**, and the crisis signals are the **sensor triggers** for moving between them.
- Transitions become **bidirectional**. Human orgs traverse Greiner one way because
  shrinking is traumatic; an agent org oscillates freely — activate a layer under load,
  dissolve it when load passes. De-scaling is a first-class move, not a failure.
- The span-of-control gate (§3) stops being "when to hire a manager" and becomes
  the **admission condition on activation**: you may not activate an eleventh department
  under a supervisor whose effective span is eight — widen span (context investment;
  docs/07) or activate a sub-supervisor *with* the departments it will absorb (this is
  `add_layer`, charter-tier — a human decides).

### 7.2 The product-side mirror: the org is designed-full, but the system is built-out progressively

Elastic activation says *design the whole chart, activate part of it*. That is the right
rule for the **org shape** — but it does not carry over to the **system the org is
building**. A chart is near-free to design in full on day one (design is a yaml diff; §6);
a *system* is not. You cannot "design the whole product in full and activate slices" the
way you design the whole org and activate departments, because the product is discovered by
building it through the lifecycle (docs/11), and each phase's output is the input the next
phase needs. So the two run on opposite schedules, and this is not an inconsistency — it is
the two axes of §2b:

> **The organization is designed-full and activated-elastically; the system is built-out
> progressively through the SDLC phases.** The latent chart is complete on day one; the
> product exists only up to the phase its work has actually been admitted through.

This ties elastic *org* activation to *product* phase progress. A phase's departments
activate when — and only when — the **prior phase's output has been admitted** (the
`requires_prior` phase-gate of docs/11 §2). You do not activate a deploy department before
something is admitted to deploy; you do not stand up a test department before there is an
implemented deliverable that passed its design gate. The activation trigger is not only the
growth-stage sensor (a *load* signal) but also the **phase-admission event** (a *readiness*
signal):

- `requirements_signed_off` is the admission condition that makes activating a **design**
  department legitimate for that deliverable.
- `design_reviewed` gates activation of **implement**; the maker's `judge` and then the
  gate/skeptic chain gate activation of **deploy** (docs/03, docs/11 §1).
- The **deploy department itself** stays latent until the pipeline (CI/CD; docs/11 §3) has a
  `survives` result and a healthy reliability budget (docs/05) to release against.

So elasticity composes cleanly: the *org axis* breathes with load (activate/dissolve
departments), and the *product axis* advances monotonically with admitted phase output
(the system only ever grows through the gates). Activating a downstream phase's department
against un-admitted upstream output is exactly the phase-skip the docs/11 tooth refuses —
elastic activation may not be used as a back door around the phase chain.

### 7.3 What must never be elastic

The two-layer law (docs/03) applies to activation exactly as it applies to
self-organization:

1. **The control skeleton is never dormant while anything explores.** Gate, the
   adversarial checker ("skeptic" in the worked example of template/organization.yaml),
   supervisor, and ledger scale *with* active exploration (requisite variety for what
   they check, span of control for how much) and scale to zero only when exploration
   does. An active maker with a dormant checker is not a
   lean configuration; it is separation-of-duties disabled by a scheduling decision.
2. **The constitution is never latent.** Delegation boundaries, SoD, safety limits are
   in force at every activation level, including level zero.
3. **Activation authority is itself a controlled action.** Which departments run is a
   structural decision — it goes through the moves catalog (template/moves.yaml) and the
   audit lint, not through any agent's free judgment. In particular, no department may
   activate or deactivate its own checker.
4. **The phase order is never elastic.** Activation may bring a phase's department online
   earlier or later, but it may never let a deliverable *skip* a phase. Whatever the
   activation state, a phase may start only against its predecessor's admitted output
   (docs/11 §2 `requires_prior`). Elasticity chooses *when capacity comes online*, never
   *whether the chain is traversed* — the mold is invariant at every activation level.

---

## 8. The activation decision (the specialization gate)

When new work arrives, the org faces a choice that looks like make-or-buy but is not:
**stretch an active generalist** (context dilution, no spin-up cost) **or activate the
latent specialist** (spin-up + coordination overhead, clean context). Call it the
**specialization gate**. To be honest about the economics: this is an internal
division-of-labor decision, not a Coasean firm-boundary decision — there is no market on
either side of it. The right reference is Becker & Murphy (1992): the degree of
specialization is limited by the coordination costs among specialists, not by the extent
of the market. The rule:

> Activate the specialist when the work is (a) recurring rather than one-shot, or
> (b) far enough from any active department's profile that stretching would dilute its
> context pack, or (c) required to be independent for SoD reasons — a checker is never
> "absorbed" into a maker to save a spin-up.

And deactivate on the mirror conditions: a department whose queue has been empty for a
full review cycle, whose function has been absorbed by a standing convention
(standardization replacing supervision — Mintzberg's own progression), or whose product
phase has passed (see docs/05, maintenance and sunset).

### 8.1 Who may scale — authority scoped to span (§scale-authority)

The activation/deactivation *decision* above is separate from the *authority to make it*.
That authority is **the same for every manager; only the scope differs** — a section-chief may
scale within their section, a dept-head within their department, the CEO across the whole
chart. It is one primitive with a range parameter, not a different power per rank.

The range is not a new field: **a manager's scale scope is exactly the transitive closure of
its `supervises:`** (organization.yaml). A dept-head supervises section-chiefs and therefore,
transitively, their sections; the nesting composes for free. The rule the lint (O2c) and the
scale moves enforce:

> A role may activate / deactivate / re-scope a department **only if that department lies in
> the transitive closure of the role's `supervises:`.** (`requester_scope_covers_target`.)

Two guards keep this from becoming a back door. **The regime boundary:** an organic manager's
closure may never contain a control role — no dept-head can deactivate the gate/skeptic
"within its span" (O2c fails closed on this). **The span gate stays upstream:** this decides
*who may scale an existing layer*, not *when a layer may exist* — a supervisory layer is still
minted only by charter-tier `add_layer` after `widen_span_via_context` is tried first (§3).
Critically, do **not** pre-build a multi-level `supervises:` tree to "give managers someone
to be": design the *departments* fully (§5.1) but let the supervisory tree stay single-level
until `add_layer` earns each level under load — scale scope is *derived from* whatever tree
`add_layer` actually produced, never a place to author aspirational hierarchy. Built
conditionally, scoped scale-authority is fully compatible with "stay flat, widen span first";
built eagerly, it rebuilds the tall-structure tax through the back door.

At the top of this hierarchy sits the human CEO, whose scope is the whole chart and who alone
may **re-found** — tear the structure down and rebuild it with new roles, assets intact
(docs/05 §4.4). Same primitive, widest scope, plus the founding-tier ceremony that re-scoping
the whole org demands.

---

## 9. Rules of the elastic organization (summary)

1. **Design fully, day one.** The ideal org chart, complete with SoD matrix and
   supervision lines, is written before the first task runs — by the founder process
   from the RFP (docs/05 §1). Design is cheap; under-design is not.
2. **Run elastically.** Departments are latent by default; activation is load-driven,
   sensor-triggered, and executed only through the moves catalog.
3. **Both directions are first-class.** De-activation and layer dissolution are normal
   moves, not admissions of failure. The org breathes.
4. **Control scales with exploration and never sleeps while it runs.**
5. **No knowledge outside the ledger.** The one invariant that reduces person-dependence
   to an enforceable discipline and makes dormancy lossless (see the caveats in §6).
6. **Activation is bounded by span and budget, not by ambition.** The state invariants —
   span, SoD, control-never-dormant — are enforced mechanically by the audit lint;
   budget enforcement lives in the runtime's budget guard. Neither relies on anyone's
   restraint.
7. **Design the org fully; build the system progressively.** The chart is complete on day
   one and activated by load; the product is built out phase by phase and exists only up
   to its admitted phase (docs/11). A downstream phase's department activates only against
   the prior phase's admitted output — the two axes (§2b) advance on opposite
   schedules, and the phase chain is invariant across every activation level.
8. **Advance both axes together.** The delivery capability (§2b, P0→P4) advances at least
   as fast as the org shape (§2, Stages 0→5) that runs it — a bigger chart that ships
   worse is the amplifier failing (THEORY §1b, Organ 7: *the system and the organization
   grow together*).

---

## Sources

**Staged growth and span (§§1–4)**

- **Greiner curve (five growth phases, each ending in a crisis)** —
  <https://www.mindtools.com/aks7u4n/the-greiner-curve/>
- **Span of control (effective limits; Urwick 5–6, up to 15–20 in high-skill /
  high-communication settings; middle layers when span is exceeded; tall-structure
  costs)** — <https://en.wikipedia.org/wiki/Span_of_control>
- **Mintzberg's organizational configurations and coordinating mechanisms (simple
  structure / machine bureaucracy / professional bureaucracy / divisionalized form /
  adhocracy; direct supervision, standardization of work, skills, and outputs, mutual
  adjustment)** — see the span-of-control reference above and Mintzberg's
  *Structuring of Organizations*.
- **The product/SDLC axis (§2b)** — Forsgren, Humble & Kim, *Accelerate* (the four DORA
  metrics: deploy frequency, lead time, change-fail rate, MTTR) and the annual *DORA State
  of DevOps* reports; Goldratt, *The Goal* (Theory of Constraints: navigate to the moving
  bottleneck). The stage names (walking skeleton, CI, CD) are standard delivery practice;
  the reliability/error-budget stage is SRE (Beyer et al., *Site Reliability Engineering*).
  These live in this repo at docs/05 and docs/11.

**Elastic organization (§§5–9)**

- Coase, R. — *The Nature of the Firm* (1937): the margin at which a firm stops growing
  is coordination (transaction) cost.
  <https://en.wikipedia.org/wiki/The_Nature_of_the_Firm>
- Brooks, F. — *The Mythical Man-Month*: communication channels n(n−1)/2; Brooks's law
  (whose onboarding component is Family A, per §5.1).
  <https://en.wikipedia.org/wiki/Brooks%27s_law>
- Graicunas, V. A. — "Relationship in Organisation" (1933): the supervisory-relationship
  combinatorics underlying Urwick's 5–6.
- Penrose, E. — *The Theory of the Growth of the Firm* (1959): the Penrose effect —
  growth rate bounded by managerial absorption of new managers into firm-specific
  experience. <https://en.wikipedia.org/wiki/The_Theory_of_the_Growth_of_the_Firm>
- Becker, G. S. & Murphy, K. M. — "The Division of Labor, Coordination Costs, and
  Knowledge" (1992): specialization limited by coordination costs among specialists —
  the economics behind §8's specialization gate.
- Greiner — growth phases ending in management-regime crises; a model, not a finding
  (see staged-growth sources above).
- Ashby, W. R. — Law of requisite variety.
  <https://en.wikipedia.org/wiki/Variety_(cybernetics)>
- Cyert & March — organizational slack (paid excess to coalition members), *A Behavioral
  Theory of the Firm*. Note that latent capacity in §7 is standby capacity, not slack in
  their sense. <https://en.wikipedia.org/wiki/A_Behavioral_Theory_of_the_Firm>
- Starkey, K., Barnatt, C. & Tempest, S. — "Beyond Networks and Hierarchies: Latent
  Organizations in the U.K. Television Industry", *Organization Science* 11(3) (2000):
  the prior coinage of "latent organization".
- DeFillippi, R. J. & Arthur, M. B. — "Paradox in Project-Based Enterprise: The Case of
  Film Making" (1998): project-based film production.
- Project-based organization (the "Hollywood model").
  <https://en.wikipedia.org/wiki/Project-based_organization>
- Polanyi, M. — *The Tacit Dimension*; Nonaka, I. & Takeuchi, H. — *The
  Knowledge-Creating Company* (the SECI model): why much human knowledge resists
  documentation (§6's tacit-knowledge caveat).
- Anthropic — multi-agent token cost, ≈15× a chat interaction (≈4× a single agent), as
  cited in docs/04 §4.

*These are human-organization models applied as lenses to agent orgs. The mappings are
working hypotheses to test against your own system, not established results. The Family
A / B / C split and its consequences (§§5–9) are this repo's own synthesis; the
constraints themselves are the cited classics. Treat §§7–9 as design hypotheses to be
tested against a running system, per the repo's falsifiability stance.*
</content>
</invoke>
