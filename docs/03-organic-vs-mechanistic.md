# 03 — Organic vs. Mechanistic: Resolving the Designed-Structure Debate

> The hardest objection to "design your agent organization" is that a strong,
> recent result claims the opposite: agents self-organize better than we can
> design them. This document takes that objection seriously, then shows why it
> does **not** overturn the case for design — because it answers a different
> question than the one that matters most.

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
> shared record, intent block, and contract seams (Organ 5, docs/08) are that integration
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
- **The recording / ledger** — the source of truth, write-controlled away from
  the agents it evaluates.
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
