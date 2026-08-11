# Quickstart — install and run in a few minutes

> **Official standalone versions:** [English](docs/en/quickstart.md) ·
> [日本語](docs/ja/quickstart.md)

The happy path: **found an AI-native IT business company, watch it build and ship a backlog item
through the forced SDLC (requirements → design → implement → test → integrate → deploy → operate), and put it
into continuous operation** — all on a real Claude Code session, with the guardrails actually
enforcing at the tool boundary. It does not require publishing the repo — a private GitHub repo or a
local path both work (see [Distribution](#distribution) at the end).

The company builds through a **non-skippable phase mold** and ships **reproducibly**: same org spec +
RFP ⇒ same process, gates, and contracts, and the repos it produces clone-and-run the same for anyone
(docs/11 §0/§4a). Proving a guardrail blocks is *one step* along the way, not the point — the point is
that the company builds and ships something reproducibly through that mold.

> For the whole-system picture — the ecosystem (neutral core → projection → harness), the organs, and
> the two coupled lifecycles (the org's metabolism and the product's SDLC) — read
> [ARCHITECTURE.md](ARCHITECTURE.md). This quickstart is the hands-on path through it.

> **The extent of the guarantee.** This Quickstart addresses hallucination, sycophancy, insufficient
> checking, skipped phases, and mis-operation. `cross-harness` decorrelates review across model
> families, local signing reaches `attested`, and the writer defaults to `process_mediated`. A
> separate UID, a KMS/HSM, and an external judge are all unnecessary, and separate-UID writer
> isolation is an experiment not adopted into the supported core, so it is not used here.

## 1. Install the plugin

**Install PyYAML first.** The organs read `constitution.yaml` and `organization.yaml` to decide the
enforcement, so without it `org_lint.py` dies with `ModuleNotFoundError` and `judges.lineage`
cannot be read either (the failure where a cross-harness declaration vanishes silently).
Install it into the interpreter the plugin actually uses (the `python3` on PATH):

```
python3 -m pip install pyyaml
python3 -c "import yaml; print(yaml.__version__)"   # confirm
```

```
/plugin marketplace add <owner>/orgforge-plugin      # reference the GitHub repository
/plugin install orgforge-plugin@orgforge-plugin      # choose the user scope (active in every project)
/reload-plugins
```

**Do not use a local directory reference (`marketplace add /path/to/orgforge-plugin`).** It works
only on that machine and **runs your uncommitted changes as they are** — which means running the
org on unverified code. With a GitHub reference, which commit is running is recorded in
`installed_plugins.json`.

The steps after fixing the plugin (a GitHub reference makes a push mandatory):

```
integrations/claude-code/build.sh           # regenerate the bundle from the neutral core
integrations/claude-code/build.sh --check   # confirm they are in sync (the CI gate)
python3 -m pytest tests/ -q                 # the tests
git commit && git push
/plugin marketplace update orgforge-plugin  # pick it up on the session side
/plugin update orgforge-plugin@orgforge-plugin
```

To run headless without installing:

```
echo "your prompt" | claude -p --plugin-dir integrations/claude-code \
  --allowedTools "Bash,Write,Agent"
```

After touching a manifest, validate it with
`claude plugin validate integrations/claude-code --strict`.

## 2. No setup needed — the org is discovered

**No environment variable has to be set.** An org is a place on disk (the `.orgforge/` beside
`organization.yaml`), and the backlog repository is wherever `git remote origin` points. Both are
facts readable from the checkout, so the organs and the guardrail hooks **find them themselves**
（`tools/discover.py`）。

This is not a matter of convenience. An org addressed by an absolute path like
`/Users/someone/proj/.orgforge/ledger` **does not work on another machine**. The point of writing
the whole specification onto the Issue is that it can be picked up in any environment, so breaking
that collapses the whole design. On top of that, **a setup step repeated per machine always gets
skipped** — and when it is skipped, the guardrails cannot find the ledger and **silently permit
everything**. Discovery erases that failure mode.

As a side effect, **one environment can operate the orgs of several repositories at once**. A `cd`
switches which org is addressed, and neither the audit records nor the blast-radius budgets get
crossed.

```
cd ~/product-a && /orgforge-plugin:org        # product-a's org
cd ~/product-b && /orgforge-plugin:org        # product-b's org (independent)
```

### Use an environment variable only where an override is needed

Precedence runs: an explicit argument > an environment variable > discovery. The default path needs
none of them, but they are available for deliberately placing the ledger outside the checkout, or
for pinning it in CI.

| variable | purpose | default |
|---|---|---|
| `ORG_LEDGER_ROOT` | put the ledger somewhere else | discovered (`.orgforge/ledger`) |
| `ORG_GITHUB_REPO` | pin the backlog repository | discovered (`git remote origin`) |
| `ORG_ROLE` | which role this session is (the key for doctrine injection and resume) | (none) |
| `ORG_DOCTRINE_ROOT` / `ORG_CONVENTIONS_ROOT` | put them somewhere else | discovered (`.orgforge/…`) |
| `ORG_HOOK_FAIL_OPEN` | pass when an organ errors — **development only** | off (fail-safe) |

**The blast-radius caps, the iteration limits, and the seam gate are declared in
`constitution.yaml`'s `enforcement:` block** (so the same org takes effect at the same strength
wherever it is installed). Environment variables such as `ORG_CAP_*` are **development overrides**
of that, not the way to configure an org. For details see
[REFERENCE.md](REFERENCE.md)。

## 3. What to do first

Adopting into an existing repository is one command:

```
/orgforge-plugin:org-adopt
```

Preparing local state, reading the code that exists, the minimal organization, the architecture,
the remaining-work manifest, the baseline, and the readiness doctor all complete within the same
workflow. Decomposing into Issues happens later, and only where it is needed.

Founding a new org from a brief is three commands:

```
/orgforge-plugin:org-init Tatekae ja       # 1. set up (it does not design)
/orgforge-plugin:org-found REQUIREMENTS.md # 2. design → stops for the CEO's approval
/orgforge-plugin:org-decompose             # 3. decompose into atomic task Issues
```

> **Qualify a command name with the plugin's name**, e.g. `/orgforge-plugin:org-init`.
> This is the formal form, so names do not collide with another plugin's.

`/orgforge-plugin:org-init` creates the org in **the current directory at run time**. Run it in the
product's repository — step 0 prints the location and stops if it is the plugin's own development
tree.

`org-init` also takes `repro_lint`'s **baseline** once (the starting point that records where the
machine bar currently stands). Without it, a later gate judgment cannot tell "a regression from
this change" from "debt that was already there" — in the field a gate read pre-existing debt as a
new regression and stopped the judgment. In a new repository the failures are near zero, and that
is the correct starting point (every later regression is visible).

