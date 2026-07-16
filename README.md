# org-first-agents

**In a world where AI runs the work around the clock and the human decides only the essential
things, designing an agent system reduces to one act: putting the organization into words an AI
can act on.** This repository is a template for that articulation.

> A human company runs on things it never writes down — what we're trying to do, who needs to
> know what, who owns which deliverable, and which calls the boss makes vs. delegates. People
> carry that tacitly, in culture and judgment. An AI can't: it acts only on what you give it. So
> the moment AI runs the org autonomously, all of that tacit knowledge has to become **explicit**.
> That is the whole design problem — and this template is how you write it down.

---

## The thesis in one paragraph

An LLM agent produces work aligned to the goal only if the **right information reaches it in the
right amount** (context) and the **division of labor is clear** (roles) — otherwise the output is
a coarse, essence-missing average. Those are organizational problems, and a human company solves
them *tacitly*, through culture, hallway conversation, and a manager's sense of who-needs-to-know
and who-decides-what. The agent-building industry re-invented fragments of this bottom-up —
*context engineering* (information flow), *harness engineering* (the substrate a member perceives
and acts through), *loop engineering* (the operating cadence) — but as tactical parts, never
forcing the questions that decide whether the output is any good: *is the goal actually
propagated? is the division of labor clear? and — for a 24/7 system — which decisions does the
human still make, and which run unattended?* Those are the tacit organizational things, and an AI
can only act on them if they are **articulated**. So the design act is: articulate the goal, the
information flow, the division of labor, and the decision line — explicitly, for the AI. The
empirical backing is direct: multi-agent LLM systems fail mostly at role clarity, information
flow, and verification (the MASFT study) — precisely the tacit things left un-said.

See **[THEORY.md](THEORY.md)** for the full decomposition. This is an **organizing frame and a
template, not a silver bullet** — the honest research map (who has done what, and where the real
white space is) is in [docs/sources.md](docs/sources.md).

