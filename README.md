# orgforge-plugin

> **Official documentation:** [English](docs/en/README.md) · [日本語](docs/ja/README.md)
>
> This root document is the long-form design overview. The language-specific sets above define the
> current supported product, assurance vocabulary, and operating model.

## Resilience engineering for agentic software delivery

orgforge is a portable governance plane for coding agents you already use. It helps the development
organization sustain acceptable outcomes under variability, degrade or stop safely, recover with
the right revalidation, and adapt from evidence without losing human control. It does not replace
Claude Code, Codex, CI, or your deployment platform. It turns an existing repository and its
instructions into an explicit operating model: ownership, workflow gates, independent checks,
evidence, and the decisions that remain human-held.

Respond, Monitor, Learn, and Anticipate are an interconnected capability model and evaluation lens,
not four product modules. The implementation is organized around operational state, observations,
evidence, and bounded adaptation. It never reduces resilience to one score: it makes the evidence,
missing observations, confidence, decision owner, and effects of change inspectable while leaving
the judgment of acceptable outcomes and permanent organizational change with humans.

The product has six parts:

1. **Organization compiler** — derive the smallest useful role and ownership map from real code.
2. **Workflow governance** — require work to move through declared SDLC phases and acceptance bars.
3. **Evidence ledger** — preserve decisions, checks, and effects as replayable evidence.
4. **Harness adapters** — project the same neutral organization onto Claude Code and Codex.
5. **Operational insight** — show status, drift, caps, HALT state, and remaining work without a new
   agent runtime.
6. **Organization evolution** — turn observed bottlenecks and failures into reviewable changes to
   roles, contracts, context, and controls without letting agents rewrite the human-held purpose.

The constitution and workflow describe Work-as-Imagined. The ledger, Git, CI, and traces are
Work-as-Recorded; agent and human explanations are Work-as-Reported. OrgForge triangulates those
partial observations to support an explicitly uncertain inference about Work-as-Done—it does not
claim that one ledger fully captures real work.

An explicit objective can also survive a Claude Code/Codex restart through `org-goal`: its state,
next action, blocker observations, completion evidence, and owning host session live in the shared
ledger. Codex's native Goal is synchronized as an adapter projection; Claude Code resumes from
SessionStart and can use a session-scoped `/loop`. Neither path claims execution while its host is
closed.

For an existing repository, adoption is one command: `/orgforge-plugin:org-adopt`. It requires no
daemon, sudo, separate OS user, or signing infrastructure. orgforge addresses ordinary agent
failure—drift, skipped checks, self-approval, lost decisions—not hostile-process containment.
Credentials and irreversible actions stay in the host platform's protected environments.

The shipped configuration favors adoption speed: trusted developer mode runs ordinary development
without permission prompts and disables the Codex sandbox. Use it only in a trusted checkout with
no production credentials. orgforge's hooks and policies still govern the normal workflow, but they
are not a containment boundary.

The longer “AI-native company” model remains useful as a design horizon, but it is not the adoption
prerequisite or the product boundary. The supported core is the governance layer above.

### Where to go

| | |
|---|---|
| **Run it** | [`QUICKSTART.md`](QUICKSTART.md) — adopt an existing repository in one command or found a new organization from a brief. |
| **Look something up** | [`REFERENCE.md`](REFERENCE.md) — every env var, command, subcommand, ledger event, cap, and the fixes for problems people actually hit. |
| **See the whole system** | [`ARCHITECTURE.md`](ARCHITECTURE.md) — the ecosystem (neutral core → projection → harness), the organs, and the two coupled lifecycles. |
| **Understand why** | [`docs/README.md`](docs/README.md) — the reasoning in four Parts / twelve chapters. [`THEORY.md`](THEORY.md) §0–§1b is the intellectual core. |
| **See what changed** | [`CHANGELOG.md`](CHANGELOG.md) — including the checks that were **removed** and why. |

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
  *control*: separation of duties, authorization, anti-gaming, safety. Let exploration
  self-organize; **design the control skeleton only.**
  (See [docs/03-organic-vs-mechanistic.md](docs/03-organic-vs-mechanistic.md).)

