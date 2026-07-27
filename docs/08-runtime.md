# 08 — Execution: Delegate to the Host Harness, Project the Profile

*Part II · Design — see [the four-part map](README.md).*

> An agent organization does not need its own execution engine. The repository's first
> principle (docs/01, R0) and its thesis (THEORY.md) hold that **the harness and the loop
> are organs the industry already built.** A department does not need a new runtime. It
> needs an *existing* one — Claude Code, Codex, or any general coding agent — pointed at a
> working directory whose instruction file is this role's projected profile. This document
> describes that: what the system delegates, what thin layer it adds, and what the host must
> provide.

---

## 1. The delegation principle

**A department is a host harness running in a working directory; the harness supplies
perception, tools, memory, and the control loop.** The system does not intercept the
agent's every action through a bespoke choke point — it configures the harness the agent
already runs on, using that harness's own mechanisms:

| Organ / need | Who provides it | How the system expresses it |
|---|---|---|
| Perception, tools, memory (Organ 3) | **Host harness** | The projected profile + the harness's file/tool access; scope via which files land in the working dir |
| Perceive→decide→act loop, stop, iteration cap (Organ 4) | **Host harness** | Declared `loop.cadence` / stop intent; the harness enforces it |
| Token budget, no-progress halt | **Host harness** | Declared budget intent; the harness's own budget/turn caps enforce it |
| Scheduling (activate on cadence) | **Host environment** | The schedule as data; a cron / CI trigger / the harness loop fires it |
| CI/CD + deploy target (the deploy phase, Organ 6 / docs/11) | **Host environment** | The org authors a workflow (GitHub Actions) as an owned deliverable; the host builds, runs the test evidence, and releases — the org ships no pipeline runner |
| Tool permissions, sandboxing, secret custody | **Host environment** | Chosen to fit the org's threat tier (docs/01 §5); the system does not reimplement it |
| The org skeleton (who/what/checks) | **This repository** | organization.yaml, constitution.yaml, moves/sensors/schemas |
| The shared record | **Host storage + this repo's schema** | An append-only store the host provides; ledger-schema.yaml defines its shape |
| Audit of the skeleton | **This repository** | tools/org_lint.py |

The thin layer this repository adds on top of an existing harness is exactly three things:
**(1) the neutral profile and its projection, (2) the declarative skeleton + schemas, and
(3) the lint.** Everything else is delegated. If a proposed mechanism is not one of those
three, ask first whether the host harness already provides it (C4).

## 2. The projection (the only harness-specific layer)

A role's profile is authored once, harness-neutral (template/ROLE.md). To run a department
on a given host harness, the profile is **projected** into that harness's instruction-file
convention — the file the harness reads on launch to know its job:

- The neutral profile is the **source of truth**; the per-harness instruction files are
  **generated views**, regenerated from it, never hand-forked (the derived-view discipline
  of Organ 5, applied to profiles).
- Projection assembles, into the working directory, what docs/07's context-pack formula
  requires: the intent block, the role's contract and doctrine, the granted views of the
  shared record, and nearby failures — as files the harness reads. "Assembling the context
  pack" is **writing those files into the working dir before launch**, not running a
  bespoke `registrar` process. (The registrar role, where present, is itself just another
  department running on a harness; it authors reorg *diffs* as work products — it is not
  the execution engine.)
- The projection is the **one place** harness-specific knowledge lives. Porting the org to
  a different harness changes only which instruction files are generated and how the
  launch/stop/schedule signals are wired — nothing in the skeleton.

*Deliberately unspecified here (docs/01 §7, open question 1):* the exact instruction-file
names to target and whether to lead with a neutral filename or a specific convention with
others as fallback. That is a projection-format decision; the skeleton is identical under
any choice.

## 3. What the host harness must provide (the delegation contract)

For a department to run, its host harness/environment must supply — and most general
coding agents already do:

- **An instruction file it reads on launch** (where the projected profile lands).
- **File read/write in a working directory** (perception and action over the pack + the
  role's outputs).
- **Tool execution** with **permissions/sandboxing appropriate to the org's threat tier**
  (docs/01 §5) — for a Tier-A documentation org, ordinary file tools; for a Tier-B
  asset-touching org, a sandboxed environment with credential custody. *The system chooses
  a host that provides the needed isolation; it does not build isolation.*
- **A control loop with stop conditions** (turn/iteration caps, a token budget) — Loop
  engineering, which the harness already implements.
- **A launch/stop signal on a schedule** (a scheduler the environment provides).
- **A CI/CD pipeline and a deploy target** (GitHub Actions and a deploy environment) —
  the spine of the SDLC mold's **deploy phase** (docs/11 §3). The org *declares intent*
  into a workflow (build → run the test phase's evidence → gate on `survives` + error
  budget → release) and the host runs it; a green pipeline carrying those checks is the
  machine form of the deploy gate. **CI/CD-as-host is exactly the R0 discipline already
  applied to scheduling** — GitHub Actions is to deploy what cron / `/loop` is to the
  metabolism, and GitHub is the natural web-projection environment for a software company's
  work. The org authors and maintains the workflow (a gated maker deliverable); it does not
  implement a pipeline runner.
- **An append-only place to write the shared record** whose shape matches
  ledger-schema.yaml.

If a host lacks one of these, that is a host-selection problem, not a thing this repo
implements. The baseline assumption (docs/01 R2.5) is a general coding agent; richer hosts
(native sub-agents, managed memory, managed scheduling) are optional accelerators.

## 4. Loop, schedule, and budget — declared here, enforced there

The skeleton declares *intent*; the host enforces it. Concretely:

- **Cadence** (`loop.cadence: every_4_hours` / `on_candidate_arrival`) is a schedule the
  host's scheduler realizes — a cron entry, a CI trigger, or the harness's own loop. The
  system never ships a scheduler (docs/01 R2.3).
- **Stop conditions** (a verifiable goal met, no-progress, iteration cap) are the host
  loop's own stop mechanisms; the skeleton names the goal, the host stops on it.
- **Budget** (a per-window token cap, the no-progress rule) maps onto the host's budget/turn
  controls. "24-hour operation" is the host running the schedule unattended, with the
  approval queue (docs/05) holding charter/irreversible actions for the operator — not a
  bespoke daemon.

## 5. Control enforcement — split by threat tier (docs/01 §5)

The maker/checker line and separation of duties (Organ 6) must hold at runtime, not just
in the lint. *How* they're enforced depends on the threat tier the org is deployed under:

- **Tier A (drift & honest error — every org).** Enforced by **structure the projection
  guarantees**: a maker's context pack routes its positive results to a *different*
  department (its checker); the checker runs on its own harness instance with its own
  profile; no department's projection gives it its own admission authority. This is
  separation of duties realized as *which files land in which working directory* — no
  runtime interception needed. The lint proves the skeleton has this shape (O6/O6b/O6c/O7);
  the projection preserves it at launch. This tier is always on.
- **Tier B (adversarial optimization — asset-touching orgs only).** When a department can
  reach real assets/production/funds, structural separation is not enough — you also need
  the host *environment* to provide write-authorization, tamper-evident records, credential
  custody, and sandboxing. **These are host-environment features you select, not runtime you
  build** (docs/01 R2, C4): run such an org on an environment whose sandbox and permission
  model already provide them. The system's job is to *require the right host* for the tier,
  and to keep the irreversible-action approval gate (docs/05) between "prepared" and
  "executed."

Tier-B guarantees are not built inside this repo. Under R0/C4 that would be the
wrong layer: for asset-touching orgs, choose a host environment that provides a mediation
layer, effect classification, and an external watchdog; for the
common Tier-A org, structural separation + the approval gate + the lint suffice.

## 6. Conformance — restated as delegation, not implementation

An organization built from this repo is *runnable* when, on a chosen host harness:

- [ ] a department launches with its projected profile as the harness's instruction file,
      reads its context-pack files, does a cycle of contract work, and writes its output —
      **with no bespoke runtime process involved** (docs/01 S1/J2; the load-bearing test)
- [ ] a maker's positive result is routed to a *different* department as checker, enforced
      by what the projection writes into each working dir (Tier-A SoD)
- [ ] the role's cadence, stop condition, and token budget are realized by the host loop /
      scheduler, from the declared intent
- [ ] the shared record is an append-only store the host provides, shaped per
      ledger-schema.yaml
- [ ] charter/irreversible actions are held for the operator's approval queue (docs/05),
      and — for a Tier-B org — the host environment provides the sandboxing/custody the tier
      requires
- [ ] the lint passes on the skeleton and every reorg diff

The first box is the one that matters: **until an org from this template actually launches
and does useful work on an existing harness with nothing bespoke in the loop, R0 is unmet.**
That, not spec completeness, is the definition of done.

*Status: the remaining implementation work is the projection layer (docs/01 §7 open
question 1) and broader end-to-end demonstration on a real host harness (docs/01 S1–S6) —
deliberately small, because the heavy organs are the host's, not ours.*