## 4. Sanity-check: a guardrail actually fires

Before founding a company you'll trust to fan out, confirm the teeth are live. With `ORG_LEDGER_ROOT`
set and a low cap, a runaway is blocked at the tool boundary — one quick check, not the headline:

```
mkdir -p /tmp/myorg/.orgforge/ledger && cd /tmp/myorg   # the minimum discoverable as an org
export ORG_CAP_DESTRUCTIVE_OPS=2
echo '{"hook_event_name":"PreToolUse","tool_name":"Bash","tool_input":{"command":"rm -rf /tmp/x"}}' \
  | python3 integrations/common/org_hook.py; echo "exit=$?  (2 = blocked)"
```

(For the full certification — including that the block fires for a *spawned subagent's* tool call —
run `/orgforge-plugin:org-verify-guards` once at founding. Caps, the iteration/cycle limits, and the seam gate are
declared in `constitution.yaml`'s `enforcement:` block; the `ORG_CAP_*` env vars above are **dev
overrides** over that spec — see [REFERENCE.md](REFERENCE.md).)

## 5. Run a department (headless)

### Three-minute reviewer-outage exercise

Before enabling an acting scheduler, run the deterministic resilience fixture. It uses a temporary
workspace, local tracker artifact, injected dependency failure, and the real judge-preflight,
adaptive-envelope, and ledger paths; it needs no network, model subscription, credential, or real
repository mutation:

```bash
orgforge resilience-exercise reviewer-outage --expect GREEN
```

From a source checkout, use `python3 tools/resilience_exercise.py reviewer-outage --expect GREEN`.
The fixture proves the production path detects the outage, enters `DEGRADED`, authorizes only the
declared cross-harness failover, enters `RECOVERING` after a successful half-open probe, revalidates
every tainted artifact, and returns to `NORMAL`. Safe stop remains an acceptable outcome rather than
being counted as a failure; an injected fault that does not reach judge preflight is `INVALID`.

The companion false-GREEN exercise proves a distinct critical function: a passing test process
cannot establish a mutation that never took effect. It routes the claim through the production
skeptic-intake boundary and is GREEN only when that boundary rejects the false evidence:

