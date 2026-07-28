# 11 — The forced SDLC mold: the shape the work is made to travel through

*Part III · Operate — see [the four-part map](README.md).*

> **In one sentence:** an IT business company builds by forcing every deliverable through a
> non-skippable phase chain — requirements → design → implement → test → deploy → operate — and the
> chain is enforced by the *same* `requires_prior` mechanism the repo already uses to stop a maker
> from grading its own work (docs/03) and a manager from reporting up unverified work (docs/09),
> now generalized from *admission gating* to *phase gating*.

This doc adds no new machinery. It **lifts one mechanism the repo already has** — the ledger's
`requires_prior` idiom — from the two places it lives today to the one place the re-scope needs it:
the software-delivery lifecycle. Read it after docs/03 (which introduces routing and `requires_prior`)
and docs/09 (which instantiates it as spec-before-report-up); this doc generalizes both.

---

## 0. Why a mold, and why *forced*

THEORY §1b states the load-bearing reason: **AI is an amplifier.** Drop it into a process and it
magnifies that process — good and bad equally — and by accelerating the upstream it *degrades
stability* and shifts the binding constraint downstream to review, test, and deploy (DORA 2024–2025).
An amplifier without a mold does not go faster in any way that matters; it produces more, faster, of
whatever it was already producing — including defects that surface at the newly-moved bottleneck.

A human software org survives this because the lifecycle is carried tacitly: an experienced team
*doesn't* start coding before the requirement is understood, *doesn't* ship before the test passes —
not because a gate blocks them but because they'd be embarrassed to. An AI carries nothing it is not
given. Left to infer the lifecycle, an agent will skip straight from a one-line intent to a deploy,
because each local step looks locally reasonable and nothing tacit stops it. So the lifecycle, like
every other tacit organizational thing in this repo, has to be **made explicit and made checkable**.

**The deep purpose of the mold is reproducibility.** Forcing the phase order is not bureaucracy for
its own sake — it is what makes the outcome *converge*. An LLM is non-deterministic: hand the same
intent to two makers (or the same maker twice) and the generated code will differ. That variation is
accepted. What must **not** vary is the *process, the contracts, the gates, and the verification*:
given the same org spec + RFP, whoever founds the company, whenever they run it, the **same phases run
in the same order, the same gates must pass, the same contracts (interfaces, acceptance criteria,
ownership seams) are satisfied, and the same verification fires.** Two people building the same spec
get systems that *satisfy the same contracts and passed the same gates* — even if the code inside
differs. This is *process-and-contract reproducibility*, and it is the whole reason to force a type:
a mold is a shape that makes many pourings come out the same. Everything in this doc — the phase
predicate (§2), the deploy spine (§3), and the reproducibility admission standard (§4a) — exists to
make that convergence hold at two levels: **Level 1**, the org itself (same spec ⇒ same process/gates,
§1–§3); and **Level 2**, the *repositories the org builds* (the dev experience a stranger clones is
the same for everyone, §4a). Non-determinism is confined to the generated code; the mold makes
everything around it reproducible.

Two clarifications the repo's own lessons force:

- **The mold is promoted by doctrine, enforced by lint — never by forced delegation.** The standing
  lesson (docs/03 §6.5, the O8/O9 teeth; the delegation-vs-knowledge resolution) is that *forcing a
  fan-out* is a design error — fan-out is a judgment — while *forcing a checkable invariant* is
  correct. The phase order is a checkable invariant: "no `design_started` without a prior
  `requirements_signed_off`" is a ledger predicate, exactly like "no `result_deployed` without a
  prior `survives`." So the mold is enforced the right way: doctrine says *this is how we build*
  (loaded every cycle), and a lint/hook tooth refuses the few transitions that must not skip.

