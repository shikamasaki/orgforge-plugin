# THEORY — Articulating the Organization So AI Can Run It

> **Current product documentation:** [English](docs/en/README.md) ·
> [日本語](docs/ja/README.md). This file is the long-form intellectual record.

> **The claim of this repository, in one sentence:** the goal is to run the engineer's
> work autonomously around the clock with minimal human steering, and getting there
> **centers on putting the organization into words** — writing down, explicitly enough for
> an AI to act on, the things a human company runs on *without* writing them down: what we
> are trying to do, who knows what, who does what, what may be decided where, and which
> decisions the human at the top still makes.
>
> That is the whole idea. Everything else — harness, loop, context engineering, the yaml
> files, the lint — is downstream of it.

## 0. Why it centers on articulation

Consider what an LLM agent system actually needs to produce good work, and notice that
each need is something a human organization already solves — but solves **tacitly**:

- **Context / information flow.** An agent, like an employee, produces output aligned to
  the goal only if the *right information reaches it in the right amount*. Too little and
  it hallucinates the missing context; too much and the goal is buried. This is exactly
  what an organization's information flow is *for* — and in a human org it runs largely on
  culture, hallway conversation, and a manager's sense of "who needs to know this."
- **Division of labor.** Without a clear split of *who owns what deliverable to what
  standard*, the output is a coarse, essence-missing average — the same way an
  undifferentiated human team produces mush. Roles are how an org avoids that.
- **The metabolism (the loop).** The rhythm of picking up work, acting, checking, and
  correcting — an organization's operating cadence, which in a human firm is "just how we
  work," never spelled out.
- **The substrate (the harness).** What a member can perceive, act on, and remember — the
  desk, the tools, the files. Change the desk and you change the job.
- **Intent and the decision line.** The organization exists *for* something, and — this is
  the load-bearing part for a 24/7 AI system — **the human at the top decides the few
  essential things and delegates the thousand small ones.** A CEO does not adjudicate
  every judgment; the art of running a company is drawing the line between what the top
  decides and what the field is trusted to decide. Humans draw that line by feel.

Here is the pivot. **A human organization can leave all of this tacit** — carried in
experience, culture, and the air in the room — because humans read context, absorb norms,
and fill gaps on their own, *reliably enough*. **An AI can't be trusted to.** An AI does
fill unwritten gaps — that is exactly the problem: what it infers unbidden is unreliable and
un-auditable, and over a 24/7 unattended run those silent guesses compound into drift. So the
load-bearing tacit things have to become *explicit* — written down in a form the AI acts on,
so the system's behavior is pinned and checkable rather than left to inference. The goal has
to be stated, not felt. "Who needs to know this" has to be a rule, not an instinct. "This is
mine to decide, that goes up to the human" has to be a declared boundary, not a judgment.

**So designing an agent organization = articulating, in machine-actionable form, the tacit
organizational knowledge a human company runs on.** That is what this repository is: a
template for that articulation. `organization.yaml` articulates the division of labor;
`constitution.yaml` articulates the decision line (what the human decides vs. what is
delegated); `ROLE.md` articulates each member's job; the intent block articulates the goal;
the context packs articulate "who needs to know what." The lint checks that the
articulation is coherent. None of it is a new runtime — it is the organization, said out
loud so an AI can run it.

## 0.1 The engineering vocabulary, relocated

The industry named its concepts bottom-up — *prompt* (2023) → *context engineering*
(2024–25) → *harness engineering* (2026) → *loop engineering* (2026) — as tactical parts.
Each is real. But read against the pivot above, each is **a fragment of an organizational
act that a human firm performs tacitly**:

- *Context engineering* is articulating **information flow** — getting the right
  information, in the right amount, to the member who needs it.
- *Harness engineering* is articulating the **substrate** — what a member perceives, acts
  on, remembers.
- *Loop engineering* is articulating the **metabolism** — the operating cadence.

The parts are not wrong; they are *under-scoped*. Assembled bottom-up, they never force the
questions that decide whether the output is any good: is the goal actually propagated? is
the division of labor clear, or is the output coarse and essence-missing? **which decisions
does the human still make, and which run unattended?** Those are organizational questions,
and a parts-first vocabulary has no slot for them. Naming the whole — *the organization* —
and asking what must be *articulated* for an AI to run it puts every part in its place and
surfaces the ones the parts-first view left tacit.

> The "seven organs" that follow are **a checklist of the things a human organization runs
> on tacitly and an AI organization must have articulated** — distilled from how
> organizations succeed and fail, and matched to where multi-agent LLM systems actually
> break (information flow, role clarity, verification — exactly the tacit things). Read them
> as *what must be put into words*, not as a proof that the list is exhaustive.

