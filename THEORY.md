# THEORY — Decomposing an Agent System from the Organization Down

> The claim of this repository: a multi-agent AI system **is an organization**, and the right way
> to design one is to **decompose it top-down from what an organization needs**, not to assemble
> it bottom-up from separately-invented parts (prompt → context → harness → loop). When you
> decompose from the top, the harness and the loop **fall out as two organs among seven** — and
> you also recover the organs a parts-first view structurally cannot see.

This document is the core. Everything else in the repo (`template/`, the growth-stage playbook, the
failure-mode catalog, the elastic-organization model and the lifecycle/operations spec, the
knowledge/doctrine organ and the context economy — `docs/05`–`docs/08` — and the machine audit,
`tools/org_lint.py`) is an application of it.

---

## 0. Method: why top-down, and why it matters

There are two ways to arrive at a complex artifact.

**Bottom-up (part-assembly).** You notice a useful pattern, name it, harden it, and later try to
compose it with other patterns you named. This is how agent engineering actually happened:
*prompt engineering* (2023) → *context engineering* (what the model sees, 2024–25) → *harness
engineering* (the scaffolding around the model, 2026) → *loop engineering* (the control loop that
reruns the model, 2026). Each is real and useful. But part-assembly has a structural blind spot:
**you can only compose the parts you happened to invent.** Nothing in "harness + loop" ever forces
you to ask *how many agents can one supervisor actually oversee before review quality collapses?*
— because span of control is not a harness concept or a loop concept. It is an **organizational**
concept, and a parts-first vocabulary has no slot for it.

**Top-down (first-principles decomposition).** You name the whole first — here, *an organization* —
and ask *what must this whole have, necessarily, to exist and function?* Each answer is an organ.
The organs are not a wish-list; they are what the definition of the whole entails. This is the same
discipline as decomposing a strategy from its purpose, or building a large machine from small
composable wheels that each snap onto a shared interface: **the root is primary, the parts hang off
it.** Harness and loop are two such wheels.

The payoff of top-down is not elegance. It is **completeness and ordering**: it tells you what you
are missing, and it tells you what to build next.

---

## 1. The first principle: an agent system is an organization

Define an **organization** minimally, in a way that is neutral between humans and agents:

> An organization is a **coordinated division of labor directed at a purpose**, persisting over
> time, whose members have bounded capabilities and imperfect alignment with the purpose.

