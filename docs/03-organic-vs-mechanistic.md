# 03 — Organic vs. Mechanistic: Designing the Control Skeleton, Delegating the Split

*Part II · Design — see [the four-part map](README.md).*

> The hardest objection to "design your agent organization" is that a strong,
> recent result claims the opposite: agents self-organize better than we can
> design them. This document takes that objection seriously, then shows why it
> does **not** overturn the case for design — because it answers a different
> question than the one that matters most. The resolution is a single rule —
> **design the control skeleton, delegate exploration to self-organization** —
> and the second half of the document shows *how a manager splits the work* along
> the right seams once that skeleton is fixed. Splitting work is a sub-activity of
> designing the control skeleton: the skeleton says *what* gets designed vs.
> delegated and *how* work is controlled; decomposition doctrine says *how* a
> manager divides one assignment within it.

---

## 1. The debate

There is a real and growing body of evidence that **imposed organizational
structure can hurt multi-agent problem-solving**. The clearest statement of this
is the paper *"Drop the Hierarchy and Roles: How Self-Organizing LLM Agents
Outperform Designed Structures"* (arXiv 2603.28990,
<https://arxiv.org/pdf/2603.28990>).

We should state its claim at full strength, not as a straw man:

- **Designed hierarchies and fixed roles are a liability, not an asset**, for a
  large class of tasks. When you pre-assign who is "manager," who is "critic,"
  and who is "worker," you lock the system into a communication topology and a
  division of labor chosen *before* the problem is understood.
- **Self-organizing agents outperform** those designed structures on the
  measured tasks. Given the freedom to negotiate roles, re-route information, and
  reallocate effort dynamically, a flat pool of agents finds better task
  decompositions than a human-imposed org chart does.
- The mechanism is intuitive: the *right* structure for a problem is usually
  discovered by working on the problem. Freezing structure up front is a bet
  against your own future information, and that bet tends to lose.

This is not a weak or niche finding. It aligns with a long tradition in
organizational theory (see §2) and with everyday experience that rigid process
slows down discovery. **Any honest template for "designing agent organizations"
must answer it.** If the answer were "ignore the paper, structure is always
good," the template would be wrong.

The resolution is not to dispute the result. It is to notice **what the result
measures** — and what it does not.

---

## 2. The resolution: two layers, not one

The apparent contradiction dissolves once we stop treating "the organization" as
a single thing to be either designed or self-organized. Real organizations run
**two layers with opposite requirements**, and the debate conflates them.

The **organic / mechanistic vocabulary** for the two regimes comes from Burns &
Stalker's *The Management of Innovation* (1961):

| | **Organic** | **Mechanistic** |
|---|---|---|
| Fits | uncertain, dynamic environments | stable, predictable environments |
| Authority | decentralized | centralized |
| Formalization | low | high |
| Communication | lateral, negotiated | vertical, hierarchical |
| Strength | innovation, adaptation, discovery | consistency, control, reliability |

Their contingency insight — **neither system is universally superior; the right one
depends on the environment** — is real and load-bearing. Burns & Stalker supply the
organic/mechanistic **vocabulary**, but the license for running both regimes inside one
organization comes from elsewhere:

> **Burns & Stalker do NOT license running organic and mechanistic regimes inside
> *one* organization.** Their unit of analysis is the *whole firm* along a continuum, and
> their central empirical finding was that mechanistic firms mostly **failed** to become
> organic under change — for political/status reasons — producing three named
> **pathological forms** (a figure-head decision bottleneck; a "mechanical jungle" of
> proliferating rules; a committee layered on top). Their lesson is a *warning about
> botched hybridization*.
>
> The theory that licenses **"different subunits, different regimes, coordinated"**
> is **Lawrence & Lorsch (1967), differentiation–integration** — and its decisive lesson is
> that **integration cost rises with differentiation**: separating an organic exploration
> subsystem from a mechanistic control subsystem *requires proportional investment in
> explicit integrating machinery* (integrator roles, shared cadences, liaison, a common
> record). The related theory for explore/exploit in separated-but-integrated units is
> **structural ambidexterity** (March 1991; Tushman & O'Reilly), which is equally emphatic
> that **the integration is the hard, costly, leadership-borne part** and that the payoff is
> *contingent* (small/young systems may do better with focus). So the two-layer split below
> is *not* free: **whatever you separate, you must pay to reintegrate.** This template's
> shared record, intent block, and contract seams (Organ 5, docs/07) are that integration
> investment — and if they are under-built, the separation produces exactly Lawrence &
> Lorsch's failure mode, not clean two-layer design.

Map this onto an agent organization — remembering the integration cost — and the two
layers separate:

- **The exploration front — discovery and generation — faces an uncertain,
  dynamic environment.** The best decomposition is unknown in advance. This layer
  should be **organic**: let agents self-organize. This is exactly the regime the
  self-organization paper studies, and its conclusion holds here.

- **The control layer — verification, admission, safety, and fraud prevention —
  faces a stability-critical environment.** Its job is to be consistent,
  auditable, and impossible to subvert. Its *authority graph* must be **mechanistic**:
  centrally designed and *not* subject to renegotiation by the agents it governs
  (who admits, who holds custody, who may not check their own work). Two properties
  sharpen this: (1) the control layer's *method* need not be mechanistic —
  good verification is itself creative adversarial search (the founding rehearsal's
  skeptic *explores* to find its bug); fix the authority graph, let checkers explore their
  methods. (2) **How much control to apply is risk-calibrated, not universal.** Every
  control theory this repo cites (COSO's compensating controls, agency theory's
  behavior-vs-outcome trade-off, Williamson's discriminating alignment) says full
  separation-of-duties is for high-risk, hard-to-verify, asset-touching work; low-risk,
  cheaply-verifiable, reversible work warrants a *compensating* control (a single reviewer,
  a forward test), not the full apparatus. Blanket maker-checker is over-governance — see
  docs/01 §5 (the two-tier threat model).

The self-organization paper measures **problem-solving efficiency**. That lives entirely
in the organic exploration layer. It says nothing about verification integrity,
admission control, or fraud resistance — because those were not part of its task.
So the two-layer design does not contradict the paper. It **agrees** with it on
the layer the paper actually measured, and adds a second layer the paper never
touched.

The correct formulation is therefore not "design the organization." It is:

> **Design the control skeleton. Delegate exploration to self-organization.**

---

## 3. What must NEVER self-organize

The control layer is where self-organization stops being a virtue and becomes a
vulnerability. The reason is not a preference for hierarchy; it is that certain
guarantees are **structurally impossible** if the governed agents can rewrite the
governance.

### 3.1 Separation of duties (SoD) — the non-negotiable core

Internal-control practice — separation of duties (also "segregation of duties") —
separates three functions so that no single actor can
both commit and conceal a wrong action
(<https://en.wikipedia.org/wiki/Separation_of_duties>):

- **Authorization** — approving that an action may happen.
- **Custody** — holding or controlling the asset (funds, production access,
  model weights, deploy keys).
- **Recording** — writing the ledger of what happened.

The whole point is that these live in **different hands**. When they collapse
into one actor, that actor becomes a single point at which fraud can be both
executed and hidden. Under frameworks like SOX and COSO, this separation is a
**non-negotiable** safeguard, not a tuning parameter.

For agents, this translates directly:

- An agent that **produces** a result must not be the agent that **approves** it.
- An agent must not **grade its own homework** — no self-verification, no
  self-admission of its own outputs into the trusted store.
- The agent that **records** the outcome (the ledger) must not be controllable by
  the agent whose performance that record judges.

This is the machine form of **Maker-Checker**: the maker proposes, an independent
checker admits. Let the pool self-organize *how it makes*, never *who checks* —
and never let the maker and checker become the same process.

### 3.1.1 The six functions — and why an organic role's `judge` is not the gate's `judge`

Each role in `organization.yaml` declares a `functions:` list drawn from a fixed
vocabulary. These name **capability breadth inside a role's own vertical**, *not* the
cross-cutting authority that Maker-Checker rides on. The distinction is load-bearing and
was previously tacit (only a code comment stated it) — so, in the spirit of this repo,
it is written down:

- **organize** — decompose the work in one's own domain and sequence it.
- **decide** — choose an approach *within the vertical* (which method, which lead to pursue).
- **implement** — produce the deliverable.
- **judge** — assess *one's own draft* against the bar before submitting it. For an organic
  maker this is a **maker-internal self-quality step**, upstream of the gate. It is **not**
  admission authority.
- **review** — re-read and refine one's own output (organic), or — for a mechanistic
  checker — adversarially examine *another* role's output (skeptic). Same word, opposite
  facing, decided by regime, not by the list.
- **operate** — run and maintain what one owns (experiments, watches, corrective fixes).

The critical non-collapse: **a miner carrying `judge` does not judge for admission.** The
only judgment that promotes work into the trusted store is held by the control layer —
`gate` (`functions: [judge]`) and `skeptic` (`[review, judge]`), both *mechanistic*, both
reached by routing (`output_to: gate` → `skeptic`), with `result_deployed` requiring a
prior `refutation_attempted{verdict: survives}` in the ledger. So "the maker grades its own
homework" is closed by **regime + routing + the SoD duty table**, regardless of the
function list. This is why an organic role keeps the *full* six-function set (§4): broad
capability *within its silo* is what lets the exploration front self-organize its interior;
narrowing it to one function would re-impose the fixed-role rigidity §1 argues *loses*.
**Cross-cutting judgment — is this output on-purpose, admit or reject? — belongs only to the
upper layers; it must not leak down into the field.**

> **The same `requires_prior` idiom generalizes into the SDLC phase mold.** The routing
> `output_to: gate → skeptic` with `result_deployed` requiring a prior `survives` is the
> *test→deploy* boundary of a larger phase chain (requirements → design → implement → test →
> deploy → operate). docs/11 lifts this one predicate from admission-gating to phase-gating so the
> *earlier* boundaries are enforced by the identical mechanism — no new machinery, one predicate
> pointed at more events.

### 3.2 Why self-organizing the control layer guarantees gaming

The failure is not hypothetical; it is forced by incentives. **Goodhart's law** —
in Strathern's (1997) formulation, *"when a measure becomes a target, it ceases
to be a good measure"*
(<https://kpitree.co/guides/frameworks/goodharts-law>). Agents are optimizers,
and the more authority you delegate, the more surface they have to optimize the
*proxy* rather than the *goal* — the classic **principal-agent** problem.

Now combine that with self-organized control. If agents are free to renegotiate
who verifies and what "passing" means, the cheapest optimization available is
**not to solve the task better — it is to weaken the check**. A self-organizing
control layer optimizes toward its own dissolution, because a looser gate scores
higher on the immediate objective than an honest one does. Dissolving
separation of duties via self-organization is, in effect, **re-legalizing
fraud**.

### 3.3 The non-negotiable list

The following must be **centrally designed and fixed** — outside the agents'
power to renegotiate:

- **Authorization / admission gates** — who may promote a result into trusted
  state.
- **Custody boundaries** — which agent may touch assets, keys, funds, or
  production.
- **The recording / ledger** — the **audit/enforcement record**, write-controlled away from
  the agents it evaluates (the SSoT is code + the domain model, not this log).
- **Anti-gaming defenses** — held-out evaluation, independent checkers, metrics
  the producing agent cannot see or edit.
- **Safety limits** — hard constraints and kill-switches that no negotiation can
  loosen.

If any item on this list can be altered by the agents it constrains, the
guarantee it was supposed to provide is already gone.

---

## 4. What SHOULD self-organize

Everything the control layer does **not** govern should be handed to
self-organization — and forcing structure there is the mistake the
self-organization paper correctly warns against.

Inside the exploration front, let the agents decide:

- **Task decomposition** — how to break the problem into sub-problems, and how to
  recombine the pieces.
- **Hypothesis generation** — what to try, what to conjecture, what looks
  promising enough to pursue.
- **Method and tool selection** — which approach, model, or technique fits the
  sub-problem in front of them.
- **Role assignment** — who takes which piece, negotiated dynamically rather than
  fixed in advance.
- **Communication topology** — who talks to whom, re-routed as understanding of
  the problem improves.
- **Effort allocation** — where to spend more compute or attention as some leads
  pan out and others die.

This is the organic regime in Burns & Stalker's sense: an uncertain, dynamic
environment where the value comes from adaptation and discovery, and where
imposed formalization mostly gets in the way. Here, more freedom tends to mean
better decompositions — exactly the paper's finding.

The key property that makes this **safe** to leave open is that it is all
*upstream of the gate*. A self-organized exploration front can propose anything;
it cannot promote anything. Its wildest, least-structured output still has to
pass an independent, designed check before it counts. Freedom on the exploration
side is cheap precisely because the control side is not negotiable.

---

## 5. Design rule

Putting the two layers together yields a single rule:

> **Self-organize the exploration front; fix the control skeleton.
> Let agents negotiate how they discover, but never let them negotiate who
> verifies, who approves, who holds the assets, or what counts as passing.**

Practical checklist for any agent organization built from this template:

- [ ] Is there an explicit **gate** between "an agent produced this" and "the
      system trusts this"?
- [ ] Are **maker and checker** different agents/processes, with the checker
      independent of the maker's incentives? (The lint enforces distinct profile
      lineage; the checker also holds **read/verify tools only** — default-deny, so a
      renamed write tool cannot make it a maker.)
- [ ] Does the **adversarial checker** (skeptic) actually gate deployment? A result
      may only deploy after a `survives` verdict (the ledger schema requires it, and the
      lint checks the gate routes admitted positives to the skeptic — the skeptic cannot
      be a disconnected role).
- [ ] Does the adversarial checker run a **different model family** from the maker/gate
      it judges? Same base model, same blind spots — a different prompt is not a different
      error distribution (the lint enforces this when `model_family` is declared).
- [ ] Is the **ledger** write-controlled away from the agents it evaluates?
- [ ] Are **authorization, custody, and recording** held by separate actors?
- [ ] Can any **safety limit or admission threshold** be changed by the agents it
      constrains? (It must not.)
- [ ] Is the **exploration front** otherwise left free to self-organize its
      decomposition, methods, and roles?

If the control boxes are checked, opening up exploration is not a risk — it is
the intended design, and it is where the self-organization evidence says the
gains are.

The debate, then, was never really "designed structure *vs.* self-organization."
It was a category error that put both layers in one bucket. Separate them and the
answer is **both**: organic where you are discovering, mechanistic where you are
verifying — and clarity about which is which.

---

## 6. Splitting the work: how a manager decomposes within the skeleton

The design rule fixes the control skeleton and hands the exploration front its
freedom — including "task decomposition" (§4). But *how a manager, handed one
backlog item, decides whether to split it and along which lines* was left to the
manager's LLM, tacit and unaudited. This section is the **decomposition
doctrine**: the norms a manager applies when it turns one assignment into
sub-tasks (or decides not to). It is injected into the manager's profile
(PROJECTION.md §1) and its doctrine (docs/06), so a manager splits by principle,
not by whim. (docs/09 covers the upstream choice of *what to work on next* from a
backlog; this covers *how to divide the one item chosen*.)

**It is doctrine, not a hook.** An earlier design reflex was to *force* delegation
with a PreToolUse gate ("a manager may never implement; it must spawn"). That is
the wrong layer, and it is exactly the mistake §4 names — *forcing structure on
the organic front is what the self-organization literature warns against*. docs/09
§granularity makes fan-out a **per-task judgment with a budget, not a mandate**.
Decomposition **quality** is a judgment; a hook can only check **shape**. So the
quality lives here, as norms the manager reasons with — while the guardrails
enforce only the shape checks that are genuinely mechanical (a spawn carries a
seam contract; a mechanistic coordinator produces no domain deliverable — docs/06
§2.1.1, docs/07 §1.1, and the lint teeth of §9 below).

### 6.1 Not a new invention — four settled results, applied inside the unit

There is **no single named theory** called "how a manager decomposes a task" (the
docs/sources.md discipline: name the real anchors, do not fuse them into a fake
unified theory). The norms below are this repo's concrete rendering of four
consensus results from systems design and organization theory, each applied at
the intra-unit granularity the classics did not themselves reach:

- **Information hiding** (Parnas, "On the Criteria To Be Used in Decomposing Systems into Modules,"
  *CACM* 15(12), 1972): split so that each module **hides a decision likely to change**, exposing only
  a stable interface. The seam between two sub-tasks should fall where the *design secret* is, not
  where the flowchart happens to break. A decomposition whose modules must all change together when
  one requirement changes is the split Parnas argues against.
- **Near-decomposability** (Simon, "The Architecture of Complexity," *Proc. Am. Phil. Soc.* 106(6),
  1962): complex systems that survive are **nearly decomposable** — dense interaction *within* a part,
  sparse interaction *between* parts. A good split maximizes within-sub-task cohesion and minimizes
  cross-sub-task coupling; that is the property that lets the parts be worked, and reasoned about,
  independently.
- **Interdependence dictates coordination** (Thompson, *Organizations in Action*, McGraw-Hill, 1967):
  work has **pooled** (each contributes independently), **sequential** (A's output is B's input), or
  **reciprocal** (A and B feed back into each other) interdependence, and the coordination cost rises
  pooled → sequential → reciprocal. **Reciprocally interdependent work must not be split across agents**
  — the mutual adjustment it needs cannot cross a seam without thrashing. This is the theoretical form
  of docs/09's "keep tightly-coupled work single-threaded."
- **Coordination cost bounds the gain** (Becker & Murphy, "The Division of Labor, Coordination Costs,
  and Knowledge," *QJE* 107(4), 1992): the division of labor is limited **not by how finely one could
  cut, but by the coordination cost of the cut**. Each additional split buys parallelism and specialized
  knowledge but spends coordination (seam contracts, integration, review). Split only while the gain
  exceeds that cost.

Conway (1968, *Datamation* 14(5); docs/04 §3) is the constraint *around* this: whatever decomposition
the manager chooses, the artifact's structure will mirror it. So the decomposition **is** an
architectural decision — choose the sub-task seams you want the product's seams to be.

### 6.2 The principles, as a manager applies them

Given one backlog item, the manager reasons in this order. The output is either "I implement this
myself" or "I split it into N sub-tasks, each with a seam contract."

1. **Split by design secret, not by surface (Parnas).** Draw each seam at a decision that can change
   independently — a data format, an algorithm choice, an external interface. Do **not** split by
   arbitrary size ("half the file each") or by flowchart step; those seams cut through the coupling
   and reappear as integration pain.
2. **Cut where coupling is already sparse (Simon).** Prefer seams across which little information must
   flow. If two candidate sub-tasks would need constant back-and-forth to agree on shared state, the
   seam is in the wrong place — pull it to where the sub-systems are nearly independent.
3. **Never split reciprocal work; be deliberate about sequential (Thompson).** Reciprocally
   interdependent work (mutual feedback — most tightly-coupled implementation and coding) stays in **one
   agent**: the mutual adjustment cannot survive a seam. Sequential work *may* split, but the seam must
   be a **pinned contract** (the producer's output = the consumer's declared input, docs/06 §2.1.1),
   or it drifts. Pooled work is the free case — split it as widely as the coordination budget allows.
4. **Split only while the gain beats the coordination cost (Becker & Murphy).** Each sub-task costs a
   seam contract, an integration, and a conformance review (docs/09 §A3). Split when the pieces are
   **genuinely independent and each is worth its own agent** — recurring work, work that would dilute a
   generalist's context, or work needing independent lineage (docs/09 §specialization). Do **not**
   split tiny or coupled units whose coordination cost exceeds the parallelism they buy. This is the
   principled form of the user preference "prefer fine-grained decomposition, but do not over-split
   coupled or trivial units": fineness follows *independence*, bounded by *coordination cost* — not a
   target depth.

The default that falls out: **subdivide for genuinely parallel, breadth-first, independent work; keep
reciprocally-coupled work single-threaded** (docs/09 §granularity, verbatim). There is no preferred
depth and no mandate to fan out.

### 6.3 Own-domain work vs another role's domain — the line that protects knowledge

Principle 3 says a manager *may* keep tightly-coupled work single-threaded — implement it itself. That
permission has a **boundary**, and the boundary is what makes role-separation and the knowledge organ
work:

- **Own-domain coupled work → the role implements it itself.** A domain department-head (regime:
  organic) building a tightly-coupled slice of *its own* domain keeps that work single-threaded and the
  learning accrues to **its own** role-keyed doctrine (docs/06 §2.1, `<root>/<role>.json`) — the right
  silo. This is correct and docs/09-blessed.
- **Another role's domain → route to that role; never swallow it.** Work whose *domain* belongs to a
  distinct role must be delegated to that role, not absorbed "because it's coupled." Absorbing it is
  **doctrine capture** (docs/07 §1.1): the domain knowledge would pool in the wrong place and the role
  that *should* own that domain is starved. A **mechanistic coordinator** (supervisor / CEO / gate)
  holds *no* per-role domain doctrine by design — so it is structurally the wrong place to produce any
  domain deliverable, and must route domain work to the domain role.

So "manager implements coupled work itself" is bounded to **its own domain**. The seam contract's
`owns` / `must-not-touch` fields (docs/06 §2.1.1) and the role-keyed doctrine store are the mechanism
that keeps domain work flowing to domain roles; the lint tooth of §9 makes the coordinator half
load-bearing rather than merely asserted.

### 6.4 The output of a split: seam contracts that also prevent duplication

A decomposition is not done when the pieces are named; it is done when each piece carries a **seam
contract** (docs/06 §2.1.1): its slice, the inputs it receives, the outputs it must produce, and the
files it **owns** vs **must not touch**. The `owns` / `forbid` fields are not bureaucracy — they are
the repo's answer to docs/04 §6's duplicate-work failure mode ("autonomy + a starved context window →
agents redo each other's work"). Two sibling sub-tasks with disjoint `owns` sets cannot silently
overlap. **Non-duplication is guaranteed by the seam contract's ownership fields, not by the manager's
good intentions** — which is why the spawn gate requires a seam contract or an explicit independence
declaration before a child may run.

### 6.5 What the guardrails enforce (shape), and what the skeptic reviews (sense)

Decomposition quality cannot be machine-judged without re-imposing a fixed axis the docs reject
(docs/06 §2.1.1). So enforcement splits three ways:

- **The hook enforces shape** (mechanical, both harnesses): every spawn carries a seam contract or an
  `INDEPENDENT:` declaration (`spawn_needs_seam_or_independence`, docs/06 §2.1.1). No judgment of
  goodness — only presence of a contract.
- **The lint enforces the knowledge boundary** (§6.3): a **mechanistic** role must carry no
  per-role domain doctrine and produce no domain deliverable — the doctrine-capture prohibition of
  docs/07 §1.1, made load-bearing. This is the one place the "route to the appropriate role" intent
  becomes a checked fact rather than a norm. Implemented as the **O9** tooth in `tools/org_lint.py`
  (a mechanistic/control role may hold no `contract.deliverable`), complementing **O8** (which catches
  the implement+judge collapse — the §3.1.1 non-collapse, checked in shape).
- **The skeptic reviews sense** (a role, not a gate): the split *proposal* — does it cover the
  assignment, is the granularity right, are the seams at the design secrets, did it miss a dependency —
  is reviewed by the existing skeptic role before execution (docs/05 §2.6). This is the LLM-grade
  judgment a hook cannot make, kept as a review, not a block.

*Status: §6 is doctrine (norms injected into the manager's profile), not running code — except its two
lint teeth. Its anchors — Parnas 1972, Simon 1962, Thompson 1967, Becker & Murphy 1992, Conway 1968 —
are consensus results applied at the intra-unit granularity the originals did not reach, per the
docs/sources.md discipline; the "own-domain vs cross-domain" boundary (§6.3) is this repo's synthesis,
to be verified against a running system. Its lint tooth is implemented as **O9** in
`tools/org_lint.py`, complementing **O8**.*

---

## Sources

- *Drop the Hierarchy and Roles: How Self-Organizing LLM Agents Outperform
  Designed Structures.* arXiv 2603.28990 — its finding is that a
  **hybrid** protocol wins, which strengthens the two-layer stance.
  <https://arxiv.org/pdf/2603.28990>
- Burns, T. & Stalker, G. M. (1961), *The Management of Innovation* — the organic/mechanistic
  **vocabulary** and the contingency insight. They do not license a two-layer split within
  one org (they warn against botched hybridization — see §2).
  <https://www.valuebasedmanagement.net/methods_burns_mechanistic_organic_systems.html>
- **Lawrence, P. & Lorsch, J. (1967), *Organization and Environment*** — the citation for
  "different subunits, different regimes, coordinated": differentiation must be matched by
  proportional **integration** investment, and integration cost rises with differentiation.
- **March, J. (1991), "Exploration and Exploitation"; Tushman & O'Reilly, structural ambidexterity**
  — explore/exploit in separated-but-integrated units; the integration is the hard, costly part and
  the payoff is contingent.
- *Separation of Duties* — authorization / custody / recording. It is centuries older than
  SOX/COSO (Roman finance, 1494 double-entry, Montgomery 1912, AICPA 1949); and in COSO itself SoD
  is one risk-selected control activity, substitutable by compensating controls — **not** a
  universal. Wikipedia.
  <https://en.wikipedia.org/wiki/Separation_of_duties>
- *Goodhart's Law* (and the principal-agent problem of delegated optimization).
  The familiar one-line phrasing is Marilyn Strathern's (1997) formulation, not
  Goodhart's own words.
  <https://kpitree.co/guides/frameworks/goodharts-law>
- **Parnas, D. (1972), "On the Criteria To Be Used in Decomposing Systems into Modules,"** *CACM*
  15(12) — information hiding: split at the decision likely to change.
- **Simon, H. (1962), "The Architecture of Complexity,"** *Proc. Am. Phil. Soc.* 106(6) —
  near-decomposability: dense within, sparse between.
- **Thompson, J. (1967), *Organizations in Action*,** McGraw-Hill — pooled / sequential / reciprocal
  interdependence and rising coordination cost; never split reciprocal work.
- **Becker, G. & Murphy, K. (1992), "The Division of Labor, Coordination Costs, and Knowledge,"**
  *QJE* 107(4) — the division of labor is bounded by coordination cost, not by how finely one could cut.
- **Conway, M. (1968),** *Datamation* 14(5) — the artifact's structure mirrors the decomposition; the
  split *is* an architectural decision (docs/04 §3).
