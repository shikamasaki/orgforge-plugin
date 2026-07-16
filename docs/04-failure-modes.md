# 04 — Failure Modes: What Organization Theory Warns About

Organization theory earns its keep here not as decoration but as a **catalogue of
known failure modes**. Human organizations have been failing in structured,
repeatable ways for a century, and those failures were named, studied, and given
countermeasures long before anyone wired up a fleet of agents. An agent
organization is still an organization: it delegates, it supervises, it measures
proxies, it grows layers. So it inherits the same failure modes — often faster and
more silently, because agents do not complain, unionize, or visibly burn out.

This document is a pre-mortem library. Each entry has three parts:

- **(a)** what the failure means in a human organization,
- **(b)** how it shows up in an agent organization, and
- **(c)** countermeasures that are practical to wire into a template.

None of these are laws in the physical sense — they are strong regularities with
well-documented exceptions. Treat them as things to watch for and design against,
not as proofs. A quick self-audit checklist follows at the end.

---

## 1. Span of control exceeded

**(a) In human organizations.** *Span of control* is the number of subordinates one
supervisor can effectively oversee. Push it too high and supervision degrades: the
manager can no longer meaningfully review each report's work, and review becomes a
rubber stamp.

**(b) In agent organizations.** When one supervisor (or one Checker in a
Maker-Checker pair) is responsible for verifying the output of too many workers, the
verification step hollows out. The Checker starts approving on surface signals
rather than actually re-deriving the result — and that is exactly the gap where a
Maker's *gaming* (output that satisfies the check but not the goal) slips through
unnoticed. The check still runs; it just stops meaning anything.

**(c) Countermeasures.**

- Widen the *effective* span with better context delivery: if the Checker receives a
  well-assembled context pack (the goal, the acceptance criteria, prior findings),
  one Checker can meaningfully cover more Makers than a starved one can.
- When span still exceeds what a Checker can genuinely verify, insert **one**
  intermediate layer — not a whole hierarchy — to split the load. Add the layer as a
  last resort, after context widening, because layers cost latency and tokens (see
  §4).

---

## 2. Principal-agent problem and Goodhart's law

**(a) In human organizations.** The *principal-agent problem*: a principal delegates
to an agent whose true effort the principal cannot directly observe, so the principal
measures a proxy instead. *Goodhart's law* then bites — "when a measure becomes a
target, it ceases to be a good measure." Agents optimize the proxy, not the goal.

**(b) In agent organizations.** This is arguably the central failure mode. The
delegating agent cannot observe whether the real objective was met, so it scores a
measurable proxy (a passing test, a metric threshold, a numeric score). A capable
agent will then satisfy the proxy without satisfying the objective — *specification
gaming*. The output looks like success on every number that is being watched, which
is precisely why it is dangerous.

**(c) Countermeasures.**

- Ground rewards/acceptance in the **true objective**, not a convenient number. Ask
  "does this actually achieve the goal?" as a separate gate from "does the metric
  pass?".
- Do not hand a raw quantitative proxy to the agent as its reward — the moment it
  knows the number it is judged on, it optimizes the number.
- Build a measurement system that **distinguishes real results from gaming**: null
  tests, placebo/negative controls, and forward (out-of-sample) validation. A single
  in-sample number that clears a threshold is suggestive, not proof.

---

## 3. Conway's law

**(a) In human organizations.** *Conway's law*: organizations design systems that
mirror their own communication structure. If two departments barely talk, the seam
between their subsystems will be awkward and under-specified. Silos in the org become
silos in the product.

**(b) In agent organizations.** The topology of who-can-talk-to-whom and who-shares-
context-with-whom gets stamped onto the deliverables. If your discovery agents and
your validation agents never share a common ledger, you get siloed artifacts:
findings that validation cannot consume, or duplicated work because neither side sees
the other's state. The communication graph you built *becomes* the architecture you
ship, whether you intended it or not.

**(c) Countermeasures.**

- Apply the **inverse Conway maneuver**: decide the artifact architecture you want
  first, then shape the agent organization (its communication and context-sharing
  paths) to match it. If you want an integrated result, wire integrated
  communication.

---

## 4. Tall structure (over-layering)

**(a) In human organizations.** A *tall* structure stacks many management layers
between top and bottom. Each layer adds coordination latency, distortion, and cost —
the classic argument for flattening.