## What's in here

The split is simple: the **neutral core** this repo ships is the declarative skeleton + the
projection + the machine audit (the lint and the organ tools). Everything the docs call "heavy" — the
loop, the scheduler, perception, sandboxing, CI/CD — is **delegated to the host harness** (R0). The
docs are the articulation; the tools are its machine-checkable proof; the templates are what you fill
in for your own org.

| | |
|---|---|
| **`docs/`** | The reasoning in four Parts / twelve chapters — Foundations (what it must be, what theory warns will break it), Design (the control skeleton, context economy, delegate the runtime), Operate (lifecycle, doctrine, attention, loop reliability, **the forced SDLC mold**), North star. Map: [docs/README.md](docs/README.md). |
| **[`template/`](template/)** | What you fill in: the org chart as data ([`organization.yaml`](template/organization.yaml)), the human-only charter ([`constitution.yaml`](template/constitution.yaml)), the legal-move catalog ([`moves.yaml`](template/moves.yaml)), the [ledger schema](template/ledger-schema.yaml), the [sensors](template/sensors.yaml), the [schedule](template/schedule.yaml), the [requirement](template/REQUIREMENTS.md) and [SPEC](template/SPEC.md) skeletons, per-role [job descriptions](template/ROLE.md) and the [founding process](template/FOUNDER.md), and the **[projection](template/PROJECTION.md)** onto each harness's instruction file. |
| **`tools/`** | The machine audit and the organs as running code: `org_lint` (cross-validates all five data files), `ledger` (append-only, hash-chained, `requires_prior` enforced at write time), `org_cycle` (one command per cycle of plumbing), `github_sync` (the backlog↔Issue projection), `req_lint` / `repro_lint` (the requirement and reproducibility gates), plus doctrine, sensors, guardrails, attention, reconcile, alignment, and `tick` (the schedule **planner** — it detects a check that was due and did not run; the host cron drives). Every command is listed in [REFERENCE.md](REFERENCE.md). |
| **`integrations/`** | The one harness-specific layer. Ships as a Claude Code **plugin** — a `PreToolUse` hook that makes a cap or a mandate check *actually block a real tool call*, a `SessionStart` hook that injects the role's doctrine, per-department subagents, and the organ commands. Plus a Codex `.codex/` config. See [integrations/README.md](integrations/README.md). |
| **`demos/` `examples/`** | [S1, demonstrated](demos/S1-founding-rehearsal.md): a real RFP run end-to-end on a real harness — maker, gate, and skeptic as three separate agents, no bespoke runtime — where the adversarial checker caught a genuine bug the maker and gate both missed. |

## How to use it

### Requirements

- **Python 3.12+** with **PyYAML** — the organs read `constitution.yaml` / `organization.yaml`,
  and the enforcement they perform is declared there. Install it into the interpreter the plugin
  actually runs (`python3` on PATH), not a virtualenv you activate by hand:

  ```
  python3 -m pip install pyyaml
  ```

  Without it, the org's own lint (`org_lint.py`) exits on an unhandled `ModuleNotFoundError`, and
  `judges.lineage` cannot be read — a cross-harness declaration would otherwise be silently lost.
- **git**, and **`gh`** authenticated against the repository if you use the GitHub backlog.
- Optional: the **`codex`** or **`claude`** CLI, only if `enforcement.judges.lineage` is set to
  `cross-harness` so judges run on a second model lineage.

### Install

```
/plugin marketplace add <owner>/orgforge-plugin
/plugin install orgforge-plugin@orgforge-plugin
/reload-plugins
```

Choose the **user** scope so the org is available in every project. Reference the plugin by its
GitHub repository rather than a local path: a local path runs whatever is uncommitted on that one
machine, whereas a GitHub reference records the exact commit in `installed_plugins.json`.
Restart the host session after an update so `SessionStart` rebinds to the new organs.

For the Codex projection, and for local-path development installs, see
[`QUICKSTART.md`](QUICKSTART.md) §1.

### Adopt or found

For an existing repository:

