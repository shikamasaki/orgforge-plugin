# orgforge-plugin

**orgforge stands up and runs an AI-native IT business company: it decides what to build, builds it
through a forced, non-skippable SDLC, ships continuously via CI/CD, operates on a reliability budget,
and does it all reproducibly — the org and the system it builds grow together.** This repository is
the template for standing one up. AI is an amplifier — it magnifies whatever process it's dropped
into, good or bad — so the hard part isn't the model; it's that a company left running unattended
drifts, skips phases, duplicates, over-spends, and ships the wrong thing unless the organization it
runs as, and the mold it builds through, are **written down and enforced**.

Four properties are the headline, and each has a chapter behind it:

- **A business, not just an org.** It decides *what to build as a business* — customer / RFP /
  priority — not merely "does tasks." (THEORY §1b, [docs/01](docs/01-requirements.md) R0b.)
- **A forced SDLC mold.** Every deliverable travels a non-skippable phase chain —
  requirements → design → implement → test → integrate → deploy → operate — enforced by a ledger phase-gate, not
  a prompt. ([docs/11](docs/11-sdlc-mold.md).)
- **Ships and operates continuously.** Deploy is a phase; CI/CD (GitHub Actions) is its spine; the
  running company navigates by a reliability/error budget and DORA metrics to the moving bottleneck.
  ([docs/05](docs/05-lifecycle-operations.md), [docs/11](docs/11-sdlc-mold.md).)
- **Reproducible, at two levels.** *Same org spec + RFP ⇒ same process, gates, contracts, and
  verification* (Level 1); and *the repos it builds clone-and-run the same for anyone* (Level 2 —
  committed lockfile, pinned toolchain, one-command setup+test, green CI from a clean clone), checked
  by a deterministic tooth, not asserted. This is the **deep purpose** of forcing the SDLC type.
  ([docs/11](docs/11-sdlc-mold.md) §0/§4a, [docs/01](docs/01-requirements.md) J14/S9.)

**New here?** [`QUICKSTART.md`](QUICKSTART.md) installs the plugin and walks the happy path — found a
company, watch it build and ship a backlog item through the forced SDLC, then operate — in a few
minutes, no OSS publish required (a private repo or local path both install).
[`ARCHITECTURE.md`](ARCHITECTURE.md) is the whole-system map: the ecosystem (neutral core → projection
→ harness), the organs, and the two coupled lifecycles — the org's metabolism and the product's SDLC.
[`REFERENCE.md`](REFERENCE.md) is the flat lookup: every env var, command, ledger event, cap, and the
fixes for problems people actually hit.
[`docs/README.md`](docs/README.md) is the reasoning, in **four Parts / twelve chapters**.
[`CHANGELOG.md`](CHANGELOG.md) tracks what's new.

### How it gets there — the load-bearing bet

Concretely, a "department" here is nothing exotic: **an existing coding-agent harness — Claude
Code, Codex — pointed at a working directory whose instruction file is that one role's job.** The
template doesn't build a runtime; it writes down the organization and projects each role onto a
harness that already exists. The heavy machinery a running company needs — the loop, the scheduler,
the tools, sandboxing, **and the CI/CD substrate** — is *borrowed* from the host, not rebuilt (R0).

