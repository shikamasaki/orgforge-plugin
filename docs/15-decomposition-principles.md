# 15 — Decomposition principles: how a manager splits work into sub-tasks

docs/12 said how a department, handed a backlog, picks *what to work on next*. It did not say how a
manager, handed one backlog item, decides **whether to split it and along which lines**. That choice
was left to the manager's LLM, tacit and unaudited — the same gap docs/12 closed for triage, still
open for decomposition. This document is the **decomposition doctrine**: the norms a manager applies
when it turns one assignment into sub-tasks (or decides not to). It is injected into the manager's
profile (PROJECTION.md §1) and its doctrine (docs/07), so a manager splits by principle, not by whim.

**It is doctrine, not a hook.** An earlier design reflex was to *force* delegation with a PreToolUse
gate ("a manager may never implement; it must spawn"). That is the wrong layer and the docs reject it:
docs/14 §granularity makes fan-out a **per-task judgment with a budget, not a mandate**, and docs/03 §4
warns that *forcing structure on the organic front is the mistake the self-organization literature
names*. Decomposition **quality** is a judgment; a hook can only check **shape**. So the quality lives
here, as norms the manager reasons with — while the guardrails enforce only the shape checks that are
genuinely mechanical (a spawn carries a seam contract; a mechanistic coordinator produces no domain
deliverable — docs/07 §2.1.1, docs/08 §1.1, and the lint tooth of §5 below).

## §1 It is not a new invention — it is four settled results, applied inside the unit

There is **no single named theory** called "how a manager decomposes a task" (the docs/sources.md
discipline: name the real anchors, do not fuse them into a fake unified theory). The norms below are
this repo's concrete rendering of four consensus results from systems design and organization theory,
each applied at the intra-unit granularity the classics did not themselves reach:

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
  of docs/14's "keep tightly-coupled work single-threaded."
- **Coordination cost bounds the gain** (Becker & Murphy, "The Division of Labor, Coordination Costs,
  and Knowledge," *QJE* 107(4), 1992): the division of labor is limited **not by how finely one could
  cut, but by the coordination cost of the cut**. Each additional split buys parallelism and specialized
  knowledge but spends coordination (seam contracts, integration, review). Split only while the gain
  exceeds that cost.

Conway (1968, *Datamation* 14(5); docs/04 §3) is the constraint *around* this: whatever decomposition
the manager chooses, the artifact's structure will mirror it. So the decomposition **is** an
architectural decision — choose the sub-task seams you want the product's seams to be.

## §2 The principles, as a manager applies them

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
   be a **pinned contract** (the producer's output = the consumer's declared input, docs/07 §2.1.1),
   or it drifts. Pooled work is the free case — split it as widely as the coordination budget allows.
4. **Split only while the gain beats the coordination cost (Becker & Murphy).** Each sub-task costs a
   seam contract, an integration, and a conformance review (docs/14 §A3). Split when the pieces are
   **genuinely independent and each is worth its own agent** — recurring work, work that would dilute a
   generalist's context, or work needing independent lineage (docs/14 §specialization). Do **not**
   split tiny or coupled units whose coordination cost exceeds the parallelism they buy. This is the
   principled form of the user preference "prefer fine-grained decomposition, but do not over-split
   coupled or trivial units": fineness follows *independence*, bounded by *coordination cost* — not a
   target depth.

The default that falls out: **subdivide for genuinely parallel, breadth-first, independent work; keep
reciprocally-coupled work single-threaded** (docs/14 §granularity, verbatim). There is no preferred
depth and no mandate to fan out.

## §3 Own-domain work vs another role's domain — the line that protects knowledge

Principle 3 says a manager *may* keep tightly-coupled work single-threaded — implement it itself. That
permission has a **boundary**, and the boundary is what makes role-separation and the knowledge organ
work:

- **Own-domain coupled work → the role implements it itself.** A domain department-head (regime:
  organic) building a tightly-coupled slice of *its own* domain keeps that work single-threaded and the
  learning accrues to **its own** role-keyed doctrine (docs/07 §2.1, `<root>/<role>.json`) — the right
  silo. This is correct and docs/14-blessed.
- **Another role's domain → route to that role; never swallow it.** Work whose *domain* belongs to a
  distinct role must be delegated to that role, not absorbed "because it's coupled." Absorbing it is
  **doctrine capture** (docs/08 §1.1): the domain knowledge would pool in the wrong place and the role
  that *should* own that domain is starved. A **mechanistic coordinator** (supervisor / CEO / gate)
  holds *no* per-role domain doctrine by design — so it is structurally the wrong place to produce any
  domain deliverable, and must route domain work to the domain role.

So "manager implements coupled work itself" is bounded to **its own domain**. The seam contract's
`owns` / `must-not-touch` fields (docs/07 §2.1.1) and the role-keyed doctrine store are the mechanism
that keeps domain work flowing to domain roles; the lint tooth of §5 makes the coordinator half
load-bearing rather than merely asserted.

## §4 The output of a split: seam contracts that also prevent duplication

A decomposition is not done when the pieces are named; it is done when each piece carries a **seam
contract** (docs/07 §2.1.1): its slice, the inputs it receives, the outputs it must produce, and the
files it **owns** vs **must not touch**. The `owns` / `forbid` fields are not bureaucracy — they are
the repo's answer to docs/04 §6's duplicate-work failure mode ("autonomy + a starved context window →
agents redo each other's work"). Two sibling sub-tasks with disjoint `owns` sets cannot silently
overlap. **Non-duplication is guaranteed by the seam contract's ownership fields, not by the manager's
good intentions** — which is why the spawn gate requires a seam contract or an explicit independence
declaration before a child may run.

## §5 What the guardrails enforce (shape), and what the skeptic reviews (sense)

Decomposition quality cannot be machine-judged without re-imposing a fixed axis the docs reject
(docs/07 §2.1.1). So enforcement splits three ways:

- **The hook enforces shape** (mechanical, both harnesses): every spawn carries a seam contract or an
  `INDEPENDENT:` declaration (`spawn_needs_seam_or_independence`, docs/07 §2.1.1). No judgment of
  goodness — only presence of a contract.
- **The lint enforces the knowledge boundary** (new tooth, §3): a **mechanistic** role must carry no
  per-role domain doctrine and produce no domain deliverable — the doctrine-capture prohibition of
  docs/08 §1.1, made load-bearing. This is the one place the "route to the appropriate role" intent
  becomes a checked fact rather than a norm.
- **The skeptic reviews sense** (a role, not a gate): the split *proposal* — does it cover the
  assignment, is the granularity right, are the seams at the design secrets, did it miss a dependency —
  is reviewed by the existing skeptic role before execution (docs/06 §2.6). This is the LLM-grade
  judgment a hook cannot make, kept as a review, not a block.

*Status: this document is doctrine (norms injected into the manager's profile), not running code. Its
anchors — Parnas 1972, Simon 1962, Thompson 1967, Becker & Murphy 1992, Conway 1968 — are consensus
results applied at the intra-unit granularity the originals did not reach, per the docs/sources.md
discipline; the "own-domain vs cross-domain" boundary and its lint tooth (§3, §5) are this repo's
synthesis, to be verified against a running system. The one piece of new enforcement (§5's
mechanistic-no-domain-deliverable lint tooth) is specified here and is not yet implemented in
tools/org_lint.py.*