```bash
orgforge resilience-exercise false-green-mutation --expect GREEN
```

The provider-outage exercise verifies the complementary containment path. A required provider
fails at the production preflight boundary; the declared envelope permits only safe responses,
rejects an unverified substitution and merge, deduplicates repeated containment, and requires
human handback rather than a retry claim:

```bash
orgforge resilience-exercise provider-outage --expect GREEN
```

The heartbeat-correlation exercise checks the monitor's real registry and probe paths. Duplicate
or stale heartbeats remain `ATTENTION` even when a single ledger probe is quiet, so no one signal
can manufacture a healthy claim:

```bash
orgforge resilience-exercise heartbeat-correlation --expect GREEN
```

The repeated-failure-learning exercise verifies that recurring death causes escalate through the
production learning organ and produce an actionable doctrine handoff without silently changing
roles or doctrine. Human judgment and a bounded microexperiment remain required.

```bash
orgforge resilience-exercise repeated-failure-learning --expect GREEN
```

A "department" is a Claude Code (or Codex) turn pointed at one role's profile. Use the runner —
it projects the role onto the harness and attaches the plugin so the guardrails apply:

```
python3 integrations/runner/run_department.py --harness claude --role <role> \
  --task "…" --ledger $ORG_LEDGER_ROOT --doctrine $ORG_DOCTRINE_ROOT \
  --tools read,write,run_tests --dry-run     # drop --dry-run to actually run
```

## 6. Start the metabolism — one command brings the org to its running state

Once an org is defined (§7) and `ORG_LEDGER_ROOT` + `ORG_ROLE` are set, **run `/orgforge-plugin:org-start`**:

```
/org-start [role] [tick-min] [work-min] [discover-hours]     # defaults: supervisor 15 60 6
```

It prints three **`/loop`** invocations that drive this session's cycles, so the org runs itself **while
this session is open**:

```
/loop 15m /org-tick               # monitoring: due/MISSED checks, stalls, repeated deaths
/loop 60m /org-work supervisor    # the PM loop: select, delegate, record
/loop 6h  /org-discover supervisor # raise self-tasks from aspiration gaps
```

The drive is delegated to Claude Code's built-in `/loop` (R0 — borrow the harness's loop, don't build
one); the org keeps only the monitoring `/loop` can't give it (the missed-tick detector in `/orgforge-plugin:org-tick`).
You usually won't type `/orgforge-plugin:org-start` yourself — on an org session the SessionStart hook prompts the model
to run it. Check on the org any time with **`/orgforge-plugin:org`**.

**Session-scoped:** these `/loop` cycles run while this Claude Code session is open and stop when it
closes. For a genuinely 24/7 org with no session open, use an OS-level cron —
`integrations/claude-code/scheduler-install.sh` (see [SCHEDULER.md](integrations/claude-code/SCHEDULER.md)) —
a separate, explicit setup.

**Check on it any time with `/orgforge-plugin:org`** — one GREEN/AMBER/RED board: what it did, what's in progress, and
whether it needs you. You don't read the ledger; `/orgforge-plugin:org` tells you in plain language. Feed new work in
with `/org-triage <a bug/issue/idea>` (or drop it on the backlog); the org works it on its own.

### The three cycles it runs

The running loop is three commands operating on the **one backlog per department** — the
`open_experiments` ledger view — which holds both top-down **mandate** items and self-raised **self**
items on one footing.

```
/org-work <role>       # the PM loop: select from the backlog by attention, delegate the selected
                       #   items to subordinates in PARALLEL (one Task each, where the split is
                       #   genuine), then record cycle_completed. This ACTS.
/org-discover <role>   # problemistic search: surface aspiration gaps and raise them as source:self
                       #   backlog items. Adds to the backlog; never executes. Fail-quiet if no gap.
/org-tick              # read-only health: which checks are due / MISSED, sensors, chain integrity.
```

`/orgforge-plugin:org-work` uses `attention.py` to prioritize the whole backlog (situated attention to the org
ranking + problemistic-search boost), **floors an in-zone mandate** so a live instruction is not
starved by low-priority self work, and picks a prefix within the WIP limit. Delegation follows the
decomposition doctrine (docs/03): split only genuinely independent work, never split coupled work,
each child carries a seam contract.

### Session-scoped vs. genuinely 24/7

