# Architecture — the ecosystem and the lifecycle

This document is the whole-system map: what orgforge-plugin **is** (the ecosystem — neutral core,
projection, organs), and what an org built with it **does over time** (the lifecycle — founding →
projection → operation → guardrails → evolution). For the design *reasoning* behind each piece, follow
the `docs/NN` links; this file is the connective tissue that shows how they fit together.

> **Core thesis** (THEORY.md §1b, docs/01 R0b): orgforge stands up an **AI-native IT business
> company** — an org whose purpose is to *decide what to build as a business, build it through a
> disciplined SDLC, ship it, and operate it*. Making that run unattended is an articulation problem:
> *designing the AI organization = articulating, in machine-actionable form, the tacit knowledge a
> human company runs on* — its goal, its division of labor, its information flow, its decision line —
> **plus the shape the work is forced to travel through** (the SDLC mold). A human manager holds that
> knowledge in their head; an AI department can only act on what is written down. So the whole system
> exists to make the org's operating knowledge and its build discipline **explicit, enforced, and
> auditable**, and then to let a general coding agent run on it. Two lifecycles result and are
> **coupled**: the org's own metabolism (Part II) and the product's SDLC (Part III) — the system and
> the org grow together.

---

## Part I — The ecosystem

### 1. The neutral core, projected onto a host harness