```
/orgforge-plugin:org-adopt
```

The command reads the code that exists, prepares local governance state, writes the minimal
organization and architecture, records current debt, and verifies readiness. It does not create a
branch or Issue, access the network, install a daemon, or require sudo.

For a new organization, the founding path remains three commands:

```
/orgforge-plugin:org-init <name> ja     # 1. set up the org's state, labels, baseline
/orgforge-plugin:org-found <brief>      # 2. design → stops for your approval
/orgforge-plugin:org-decompose          # 3. carve it into atomic SPEC task Issues
```

Then `/orgforge-plugin:org-start` brings it to its running state, `/orgforge-plugin:org` is the
status board (GREEN / AMBER / RED), and `/orgforge-plugin:org-triage` feeds a signal into the
backlog. GitHub Issue decomposition is optional for adopted repositories.

The org's own metabolism — `org-work` (the PM loop), `org-discover`, `org-tick` — runs on cadence;
you rarely type it. **Plumbing is run by tools, judgment is not.** One command drives one cycle of a
task Issue (claim → worktree → phase events → log → stage), another assembles the material a gate or
a skeptic needs to judge, another opens the PR and fans it back into `develop`. What to build, whom
to delegate to, and whether to admit stay with the roles — `docs/03` §6.5: *forced delegation is a
design error; a forced invariant is correct*.

The whole cycle, command by command, is in [`QUICKSTART.md`](QUICKSTART.md) §8.

## What "non-skippable" means — the trust boundary

The enforcement claims in this README hold **against agents running under an enabled `PreToolUse`
hook**. They do not hold against the host owner, who can disable the hook. That is not a bug to be
fixed; it is the boundary, and it should be stated rather than implied.

What is inside the trusted base:

| | |
|---|---|
| **Trusted** | The host harness, the hook configuration, the local filesystem, and whoever can write to them |
| **Constrained** | Agents whose tool calls pass through the hook — subagents included, if the harness gates them (verify with `/org-verify-guards`) |
| **Not a boundary** | The ledger's `actor` field. `ledger.py append --actor` takes the actor from its argument, so one process can sign as both maker and gate, pass `DISTINCT_ACTOR`, and leave the hash chain intact. Separation of duties is therefore **evidence that review happened, not proof of who did it** |

The hash chain makes tampering *detectable*, not impossible. `judges.lineage: cross-harness`
likewise buys an independent reviewer, not an authenticated one — a second model lineage with its
own blind spots, recorded as such. The default `adaptive` mode detects whether it is running under
Claude Code or Codex. It uses the other product when available; with one subscription it falls back
to explicitly labelled pseudo same-harness role separation and never claims cross-harness diversity.

### Supported assurance

orgforge addresses **drift and honest operational error**, not a zero-trust contest between
processes owned by the same user. This is deliberate:

| Axis | Default claim | What it means |
|---|---|---|
| Judgment identity | `attested` | A receipt was verified and bound to the judgment. A local key does **not** prove that a hostile same-UID process could not use it. |
| Reviewer diversity | `adaptive` | Uses `cross-harness` when the other product is available; otherwise reports lower-assurance pseudo `same-harness`. Neither is a cryptographic security principal. |
| Writer mediation | `process_mediated` | Enabled hooks and the ledger path enforce the normal workflow inside the host harness's trust boundary. |
| Record integrity | tamper-evident | The hash chain detects rewriting; it does not make a caller-writable file immutable. |

Hostile-process containment and asset protection are **not orgforge guarantees**. Deployments that
touch production, funds, external publication, credentials, or regulated assets must rely on their
host platform for sandboxing, permissions, approvals, and credential custody. A separate writer UID,
KMS/HSM, or mTLS judge service may be useful host infrastructure, but none is a supported mode,
release prerequisite, or claim made by this plugin.

An independent audit of 0.32.0 (resilience engineering / STPA / adversarial review / SRE lenses)
found several places where multiple defence layers rest on the same local process and the same
self-declared actor. Those are recorded in CHANGELOG 0.32.1 under "Known limitations recorded, not
fixed" rather than being written out of the README. **Treat this as research and supervised
operation, not as unattended production control.**

