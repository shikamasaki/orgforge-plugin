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

### 検査は、自分が要求している文面と同じ厳しさで書く

ガードのメッセージが「子プロンプトの**冒頭に1行**書く」と言っているのに、検査は**全文の部分
一致**だった。結果、**否定文が宣言として通った** — 「contract も `INDEPENDENT:` も付けて
いません」がそのまま独立宣言として一致した（実地のプローブ）。

実害のある形は「この作業は independent ではないので contract を付ける」と書いた spawn が
独立宣言と誤判定されることで、**独立宣言は `owns` の宣言を免除する**ので、偶然の一致で免除が
取れる。**検査が文面より緩いと、正しく書いた人だけが厳しい制約を負う。**

同じ穴が seam 側にもあった: `"seam contract"` という**語**を見ていたため、「no seam contract is
attached」が宣言として通った。語ではなく**構造**（`## Your slice` / `Inputs you receive:` /
`Outputs you MUST produce:`）を見る — 構造は否定文に現れない。「`Inputs you receive:` が無い」と
書くことはあっても、コロン付きの見出しを否定文の中に置くことはまずない。

**一般形**: 宣言や約束を検査するなら、**それが現れる位置と形**を見る。散文に混ざりうる語だけを
見ると、その語について語っただけで検査を通過する。この org が繰り返し塞いできた「確かめて
いないことを確かめたかのように述べる」の、**道具側の変種**である。

### 観測経路が値を隠すことがある

`intake` が「本命ケースだけ exit=0」と報告されたが、実装は3経路すべてで 10 を返していた。
原因は**パイプ**で、`| tail` を通すとシェルの終了コードは最後のコマンドのものになる。

**実装が正しくても、観測が違えば同じように誤判断が起きる。** 終了コードで判定させる設計は、
パイプを挟まれた瞬間に無効になる — 機械が拾う判定は**出力の中**にも置く（`INCOMPLETE` の1行）。

### 報告の切断 — 判定として読む前に、形を見る

subagent の turn が**作業の途中で終わる**ことがある: `status` は
completed で返り、`result` は「Now the key attack:」のような宣言1文だけ。`SendMessage` で
再開させると続きを実行して完走したので、**agent が死んだのではなく、報告が成果物の形になる
前に turn が終わっている**。

**危ないのは、それらしく切れた形である。** 「Now the key attack:」なら verdict が無いと分かる
が、「MUST 2 は防がれました」で切れていたら、それを verdict として読んで admit しかねない。
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
1周 ≈ 15.3分 ／ 反証による周回 = 214分 / 269分 = 79%
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

### 記録の手順が、判定の実行を要求してはいけない

判定を記録するために必要な値を得る手段が「判定をもう一度回すこと」なら、監督はその手順を
飛ばす。実例: 判定対象の id を知るために材料を組むコマンドを打ち、別ハーネスの judge が
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

判定に使う読み取りは、書き手が起動時に固定した実体を見る。**参照を張り替えられても、
見る先は動かない。**

### 検査の入力を、検査される側が書けてはいけない

統制の判定に使う値が **記録の本文に書けるもの**なら、それは検査ではない。実測で、2つの文字列を
本文に書くだけで職務分離の強制を回避できた。

**そして自分のテストがその偽装を「正しい経路」として固定していた。** 検査を足したとき、
その検査が読む値を **誰が書けるか**を必ず確かめる。書ける側が書いた値を根拠にすると、
検査は形だけになり、テストがそれを正常系として保存する。

判定に使う値は、**検証した経路だけが生成する**形にする。本文に書かれた同名の値は拒否する。

### 設定は三値で読む

有効・無効の二値で読むと、**読めないときに無効へ倒れる**。有効にしていた org が、設定ファイルが
壊れた瞬間に無防備になる（実測: 破損前 exit 3 → 破損後 exit 0）。

読み取りは **有効・無効・判定できない** の三値にし、判定できないなら止める。構文の破損だけでなく、
**型が違う**場合（map であるべき所が文字列、真偽値であるべき所が別の値）も「判定できない」に
含める — 曖昧な値を「無効」と読まない。

### 評価に使う値は、署名が覆う