The single most important structural fact: **orgforge ships a neutral core and projects it onto a host
harness; it ships no execution engine of its own** (docs/08, the R0 principle). The harness — Claude
Code or Codex — already provides the loop, the tools, the file access, the sub-agent spawning, the
scheduler, and the **CI/CD substrate** (GitHub Actions is the deploy phase's spine — docs/11 §3).
orgforge adds the thin layer that a general coding agent lacks: the articulated org, the **forced SDLC
mold** the work travels through, and the guardrails that hold both.

```
        NEUTRAL CORE (harness-agnostic, the source of truth)
        ├── tools/             14 organ tools — pure functions over the ledger
        ├── template/          the org's YAML/MD skeleton + role profiles
        └── integrations/common/   the two shared hooks (guardrail + doctrine injection)
                     │
                     │  build.sh copies the core into each harness folder
                     ▼
   ┌─────────────────────────────┬─────────────────────────────┐
   │  integrations/claude-code/  │      integrations/codex/     │   ← the PROJECTION layer
   │  plugin: hooks, commands,   │  hooks.json, config.toml,    │     (the ONE place harness-
   │  subagents, bundled core    │  AGENTS.md.tmpl, bundled core│      specific knowledge lives)
   └─────────────────────────────┴─────────────────────────────┘
                     │                             │
                     ▼                             ▼
              Claude Code                        Codex          ← the HOST HARNESS
        (supplies loop, tools, scheduler, sub-agents, file access)
```

**Why this split matters.** Porting the org to a different harness changes only which instruction files
are generated and how the launch/stop/schedule signals are wired — nothing in the skeleton. The same
`org_hook.py` blocks a dangerous tool call on *both* harnesses because they share one PreToolUse
contract (stdin event JSON; block via exit 2 + stderr, or a `permissionDecision: deny` JSON).

**The build model** (`integrations/claude-code/build.sh`): a Claude Code plugin may only reference paths
under `${CLAUDE_PLUGIN_ROOT}`, so `build.sh` **copies** the neutral source (`tools/`, `integrations/
common/`, `template/`) into the plugin's own `tools/ scripts/ template/`. Edit the source of truth, run
`build.sh`, and the bundle is regenerated; `build.sh --check` fails CI if the bundle drifted. This is
why every change in this repo touches a source file and its bundled copy stays in sync.

### 2. The shared record — the ledger is the spine

Everything the org knows about itself lives in one place: `<ORG_LEDGER_ROOT>/ledger.jsonl`, an
append-only, hash-chained log (plus a `HEAD` file holding the chain tip). This is **Organ 5, the
information flow**, made concrete (`tools/ledger.py`). Every organ reads it; the org's entire state —
what work is open, what was decided, what was checked, what the caps have spent — is a **deterministic
projection of this log** (`ledger.py view`). No hidden state, no private per-department queue.

A deliberate discipline governs writes — the **R0 emit/append split**:

- **Organs COMPUTE, they never write.** A tool reads the ledger, decides, and prints a line
  `LEDGER-EVENT {json}` to stdout. It exits `0` (allow / silent breadcrumb) or `10` (escalate).
- **The host WRITES.** Only `ledger.py append` mutates the log (enforcing gapless sequence, a
  hash chain, and `requires_prior` invariants — e.g. a `result_deployed` is rejected unless a prior
  `survives` verdict exists). The guardrail hook closes the loop: after it allows a tool call, it
  appends the events the organ emitted, so aggregate caps actually accumulate.

This is what keeps the organs pure and portable: they are functions over a file, and the *host* owns
the side effects — exactly the R0 boundary.

### 3. The organs — seven functions, fourteen tools

The system is organized as seven **organs** (THEORY.md §133–409). Two of them (the harness and the
loop) are deliberately delegated to the host; the rest are implemented as tools.

| Organ | What it is | Implemented by |
|---|---|---|
| **1 — Purpose / telos** | the goal, guarded against Goodhart | `org_lint` O1; `alignment.py` (telos-drift) |
| **2 — Structure** | division of labor, span, coordination | `org_lint` (span/regime/contracts); `handoff.py` (seam at each cut); `attention.py` (intra-unit) |
| **3 — Harness** | perception, tools, memory | **delegated to host** (R0); `org_hook.py` is the adapter into it |
| **4 — Loop / metabolism** | the operating cadence | **delegated to host** (R0); `tick.py` only *plans* what is due |
| **5 — Information flow** | the coordination record | `ledger.py` (record); `reconcile.py` (lateral seam); `sensors.py` (readings) |
| **6 — Decision line / control** | maker/checker, authorization, custody, mandate precedence | `ledger.py` (custody); `org_lint` (SoD teeth); `reconcile.py mandate`; `guardrails.py` |
| **7 — Growth / adaptation** | reshape without collapse | `resource.py` (rank/reclaim); `doctrine.py remap` (refound); `org_lint` (move guards) |

The fourteen tools in `tools/`:

| Tool | Purpose | Key subcommands |
|---|---|---|
| `ledger.py` | append-only hash-chained record + deterministic views | `append` `verify` `view` `census` `digest` |
| `org_lint.py` | static validator of the articulated org (the YAML) | *(positional YAML args)* — teeth `SC O1 O2 O2b/c O2d/e O5 O6 O6b/c O7 O8 CH MV LS CP CA SN RS` |
| `attention.py` | a department's internal work selection from its backlog | `select` |
| `guardrails.py` | 24/7 safety checks (blast-radius, state, stale-ref, consent) | `cap` `reconcile` `staleref` `consent` |
| `tick.py` | schedule *planner*: which checks are due / missed | `plan` |
| `sensors.py` | compute the machine sensors that fire reorg moves | `eval` |
| `reconcile.py` | lateral peer reconciliation + mandate adjudication | `collision` `stall` `contract` `mandate` |
| `resource.py` | priority ranking, resource reclaim, authority review | `rank` `reclaim` `authority` |
| `alignment.py` | proxy-stack guards (premise / sunk-cost / frame-review) | `premise` `sunk` `frame` |
| `learning.py` | org learns from its own outcomes (predicted vs realized) | `delta` |
| `doctrine.py` | per-role external-knowledge store, gated + TTL'd, injected | `propose` `admit` `render` `remap` |
| `conventions.py` | internal reusable precedent ("how we do X here") | `adopt` `conflict` `render` |
| `handoff.py` | build a delegation packet: slice + seam contract + scoped doctrine | *(single command)* |
| `repro_lint.py` | the **Level-2 reproducibility gate** — deterministic check that a repo the org *builds* clones-and-runs the same for anyone (docs/11 §4a) | `check <repo> [--phase]` |
| `_organ.py` | shared substrate: ledger reader, event emitter, exit-code contract | *(library)* |

`repro_lint.py` is the enforcement half of **reproducibility as a first-class property** (docs/11 §0,
docs/01 J14/S9): it runs at the SDLC implement/test/deploy gates and holds a repo that a stranger
couldn't reproduce (missing lockfile, unpinned toolchain, no one-command setup+test, no green
CI-from-clean). The org's own reproducibility (Level 1 — same spec ⇒ same process/gates) is enforced
by the forced phase-gate and `org_lint`; this tool enforces the repos it *produces* (Level 2).