- **The mold is a shape, not a waterfall.** Forcing the phase *order* per deliverable does not force
  big-batch sequential delivery. A deliverable is small (docs/03: near-decomposable units), and each
  small unit travels the full chain quickly and continuously — this is the always-shippable trunk, not
  a six-month cascade. The mold constrains *ordering within a unit of work*, not *batch size* or
  *concurrency across units*. Ten units can each be at a different phase at once (that is the pipeline
  of docs/09's backlog); no single unit may jump its own phases.

---

## 1. The seven phases and what each admits

Each phase produces an artifact the next phase depends on, and each transition is a **gate**: the
next phase may not start until the prior phase's artifact carries an admission verdict in the ledger.
The gate is the generalization of docs/03's `output_to: gate → skeptic` and docs/09's
`conformance_reviewed` — the same `requires_prior` predicate, one row per phase boundary.

| Phase | Produces | Gate to enter the *next* phase (the `requires_prior`) |
|---|---|---|
| **requirements** | a stated intent + acceptance criteria (what "done" and "valuable" mean) | `requirements_signed_off` — the intent is grounded in the purpose (Organ 1), not in volume |
| **design** | an approach + the seams it will touch (`owns:` sets, interfaces) | `design_reviewed` — conforms to the requirement (docs/09 A3 conformance, applied one phase up) |
| **implement** | the deliverable | the maker's own `judge` (docs/03 §3.1.1 — *not* admission) |
| **test** | evidence the deliverable meets the acceptance criteria (its own unit tests green) | `admission_decided{admit}` by the **gate**, then `refutation_attempted{survives}` by the **skeptic** (docs/03) — the existing maker→gate→skeptic chain, per-unit |
| **integrate** | the unit merged into the integration branch (`develop`) and passing the *combined* suite alongside its siblings | `integration_admitted` — the fanned-out siblings build and test **together** green on `develop` (§6). This is where fan-out fans back in; green CI on `develop` is its machine form |
| **deploy** | the change, live (`develop` → `main`) | `result_deployed` — requires the prior `survives` (today's schema) **and** a healthy reliability budget (docs/05 §reliability-budget); CI/CD is the spine (§3) |
| **operate** | monitoring, corrective fixes, the realized-outcome record | `outcome_recorded` (docs/05 OUTCOME-DELTA) feeds back to requirements — the loop closes |

The important observation: **the repo already implements the two hardest gates.** The
test→deploy boundary *is* the maker→gate→skeptic chain from docs/03 (`result_deployed` already
requires a prior `survives`). The design→implement conformance *is* docs/09's `conformance_reviewed`.
This doc's job is only to (a) name the phases as a chain so the *earlier* boundaries
(requirements→design, design→implement) get the same `requires_prior` treatment, and (b) give the
deploy and operate phases their home (§3, §4).

---

## 2. Enforcement: the phase-gate tooth (generalizing `requires_prior`)

The ledger already refuses `result_deployed` without a prior `refutation_attempted{survives}`, and
refuses `report_up` without a prior `conforms` (docs/09). The phase mold adds the analogous refusals
for the earlier boundaries, as one uniform predicate:

```
phase_started{deliverable, phase: P}  is INVALID unless
    the ledger holds  phase_admitted{deliverable, phase: prior(P), verdict: pass}
```

where `prior(requirements)=∅` (the first phase needs no predecessor), `prior(design)=requirements`,
and so on. This is deliberately the *same shape* as `result_deployed requires_prior survives` — a
new operator would be a second mechanism to maintain; a reused predicate is one mechanism pointed at
a new set of events.

**Where the tooth lives** follows docs/10's request-vs-enforcement split exactly:

- **Doctrine (the request layer, p<1):** every cycle's context pack carries "we build through the
  phase chain; do not skip." This is where the *norm* lives — it makes the right thing the default and
  is cheap to update as practice evolves (docs/06).
- **Lint/hook (the enforcement layer, p=1):** `org_lint` refuses an organization whose routing lets a
  phase's output reach deploy without traversing its predecessors, and the PreToolUse hook refuses a
  spawn that asserts a `phase_started` with no admitted predecessor in the ledger — the same place the
  seam-gate and blast-radius cap already sit. A must-not-skip belongs in the deterministic layer, not
  in a prompt that an amplifier can rationalize past.

This is the whole enforcement story: no forced delegation, no new organ, one predicate generalized.

---

## 3. Deploy is a phase, and CI/CD is its spine (R0-consistent)

The deploy phase is where "always-shippable" becomes real, and it is realized on the **host**, not
built by the org — the same R0 discipline as scheduling (docs/08). A software company's deploy spine
is **CI/CD (GitHub Actions)**: the org *declares intent* into a workflow (build, run the test phase's
evidence, gate on `survives` + budget, then release), and the host runs it. The org authors and
maintains the workflow as an owned asset (a maker deliverable, gated like any other); it does not
implement a pipeline runner. GitHub Actions is to the deploy phase what cron/`/loop` is to the
metabolism: a host primitive the org borrows.

This makes the deploy gate concrete and auditable: a green pipeline that includes the `survives`
check and the budget check *is* the machine form of `result_deployed`'s `requires_prior`. The
enforcement is not a hook watching a human — it is the pipeline refusing to release without its
predecessors, on infrastructure the industry already built.

docs/08 gains one delegation row for this (CI/CD + deploy target = host-provided); this doc names why
the deploy phase belongs there.

---

## 4. Operate closes the loop back to requirements

The operate phase is not the end of the line; it is the edge that makes the chain a *loop*. What a
deployed change actually did in the world is recorded (docs/05's OUTCOME-DELTA — the realized outcome
joined to the decision that predicted it), and that record re-enters as evidence for the *next*
requirement: the aspiration levels of problemistic search (docs/09) and the DORA metrics that
navigate to the moving bottleneck (docs/05 §DORA) both read from here. "The system and the
organization grow together" (THEORY §1b, Organ 7) is this edge: operate → requirements is where the
running product teaches the company what to build next, and where a repeatedly-missed outcome becomes
a reshape signal rather than a silent drift.

The reliability/error budget that bounds how fast deploy may fire is an operate-phase instrument and
lives with the other 24/7 operating events in docs/05 (it is a sibling of BLAST-RADIUS-CAP: an
aggregate limit over a window that gates action). This doc only notes that the deploy gate reads it;
the budget mechanism itself is docs/05's.

---

## 4a. Level 2: the repository the org builds must be reproducible for anyone

§1–§4 make the *org's* process reproducible (Level 1). But an IT business company's output is a
**repository**, and a repository is only reproducible if a stranger who clones it gets the same system
the maker did — installs the same dependencies, runs the same tests green, builds the same artifact,
on any machine, on any day. The generated *code* may vary (LLM non-determinism, accepted); the
**dev experience** must not. So the mold forces a **reproducibility admission standard** on the
repositories it produces, checked at the implement → test → deploy gates exactly like any other
`requires_prior` — a deterministic tooth, not a maker's "I verified it" self-claim.

A candidate deliverable is **not admissible** past the phase named unless its repository carries:

| Artifact | Phase gate | Why it is a reproducibility requirement |
|---|---|---|
| **A committed lockfile + a populated, version-pinned manifest** | implement → test | `clone → install` must resolve to *one* dependency tree on every machine and every day; a manifest with version ranges and no lockfile resolves differently over time (the タテカエ failure: manifest with no deps, no lock). |
| **A pinned toolchain** (`.nvmrc` / `.tool-versions` / `engines`, per-language) | implement → test | the same source transpiles/builds/tests identically only on a pinned runtime; an unpinned node/deno/python floats the result. |
| **A one-command setup and a one-command test, documented in a README** | test → deploy | "verified end-to-end" must be reproducible *by a stranger from a clean clone*, not asserted by the maker; the **gate re-runs both from a fresh checkout** rather than trusting the claim. |
| **Idempotent, re-runnable migrations + a one-command DB bring-up** | test → deploy | a second developer must be able to bring up state deterministically; bare `create table` (no `if not exists`, no seed, no apply command) is not re-runnable. |
| **A committed `.env.example` enumerating every required variable (names only)** | test → deploy | the *set* of required secrets must be discoverable, or a stranger's setup fails with no manifest of what to provide (secrets themselves stay gitignored). |
| **A committed CI workflow (GitHub Actions) that runs setup + test from a clean clone, and is green** | deploy | this **is** the machine form of the deploy gate (§3): a green from-clean pipeline is reproducibility *proven continuously*, not a one-time local pass. The doctrine already names CI/CD (docs/01 J12); this makes it an admission artifact, not an aspiration. |

The enforcement mirrors §2: **doctrine promotes** ("we ship repos anyone can clone-and-run" — in the
maker and gate contracts), and a **deterministic lint tooth enforces** the checklist at each gate.
That tooth is `tools/repro_lint.py` — `repro_lint check <repo> --phase implement|test|deploy` returns
0 (artifacts present) or 10 (HOLD: a required artifact is missing), tagged by the phase that first
requires each artifact, so an implement candidate is held to a lighter bar than a deploy one. It is a
*presence* check (deterministic: same repo ⇒ same verdict); the **deploy** gate additionally re-runs
setup + test from a clean clone (the CI workflow, §3) — presence is the cheap first tooth, the
clean-clone re-run the expensive second. This is what makes two makers, handed the same spec, ship
repositories that are *equally reproducible* — the Level-2 counterpart to the Level-1 phase gate.
Without it, the repo's dev experience is a free maker choice and diverges; with it, "clone → one
command → the same running, tested system" holds for everyone.

---

## 4b. The spec / plan / tasks layering — SDD, mapped onto the Issue hierarchy

The canonical Spec-Driven Development form (GitHub Spec Kit, AWS Kiro; docs/sources) splits the front of
the lifecycle into **three artifacts**, each a checkpoint before the next: **spec** (WHAT — user stories
+ acceptance criteria), **plan** (HOW — architecture, data model, API contracts, libraries), **tasks**
(the WHAT broken into *atomic, independently-completable units* with dependency order, a parallel marker,
and exact file paths). orgforge adopts this layering — but it does **not** create `spec.md`/`plan.md`/
`tasks.md` *files* (that is the fragment-Spec trap docs/12 §6 forbids; the SSoT is code + the domain
model, not a pile of task files). Instead the three layers **map onto the GitHub Issue hierarchy** the
org already has (docs, web-harness):

| SDD layer | orgforge home | contents |
|---|---|---|
| **spec** (WHAT) | the **objective Issue** (`kind:objective`) | user stories + acceptance criteria in **EARS** (below); tech-stack-agnostic |
| **plan** (HOW) | the objective's **design** (its body / a design comment), admitted at the `design` phase | architecture, data model, API/seam contracts, library choices |
| **tasks** (atomic units) | the **task sub-issues** (`kind:task`), one per atomic unit | each an independently-completable unit (one endpoint/function, not a whole domain), with `depends_on` (order), a boundary (`owns` disjoint from siblings = the `[P]` parallel-safe marker), and its entry files (the exact paths) — the SPEC structure |

**Acceptance criteria use EARS** (Easy Approach to Requirements Syntax) so a MUST is testable and
AI-parseable, not prose: *Ubiquitous* ("the system SHALL log every auth attempt"), *Event* ("**WHEN** a
user submits login **THE system SHALL** validate credentials"), *State* ("**WHILE** a sync runs **THE
system SHALL** show progress"), *Unwanted* ("**IF** validation fails 3× **THEN THE system SHALL** lock
the account"), *Optional* ("**WHERE** MFA is enabled **THE system SHALL** require a TOTP"). The SPEC's
MUST list (template/SPEC.md) is written in these five patterns.

The upshot for granularity (the "split finer" concern): **a task sub-issue is ONE atomic unit**, not a
domain. The discriminator is the `owns` set — split at every seam where sibling `owns` sets are disjoint
and `depends_on` is a pinned one-directional contract (`[P]`-parallel-safe); keep single-threaded only
what needs reciprocal back-and-forth (docs/03 §6.2 — over-splitting coupled work is 17× worse, docs/12
§6). A lint flags an Issue whose acceptance criteria span multiple disjoint `owns` territories as a
re-split candidate (a *shape* check, not a quality judgment).

---

## 4c. The integration seam — feature → develop → main, and where fan-out fans back in

docs/03 fans work **out** into parallel task sub-issues; the theory it rests on (Lawrence & Lorsch, via
docs/03 §2) warns that **whatever you separate, you must pay to reintegrate**. The `integrate` phase
(§1) is that payment — the point the parallel deliverables come back together and are tested *as a
whole*, before any of them deploys. It is realized on git branches (R0: borrow git/GitHub, build no
runtime):

- **feature branch per task.** Each task sub-issue opens `feat/issue-<N>-<slug>` off `develop`. The
  branch name is deterministic (`github_sync branch --issue N`), so it is reproducible the way Issue
  creation is (docs/11 §0). A task's work happens on its own branch — siblings never collide.
- **`develop` is the integration branch.** A task's per-unit `test` passing (its own suite green) admits
  it to merge into `develop` — **not** into `main`. `main` is release-only.
- **the `integrate` phase gate = green CI on `develop`.** Once siblings have merged, the combined suite
  must build and pass **together** on `develop`. That green run is `integration_admitted` (the same
  `requires_prior` idiom: `result_deployed` may not fire without it). Green CI on `develop` is the
  machine form of the integrate gate, exactly as green CI on `main` is the machine form of deploy (§3).
  This is the state a human reviews against: the work is *merged into `develop` and testable there* —
  not a pile of per-task PRs against `main` that were never assembled.
- **who owns it.** No new "integrator" rank (docs/09 §1 forbids minting PM ranks). The **supervising
  manager's A3 accountability** (docs/09 — "verify subordinate work against its contract") is *extended*
  from per-child conformance to the **cross-deliverable integration test on `develop`**: the manager
  who fanned the work out owns bringing it back together and proving it works assembled.
- **deploy is `develop` → `main`.** Only an integrated, green `develop` promotes to `main` (deploy, §3),
  keeping the trunk always-shippable (docs/11 §0) with the integration buffer in front of it.

So the hand-back a task submits is a **PR against `develop`** (not `main`), and "done for review" means
"merged to `develop`, integration-green" — the reviewer reads a develop that actually runs.

---

## 5. What this doc is, and is not

- It **is** the declaration that an IT business company builds through a fixed phase order, and that
  the order is enforced by generalizing the one `requires_prior` predicate the repo already runs.
- Its **purpose is reproducibility** (§0): the mold makes the process, contracts, gates, and
  verification converge across founders and runs at two levels — the org itself (§1–§3) and the
  repositories it builds (§4a) — while the generated code stays free to vary.
- It is **not** a new runtime, a new organ, or a forced fan-out. The phases are content of Organs 2,
  4, and 6 (THEORY §1b); the enforcement is the existing lint/hook layer; the deploy spine is a host
  primitive (docs/08).
- It deliberately **references rather than restates** docs/03 (routing, the maker→gate→skeptic chain),
  docs/09 (conformance as a phase gate), docs/08 (R0/host delegation), docs/05 (reliability budget,
  DORA, OUTCOME-DELTA), docs/09 (the backlog pipeline), docs/03/16 (decomposition and the
  request-vs-enforcement split). If any of those change, this doc follows — it holds no independent
  copy of their mechanisms, only the one generalization that ties them into a lifecycle.