So the design act reduces to one thing: **put the organization into words the AI can act on**, and
force the shape the work travels through. The payoff is concrete and vendor-neutral. The *same*
neutral guardrail blocks a real tool call because Claude Code and Codex share the pre-tool hook
contract — verified on the Claude Code CLI, and designed to block identically on Codex through that
shared contract (the Codex run is the adopter's step, not yet exercised here). No rewrite per vendor,
no bespoke per-vendor runtime.

That is the opposite of the field's other "company of agents" frameworks (MetaGPT, ChatDev, CrewAI),
which each build their own bespoke runtime. Here the harness, the loop, and CI/CD are organs the
industry *already built*, so the template ships only a thin neutral core — the org skeleton as
declarative data, a **projection** of each role onto its harness's instruction-file convention, the
forced-SDLC phase-gate, and a machine audit of the skeleton and the repos it produces. What the
product must do is **[docs/01-requirements.md](docs/01-requirements.md)** (read it before judging the
repo: a design or review is measured against it first).

Enforcement is never *forced delegation*: **doctrine promotes** the right shape and **lint/hooks
enforce** the load-bearing constraints (the phase-gate, the caps, separation of duties). The tacit
knowledge a human company runs on has to become explicit — that is the *how* under the four
properties above, not a competing thesis.

> A human company runs on things it never writes down — what we're trying to do, who needs to
> know what, who owns which deliverable, and which calls the boss makes vs. delegates. People
> carry that tacitly. An AI can't: what it reads is what it acts on, and what it infers unwritten
> is unreliable and un-auditable — so the moment AI runs the work autonomously, the load-bearing
> tacit knowledge has to become **explicit**.

---

## Why a company, decomposed as an org

The unit orgforge stands up is an **AI-native IT business company** (THEORY §1b): its purpose isn't
"solve tasks" but *decide what to build as a business, build it through a disciplined SDLC, ship it,
and operate it* — with the org and the system growing together. That is the content of the seven
organs; everything below is how you make a *company* run unattended without it drifting.

An LLM agent produces aligned work only if the **right information reaches it in the right amount**
(context) and the **division of labor is clear** (roles) — otherwise the output is a coarse,
essence-missing average, and over a 24/7 run those small misalignments compound. And because AI is an
**amplifier**, a company with *no enforced mold* doesn't build faster — it produces more, faster, of
whatever it was already doing wrong. Those are organizational problems. The industry re-invented
fragments bottom-up — *context engineering*, *harness engineering*, *loop engineering* — without
forcing the questions that decide whether an unattended company stays on-goal: *is the goal
propagated? is the division of labor clear? did the work actually pass every SDLC phase? which
decisions stay with the human?* This template centers on those, and it does so by borrowing the
large frames the field already has — classical management theory (Mintzberg, Greiner, span of
control, separation of duties) plus the software-delivery canon (the SDLC, CI/CD, DORA, error
budgets), where that grounding is still thin for agents — and turning them into
**machine-checkable constraints**: an org chart the lint validates, a decision line the projection
enforces, a separation of duties a hook actually blocks on, and a **forced phase-gate** that refuses
to let a deliverable skip a phase. The empirical backing is direct: multi-agent LLM systems fail
mostly at role clarity, information flow, and verification (the MASFT study) — precisely the tacit
things left un-said. See **[THEORY.md](THEORY.md)** for the full picture (its §0–§1b are the core;
the rest is reference); the research map is in [docs/sources.md](docs/sources.md).

## What decomposing from the org tells you that harness+loop can't

Decomposing from the organization (not from the parts) changes what you build:

- It tells you **what you are missing.** A harness+loop view has no concept of *span of control*,
  so it never asks "how many agents can one supervisor actually watch before review quality
  collapses?" Organizational theory does.
- It tells you **when to add hierarchy** (Greiner growth stages) — and, more importantly,
  when **not** to (a middle-management layer is the *last* resort, not the first; invest in
  information flow to widen span and stay flat).
- It tells you **what must never self-organize.** The common counter to designed structure is that
  *self-organizing agents outperform designed ones*
  ([arXiv 2603.28990](https://arxiv.org/pdf/2603.28990)) — but read closely that result is about
  **task-solving efficiency** (the *exploration* layer) and its hybrid finding actually *strengthens*
  the two-layer stance here (see [docs/sources.md](docs/sources.md)). It says nothing about
  *control*: separation of duties,
  authorization, anti-gaming, safety. Let exploration self-organize; **design the control skeleton
  only.** (See [docs/03-organic-vs-mechanistic.md](docs/03-organic-vs-mechanistic.md).)

## What's in here

The inventory below is large, but the split is simple: the **neutral core** the repo actually
ships is the declarative skeleton + the projection + the machine audit (the lint and the organ
tools). Everything the docs call "heavy" — the loop, the scheduler, perception, sandboxing — is
**delegated to the host harness**, not built here (that's R0). The docs are the articulation; the
tools are its machine-checkable proof; the templates are what you fill in for your own org.

**Start here**

| Path | What it is |
|---|---|
| [docs/README.md](docs/README.md) | **The map** — the reasoning in four Parts / twelve chapters, read as one argument (Part I Foundations → Part IV North star). Start here for the *why*. |
| [docs/01-requirements.md](docs/01-requirements.md) | **The product spec** — actors, jobs-to-be-done, success criteria, the IT-business-company scope (R0b), reproducibility (J14/S9), and the load-bearing requirement (R0): an LLM must run autonomously on an *existing* harness, no bespoke runtime. A design or review is judged against this first. |
| [THEORY.md](THEORY.md) | The intellectual core: organization → seven organs (harness & loop are two of them, delegated to existing harnesses — not rebuilt), and §1b — *which* organization: an AI-native IT business company. §0–§1b are the point. |

**The four Parts** (full chapter list in [docs/README.md](docs/README.md)):

| Part | Chapters | What it covers |
|---|---|---|
| **I — Foundations** | [01 Requirements](docs/01-requirements.md), [04 Failure Modes](docs/04-failure-modes.md) | What the system must be (the IT-business-company scope, reproducibility) and what organization theory warns will break it (Goodhart, Conway, tall hierarchies, phase-skipping, the amplifier failure). |
| **II — Design** | [02 Scaling](docs/02-growth-stages.md), [03 Control skeleton & decomposition](docs/03-organic-vs-mechanistic.md), [07 Context economy](docs/07-context-economy.md), [08 Execution / R0](docs/08-runtime.md) | The design law: grow staged / run elastic, design the control skeleton and split along the right seams, need-to-know context, and **delegate the loop / harness / scheduler / CI-CD to the host** — ship no runtime. |
| **III — Operate** | [05 Operating a running company](docs/05-lifecycle-operations.md), [06 Doctrine](docs/06-doctrine-and-knowledge.md), [09 Supervising role](docs/09-attention-allocation.md), [10 Loop reliability](docs/10-loop-reliability.md), [11 SDLC mold](docs/11-sdlc-mold.md) | The 24/7 mechanics: lifecycle + operating/safety events (blast-radius, reconciliation, the reliability-budget and DORA instruments), doctrine that grows with the system, attention & accountability, why the loop survives, and **the forced SDLC mold that makes the build reproducible**. |
| **IV — North star** | [12 Ideal state](docs/12-ideal-state.md) | What orgforge is *for* — an AI-native IT business company with a spec-driven build engine — bounded by *autonomy is bounded by verifiability* and the **amplifier constraint**, plus the honest, enumerated gap still to close. |

**The demonstrated run & maps**

| Path | What it is |
|---|---|
| [demos/S1-founding-rehearsal.md](demos/S1-founding-rehearsal.md) | **S1, demonstrated:** a real RFP run end-to-end on a real host harness — maker, gate, and skeptic as three separate agents, no bespoke runtime — where the adversarial checker caught a genuine bug (a U+212A unicode edge case) the maker and gate both missed. Artifacts in [examples/founding-rehearsal/](examples/founding-rehearsal/). |
| [docs/sources.md](docs/sources.md) | Every citation, with primary/secondary honestly distinguished. |

**Templates**

| Path | What it is |
|---|---|
| [template/organization.yaml](template/organization.yaml) | Declare your org as data: departments, roles (job descriptions), supervisors, span, Maker/Checker, growth stage. |
| [template/ROLE.md](template/ROLE.md) | A job-description template for one role/department (the "profile"). |
| [template/SUPERVISOR.md](template/SUPERVISOR.md) | The supervision loop spec — the 1-on-1 that checks direction and corrects profiles. |
| [template/FOUNDER.md](template/FOUNDER.md) | The founding process: RFP → purpose → inverse-Conway architecture → output contracts → full latent org, minimally activated. |
| [template/constitution.yaml](template/constitution.yaml) | The charter (定款, *teikan* — articles of incorporation): delegated / charter/*ringi* (稟議 — an approval queue inspired by Japanese written-proposal practice) / irreversible-hold tiers, night rules, invariants. Written by humans, writable by no agent. |
| [template/moves.yaml](template/moves.yaml) | The legal-move catalog: every structural change the org may make, with preconditions, tier, and reversal. |
| [template/ledger-schema.yaml](template/ledger-schema.yaml) | The audit/enforcement record, specified: event classes, hash-chained envelope, derived views (the only context-pack vocabulary), pack assembly, proposal & digest shapes. |
| [template/sensors.yaml](template/sensors.yaml) | Every crisis signal as a measurement: source views, formula, window, threshold, machine/llm judge, and the night-preregistration list. |
| [template/PROJECTION.md](template/PROJECTION.md) | **The LLM-config layer** — how the articulated org renders into each harness's actual config: what goes into a department's instruction file (CLAUDE.md / AGENTS.md / …), and the neutral→per-harness settings map. The one harness-specific layer; everything above it is neutral. |
| [template/role-settings.yaml](template/role-settings.yaml) | The neutral model/runtime settings per role — model *tier* (not vendor string), effort, capability scope (the deontic "who may do what"), stop condition, output form. Risk-calibrated; lint-checked (optional extra file) for coherence with the org chart. |
| [template/schedule.yaml](template/schedule.yaml) | The declarative operating schedule (docs/05 §5.6): which operating-event check runs on which cadence, whether it is night-safe, and the `verify_event` that proves it ran. The registrar (an LLM) edits it; `org_lint.py`'s `SCH` checks are the guardrail keeping edits R0-safe, night-safe, and missed-tick-detectable. Data, not a runtime — [tools/tick.py](tools/tick.py) plans from it; the host cron drives. |

**Tools**

| Path | What it is |
|---|---|
| [tools/org_lint.py](tools/org_lint.py) | The audit gate: meant to run as the gate on every founding/reorg commit (run it as a pre-commit check; it cross-validates all five data files — organization, constitution, moves, ledger-schema, sensors) against the theory (Goodhart, span, SoD, control-never-dormant, need-to-know packs). |
| [tools/doctrine.py](tools/doctrine.py) | The knowledge organ as running code (docs/06): a file-backed per-role doctrine store + admission gate + render + stale check. Enforces no-anonymous-doctrine (provenance), untrusted-until-admitted (gate-only admit), TTL, and render-admitted-only within a token budget. The curator's watch and the scheduler that calls it are the host's (R0). |
| [tools/ledger.py](tools/ledger.py) | The record organ as running code (ledger-schema.yaml): append-only, hash-chained (tamper-evident, replayable by `verify` — the watchdog primitive), gapless seq, actor-from-runtime-not-payload, `requires_prior` enforced at write time (the skeptic is load-bearing), and deterministic view/census/**digest** projections (same window + same ledger ⇒ byte-identical). |
| [tools/sensors.py](tools/sensors.py) | Evaluates the **machine** sensors of sensors.yaml as pure formulas over the ledger (red_tape_ratio, doctrine_stale, blocked_on_missing_context, …). `llm` sensors and those whose inputs aren't fully in the ledger are honestly **deferred**, never silently skipped. |
| [tools/guardrails.py](tools/guardrails.py) | The three load-bearing safety events for 24/7 unattended operation (docs/05 §5.1): BLAST-RADIUS-CAP (aggregate exposure the approval queue can't see), STATE-RECONCILED (ledger-belief vs external ground truth), STALE-REFERENCE (roles silent against a reference that moved). Each is fail-quiet on the happy path (exit 0) and escalates the exception (exit 10). |
| [tools/reconcile.py](tools/reconcile.py) | Lateral, in-flight reconciliation between peers (docs/05 §5.2) — the one net-new information flow the meetings dissolved into: COLLISION-SCAN (overlapping claims), DEPENDENCY-STALL (silence-as-block made explicit), CONTRACT-CHANGE (a breaking seam change announced before it lands). Duplicate self-heals laterally; only a true conflict escalates. |
| [tools/resource.py](tools/resource.py) | Allocation, prioritization, and grant-decay events (docs/05 §5.4): PRIORITY-RANKING (emits only when the order changes), ALLOCATION-RECLAIM (takes back stranded compute from idle/low-yield holders, safe-direction), AUTHORITY-EXPIRED (auto-narrows stale grants; escalates only to widen). |
| [tools/learning.py](tools/learning.py) | OUTCOME-DELTA (docs/05 §5.4): the org learning from its OWN track record (distinct from doctrine's outside-world intel). Joins closed decisions to realized outcomes; silent when they matched; escalates only when the same miss recurs systemically. |
| [tools/attention.py](tools/attention.py) | A department's INTERNAL work selection (docs/09): given its backlog, picks what to do next by situated attention (anchored to the org-wide priority ranking), problemistic search (what's failing vs aspiration), sequential attention (rank-order prefix), and a WIP limit. Records why in the ledger, flags choices that drift off the org ranking. |
| [tools/alignment.py](tools/alignment.py) | The proxy-stack guards (docs/05): PREMISE (is the founding premise still true — the sensor for the human's pivot/sunset decision), SUNK-COURSE (a running course outrunning its own progress — the runaway BLAST-RADIUS-CAP can't see), FRAME-REVIEW (accurate predictions against a target that may itself be wrong — double-loop). Each surfaces; the human decides. |
| [tools/conventions.py](tools/conventions.py) | Internal precedent (docs/05 §6.5): the org's own settled "how we do X here," adopted through a checker, projected into a role's workspace, TTL'd. A third knowledge box — internal (vs doctrine's external), reusable, so peers don't re-derive and diverge. |
| [tools/tick.py](tools/tick.py) | The self-driving schedule **planner** (docs/05 §5.6), not a scheduler (R0). Given [template/schedule.yaml](template/schedule.yaml) + now + the ledger, it computes which checks are due, applies the night fail-safe, and — the guardrail — **detects a due check that did NOT run** (a missing verify_event) and escalates it. "It was supposed to run" becomes a paged fact. The host cron only invokes this planner. |
| [tools/repro_lint.py](tools/repro_lint.py) | The **Level-2 reproducibility gate** (docs/11 §4a): deterministic check that a repo the org *builds* is reproducible for a stranger — committed lockfile + populated manifest, pinned toolchain, one-command setup+test in a README, idempotent migrations, `.env.example`, a green CI-from-clean-clone workflow. Tagged by the earliest SDLC phase that requires each artifact; run BY THE GATE at the implement/test/deploy phase gates, not trusted from a maker's "I verified it." Exit 0 = present, 10 = a gate should HOLD. |

## How to use it

**Track A — manual (the v0.1 spirit).** You design and operate the org by hand:

1. Read [THEORY.md](THEORY.md) §0–§1 once — they are short and they are the point (the rest is
   reference you can pull as needed).
2. Copy [template/organization.yaml](template/organization.yaml) and describe **your** system as an
   organization: what are the departments, who supervises whom, where is the Maker/Checker line,
   what growth stage are you in.
3. For each department, write a **profile** from [template/ROLE.md](template/ROLE.md) — a job
   description that loads the right prior context (onboarding) before it acts.
4. Stand up the **supervision loop** ([template/SUPERVISOR.md](template/SUPERVISOR.md)): periodically
   check each department's *direction*, and when it drifts, **edit the profile** (the org's way of
   coaching an employee) so the next run is corrected. This applies to **organic roles only** —
   editing a mechanistic (control-layer) profile is a charter-tier change, not a supervision tweak.
5. Consult [docs/02-growth-stages.md](docs/02-growth-stages.md) before adding a department or a layer.

**Track B — autonomous founding (v0.4).** The org designs and runs itself inside human-written law,
**on an existing harness**:

1. Read [docs/01-requirements.md](docs/01-requirements.md) — it fixes what "runs autonomously" means
   and that the heavy organs are delegated to the host harness, not built.
2. Humans author [template/constitution.yaml](template/constitution.yaml) from the template — the
   charter no agent may write.
3. Hand an RFP to the founder process ([template/FOUNDER.md](template/FOUNDER.md)); it produces the
   full latent org plus its output contracts and each department's **neutral profile**.
4. The founding commit must pass [tools/org_lint.py](tools/org_lint.py) **and** human charter
   approval.
5. **Project** each active department's profile onto the host harness that will run it (its
   instruction-file convention — [docs/08-runtime.md](docs/08-runtime.md) §2), and let that harness
   supply the loop, tools, and scheduling. The org runs within the constitution
   ([docs/05-lifecycle-operations.md](docs/05-lifecycle-operations.md)), reorganizing only through
   [template/moves.yaml](template/moves.yaml); doctrine and scopes evolve per
   [docs/06](docs/06-doctrine-and-knowledge.md) and [docs/07](docs/07-context-economy.md).

**Track C — wire it to a real harness ([integrations/](integrations/)).** Step 5 above, made
concrete for Claude Code and Codex. The organs become **direct harness features**: a `PreToolUse`
hook (the *same* neutral `org_hook.py` on both harnesses — they share the exit-2 block contract)
makes a blast-radius cap or a mandate check **actually block a real tool call**; a `SessionStart`
hook injects the role's doctrine + conventions every cycle; departments run headless via
`claude -p` / `codex exec` (the runner projects one neutral role onto either); the schedule's
cadences are realized by the harness's own scheduler (Claude Code's `/schedule` / `/loop`, or a
cron), and `tools/tick.py` detects a missed check so "the schedule stopped firing" is a paged fact
([integrations/claude-code/SCHEDULER.md](integrations/claude-code/SCHEDULER.md)). Ships as a Claude
Code **plugin** — hooks + subagents + commands. The **commands you use** are few, and the setup path is
three of them in order: **`/orgforge-plugin:org-init`** (set up the org's state, env, and labels), **`/orgforge-plugin:org-found`**
(draft the org from a brief into four fixed-name artifacts — `REQUIREMENTS.md`, `FEATURE-INVENTORY.md`,
`ARCHITECTURE.md` = the 全体設計書, `coverage-manifest.md`), **`/orgforge-plugin:org-decompose`** (carve those into
atomic SPEC task Issues, coverage-gated, each self-contained enough to be picked up from any
environment). **既にコードがあるリポジトリに後付けする場合**は `/org-found` ではなく
**`/orgforge-plugin:org-adopt`**（実在するコードから設計を読み取り、未実装分だけを manifest に
載せ、機械バーの現状を baseline として記録する）。 Then **`/orgforge-plugin:org-start`** (bring it to its running state), **`/orgforge-plugin:org`** (the status
board — GREEN/AMBER/RED), and **`/orgforge-plugin:org-triage`** (feed a signal into the backlog); `/orgforge-plugin:org-mandate` and
`/orgforge-plugin:org-verify-guards` handle the occasional exception. The org's **own metabolism** — `/orgforge-plugin:org-work`,
`/orgforge-plugin:org-discover`, `/orgforge-plugin:org-tick` — runs on cadence and you rarely type it. Plus a Codex `.codex/` config;
neutral core, one folder per harness. See [integrations/README.md](integrations/README.md).

## Status & honesty

v0.9. This is a **framing + template**, distilled from published organizational theory and the
current agent-engineering literature. The parts (principal-agent theory, harness/loop engineering,
runtime substrates like AIOS, automated agent design like ADAS/DGM) already exist; the contribution
here is **the top-down organizational decomposition that places them** — and, per the research in
[docs/sources.md](docs/sources.md), applying *classical* management theory (Mintzberg, Greiner,
span of control, separation of duties) to agent design is where the literature is currently thin.

The design is **harness-neutral and delegation-first**: the heavy organs (perception, tools, loop,
scheduling, sandboxing) are the host harness's job; this repo ships the skeleton, the profile
projection, and the lint (docs/01, docs/08). The lint cross-validates all five data files and is the
one part that runs standalone today. **S1 — one organization from this template launching and doing
useful work on an existing harness end-to-end, with nothing bespoke in the loop — has now been
demonstrated once ([demos/S1-founding-rehearsal.md](demos/S1-founding-rehearsal.md), artifacts in
[examples/founding-rehearsal/](examples/founding-rehearsal/)): three departments ran as separate
agents, the maker/checker separation held structurally, and the adversarial checker caught a real bug
the maker and gate both missed.** That answers the load-bearing "has it ever run?" question. What
remains: an automated projection layer (which instruction-file conventions to target — done by hand
in the rehearsal), the Tier-B host-environment controls for asset-touching orgs, the multi-cycle
elastic lifecycle at scale, and the client/delivery/company-layer surfaces (docs/01 §7). The fuller
autonomy story is still ahead; the design is no longer unrun.

**0.9 retires human diff review** (docs/11 §4f) on the argument that at fan-out volume a reviewer who
cannot keep up skims, and a skimmed diff enters the record as reviewed. What replaces it is mechanical:
an unread-safe bar (complexity ceilings, closed type escapes, no blanket inline suppressions,
duplication/dead-code scanning, multi-OS CI), a gate and an adversarial skeptic whose independence is
now enforced at *write* time (the ledger refuses an admission from the actor that did the work), and a
mandatory record — every judgment carries its reasoning, its evidence, and any knowingly-accepted risk
onto the task Issue. Two limits stated plainly rather than glossed: the reasoning digest makes an
edited account **detectable but not impossible**, and the periodic re-hash sweep that would make that
continuous is not yet an organ. And docs/11 §4f.3 argues against comprehension debt (Osmani) rather
than ignoring it — the substitution is argued, not proven, and the honest test is whether the domain
model keeps growing (§4d) once an org runs for months.

The value of any org design is proven by whether the organization actually **produces**, not by the
elegance of its chart. Treat this as scaffolding for that, not a substitute for it.

## License

MIT — see [LICENSE](LICENSE).