### 4. Enforcement vs advisory — where the teeth are

A crucial distinction for understanding what the system actually *forces* vs what it merely *surfaces*.

**Enforcement — can block a commit or a live tool call:**
- **`org_lint.py`** — the founding/reorg gate. Any violation → exit 1 → the chart is not founded and a
  reorg diff is not admitted.
- **`org_hook.py`** (the PreToolUse hook) — the only thing that reaches into the *live* tool loop. It
  turns an organ's exit-10 verdict into a harness BLOCK (exit 2 / deny). **Fail-safe**: an unevaluable
  guardrail blocks (unless `ORG_HOOK_FAIL_OPEN=1`).
- **`ledger.py append`** — write-time invariants (rejects an out-of-order or prior-less event).

**Advisory — surface and escalate, but cannot themselves block:**
`tick.py`, `sensors.py`, `attention.py`, `reconcile.py`, `alignment.py`, `learning.py`, `resource.py`.
Their exit `0` is a silent breadcrumb (fail-quiet is the *normal* state); their exit `10` pages a human.
They inform decisions; they do not enforce them. (An advisory organ becomes enforcement only when its
verdict is routed through `org_hook` — today only the blast-radius cap is so wired.)

---

## Part II — The lifecycle

orgforge runs **two coupled lifecycles**, and it is worth naming them separately before either:

- **The org metabolism** (this Part II) — how the *organization itself* comes to be and reshapes over
  time: founding → projection → operation → guardrails → evolution.
- **The product SDLC** (Part III below) — the *forced phase mold every deliverable travels through*:
  requirements → design → implement → test → integrate → deploy → operate, ships via CI/CD, operating under a
  reliability budget.

They are **coupled — the system and the org grow together**: a product moving through the SDLC (a
maturing test/deploy pipeline, a rising DORA bottleneck) is exactly what fires the metabolism's
evolution (a sensor → a reorg move), and an evolved org (a new department, refreshed doctrine) is what
lets the next deliverable clear its phases. Neither lifecycle is primary; they drive each other.

### The org metabolism, in five phases

An org built with orgforge moves through five phases. Founding happens once; projection happens at every
launch; operation, guardrails, and evolution run continuously.

```
  FOUNDING ──▶ PROJECTION ──▶ OPERATION ◀──▶ GUARDRAILS
  (define &     (neutral       (the running       (block/escalate,
   validate     profile →      metabolism)         every cycle)
   the chart)   department)          │
                                     ▼
                                 EVOLUTION
                        (the org reshapes itself)
```

### Phase 1 — Founding: define and validate the org

An org **is** a set of neutral source files (all templated in `template/`):

| File | What it declares | Who may edit |
|---|---|---|
| `organization.yaml` | the chart: purpose, latent layers, roles + contracts, SoD map, info-flow scopes | founding / charter tier |
| `constitution.yaml` | the charter: decision line, invariants, change tiers, `mandate_precedence` | **no agent — human only** |
| `moves.yaml` | the catalog of legal structural changes, each tiered | charter tier to extend |
| `ledger-schema.yaml` | the ledger's event vocabulary + derived views (incl. the `open_experiments` backlog) | — |
| `sensors.yaml` | the machine/LLM sensors that trigger reorg moves | registrar (delegated) |
| `role-settings.yaml` | neutral runtime knobs per role (model tier, tools, budget, stop) | projection input |
| `ROLE.md` / `SUPERVISOR.md` / `FOUNDER.md` / `PROJECTION.md` | neutral role, supervisor, founder profiles + the projection contract | source of truth |

**Two ways in** (see QUICKSTART for the commands):
1. **Hand-fill** — copy `template/organization.SKELETON.yaml`, fill the `<ANGLE_BRACKET>` domain-role
   slots. The control skeleton (supervisor / gate / skeptic / registrar) is kept intact; you supply the
   purpose, the domain roles, and their contracts.