署名された記録に、**署名の外側の欄**を混ぜてはいけない。実測で、独立性の評価に使う値が署名の外に
あり、署名後にその値を強い方へ書き換えても検証が通った。

評価に使うなら署名対象に入れる。そして **形式が変わったら版を上げる** — 古い版の記録を新しい
規則で読むと、覆っていない値を覆っていると誤解する。

### 中身の権限を絞っても、入れ物を差し替えられるなら意味が無い

権威データの権限を絞っても、**その親ディレクトリが呼び出し側の所有**なら、ディレクトリごと
置き換えられる。実体を呼び出し側の管理下から出し、参照だけを残す。そして **実際に書く側には
実体のパスを渡す** — 参照を張り替えられても、書き込み先は動かない。

### 名乗りを変えられるなら、名乗りの比較に意味は無い

職務分離を「誰が書いたか」の比較で行うとき、**その「誰か」を自由に名乗れるなら統制は無い**。
実測で、本人としての自己承認は拒否されるのに、同じプロセスが別名を名乗ると通った。

塞ぐには、統制の中核となる記録に **検証済みの署名由来の主体** を要求する。ただし要求を有効に
すると、署名の仕組みを持たない既存の運用が全部止まる — **既定は無効にし、鍵を配ってから
有効にする**。無効が安全という意味ではなく、移行を可能にするための既定である。

### 権限は「作れること」と「守れること」の両方を満たす

経路を守るために親ディレクトリの権限を絞るとき、**その経路を作る側が作れるか**を確かめる。
実測で、root 所有の読み取り専用ディレクトリには、別の主体として動く常駐プロセスが socket を
**作れなかった** — 守りすぎて動かない。

解決は階層を分けることである。**anchor**（呼び出し側が書けない）と **leaf**（作る側が書ける）
に分け、保証は「anchor に書けないので leaf ごと差し替えられない」とする。

### 別の主体が守っていることと、判断が独立していることは別

書き込みを担う主体を隔離しても、**判断する主体同士が独立しているかは別の問い**である。実測で、
書き手の隔離値が判断者の隔離として記録され、鍵が違うだけで「別ワークロード」に昇格していた。

欄を分けること。書き手の隔離は書き手の性質であり、判断者の独立性は判断者が申告するか、
分からなければ「不明」である。**借りてきた値で昇格させない。**

### 導入する側と、受け入れる側の条件を突き合わせる

設定を書く道具と、その設定で動く道具が別なら、**両者の条件が食い違っていないかを確かめる**。
実例: 導入スクリプトが親ディレクトリを group から書ける形にし、**受け入れる側がまさにその形を
拒否した** — 導入は成功し、daemon は起動しない。

そして **前提を検査する主体を間違えない**。利用者の環境に必要なものが揃っていても、実際に動く
主体（別の利用者として起動される常駐プロセス）から見えなければ意味が無い。検査は**動く側の
環境で**行う。

### 「書けない」と「見えない」を混同しない

統制が要求するのは書けないことであって、見えないことではない。**読めない記録は、監査のための
記録ではない。** 権限を絞るときは、検査・集計・投影が動き続けることを同時に確かめる。

### 検証が検証対象を壊してはいけない

境界を確かめるために「書いてみる」と、成功したときに本物が壊れる。**開けるかどうかだけを見て、
1バイトも書かない。** 権限を変えられるかは、実際に変えるのではなく**所有者を見る**。停止できるか
を確かめるために止めてはいけない — 止まったら、以降の検証も、実運用の統制も落ちる。

副作用がゼロで回せる経路を用意する。そして **その経路では「通せること」を確かめていない**と
明記する — 止まるだけの仕組みは運用できない。

### 隔離を主張する前に、実測で確かめる

設定を書いたことは、境界があることではない。**通常の呼び出し側から実際に書けないこと**を測る。
書き込み・権限変更・経路の差し替え・停止を、それぞれ試して失敗することを確かめる。

その検証は **特権で走らせてはいけない** — 特権なら全部できてしまい、何も確かめたことにならない。

### 鍵が違うことは、主体が違うことではない