`/orgforge-plugin:org-start` schedules the cycles **within this session** (Claude Code's `CronCreate` / `/schedule` are
session-only — they stop when the session closes). That is the right default for an attended or
kept-open session. For an org that must run with **no session open**, install the cadence on the OS
cron with `integrations/claude-code/scheduler-install.sh --role <role>` — see
[SCHEDULER.md](integrations/claude-code/SCHEDULER.md) for the difference and the full wiring.

Either way, `tick.py` detects a **missed check** (a due check with no proof-of-run in the ledger), so
"the scheduler stopped firing" becomes a paged fact, not silent drift — the org checks its own
heartbeat regardless of who fires the cadence.

## 7. Define your own org — two ways in

The plugin is the *engine*; your organization is `organization.yaml` + `constitution.yaml` +
`moves.yaml`, validated by `python3 tools/org_lint.py …`. Two starting points ship with it:

- **Write it yourself** — copy `template/organization.SKELETON.yaml` to `organization.yaml` and
  fill the `<ANGLE_BRACKET>` slots. The control skeleton (supervisor / gate / skeptic / registrar)
  is kept intact — you fill purpose, domain roles, and their contracts. Then lint it and iterate.
- **Let the org draft it** — the three-command path below. The org does its own feature inventory,
  architecture with seam contracts, and a linted `organization.yaml`, then **stops and reports up for
  your review** before anything is built (founding is design; the build is the CEO's next call).

```
/org-init      "Tatekae" ja          # 1. set up:     ledger root, spec files, .envrc, labels, develop, guard probe
/org-found     <RFP or path/to/brief> # 2. design:     the four fixed founding artifacts → STOP for your approval
/org-decompose                        # 3. decompose:  the manifest → atomic SPEC task Issues, coverage-gated
```

**Step 2 writes four files under fixed names** ([docs/11](docs/11-sdlc-mold.md) §0a) — `REQUIREMENTS.md`,
`FEATURE-INVENTORY.md`, **`ARCHITECTURE.md` (the whole-system design)**, `coverage-manifest.md`, plus
`organization.yaml`. The names are fixed because step 3 reads them *by name*; a renamed artifact is one
no command can find. `/orgforge-plugin:org-found` is *design only* — you approve the scope. It is the moment the abstract
"org" becomes a **company**: a purpose stated as a business, a feature inventory with an explicit exclude
list, and contracts the lint's O10 tooth checks for coverage (every deliverable is owned and
independently checked — [docs/11](docs/11-sdlc-mold.md) §0, [docs/01](docs/01-requirements.md) J14/S9).

**Step 3 is what makes the design workable from anywhere.** `/orgforge-plugin:org-decompose` carves each must-have into
*atomic, independently-completable* task Issues (split wherever sibling `owns` sets are disjoint; keep
reciprocally-coupled work together), fills the full `template/SPEC.md` structure into each Issue body —
clone URL, the literal setup+test commands, entry files, MUSTs in EARS, the seam contract, the DoD
command — and hangs each one under its objective as a native GitHub sub-issue. Because the whole spec
lives *in the Issue*, any environment can claim one and start: a web session, another machine, a fresh
agent with none of your context. It ends on a **coverage gate** (`github_sync coverage-check`) that exits
non-zero if any must-have never became an Issue — the design-to-backlog gap that is otherwise invisible.

## 8. The company builds and ships — through the forced SDLC

This is the headline. Once you approve the scope and the metabolism is running (§6), the PM loop
(`/orgforge-plugin:org-work`) pulls a backlog item and the company builds it — but it cannot skip a step. Every
deliverable travels a **non-skippable phase chain**, enforced not by a prompt but by the ledger's
phase-gate (the same `requires_prior` idiom that makes the skeptic load-bearing):

```
requirements ─▶ design ─▶ implement ─▶ test ─▶ deploy ─▶ operate
     └── each phase emits phase_started; a gate emits phase_admitted{verdict:pass}
         BEFORE the next phase_started is legal (docs/11 §2)
```

What that buys you, concretely:

- **A phase cannot be skipped.** `phase_started{implement}` is *invalid* in the ledger unless a
  `phase_admitted{design, pass}` exists for that deliverable. The mold is data, enforced at write
  time — not a checklist the model can talk its way past ([docs/11](docs/11-sdlc-mold.md) §2).
- **Deploy is a real phase, and CI/CD is its spine.** The deploy gate re-runs setup + tests from a
  **clean clone** and reads a committed GitHub Actions workflow that must be green — shipping is
  continuous, not a one-time local "it worked on my machine" ([docs/11](docs/11-sdlc-mold.md) §3/§4a).