2. **`/org-found <your RFP or brief>`** — the org drafts itself: a feature inventory (must/should/nice +
   an explicit exclude list), an architecture with seam contracts (inverse-Conway, per `FOUNDER.md`), a
   concrete linted `organization.yaml` — then **stops and reports up** for your scope approval. Founding
   is design; building the product is the CEO's next call.

**Validation is a hard gate** — `tools/org_lint.py` over the five required files. It checks structural
coherence: span budgets (O2), the organic/mechanistic regime boundary (O2b), separation of duties (O6,
including that an independent adversarial checker sits on the deploy path), the anti-puppet-checker
lineage rule (O6c), and — the newest tooth — **O8 no-doctrine-capture**: no control role may carry
`implement` together with `judge`/`review`, so domain knowledge accrues to the field role that owns it,
not to the boss. A chart that does not lint is not founded.

### Phase 2 — Projection: a neutral profile becomes a running department

A department is a host harness running in a working directory, reading that role's **projected profile**
(`template/PROJECTION.md`). The neutral `ROLE.md` instance is the source of truth; the per-harness file
(`CLAUDE.md` for Claude Code, `AGENTS.md` for Codex) is a regenerated view, assembled in order:

1. the **intent block** (broadcast org purpose) → 2. **this role's job** (ROLE.md: mission, duties, the
decomposition doctrine of docs/03) → 3. **this role's doctrine** (its gate-admitted normative playbook)
→ 4. the **decision line** reduced to this role → 5. the **discipline preamble** (charter-protected,
verbatim) → 6. the **granted context-pack views** written as files in the working dir (need-to-know,
deny-by-default — docs/07).

Two mechanisms make projection live:
- **SessionStart doctrine injection** (`integrations/common/org_session_start.py`): a SessionStart hook
  renders the role's `DOCTRINE.md` + `CONVENTIONS.md` and returns them as context *before* the role
  acts — every cycle, not last quarter's world.
- **The runner** (`integrations/runner/run_department.py`): launches one role headless
  (`claude -p …` / `codex exec …`) with the projected profile and the role's allowed tools. It ships no
  scheduler — the host fires it.

### Phase 3 — Operation: the metabolism

The running loop is one backlog per department, driven by a PM loop, fed by a discovery loop, watched by
a health tick — all realized on the harness's own scheduler.

**The backlog is one queue** — the `open_experiments` ledger view. Items enter by two paths and are
**not** kept in separate queues:
- `source: mandate` — a top-down instruction handed down.
- `source: self` — a task the department raised from its own aspiration gap (problemistic search).

**The three commands of the metabolism:**

| Command | Role | Mechanism |
|---|---|---|
| **`/org-work <role>`** | the **PM loop** (acts) | `attention.py select` prioritizes the whole backlog on one footing (situated attention to the org ranking + problemistic-search boost), **floors an in-zone mandate** (zone of acceptance — a live instruction is never starved by low-priority self work), picks a prefix within the WIP limit → delegates the selected items **in parallel** (one `Task` each, only where the split is genuine per docs/03) → records `cycle_completed`. |
| **`/org-discover <role>`** | the **discovery loop** (adds only) | surfaces aspiration gaps and raises them as `source: self` backlog items, scoped to the role's own domain, deduped, append-only. Fail-quiet when there is no gap. |
| **`/org-tick`** | the **health tick** (read-only) | which checks are due / MISSED, machine sensors, ledger-chain integrity. Surfaces, never acts. |