共有鍵では、**検証できる側が署名も作れる**。したがって別の共有鍵を使っても示せるのは「鍵が
違う」ことだけで、別の主体・別のプロセス・独立した承認は何も示さない。**それを独立性の根拠に
すると、名前と保証がまた食い違う。**

非対称にすると、判断する側が秘密鍵を持ち、**検証する側は公開鍵だけを持つ** — 検証する側は
判断を作れない。これは「申告より強い」attestationの条件である。

ただし鍵を非対称にしただけでは、**ワークロードは隔離されていない**。同じ利用者が書き手も鍵も
差し替えられるなら、そこはまだidentity authenticationの境界ではない。隔離は別の軸として残す。
orgforgeは異なるモデル系統によるレビュー品質の非相関化を狙う。別host/KMS/HSMをコアの
前提にしてR0を破ってはいけない。

### 署名が正しいことと、その判定を出してよいことは別

検証が通っても、**その主体がその役・その血統の判定を出す権限を持つか**は別の問いである。
権限は宣言し、宣言の無いものは「許可されていない」と読む（認可の既定は拒否）。

とくに **止めた状態を解除する権限は、止める権限と分ける**。同じ主体が両方を持つなら、独立した
承認という考え方が成り立たない。

### 解除は、記録してから状態を変える

止まった状態を解く手順の順序が、そのまま安全性である。

    確認 → 独立した承認の検証 → 復旧の証拠の検証 → 記録の追記と永続化 → **その後で** 状態を解く

逆順にすると、状態を解いたあとに記録が失敗して、**止まっていた証拠も、止まっている状態も無い**
という最悪の形になる。記録できなかったら、**止まったままにする**。そして同じ承認での再実行が
安全に後片付けを完了できるようにする。

### 保証を1つの強弱値に潰さない

「署名されている」は「独立している」ではない。**同じ主体、あるいは同じ鍵が両方の血統を作れる
なら、それは独立レビューではない。** 潰すと、この誤読がそのまま通る。

少なくとも次を別の軸にする:

    identity assurance      判断者の identity をどこまで確かめたか
    recorder assurance      記録者を観測したのか、申告なのか
    workload isolation      同じプロセス／同じ利用者／別ホストか
    reviewer independence   別の署名者か、別のワークロードか

そして **確かめられていない段階を「確かめた」と呼ばない**。共有鍵で得られるのは、申告より強い
という程度である。**認証と呼べるのは、隔離された書き手・限定された経路・鍵の保護・主体ごとの
認可が揃ったときだけ**である。別プロセスに問い合わせることは、信頼境界ではない。

段階を分けたなら、**弱い段階の結果を「強制」に使わない**。証拠にはなるが、独立性を要求する
根拠にはならない。

### 検査に使う記録は、検査する側だけが書ける

上限や履歴を検査する仕組みは、その検査が読む記録を**自由に書けてはいけない**。実測で、負の曝露を
1件通常の追記で入れるだけで、上限が完全に無効になった（しかも鎖は健全と報告された）。

**記録の種類ごとに「どの操作が書けるか」を宣言する。** これは identity の認証ではない（同じ権限
なら writer を騙れる）が、「通常の経路で偶然にも意図的にも書けてしまう」ことは塞げる。

ただし**既に書かれたものを検証するときは、この規則を適用しない** — 経路は記録に残らないので、
書いた時点でしか確かめられない。適用すると、正しく書かれた記録が「書けないはずのもの」として
拒否され、健全な台帳が壊れていると報告される。

### 再実行と、同じキーの別の要求は違う

冪等キーが一致しても、**要求の内容が違えば再実行ではない**。実測で、少ない量の許可を根拠に
大きな量が通った。キーとは別に**要求内容の digest** を持ち、違えば衝突として拒否する。

そしてキーは**区切り文字での連結ではなく、正規化した組の hash** にする。値に区切り文字が入ると、
別の組が同じキーになる。

### 終了コードだけを信じない

構造化された結果を返す道具を呼ぶなら、**結果を読む**。終了コードだけを見ると、「拒否と言いながら
0 で終わる」実装を通してしまう（実測でそうなった）。