> **Read this caveat before believing the framing.** After a deep literature read (structure,
> control, and multi-agent-systems theory) the framing was corrected — see
> **[docs/11-refoundation.md](docs/11-refoundation.md)**. The corrected version *strengthens* the core
> thesis rather than replacing it: the design act is **articulating the organization** (goal,
> information flow, division of labor, and the decision line between what the human decides and what
> runs delegated) in a form an AI can act on. That articulation *renders to* a permissioned dataflow
> graph on an existing harness — the graph is the medium, not the message (Conway's law: the
> communication structure you write down becomes the system's structure). The empirical backing is
> real: multi-agent LLM systems fail mostly at coordination, role clarity, and verification (the MASFT
> study) — i.e. exactly where the organization was left *tacit*. What was over-claimed: the "seven
> organs derived top-down, complete and ordered" (a retrofitted checklist, not a proof), and several
> classical citations were mis-sourced (e.g. Burns & Stalker do **not** license the two-layer split —
> Lawrence & Lorsch do, *with* an integration cost; separation of duties is risk-calibrated in COSO,
> not a universal). docs/11 is the corrected map; the remaining docs are being brought into line.

**Harness-neutral by construction.** Because harness and loop are organs the industry *already
built* (Claude Code, Codex, and their kin are runnable harnesses), this template does not build a
runtime — it **delegates the heavy organs to whatever existing coding-agent harness runs each
department**, and ships only three thin things: the organization's skeleton as declarative data, a
**projection** of each role's neutral profile onto that harness's own instruction-file convention,
and a machine audit of the skeleton. An LLM agent must be able to pick this up and run autonomously
on a harness that already exists — that requirement, and everything the product must do, is the
subject of **[docs/01-requirements.md](docs/01-requirements.md)** (read it before judging the repo:
a design or review is measured against it first).

## Why this framing is not just aesthetics

Decomposing from the organization (not from the parts) changes what you build:

- It tells you **what you are missing.** A harness+loop view has no concept of *span of control*,
  so it never asks "how many agents can one supervisor actually watch before review quality
  collapses?" Organizational theory does.
- It tells you **when to add hierarchy** (Greiner growth stages) — and, more importantly,
  when **not** to (a middle-management layer is the *last* resort, not the first; invest in
  information flow to widen span and stay flat).
- It tells you **what must never self-organize.** The strongest counter-argument to designed
  structure is that *self-organizing agents outperform designed ones*
  ([arXiv 2603.28990](https://arxiv.org/pdf/2603.28990)). That result is about **task-solving
  efficiency** — the *exploration* layer. It says nothing about *control*: separation of duties,
  authorization, anti-gaming, safety. Let exploration self-organize; **design the control skeleton
  only.** (See [docs/03-organic-vs-mechanistic.md](docs/03-organic-vs-mechanistic.md).)

## What's in here

**Start here**

| Path | What it is |
|---|---|
| [docs/01-requirements.md](docs/01-requirements.md) | **The product spec** — actors (client vs operator vs department vs host harness), jobs-to-be-done, success criteria, the two-tier threat model, and the load-bearing requirement (R0): an LLM must run autonomously on an *existing* harness, no bespoke runtime. A design or review is judged against this first. |
| [docs/11-refoundation.md](docs/11-refoundation.md) | **The literature-grounded correction** — what a deep read of organizational/control/MAS theory says the template got right (coordination is the real risk; the maker/checker insight) and wrong (org-as-primary-lens; SoD-as-universal; Burns & Stalker mis-cited; span numbers; the "derivation"). What to keep, drop, and reframe. Where an older doc conflicts, this wins. |

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

**Tools**

| Path | What it is |
|---|---|
| [tools/org_lint.py](tools/org_lint.py) | The audit gate: meant to run as the gate on every founding/reorg commit (run it as a pre-commit check; it cross-validates all five data files — organization, constitution, moves, ledger-schema, sensors) against the theory (Goodhart, span, SoD, control-never-dormant, need-to-know packs). |

## How to use it

**Track A — manual (the v0.1 spirit).** You design and operate the org by hand:

1. Read [THEORY.md](THEORY.md) once — it is short and it is the point.
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

## Status & honesty

v0.4. This is a **framing + template**, distilled from published organizational theory and the
current agent-engineering literature. The parts (principal-agent theory, harness/loop engineering,
runtime substrates like AIOS, automated agent design like ADAS/DGM) already exist; the contribution
here is **the top-down organizational decomposition that places them** — and, per the research in
[docs/sources.md](docs/sources.md), applying *classical* management theory (Mintzberg, Greiner,
span of control, separation of duties) to agent design is where the literature is currently thin.

**Provenance caveat (important).** The classical-theory citations were originally written from the
author model's training memory, not by reading the primary texts — a real weakness for a repo whose
selling point is source honesty. A 2026-07 verification pass has since checked the *load-bearing*
citations against external sources (Greiner, Graicunas/span, Barnard, Burns & Stalker, Ashby, Conway,
Penrose, and arXiv 2603.28990 — all confirmed to exist and, mostly, to say what the repo claims), and
**corrected the memory errors it found** (e.g. "Conway's law" was named by Brooks, not Conway; the span
number is Graicunas's ~4–5 / Urwick's 5, not a single "5–6 to 15–20" law; the cited counter-paper
actually supports a *mixed* stance, mildly strengthening rather than threatening the two-layer law).
Those corrections and the ✓-verified markers are in [docs/sources.md](docs/sources.md). The long tail
of secondary citations remains memory-sourced and should be treated as lower-confidence until checked.
The design is **harness-neutral and delegation-first**: the heavy organs (perception, tools, loop,
scheduling, sandboxing) are the host harness's job; this repo ships the skeleton, the profile
projection, and the lint (docs/01, docs/09). The lint cross-validates all five data files and is the
one part that runs standalone today. **S1 — one organization from this template launching and doing
useful work on an existing harness end-to-end, with nothing bespoke in the loop — has now been
demonstrated once ([docs/10](docs/10-founding-rehearsal.md), artifacts in
[examples/founding-rehearsal/](examples/founding-rehearsal/)): three departments ran as separate
agents, the maker/checker separation held structurally, and the adversarial checker caught a real bug
the maker and gate both missed.** That closes the load-bearing "has it ever run?" question. What
remains: an automated projection layer (which instruction-file conventions to target — done by hand
in the rehearsal), the Tier-B host-environment controls for asset-touching orgs, the multi-cycle
elastic lifecycle at scale, and the client/delivery/company-layer surfaces (docs/01 §7). The fuller
autonomy story is still ahead; the design is no longer unrun.
The value of any org design is proven by whether the organization actually **produces**, not by the
elegance of its chart. Treat this as scaffolding for that, not a substitute for it.

## License

MIT — see [LICENSE](LICENSE).
