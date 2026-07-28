# 01 — Requirements: What This System Must Actually Be

*Part I · Foundations — see [the four-part map](README.md).*

> Every other document describes *how* the organization is decomposed. This one fixes
> *what the whole thing is for and what it must do to count as working* — the actors it
> serves, the jobs those actors need done, the success criteria, the threat model, and
> the non-negotiable constraints. It is the anchor: a design or a review is judged
> against this file first. THEORY.md is the intellectual core; this is the product spec.

---

## 0. The first principle, stated as a requirement

The repository's thesis (THEORY.md): **in a world where AI runs the work
around the clock and the human decides only the essential things, designing the system
reduces to *articulating* — in a form an AI can act on — the tacit organizational
knowledge a human company runs on: the goal, the information flow, the division of labor,
and the decision line between what the human decides and what is delegated.** That gives
the deepest requirement:

> **R−1 (the articulation requirement) — The system's job is to make the tacit explicit.**
> Everything a human org leaves unwritten (what we're trying to do, who needs to know
> what in what amount, who owns which deliverable to what standard, which decisions the
> human makes vs. delegates) must be written down in machine-actionable form, because an
> AI acts only on what it is given. `organization.yaml` articulates the division of labor
> and information flow; `constitution.yaml` articulates the decision line; `ROLE.md`
> articulates each member's job; the intent block articulates the goal. If any of these is
> left tacit or coarse, the output is mis-aligned or essence-missing — which is exactly
> where multi-agent LLM systems empirically fail (MASFT: ~40% inter-agent misalignment,
> ~35% role/spec, ~25% verification). The articulation *renders to* a permissioned
> dataflow graph on the host harness (Conway's law), but the design act is the
> articulation, not the graph.

And R−1 constrains *how* the system runs, which is R0: the harness and loop are organs the
industry already built — Claude Code, Codex, and their kin are runnable harnesses with
context management, tool mediation, and a control loop. You *place* those existing wheels;
you do not re-forge them. So the load-bearing runtime requirement:

> **R0 — The system must let an LLM agent run autonomously on an EXISTING harness, with
> no new runtime to build first.** What this repository ships is (a) the organization's
> skeleton as neutral, declarative data, (b) a thin projection of each role onto whatever
> harness will run it, and (c) a machine audit of the skeleton. The heavy organs —
> perception, tool mediation, the control loop, scheduling, budgets — are **delegated to
> the host harness**, which already implements them. The system is *harness-neutral*: it
> assumes no single vendor and no bespoke execution engine.

A design that requires standing up a custom mediation runtime, a custom event bus, or a
custom scheduler *before an agent can do useful work* has violated R0. "It's specified"
is not "it runs." If the smallest useful configuration cannot be launched on a
general-purpose coding agent as it ships, the requirement is unmet — no matter how
complete the spec is.

And R−1/R0 say nothing yet about *which* organization is being articulated. This
repository does not stand up an arbitrary org; it stands up a **specific kind**, and that
narrows the requirements — so it is fixed here as the first principle after articulation
itself (THEORY §1b):

> **R0b — The thing being stood up is an IT business company.** The org's purpose slot
> (Organ 1) is filled with a *business telos*: it **decides what software to build as a
> business** from a market intent (a customer, an RFP, a priority ranking), builds it,
> ships it, operates it, and is answerable for **delivery and economics — not volume of
> output**. This is why §1's *client* actor, §3's *serve-the-client* and *manage-delivery*
> jobs, and §4's *acceptance* / *unit-economics* / *on-time* criteria are requirements at
> all and not decoration: they are the concrete obligations a company-shaped org owes that
> an abstract "agent org" does not. The neutral seven-organ theory is untouched; R0b only
> says which organization these requirements are written for.

---

## 1. Actors

The system was previously written as if there were one human ("the operator") and a pool
of agents. That is too coarse and hid real requirements. The actors are:

| Actor | Who / what | What they need from the system |
|---|---|---|
| **Client** | The party the RFP is *for* — a paying customer, an internal stakeholder, a downstream team. Distinct from the operator. | A way to submit and amend the RFP, see milestone-level progress in their terms, and accept or reject deliverables at a gate. |
| **Operator** | The human running the org day-to-day; holds charter authority (docs/05). Not the client. | A morning digest, an approval queue for charter/irreversible actions, delegation-bound tuning, purpose/intent revision. |
| **Department** | An LLM agent (or a self-organizing pool behind one contract) running on a host harness. A *member* of the org. | Its profile projected into the harness it runs on, a scoped context pack, its contract and doctrine, a way to hand work to its checker. |
| **Host harness** | The existing LLM coding-agent runtime a department runs on (e.g. Claude Code, Codex). Supplies Organs 3 & 4. | A neutral profile it can read as its instruction file; a working directory; a launch/stop signal on a schedule. |
| **Founder process** | Runs once, turns an RFP into the latent org (FOUNDER.md). | The RFP, the human-authored constitution, the moves/sensors/schema templates. |

The client↔operator distinction is a hard requirement: the human who *approves a
production deploy* (operator, charter authority) is often not the human whose *needs the
RFP encodes* (client). Conflating them hides the entire customer-facing surface
(§3, jobs J1/J5).

---

## 2. Harness neutrality (the concrete form of R0)

**A department is not a bespoke process; it is a host harness pointed at a working
directory whose instruction file is this role's projected profile.** Requirements:

- **R2.1 — Neutral profile is the source of truth.** A role's profile (ROLE.md instance)
  is authored once in a harness-neutral form. It is *projected* into each host harness's
  own instruction-file convention (a Claude Code repo reads `CLAUDE.md`; a Codex repo
  reads `AGENTS.md`; others have their own). The neutral profile is canonical; the
  per-harness files are generated views, regenerated, never hand-forked — the same
  discipline the ledger's derived views already follow (Organ 5).
- **R2.2 — Delegate the organs the harness owns.** Perception/tools/memory (Organ 3),
  the perceive→decide→act loop, stop conditions, iteration caps, and token budgets
  (Organ 4) are configured *through* the host harness's existing mechanisms, not
  reimplemented. The system declares *intent* ("this role's cadence is hourly", "cap
  tokens per window"); the harness enforces it.
- **R2.3 — Scheduling is a host concern.** "Activate department X on cadence Y" maps onto
  whatever scheduler the deployment already has (a cron, the harness's own loop, a CI
  trigger). The system specifies the schedule as data; it does not ship a scheduler.
- **R2.4 — The projection is the only harness-specific code.** Everything else
  (organization.yaml, constitution.yaml, moves/sensors/ledger schemas, the lint) is
  harness-agnostic. Swapping Claude Code for Codex changes which instruction files get
  generated and how launch/stop is wired — nothing in the org's skeleton.
- **R2.5 — No capability is assumed beyond a general coding agent.** The baseline host is
  an agent that can read an instruction file, read/write files in a working directory,
  run tools, and be launched on a schedule. Anything richer (native sub-agents, hosted
  memory, managed scheduling) is an *optional accelerator* the projection may use when
  present, never a precondition.

The open decision (deliberately not fixed here): *which* instruction-file conventions to
target first and whether to lead with a neutral name or a specific one. That is a
projection-layer choice (docs to be written), not an organizational one — the skeleton is
identical either way. Recorded as an open question in §7.

---

## 3. Jobs to be done

What the system must let its actors accomplish. Each is testable.

- **J1 — Found from an RFP.** Given an RFP + a human-authored constitution, produce a
  complete latent org (contracts, SoD, profiles) that passes the lint and a human charter
  approval, with the minimal first set launchable on a host harness. (FOUNDER.md)
- **J2 — Run a department autonomously.** Launch one department on its host harness and
  have it do a cycle of real work toward its contract — perceive its scoped context, act,
  hand a positive result to its checker — with **no bespoke runtime in the loop**. (R0)
- **J3 — Coordinate independent departments.** Multiple departments pursue their own
  contracts and integrate through contract seams + the shared record, without a central
  agent scripting their steps. (docs/05 §1, docs/07)
- **J4 — Keep control honest.** No maker admits its own work; the maker/checker line and
  the three incompatible duties hold at runtime, not just on paper. (Organ 6)
- **J5 — Serve the client across the lifecycle.** Accept RFP amendments as they arrive,
  report milestone progress in client terms, run acceptance gates on deliverables, and
  keep the client informed — the org is a *vendor with a customer*, not an island. (new;
  the gap §1 names)
- **J6 — Manage delivery, not just health.** Surface whether the work is *on track to the
  milestone* and *net-positive after cost per admitted result* — progress and unit
  economics, not only organizational liveness. (new; the sensor gap)
- **J7 — Renegotiate contracts.** When integration reveals a wrong seam, change the
  contract (what a department owes), not just its context scope. Architecture is
  discovered by building. (new; the moves-catalog gap)
- **J8 — Run around the clock, human above the loop.** Delegated work proceeds
  unattended; charter/irreversible actions queue for asynchronous human decision; the
  human audits a night in minutes. (docs/05)
- **J9 — Scale elastically and end cleanly.** Activate/deactivate departments by load;
  enter maintenance, hand over, sunset — cradle to grave. (docs/02, docs/05)
- **J10 — Compound assets across projects.** Profiles, doctrine, parts, and failure
  lessons outlive any single RFP and seed the next org from a company-level pool — the
  purpose's "durable asset" promise. (new; the company-layer gap)
- **J11 — Build through the forced SDLC mold.** Every deliverable travels a
  **non-skippable phase chain** — requirements → design → implement → test → integrate → deploy →
  operate — and a phase may not start until the prior phase's output carries an admission
  verdict. This is the `requires_prior` mechanism (Organ 6, docs/03/14) *generalized from
  admission-gating to phase-gating*; the mold is promoted by doctrine and enforced by
  lint/hook, never by forced delegation. (new; the SDLC gap — docs/11)
- **J12 — Ship continuously (CI/CD).** The org keeps the trunk always-shippable and
  releases through a continuous-integration/continuous-delivery spine — **GitHub Actions**
  — that the org *declares intent into* and the host runs, exactly as scheduling is
  delegated (R0/R2.3). A green pipeline that includes the `survives` check *is* the machine
  form of the deploy gate. (new; the continuous-delivery gap — docs/11 §3)
- **J13 — Operate under a reliability budget, navigate by DORA.** A running product carries
  a **reliability/error budget** that *bounds deploy velocity* (an SRE governor at the
  deploy gate), and the org steers by **DORA metrics** — deploy frequency, lead time,
  change-fail rate, MTTR — to the moving bottleneck (Theory of Constraints). The budget and
  the metrics live with the other 24/7 operating instruments (docs/05). (new; the
  reliability/DORA gap)
- **J14 — Produce reproducible outcomes, at two levels.** Given the same org spec + RFP, the
  **process, contracts, gates, and verification must converge** no matter who founds the company
  or when (Level 1) — the generated code may vary, an LLM is non-deterministic, but the mold makes
  everything around it the same. And the **repositories the org builds must be reproducible for
  anyone who clones them** (Level 2): a committed lockfile + pinned toolchain, a one-command
  documented setup and test the gate re-runs from a clean clone, idempotent migrations, a
  `.env.example`, and a green from-clean CI workflow — each an *admission artifact*, not a maker's
  self-claim. (new; the reproducibility gap — docs/11 §0, §4a)

---

## 4. Success criteria

The org's value is what it *produces*, not the elegance of its chart (THEORY.md, Organ 1).
Concretely, the system succeeds when:

- **S1 — It runs, unmodified, on at least one existing host harness** with no custom
  runtime — the direct test of R0/J2. Until this is demonstrated once end-to-end, every
  other claim is provisional.
- **S2 — Admitted deliverables meet the RFP's acceptance criteria**, judged by an
  independent checker, with gaming-resistant measurement (nulls/placebos/forward tests).
- **S3 — Net-positive unit economics**: tokens-per-admitted-result and cost-after-value
  are measured and reported, and the objective metric (value, not volume) trends up.
- **S4 — On-time delivery is visible**: the operator and client can see, before the
  deadline, whether a milestone is at risk — not discover it after.
- **S5 — Control never silently fails**: the lint passes on every reorg, and the runtime
  invariants the host can enforce (independent checker, no self-admission) demonstrably
  hold on a live run.
- **S6 — A night of autonomous operation is auditable in ≤15 minutes** and no
  irreversible action fired without human approval.
- **S7 — The phase order holds mechanically.** No deliverable reaches deploy without a
  ledgered admission verdict on each prior phase; the lint refuses a routing that lets a
  phase skip its predecessors, and the deploy hook refuses a `phase_started` with no
  admitted predecessor (J11 — docs/11 §2).
- **S8 — Release is continuous and gated by the pipeline.** Changes ship through the CI/CD
  spine, and the pipeline *itself* refuses to release without the `survives` check and a
  healthy budget — the deploy gate is machine-enforced, not a human watching a checklist
  (J12/J13 — docs/11 §3, docs/05).
- **S9 — The same spec yields a reproducible outcome.** Two foundings from the same org spec + RFP
  pass the *same gates* and satisfy the *same contracts* (Level 1), and every repository the org
  admits clones-and-runs deterministically for a stranger — lockfile + pinned toolchain present,
  one-command setup+test green from a clean checkout, migrations idempotent, CI green from clean
  (Level 2). Reproducibility is checked by a deterministic tooth, not asserted (J14 — docs/11 §0,
  §4a).

The honest status line for the repo: **S1 has been demonstrated once** — a small Tier-A
RFP run end-to-end on an existing harness, three departments as separate agents, with the
maker/checker separation holding structurally (demos/S1-founding-rehearsal). S2–S6 — scale, on-time delivery,
unit economics, and unattended 24-hour operation — remain to be shown. R0 says a runnable
design is the first requirement; that bar is now cleared for the smallest case, and the
frontier is scale and autonomy.

---

## 5. Threat model (stated explicitly, so reviews stop defaulting to max-adversarial)

Earlier reviews collapsed toward exhaustive red-teaming because the threat model was never
written down. It has two tiers, and controls attach to the tier they defend:

- **Tier A — Drift & honest error (the common case, applies to EVERY org).** LLM
  departments hallucinate, sycophantically agree, skimp on verification, apply stale
  knowledge, or optimize a proxy without intending fraud. Defenses: the independent
  checker (skeptic), purpose-grounded admission, fresh doctrine, direction supervision,
  the lint. These are always on. **This is the primary risk for the overwhelming majority
  of deployments.**
- **Tier B — Adversarial optimization (only where the stakes justify it).** A department
  actively games the boundary — laundering a bad result past the gate, manufacturing a
  sensor reading, flooding the approval queue, escaping the boundary via a mislabeled
  action. Defenses: write-authorization, tamper-evident records, external watchdogs,
  effect resolution. **These are required only for orgs that touch real assets,
  production, funds, or external publication** — and even then, they are the *host
  harness's and host environment's* job to provide (sandboxing, permissions, credential
  custody), which R2 already delegates, not something this repo reimplements.

The design rule: **build Tier-A defenses into the skeleton for everyone; require Tier-B
defenses only for asset-touching orgs, and satisfy them by choosing a host environment
that provides them, not by hand-rolling a runtime.** A review must state which tier a
finding targets; a Tier-B finding against a documentation-generation org is out of scope.

---

## 6. Non-negotiable constraints

- **C1 — Harness-neutral.** No requirement may assume a specific vendor's harness in the
  org skeleton. (R0/R2)
- **C2 — Separation of duties is absolute.** A maker never admits its own work; this
  survives every scheduling and elasticity decision. (Organ 6, docs/03)
- **C3 — Purpose is human-held.** Telos revision is never delegated. (Organ 1)
- **C4 — Delegate before you build.** For any organ the host harness already provides,
  the requirement is to *use* it, not to reimplement it. Reimplementation must be
  justified against R0. (R2.2)
- **C5 — No knowledge outside the shared record**, so dormancy is lossless and departments
  are not person-dependent. Enforced by discipline + audit (and, where the host provides
  it, by the host's storage). (docs/02 §5)
- **C6 — The value test governs.** Elegance of the chart is not success; a produced,
  admitted, net-positive deliverable is. (Organ 1)

---

## 7. Open questions (decisions deliberately deferred)

These are recorded, not resolved — they are choices for later, and none blocks writing the
harness-neutral skeleton:

1. **Which instruction-file conventions to target first** (a neutral filename vs. leading
   with a specific one like `AGENTS.md`, with others as fallback), and the exact
   projection format. A projection-layer decision (§2), not an organizational one.
2. **Company layer scope** (J10): whether the cross-project asset pool ships now or is a
   future layer above the single-org model.
3. **How much of Tier B to specify** vs. delegate wholly to the host environment — the
   §5 rule leans toward delegation, but the boundary for asset-touching orgs needs a
   concrete checklist.

---

## 8. What this changes about the rest of the repo

This requirements pass reframes documents that were written runtime-first:

- **docs/08** must be rewritten from "the runtime you build" to "the host harness you
  delegate to, and the thin projection you add" (R0/R2). Its conformance checklist becomes
  "what the host must provide" + "what the projection must generate", not "what you must
  implement."
- **The sensor and delivery gaps** (J6/S3/S4) add progress and unit-economics signals the
  current sensors.yaml lacks.
- **The contract-renegotiation move** (J7) is missing from moves.yaml.
- **The client actor** (J1/J5) adds a customer-facing surface absent from docs/05.
- **Reviews** must cite the threat tier (§5) and treat R0/S1 — *does it actually run on an
  existing harness?* — as the first question, ahead of any spec-completeness finding.

*This is the product spec the rest of the repository is accountable to. The deepest
requirement is the simplest: an LLM picks up this template and runs — autonomously, on a
harness that already exists.*