`終了コードが 0` かつ `結果が許可` の**組でしか通さない**。結果が無い・読めない・矛盾している —
すべて拒否側に倒す。ただし「結果が読めない」と「読めた結果が拒否」は別の事象である。前者は環境の
問題なので開発用の逃げ道が効いてよいが、**後者に逃げ道を効かせてはいけない**。

### 無料と宣言したものを、検査で止めない

「これは計量しない」と決めた操作（再生成できる対象の削除など）に、**量を要求する検査をかけると
止まる**。実測で、`node_modules` の削除が「重み 0 なので予約できない」として拒否された — 無料だと
決めたものを止めるのは、設計と真逆の結果である。**計量しないものは、計量の経路に入れない。**

### 止まったことの呼び名を変えない

判断の出所を組み替えたとき、**メッセージの語彙を維持する**。監督も検査も特定の語を探しているので、
中身が同じでも呼び名が変わると「止まったことが見えなくなる」。

### 冪等キーは、識別子1つでは足りない

同じ操作の再実行を二重に数えないためのキーは、**(セッション, 呼び出し, 規則, 記録の種類)** を
束ねる。呼び出しの識別子だけでは、別のセッションや別の規則の間で衝突する。

そして **キーが欠けていれば、計量される操作を拒否する**。同一性を確かめられないなら、二重計上
しないという保証そのものが成り立たない。

「同じ呼び出しで検査が二度走るか」が文書に書かれていないなら、**書かれていないことを「走らない」
と読まない**。キーを付けておけば、走っても数えられる。

### 逃げ道は、記録と引き換えである

塞ぎきれない経路に明示の逃げ道を置くのは正しい。ただし **宣言が記録されるから許される**のであって、
宣言したと言えば許されるのではない。**記録に失敗した迂回は通さない。**

### fail-closed は、故障注入できなければ主張できない

「失敗したら止まる」という性質は、**失敗させてみなければ確かめられない**。正常系だけを試して
「fail-closed にした」と書くのは、検査していないことを検査したと述べることである。

実例: ロックの失敗時に止まる、と書いた。しかし置換が一致せず適用されておらず、判定用の変数は
初期化されるだけで設定されず、逃げ道の環境変数はコードのどこにも無かった。**正常系は通るので、
何も気づかなかった。**

だから故障注入の口を道具に持たせる（`ORG_LEDGER_FORCE_LOCK_FAIL=1` のような）。異常系を
再現できない検査は、書いた本人にも確かめられない。

### 時刻の形式検査は、実在性の検査ではない

`YYYY-MM-DDTHH:MM:SSZ` に合っていても、`2026-99-99T99:99:99Z` は実在しない。**実日時として
parse する。** そして順序を偽れないよう、未来と遠すぎる過去を拒否する — どちらも「いま起きた
こと」を窓の外に置き、窓で集計する上限を迂回できる。

時刻を指定できる経路は、**通常の書き込みから分ける**。名前に意図を出す（`--backfill-ts`）。
同じ引数で「いまを記録する」と「過去を補う」の両方ができると、後者の検査が前者を邪魔する。

そして **時刻を検査するテストに固定日付を書かない。** その時刻が未来から過去に変わった瞬間に
壊れる（実際に、この検査を入れた版で自分のテストがそう壊れた）。いまからの相対で組む。

### 検証規則の欠落は、宣言の欠落と同じくらい静かに効く

設定の差分を「ブロックがあるか」で見てはいけない。**中身の欠落**を見る。検証規則が1つ消えて
いれば、拒否されるべき記録が通り、通ったことは記録に残らない。

そして規則を埋めるときも、**足すだけにする**。ブロックごと差し替えると、org が自分で足した
**厳格な**規則が消える — 実測で、org が加えた `required.progress_recorded: [milestone]` が
修復で失われた。**修復が org 所有の安全設定を弱めるのは、修復ではなく退行である。**

同じ位置に違う値があるときは、自動で上書きしない。org が意図して変えたのか、テンプレートが
変わったのかは道具では判別できないので、**衝突として報告して人に決めさせる**。そして欠落と衝突は
**1つの計算から出す** — 別々に判定すると、片方だけ検出して片方を見落とす（実測でそうなった）。