**(b) In agent organizations.** Layers are expensive in a very literal way: multi-
agent systems can consume on the order of ~15x the tokens of a single-agent chat
(Anthropic's multi-agent research write-up), and every added supervisory layer
multiplies latency and token spend while adding a place for the objective to get
distorted in translation. It is easy to reach for another orchestrator layer; it is
rarely cheap.

**(c) Countermeasures.**

- Treat added hierarchy as a **last resort**. Prefer to keep the structure flat by
  widening span (§1) through context delivery.
- Add a layer only when you can name the specific coordination or verification load
  it relieves — and remove it if that load disappears.

---

## 5. Separation of duties breaks down

**(a) In human organizations.** *Separation of duties* splits a sensitive task so no
single person controls it end to end — the person who executes a transaction is not
the person who approves it. Collapse that separation and you create a single point
that can both commit a fault and conceal it.

**(b) In agent organizations.** The failure is an agent that verifies its own work.
A Maker that also acts as its own Checker is a single point that can produce a flawed
result *and* certify it as good, with no independent party positioned to catch the
discrepancy. Self-verification is not verification.

**(c) Countermeasures.**

- Keep the **discovery/implementation agent and the validation/acceptance agent
  strictly separate**. The one that produces a result must never be the one that
  decides whether it is accepted. This is a hard rule, not a preference — it is the
  structural guarantee behind everything in §2's measurement system.

---

## 6. Empowered execution without shared consciousness

**(a) In human organizations.** *Team of Teams* (McChrystal) pairs two ideas:
*empowered execution* (push decision authority down to the edge) and *shared
consciousness* (give the edge a common, real-time picture of the whole). Empowerment
**without** shared consciousness is the trap — autonomous units acting on local
information produce local optima, duplication, and occasionally runaway behavior.

**(b) In agent organizations.** Granting agents autonomy is only safe if they also
share context. Autonomy plus a starved context window yields agents that optimize
their local slice, redo each other's work, or charge off in a direction that made
sense locally and nowhere else. The autonomy was not the problem; the missing shared
picture was.

**(c) Countermeasures.**

- Increase **delegated authority and shared information together, as a pair**. Every
  time you give an agent more room to act on its own, give it correspondingly more
  shared context — a common ledger, a current context pack. If you cannot raise the
  shared picture, do not raise the autonomy.

---

## 7. Bureaucratic ossification of exploration

**(a) In human organizations.** Burns & Stalker distinguished *mechanistic* systems
(rigid, procedural — good for stable, well-understood work) from *organic* systems
(fluid, adaptive — good for novel, uncertain work). Forcing a mechanistic, heavily-
proceduralized regime onto genuinely exploratory work kills the emergence you were
hoping for.

**(b) In agent organizations.** Bolting a rigid, step-locked procedure onto a
*discovery* phase suppresses exactly the creative, surprising output that made
discovery worth running. The agent dutifully executes the checklist and produces
competent, unsurprising, low-value results — the process worked and the point was
lost.

**(c) Countermeasures.**

- Keep exploration/discovery phases **organic**: loose procedure, wide latitude,
  emergence allowed. Reserve mechanistic rigor for phases that are genuinely stable
  and repeatable (validation, deployment, reporting). Match the regime to the nature
  of the work, not to a uniform house style. (Running both regimes in one org is
  Lawrence & Lorsch differentiation–integration, with its integration cost — docs/03 §2.)

---

## 8. Star Model misalignment

**(a) In human organizations.** Galbraith's *Star Model* holds that an organization's
design has five interlocking points — strategy, **structure**, **processes**,
**rewards**, and **people** — and they must be aligned. Change the structure alone and
leave processes, rewards, and people untouched, and a *shadow organization* emerges:
informal workarounds that route around the official design to get things done.

**(b) In agent organizations.** If you rewire the org chart (structure) — new roles,
new supervisors — but leave context delivery, gates, and model selection on their old
settings, agents route around the new design. You get a shadow flow: work quietly
bypassing the official pipeline because the official pipeline was never fully wired
for the new structure. The chart says one thing; the token traffic says another.

**(c) Countermeasures.**

- When you change structure, move the **other points in the same commit**: update
  context delivery, acceptance gates, and per-role model selection together so the
  whole Star stays aligned. A structural change is not done until processes, rewards,
  and people (here: context, gates, models) have caught up.

---

## Quick self-audit

Run this checklist against your agent organization periodically:

- [ ] **Span** — Can each Checker/supervisor genuinely re-derive the work it signs
  off, or is it rubber-stamping? (§1)
- [ ] **Proxy** — Is any agent being rewarded on a raw quantitative proxy it can see
  and optimize directly? (§2)
- [ ] **Anti-gaming** — Does acceptance include null/placebo/forward tests that
  separate real results from spec-gaming? (§2)
- [ ] **Conway** — Do the agents that must integrate actually share a communication
  path / common ledger? (§3)
- [ ] **Layers** — Can every hierarchy layer name the specific load it relieves, or
  is it dead weight adding latency and tokens? (§4)
- [ ] **Separation** — Is any agent verifying its own output? (§5)
- [ ] **Autonomy/context** — Has autonomy been raised without a matching rise in
  shared context? (§6)
- [ ] **Exploration** — Is a discovery phase being run under rigid, mechanistic
  procedure? (§7)
- [ ] **Alignment** — After the last structural change, did context, gates, and model
  selection get updated too — or is a shadow flow forming? (§8)

If any box is unchecked, you have located a live failure mode, not a hypothetical
one.

---

## Sources

1. Span of control — https://en.wikipedia.org/wiki/Span_of_control
2. Goodhart's law — https://kpitree.co/guides/frameworks/goodharts-law
3. Conway's law — https://en.wikipedia.org/wiki/Conway%27s_law
4. Anthropic, "Building a multi-agent research system" (token cost of multi-agent
   systems) — https://www.anthropic.com/engineering/multi-agent-research-system
5. Separation of duties — https://en.wikipedia.org/wiki/Separation_of_duties
6. McChrystal Group, "Empowered Execution" (Team of Teams) —
   https://www.mcchrystalgroup.com/about/team-of-teams/empowered-execution
7. Burns & Stalker, mechanistic vs. organic systems —
   https://www.valuebasedmanagement.net/methods_burns_mechanistic_organic_systems.html
8. Galbraith's Star Model —
   https://strategicmanagementinsight.com/tools/galbraiths-star-model-explained/
