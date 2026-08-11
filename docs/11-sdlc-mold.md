# 11 — The forced SDLC mold: the shape the work is made to travel through

*Part III · Operate — see [the four-part map](README.md).*

> **In one sentence:** an IT business company builds by forcing every deliverable through a
> non-skippable phase chain — requirements → design → implement → test → integrate → deploy → operate — and the
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

## 0a. The founding artifacts have FIXED filenames — the rule, not a suggestion

Founding (`/org-found`) runs *before* the phase chain: it turns an RFP into the org's scope and
structure. Its outputs are the base every later phase reads, so they are the one place where **file
names are part of the contract**. If founding writes `architecture.md` one time and `design-overview.md`
the next, nothing downstream can find its input without a human pointing at it — a later command, a
fresh session, or a web harness has to *guess*. That guess is exactly the tacit-not-articulated failure
the repo exists to prevent, and it breaks reproducibility at its root (§0): two foundings from the same
RFP must produce the same *addressable* artifacts, not merely similar prose.

So founding writes **exactly these four files, at the org root, under these exact names**:

| File | SDD/lifecycle role | What it holds |
|---|---|---|
| `REQUIREMENTS.md` | the received brief | the RFP verbatim (or the brief restated), + the one-sentence purpose. The immutable input the rest traces to. |
| `FEATURE-INVENTORY.md` | the full sweep | every capability the RFP requires, grouped must / should / nice, + the explicit EXCLUDE list |
| `ARCHITECTURE.md` | **the whole-system design**, distinct from any per-task spec | layers/components + the **seam contracts** between them, each in the normalized shape `{deliverable, standard, checker, depends_on}` |
| `coverage-manifest.md` | the RFP→contract coverage map | one row per must-have: `{rfp_capability, owning_role, deliverable, acceptance}` |

Plus `organization.yaml` (the machine-checkable side of the manifest), which already had a fixed name.

Three consequences that make this load-bearing rather than cosmetic:

- **`ARCHITECTURE.md` is the whole-system design, and it is NOT an SDD artifact.** SDD's three layers (§4b) —
  spec / plan / tasks — live in the *Issue hierarchy* and are per-objective and per-task. `ARCHITECTURE.md`
  sits *above* all of them: it is the whole-system design the objectives are carved out of, authored once
  at founding and amended at reorg. Keeping it a file (not an Issue) is deliberate — it is not disposable
  work surface, it is the standing shape of the system. It does not contradict §4b's "no `plan.md` files":
  that rule forbids **per-task** fragment files, which rot; a single whole-system design does not fragment.
- **Downstream commands address these by name, not by search.** `/org-decompose` reads
  `coverage-manifest.md` + `ARCHITECTURE.md` to mint task Issues; `/org-init` scaffolds their paths. A
  fixed name is what lets a command take the artifact as *input* instead of asking the operator where it is.
- **The names are the same in every org.** A stranger — or an agent with none of the founding context —
  opening any orgforge org finds the design in the same place. That is Level-1 reproducibility (§0)
  applied to the founding artifacts themselves.