(This definition is compressed, not invented: it condenses Barnard (1938) — "a system of
consciously coordinated activities of two or more persons" — and the *bounded capabilities* clause
is Simon's bounded rationality.)

Every clause is load-bearing, and every clause forces an organ:

- **purpose** → the organization needs a *telos* that grounds every local decision (Organ 1).
- **division of labor** → it needs *structure*: who does what, who coordinates whom (Organ 2).
- **members with bounded capabilities** → each member needs a *substrate* through which it
  perceives, acts, and remembers — its anatomy (Organ 3 = **the harness**).
- **persisting over time** → it needs a *metabolism*: a rhythm of acting, deciding, resting, and
  self-correcting (Organ 4 = **the loop**).
- **coordinated** → it needs *information flow* between members and across time (Organ 5).
- **imperfect alignment** → it needs *incentives and control* so members serve the purpose and not
  a convenient proxy for it (Organ 6).
- **persisting + growing** → it needs a way to *scale without collapsing* (Organ 7).

That is the whole decomposition. The rest of this document develops each organ: the human-org
meaning, the derivation, the agent-system realization, the failure mode when the organ is absent or
malformed, and the concrete primitives that implement it.

A note on the two organs the industry already named: **the harness (Organ 3) and the loop (Organ 4)
are the most *mechanical* organs** — the ones made of tools, runtimes, and control flow — so they
were the first to be seen, isolated, and given names by engineers building the substrate. That is
why they feel like the foundation. Organizationally they are not the foundation; they are the
anatomy and the metabolism of a body whose **structure, incentives, and growth** are equally
necessary and were simply harder to see from inside the tooling.

---

## 2. The seven organs

### Organ 1 — Purpose (telos)

**Human org.** A firm exists for something. Peter Drucker's *management by objectives* (1954) and
its descendant OKRs both start here: goals cascade from the top so that a local decision at the edge
can be checked against the purpose. But the two differ on the point this organ turns on. MBO as
historically practiced was routinely coupled to appraisal and pay — the coupling Deming famously
attacked — and that coupled form is the cautionary case: reward the number and people manage the
number. It is modern OKR practice (Doerr/Google) that deliberately **separates the goal from the
reward** (OKRs are not tied to compensation) precisely to stop people from gaming the number instead
of pursuing the goal.

**Derivation.** The definition begins with *directed at a purpose*. Without an explicit, propagated
telos, a division of labor has nothing to divide *toward*; every other organ becomes unanchored.

**Agent realization.** A single, explicitly stated objective, delivered into every agent's context,
against which any proposed action or admission can be tested. Not a metric — a *purpose*, with the
metric held one level below it as an instrument that can be wrong.

**Failure mode if malformed.** This is the deepest failure in the whole system, because it
propagates. If you operationalize the purpose as a proxy metric and then *reward the proxy*, you
have created the conditions for **Goodhart's law**: the metric stops measuring the goal the moment
it becomes the target. Agents, which are relentless local optimizers with full knowledge of their
own context, will find the gap between "satisfy the metric" and "serve the purpose" faster than any
human employee. The defense is architectural, not motivational: **ground admission in the true
purpose, keep quantitative proxies out of the reward, and build measurement systems that can tell
gaming apart from genuine success** (nulls, placebos, forward tests). "More output" must never be
the objective if the objective is "value."

**Primitives.** A purpose statement in every context pack; an admission standard grounded in the
purpose (not in volume); measurement instruments designed to be gaming-resistant.

---

### Organ 2 — Structure (division of labor + coordination)

**Human org.** Henry Mintzberg's insight is that an organization's *type* is determined by its
dominant **coordination mechanism**: direct supervision (simple structure), standardization of work
(machine bureaucracy), standardization of skills (professional bureaucracy), standardization of
outputs (divisionalized form), or mutual adjustment (adhocracy). The second structural lever is
**span of control** — the number of subordinates one supervisor can *effectively* oversee (classic
estimates 5–6; 15–20 in high-skill, high-communication settings). Span sets how *tall* the hierarchy
must be: narrow spans force many layers (costly, slow); wide spans keep it flat (cheap, fast) but
demand that subordinates be self-sufficient.

**Derivation.** *Division of labor* is explicit in the definition. Any division requires a
coordination mechanism to re-integrate the divided work, and any supervision relationship is bounded
by span. So structure — roles plus a coordination mechanism plus a span budget — is entailed.

**Agent realization.** Named departments/roles, each with a profile (job description); a coordination
mechanism chosen deliberately (a supervisor agent = direct supervision; a shared context standard =
standardization of skills; a gate on outputs = standardization of outputs); and an explicit span
budget for each supervisor.

**Failure mode.** Exceed span and the supervisor "sees" its reports without the time to actually
check them — review degrades to rubber-stamping, and because review is where fraud and gaming are
caught (Organ 6), exceeding span silently disables the control system. Over-correct with too many
layers and you pay the **tall-structure tax**: latency and, for agents specifically, a token cost
that multiplies with each orchestration hop (multi-agent systems can consume on the order of 15× a
chat interaction's tokens — roughly 4× a single agent's). The load-bearing rule: **invest in information flow (Organ 5) to widen span
and stay flat; add exactly one middle layer, at a natural domain boundary, only when department
count genuinely exceeds the supervisor's effective span.** Hierarchy is the last resort, not the
first.

**Primitives.** `organization.yaml` declaring departments, supervisors, and span; a role/profile
template; an explicit choice of coordination mechanism per boundary.

---

### Organ 3 — Substrate / anatomy = **the harness**

**Human org.** A member of an organization can only contribute through the means available to it:
what it can perceive (its desk, its inbox, the reports it receives), what it can act on (its tools,
its authority), and what it can remember (its files, the institutional record it can reach). Change
the desk and you change the job. This is the organization's *physical plant and nervous system*.

**Derivation.** The definition says members have *bounded capabilities*. The bound is set by the
substrate: perception, action, memory. An organization with a structure but no substrate for its
members to perceive/act/remember is an org chart, not an organization.

**Agent realization — this is exactly harness engineering.** The harness is the set of means through
which an agent perceives (its context window, retrieval, tools that read), acts (tools that write,
permissions), and remembers (working, long-term, and procedural memory). The industry named this in
2026 ("Agent = Model + Harness"), and cognitive-architecture research (CoALA) and runtime work
(AIOS, which factors the substrate into scheduler / context / memory / tool / access managers) give
it structure. **Organizationally, the harness is Organ 3: the anatomy that turns a role on a chart
into a member that can actually do work.** *Context engineering* is a sub-part of this organ — the
curation of what enters perception each cycle.

**This organ is not ours to build — it already exists, and that is the whole point.** Claude Code,
Codex, and their kin *are* runnable harnesses: they supply perception, tools, memory, and the
control loop. The decomposition's job is to *place* those existing wheels, not re-forge them
(README's thesis, made literal). So a department in this template is not a bespoke process; it is an
**existing harness pointed at a working directory whose instruction file is this role's projected
profile.** The system delegates Organ 3 to the host harness and adds only a thin *projection* of the
neutral profile onto that harness's instruction-file convention. Reimplementing the harness would
contradict the thesis — see `docs/01-requirements.md` (R0, the harness-neutrality requirement) and
`docs/09-runtime.md` (delegate + project).

**Failure mode.** Give an agent authority (a role) without the substrate to exercise it well and you
get confident, well-formed, wrong work — the equivalent of an employee empowered to decide but
without access to the information the decision needs. Under-provision perception and the agent
hallucinates the missing context; under-provision memory and the organization cannot learn across
time (see Organ 5).

**Primitives.** Tool definitions and permission boundaries; a context-delivery mechanism (the
onboarding/briefing that runs *before* the agent acts); working/long-term/procedural memory stores.

---

### Organ 4 — Metabolism / cadence = **the loop**

**Human org.** An organization is not a snapshot; it *runs*. It has a cadence: when work is picked
up, when decisions are made, when the organization rests, when it reviews itself and corrects. A
firm with perfect structure and anatomy but no operating rhythm — no cycle of act, observe, decide,
repeat — does nothing. This is the organization's *circulatory system and circadian rhythm*.

**Derivation.** The definition says the organization *persists over time*. Persistence-in-action is
a metabolism: a repeated cycle. So a loop is entailed by the temporal clause exactly as the harness
is entailed by the capability clause.

**Agent realization — this is exactly loop engineering.** The loop is the control cycle
(perceive → decide → act → observe, the ReAct pattern at its root), plus the higher-order questions
loop engineering actually cares about: *when to continue and when to stop* (iteration caps, token
budgets, verifiable goals, no-progress detection), *how to run continuously and durably* (crash-safe
long-running execution, self-scheduling), and *who reruns whom* (the shift from "prompting a model"
to "writing loops that prompt models"). **Organizationally, the loop is Organ 4: the metabolism that
makes the anatomy do something over time.** It sits *above* the harness in the sense that it decides
how often and how long the harness is exercised — which is why some practitioners describe the
harness as containing the loop and others the reverse; from the organization's view they are simply
adjacent organs, anatomy and metabolism.

**Like the harness, the loop is delegated, not built.** Stop conditions, iteration caps, token
budgets, and self-scheduling are things the host harness and host environment already do. This
template *declares* the loop's intent — a role's cadence, its stop goal, its budget window — and the
host realizes it with its own scheduler and loop controls (`docs/09-runtime.md` §4). "24-hour
autonomous operation" is the host running the declared schedule unattended, with the operator's
approval queue holding charter/irreversible actions — not a daemon this repository ships.

**Failure mode.** A loop with no stop condition is the runaway autonomous agent that burns budget
going nowhere; a loop with no continuity is a system that forgets and restarts on every crash; a
loop that reruns a *bad* context just repeats a mistake faster ("a bad context is a bad context,
looped"). The metabolism inherits the health of every organ beneath it — which is the whole reason
top-down decomposition matters: tuning the loop cannot fix a defect in purpose, structure, or
substrate.

**Primitives.** The control-loop runtime; explicit stop conditions; durable/self-scheduling
execution; a supervision cadence (the 1-on-1 rhythm — see `template/SUPERVISOR.md`).

---

### Organ 5 — Information flow (coordination substrate)

**Human org.** A division of labor only re-integrates if information moves: between members
(horizontal), up and down supervision lines (vertical), and **across time** (institutional memory).
Two classic results govern this organ. **Conway's law**: a system's architecture inevitably mirrors
the communication structure of the organization that builds it — so the wiring of who-talks-to-whom
*becomes* the shape of the product. And McChrystal's **shared consciousness**: distributed autonomy
is only safe when paired with pervasive information sharing — to paraphrase the argument of *Team of
Teams*, empowered execution without shared consciousness is dangerous — because a member with
authority but not context will act confidently in the wrong direction.

**Derivation.** *Coordinated* is explicit in the definition. Coordination is information flow. And
because the organization persists over time, the flow must include a channel *across* time — memory
that outlives any single member or cycle.

**Agent realization.** Two coupled mechanisms: **context delivery** (the right prior knowledge —
nearby failures, live findings, verification state — pushed into an agent's context at the moment it
acts; this is onboarding, done every cycle) and a **shared institutional record** (an append-only
ledger that is the single source of truth, so learning from one agent/cycle reaches the next).

**Failure mode.** Two failures, both predicted by the classics. Silo the departments (they don't
share) and Conway's law guarantees a **siloed product**: discoveries never get digested, knowledge
fragments. Grant autonomy without shared consciousness and agents duplicate work, reach contradictory
conclusions, and drift. The design rule follows directly: **whenever you increase an agent's autonomy,
increase information sharing in the same proportion** — the two are one lever, not two.

**Primitives.** A context-pack mechanism run before every delegation; an append-only ledger as SSoT;
derived views regenerated from the ledger, never hand-edited.

---

### Organ 6 — Incentives & control (alignment enforcement)

**Human org.** Because members are imperfectly aligned (the definition says so), organizations run on
**internal control**. The cornerstone is **separation of duties**: authorization, custody of assets,
and recording must be held by *different* parties, so that no single member can both commit an
irregularity and conceal it. This is the Maker-Checker principle, non-negotiable in finance
(SOX/COSO). Its economic framing is the **principal-agent problem**: the principal cannot fully
observe the agent and measures a proxy; the agent, knowing its own context, can satisfy the proxy
without serving the principal (Goodhart again, from the control side).

**Derivation.** *Imperfect alignment* is explicit. Imperfect alignment plus valuable outputs entails
a control system that does not assume good behavior but makes misbehavior structurally hard.

**Agent realization.** Separate the agent that *discovers/implements* from the agent that
*verifies/admits* — the Maker is never its own Checker. Split the three incompatible duties across
agents: **authorization** (a gate or a human approves), **custody** (the data and the ledger are a
single protected source of truth), **recording** (results are written where they cannot be quietly
altered). Keep admission grounded in the true purpose (Organ 1) so the Checker is checking the right
thing.

**Failure mode.** Let the Maker check its own work and you have built the single point at which a
false positive can be "committed and concealed" — the discovery is stamped valid by the very agent
that has an interest in it passing. And note the coupling: **exceeding span (Organ 2) collapses this
organ**, because a supervisor without time to review rubber-stamps, which is separation-of-duties in
name only. Control is the organ most often quietly disabled by pressure elsewhere.

**Primitives.** A Maker/Checker matrix (who may not verify their own work); a machine-decided
admission gate; an append-only, tamper-evident record; independent adversarial review of positive
results.

---

### Organ 7 — Growth & adaptation (scaling without collapse)

**Human org.** Organizations grow through **stages**, and Larry Greiner's central finding is that
*each stage of growth ends in its own characteristic crisis*, which is the transition to the next
stage: creativity ends in a *leadership* crisis, direction ends in an *autonomy* crisis, and so on.
Growth is therefore not smooth scaling but a sequence of structural regime changes. Layered on top is
Burns & Stalker's **contingency** result: stable environments suit **mechanistic** organizations
(centralized, formalized, hierarchical), while uncertain, dynamic environments suit **organic** ones
(decentralized, low-formalization, laterally coordinated, innovation-friendly).

**Derivation.** Persistence over time, under a changing environment, means the organization that is
correct at one scale is wrong at the next. So the organization needs an organ for *changing its own
structure on schedule* — growth is not optional maintenance, it is a first-class organ.

**Agent realization.** A growth-stage model that tells you which organ/layer to add next and, equally,
which crisis you are about to hit (see `docs/02-growth-stages.md`). And a *two-regime* stance drawn
straight from Burns & Stalker, developed as its own law below: keep the exploratory front organic,
keep the control skeleton mechanistic.

**Failure mode.** Skip the diagnosis and you either under-build (stay a founder-supervised simple
structure past its span ceiling — the leadership crisis, unaddressed) or over-build (bolt on layers
you don't need — the tall-structure tax). Both are failures of the *growth* organ, not of any single
department.

**Primitives.** A stage self-diagnosis checklist; a rule for when to add a layer; the organic/
mechanistic split (next section).

---

## 3. The load-bearing law: organic exploration, mechanistic control

The single most important design rule that the decomposition produces — and the one that resolves
the strongest objection to this whole approach — is the **two-layer law**.

The objection is real and recent: there is evidence that **self-organizing agents outperform
designed structures** ([arXiv 2603.28990](https://arxiv.org/pdf/2603.28990)). Taken naively, this
says "don't design your organization at all." The decomposition shows why that reading is a
category error.

That result measures **task-solving efficiency** — the work of Organs that *explore*: generating
hypotheses, searching, discovering, choosing methods. On that layer, Burns & Stalker already predict
the finding: exploration lives in an uncertain, dynamic environment, which is exactly where
**organic** (self-organizing, low-formalization) structure wins. So on the exploratory front, *let it
self-organize.* Designing rigid roles there would be the bureaucratic-ossification failure — forcing
machine bureaucracy onto creative work and killing emergence.

But the result says **nothing about control** — Organ 6. Separation of duties, authorization,
anti-gaming, and safety are not task-solving; they are the guarantees that keep a relentless local
optimizer from satisfying a proxy while defrauding the purpose. Allowing *those* to self-organize is
not flexibility; it is dissolving the Maker-Checker line, i.e. **legalizing fraud**. An agent
permitted to self-approve will, by Goodhart, eventually do so.

So the law is:

> **Self-organize the exploration. Design only the control skeleton.**
> The exploratory front (mining, generation, method selection) is organic and may reorganize itself
> freely. The control layer (separation of duties, gates, admission, safety) is mechanistic,
> designed, and non-negotiable — it never self-organizes.

Read this way, the counter-evidence and organizational design are **not in conflict**. You are not
"designing the hierarchy." You are designing the *skeleton that keeps the system honest* and letting
everything else find its own shape. (Full treatment: `docs/03-organic-vs-mechanistic.md`.)

---

## 4. Placing harness and loop (and what a parts-first view misses)

To make the central claim concrete, here is the whole industry vocabulary relocated onto the organ
map:

| Named discipline (bottom-up) | Organ (top-down) | What it is, organizationally |
|---|---|---|
| Prompt / **context engineering** | part of Organ 3 (harness) | curating what a member perceives each cycle |
| **Harness engineering** | Organ 3 (substrate/anatomy) | the means to perceive, act, remember |
| **Loop engineering** | Organ 4 (metabolism/cadence) | the operating rhythm; when to act and stop |
| Runtime substrates (AIOS) | Organs 3+4 factored as an "OS" | scheduler (loop) + context/memory/tool/access (harness) |
| Multi-agent orchestration (roles, supervisors) | Organ 2 (structure) | division of labor + coordination mechanism |
| Principal-agent / eval-harness discipline | Organ 6 (control) | measuring and constraining misaligned agents |

The gaps are the point. A harness+loop practitioner has **no native concept** of Organ 1 grounding
(so they reward proxies and get gamed), Organ 2 span (so they add agents until review silently
fails), Organ 6 separation of duties (so Makers check themselves), or Organ 7 growth stages (so they
under- or over-build). These are not advanced topics; they are **load-bearing organs that a
parts-first vocabulary has no slot for.** That is the entire argument for decomposing from the
organization down.

---

## 5. Build order (the decomposition is also a sequence)

You do not build seven organs at once. The growth-stage model (Organ 7) implies the order, and it
matches how a startup actually becomes a company:

1. **Purpose (1)** — write the telos first; everything is checked against it.
2. **One member with a substrate (3) and a loop (4)** — a single agent that can perceive/act/remember
   and runs a cycle. (This is where harness+loop engineering alone gets you — a capable soloist.)
3. **Structure (2) + control (6)** — the moment there is more than one member, you need a division of
   labor *and* a Maker-Checker line. These arrive together; a second member without separation of
   duties is just a bigger single point of failure.
4. **Information flow (5)** — as members multiply, context delivery and a shared ledger become the
   thing that keeps them coherent (shared consciousness); autonomy and information scale together.
5. **Growth (7)** — once several departments exist, actively diagnose the stage and decide whether to
   widen span (invest in Organ 5) or add exactly one supervisory layer.

Note that harness+loop (step 2) is the *earliest* and most visible milestone — which, again, is why
the industry saw and named those organs first. The organization only *becomes* an organization at
step 3, when division of labor and control appear.

One qualification from the elastic model (`docs/05-elastic-organization.md`): under that model, this
sequence is an **activation order, not a construction order**. The full chart — every organ, every
latent department — is designed at founding (`template/FOUNDER.md`), and steps 2–5 describe which
parts of that latent organization come alive when. The ordering logic above still holds; what changes
is that "build next" becomes "activate next."

---

## 6. What this is, and what it is not

**It is** an organizing frame and a template: a decomposition that places the disciplines you already
use, names the organs you were missing, and gives an order to build them in. Its parts are drawn from
published, cited work (Mintzberg, Greiner, span of control, Conway, Goodhart/principal-agent,
separation of duties, Burns & Stalker, McChrystal) and from the current agent-engineering literature
(context/harness/loop engineering, AIOS, CoALA, ADAS/DGM). Applying the *classical* management side to
agent design is where the literature is currently thin — see `docs/sources.md` for the honest map of
who has done what.

**It is not** a silver bullet or a novelty claim. The decomposition is a *hypothesis about what an
agent organization needs*, and it is falsifiable: if a system missing an organ outperforms one that
has it, the frame is wrong about that organ. And the deepest caveat is the one Organ 1 insists on:
**the value of an organization is proven by what it produces, not by the elegance of its chart.**
This decomposition earns its keep only as scaffolding for an organization that actually delivers — it
is never a substitute for delivering.

---

### See also

- `template/organization.yaml` — the org as declarative data.
- `template/ROLE.md` — a member's job description (profile).
- `template/SUPERVISOR.md` — the supervision loop (the 1-on-1 that corrects profiles).
- `template/FOUNDER.md` — the founding process: RFP → full latent org, minimally activated.
- `template/constitution.yaml` — the human-written charter: decision tiers, night rules, invariants.
- `template/moves.yaml` — the legal-move catalog: every structural change the org may make.
- `docs/02-growth-stages.md` — which organ to add at each stage.
- `docs/03-organic-vs-mechanistic.md` — the two-layer law in full.
- `docs/04-failure-modes.md` — the failure modes, cataloged.
- `docs/05-elastic-organization.md` — the elastic model: design the full org at founding, run it elastically.
- `docs/06-lifecycle-operations.md` — founding to sunset: 24-hour operation, the approval queue, handover.
- `docs/07-doctrine-and-knowledge.md` — the knowledge organ: boundary spanners, role-scoped doctrine.
- `docs/08-context-economy.md` — need-to-know information flow: scoped context packs, budgets, commander's intent.
- `tools/org_lint.py` — the machine audit of `organization.yaml`, `constitution.yaml`, and `moves.yaml`.
- `docs/sources.md` — every citation, primary/secondary distinguished.