**設定ブロックの範囲を正規表現で切らない。** `\nkey:\n(?:(?: |\n).*\n)*` は、次のトップレベル
キーの前にあるコメント行やその子行まで飲み込む。実際に、ある置換が別のブロックを丸ごと消し、
**結果は YAML として読めた**ので気づきにくかった。範囲は「インデントの無い次の行」で決める。

### 修復する道具は、途中で止まっても壊さない

設定ファイルを直接上書きする修復は、途中で止まると**その org が何も書けない状態**を作る。
temp → fsync → rename → fsync(dir) で置き換える。修復が壊すのは最悪の形である。

### 厳格化は、可用性事故になりうる

「宣言の無いものを拒否する」を全体に一度にかけると、**宣言と実態の乖離が「組織全体の記録停止」に
変わる**。それは fail-closed ではなく、**既知の移行不備による可用性事故**である。区別すること。

検証は軸を分けて入れる:

    required        宣言したクラスだけ、必須の欠落を拒否
    require_any     相関キーは複数のうち1つでよい（経路によって違う）
    enum / 型       宣言済みの項目は **存在する場合に** 検証
    closed world    厳格化したい少数のクラスだけ、未宣言を拒否

未宣言のものは既定で許し、**乖離として記録する**（見えるようにするが止めない）。統制の中核だけ
最初から厳格にし、乖離しているクラスは**実態を宣言に反映してから**別の移行として厳格化する。

相関キーを1つに固定してはいけない。同じ対象を指すキーが経路によって違うなら、**どれか1つで
足りる**形にする。固定すると正当な書き込みを弾く。

### 所有物のコピーは、配らないと古くなる

org が自分の設定ファイルを所有する設計は正しい（org が自分の形式を決める）。しかし**プラグイン
側が宣言を増やしても、org のコピーは古いまま**である。そこに「宣言の無いものは書けない」検査を
入れると、更新直後に記録が止まる。

だから検査より先に、**差分を診断する道具**と**明示的に埋める道具**を持つ。診断は「使われている
かどうか」を言うこと — 実データで使われているクラスが欠けているなら、緊急度が違う。

そして **埋める側は既存の宣言を書き換えない。** org が実態に合わせて変えた宣言を上書きすると、
検査が実態と食い違う。足すだけにする。

**修復の書き込み前に、結果を検証すること。** この修復の初版は、テンプレートのブロックを丸ごと
挿入して `event_classes` を2つにし、YAML の後勝ちで65クラスの宣言を消した。**修復が壊す**のは
最悪の形なので、書く前に「読めるか」「減っていないか」を確かめる。

### 宣言の無いクラスは、書けても読まれない

台帳に書けるクラスと、schema が宣言しているクラスは、放っておくとずれる。**宣言の無いクラスは
projection にも sensor にも乗らないので、書いても読まれない。** 実際に、道具が書いていた5つの
クラスが宣言されておらず、そのうち2つは実データに5件・23件あった。`show` の警告が沈黙した一因
でもある。

検査を入れるときは、**宣言を実態に合わせる**こと。実データの payload を数えてから書く。
宣言が実態と違えば、検査は嘘になる。

### HEAD は権威ではなく cache である

追記型の記録で、末尾を指すファイルを別に持つなら、**それは log から再構築できる cache として
扱う。** 権威にすると、cache が壊れたときに記録全体が読めなくなる。

ただし **途中の破損を自動修復してはいけない。** torn line、seq の飛び、hash 不一致の上に整合した
HEAD を載せると、壊れていることが分からなくなる。破損は fail-closed で報告する。

### 偽の記録で試験すると、検査を入れたときに露見する

手で組んだイベント（hash の無いもの）で台帳を seed していると、鎖の健全性を検査し始めた瞬間に
落ちる。**それは検査が正しい** — 鎖の無い台帳に追記できてはいけない。試験も実際の追記経路を
通すこと。

### 統制を配るなら、配ったものだけで動くこと

統制の仕組みを配布物にするなら、**その配布物の中だけで完結させる**。元の作業ツリーを参照する形は、
そのツリーが動いた瞬間に統制が消える。しかも消えたことは静かで、通常の操作は成功し続ける。

