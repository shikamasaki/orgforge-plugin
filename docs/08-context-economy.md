# 08 — The Context Economy: Need-to-Know Collaboration, Intent for Everyone

> Organ 5's rule says: *increase information sharing in the same proportion you increase
> autonomy.* Read naively, that means "share everything with everyone" — which, for
> agents, is wrong three ways at once: context windows are finite (attention is the
> scarce resource), every shared token is injection surface, and total sharing couples
> every department to every other (Conway blur). This document refines the rule:
> **broadcast the *intent* to everyone; deliver the *details* on need-to-know, through
> contract interfaces, within a budget.** Departments collaborate without drowning each
> other, and the organization's direction still reaches every member every cycle.

---

> **Framing (read before the mechanisms): context packs are delivered by projection, not
> assembled by a bespoke engine.** A "context pack" is a set of **files the projection
> writes into the working directory before the consuming department's harness launches**
> (docs/09 §2, docs/01 R2) — the intent block, the role's contract and doctrine, its
> granted views, nearby failures. The "registrar" that does this is itself **a department
> the host runs** on a schedule, not a runtime this repo ships; "pack assembly" is that
> file-writing step, and "on the next cycle" / "on a cadence" is a schedule the **host
> scheduler** realizes (docs/09 §4). Read the mechanisms below as *what files go where and
> who is granted to read them* — need-to-know as file placement — not as a live gatekeeper.

## 1. The refinement of the Organ 5 rule

McChrystal's shared consciousness is often misread as total transparency. What Team of
Teams actually built was a **common relevant picture** — everyone holds the same compact
understanding of the mission and the state of adjacent units, not a copy of everyone's
inbox. Simon named the underlying economics decades earlier: *a wealth of information
creates a poverty of attention* — and an agent's context window is exactly its attention.
Galbraith's information-processing view completes the frame: organization design **is**
the design of information flows to fit processing capacity — you either increase capacity
(bigger packs, more tokens) or reduce the need to process (better abstractions,
self-contained tasks). This organ chooses the second lever first.

So the rule becomes:

> **Autonomy scales with the quality of the shared *abstraction*, not the volume of
> shared *data*.** Every member always holds the intent and its own contract's
> neighborhood; everything else is pulled on demand, by grant.

### 1.1 Knowledge and viewpoint are separated *by layer* — the field stays narrow-and-deep

The need-to-know rule is not only horizontal (peers don't read each other's details). It is
also **vertical**, and the vertical separation is deliberate in *both* directions:

- **The field is siloed narrow-and-deep.** An exploration-front role reads only the few
  views of its own vertical (miner: `coverage_map, live_findings, nearby_deaths` — three
  views, one budget), so its attention is forced *down* its silo, not *across*. Narrow scope
  is what buys depth; widen it and the specialist thins into a generalist.
- **The upper layers do NOT accumulate the field's knowledge, and this is correct, not a
  gap.** A supervisor reads `direction_flags, sensor_readings`, never a maker's
  `coverage_map`; the control layer holds no per-role doctrine (that would be *doctrine
  capture* — a self-taught gate, docs/07). The upper layers hold a *cross-cutting* picture
  (direction, sensor state, the full evidence trail for the item under review), not a copy
  of the field's domain knowledge. **The boss does not need to know what the specialist
  knows; the boss needs to know whether the specialist's output is on-purpose.**
- **Cross-cutting viewpoint does not leak down.** Only the intent (the compact abstraction,
  §2.1) is broadcast downward; the *cross-cutting judgment* — is this output serving the
  purpose, admit or reject? — stays in the upper layers (gate, skeptic, supervisor). It is
  not handed to the field. If a specialist were fed the org-wide outcome picture and told to
  judge its own work against the purpose, it would start optimizing across the whole rather
  than deepening its silo — the field would go wide-and-shallow, which is the failure this
  separation exists to prevent. **The specialist produces; the upper layer judges whether the
  output meets the goal and admits or rejects it.**

So the layered rule: *intent flows down, details are pulled sideways on grant, cross-cutting
judgment stays up, and no layer accumulates another layer's knowledge.* The field is kept
narrow-and-deep on purpose; the breadth lives — and only lives — where the authority to
judge across silos lives.

## 2. The four mechanisms

### 2.1 The intent block (the one broadcast)

A compact, versioned statement — purpose (Organ 1), the current priorities under it, and
the constraints in force — present in **every** context pack, at every activation level,
in identical wording. This is commander's intent from mission command (Auftragstaktik):
the edge can act autonomously *because* it knows what outcome matters, without the center
scripting the method. **Org-wide policy propagation is exactly an intent-block revision**:
version-stamped in the ledger, then delivered by the registrar — a host-run department, not
a runtime — writing the revised block into each role's working directory the next time the
host launches that role on its schedule ("on the next cycle" = a host-realized schedule,
docs/09 §2/§4), and never forked per department (one intent, everywhere, or coordination
dissolves into local interpretations). Purpose changes are human-held (docs/06 §2.5); priority
re-weighting within an unchanged purpose is charter-tier (proposed via the approval
queue, adjudicated by humans).

### 2.2 Scoped context packs (need-to-know by default)

A context pack is a **derived view of the ledger and knowledge base, not a feed**. The
scope matrix in `organization.yaml` (`information_flow.scopes`) is deny-by-default: a
role reads the views it has been granted and nothing else — least privilege, applied to
information (Saltzer & Schroeder's need-to-know, imported from security because a
misaligned optimizer with extra context is an attacker with extra reconnaissance). This
scoping is realized by **which files the projection writes into each working directory** —
need-to-know as file placement — enforced structurally for every org (Tier A) and, for
asset-touching orgs, by the host environment (Tier B), not by a runtime gatekeeper
intercepting reads (docs/01 §5, docs/09 §5). The standard pack formula, for every role:

> intent block + own contract & doctrine (docs/07) + **live state of adjacent
> contracts** (its declared `depends_on` seams) + nearby failures relevant to its scope.

Nothing else rides along by default. Every grant is recorded in the ledger; grants are
**reviewed on a cadence and unused grants are revoked** (access recertification —
scope creep is how need-to-know quietly becomes share-everything). "On a cadence" here is
host-realized: a scheduled run of the responsible department (the host's scheduler firing
it), declared as intent — this repo ships no scheduler (docs/09 §4).

### 2.3 Contract interfaces (how departments collaborate)

Departments talk through the **seams their contracts declare**, and a handoff carries the
interface's fields — the deliverable, its verification state, the assumptions the
receiver must know — never the sender's working context. This is Parnas's information
hiding applied to the org: each department hides its method (its organic interior) and
exposes a stable interface (its contract), which is also exactly the inverse-Conway
discipline of docs/04 §3 — the communication paths you wire *are* the product seams you
get. Lateral mutual adjustment is free **within** a declared seam; opening a *new* seam
between departments is a scope change (`adjust_context_scope` in moves.yaml), recorded
and reviewable, because a new communication path is a new product seam whether you
intended one or not.

### 2.4 Context budgets and progressive disclosure (push the abstraction, pull the detail)

Every pack and every handoff has a **size budget**. Over budget → summarize and link:
the receiving role gets the abstraction plus ledger/KB references it can expand on
demand (the RAG pull of docs/07). Push what fits attention; let the reader pull depth.
A budget forces the sender to do the distillation work once instead of exporting its
processing load to every reader — Galbraith's lever again. Budgets are set per seam in
the scope matrix and enforced at **pack assembly** — the registrar department's
file-writing step, when the host launches it on its schedule, deciding what fits and what
gets summarized-and-linked before the files land in the working dir (docs/09 §2/§4). The
registrar is a host-run department applying the budget as it writes, not a runtime
gatekeeper intercepting reads.

---

## 3. Failure modes on both sides of the dial

The scope matrix is a dial with failure on both ends, and the sensors watch both:

- **Under-sharing** (dial too tight): duplicated work, contradictory conclusions,
  agents blocked on context they weren't granted — McChrystal's original danger, and
  docs/04 §6's autonomy-without-consciousness trap. Sensors: `divergence`,
  `blocked_on_missing_context` (grant-request denial rate). Remedy: `adjust_context_scope`
  widening, at the seam that actually starved.
- **Over-sharing** (dial too loose): attention poverty (the contract buried under
  context), widened injection surface, and Conway blur — when everyone reads everything,
  the product's seams dissolve with the org's. Sensors: `context_utilization` (how much
  of a pack a role's outputs actually used), pack-size trend against budget. Remedy:
  scope revocation, re-distillation, budget tightening.
- **Fork drift on the intent**: departments paraphrasing the intent block into local
  copies that then age independently. The block is loaded by reference from its
  ledger-stamped version, never copied into profiles.

The supervisor's direction check (SUPERVISOR.md) reads these sensors: a department going
the wrong direction with high context utilization has a doctrine or intent problem; one
with low utilization has a scope problem. Which is the diagnosis matters — the fixes are
different organs.

---

## 4. What this must never optimize away

Need-to-know applies to the exploration front's *lateral* traffic. It never restricts:

- **the control layer's read access** — the gate, skeptic, and supervisor see whatever
  their duties require, and a maker can never scope-fence its Checker out of the evidence
  (that would be separation of duties defeated by information starvation). This is
  guaranteed structurally: the projection writes the evidence files into the checker's
  working directory regardless of the maker's grants (Tier-A SoD, docs/09 §5);
- **the ledger's completeness** — scoping governs who *reads* which views, never what
  gets *written*; the record stays whole (custody, Organ 6);
- **the intent block** — no role is ever "not cleared" for the organization's purpose.

---

## Sources

- Parnas, D. 1972 — "On the Criteria To Be Used in Decomposing Systems into Modules,"
  *CACM* (information hiding).
- Galbraith, J. 1974 — "Organization Design: An Information Processing View,"
  *Interfaces*.
- Simon, H. 1971 — "Designing Organizations for an Information-Rich World" (attention
  scarcity).
- McChrystal et al. 2015 — *Team of Teams* (shared consciousness as common relevant
  picture).
- Mission command / commander's intent — Auftragstaktik; U.S. Army ADP 6-0 as a modern
  doctrinal reference.
- Saltzer, J. & Schroeder, M. 1975 — "The Protection of Information in Computer
  Systems" (least privilege, need-to-know).

*Status: this is a design for how the context economy **maps onto host-run departments**.
Context packs are delivered by the projection writing files into each working directory
before launch, and the registrar that does so is a department the host launches on a
schedule (docs/09 §1/§2, docs/01 R2) — scoping, budgets, and grants are enforced
structurally (Tier A) or by the host environment (Tier B), not by a bespoke gatekeeper
(docs/09 §5). The mechanisms are this repo's synthesis of the cited frames plus
standard security practice; the sensor thresholds and budget sizes are unvalidated design
parameters. Treat the dial metaphor seriously — both failure directions are real, and only
a running system tells you where your dial sits.*
