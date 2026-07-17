# org-first-agents

**The goal is to run the engineer's problem-solving process autonomously, around the clock — AI
that keeps working while you sleep, with you deciding only the essential calls.** This repository
is a template for getting there. The hard part isn't the model; it's that a system left running
unattended drifts, duplicates, over-spends, and ships the wrong thing unless the org it runs as is
written down.

**New here?** [`QUICKSTART.md`](QUICKSTART.md) installs the plugin and proves a guardrail blocks
in a few minutes — no OSS publish required (a private repo or local path both install).
[`CHANGELOG.md`](CHANGELOG.md) tracks what's new (0.2.0: hierarchical doctrine, refounding,
delegation seams, and a blast-radius cap that no longer blocks normal work).

Concretely, a "department" here is nothing exotic: **an existing coding-agent harness — Claude
Code, Codex — pointed at a working directory whose instruction file is that one role's job.** The
template doesn't build a runtime; it writes down the organization and projects each role onto a
harness that already exists.

So the design act reduces to one thing: **put the organization into words the AI can act on.**
The payoff is concrete and vendor-neutral. The *same* neutral guardrail blocks a real tool call
because Claude Code and Codex share the pre-tool hook contract — verified on the Claude Code CLI,
and designed to block identically on Codex through that shared contract (the Codex run is the
adopter's step, not yet exercised here). No rewrite per vendor, no bespoke per-vendor runtime.

That is the load-bearing bet, and it is the opposite of the field's other "company of agents"
frameworks (MetaGPT, ChatDev, CrewAI), which each build their own bespoke runtime. Here the harness
and the loop are organs the industry *already built*, so the template ships only a thin neutral
core — the org skeleton as declarative data, a **projection** of each role onto its harness's
instruction-file convention, and a machine audit of the skeleton. What the product must do is
**[docs/01-requirements.md](docs/01-requirements.md)** (read it before judging the repo: a design
or review is measured against it first).

> A human company runs on things it never writes down — what we're trying to do, who needs to
> know what, who owns which deliverable, and which calls the boss makes vs. delegates. People
> carry that tacitly. An AI can't: what it reads is what it acts on, and what it infers unwritten
> is unreliable and un-auditable — so the moment AI runs the work autonomously, the load-bearing
> tacit knowledge has to become **explicit**.

---

## Why the org, not the parts

An LLM agent produces aligned work only if the **right information reaches it in the right amount**
(context) and the **division of labor is clear** (roles) — otherwise the output is a coarse,
essence-missing average, and over a 24/7 run those small misalignments compound. Those are
organizational problems. The industry re-invented fragments bottom-up — *context engineering*,
*harness engineering*, *loop engineering* — without forcing the questions that decide whether an
unattended system stays on-goal: *is the goal propagated? is the division of labor clear? which
decisions stay with the human, which run unattended?* This template centers on those, and it does
so by borrowing the large frames the field already has — classical management theory (Mintzberg,
Greiner, span of control, separation of duties), where that grounding is still thin for agents —
and turning them into **machine-checkable constraints**: an org chart the lint validates, a
decision line the projection enforces, a separation of duties a hook actually blocks on. The
empirical backing is direct: multi-agent LLM systems fail mostly at role clarity, information flow,
and verification (the MASFT study) — precisely the tacit things left un-said. See
**[THEORY.md](THEORY.md)** for the full picture (its §0–§1 are the core; the rest is reference);
the research map is in [docs/sources.md](docs/sources.md).

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
| [docs/01-requirements.md](docs/01-requirements.md) | **The product spec** — actors (client vs operator vs department vs host harness), jobs-to-be-done, success criteria, the two-tier threat model, and the load-bearing requirement (R0): an LLM must run autonomously on an *existing* harness, no bespoke runtime. A design or review is judged against this first. |

**Core theory**

| Path | What it is |
|---|---|
| [THEORY.md](THEORY.md) | The core: organization → seven organs (harness & loop are two of them, delegated to existing harnesses — not rebuilt). |
| [docs/05-elastic-organization.md](docs/05-elastic-organization.md) | Why "no salary cost" changes everything (and what it doesn't): design the ideal org fully on day one, run it elastically. |
| [docs/06-lifecycle-operations.md](docs/06-lifecycle-operations.md) | Cradle to grave: founding from an RFP, 24-hour autonomous operation (an approval queue with a delegation-of-authority (決裁権限) matrix — inspired by the written-proposal aspect of 稟議 (*ringi*), not its consensus formation — plus night safe mode), maintenance, handover, sunset. |
| [docs/07-doctrine-and-knowledge.md](docs/07-doctrine-and-knowledge.md) | The knowledge organ: market-watching boundary spanners feed a role-scoped knowledge base; each role's doctrine (べき論 — its current normative playbook) is updated through Maker/Checker and always loaded as context. |
| [docs/08-context-economy.md](docs/08-context-economy.md) | Need-to-know information flow: scoped context packs, contract-interface collaboration, context budgets, and commander's-intent policy propagation. |
| [docs/09-runtime.md](docs/09-runtime.md) | Execution: **delegate the heavy organs to the host harness, project the profile onto its instruction-file convention.** What the system adds (projection + skeleton + lint) vs. what the host provides (perception, tools, loop, scheduling, sandboxing). |
| [docs/10-founding-rehearsal.md](docs/10-founding-rehearsal.md) | **S1, demonstrated:** a real RFP run end-to-end on a real host harness — maker, gate, and skeptic as three separate agents, no bespoke runtime — where the adversarial checker caught a genuine bug (a U+212A unicode edge case) the maker and gate both missed. Artifacts in [examples/founding-rehearsal/](examples/founding-rehearsal/). |
| [docs/12-attention-allocation.md](docs/12-attention-allocation.md) | How a single department decides **what to work on next** — the intra-unit attention organ (Carnegie School sequential attention + problemistic search, Ocasio situated attention, ToC/Kanban WIP). The org-wide ranking finally reaches the work, and the work's ordering becomes auditable. Running code: [tools/attention.py](tools/attention.py). |
| [docs/13-proxy-stack-and-conflict.md](docs/13-proxy-stack-and-conflict.md) | Is the org still solving the **right problem**? Five gaps a theory-coverage sweep found — PREMISE/telos-validity, sunk-course, double-loop frame-review (the proxy stack), mandate-conflict adjudication (against a human-declared precedence), and internal precedent — plus the honest DROP list (motivation, culture-as-whole, politics: no AI analog). Running code across [tools/alignment.py](tools/alignment.py), [tools/reconcile.py](tools/reconcile.py), [tools/conventions.py](tools/conventions.py). |
| [docs/11-operating-events.md](docs/11-operating-events.md) | What a 24/7 **unattended** org needs beyond founding, named by essence not by human ritual: why 1-on-1 / team-sync / exec-review *dissolve* into existing organs (only lateral peer reconciliation is net-new), and the governing rule — **reconcile by exception, never stop to meet** (default silent; escalate only the exception). The three load-bearing safety events are running code ([tools/guardrails.py](tools/guardrails.py)). |

**Playbooks & maps**

| Path | What it is |
|---|---|
| [docs/02-growth-stages.md](docs/02-growth-stages.md) | Greiner-based playbook: which organ to add at each stage of growth. |
| [docs/03-organic-vs-mechanistic.md](docs/03-organic-vs-mechanistic.md) | Resolving "designed structure vs self-organization" via a two-layer split. |
| [docs/04-failure-modes.md](docs/04-failure-modes.md) | The failure modes organizational theory warns about, mapped to agent orgs. |
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
| [template/ledger-schema.yaml](template/ledger-schema.yaml) | The single source of truth, specified: event classes, hash-chained envelope, derived views (the only context-pack vocabulary), pack assembly, proposal & digest shapes. |
| [template/sensors.yaml](template/sensors.yaml) | Every crisis signal as a measurement: source views, formula, window, threshold, machine/llm judge, and the night-preregistration list. |
| [template/PROJECTION.md](template/PROJECTION.md) | **The LLM-config layer** — how the articulated org renders into each harness's actual config: what goes into a department's instruction file (CLAUDE.md / AGENTS.md / …), and the neutral→per-harness settings map. The one harness-specific layer; everything above it is neutral. |
| [template/role-settings.yaml](template/role-settings.yaml) | The neutral model/runtime settings per role — model *tier* (not vendor string), effort, capability scope (the deontic "who may do what"), stop condition, output form. Risk-calibrated; lint-checked (optional extra file) for coherence with the org chart. |
| [template/schedule.yaml](template/schedule.yaml) | The declarative operating schedule (docs/11 §5): which operating-event check runs on which cadence, whether it is night-safe, and the `verify_event` that proves it ran. The registrar (an LLM) edits it; `org_lint.py`'s `SCH` checks are the guardrail keeping edits R0-safe, night-safe, and missed-tick-detectable. Data, not a runtime — [tools/tick.py](tools/tick.py) plans from it; the host cron drives. |

**Tools**

| Path | What it is |
|---|---|
| [tools/org_lint.py](tools/org_lint.py) | The audit gate: meant to run as the gate on every founding/reorg commit (run it as a pre-commit check; it cross-validates all five data files — organization, constitution, moves, ledger-schema, sensors) against the theory (Goodhart, span, SoD, control-never-dormant, need-to-know packs). |
| [tools/doctrine.py](tools/doctrine.py) | The knowledge organ as running code (docs/07): a file-backed per-role doctrine store + admission gate + render + stale check. Enforces no-anonymous-doctrine (provenance), untrusted-until-admitted (gate-only admit), TTL, and render-admitted-only within a token budget. The curator's watch and the scheduler that calls it are the host's (R0). |
| [tools/ledger.py](tools/ledger.py) | The record organ as running code (ledger-schema.yaml): append-only, hash-chained (tamper-evident, replayable by `verify` — the watchdog primitive), gapless seq, actor-from-runtime-not-payload, `requires_prior` enforced at write time (the skeptic is load-bearing), and deterministic view/census/**digest** projections (same window + same ledger ⇒ byte-identical). |
| [tools/sensors.py](tools/sensors.py) | Evaluates the **machine** sensors of sensors.yaml as pure formulas over the ledger (red_tape_ratio, doctrine_stale, blocked_on_missing_context, …). `llm` sensors and those whose inputs aren't fully in the ledger are honestly **deferred**, never silently skipped. |
| [tools/guardrails.py](tools/guardrails.py) | The three load-bearing safety events for 24/7 unattended operation (docs/11 §2): BLAST-RADIUS-CAP (aggregate exposure the approval queue can't see), STATE-RECONCILED (ledger-belief vs external ground truth), STALE-REFERENCE (roles silent against a reference that moved). Each is fail-quiet on the happy path (exit 0) and escalates the exception (exit 10). |
| [tools/reconcile.py](tools/reconcile.py) | Lateral, in-flight reconciliation between peers (docs/11 §2.4) — the one net-new information flow the meetings dissolved into: COLLISION-SCAN (overlapping claims), DEPENDENCY-STALL (silence-as-block made explicit), CONTRACT-CHANGE (a breaking seam change announced before it lands). Duplicate self-heals laterally; only a true conflict escalates. |
| [tools/resource.py](tools/resource.py) | Allocation, prioritization, and grant-decay events (docs/11 §3): PRIORITY-RANKING (emits only when the order changes), ALLOCATION-RECLAIM (takes back stranded compute from idle/low-yield holders, safe-direction), AUTHORITY-EXPIRED (auto-narrows stale grants; escalates only to widen). |
| [tools/learning.py](tools/learning.py) | OUTCOME-DELTA (docs/11 §3): the org learning from its OWN track record (distinct from doctrine's outside-world intel). Joins closed decisions to realized outcomes; silent when they matched; escalates only when the same miss recurs systemically. |
| [tools/attention.py](tools/attention.py) | A department's INTERNAL work selection (docs/12): given its backlog, picks what to do next by situated attention (anchored to the org-wide priority ranking), problemistic search (what's failing vs aspiration), sequential attention (rank-order prefix), and a WIP limit. Records why in the ledger, flags choices that drift off the org ranking. |
| [tools/alignment.py](tools/alignment.py) | The proxy-stack guards (docs/13): PREMISE (is the founding premise still true — the sensor for the human's pivot/sunset decision), SUNK-COURSE (a running course outrunning its own progress — the runaway BLAST-RADIUS-CAP can't see), FRAME-REVIEW (accurate predictions against a target that may itself be wrong — double-loop). Each surfaces; the human decides. |
| [tools/conventions.py](tools/conventions.py) | Internal precedent (docs/13 §5): the org's own settled "how we do X here," adopted through a checker, projected into a role's workspace, TTL'd. A third knowledge box — internal (vs doctrine's external), reusable, so peers don't re-derive and diverge. |
| [tools/tick.py](tools/tick.py) | The self-driving schedule **planner** (docs/11 §5), not a scheduler (R0). Given [template/schedule.yaml](template/schedule.yaml) + now + the ledger, it computes which checks are due, applies the night fail-safe, and — the guardrail — **detects a due check that did NOT run** (a missing verify_event) and escalates it. "It was supposed to run" becomes a paged fact. The host cron only invokes this planner. |

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
   instruction-file convention — [docs/09-runtime.md](docs/09-runtime.md) §2), and let that harness
   supply the loop, tools, and scheduling. The org runs within the constitution
   ([docs/06-lifecycle-operations.md](docs/06-lifecycle-operations.md)), reorganizing only through
   [template/moves.yaml](template/moves.yaml); doctrine and scopes evolve per
   [docs/07](docs/07-doctrine-and-knowledge.md) and [docs/08](docs/08-context-economy.md).

**Track C — wire it to a real harness ([integrations/](integrations/)).** Step 5 above, made
concrete for Claude Code and Codex. The organs become **direct harness features**: a `PreToolUse`
hook (the *same* neutral `org_hook.py` on both harnesses — they share the exit-2 block contract)
makes a blast-radius cap or a mandate check **actually block a real tool call**; a `SessionStart`
hook injects the role's doctrine + conventions every cycle; departments run headless via
`claude -p` / `codex exec` (the runner projects one neutral role onto either); a cron drives
`tools/tick.py`, which detects a missed check so "the schedule stopped firing" is a paged fact.
Ships as a Claude Code **plugin** (hooks + subagents + `/org-tick`, `/org-mandate` commands) and a
Codex `.codex/` config — neutral core, one folder per harness. See
[integrations/README.md](integrations/README.md).

## Status & honesty

v0.4. This is a **framing + template**, distilled from published organizational theory and the
current agent-engineering literature. The parts (principal-agent theory, harness/loop engineering,
runtime substrates like AIOS, automated agent design like ADAS/DGM) already exist; the contribution
here is **the top-down organizational decomposition that places them** — and, per the research in
[docs/sources.md](docs/sources.md), applying *classical* management theory (Mintzberg, Greiner,
span of control, separation of duties) to agent design is where the literature is currently thin.

The design is **harness-neutral and delegation-first**: the heavy organs (perception, tools, loop,
scheduling, sandboxing) are the host harness's job; this repo ships the skeleton, the profile
projection, and the lint (docs/01, docs/09). The lint cross-validates all five data files and is the
one part that runs standalone today. **S1 — one organization from this template launching and doing
useful work on an existing harness end-to-end, with nothing bespoke in the loop — has now been
demonstrated once ([docs/10](docs/10-founding-rehearsal.md), artifacts in
[examples/founding-rehearsal/](examples/founding-rehearsal/)): three departments ran as separate
agents, the maker/checker separation held structurally, and the adversarial checker caught a real bug
the maker and gate both missed.** That answers the load-bearing "has it ever run?" question. What
remains: an automated projection layer (which instruction-file conventions to target — done by hand
in the rehearsal), the Tier-B host-environment controls for asset-touching orgs, the multi-cycle
elastic lifecycle at scale, and the client/delivery/company-layer surfaces (docs/01 §7). The fuller
autonomy story is still ahead; the design is no longer unrun.
The value of any org design is proven by whether the organization actually **produces**, not by the
elegance of its chart. Treat this as scaffolding for that, not a substitute for it.

## License

MIT — see [LICENSE](LICENSE).