- **Reproducibility is checked, not asserted.** At the implement/test/deploy gates the gate runs
  `tools/repro_lint.py` over the repo the company built — committed lockfile, pinned toolchain,
  one-command setup+test, idempotent migrations, `.env.example`, green CI-from-clean. A repo that a
  stranger can't clone-and-run the same way is **held**, not admitted:

  ```
  python3 tools/repro_lint.py check <repo_dir> --phase deploy   # exit 0 = present · 10 = gate HOLDs
  ```

- **The company then operates.** In the `operate` phase it runs under a **reliability / error
  budget** (a `reliability_budget_checked` event freezes deploys when the budget is burned) and
  navigates by **DORA** metrics (a `dora_snapshot` names the *moving bottleneck* — when generation
  gets cheap the constraint moves downstream to review/test/deploy, and the attention layer steers
  there). See [docs/05](docs/05-lifecycle-operations.md) §reliability-budget / §DORA and
  [docs/11](docs/11-sdlc-mold.md) §4.

### Running one Issue — the commands actually typed

This sequence is what the PM loop (`/org-work`) consists of. **The tool runs the plumbing; the role
makes the judgment.**

```
org_cycle.py begin     --role R --issue N [--agent A]
  # claim → worktree(.orgforge/wt/issue-N/) → spec_delegated → phase_started → cycle_started
  #   → log to the Issue → stage. parent and candidate_id resolve from the Issue automatically
  # it also prints the pre-start checks (is a dependency in rework, is anything waiting on a
  #   human). It does not stop you

  … the maker builds inside the worktree …

org_cycle.py complete  --role R --issue N --outputs T --command CMD --result OUT
                       (--domain-model-updated REF | --domain-model-none WHY) [--learned "a learning"]
  # where new public surface has appeared (a SECURITY DEFINER function, a grant, an endpoint),
  #   it stops until it is declared — an authorization hole is born where one function was added
  # --learned is proposed to doctrine (the admit is the gate's job)

org_cycle.py handback  --issue N --summary S --result OUT      # push → PR（Closes #N）→ log
org_cycle.py verify    --issue N --role gate                   # assemble the material for judging
  # stdout = the body handed to the subagent (the charter, the SPEC/MUSTs, the judgment history,
  #   and what to return)
  # stderr = the command the supervisor types (feeding the gate's returned values into decide)
  #   → the subagent's role ends at returning the judgment. The supervisor records it

org_cycle.py verify    --issue N --role skeptic                 # after the gate's admit
  # it hands over what the gate already looked at, and the areas the gate itself wrote it had not
  #   fired at

org_cycle.py integrate --issue N [--plan]
  # --plan: shows first what would be integrated, and conflicts with a parallel worktree
  # it stops unless the gate's admit and the skeptic's survives are **in the ledger** (exit 4)
```

See the state at any point with `org_cycle.py show --issue N` (the judgment history, the character
of the rounds, what it now waits on, and the number of irreversible changes). After touching a
production asset (DDL or privileges on a DB), leave it with `touched`, together with under whose
authority it went in. Accumulated worktrees go to `gc`. A record written in error, or a probe
written for verification, is declared void with `correction` (an append-only ledger cannot delete
it).

The org and the system grow together: `operate` closes the loop back to `requirements`
([docs/11](docs/11-sdlc-mold.md) §4), and the doctrine that guides each role is retrained as the
system matures ([docs/06](docs/06-doctrine-and-knowledge.md)).

See [ARCHITECTURE.md](ARCHITECTURE.md) for the whole system and [docs/README.md](docs/README.md) for
the reasoning in four Parts / twelve chapters: `docs/01`–`docs/04` (Foundations), `docs/02`/`docs/03`/`docs/07`/`docs/08`
(Design), `docs/05`/`docs/06`/`docs/09`/`docs/10`/`docs/11` (Operate — lifecycle, doctrine, attention,
loop reliability, the SDLC mold), and `docs/12` (the north star). `demos/S1-founding-rehearsal.md` is a
worked founding; `examples/` holds real runs (doctrine scoping, seam-driven delegation).

## Distribution

Publishing to OSS is **not required**. A Claude Code plugin is installed from a git source or a
local path, so the repo's visibility decides who can install:

- **Public GitHub (OSS):** anyone — `/plugin marketplace add github.com/you/orgforge-plugin`.
- **Private GitHub:** only people with repo access (their git credentials must resolve the clone).
- **Local / hand-delivered:** `/plugin marketplace add /path/to/orgforge-plugin`.

Private and local both work today; make it public only when you want open distribution.