### Delegation Resilience adapter

The [Delegation Resilience adapter](docs/en/delegation-resilience-adapter.md) exports OrgForge
exercise evidence to the formally pinned DR v0alpha1 Assurance Graph and v0alpha2 packet profiles.
The graph is a deterministic, source-bound derived artifact: `GRAPH_VERIFIED` means only that the
graph is internally valid and reproducible. Recovery capability, human takeover, and deployment
approval remain `not_demonstrated` unless independently established by DR evidence.

## Status & honesty

v2.0.0. This is a **framing + template**, distilled from published organizational theory and the
current agent-engineering literature. The parts (principal-agent theory, harness/loop engineering,
runtime substrates like AIOS, automated agent design like ADAS/DGM) already exist; the contribution
here is **the top-down organizational decomposition that places them** — and, per the research in
[docs/sources.md](docs/sources.md), applying *classical* management theory (Mintzberg, Greiner,
span of control, separation of duties) to agent design is where the literature is currently thin.

**S1 — one org from this template doing useful work on an existing harness, nothing bespoke in the
loop — has been demonstrated** ([demos/](demos/S1-founding-rehearsal.md)). That answers the
load-bearing "has it ever run?" question.

**S2 — continuous operation — is what 0.12 through 0.25 was.** One PWA, decomposed from an RFP into
18 task Issues, run through maker / gate / skeptic. What surfaced was not missing features but a
class of defect worth naming: **controls that looked enforced and were not.** A self-admission
refusal that a payload-key mismatch walked straight past. A deploy gate voided by `null == null`. A
detector reporting "accumulated learning is being used" about an org that had re-made the same
mistake three times. A tool asserting a `baseline` it had never read, which stopped a gate from
judging. Each was reproduced against real data and closed with a test ([CHANGELOG](CHANGELOG.md)).

The controls also worked. A gate rejected three rounds running and caught a real bug that sat behind
a fully green suite (a fair-looking split whose remainder always landed on the same person), plus the
test hole that hid it. On another Issue the skeptic named a structural omission: *"the gate spent five
rounds proving no non-member can get in, and never once asked what a member can do to another
member."* With human diff review retired, the mechanical layer and the adversarial reviewer are what
stopped defective work.

**Two checks were added and then removed.** One judged whether a rework had drifted out of scope by
vocabulary overlap and mis-fired; one checked a requirement's verb-object dependency and never fired
at all, because Japanese requirements don't carry the identifiers it looked for. **A check that only
false-positives is worse than no check** — a false alarm disables the true ones — so both were pulled
and the reason recorded. The history of this tooling is meant to show what came out as plainly as
what went in.

What remains: an automated projection layer (which instruction-file conventions to target — done by
hand in the rehearsal), deployment guidance for asset-touching orgs, the multi-cycle elastic
lifecycle at scale, and the client/delivery/company-layer surfaces (docs/01 §7).

**Human diff review is retired** (docs/11 §4f), on the argument that at fan-out volume a reviewer who
cannot keep up skims, and a skimmed diff enters the record as reviewed. What replaces it is
mechanical: an unread-safe bar (complexity ceilings, closed type escapes, duplication and dead-code
scanning, multi-OS CI), a gate and an adversarial skeptic whose independence is enforced at *write*
time (the ledger refuses an admission from the actor that did the work), and a mandatory record —
every judgment carries its reasoning, its evidence, and any knowingly-accepted risk onto the task
Issue. Two limits stated plainly rather than glossed: the reasoning digest makes an edited account
**detectable but not impossible**, and the periodic re-hash sweep that would make that continuous is
not yet an organ. And docs/11 §4f.3 argues against comprehension debt (Osmani) rather than ignoring
it — the substitution is argued, not proven, and the honest test is whether the domain model keeps
growing (§4d) once an org runs for months.

The value of any org design is proven by whether the organization actually **produces**, not by the
elegance of its chart. Treat this as scaffolding for that, not a substitute for it.

## License

MIT — see [LICENSE](LICENSE).
