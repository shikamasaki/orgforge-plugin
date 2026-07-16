# FOUNDER — from RFP to organization (the founding process)

The founder is the process that runs **once per organization**, at the cradle. Input: an
RFP (or any statement of what must be built) plus the constitution template. Output: a
complete, lint-passing, mostly-latent organization — after which the founder itself goes
dormant and the organization runs autonomously within its constitution.

The founder designs the org; it never runs it. Founding authority and operating
authority are separated for the same reason authorization and custody are (Organ 6).

---

## Inputs

- **The RFP** — preserved verbatim in the ledger as the purpose's source document.
- **`constitution.yaml`** (instance) — the delegation bounds, charter list, and safety
  limits the humans have set. The founder works *inside* these; it cannot write them.
- **`moves.yaml`** — the legal-move catalog its activation plan must be expressed in.

## The four founding steps

### 1. Distill the telos (Organ 1)

Restate the RFP as a one-sentence purpose. Derive the **admission standard** from the
RFP's acceptance criteria — and **every criterion must reference at least one
gaming-defense instrument** (nulls, placebos, forward tests); a criterion that is a bare
number is a proxy an optimizer will satisfy without serving. Hold the **objective
metric** as a subordinate instrument (`reward_agents_on_this: false`, always). If the
RFP contains only metrics and no purpose, that is a founding-blocker: return it to the
humans — an org founded on a proxy is Goodhart-doomed from birth (THEORY.md, Organ 1).

### 2. Derive architecture, then org (inverse Conway)

Sketch the target system's architecture from the RFP *first*. Then draw departments and
their communication paths to mirror that architecture (docs/04 §3). Checklist:

- Every architectural seam has a corresponding contract interface between departments.
- Departments that must integrate share a ledger view; departments that must stay
  independent (Maker/Checker pairs) do not share incentives or profile lineage.

### 3. Decompose the RFP into output contracts

For each department, write a **contract**: the deliverable slice of the RFP it owes,
the standard it must meet, its named Checker, and the adjacent contracts it may depend
on. Contracts say **what, never how** — method is the department's own (standardization
of outputs; the organic regime of docs/03 governs everything behind the contract line).
This is what makes departments able to pursue the RFP **independently**: they
coordinate through contract interfaces and the shared ledger, not through a central
director.

Contract rules:

- No department is the Checker of its own contract (SoD, non-negotiable).
- Every contract traces to a specific RFP requirement; an untraceable contract is scope
  creep at birth — delete it.
- Every RFP requirement traces to a contract; an uncovered requirement is a silent gap —
  the completeness check runs both directions.

The founder produces the **neutral profiles** (ROLE.md instances) for these departments — not a
runtime. **Running the org means projecting those profiles onto the chosen host harness(es)** and
letting that harness supply the perceive→decide→act loop, the tools, and the scheduling (docs/01
R0/R2; docs/09 §2). The founder never builds an execution engine; it authors the harness-neutral
source of truth that a host harness will read.

### 4. Design fully, activate minimally (docs/05)

Enumerate **every** department the RFP will ever need — including the maintenance-phase
watch and the handover packager — and declare them all, latent. Seed each role's
**doctrine** (docs/07: the starting normative playbook, with provenance) and the
**scope matrix** (docs/08: deny-by-default grants matching the contract seams). Then
compute the first activation set: the smallest group of departments the first milestone
requires, plus the control skeleton (gate, skeptic, supervisor, registrar — active
whenever anything is). Check the set against the span budget; if it exceeds a
supervisor's span on day one, the RFP's first milestone is too big — split the
milestone, not the rule.

The day-one chart is a **revisable hypothesis, not a prophecy**. Contingency theory and
emergent-strategy work (Mintzberg & Waters 1985) — and this repo's own docs/03 — say the
right structure is usually discovered by working the problem. The elastic model absorbs
this: the latent chart is cheap to amend through the moves catalog, and being wrong
about a future department costs a diff, not a reorg. Design ambitiously *because* the
design is revisable, not because it is final.

## Outputs

1. `organization.yaml` instance — full latent chart, activation flags, SoD matrix with a
   forbidden-pair entry for **every** maker, profile lineages, span budget, contracts
   (deliverable / standard / named checker / depends_on) per role, scope grants.
2. Ledger genesis entries — the RFP, the purpose, the contracts, seeded doctrines with
   provenance, the founding rationale.
3. The founding commit — which must pass `tools/org_lint.py` **and receive human
   charter approval** (`constitution.yaml: founding_commit`). The lint checks the
   chart's shape; only a human can judge whether an acceptance criterion is a gameable
   proxy — and Stinchcombe's imprinting result says founding conditions persist, so this
   is the cheapest moment to get control right. **An org cannot be born violating the
   rules it will be held to — nor without the humans signing the rules.**

## Founding is not "done" until it can LAUNCH

Spec completeness is **not** the bar. The founding is not finished until the minimal first
activation set can actually **launch on an existing host harness** — its profiles projected into that
harness's instruction files, reading their context-pack files, doing a cycle of real contract work,
with nothing bespoke in the loop (docs/01 S1/J2). A lint-passing, charter-approved chart that has
never been demonstrated to run is still provisional: R0 makes "it actually runs on a harness that
already exists," not "it is fully specified," the definition of done.

## What the founder must NOT do

- Write or alter the constitution (that is the humans' charter authority).
- Assign itself a standing role in the org it designs.
- Encode *methods* into contracts (that is the departments' organic space).
- Activate anything beyond the first milestone set — ambition is expressed in the
  *latent* chart, thrift in the *active* one.
