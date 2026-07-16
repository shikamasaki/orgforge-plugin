# Growth-Stage Playbook

*How to scale an agent organization the way a company scales — and which organ or
layer to add at each stage.*

This document maps a small set of well-established organizational findings onto the
problem of growing an agent org (a system of collaborating AI agents). The goal is
practical: help you diagnose **what stage you are in** and choose **the next single
move**, rather than adding structure by reflex.

Nothing here is presented as a proven law of agent systems. These are human-organization
models used as *lenses*. Treat the mapping as a hypothesis to check against your own
system, not a template to obey.

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
assigns work, and integrates results. This maps to Greiner's *creativity* phase — output
grows through informal, hands-on direction.

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

---

## 5. Sources

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

*These are human-organization models applied as lenses to agent orgs. The mappings are
working hypotheses to test against your own system, not established results.*