**Prioritization is grounded, not ad-hoc** (docs/09): the score is the Carnegie-School synthesis —
situated attention (Ocasio: align to the org ranking), problemistic search (Cyert & March: boost what is
failing its aspiration), sequential attention within a WIP limit (March & Simon; Goldratt/Kanban), and
the mandate floor (Simon's zone of acceptance). `attention.py` **escalates** only when the backlog
cannot serve the org's top objective (a coverage gap) or WIP is saturated by stalled work.

**Decomposition is a judgment, not a mandate** (docs/03, injected into every ROLE profile): subdivide
only genuinely independent work; **never split reciprocally-coupled work**; cut seams at the design
secret; each child carries a seam contract (its slice, inputs, outputs, `owns`/`must-not-touch`); route
another role's domain to *that* role (own-domain coupled work you may implement yourself). Parallelism
follows independence, bounded by coordination cost — no target depth.

**Scheduling** (`integrations/claude-code/SCHEDULER.md`): `template/schedule.yaml` is data; the host
realizes its cadences on Claude Code's own scheduler — `/schedule` (cron routines) for the unattended
24/7 cadence, `/loop` for attended runs. This is R0-conformant: docs/08 names "the harness's own loop"
as a valid realization, so no R0 change is needed and the wiring stays in the integration layer.
`tick.py`'s missed-check detector survives the wiring as the org's own heartbeat — a scheduler can be
down, and silence must never read as success.

### Phase 4 — Guardrails: the teeth, every cycle

Two enforcement surfaces run alongside operation.

**The PreToolUse hook** (`integrations/common/org_hook.py`) — one neutral adapter, wired for both
harnesses, reading each tool call **and the ledger**:
1. **Blast-radius cap** — meters *irreversibility, not activity*. New-file creates and read-only shell
   are never metered (a 300-file build proceeds); overwriting existing files has a high cap; destructive
   / external-write / infra-change ops have low caps, scope-weighted so one `rm -rf` / `DROP` /
   `reset --hard` can trip alone. The hook appends the emitted event so the cap accumulates.
2. **Seam-contract-on-spawn** (**on by default**; opt out with `ORG_REQUIRE_SEAM=0`) — an `Agent`/`Task`
   spawn is blocked unless the prompt carries a seam contract or an explicit `INDEPENDENT:` declaration
   (turns "please split cleanly" into structure), and a declared `owns:` territory that collides with a
   live sibling's claim in the ledger is refused — concurrent-write drift is prevented at spawn time, not
   detected after the fact (docs/12 §5).
3. **Word-boundary destructive detection** — classifies destructive commands on *whole tokens*, so a
   path like `.../fx-ml-platform/…` or a flag like `grep -f` never misfires as `rm` / `-f`. **Fail-safe**:
   an unevaluable guardrail blocks.

**The lint teeth** (`org_lint.py`) — the structural gate on every founding and reorg commit, described in
Phase 1. Its O8 tooth is the enforcement half of the knowledge-aggregation guarantee: a control role
that adjudicates may not also implement a domain.

### Phase 5 — Evolution: the org reshapes itself

The chart is not fixed — it is elastic, and change flows through a controlled path:

```
  sensor fires  ──▶  registrar selects a legal move  ──▶  lint + gate admit  ──▶  chart changes
  (sensors.py)       (from moves.yaml, as a Maker)        (org_lint + gate)       (the reorg lands)
```

1. **A sensor fires** (`sensors.py eval` over `sensors.yaml`): e.g. `supervisor_saturation` →
   widen-span / `add_layer`; `demand_signal` → `activate_department`; `queue_empty` →
   `deactivate_department`; `doctrine_stale` → refresh doctrine. Only `delegated`-tier moves are
   pre-registered to fire unattended overnight.
2. **The registrar selects a legal move** from `moves.yaml` (tiered `delegated` / `charter` /
   `irreversible`) and authors the reorg diff **as a Maker** — it approves nothing, ever.
3. **Lint + gate admit** the diff: it must pass `org_lint.py` and be admitted by the independent gate.
4. **The chart changes** — the elastic operations: `activate_department` / `deactivate_department`
   (reversible activation), `add_layer` (charter tier — a human decides; it mints new authority),
   `refound` (charter tier — with required guards that the lint enforces: the doctrine remap covers every
   live claim, and the new structure passes lint), `sunset` (irreversible — prepared by the org, executed
   by humans). **Mandate conflicts** resolve via `/org-mandate` → `reconcile.py mandate` against the
   human-authored `mandate_precedence` in the constitution: precedence applies, or both integrate, or it
   escalates.

The top of the chart is not agent-mutable: an agent never mints a new top-level department. Changing the
top layer requires the charter/founding ceremony (human authority), not an agent's free judgment.

---

## Part III — The product SDLC (the second, coupled lifecycle)

Part II is how the *org* comes to be and evolves. This Part is what the org *does with every
deliverable*: forces it through a non-skippable software lifecycle, ships it via CI/CD, and operates it
under a reliability budget. This is the enforcement of THEORY §1b — an amplifier without a mold just
produces more of whatever it was already doing wrong (docs/04), so the *shape of the work* is forced,
not suggested. See **docs/11** for the full doc; this is the architectural summary.

### The forced phase mold

Every deliverable travels one non-skippable chain:

```
  requirements ──▶ design ──▶ implement ──▶ test ──▶ deploy ──▶ operate
        │            │           │           │         │          │
        └────────────┴───── each phase: phase_started, then a gate's ─────┘
                            phase_admitted{verdict:pass} BEFORE the next
                            phase_started is a legal ledger event (docs/11 §2)
                                                                     │
                            operate closes the loop back to requirements ◀┘
```

**How the mold is enforced — not by a prompt, by the ledger.** The phase-gate generalizes the same
`requires_prior` idiom that already makes the skeptic load-bearing (Part I §2): `ledger.py append`
*rejects* a `phase_started{implement}` unless a `phase_admitted{design, verdict:pass}` already exists
for that deliverable (`prior(requirements)=∅`). A phase cannot be skipped because the record won't
accept the skip. This is deterministic enforcement, in the same class as the blast-radius cap — not a
checklist the model can talk past. New ledger events: `phase_started` and `phase_admitted` (docs/11 §2).

### CI/CD is the deploy phase's spine (borrowed, not built)

Deploy is a real phase, and its machine form is **CI/CD on the host's substrate** (GitHub Actions) —
R0-consistent: orgforge ships no pipeline runner, it *requires and reads one*. The deploy gate re-runs
setup + tests **from a clean clone** and admits only when a committed workflow is green from that clean
clone (docs/11 §3/§4a). "Green CI from a clean clone" is reproducibility *proven continuously*, and it
is an **admission artifact**, not an aspiration.

### The reproducibility gate

Reproducibility is a first-class property at two levels (docs/11 §0):
- **Level 1 — the org.** Same org spec + RFP ⇒ same process, gates, contracts, verification. Enforced
  by the forced phase-gate above + `org_lint` (including the **O10** tooth: every declared contract
  deliverable is owned and independently checked — the chart side of the RFP-coverage manifest).
- **Level 2 — the repos the org builds.** A stranger who clones gets the same system: committed
  lockfile, pinned toolchain, one-command setup+test, idempotent migrations, `.env.example`, green
  CI-from-clean. Enforced by **`tools/repro_lint.py`**, run *by the gate* at the implement/test/deploy
  phase gates (each artifact tagged with the earliest phase that requires it). Presence is checked
  deterministically; the clean-clone re-run is the expensive second tooth the deploy pipeline performs.

The generated *code* is free to vary (LLM non-determinism, accepted); the mold makes everything around
it — process, contracts, gates, dev experience — reproducible.

### The operate organ: reliability budget + DORA

Once shipped, the deliverable enters `operate`, and the running company navigates by two standing
instruments (docs/05 §reliability-budget / §DORA, docs/11 §4):
- **A reliability / error budget** — `reliability_budget_checked` fires at every deploy gate and on a
  burn-rate cadence; on the transition to `freeze` it surfaces (a frozen deploy pipeline is an
  exception the org must see), and a fast burn escalates as a systemic regression.
- **DORA's four keys** — `dora_snapshot` computes deploy frequency, lead time, change-fail rate, and
  MTTR from the ledger's own events. Their purpose is **navigation**: read together they locate the
  **moving bottleneck**. When the amplifier makes generation cheap, the constraint moves *downstream*
  to review/test/deploy — the exact signal the attention layer (docs/09) and the priority ranking
  (docs/05 §5.4) steer by. This is where the two lifecycles couple: a moved bottleneck is a
  re-prioritization signal the registrar reads, and can be the sensor that fires an org evolution.

---

## Where to go next

- **To run it:** [QUICKSTART.md](QUICKSTART.md) — install, define an org, drive the metabolism.
- **To understand a piece:** the `docs/NN` links above; [docs/sources.md](docs/sources.md) grounds every
  claim in the literature.
- **To wire a harness:** [integrations/README.md](integrations/README.md) and
  [integrations/claude-code/SCHEDULER.md](integrations/claude-code/SCHEDULER.md).
