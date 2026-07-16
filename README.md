# org-first-agents

**Design multi-agent AI systems the way you design an organization — top-down from
organizational theory — instead of assembling bottom-up from separately-invented parts.**

> Harness engineering and loop engineering are not co-equal disciplines to "combine."
> They are two of the **organs you get when you decompose an organization from first
> principles.** This repository does that decomposition, and ships it as a reusable template.

---

## The thesis in one paragraph

The agent-building industry invented its vocabulary **bottom-up**: prompt engineering, then
*context engineering* (what the model sees), then *harness engineering* (the scaffolding around
the model), then *loop engineering* (the control loop that reruns it). Each was named as a
tactical pattern (2024–2026). But a multi-agent system **is an organization** — members with
roles, a division of labor, supervision, incentives, and a growth path. Organizations have been
studied for a century. If you start from the question *"what must any organization have to exist
and function?"* and decompose, the harness and the loop **fall out as necessary organs** — and
so do several organs a harness/loop-only view **misses**: structure (span of control, hierarchy),
incentives/control (separation of duties, anti-gaming), information flow (Conway's law), and
growth (Greiner's stages). Organization is the **first principle**; harness and loop are
**small, composable wheels** that hang off it.

See **[THEORY.md](THEORY.md)** for the full decomposition. This is an **organizing frame and a
template, not a silver bullet** — the honest research map (who has done what, and where the real
white space is) is in [docs/sources.md](docs/sources.md).

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

**Core theory**

| Path | What it is |
|---|---|
| [THEORY.md](THEORY.md) | The core: organization → seven organs (harness & loop are two of them). |
| [docs/05-elastic-organization.md](docs/05-elastic-organization.md) | Why "no salary cost" changes everything (and what it doesn't): design the ideal org fully on day one, run it elastically. |
| [docs/06-lifecycle-operations.md](docs/06-lifecycle-operations.md) | Cradle to grave: founding from an RFP, 24-hour autonomous operation (an approval queue with a delegation-of-authority (決裁権限) matrix — inspired by the written-proposal aspect of 稟議 (*ringi*), not its consensus formation — plus night safe mode), maintenance, handover, sunset. |
| [docs/07-doctrine-and-knowledge.md](docs/07-doctrine-and-knowledge.md) | The knowledge organ: market-watching boundary spanners feed a role-scoped knowledge base; each role's doctrine (べき論 — its current normative playbook) is updated through Maker/Checker and always loaded as context. |
| [docs/08-context-economy.md](docs/08-context-economy.md) | Need-to-know information flow: scoped context packs, contract-interface collaboration, context budgets, and commander's-intent policy propagation. |

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

**Tools**

| Path | What it is |
|---|---|
| [tools/org_lint.py](tools/org_lint.py) | The audit gate: meant to run as the gate on every founding/reorg commit (run it as a pre-commit check; it validates organization.yaml, constitution.yaml, and moves.yaml) against the theory (Goodhart, span, SoD, control-never-dormant). |

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

**Track B — autonomous founding (v0.3).** The org designs and runs itself inside human-written law:

1. Humans author [template/constitution.yaml](template/constitution.yaml) from the template — the
   charter no agent may write.
2. Hand an RFP to the founder process ([template/FOUNDER.md](template/FOUNDER.md)); it produces the
   full latent org plus its output contracts.
3. The founding commit must pass [tools/org_lint.py](tools/org_lint.py) **and** human charter
   approval.
4. The org runs 24 hours a day within the constitution ([docs/06-lifecycle-operations.md](docs/06-lifecycle-operations.md)),
   reorganizing itself only through moves declared in [template/moves.yaml](template/moves.yaml).
5. Doctrine and context scopes evolve per [docs/07-doctrine-and-knowledge.md](docs/07-doctrine-and-knowledge.md)
   and [docs/08-context-economy.md](docs/08-context-economy.md).

## Status & honesty

v0.3. This is a **framing + template**, distilled from published organizational theory and the
current agent-engineering literature. The parts (principal-agent theory, harness/loop engineering,
runtime substrates like AIOS, automated agent design like ADAS/DGM) already exist; the contribution
here is **the top-down organizational decomposition that places them** — and, per the research in
[docs/sources.md](docs/sources.md), applying *classical* management theory (Mintzberg, Greiner,
span of control, separation of duties) to agent design is where the literature is currently thin.
Docs 05–08 and the constitution/moves/lint layer are the newest and least-tested material in the
repo — treat them accordingly. The lint enforces state invariants (SoD, span,
control-never-dormant, schema); transition/tier enforcement and the ledger/sensor runtime are
specified but not yet implemented.
The value of any org design is proven by whether the organization actually **produces**, not by the
elegance of its chart. Treat this as scaffolding for that, not a substitute for it.

## License

MIT — see [LICENSE](LICENSE).