`ARCHITECTURE.md` (the org's own repo has one too, describing orgforge) is the whole-system design *of the
product the org builds*, written into the product/org root — not a copy of this repo's file.

---

## 0b. The format of the requirements conforms to a standard — fix the content, not just the name

§0a fixed the **file names** of the founding artifacts. It prescribed nothing about **the format of
their content**, so an agent invented the structure afresh at every founding. If the same
requirements produce documents of different structure, §0's claim — "same spec ⇒ same process, same
contract" — is **already broken at the layer where requirements are written**. Fixing the names and
leaving the content is the same as standardising the vessels and asking nothing of what goes in.

### Level of conformance: tailored conformance to ISO/IEC/IEEE 29148:2018

We declare the form of conformance that standard's §4.5.2 formally recognises. **Not all twenty SRS
clauses (§9.6) are adopted** — `Memory constraints`, `Site adaptation requirements`, and
`Logical database requirements` are clauses for embedded, defence, and regulated industries, and in
a small product they become empty fields or boilerplate. **A document lined with empty sections
stops being read and eventually stops being updated.** The four adopted are:

| clause | content | check |
|---|---|---|
| §5.2.4 | syntactic rules (subject + `shall`; `must` is not used, as it is mistaken for a requirement) | warning |
| §5.2.5 | the nine characteristics of each requirement (Verifiable / Singular / Unambiguous …) | partly mechanised |
| §5.2.6 | the five characteristics of the set (no TBD/TBS/TBR left, no contradiction or duplication) | fails on TBD |
| §5.2.7 | **the words to avoid** (subjective, superlative, loophole, universal, vague conjunction) | **fails** |

§5.2.7 is the substance. "Easy to use", "if possible", and "in all cases" either **change their
verdict from person to person**, **become an excuse not to implement**, or **leave the existence of
exceptions unverified**. They are especially dangerous in a sentence handed to an AI agent: a vague
word flows straight into the implementation as room for a guess.

### What is adopted alongside it

- **EARS** (Alistair Mavin / Rolls-Royce; adopted by Airbus, NASA, Bosch, Intel, and Siemens) —
  its six patterns and the ruleset "**at most one trigger**". That constraint **enforces the
  granularity of a requirement at the syntactic level**. It costs effectively nothing to learn and
  gives the largest effect. It satisfies §5.2.5's *Conforming* at the same time
- **Given-When-Then** (only the notation, borrowed from Gherkin in Cucumber's official
  specification) — the acceptance criteria. Requirements in EARS, their verification scenarios in
  GWT
- **the `[NEEDS CLARIFICATION]` marker** (from GitHub Spec Kit) — **the most important one**. It
  stops something ambiguous from being implemented on a guess. Left unresolved, the lint fails
- **Non-Goals / Alternatives Considered** (from Google's Design Doc) — the cheapest device there is
  for stopping scope creep

The prescription is `template/REQUIREMENTS.md` and the check is `tools/req_lint.py`. `/org-found`
calls both.

### Why "RFP" was dropped

An RFP (Request for Proposal) is **a procurement document**. A commissioning party issues it to
solicit proposals from **competing external vendors** and **evaluate them comparatively to select a
party to contract with**. Its core is the evaluation criteria, the scoring, the required proposal
format, and the contract terms — and in in-house development (a single implementing party, an
interior that is visible, negotiation available at any time) **all of them become meaningless**.

The exact counterpart of what is written here is 29148's **StRS (Stakeholder Requirements
Specification)** — a document describing needs from the commissioning side, before stepping into a
solution. The file is named `REQUIREMENTS.md` (it carries no standard's acronym, and misleads
nobody).

The one thing worth borrowing from an RFP is **the discipline of documenting the evaluation criteria
in advance**, which in in-house development translates to "**settle the acceptance criteria before
implementing**". In this template §4 (Acceptance) and §5 (Success Criteria) carry that, and
`coverage-manifest.md` carries its mapping onto the contract.

---

## 0c. Work only a human can carry out becomes an Issue too — it does not fall into prose

§0a fixed the names of the founding artifacts and §0b the format of the requirements. Both concern
"what the org produces". A real founding, however, always contains **work the org is structurally
incapable of carrying out**:

- creating and billing accounts on external services (Supabase, a payment provider)
- registering an OAuth client, issuing an API key
- acquiring a domain, registering as a store developer and submitting for review
- GitHub's administrative settings (branch protection, registering secrets)

None of these complete within the org's tools, so **asking the CEO** is the only option — and that
request appeared only in the prose a command printed. In a founding in the field, three of them were
written into the text as "handover notes" and **left neither on an Issue nor in the ledger**.

### Why prose does not work

| what is lost | what actually happens |
|---|---|
| **persistence** | it vanishes when the session ends. `/org-resume` reads the ledger, so it is not restored |
| **a correct board** | `/org` reports "every Issue ready, GREEN" while nothing can actually be started |
| **a correct ready** | waiting on a human cannot be expressed as a dependency, so a blocked task reaches a maker |
| **correct coverage** | `coverage-check` only asks "did it become an Issue". It reports 66/66 with a prerequisite missing |

The last is the most telling: **setting branch protection is part of §4e's layer of mechanical
refusal**, and yet it is a GitHub administrative setting that code cannot achieve. Vanishing into
prose, it leaves a hole in the layer that "the machine is supposed to guard", with nobody noticing.

### The rule

**`/org-found` and `/org-decompose` file the prerequisites only a human can carry out as Issues.**
`github_sync needs-human` is the dedicated entry point for that, and it raises the
`orgforge:needs-human` label.

The test is simple: **does it complete within the org's tools?** If not, it is a human task.

The sources to extract from are already at hand — `REQUIREMENTS.md`'s **Open Questions** (what you
yourself wrote as "decide before implementing") and **Assumptions** (what you wrote as "the CEO
provides this") are standard 29148 sections and sit somewhere a machine can read. Making those
sections required in §0b was partly to make this work.

The Issue it files has the same shape as an ordinary task, so a downstream one can be bound with
`--blocks` and `Depends on: #N`. Until the human's work is closed, whatever depends on it does not
appear in `ready`.

**On `/org`'s board it appears at the top, as RED.** What "is waiting on you" is precisely what a
board is for, and a board that does not show it is lying.

> **A request to a human is the kind of work that stops things longest when it is forgotten.** For
> an org to structure only its own work and let its requests to a human fall into prose is to put
> the thing most likely to stall in the place most likely to lose it. It should be the other way
> around.

---

## 0d. Automate the plumbing; do not automate the judgment

§0a through §0c fixed "what is written". This section is about "**who types it**".

`/org-work` was for a long time a prose instruction to "type these events". An agent was what
executed it, and in the field **eleven commands were typed by hand per two Issues**. Eighteen Issues
comes to around ninety, and one mistake among them breaks the ledger's consistency.

Worse was how `parent` was handled. A phase chain inherits the parent objective's admit (§2), and yet
**a human picked that value out of the Issue by eye and typed it in**. **Implementing the inheritance
changes nothing while the value is typed by hand** — not picking up what can be picked up is
negligence in the design.

### The line: plumbing, or judgment?

| | examples | who |
|---|---|---|
| **plumbing** (the order and actor are settled) | claim → spec_delegated → phase_started → cycle_started → log → stage / cutting a worktree per Issue / generating the seam contract / injecting the charter and the SPEC / carrying the gate's findings to the skeptic / the `decide` template | **the tool** (`org_cycle.py`) |
| **judgment** (the role's work) | what to choose / whom to delegate to / whether to split / whether to admit / the verdict, why, and risk / which mutation to try | **the role** (not automated) |

**That `verify` does not fill in the verdict is the least negotiable point on this line.** The
moment a tool decides the verdict, the gate becomes a formality and an admission falls to "a ritual
in which a role transcribes a string the tool produced". What may be filled in is **the material**
(the charter, the SPEC, the seam, the gate's findings); **the conclusion** comes from the role.
The opposite state — a human writing the material out afresh each time — is equally bad: a human
writing the verification procedure shifts the strictness with each writing, and eighteen Issues
produce eighteen standards. The standard has one source, `agents/<role>.md`, and a change there
takes effect everywhere.

**No double bookkeeping — one command writes.** A judgment stays in both the Issue and the ledger
(the reason on the Issue; the receipt and digest in the ledger), but **it is typed once**. The
earlier design had `decide` write to the Issue and a human type `ledger append` separately, and in
operation one side went missing again and again (no refutation record in the ledger; zero
`progress_recorded`). The actor was already passed through `--by`, so there was no reason to
separate them.

The order is **the ledger first, the Issue second**. The controls (refusing self-approval, order
violations) live in the ledger, so writing to the Issue first and then being refused leaves the
worst kind of mismatch visible from outside: "the Issue says admit but the ledger has nothing". If
it is refused, stop before any record visible from outside exists.

**An idempotency key must not become a back door around the controls.** An idempotent no-op is
limited to "a re-run of the same logical event by the same actor". While only
`(class, natural_key)` was read, a matching key made it a no-op even with a different actor, and
neither DISTINCT_ACTOR nor REQUIRES_PRIOR was **even evaluated** — a maker using the same key as
the gate's judgment got a self-approval through at exit 0. Idempotency is a mechanism for
protecting a re-run, not a path around the controls.

**A correction is a first-class event.** An append-only ledger cannot erase the past. A record
written in error, and a probe written to verify the specification, both stay there. Settling for a
free-text note leaves it **unreadable by machine** — verification probes were counted as real
judgments and the board kept displaying "admitted, but no record from the skeptic", at odds with
reality. `correction{corrects, kind}` declares the void, and `kind: probe|mistake` is excluded from
the counts. `backfill` (a real judgment written afterwards) and `superseded` (replaced by a later
judgment) are not excluded — the first is a valid judgment, and the second belongs to the
chronological resolution that "the latest judgment on a deliverable is the live one".

**A control must not vanish through variation in identifiers.** The human side wrote Issue numbers
(`deliverable` / `issue`) while the enforcement logic read `candidate_id` / `claim_id`. Both point
at the same work, and reading only one let both a self-approval and a deploy without refutation
walk straight through in the field. If a control's effectiveness depends on which key the writer
used, it is not a control. The correspondences present in the ledger (`pack_manifest_id:
"issue-7"` and the like) are followed to resolve identity, and **a judgment that cannot be
correlated is refused**. Walking through is the worst outcome because the hash chain then lends its
endorsement to a forgery, with nobody able to see that the control is not in effect.

**A worktree is a worked example of an invariant judgment cannot protect.** In a parallel fan-out,
the accident of one Issue's commits landing on `feat/issue-8-settle` actually happened. `git
checkout` switches the whole tree, so for as long as parallel makers share one tree it recurs as a
structural problem rather than a problem of care.
**A design that assumes "judge correctly every time" breaks** — which is why `begin` separates
`.orgforge/wt/issue-<N>/` physically. This is a forced invariant, not forced delegation.

This follows exactly the line docs/03 §6.5 draws — **forced delegation is a design error; a forced
invariant is right**. What `org_cycle` automated is only the latter: whether to fan out and whether
to admit both remain the role's judgment.

### Three properties

1. **Automatic resolution** — `parent` resolves from the Issue's `Parent: #N` (written by `create`)
   and from the native sub-issue API. `candidate_id` is read from the Issue's trailer. **No human
   carries a value**
2. **Stopped means stopped** — on a failure partway, nothing beyond it is typed. Reporting
   "success" while half-applied is the worst outcome (it presents a ledger left inconsistent as
   normal)
3. **Re-running is safe** — each event is idempotent by natural key, so what is done becomes a
   no-op. That is what makes "fix it and run it again" work

The `plan` subcommand **runs nothing** and prints only the sequence of events. For when you want to
look before typing.

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
| **integrate** | the unit merged into the integration branch (`develop`) and passing the *combined* suite alongside its siblings | `integration_admitted` — the fanned-out siblings build and test **together** green on `develop` (§4c). This is where fan-out fans back in; green CI on `develop` is its machine form |
| **deploy** | the change, live (`develop` → `main`) | `result_deployed` — requires the prior `survives` (today's schema) **and** a healthy reliability budget (docs/05 §reliability-budget); CI/CD is the spine (§3) |
| **operate** | monitoring, corrective fixes, the realized-outcome record | `outcome_recorded` (docs/05 OUTCOME-DELTA) feeds back to requirements — the loop closes |

The important observation: **the repo already implements the two hardest gates.** The
test→integrate→deploy boundary *is* the maker→gate→skeptic chain from docs/03 (`result_deployed` already
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
- **The ledger append (the enforcement layer, p=1):** the refusal is enforced at **`ledger.py append`**
  — appending a `phase_started` whose predecessor is not admitted is **rejected** (`REQUIRES_PRIOR`,
  the same code path that rejects `result_deployed` without a `survives`). This is the deterministic
  point where the mold bites: a maker cannot *record* starting a phase out of order, so it cannot
  legitimately do the work — the ledger is the single writer and it refuses. The gate only bites when
  the flow **emits** the phase events, so `/org-work` emits `phase_started` at delegation (docs/org-work
  §2b) and the gate agent emits `phase_admitted` as it clears each phase — without those emits the
  predicate is dormant, which is why the wiring, not just the predicate, is the enforcement.

This is the whole enforcement story: no forced delegation, no new organ, one predicate generalized,
enforced at the ledger append and fired by the work cycle's emits. (An `org_lint` static check that an
org's routing can't reach deploy skipping a predecessor is a possible *additional* belt-and-braces
tooth, but the load-bearing enforcement is the append-time `requires_prior`, not a lint.)

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
repositories it produces, checked at the implement → test → integrate → deploy gates exactly like any other
`requires_prior` — a deterministic tooth, not a maker's "I verified it" self-claim.

A candidate deliverable is **not admissible** past the phase named unless its repository carries:

| Artifact | Phase gate | Why it is a reproducibility requirement |
|---|---|---|
| **A committed lockfile + a populated, version-pinned manifest** | implement → test | `clone → install` must resolve to *one* dependency tree on every machine and every day; a manifest with version ranges and no lockfile resolves differently over time (the Tatekae failure: manifest with no deps, no lock). |
| **A pinned toolchain** (`.nvmrc` / `.tool-versions` / `engines`, per-language) | implement → test | the same source transpiles/builds/tests identically only on a pinned runtime; an unpinned node/deno/python floats the result. |
| **A one-command setup and a one-command test, documented in a README** | test → integrate → deploy | "verified end-to-end" must be reproducible *by a stranger from a clean clone*, not asserted by the maker; the **gate re-runs both from a fresh checkout** rather than trusting the claim. |
| **Idempotent, re-runnable migrations + a one-command DB bring-up** | test → integrate → deploy | a second developer must be able to bring up state deterministically; bare `create table` (no `if not exists`, no seed, no apply command) is not re-runnable. |
| **A committed `.env.example` enumerating every required variable (names only)** | test → integrate → deploy | the *set* of required secrets must be discoverable, or a stranger's setup fails with no manifest of what to provide (secrets themselves stay gitignored). |
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

## 4e. The unread-safe bar — the diff nobody reads must still be safe to merge

§4a makes the repo reproducible for a stranger. This section addresses a different consequence of the
same fan-out: **at parallel-agent throughput, no one reads every diff.** Not the CEO, not a reviewing
agent, not the maker who wrote it. An org running many makers concurrently produces more change per day
than any reader can absorb, and the honest response is not to read faster or to throttle generation —
it is to **make the classes of defect that only a careful reader catches impossible to merge**.

This is the repo's own thesis (docs/03 §6.5) applied one level down. The standing lesson is that
*forcing a judgment* is a design error while *forcing a checkable invariant* is correct. "Review this
diff carefully" is a judgment, and it degrades silently as volume rises — a reviewer who cannot keep up
does not announce it, they skim. "No function exceeds N lines" is an invariant: it is either configured
and enforced, or it is not, and the answer is mechanical.

The bar has four teeth, checked by `repro_lint` at the phase gates (presence of the layer, not its
verdict — running it is CI's job):

| Tooth | Phase | What it stops |
|---|---|---|
| **complexity-bounded** | implement | Unbounded function size / cyclomatic / cognitive complexity / nesting depth. This is the highest-value tooth: an over-long, deeply-nested function is exactly where the defects a reader *would* have caught actually hide, and appending to a working function is the shape an agent produces most readily when the alternative is decomposing. |
| **type-escapes-closed** | implement | Strict typing off, or `any` / `@ts-ignore` / non-null assertions available. A type checker with open escape hatches is advisory: an agent under pressure to turn a build green will reach for them, and the resulting hole is invisible in a diff nobody reads. |
| **tests-present** | test | A repo whose CI proves only that the code compiles. Tests are the artifact that *substitutes* for a reader; without them the pipeline verifies nothing about behavior. |
| **no-inline-suppress** | test | Blanket inline suppressions — `eslint-disable`, `@ts-ignore`, bare `# type: ignore`/`# noqa`. A config-level exception names the file it covers and *why*, and can be audited and expired; an inline one is invisible at review time and immortal. With no reader, it is the cheapest way for an agent to make a bar stop applying. A *targeted* suppression that names its code (`# type: ignore[arg-type]`) is a scoped exception and passes. |
| **dup-dead-code** | deploy | Parallel makers re-solving each other's problems, and superseded code that is never deleted. Neither appears as a failure in any single diff — only a cross-cutting scan sees them, which is precisely what a reader-less pipeline needs. Report-only is the right default (a blocking duplication gate on day one teaches evasion, not decomposition). |
| **multi-os-ci** | deploy | Platform-specific breakage — path case-sensitivity, reserved device names, line endings, fs-watch behaviour. A team on one platform has no other real machine, so the second OS *is* the only reader that catches these. A scheduled daily job on a second OS satisfies it; it need not gate every PR. |

Three disciplines the teeth depend on:

- **Drain, then ratchet.** Turning a strict bar on over a red codebase produces a wall of failures and
  a culture of suppression comments. Land the rule as a warning, drive the count to zero, *then* make
  it an error. A bar that is on and violated everywhere enforces nothing.
- **Exceptions live in the config, with a reason.** An inline `eslint-disable` is invisible at review
  time and immortal — nobody ever deletes one. An exception in the config file carries the file it
  covers and *why*, and it can be audited and removed when the reason expires.
- **The org's own gate is not exempt.** The gate and skeptic (docs/03) are the *judgment* layer, and
  they remain — a different-lineage adversarial reader catches what no linter can (wrong requirement,
  plausible-but-false reasoning). The mechanical layer does not replace them; it removes from their
  plate everything a machine can decide, so the scarce judgment is spent where it is irreplaceable.

The relationship to §4a is worth stating plainly: §4a asks *"can a stranger run this?"* — §4e asks
*"is this safe to merge without anyone reading it?"* An org that fans out needs both, and only the
second one scales with the number of makers.

---

## 4f. Human review is retired — the Issue becomes the audit record

§4e removes the human from *reading the diff*. This section takes the consequence to its end: **there
is no human review step at all.** No person reads the change before it merges — not the CEO, not a
reviewer, not the maker in a second pass. The mechanical bar (§4e), the gate, and the skeptic are the
entire judgment layer, and CI is the only thing standing between a commit and `develop`.

That is a defensible position at fan-out scale — a reviewer who cannot keep up does not announce it,
they skim, and a skimmed review is worse than an honest absence because it launders unread code as
reviewed. But retiring the human removes something real, and pretending otherwise is how this decision
goes wrong. What it removes is the **account**: when a person approves a change, the approval is a
record that someone weighed it. Delete the person and, unless something replaces it, the change merges
with no account of why it was allowed to.

So the trade is explicit: **human review is retired; recording is not optional.** Everything the org
decides and everything it does lands on the task Issue, in enough detail that someone with none of the
originating context can reconstruct the merge months later. Two obligations follow, and neither is
advisory.

### 4f.1 Every judgment is recorded with its reasoning

A verdict without reasoning is a stamp. `admission_decided{verdict: admit}` in the ledger proves a
decision *happened* and is tamper-evident — it does not say what was weighed, what the alternative was,
what evidence was consulted, or what risk was knowingly accepted. With a human in the loop that gap was
survivable because a person remembered. With no human, an unrecorded judgment is indistinguishable from
no judgment at all.

Judgments therefore **double-write**, exactly as a settled convention does (docs/06, conventions.py):
the **ledger gets the receipt** (tamper-evident, machine-queryable, hash-chained), the **Issue gets the
reasoning** (readable, in context, next to the work it judged). The decision lives where it can be
*inferred*; the ledger records that it happened. `github_sync decide` writes the Issue side and rejects
reasoning that is empty, verdict-restating, or padding, and **requires `--evidence` for any admitting
verdict** — an admission with nothing consulted is a stamp however well the prose reads. Be precise
about what that buys: these are **shape** checks, the same class as `repro_lint`'s. They make the
laziest degradations impossible; they cannot tell good reasoning from plausible reasoning. The floor is
enforced, the ceiling is not.

**Who may record a judgment is enforced at the ledger, not asked for.** `admission_decided` and
`refutation_attempted` carry a distinct-actor predicate: the actor recording a verdict must not be the
actor who did the work it judges, and the skeptic must differ from the gate. Without that tooth a maker
could write its own admission and forge the skeptic's `survives`, and the hash chain would then
*launder* the forgery — a forged verdict is tamper-evidently recorded and verifies clean, which reads as
stronger evidence than no record at all. This is the runtime half of O6: `org_lint`'s O6 checks the
*chart* separates maker from checker; a static chart cannot see one process writing both sides at run
time. With no human able to notice, that check has to happen at write time.

What a recorded judgment carries: the **verdict**, the **reasoning** (what was weighed), the
**evidence consulted** (the command run and its real output, the CI run, the `repro_lint` verdict), the
**alternatives rejected and why**, the **standard applied**, and any **risk knowingly accepted**. That
last field matters most: a gate that admits despite a known hole must say so, or the hole becomes a
surprise instead of a decision.

**The reasoning is hashed, because a GitHub comment is not tamper-evident.** The ledger is hash-chained;
an Issue comment is editable and deletable by anyone with write access — including the agents whose work
it judges. Left there alone, an agent could quietly rewrite its own account (dropping the `--risk` it
admitted, say) and `ledger verify` would still report the chain intact: the most control-critical record
in a human-free system, stored in the one place with no integrity property. So `decide` emits a
`reasoning_sha256` over the judgment's fields, prints it in the comment *and* on stdout, and the ledger
receipt carries the same digest. Re-hashing the comment later either matches or it does not.

Two honest limits. This makes tampering **detectable, not impossible** — that is what tamper-evidence
means, and it is the same guarantee the hash chain gives. And detection requires someone to *run* the
comparison: the digest is written today, the periodic re-hash sweep is not yet an organ. Until it is,
the property holds on demand rather than continuously.

### 4f.2 The work log is maximally granular

The Issue is the org's primary work surface (it is terminal-independent and survives a context wipe),
and with review gone it is also the primary audit surface. A log entry that says "progress recorded"
satisfies the letter of logging and records nothing recoverable — it is the failure mode to design
against, not a minor lapse.

Log at every step that changed the world or changed the plan, and record what actually happened:

- **the exact command run**, verbatim and re-runnable — not "ran the tests"
- **what it returned**, the real output including failures. A log that only records successes is a
  fiction, and the failed attempt is usually the most informative entry in the Issue.
- **the files created or changed**
- **the next step** — the field a fresh session resumes from
- **what is blocking**, if anything
- **course changes with their cause**: the approach abandoned and what made it wrong. This is what
  stops the next maker re-deriving the same dead end (it feeds `nearby_deaths`, docs/06).

The bar to hold: **a stranger reading only the Issue can reconstruct what was built, what was tried and
abandoned, what was run, what came back, and why it was allowed to merge** — without the ledger, without
the transcript, and without asking anyone. If they cannot, the log is too thin, whatever its volume.

### 4f.3 The objection this must answer: comprehension debt

docs/12 §1 names the Software Factory's defining failure mode — **comprehension debt**: *run the factory
for months with no human reading output and green tests hide eroding understanding* (Osmani). §4f
prescribes exactly the condition that doc names as the pathology. That has to be argued, not passed over
in silence, because the objection is correct as far as it goes: **green tests are not comprehension.**

What §4f actually claims is narrower than "understanding does not matter." It is that *reading every
diff* was never what produced understanding — at fan-out volume it produces the **appearance** of
understanding, which is worse than its absence because it licenses trust. A reviewer who cannot keep up
skims, and a skimmed diff enters the record as reviewed. Retiring the ritual does not create the debt;
it stops mislabelling it as paid.

But something must actually pay it, and §4f names two things that do — neither of which is "CI is green":

- **The domain model must grow every cycle (§4d).** This is the load-bearing answer. The ledger *rejects*
  a `cycle_completed` that does not state what the cycle did to the domain model — either a settled rule
  co-committed with the code, or an explicit `none_asserted` a skeptic can refute. Comprehension debt is
  precisely the failure to convert work into durable understanding; §4d makes that conversion a
  **write-time precondition of finishing**, not a discipline someone remembers. A factory that cannot
  record a completed cycle without saying what it learned is not accruing the debt Osmani describes.
- **The Issue audit record (§4f.1/§4f.2).** Comprehension is recoverable when the reasoning, the
  alternatives, the accepted risks, and the failed attempts are written down at the moment they were
  live. The bar in §4f.2 — a stranger reconstructs the merge from the Issue alone — *is* a
  comprehension standard, and it is checkable in a way "did someone read it?" never was.

The honest residue: this is an **argued substitution, not a proven one.** docs/12 §5 is right that
orgforge has not run long enough to have met this failure, and §4f does not change that. What §4f does
is make the substitution explicit and falsifiable — if the domain model stops growing (§4d's
`none_asserted` rate climbs) or Issue records thin out toward the floor, the debt is accruing and the
sensor should say so. Treat that as the open question it is; do not treat green CI as its answer.

### 4f.4 What this does not license

Retiring human review removes a *reading* step; it does not remove the *judgment* layer. The gate and
the skeptic remain, and their independence remains load-bearing — O6c's distinct-lineage rule matters
more without a human backstop, not less, because a puppet checker is now the only checker. Nor does it
license skipping a phase: the mold (§2) is unchanged. And the CEO's charter-tier decisions (founding,
irreversible moves, scope) are still human — what is retired is diff review, not governance.

---

## 4d. The domain model must grow every cycle — SDD runs ON a rising context base

The point of SDD in orgforge is not to write specs in a vacuum — it is to implement **on top of a
domain model that is already rich**, so the LLM's context is *raised* before it writes a line, and then
to **raise it further** with what this cycle settled (the user's AI-DLC thesis: context accumulates as a
by-product of work, co-committed with the code, docs/12 §3.3). A cycle that produces code but leaves the
domain model untouched silently lets the context base rot — the same fragment-decay the whole system
exists to prevent, one level down.

So the domain-model update is **forced, not encouraged**. Every `cycle_completed` must carry a
`domain_model` field, and the ledger **rejects the append without it** (the same `requires_prior`
machinery as the phase gate). It is the explicit-negative pattern: either

- `domain_model: {updated: [<convention_ref / domain-model artifact>]}` — this cycle co-committed a
  settled rule / boundary / ubiquitous-language term (via `conventions adopt`, checker-adopted, or an
  ADR/domain-model file in the product repo, co-committed with the code it governs), **or**
- `domain_model: {none_asserted: "<why>"}` — this cycle established no new domain rule (a bugfix, a
  refactor) — an *explicit claim the skeptic can refute* ("you changed the money-split rounding and
  didn't record it").

"Forgot to update the domain model" therefore cannot happen silently: the cycle cannot be recorded
complete without stating what it did to the SSoT's domain-model half (conventions + org spec, docs/12).
That is what makes the context base *compound* — each SDD cycle both consumes the risen model and
raises it for the next, instead of every cycle re-deriving the same ambiguity.

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

### The axes for deciding a split — what the existing SDD tools have, and what they do not

The criteria for splitting into tasks were checked against the real templates of Spec Kit and Kiro
(the sources are in docs/sources).

| | Spec Kit | Kiro | orgforge |
|---|---|---|---|
| the primary axis | user stories (P1/P2/P3) | design components + a sequential dependency chain | the must-have rows of coverage-manifest |
| deciding parallelism | `[P]` = *"different files, no dependencies"* | no such concept (sequential by assumption) | the intersection of `owns` (= the same decision as Spec Kit) |
| a written norm for granularity | effectively none ("exact file path" required + *"not vague"*) | *"Implement X function" rather than "Support X feature"* | "is there one way it breaks" (below) |
| **detecting an oversized task** | **none** | **none** (a human approval gate only) | `split-check` (a warning) |
| tests | OPTIONAL (only on explicit request) | TDD by default | required (the machine bar, docs/11 §4e) |

**That the intersection of `owns` is not enough was the most expensive discovery in the field.**
It is the same decision as Spec Kit's `[P]`, and it **inherited the same limit**: an Issue whose
`owns` was closed inside the single directory `supabase/` was not split, while its content held two
things differing in both how they break and how they are verified — "the shape of the schema
(guarded by types and constraints)" and "authorization (guarded by attack scenarios)". As a
result the gate could not once sustain the same viewpoint across fourteen judgments, several
migrations interfered with each other, and it did not finish in over ten rounds.
On the same day #8 (one function) and #10 (a CI setting) passed in one or two.

So one more axis is added:

> When this deliverable breaks, **is there one way it breaks**? Does verifying it need **one
> means**?

Kiro's *"Implement X function" rather than "Support X feature"* says the same thing another way —
bring it down not to a unit of feature but to **a unit answering one way of breaking**.

**Detecting an oversized task is something no tool or method surveyed has** (docs/sources).
Spec Kit's `analyze` carries no granularity check, and Kiro has only a human approval gate. BMAD
has the same feature request (Issue #1471, "start a decomposition agent once the task count
exceeds a threshold") **left open and unresolved**, and on the academic side AQUSA explicitly
gives up on automating Estimatable (oversized), calling it a matter requiring semantic
understanding. The only quantitative threshold is Devin's *"if a task would take you three hours
or less"*, and even that is not a pre-filing lint. An org that has retired human diff review (§4f)
has no approval gate, so `github_sync split-check` warns after filing — are there several ways of
breaking, and does the authorization requirement set only the boundary? **It does not stop; it
warns**: what should be protected is a human's call.

**Making "does it touch the same file" the criterion for splitting is, in the existing normative
bodies, an anti-pattern.** Humanizing Work defines a vertical slice as *"a work item that delivers
a valuable change in system behavior such that you'll probably have to touch multiple architectural
layers"* — it **positively includes touching several layers**. Splitting by layer (one for the UI,
one for the DB) is named outright as a failure pattern, against both independent and valuable.
Tessl's 1:1 spec-to-code mapping is the opposite pole, and Fowler's analysis names it as a limit
that "restricts composition across components".

orgforge's `owns` criterion is right for **avoiding collisions** (parallel makers not writing the
same file), but as **the judgment about splitting** it is not sufficient on its own. Hence the
"way of breaking" axis.

### Whoever is checked must not decide whether the check runs

`integrate` confirms that the gate's admit and the skeptic's survives are in the ledger, and stops
otherwise. But **nothing happens unless it is called.** In operation a supervisor who had received
a high-quality maker report merged into `develop` with `git merge`, and several deliverables were
integrated having passed neither the gate nor the skeptic. The ledger correctly refused them
afterwards — but the refusal came **after the code was in**.

This has the same structure as "do not decide by the presence of the subject itself", one level
up: **adding a check inside a tool makes the check optional as long as calling that tool is at the
caller's discretion.** The only thing that can detect it not being called is a layer outside the
call — the PreToolUse hook.

A hole of the same shape existed in Issue operations. `gh issue create` attaches no `dept`,
`objective`, `parent`, or idempotency key, and `gh issue close` leaves no `cycle_completed` (which
requires `domain_model`). A rewrite that does not go through an organ skips the record's required
fields wholesale.

**Always attach the command to type to a hold.** A bypass happens not for speed but because "the
cost of remembering the tool's name" went unpaid. With the command in front of you, the reason to
bypass disappears. Conversely, holding without offering an alternative means **the escape-hatch
declaration gets memorised, becomes routine, and bypassing accelerates while leaving no record** —
which is worse than having no hold at all.

**Provide the escape hatch, and record that it was used.** Blocking it completely traps you when
something breaks, so an explicit declaration (`ORG_ALLOW_MANUAL_MERGE` / `ORG_ALLOW_MANUAL_GH`)
lets it through, and **the declaration itself is left in the ledger as `bypass_declared`**. It is
the shape of recording what cannot be blocked.

### Write a check as strictly as the wording it demands

The guard's message said to write **one line at the top** of the child prompt, while the check was
**a substring match over the whole text**. As a result **a negation passed as a declaration** — the
Japanese for "I attached neither a contract nor `INDEPENDENT:`" matched verbatim as a declaration
of independence (a probe in the field).

The harmful shape is a spawn written as "this work is not independent, so I attach a contract"
being misjudged as a declaration of independence: **such a declaration exempts the `owns`
declaration**, so a chance match takes the exemption. **When a check is looser than the wording,
only whoever wrote it correctly bears the strict constraint.**

The same hole existed on the seam side: it read the **word** `"seam contract"`, so "no seam
contract is attached" passed as a declaration. Read **structure** rather than words (`## Your
slice`, `Inputs you receive:`, `Outputs you MUST produce:`) — structure does not appear in a
negation. One may write "there is no `Inputs you receive:`", but one hardly ever places a
colon-terminated heading inside a negation.

**The general form**: when checking a declaration or a promise, read **the position and shape in
which it appears**. Reading only a word that can occur in prose lets merely talking about that word
pass the check. It is **the tool-side variant** of the failure this org has closed again and again:
stating something unverified as though it were verified.

### The observation path can hide a value

`intake` was reported as "exit=0 on the main case only", while the implementation returned 10 on
all three paths. The cause was **a pipe**: through `| tail` the shell's exit code becomes the last
command's.

**A correct implementation still produces the same misjudgment when the observation differs.** A
design that decides by exit code is void the moment a pipe is inserted — a decision a machine picks
up also goes **into the output** (one `INCOMPLETE` line).

### A truncated report — read the shape before reading it as a judgment

A subagent's turn sometimes **ends mid-work**: `status` returns completed and `result` holds a
single declarative sentence like "Now the key attack:". Resuming with `SendMessage` ran the rest to
completion, so **the agent did not die — the turn ended before the report took the shape of a
deliverable**.

**The dangerous shape is the one that cuts off plausibly.** "Now the key attack:" is visibly
missing a verdict, but a report cut off at "MUST 2 is defended" could be read as a verdict and
admitted.
The failure mode this org has detected again and again — stating something unverified as though it
were verified — holds through the path of **a truncated report**: nobody has lied, and the record
still carries a judgment presented as verified.

`org_cycle intake` reads only the elements each role must carry (a verdict and a trace of what was
run for skeptic/gate; commits and the measured DoD output for a maker). **It reads neither the
content nor the soundness of the verdict** — judging is the role's work, and all this reads is
whether the report has the shape of a deliverable.

**A word that merely reads as though it were cut off is not grounds.** Deciding on words like
`Now …` rejects a complete report that carefully wrote out its interim progress. With the required
elements present it counts as having run to completion, and the word is attached only as a
supplement.

### To change the speed, measure the dominant term first

Lowering the model or the effort against "it is slow overall" **does not work unless what is being
cut is the dominant term**. Measured in real operation (n=52, from the `duration_ms` of the
completion notifications):

```
maker 486.7s (54%) · gate 260.2s (29%) · skeptic 169.3s (17%)
one round ≈ 15.3 min / rounds driven by refutation = 214 min / 269 min = 79%
```

**"One wait" is only 21%; 79% is the number of rounds.** Lowering the gate's or skeptic's model on
top of that degrades the quality of the judgments, adds rounds, and **makes it slower**. What works
is the split and the definition of done (§4b), not the model layer.

Three points where the judgment nearly went wrong, recorded:

1. **"The maker is the majority, so the quality is lacking" is wrong.** The longest single run
   corresponded to several hundred lines of SQL and dozens of tests — volume of work, not
   slowness. On the same deliverable a skeptic looked for "one move over", failed to find it, and
   wrote that "enumeration was replaced with a predicate, so it is now hard to produce in
   principle" — **a worked example of a maker's design decision stopping a refutation**.
2. **"Lowering registrar is the only safe candidate" is equally meaningless.** It was called zero
   times in real operation, so no effect can be measured. It read the safety and **not the
   effect**.
3. **What could not be measured is not used as material for a decision.** registrar's duration and
   `org-tick`'s behaviour were explicitly unmeasured, and were left out of the decision.

The only thing that could be cut was **duplication in the prompt** (`verify` printed the gate's
latest judgment in two places, the judgment history and `prior`, and over 46 of the skeptic's 457
lines were duplicates). That is a term measurement made visible, not something lowered on a guess.

### The supervisor's own records are checked too

This org checks **the maker's deliverable** (`cycle_completed` refuses a thin `--result`) and **the
gate's and skeptic's judgments** (`decide` refuses a paraphrase of the verdict) by machine. **Only
the supervisor's records went unchecked** — and in operation, most of the supervisor's failures
turned out to be catchable on the tool side.

The failure mode this org detected eight times in one night was **stating something unverified as
though it were verified**, and it appeared in all four layers: **deliverable → judgment → tool →
supervisor**. **The first three had a machine check; only the fourth did not.**

| what went missing | measured | the fix |
|---|---|---|
| a commissioned rework leaves nothing in the ledger | many rejects and refutations had no `rework_requested` (one Issue was rejected four times with zero records) | make `org_cycle rework` a dedicated command, and have `verify` print it **in the same place as the judgment's record** on a reject |
| a summary drops a qualifier | the maker's "**it is not on this branch yet**" vanished in the supervisor's summary, flowed into the instructions to the gate, and became a reason for rejection | split `decide` into `--claimed` / `--verified`, and warn where a qualifier goes untouched by `--verified` |
| reusing an old path | the 0.25.2 path was still typed after 0.26.0 shipped | one line of the running version and cwd to stderr |

**The missing rework records silenced the tool's warning.** `show`'s rework warning (which appears
past three) counts `rework_requested` in the ledger, so it never reaches the threshold unless the
supervisor records it — **a tool does not count what it cannot count**. Part of the cause was that
no dedicated command existed and `ledger.py append --payload '{...}'` had to be assembled by hand
(commissioning runs "judge → verify → decide → **commission** → record", and the record gets
washed away when the commissioned subagent's notification arrives).

**This check is not complete.** `--verified` can pass on the words "I confirmed it" alone, so a
trace of execution (a command name, output, an exit code) is read coarsely — and that itself
invites the formalisation "write a command name and it passes".
**Recording honestly what cannot be blocked** is this org's discipline. As evidence: when
`cycle_completed` refused a thin `--result`, the supervisor actually measured again — a worked
example of a refusal changing behaviour rather than being a formal wall, with no guarantee that it
always holds.

**An exclusive lock on a worktree is deliberately absent.** There was real harm — "while a gate
was running, a supervisor ran a mutation check in the same worktree and the skeptic observed a
false failure" — and a warning about contention is reasonable. But a gate terminated abnormally
that same night, and **a path where a lock left unreleased creates a new jam genuinely exists**.
The decision waits on whether it recurs after the three fixes above — do not create another jam to
fix a jam.

### Do not put the instructions at odds with the permissions

Never write an instruction to a subagent **that demands a permission it was not given**. In the
field `agents/gate.md` and `agents/skeptic.md` instructed it to "record the judgment in both the
ledger and the Issue", while the subagent was given neither `ORG_GITHUB_REPO` nor the ledger path.
As a result gate and skeptic repeatedly produced a judgment, said "I leave the recording to the
supervisor", and stopped — and **once the judgment itself came close to being lost without ever
entering the ledger** (the supervisor noticed through `org_cycle show` and resumed it).

There were two directions to resolve it in, and the one adopted makes **returning the judgment the
limit of a subagent's responsibility**:

| | what it is | the decision |
|---|---|---|
| (a) grant the recording permission | give the subagent the env and write access | not adopted — a judge that also holds the recording makes the independence check (the ledger's DISTINCT_ACTOR) easy to formalise away |
| (b) narrow the responsibility to judging | as far as **returning** verdict / why / evidence / standard / risk | **adopted** — recording is the supervisor's job. In the field, too, a subagent concentrating on the judgment produced better quality |

`verify`'s output was split too: **stdout (the body handed to the subagent) carries no recording
command** and states only what to return. The command the supervisor types goes to **stderr** (for
the supervisor).
Plumbing that can no longer carry the judgment defeats the purpose, so both are kept and only their
destinations are separated.

### A tool says what it has not looked at

`repro_lint` decides "did this change newly break something" as a difference against the baseline.
With no baseline it used to attach "these are not in the baseline = newly broken by this change"
to every failure — **asserting about something it had not read**. In the field a gate took that at
face value, read pre-existing debt as a new regression, and stopped the judgment (while the Issue
in question was the work of turning those very items green).

Now it says "there is no baseline, so whether this is a regression from this change or
pre-existing debt **has not been decided**".
**Saying "this tool has not looked here" lets the judging side act correctly, where saying nothing
does not.** `/org-init` now takes a baseline once as well, so a new org no longer steps on this at
its first gate judgment.

### Before adding a new check — run it on real data

When adding a check (a lint, a warning, a detector), **run it against artifacts actually in
operation before shipping it, not against a synthetic test document**. Synthetic data is built to
reflect the check's design, so it always passes.

The same mistake was made twice in the field:

- `req_lint`'s VOIDDEP (added at 0.25.0, withdrawn at 0.25.1) — on a synthetic document both
  detection and non-detection worked correctly, while a real `REQUIREMENTS.md` held **zero**
  backtick identifiers and it **never once fired**. A Japanese requirement is naturally written as
  「利用者が表示名を変更したとき」, without the identifier notation.
- The same shape on the test side (0.22.1) — the test set `CLAUDE_PLUGIN_ROOT` before calling, so
  it never checked **the path with no env, which is how it is actually used**, and it missed verify
  dying in the split.

Both satisfy "the test is written, and it is green". **A test that does not verify at the place
that breaks is the same as no test** (the same shape this org caught on the product side, present
on the tool side).

And **a check that only produces false positives is worse than none** — a false warning voids the
correct warnings too (in the field, `complete` crying wolf led to Issue comments being integrated
by eye, and the ledger-side record went missing). Once a check is known not to reach, **withdrawing
it and leaving the reason** is cheaper than building it out.

### A judge's lineage is separated by execution, not by declaration

`role-settings.yaml` can declare a family for the skeptic different from the gate's, but **a
subagent in the same harness inherits the parent's model**, so the declaration alone does not
separate the lineage. A checker on the same base model as the maker shares its blind spots.
Separating them requires **actually running in another harness**.

The primary is not fixed by configuration. Where the running agent is Claude Code it picks Codex as
the secondary, and where it is Codex it picks Claude Code. The absence of a subscription on the
other side does not render the whole org unusable. `adaptive` degrades to a gate/skeptic inside the
same product, but that judgment is treated as `same-harness` and **is not recorded as having run
cross-harness**. It is a quality layer that separates the roles pseudonymously; it guarantees no
decorrelation of blind spots.

Where they are separated, **there are two judges** (a subagent in the same harness, and a headless
one in another). What has to be settled here is **how the two are treated when they disagree**.
Doubling up without settling it leaves the supervisor room to take whichever suits, and **more
checking becomes looser checking**.

The rule adopted is "negative from either side is negative" — falling to the stricter reading. A
majority vote does not resolve at 1:1 and returns to the supervisor's discretion. And **the side
that adopts the judgment (`decide`) must hold this agreement requirement**. Merely lining the
judgments up for display returns us to the structure where "whoever is checked decides whether the
check runs".

**A disagreement is not an anomaly; it is the point of separating the lineages.** Count it rather
than erasing it.

### A read-only judge cannot admit a MUST that requires execution

Running a judge read-only is right (with another harness's guardrails unverified, being unable to
write still falls on the safe side). That choice has a structural consequence, though — **a MUST
requiring repeated test runs, reaching a real DB, or a build cannot be re-derived, and becomes a
`park`.**

A `park` is the correct behaviour (better not to admit what cannot be measured). Learning it only
after running the judgment is waste, though, so **where that MUST carries the weight of the
admission, the supervisor measures it beforehand and passes it as evidence**. The tool says so
before the judgment.

### A per-item check does not see the common factor

gate, skeptic, repro_lint, and intake are all **per-item judgments**. Each may work correctly item
by item while nothing in the org asks "eighteen rejects came out tonight; what is the common factor
in their reasons?" **Where several fail on the same factor, what needs fixing may not be the
individual deliverables but whatever produces that factor** — how the specs are written, the
standard handed to the gate, the conventions, the granularity of the split.

This is not a judgment but **presenting material**. Which one to fix is the supervisor's call. The
moment a tool decides "the spec is bad", it has become a judge.

**The ledger alone cannot count the reasons.** A judgment event's payload holds only
`reasoning_sha256`, and the prose exists solely in the Issue comments. The ledger settles "which
Issue failed how many times", and the reasons are read from the Issue. And **do not hit something
structured with a full-text search** — running a regex over whole comments picks up the maker's
reports and rework instructions too, and four of the eight factors then match every Issue, losing
the distribution (measured).

### Confirming that it can refuse, without confirming that anything can pass

When a new check goes in, **run both the refused side and the passing side against real data.**
Confirming only the refusal ships a check that "nothing gets through, whatever you do".

A worked example: the check requiring two lineages to agree shipped after confirming that a
one-sided admit is refused. But **from an empty ledger either order is refused**, so that org could
not record a single admit. Confirming a refusal shows only that "the check is working"; **whether
a path exists that can satisfy it** is a separate experiment.

Written as acceptance criteria, "it is refused" is paired with "**a full round can be completed
from an empty state**". And a unit test of the deciding function cannot catch this — **run the real
CLI from an empty ledger**.

### A command you advise is tested as far as typing it and having it work

If a refusal message says "type this and it is fixed", **actually type that command and test that
it works.** Checking that the message contains the right words is not enough.

A worked example: when refusing a substituted judgment, the message advised how to type
`correction`, and the payload shape differed from the real one (it said `corrects_seq`, while the
real one requires `corrects: [seq]` and `kind`).
**The append succeeds, so it looks like it worked — and nothing is voided, and there is no way out
of the refusal.**

On top of that, `corrected_seqs` excludes only `probe` and `mistake` by default and leaves
`superseded` to the chronological resolution. Without knowing that distinction, whoever writes the
advice produces something that does not work even when typed correctly. **What voiding means
differs per kind** — erasing it, replacing it, or filling it in afterwards.

### Correcting a judgment hands back to a third-party authority

`correction` is an append rather than a deletion from the history, but where `probe`, `mistake`, or
`superseded` targets a judgment, that judgment can be excluded from derived views and from a joint
admission. Advising this operation to the very gate or skeptic that produced the judgment therefore
opens a path to clearing another judge's reject and substituting one's own admit.

The authority for a judgment correction is stated explicitly in the constitution:

```yaml
enforcement:
  judges:
    judgment_corrections:
      authority_roles: [supervisor]
```

The authority must be an active role other than gate or skeptic, and `org_lint` checks that it
exists, is active, and does not judge. A voiding correction additionally requires a signed receipt
bound to the org, the ledger, the target seq, the kind, the authority role, and the digest of the
reason. Merely claiming `--actor supervisor` does not pass.
The ledger writer resolves the target seq to an event that exists and fills the correction in with
the target class, Issue, effect, authority principal, and assurance. `backfill` does not void its
target and therefore does not consume this authority. probe and mistake on ordinary events can
still be self-corrected as before.

Compatibility Mode with a shared key reaches `attested` and no further; it is not a security
boundary against a host under the same UID. Where an asymmetric key is used but writer isolation
and the like are absent, the limits of the guarantee are stated alongside it. Requiring a signed
receipt nonetheless closes the ordinary path of "changing the actor name alone to feign
independence". A role name by itself is never called `authenticated`; the assurance actually
verified is what stays in the ledger.

### "Did they look at the same thing" belongs in a judgment's identity

If agreement between several judges is required, **make what was judged a condition of that
agreement.** Counting agreement from the verdict and the role alone makes two passes over different
revisions count as agreement.

The identity of what is judged is taken more broadly than a commit SHA:

    issue + role + phase + base_sha + reviewed_tree_sha + dirty + requirements_digest

`reviewed_tree_sha` is a tree rather than a commit because rebuilding a commit with the same
content does not change the subject. `requirements_digest` is included because **different
acceptance criteria make it a different judgment**. Uncommitted changes (dirty) are not hidden
either — never pretend it was clean.

And **do not express dirty as a summary of the diff.** `git diff HEAD` does not include untracked
content, so even combined with `status --porcelain` it takes the shape of "pick up the names, read
nothing inside". In practice, replacing an untracked file's content entirely still matched the id.
Where a judge read untracked files to judge, two different deliverables could be made to agree as
"the same thing".

Correctly, **the working tree is read into a temporary index and `git write-tree` is run over it**.
Pointing `GIT_INDEX_FILE` at a separate file bundles tracked, staged, unstaged, and untracked
content into one tree identity while **not breaking the supervisor's staging state**. Artifacts
excluded by `.gitignore` are left out — an id that moves with build output makes the same review
impossible to perform twice.

And **no judge produces this value.** If a judge could write it, two judgments over different
deliverables could be declared as "having looked at the same thing" and made to agree. Whoever
assembles the material observes it once, and the judge only carries it.

### An early return skips the record too

"A negative stands alone" is correct, but **returning early drops the record of the side effects
as well.** A worked example: making park and reject return first stopped the disagreement from
being recorded on the path where "a reject arrived after the admit".

When adding a branch that depends on order, **test both orders.** Confirming one lets it through.

### A recording procedure must not require a judgment to be run

If the only way to obtain a value needed to record a judgment is "run the judgment again", the
supervisor skips that step. A worked example: the command that assembles the material was typed to
learn the id of what was judged, and a judge in another harness
it actually started one and waited minutes (before being cut off).

**For a question that a read alone answers, provide a path that answers it with a read alone.**

### Place a record that carries no authority first

Writing a check that requires agreement as "the peer is already there" jams in the initial state.
Allowing **a record that carries no authority on its own** to be placed first makes the order
irrelevant.

    verdict_provisional   one lineage's judgment. On its own it permits nothing
    admission_decided     assembled by the tool once the two agree

Producing the verdict at stage 2 is plumbing, not judgment (a function of the fact of agreement).
**That there is no point at which the tool adds a new judgment** is the condition under which this
does not turn the gate into a formality.

### A setting on the safe side stops when it cannot be read

If a stronger checking mode is selected by configuration, **it must not fall back to the weaker
mode when that configuration cannot be read.** Falling back makes the layer that was declared
vanish silently, with no path by which anyone notices.

    except Exception:
        return "same-harness"    # ← this is fail-open

"So the org does not stop" is not a reason. Stopping is **safer than continuing to judge under a
lineage that was never separated**. Whether the reason it cannot be read lies in that very line is
unknowable at the point where it cannot be read.

### The validation version is stamped by the writer

If a client can name the format version, it can name a looser one and walk past validation (a
downgrade). **The writer stamps the version, and a client's specification is refused.**

And **the version itself goes into what the hash covers.** Without that, rewriting the version is
undetectable and refusing a downgrade means nothing. Since that is incompatible with the existing
chain, **what the hash covers is switched per version** — a past event carrying no version is
verified over the old range, and v1 onward includes the version. It is the concrete form of the
discipline that a validator adds versions rather than changing past ones.

Do not draw the prohibition too widely. Forbid **only a value that names a version**. An event that
records the schema boundary itself naturally carries an identifier in its payload, and rejecting
that makes the fact one wants recorded unwritable.

### Validating retroactively makes migration impossible

When new validation goes in, **applying it retroactively to existing records makes the ledger
unreadable.** Validation applies to new appends only, and the past, which carries no version, stays
readable as `legacy_unvalidated`.

And **do not mix the two assurances**. "Is the format validated" and "is the writer authenticated"
are independent properties. Conflating them invites the misreading that validating the schema makes
the actor trustworthy too:

    validation_assurance:  legacy_unvalidated | validated:v1
    identity_assurance:    claimed | observed | attested | authenticated

In the default local deployment, even an asymmetric signature reaches `attested` and no further.
`authenticated` is a value reserved for deployments where the host environment guarantees external
custody and caller authentication; "it verified against a public key" alone does not select it.

The record of the boundary (since when validation has been in effect) stays **an aid**. The
normative basis is the version each event carries itself, not the single event declaring the
boundary — so that no semantics have to be introduced for that event vanishing or appearing twice.

### A stopped state is not a warning

A mechanism that merely records "it stopped" has stopped nothing. **The state of being stopped is
expressed by the next act not getting through.** A record with acts still getting through is only a
display.

The decision to stop is read from **the record, not a declaration**. Stopping on a declaration (a
setting, an environment variable) means deleting the declaration starts it again.

And **"do not declare what cannot be recorded" is fail-open as control.** It fails to stop in the
situation where it should. A call whose recording failed does not itself get through. **The next
call must stop too** — for which there is a second path that writes a simple latch ahead of the
ledger.

The latch is not a substitute for the ledger. **Removing the latch by hand still stops things while
the ledger's record remains.** Conversely, the latch stops things even when the ledger cannot be
read. The shape is: **if either one is stopping, it stops**.

**Never read "it cannot be read" as "it is not stopped".** If it is unclear whether things are
stopped, stop.

### Stopping everything makes recovery impossible

Decide what passes while stopped. **Limit it to observation, verification, and safe repair** —
without being able to diagnose the stopped state, nobody can tell what happened. And **ordinary
work stops**. Drawing the passable range widely returns us to "it halted and nothing stopped".

Do not put the release in the same layer. **If whoever stopped it can release it, stopping meant
little.** An independent approval is needed, and that depends on the actor's identity being
authenticated. While there is no authentication, **not building a release mechanism is the correct
choice** — building one creates a path to releasing on a self-declaration.

### Do not run a control's judgment in the same process as what it judges

Importing the tool used for the judgment makes **that tool's top level run inside the judging
process**. If a replaced (or broken) tool holds an exit call, **the judging side ends there as a
"permit"** — measured: the hook printed nothing and passed at exit 0.

Ask in a separate process, and read **both the exit code and the result**. A control's judgment
happens outside the thing being judged.

### Only a judgment that was written becomes an allow

Splitting a cap check into three stages — aggregate → judge → record — opens three holes at once.

- **the aggregation and the judgment sit outside the exclusion**, so parallel calls read the same
  total and **both get through**. The total exceeds the cap.
- **ignoring a failed record** means it passed while no exposure remains. The next call sees a
  total of 0, so **an aggregating cap degrades into a memoryless per-item check**.
- **not recording what was stopped** leaves nothing showing the cap worked. It cannot be told apart
  from a cap that is not in effect.

The correct shape makes
**fetch the schema → check the history's soundness → reconcile idempotency → compute the total →
judge → record + fsync**
one operation inside the exclusion, and **passes only after the record is persisted**. If it could
not be written, it does not pass.
**A failure to record a stop does not pass either** — reading an unrecordable refusal as a permit
is the most dangerous mistake of all.

**The writer counts the total.** If the caller can declare it, it can declare a smaller number and
get past the cap. A broken past record is refused rather than counted as 0 — counting it as 0 makes
the total look smaller than it is.

**Define no timestamp argument on a cap reservation.** Placing a reservation outside the window
bypasses a cap that aggregates over a window. The authority to fill in the past stays on the side
of ordinary records.

### Do not express "who" in one field

The principal of an act separates into at least three: **the principal that formed the judgment,
the one that transcribed it, and the one that committed the record**. Collapsing them into one
field makes the separation of duties fail in any deployment with proxy recording — where a
supervisor writes a judgment by proxy, the observed principal is always the supervisor, so all that
can be said is "the supervisor did not approve the supervisor".

**The separation of duties compares the principals that judged.** Never compare the ones that
transcribed.

And **the principal that judged takes a shape no self-declaration can set**. Anything declarable
can be claimed as anyone's judgment. What is needed is not a direct record by the judge but **a
judgment receipt that cannot be altered** — carried by a third party, it still does not lose the
judge's identity. **Proxy recording and authentication coexist.**

The receipt binds every value that identifies the judgment (the org, the subject, the role, the
phase, the lineage, the conclusion, the digest of the standard, the digest of the reason, the
signer, the key, the time, the format version). **A value that is not bound can be swapped
afterwards.** And reuse against another org, another subject, or another lineage is refused.

### Narrowing to one path and guarding that path are different things

Declaring that "a record used in a check is writable only by whoever checks" **enforces nothing
while several writable paths exist**. A mechanism that narrows it to one (only one process writes)
is the first step from a declaration to a structure.

**Narrowing the path alone is not a boundary, though.** A caller running under the same privileges
can stop that mechanism, restore the file permissions, and replace the mechanism itself. So the
guarantee reaches "**there is one path**" and no further — not "a separate principal is guarding
it". Keep the names apart.

And **other things need guarding as strongly as the write path** — the halt latch, the key
registry, the validation rules. Narrowing the ledger alone to one path still leaves the controls
bypassable if the latch can be deleted, the signers replaced, or the rules loosened.

### Having connected is not having judged

Identifying the peer on a path yields material only for **the principal that recorded**. The
principal that judged is settled solely from a signed receipt. **Do not repurpose a connection's
identity as a judgment's identity.**

### Verify a request as one unit

A request across a path carries **a digest covering the whole body** and **a value usable once**.
Without the first it can be rewritten in transit; without the second the same request can be
replayed.

And **the requester must not be able to specify the write target**. If it can, it can write
anywhere through that path — and "the owner is settled" loses its meaning. The receiving side fixes
the write target at startup, and the requester can select only by name.

### Agreement is not a judgment — provide a dedicated path

A record generated from two judgments agreeing carries **no judge's signature**, because agreement
is a function of fact rather than a judgment. Trying to write it through "the path that requires a
signature" produces **a deadlock where agreement still cannot be recorded**.

A derived record is **a dedicated operation of the writer**. The writer reads the two rows in the
ledger and generates it having confirmed for itself the agreement, the subject, the lineage, and
the strength of the identity. The principal of the generated record is "derived by the system", and
**it is not recorded as anyone's judgment**.

### Binding is all or nothing

When tying evidence to a judgment, **reconciling only some of the fields lets evidence differing in
the unread fields be reused**. Beyond the subject, the phase, the conclusion, and the digest of the
reason, it binds **which org, which ledger, and which record class**.

And **the org and ledger identifiers are taken from the write target**. Reconciling against a value
written in the record's own body confirms nothing, since the caller can write that value.

### A control must not loosen its own trust

Having built a mechanism that verifies what it connects to, **the control deciding for itself that
"this time it may be loosened"** voids the verification. Whether to loosen is stated by the user.
The control does not loosen.

### The order of the cleanup is the safety itself

Removing a stopping mechanism needs an order: **stop → write back → replace the references with
real content → restore the ownership**.

Restoring the ownership first leaves whoever writes back unable to write. Not stopping first lets
the peer write mid-restore.
And **what is shared is not removed while other users remain** — do not build a shape where
removing one breaks them all.

### The side that is not verified must not be able to raise the "verified" marker

Shutting the check's input out of the body still leaves **the same hole open elsewhere if the
caller can raise a marker meaning "verified"**. Measured: merely adding one environment variable
let a forged identity through, and **a test I had written was raising that variable with no
receipt**.

The correct shape is **having the evidence itself handed over, and the receiving side verifying
it**. The caller can only hand it over saying "verify this"; it cannot assert "I verified it".

And **the field is filled in even where there is no evidence** — otherwise "checked, and it turned
out to be self-declared" cannot be told apart from "never looked at all".

### Deleting a setting is not disabling it

When enabled/disabled is expressed by a declaration, **reading the absence of the declaration as
"disabled" takes the control off through deletion alone**. Measured: deleting the configuration
file made the enforcement vanish.

There are two answers: **put the authoritative configuration somewhere the caller cannot write**,
and **leave a trace that it was once enabled, and stop when the declaration disappears**. To
genuinely disable it, make them state "disabled" explicitly.

If an environment-variable override is kept, **make its being in effect explicit** (require a second
variable alongside it). An escape hatch that works silently is not an escape hatch but a hole.

### When a control goes in, confirm the legitimate path works in the same pass

Having narrowed writes to one path, **move the callers of that path at the same time**. Measured:
the hook and the recording tools kept calling the old path, and the moment the control was enabled
**every legitimate operation would have stopped**.

Confirming only that the refusal works, and **not that what should pass does pass**, produces
exactly this shape.

### Fix the read path too

Guarding the writes still leaves the state forgeable **if the read follows a path the caller points
at**. Measured: repointing the reference at an empty location made a halted org look "not
halted".

A read used in a judgment looks at the real content the writer fixed at startup. **Repointing the
reference does not move what is read.**

### Whoever is checked must not be able to write the check's input

If the value a control judges by is **something writable in the record's body**, it is not a check.
Measured: writing two strings into the body was enough to bypass the enforcement of the separation
of duties.

**And my own tests had pinned that forgery as "the correct path".** When adding a check, always
confirm **who can write** the value it reads. Grounding a check in a value written by the side
being checked makes it a formality, and the tests then preserve that as the happy path.

A value used in a judgment takes a shape where **only the verified path generates it**. A
same-named value written in the body is refused.

### Read configuration as three values

Reading it as the two values enabled/disabled **falls to disabled when it cannot be read**. An org
that had it enabled becomes defenceless the moment the configuration file breaks (measured: exit 3
before corruption, exit 0 after).

The read gives three values — **enabled, disabled, undecidable** — and stops where it is
undecidable. Beyond broken syntax, **a wrong type** (a string where a map belongs, something else
where a boolean belongs) counts as undecidable too — an ambiguous value is never read as
"disabled".

### The signature covers the values used in an assessment

A signed record must not mix in **a field outside the signature**. Measured: the value used to
assess independence sat outside the signature, and rewriting it to the stronger value after signing
still verified.

If it is used in an assessment, it goes into what is signed. And **raise the version when the format
changes** — reading an old-version record under the new rules mistakes an uncovered value for a
covered one.

### Tightening the permissions on the contents means nothing if the container can be replaced

Tightening the permissions on the authoritative data still allows replacing the directory wholesale
**where its parent is caller-owned**. Move the real content out from under the caller's control and
leave only a reference. And **give the side that actually writes the real path** — repointing the
reference does not move the write target.

### If the name can be changed, comparing names means nothing

Where the separation of duties is done by comparing "who wrote it", **there is no control if that
"who" can be claimed freely**. Measured: self-approval under one's own name is refused, while the
same process passed by claiming another.

Closing it requires **a principal derived from a verified signature** on the records at the core of
the controls. Enabling that requirement stops every existing deployment without a signing mechanism,
though — **the default is off, and it is turned on after the keys are distributed**. Off does not
mean safe; it is a default that makes migration possible.

### Permissions satisfy both "it can be created" and "it can be guarded"

When tightening a parent directory's permissions to guard a path, confirm **whether the side that
creates that path still can**. Measured: under a root-owned read-only directory, a resident process
running as a different principal **could not create** the socket — guarded so far that it does not
run.

The answer is to split the hierarchy: an **anchor** (unwritable by the caller) and a **leaf**
(writable by the creating side), with the guarantee being "the anchor cannot be written to, so the
leaf cannot be replaced wholesale".

### A separate principal guarding it, and the judgments being independent, are different things

Isolating the principal that writes leaves **whether the judging principals are independent as a
separate question**. Measured: the writer's isolation value was recorded as the judge's isolation,
and a merely different key promoted it to "a separate workload".

Keep the fields apart. The writer's isolation is a property of the writer; a judge's independence is
declared by the judge, or is "unknown" where it is unknown. **Do not promote on a borrowed value.**

### Reconcile the conditions of the installing side and the accepting side

Where the tool that writes the configuration differs from the tool that runs under it, **confirm
that their conditions do not diverge**. A worked example: the installer made the parent directory
group-writable, and **the accepting side refused exactly that shape** — the install succeeded and
the daemon would not start.

And **do not mistake which principal checks the prerequisites**. Whatever is present in the user's
environment means nothing if it is invisible to the principal that actually runs (a resident
process started as a different user). The check happens **in the environment of the side that
runs**.

### Do not confuse "cannot be written" with "cannot be seen"

What a control demands is that it cannot be written, not that it cannot be seen. **A record that
cannot be read is not a record for auditing.** When tightening permissions, confirm at the same
time that the checks, the aggregation, and the projections keep working.

### A verification must not break what it verifies

"Trying a write" to confirm a boundary breaks the real thing when it succeeds. **Read only whether
it opens, and write not one byte.** Whether the permissions can be changed is answered by **reading
the owner**, not by changing them. Do not stop something to confirm it can be stopped — once it
stops, every later check and the controls in real operation fall with it.

Provide a path that runs with zero side effects. And state explicitly that **that path has not
confirmed anything can get through** — a mechanism that only stops cannot be operated.

### Measure before claiming isolation

Having written the configuration is not having a boundary. Measure **that a normal caller genuinely
cannot write**. Try a write, a permission change, replacing the path, and a stop, and confirm each
one fails.

That verification **must not be run with privilege** — with privilege everything succeeds, and
nothing has been confirmed.

### A different key is not a different principal

With a shared key, **whoever can verify can also produce the signature**. So using a different
shared key shows only that "the key differs" — it shows nothing about a different principal, a
different process, or an independent approval. **Making it the grounds for independence puts the
name and the guarantee at odds again.**

Going asymmetric gives the judging side the private key and **the verifying side only the public
key** — the verifying side cannot produce a judgment. That is the condition for an attestation
"stronger than a declaration".

Making the key asymmetric alone, however, leaves **the workload unisolated**. While the same user
can replace both the writer and the keys, that is not yet a boundary of identity authentication.
Isolation stays a separate axis.
What orgforge aims at is decorrelating review quality through different model families. Do not
break R0 by making a separate host, a KMS, or an HSM a premise of the core.

### A valid signature and permission to issue that judgment are different things

A verification passing leaves **whether that principal is permitted to issue a judgment for that
role and that lineage** as a separate question. Permissions are declared, and what is undeclared
reads as "not permitted" (authorization defaults to refusal).

In particular, **the permission to release a stopped state is separated from the permission to
stop**. If one principal holds both, the idea of an independent approval does not hold.

### A release records first, then changes the state

The order of the steps that lift a stopped state is the safety itself.

    confirm → verify the independent approval → verify the recovery evidence → append and persist
    the record → **and only then** lift the state

The reverse order produces the worst shape: the record fails after the state is lifted, and
**neither the evidence that it was stopped nor the stopped state exists**. Where it cannot be
recorded, **it stays stopped**. And a re-run under the same approval completes the cleanup safely.

### Do not collapse assurance into a single strong/weak value

"It is signed" is not "it is independent". **If one principal, or one key, can produce both
lineages, it is not independent review.** Collapsing them lets that misreading through unchallenged.

At minimum these are kept as separate axes:

    identity assurance      how far the judge's identity was confirmed
    recorder assurance      was the recorder observed, or declared?
    workload isolation      same process / same user / separate host?
    reviewer independence   a different signer, or a different workload?

And **a level that was not confirmed is never called confirmed**. What a shared key yields is
roughly "stronger than a declaration". **Only an isolated writer, a limited path, protected keys,
and per-principal authorization together earn the name authentication.** Asking a separate process
is not a trust boundary.

Having separated the levels, **do not use a weaker level's result for enforcement**. It serves as
evidence; it does not serve as grounds for demanding independence.

### A record used in a check is writable only by whoever checks

A mechanism checking a cap or a history **must not allow the records it reads to be written
freely**. Measured: one negative exposure entered through an ordinary append voided the cap
completely (and the chain was reported sound).

**Declare per record class which operation may write it.** This is not identity authentication
(under the same privileges one can impersonate the writer), but it does close "it can be written
through the ordinary path, by accident or design".

**The rule is not applied when verifying what is already written**, though — the path leaves no
trace in the record, so it can only be confirmed at the moment of writing. Applying it makes a
correctly written record be refused as "something that should not have been writable", and reports
a sound ledger as broken.

### A re-run and a different request under the same key are different

A matching idempotency key still **is not a re-run where the request's content differs**. Measured:
a large amount got through on the grounds of a permit for a small one. Alongside the key there is
**a digest of the request's content**, and a difference is refused as a conflict.

And the key is **a hash of a canonical tuple, not a concatenation with a separator**. A value
containing the separator makes a different tuple produce the same key.

### Do not trust the exit code alone

When calling a tool that returns a structured result, **read the result**. Reading the exit code
alone lets through an implementation that "says refused and exits 0" (which is what happened).

It passes **only on the pair** of `exit code 0` and `the result is a permit`. No result, an
unreadable result, a contradiction — all fall to refusal. "The result cannot be read" and "the
result read as a refusal" are different events, though. The first is an environment problem, so a
development escape hatch may apply; **the second must not have one**.

### Do not stop, with a check, what was declared free

Applying **a check that demands a quantity** to an operation decided as "not metered" (deleting
something regenerable, say) **stops it**. Measured: deleting `node_modules` was refused as "weight
0, so it cannot be reserved" — stopping what was decided to be free is the exact opposite of the
design. **What is not metered does not enter the metering path.**

### Do not rename what a stop is called

When the source of a judgment is rearranged, **keep the message's vocabulary**. Supervisors and
checks alike look for particular words, so renaming it while the substance is unchanged makes "the
fact that it stopped" invisible.

### One identifier is not enough for an idempotency key

The key that stops a re-run of the same operation being double-counted bundles **(session, call,
rule, record class)**. The call's identifier alone collides across sessions and across rules.

And **a missing key refuses a metered operation**. Without being able to confirm identity, the
guarantee of not double-counting does not hold at all.

Where the documentation does not say whether "the check runs twice within one call", **do not read
the silence as "it does not"**. With a key attached, running twice is still counted once.

### An escape hatch is traded for a record

Placing an explicit escape hatch on a path that cannot be fully blocked is right. It is permitted
**because the declaration is recorded**, though — not because someone said they declared it. **A
bypass whose recording failed does not pass.**

### fail-closed cannot be claimed without fault injection

The property "it stops on failure" **cannot be confirmed without making it fail**. Trying only the
happy path and writing "it is fail-closed" is stating that something unchecked was checked.

A worked example: it was written that it stops when the lock fails. But the replacement did not
match and was never applied, the deciding variable was initialised and never set, and the
escape-hatch environment variable existed nowhere in the code. **The happy path passed, so nothing
was noticed.**

So the tools carry an entry point for fault injection (`ORG_LEDGER_FORCE_LOCK_FAIL=1` and the
like). A check whose failure path cannot be reproduced cannot be confirmed even by whoever wrote
it.

### Checking a timestamp's format is not checking that it exists

`2026-99-99T99:99:99Z` matches `YYYY-MM-DDTHH:MM:SSZ` and does not exist. **Parse it as a real
datetime.** And refuse the future and the too-distant past, so the order cannot be faked — either
one puts "what happened just now" outside the window and bypasses a cap that aggregates over it.

The path that can specify a timestamp is **separated from ordinary writes**, with the intent in the
name (`--backfill-ts`). One argument doing both "record now" and "fill in the past" makes the
latter's checks get in the former's way.

And **do not write a fixed date into a test that checks timestamps.** It breaks the moment that
time turns from future into past (which is exactly how my own test broke in the version that added
this check). Build it relative to now.

### A missing validation rule works as quietly as a missing declaration

Do not read a configuration diff as "is the block there". Read **what is missing inside it**. With
one validation rule gone, a record that should be refused passes, and nothing records that it did.

And when filling rules in, **only add**. Replacing the whole block deletes the **stricter** rules
the org added itself — measured: an org's own `required.progress_recorded: [milestone]` was lost to
a repair. **A repair that weakens an org's own safety settings is not a repair but a regression.**

Where a different value sits in the same position, do not overwrite automatically. A tool cannot
tell whether the org changed it deliberately or the template changed, so **report it as a conflict
and let a human decide**. And omissions and conflicts **come out of one computation** — deciding
them separately detects one and misses the other (which is what happened).

**Do not carve a configuration block's extent with a regex.** `\nkey:\n(?:(?: |\n).*\n)*` swallows
the comment lines before the next top-level key, and their children. In practice one replacement
deleted another block wholesale, and **the result parsed as YAML**, which made it hard to notice.
The extent is decided by "the next line with no indentation".

### A repairing tool does not break things when it stops partway

A repair that overwrites the configuration file in place creates **a state where that org can write
nothing** if it stops partway. Replace via temp → fsync → rename → fsync(dir). A repair that breaks
things is the worst shape there is.

### Tightening can become an availability incident

Applying "refuse what is undeclared" to everything at once **turns a divergence between the
declaration and reality into "the whole org stops recording"**. That is not fail-closed but **an
availability incident caused by a known migration gap**. Keep them apart.

Validation goes in along separate axes:

    required        refuse a missing required field, for declared classes only
    require_any     any one of several correlation keys is enough (it differs by path)
    enum / type     validate a declared field **where it is present**
    closed world    refuse the undeclared, for the few classes to be tightened

The undeclared is allowed by default and **recorded as a divergence** (made visible without
stopping anything). Only the core of the controls is strict from the start, and a diverging class
is tightened as a separate migration **after reality is reflected into the declaration**.

Do not fix on one correlation key. Where the keys pointing at the same subject differ by path, the
shape is **any one of them is enough**. Fixing on one rejects legitimate writes.

### A copy of what someone owns goes stale unless it is distributed

A design where the org owns its own configuration file is right (the org decides its own format).
But **when the plugin side adds a declaration, the org's copy stays old**. Adding a check that
"the undeclared cannot be written" on top of that stops recording immediately after an update.

So before the check there is **a tool that diagnoses the difference** and **a tool that fills it in
explicitly**. The diagnosis says whether it is in use — a missing class that real data uses carries
a different urgency.

And **the filling side does not rewrite an existing declaration.** Overwriting a declaration the
org changed to match reality puts the check at odds with reality. It only adds.

**Verify the result before a repair writes.** The first version of this repair inserted the
template's block wholesale, produced two `event_classes`, and — YAML taking the later one — deleted
the declarations of sixty-five classes. **A repair that breaks things** is the worst shape there
is, so before writing it confirms "does it parse" and "has nothing been lost".

### An undeclared class can be written and is never read

The classes writable to the ledger and the classes the schema declares drift apart if left alone.
**An undeclared class rides on neither a projection nor a sensor, so writing it leaves it unread.**
In practice five classes the tools were writing went undeclared, and two of them had five and
twenty-three rows in real data. It was part of why `show`'s warning went silent.

When a check goes in, **bring the declaration in line with reality**. Count the payloads in real
data before writing it. A declaration at odds with reality makes the check a lie.

### HEAD is a cache, not the authority

Where an append-only record keeps a separate file pointing at the tail, **treat it as a cache
rebuildable from the log.** Making it authoritative means the whole record becomes unreadable when
the cache breaks.

**Do not auto-repair corruption partway, though.** Laying a consistent HEAD over a torn line, a
gap in seq, or a hash mismatch makes the corruption invisible. Corruption is reported fail-closed.

### Testing with fake records comes to light when the check goes in

Seeding the ledger with hand-assembled events (carrying no hash) fails the moment the chain's
soundness starts being checked. **The check is right** — appending to a ledger with no chain must
not be possible. Tests go through the real append path too.

### If controls are distributed, they run on what was distributed alone

When a control mechanism becomes a distributed artifact, **make it complete within that artifact**.
A shape that references the original working tree loses the controls the moment that tree moves.
And their disappearance is silent: ordinary operations keep succeeding.

There is only one way to confirm self-containment — **remove the original tree temporarily and run
it**. A remaining reference fails there.

### Do not think installing and enabling are the same thing

"It is installed" and "it is in effect" are different. In the environment measured, **installing
and enabling the artifact still had the checking mechanism silently skipped until it was trusted** —
no warning, no record, nothing. "Installed and not in effect" is at its least visible in this
shape.

So the artifact's documentation states **what enabling requires** and **what the not-yet-enabled
state looks like**. Do not write it in a way that reads as "install it and it works".

And in **a mechanism managing trust through a signature bound to the content**, updating the
artifact can drop that trust. Write this down too, as a path by which an update voids the
controls.

### Do not carry another environment's format over as-is

Two environments adopting a similar format still **accept different things**. A worked example:
adding one comment key to a configuration file passed in one environment and had **the whole file
skipped** in the other. The controls' configuration was voided wholesale, and ordinary operations
kept succeeding.

When porting, **have that environment actually read it and confirm**. Similar formats are no
evidence of identical ones.

### Verify a refusal paired with "try once and stop"

Do not decide whether a refusal worked from the actor's final result. **Achieving the goal by
another means after being correctly refused reads as "the refusal did not work".**

During verification the actor is instructed to "**try once and, if refused, stop without using an
alternative**". And the evidence of the refusal is confirmed not from the actor's report but from
**the subject being unchanged** and **the refusal being recorded**.

### Write down whom it is mandatory for

A tool running as a PreToolUse hook is mandatory for **an agent on a host where the hook is
enabled**, and holds no force over a host owner who can disable it. That is a boundary, not a
defect.

What becomes a problem is not the limit itself but **stating "unavoidable" without writing the
boundary down**. State the trusted computing base and the threat model, and the same implementation
is assessed correctly.

And inside the boundary there are **attributes that are not authenticated**. The ledger's `actor`
is taken from an argument, so one process can claim to be the maker and the gate in turn. The
separation of duties is therefore **evidence that a review happened**, not proof of who performed
it. Lineage separation has the same property — independent review, not authenticated independence.
**Do not call a label a trust boundary.**

### Do not confuse catching a deviation with understanding an adaptation

A supervisor making the same state change without the right tool is usually **not about speed but
about not paying the cost of remembering the tool's name**. That is not a lack of discipline but
**an adaptation**.

So when adding a check, design **catching the deviation** and **preserving the structure of the
adaptation** separately. Adding only the catching produces, next, a way out that merely satisfies
the check formally (requiring `--verified` and having "I confirmed it" pass is the same thing).
The escape hatch is not fully blocked; it takes a shape where **taking it leaves a record**
（`bypass_declared`・`judges_disagreed`・`correction`）。

**That an inconvenient record cannot be deleted** is why this org's ledger is append-only. A
correction is an appended `correction` rather than a deletion — a deletable record gets deleted
whenever someone wants it gone.

### A failed split often shows up as a missing requirement

The latter half of the Issue that went past ten rounds was work answering none of that Issue's EARS
items (UPDATE/INSERT permissions between members, expressing consent, freezing the premises — not
one of them in the MUSTs). In the skeptic's words, it **"protected a decorative text column while
leaving the amount, the payer, the direction of the debt, and group ownership undefended"**.

In a deliverable that handles authorization, the lopsidedness of MUSTs setting only "who may enter"
and never "what can be done once inside" **can be detected at filing time**. Catching it as a
problem of the requirements is cheaper than waiting for it to surface as a problem of the split.

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
  This is the state the org is judged against: the work is *merged into `develop` and testable there* —
  not a pile of per-task PRs against `main` that were never assembled. With human diff review retired
  (§4f), this green is not a *precondition* for review — it **is** the verdict, and the reasoning behind
  admitting it lands on the objective Issue like any other judgment.
- **who owns it.** No new "integrator" rank (docs/09 §1 forbids minting PM ranks). The **supervising
  manager's A3 accountability** (docs/09 — "verify subordinate work against its contract") is *extended*
  from per-child conformance to the **cross-deliverable integration test on `develop`**: the manager
  who fanned the work out owns bringing it back together and proving it works assembled.
- **deploy is `develop` → `main`.** Only an integrated, green `develop` promotes to `main` (deploy, §3),
  keeping the trunk always-shippable (docs/11 §0) with the integration buffer in front of it.

So the hand-back a task submits is a **PR against `develop`** (not `main`), and "done" means "merged to
`develop`, integration-green, with the integrate verdict and its reasoning recorded on the Issue" (§4f).
Nobody reads the diff; the assembled, green `develop` plus the recorded judgment is the whole account.

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