自己完結を確かめる方法は1つしかない — **元のツリーを一時的に無くして動かす**。参照が残っていれば
そこで落ちる。

### 導入と有効化を、同じことだと思わない

「入れた」と「効いている」は別である。実測した環境では、**配布物を入れて有効にしても、検査の
仕組みは信頼されるまで黙って読み飛ばされた** — 警告も、記録も、何も出ない。「入れたのに効いて
いない」は、この形でいちばん見えにくい。

したがって配布物の説明には、**有効化に何が必要か**と、**有効化されていない状態がどう見えるか**を
書く。「入れれば効く」と読める書き方をしてはいけない。

そして**内容に束縛された署名で信頼を管理する仕組み**では、配布物を更新すると信頼が外れうる。
更新が統制を無効化する経路として、これも書いておく。

### 他所の形式をそのまま持ち込まない

似た形式を採る2つの環境でも、**受け付けるものは違う**。実例として、設定ファイルにコメント用の
キーを1つ入れたところ、片方の環境では通り、もう片方では**ファイル全体を読み飛ばされた**。
統制の設定が丸ごと無効になり、しかも通常の操作は成功し続けた。

移植するときは、**その環境で実際に読ませて確かめる**。形式が似ていることは、同じであることの
証拠にならない。

### 拒否の検証は「1回だけ試して止まる」ことと対で行う

拒否が効いたかを、行為者の最終結果で判定してはいけない。**正しく拒否された後に別の手段で目的を
達成すると、「拒否が効かなかった」と読める**。

検証のときは行為者に「**1回だけ試し、拒否されたら代替手段を使わず終了する**」と指示する。そして
拒否の証拠は、行為者の報告ではなく**対象物が変わっていないこと**と**拒否が記録されていること**で
確かめる。

### 誰に対して強制的なのかを書く

PreToolUse hook として動く道具は、**hook を有効にしたホスト上の agent**に対しては強制的だが、
hook を無効化できるホスト所有者に対しては強制力を持たない。これは欠陥ではなく境界である。

問題になるのは限界そのものではなく、**境界を書かずに「回避不能」と述べること**である。
信頼境界（TCB）と脅威モデルを明示すれば、同じ実装が正しく評価される。

そして境界の内側にも、**認証されていない属性**がある。台帳の `actor` は引数から採られるので、
1つのプロセスが maker と gate を名乗り分けられる。したがって職務分離は「**レビューが行われた
証拠**」であって「誰が行ったかの証明」ではない。血統の分離も同じ性質を持つ — 独立したレビュー
であって、認証された独立性ではない。**ラベルを信頼境界と呼ばないこと。**

### 摘発と、適応の理解を混同しない

監督が正しい道具を使わずに同じ状態変更を行うのは、多くの場合**遅いからではなく、道具の名前を
思い出すコストを払わなかったから**である。それは規律の欠如ではなく**適応**である。

したがって検査を足すときは、**逸脱の摘発**と**適応の構造を残すこと**を分けて設計する。摘発だけを
足すと、次はその検査を形式的に満たすだけの逃げ方が生まれる（`--verified` を必須にすれば「確かめ
た」と書くだけで通るのと同じ）。逃げ道は塞ぎきらず、**逃げたことが記録に残る**形にする
（`bypass_declared`・`judges_disagreed`・`correction`）。

**都合の悪い記録が消せないこと**が、この org の台帳が append-only である理由である。訂正は
削除ではなく `correction` の追記で行う — 消せる記録は、消したい人がいるときに消える。

### 分割の失敗は、しばしば要求の欠落として現れる

10周を超えた Issue の後半は、その Issue の EARS のどれにも対応していない作業だった（メンバー間の
UPDATE / INSERT 権限・同意の表現・前提の凍結 — MUST に1件も無い）。skeptic の言葉では
**「装飾的なテキスト列を守り、金額・支払者・債務の向き・グループ所有権を無防備にしていた」**。

認可を扱う deliverable なのに、MUST が「誰が入れるか」しか定めておらず「入った後に何が
できるか」を定めていない、という偏りは**起票時に検出できる**。切り方の問題として現れる前に、
要求の問題として捕まえるほうが安い。

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