---

## 1. The reference frame: what a human organization runs on tacitly

To know *what* to articulate, hold a working picture of an organization that is neutral between
humans and agents:

> An organization is a **coordinated division of labor directed at a purpose**, persisting over
> time, whose members have bounded capabilities and imperfect alignment with the purpose.

(This picture is compressed, not invented: it condenses Barnard (1938) — "a system of
consciously coordinated activities of two or more persons" — and the *bounded capabilities* clause
is Simon's bounded rationality.)

Read each clause not as a premise in a proof but as a **pointer to a tacit thing a human company
runs on that an AI organization must have written down**:

- **purpose** → the *goal/intent* that grounds every local decision, carried in a human firm as
  mission and culture — must be articulated (Organ 1).
- **division of labor** → who does what to what standard, and who coordinates whom — must be
  articulated (Organ 2).
- **members with bounded capabilities** → the *substrate* through which a member perceives, acts,
  and remembers, its anatomy — must be articulated and delegated to the host harness (Organ 3 =
  **the harness**).
- **persisting over time** → the *metabolism*: the operating cadence of acting, deciding, resting,
  and self-correcting — must be articulated and delegated to the host (Organ 4 = **the loop**).
- **coordinated** → the *information flow* between members and across time — must be articulated
  (Organ 5).
- **imperfect alignment** → the *decision line and control*, so members serve the purpose and not a
  convenient proxy for it — must be articulated (Organ 6).
- **persisting + growing** → how the org *changes its own shape* over time — must be articulated
  (Organ 7).

This is a checklist of the tacit organizational things an AI can only act on once they are made
explicit — not a proof that the list is complete. The rest of this document develops each: the
human-org meaning, why it must be
articulated, the agent-system realization, the failure mode when it is left tacit or malformed, and
the concrete primitives that implement it.

A note on the two organs the industry already named: **the harness (Organ 3) and the loop (Organ 4)
are the most *mechanical* organs** — the ones made of tools, runtimes, and control flow — so they
were the first to be seen, isolated, and given names by engineers building the substrate. That is
why they feel like the foundation. Organizationally they are not the foundation; they are the
anatomy and the metabolism of a body whose **structure, information flow, control, and growth** are
equally necessary and were simply harder to see from inside the tooling.

---

## 1b. The organization this template stands up: an IT business company

The definition in §1 is deliberately **neutral** — it holds for any organization, human or agent,
software or not. That neutrality is load-bearing: the seven organs are *derived* from it, so it must
not be narrowed. But orgforge does not stand up an arbitrary organization. It stands up a **specific
kind**: an **AI-native IT business company** — an organization whose purpose is to *decide what
software to build as a business, build it, ship it, operate it, and keep both the system and itself
growing*. This section does not add an eighth organ; it **fills and specializes** the organs §1
already derived, the way the human-org theory is itself re-parameterized for agents — now
re-parameterized one level down, for a software company.

Concretely, being an IT business company is the **content** of five organs:

- **The purpose (Organ 1) is a business telos, not an abstract goal.** The company exists to serve a
  customer: it decides *what to build* from a market intent — a customer, an RFP, a priority ranking —
  and is answerable for delivery and economics, not for volume of output. The purpose slot is filled
  with "ship valuable software to whoever the org is a vendor to," and the admission standard is
  grounded in that (docs/01 already speaks *vendor / client / delivery / economics*; this is where it
  comes from).

- **The structure (Organ 2) owns SDLC phases, not just deliverables.** A software company's division
  of labor runs the work through a **lifecycle**: requirements → design → implement → test → integrate → deploy →
  operate. Roles own *phases* as well as slices, and the coordination mechanism re-integrates a
  *pipeline*, not just parallel outputs. **The SDLC is a mold the work is forced through** — the phase
  order is a shape, not a suggestion (docs/11).

- **The loop (Organ 4) is the SDLC cadence plus continuous delivery.** The metabolism of a software
  company is not generic experiment-cycling; it is *build → integrate → test → deploy → operate*,
  running continuously, keeping the trunk always-shippable, with **CI/CD (GitHub Actions) as the
  deploy phase's spine** — delegated to the host under R0 exactly as scheduling is (docs/08, docs/11).

- **The decision line (Organ 6) gates phases, not only admissions.** The `requires_prior` mechanism
  that already stops a maker from admitting its own work generalizes to the **phase gate**: design may
  not start before requirements are signed off, deploy may not fire before test passes. The same
  doctrine + lint + routing that enforces separation-of-duties enforces the **non-skippable phase
  chain** (docs/03, docs/09, docs/11). A running product also carries a **reliability/error budget**
  that *bounds deploy velocity* — the SRE governor, a decision-line instrument (docs/05 §reliability-budget).

- **Growth (Organ 7) grows the system and the org together.** A software company does not only reshape
  its own chart; it grows the *system it is building* alongside itself, and navigates by **DORA-style
  metrics** (deploy frequency, lead time, change-fail rate, MTTR) to find the **moving bottleneck**
  (Theory of Constraints) and reshape toward it. "The system and the organization grow together" is
  the through-line: the org's structure, its doctrine, and the product's architecture co-evolve
  (docs/06, docs/05 §DORA, docs/12 §5.5).

One cross-cutting claim frames all five, and it is why the *forced* mold matters: **AI is an
amplifier.** It magnifies whatever process it is dropped into — good process and bad process
equally — and, by accelerating the upstream, it *degrades stability* and shifts the binding
constraint **downstream** to review, test, and deploy (DORA 2024–2025). An organization that lets an
amplifier run without a mold does not go faster; it produces more, faster, of whatever it was already
producing — including defects — and blows its reliability budget at the newly-moved bottleneck. So
the company's shape is not enforced to slow it down; it is enforced because **an amplifier without a
mold amplifies the wrong things**. The enforcement is the standing lesson of this repo: *doctrine
promotes* the SDLC type (what good practice now is, loaded every cycle), and *lint/hooks enforce* the
few places a phase must not be skipped — never forced delegation, always a checkable tooth.

And the reason to force the type, beyond amplifier-discipline, is **reproducibility**: the same org
spec and RFP must yield the same *process, contracts, gates, and verification* no matter who founds
the company or when — and the *repositories* the company builds must be reproducible for anyone who
clones them (one command, same result). The generated code may vary — an LLM is non-deterministic —
but a mold is a shape that makes many pourings come out the same, so everything *around* the code
converges. This is the two-level reproducibility docs/11 makes concrete: Level 1, the org itself;
Level 2, the repos it ships.

The rest of this document develops the seven organs in their neutral form. Read §1b as the lens that
says *which* organization these organs are being articulated for: an IT business company, whose
purpose is software delivery, whose metabolism is the SDLC, and which grows its system and itself
together.

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

**What must be articulated.** In a human firm the goal lives in the mission and the culture — people
carry it and check their local choices against it without being told. An AI carries nothing it is not
given, so **the goal itself must be stated, not felt**, and propagated into every member's context.
This is the first of the tacit things to write down: without an explicit, propagated telos, a
division of labor has nothing to divide *toward*, and every other organ is unanchored.

**Agent realization.** A single, explicitly stated objective, delivered into every agent's context,
against which any proposed action or admission can be tested. Not a metric — a *purpose*, with the
metric held one level below it as an instrument that can be wrong.

**Failure mode if left tacit or malformed.** This is the deepest failure in the whole system, because
it propagates. A metric is a **lossy compression of the goal** — and optimizing a lossy proxy fails in
more ways than the familiar gaming story admits. Manheim & Garrabrant distinguish four variants of
**Goodhart's law**, and only one — *adversarial* Goodhart — is the "reward the number and people game
it" case that the fix "keep the proxy out of the reward" defends against. The other three
(*regressional*, *extremal*, *causal*) occur with **no adversary and no proxy-reward at all**: they
are statistical consequences of optimizing any lossy stand-in for the true goal. So
the deeper point is not merely anti-gaming; it is that the articulation must state the **purpose**,
because any metric substituted for it silently diverges under optimization pressure — and agents,
relentless local optimizers with full knowledge of their own context, surface that divergence faster
than any human employee. The defense is architectural: **ground admission in the true purpose, treat
every metric as an instrument that can be wrong, keep quantitative proxies out of the reward** (this
blunts the adversarial variant specifically) **and build measurement systems that can tell gaming and
statistical drift apart from genuine success** (nulls, placebos, forward tests). "More output" must
never be the objective if the objective is "value."

**Primitives.** A purpose statement in every context pack; an admission standard grounded in the
purpose (not in volume); measurement instruments designed to be gaming-resistant.

---

### Organ 2 — Structure (division of labor + coordination)

**Human org.** Who owns which deliverable, and how the divided work re-integrates, is one of the
things a human company mostly carries tacitly — org charts capture a fraction; the rest lives in
"who actually does what." Henry Mintzberg's useful observation is that an organization's *type* is
determined by its dominant **coordination mechanism**: direct supervision (simple structure),
standardization of work (machine bureaucracy), standardization of skills (professional bureaucracy),
standardization of outputs (divisionalized form), or mutual adjustment (adhocracy). A second lever is
**span of control** — how many subordinates one supervisor can *effectively* oversee. Classical span
*numbers* (Graicunas ~4–5, Urwick 5, "15–20 in high-communication settings") are **discredited as
universals**: CEO spans widened secularly over the last decades, optimal span is contingent on task
standardization and interdependence, and "flat" is not "decentralized." What
survives, and what actually transfers to agents, is not a number but a constraint: a supervisor's
**verification bandwidth** — how much it can meaningfully review — is finite, and structure has to
respect that bound.

**What must be articulated.** *Division of labor* is exactly the thing a human team leaves implicit
and an AI cannot. This is one of the tacit things that must be written down: named roles with owned
deliverables, a coordination mechanism to re-integrate the divided work, and — for forkable agents,
where headcount is free — an honest account of how much any one supervisor can actually verify.

**Agent realization.** Named departments/roles, each with a profile (job description); a coordination
mechanism chosen deliberately (a supervisor agent = direct supervision; a shared context standard =
standardization of skills; a gate on outputs = standardization of outputs); and, per supervisor, an
explicit budget expressed as **verification bandwidth / requisite variety** — how many reports it can
review to standard — rather than a transplanted human span number.

**Failure mode.** Overload a supervisor's verification bandwidth and it "sees" its reports without the
time to actually check them — review degrades to rubber-stamping, and because review is where fraud
and gaming are caught (Organ 6), overload silently disables the control system. Over-correct with too
many layers and you pay the **tall-structure tax**: latency and, for agents specifically, a token cost
that multiplies with each orchestration hop (Anthropic's production multi-agent report puts the order
of magnitude around 15× a chat interaction's tokens — a rough magnitude, not a precise coefficient,
and heavily workload-dependent). The load-bearing rule is a heuristic, not a law: **invest in
information flow (Organ 5) to widen effective span and stay flat; add a middle layer, at a natural
domain boundary, only when the count of things to coordinate genuinely exceeds what one supervisor can
verify.** Hierarchy is the last resort, not the first.

**Primitives.** `organization.yaml` declaring departments, supervisors, and a verification-bandwidth
budget; a role/profile template; an explicit choice of coordination mechanism per boundary.

---

### Organ 3 — Substrate / anatomy = **the harness**

**Human org.** A member of an organization can only contribute through the means available to it:
what it can perceive (its desk, its inbox, the reports it receives), what it can act on (its tools,
its authority), and what it can remember (its files, the institutional record it can reach). Change
the desk and you change the job. This is the organization's *physical plant and nervous system*.

**What must be articulated (and delegated).** A member's bound is set by its substrate: perception,
action, memory. A human company has this tacitly — the desk, the tools, the reach into the record —
and an organization with a structure but no substrate for its members to perceive/act/remember is an
org chart, not an organization. So the substrate is one of the tacit things that must be made
explicit — but it is also the organ least worth building, because the substrate a human org tacitly
provides is exactly what an existing coding-agent harness already ships. The articulation here is
mostly a matter of *pointing at* the host and stating what perception/tools/memory each role needs;
the realization is delegated (see docs/08).

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
`docs/08-runtime.md` (delegate + project).

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

**What must be articulated (and delegated).** Persistence-in-action is a metabolism: a repeated cycle.
In a human firm the cadence is "just how we work," never spelled out — and, like the substrate, it is
a tacit thing that must be made explicit *and* is largely provided by the host. The articulation
states the intent (a role's cadence, its stop goal, its budget window); the host harness and host
environment realize it with their own scheduler and loop controls. So the loop is one of the tacit
things that must be written down, but — like the harness — it is articulated-and-delegated, not built.

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
host realizes it with its own scheduler and loop controls (`docs/08-runtime.md` §4). "24-hour
autonomous operation" is the host running the declared schedule unattended, with the operator's
approval queue holding charter/irreversible actions — not a daemon this repository ships.

**Failure mode.** A loop with no stop condition is the runaway autonomous agent that burns budget
going nowhere; a loop with no continuity is a system that forgets and restarts on every crash; a
loop that reruns a *bad* context just repeats a mistake faster ("a bad context is a bad context,
looped"). The metabolism inherits the health of every other organ: tuning the loop cannot fix a
defect in purpose, structure, or substrate — which is why articulating those first matters, and why
the loop, though the most visible organ, is not the one that decides whether the output is any good.

**Primitives.** The control-loop runtime; explicit stop conditions; durable/self-scheduling
execution; a supervision cadence (the 1-on-1 rhythm — see `template/SUPERVISOR.md`).

---

### Organ 5 — Information flow (coordination substrate)

**Human org.** This is **the central articulation** — getting the right information, in the right
amount, to the member who needs it. A human company does this almost entirely tacitly: hallway
conversation, a shared sense of what's going on, and a manager's instinct for who-needs-to-know. It is
the single largest thing a human org leaves un-written, and therefore the largest thing an AI org must
make explicit. A division of labor only re-integrates if information moves: between members
(horizontal), up and down supervision lines (vertical), and **across time** (institutional memory).
Two classic results govern this organ. **Conway's law**: a system's architecture inevitably mirrors
the communication structure of the organization that builds it — so the wiring of who-talks-to-whom
you *write down* simply *becomes* the shape of the product (which is exactly why the articulation and
the dataflow graph it renders to are one object seen twice, not rivals). And McChrystal's
**shared consciousness**: distributed autonomy is only safe when paired with pervasive information
sharing — empowered execution without shared consciousness is dangerous, because a member with
authority but not context will act confidently in the wrong direction. (*Team of Teams* is an n=1
practitioner account, used here as illustration, not peer-reviewed evidence.)

**Why this is the strongest-supported organ.** The empirical evidence points straight here. The MASFT
study of why multi-agent LLM systems fail finds **~40% of failures are inter-agent misalignment** —
information that did not reach the member who needed it, contradictory conclusions, dropped context —
which is precisely this organ left tacit. Anthropic's production system reports token usage (i.e.
*what information reached each agent in what amount*) explains ~80% of performance variance. Of all the
tacit things that must be articulated, this is the one the data says matters most.

**What must be articulated.** *Coordination is information flow*, and because the organization persists
over time the flow must include a channel *across* time — memory that outlives any single member or
cycle. In a human firm both run on the air in the room; for an AI both must be written as explicit
mechanism: who receives what, in what amount, at what moment.

**Agent realization.** Two coupled mechanisms: **context delivery** (the right prior knowledge —
nearby failures, live findings, verification state — pushed into an agent's context at the moment it
acts; this is onboarding, done every cycle) and a **shared institutional record** (an append-only
ledger that is the **audit/enforcement record** — the SSoT is code + the domain model (conventions + the org spec) — so learning from one agent/cycle reaches the next).

**Failure mode.** Two failures, both predicted by the classics and now measured by MASFT. Silo the
departments (they don't share) and Conway's law guarantees a **siloed product**: discoveries never get
digested, knowledge fragments. Grant autonomy without shared consciousness and agents duplicate work,
reach contradictory conclusions, and drift — the ~40% inter-agent-misalignment failure surface made
concrete. The design rule follows directly: **whenever you increase an agent's autonomy, increase
information sharing in the same proportion** — the two are one lever, not two.

**Primitives.** A context-pack mechanism run before every delegation; an append-only ledger as the
**audit/enforcement record** (the SSoT is code + the domain model — conventions + the org spec);
derived views regenerated from the ledger, never hand-edited.

---

### Organ 6 — The decision line & control (alignment, calibrated to risk)

**Human org.** The load-bearing tacit thing here is **the decision line**: which calls the top makes,
and which it delegates. The art of running a company is drawing that line — a CEO who adjudicated
every judgment would be the bottleneck; one who delegated everything would lose the few decisions that
matter. Humans draw it by feel. For a 24/7 AI system this is the point of the whole organ: **articulate
the decision line so the human is freed to decide only the essential things and everything else runs
delegated and unattended.** Alongside it sits the maker/checker split — separating the party that
*produces/authorizes/records* from the party that *verifies* — which classical internal control calls
**separation of duties (SoD)**. But SoD is emphatically **not a universal non-negotiable**, and every
control theory this template cites contradicts a blanket rule:

- **COSO** (the actual internal-control framework) treats SoD as **one control activity inside one of
  five components**, *selected by risk assessment* and explicitly **substitutable by compensating
  controls** (supervisory sign-off, independent review, dual authorization above a threshold) where
  full segregation isn't cost-effective. Control is risk-*proportionate*, not uniform.
- **Agency theory** (Jensen–Meckling; Eisenhardt) centers **incentive design** and the
  behavior-vs-outcome contract trade-off — *not* "add a monitor." Monitoring is one lever that *raises*
  cost; when outcomes are measurable, outcome-based contracting is often cheaper and better.
- The economic framing is the **principal-agent problem**: the principal cannot fully observe the agent
  and measures a proxy; the agent, knowing its own context, can satisfy the proxy without serving the
  principal (Goodhart again, from the control side) — which is an argument for *calibrated* control and
  good incentives, not for a checker on every action.

**What must be articulated.** Two things a human org leaves to judgment must become declared boundaries:
(1) the **decision line** — "this is mine to decide, that goes up to the human" — written as tiers
(delegated / charter-hold / irreversible-hold), so the system knows what to run unattended and what to
queue for a human; and (2) the **maker/checker split**, calibrated to the stakes.

**Agent realization.** Separate the agent that *discovers/implements* from the agent that
*verifies/admits* — **but proportioned to risk**: full maker/checker (an independent adversarial
Checker, with authorization, custody, and recording held by different parties) for **high-stakes,
hard-to-verify, or irreversible** work; a **compensating control** (a single reviewer, a forward test,
an outcome contract) for **cheap, reversible, easily-verified** work — not the full apparatus on
everything. Keep admission grounded in the true purpose (Organ 1) so the Checker is checking the right
thing. The template's two-tier threat model (docs/01 §5) is this calibration, and it is the governing
principle of this organ: control is proportioned to risk, never applied uniformly.

**Failure mode.** Two symmetric failures. *Under-control:* let the Maker check its own high-stakes work
and you have built the single point at which a false positive can be "committed and concealed" — the
discovery stamped valid by the very agent with an interest in it passing. *Over-control:* bolt full
maker/checker onto cheap reversible work and you pay for it — the founding rehearsal (demos/S1-founding-rehearsal) spent
four agents (~15× tokens, a rough magnitude) on a slugify function, and the gate's admission was itself
wrong: over-governance that still failed. And note the coupling: **overloading a supervisor's
verification bandwidth (Organ 2) collapses whatever control you did calibrate**, because a supervisor
without time to review rubber-stamps. Control is the organ most often quietly disabled by pressure
elsewhere — and most often misapplied uniformly where it should be calibrated.

**Primitives.** A decision-line declaration (`constitution.yaml`'s delegated / charter / irreversible
tiers); a risk-calibrated Maker/Checker matrix (who may not verify their own work, and where a
compensating control substitutes); a machine-decided admission gate; an append-only, tamper-evident
record; independent adversarial review reserved for the high-risk results that warrant it.

---

### Organ 7 — Growth & adaptation (scaling without collapse)

**Human org.** An organization that is correct at one size is wrong at the next, so a company changes
its own shape over time — and *how it will change* is one more tacit thing a human firm handles by
judgment. Larry Greiner's growth-crisis sequence (creativity → leadership crisis → direction → autonomy
crisis, and so on) is a useful **lens** for anticipating which structural strain comes next — but it is
a lens, not a law and not a finding to transplant intact: contingency theory is contested (equifinality;
modest fit–performance evidence), Greiner's crisis stages are a different theory from Mintzberg's
configurations (grafting one onto the other is a category error), and both are re-parameterized heavily
once the org is made of forkable agents whose reorg is a **cheap commit** rather than a costly,
career-laden restructuring.

**What must be articulated.** How the org changes shape — which move is legal when, and what triggers
it — is the thing to write down here. In a human firm reorganization is slow, political, and mostly
tacit; for agents it is a cheap, reversible edit to the declared structure, so it can and should be made
an explicit, catalogued capability rather than left to feel.

**Agent realization.** A growth-stage model used as a diagnostic lens for which strain is coming and
which organ/layer might answer it (see `docs/02-growth-stages.md`), and a legal-move catalog so reorg is
an explicit, reversible commit. Alongside it, a *two-regime* stance — keep the exploratory front organic,
keep the control skeleton designed — developed as its own law below (sourced, per docs/03, from
Lawrence & Lorsch differentiation–integration and ambidexterity, **not** Burns & Stalker).

**Failure mode.** Skip the diagnosis and you either under-build (stay a founder-supervised simple
structure past the point one supervisor can verify) or over-build (bolt on layers you don't need — the
tall-structure tax). Because agent reorg is cheap, the more common real failure is *not committing to a
shape at all* — endlessly reshuffling instead of running. Both are failures of the *growth* organ, not
of any single department.

**Primitives.** A stage self-diagnosis checklist used as a lens; a rule of thumb for when to add a
layer; a legal-move catalog for structural change; the organic/designed-control split (next section).

---

## 3. The two-layer split: self-organize exploration, design the control skeleton

One articulation choice recurs strongly enough to state on its own — and it resolves the strongest
objection to this whole approach — the **two-layer split**.

The objection is real and recent: there is evidence that **self-organizing agents outperform
designed structures** ([arXiv 2603.28990](https://arxiv.org/pdf/2603.28990)). Taken naively, this
says "don't articulate your organization at all." But note what that same counter-paper actually
found: a **hybrid** protocol won — self-organized exploration over a designed skeleton — which mildly
*strengthens* the two-layer stance rather than refuting it.

That result measures **task-solving efficiency** — the work of exploring: generating hypotheses,
searching, discovering, choosing methods. On that layer, letting structure emerge tends to win:
exploration lives in an uncertain, dynamic environment, and designing rigid roles there would force
machine bureaucracy onto creative work and kill emergence. So on the exploratory front, *let it
self-organize* — leave that part of the division of labor deliberately under-articulated.

But the result says **nothing about control** — Organ 6. The maker/checker line, authorization,
anti-gaming, and safety are not task-solving; they are the guarantees that keep a relentless local
optimizer from satisfying a proxy while defrauding the purpose. Allowing *those* to self-organize is
not flexibility; it is dissolving the maker/checker line where it is warranted, i.e. **legalizing
fraud** on exactly the high-stakes work that needs it. An agent permitted to self-approve high-stakes
work will, by Goodhart, eventually do so.

So the split is:

> **Self-organize the exploration. Articulate and design the control skeleton.**
> The exploratory front (mining, generation, method selection) is organic and may reorganize itself
> freely. The control layer (the decision line, risk-calibrated maker/checker, gates, admission,
> safety) is designed and articulated — it never self-organizes.

The citation for "different subunits, different regimes" is **Lawrence & Lorsch** (1967)
differentiation–integration, **not** Burns & Stalker (whose actual lesson is a warning about *botched*
hybridization — see docs/03). And L&L's teaching carries a cost that is easy to miss:
**integration cost rises with differentiation** — separating an organic exploration regime
from a designed control regime demands *proportional* investment in explicit integrating machinery
(integrator roles, shared cadences, liaison), which is itself part of the information-flow articulation
(Organ 5). Read this way, the counter-evidence and organizational articulation are **not in conflict**:
you are not "designing the hierarchy," you are articulating the *skeleton that keeps the system honest*,
paying the integration cost, and letting everything else find its own shape. (Full treatment:
`docs/03-organic-vs-mechanistic.md`.)

---

## 4. Placing harness and loop (and what a parts-first view never forces you to articulate)

To make the central claim concrete, here is the whole industry vocabulary relocated onto the organ
map. The point of the map is not that a derivation proves the list complete — it doesn't —
but that a bottom-up, parts-first vocabulary has **no slot** that forces you to write down the tacit
organizational things in the right-hand column, and those are the ones that decide whether the output
is any good:

| Named discipline (bottom-up) | Organ (top-down) | What it is, organizationally |
|---|---|---|
| Prompt / **context engineering** | part of Organ 3 (harness) | curating what a member perceives each cycle |
| **Harness engineering** | Organ 3 (substrate/anatomy) | the means to perceive, act, remember |
| **Loop engineering** | Organ 4 (metabolism/cadence) | the operating rhythm; when to act and stop |
| Runtime substrates (AIOS) | Organs 3+4 factored as an "OS" | scheduler (loop) + context/memory/tool/access (harness) |
| Multi-agent orchestration (roles, supervisors) | Organ 2 (structure) | division of labor + coordination mechanism |
| Principal-agent / eval-harness discipline | Organ 6 (control) | measuring and constraining misaligned agents |

The gaps are the point. A harness+loop practitioner is never *forced to articulate* Organ 1 grounding
(so they reward proxies and get gamed — and, more than gamed, silently drifted, per the lossy-proxy
argument in Organ 1), Organ 2's verification-bandwidth bound (so they add agents until review silently
fails), Organ 5's information flow (the ~40% MASFT failure surface), Organ 6's risk-calibrated decision
line and maker/checker (so Makers check high-stakes work themselves), or Organ 7's shape-change (so
they under- or over-build). These are not advanced topics; they are **the tacit organizational things a
parts-first vocabulary gives you no reason to write down.** That is the entire argument for articulating
from the organization down — not that the seven are a proven-complete derivation, but that naming the
whole surfaces the tacit things the parts leave un-said.

---

## 5. Articulation order (a rough sequence, not a proof)

You do not articulate everything at once. A natural order — which matches how a startup actually
becomes a company — is:

1. **Purpose (1)** — state the goal first; everything is checked against it.
2. **One member with a substrate (3) and a loop (4)** — a single agent that can perceive/act/remember
   and runs a cycle. (This is where harness+loop engineering alone gets you — a capable soloist, both
   organs delegated to the host harness.)
3. **Structure (2) + control (6)** — the moment there is more than one member, articulate the division
   of labor *and* the decision line / maker-checker split (risk-calibrated). These arrive together; a
   second member without an articulated control line is just a bigger single point of failure.
4. **Information flow (5)** — as members multiply, context delivery and a shared ledger become the
   thing that keeps them coherent (shared consciousness); autonomy and information scale together. This
   is the organ the evidence says matters most, so it is worth over-investing in early.
5. **Growth (7)** — once several departments exist, use the stage lens to decide whether to widen
   effective span (invest in Organ 5) or add a supervisory layer.

Note that harness+loop (step 2) is the *earliest* and most visible milestone — which, again, is why
the industry saw and named those organs first. The set only *reads as an organization* at step 3, when
division of labor and the decision line are articulated.

One qualification from the elastic model (`docs/02-elastic-organization.md`): under that model, this
sequence is an **activation order, not an articulation order**. The full chart — every organ, every
latent department — is articulated at founding (`template/FOUNDER.md`), and steps 2–5 describe which
parts of that latent organization come alive when. The ordering logic above still holds; what changes
is that "articulate next" becomes "activate next."

---

## 6. What this is, and what it is not

**It is** a way to articulate the tacit organizational knowledge an autonomous AI system needs, and a
template for writing it down: a frame that places the disciplines you already use, names the tacit
things a parts-first vocabulary left un-said, and gives a rough order to articulate them in. Its
vocabulary and failure modes are drawn from published, cited work (Mintzberg, Conway, Goodhart's four
variants, agency/principal-agent, COSO/separation of duties, Lawrence & Lorsch, McChrystal) — used as
**re-parameterized heuristics and failure modes for agents, not as law**; the human numbers (span
counts) and growth-sequences do not transfer intact. The current agent-engineering literature
(context/harness/loop engineering, AIOS, CoALA) supplies the substrate side, and MASFT supplies the
empirical backing that coordination and verification are where these systems actually fail. See
`docs/sources.md` for the research map.

**It is not** a complete top-down derivation, and it does not claim to be: there is no completeness
theorem behind the seven organs. The durable core is not a derivation but **the articulation itself** —
the operational claim that, in a world where AI runs the
work around the clock with the human deciding only the essential things, designing the system reduces
to putting the organization into words an AI can act on, and multi-agent systems fail precisely where
that articulation is missing or coarse (unclear roles, information that didn't arrive, work no one
verified). That claim is falsifiable and empirically supported. And the deepest caveat is the one Organ
1 insists on: **the value of an organization is proven by what it produces, not by the elegance of its
chart.** This frame earns its keep only as scaffolding for an organization that actually delivers — it
is never a substitute for delivering.

---

### See also

- `docs/01-requirements.md` — the product spec: actors, jobs, success criteria, the threat model, R0/R−1.
- `template/organization.yaml` — the division of labor and information flow, articulated as data.
- `template/ROLE.md` — a member's job description (profile).
- `template/SUPERVISOR.md` — the supervision loop (the 1-on-1 that corrects profiles).
- `template/FOUNDER.md` — the founding process: RFP → full latent org, minimally activated.
- `template/constitution.yaml` — the decision line, articulated: tiers, night rules, invariants.
- `template/moves.yaml` — the legal-move catalog: every structural change the org may make.
- `template/ledger-schema.yaml` — the shared record: event classes, derived views, pack assembly.
- `template/sensors.yaml` — the crisis signals, as measurements.
- `template/PROJECTION.md` + `template/role-settings.yaml` — rendering the articulated org onto a host harness.
- `docs/02-growth-stages.md` — which organ to add at each stage.
- `docs/03-organic-vs-mechanistic.md` — the two-layer law in full.
- `docs/04-failure-modes.md` — the failure modes, cataloged.
- `docs/02-elastic-organization.md` — the elastic model: design the full org at founding, run it elastically.
- `docs/05-lifecycle-operations.md` — founding to sunset: 24-hour operation, the approval queue, handover.
- `docs/06-doctrine-and-knowledge.md` — the knowledge organ: boundary spanners, role-scoped doctrine.
- `docs/07-context-economy.md` — need-to-know information flow: scoped context packs, budgets, commander's intent.
- `docs/08-runtime.md` — execution: delegate the loop to the host, project the profile.
- `demos/S1-founding-rehearsal-founding-rehearsal.md` — the first end-to-end run (S1), with artifacts.
- `tools/org_lint.py` — the machine audit: cross-validates all five data files (+ optional role-settings).
- `docs/sources.md` — every citation, primary/secondary distinguished.
