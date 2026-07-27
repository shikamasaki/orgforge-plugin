# Quickstart — install and run in a few minutes

The happy path: **found an AI-native IT business company, watch it build and ship a backlog item
through the forced SDLC (requirements → design → implement → test → deploy → operate), and put it
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

## 1. Install the plugin

The plugin lives in `integrations/claude-code/` and is self-contained (its `build.sh` bundles the
neutral `tools/`, `scripts/`, and `template/` into the plugin root). From a Claude Code session:

```
/plugin marketplace add /path/to/orgforge-plugin      # a local clone works; or the git URL
/plugin install orgforge-plugin@orgforge-plugin
```

Or, for a headless run without installing, load it directly:

```
echo "your prompt" | ORG_LEDGER_ROOT=/tmp/myorg/ledger \
  claude -p --plugin-dir integrations/claude-code --allowedTools "Bash,Write,Agent"
```

Verify the manifest first if you edited anything: `claude plugin validate integrations/claude-code --strict`.
Regenerate the bundle after editing neutral source: `integrations/claude-code/build.sh`.

## 2. Point it at an org state (the one required setting)

The guardrails read the **ledger** — the org's single source of truth. Without it, the hook
allows everything and says so loudly on stderr (so a misconfiguration is visible, never silent).

```
export ORG_LEDGER_ROOT=/path/to/your/org/ledger      # a directory; holds ledger.jsonl + HEAD
```

That one variable turns the blast-radius cap on. Everything else below is optional tuning.

## 3. Optional settings (each has a safe default)

| Env var | What it does | Default |
|---|---|---|
| `ORG_DOCTRINE_ROOT` | dir of per-role `<role>.json` brains; the SessionStart hook injects the role's doctrine at launch | (none → no doctrine injected) |
| `ORG_ROLE` | which role this session is — the key the doctrine injection and ledger events use | (none) |
| `ORG_CONVENTIONS_ROOT` | dir of settled conventions, injected alongside doctrine | (none) |
| `ORG_REQUIRE_SEAM` | `1` blocks an `Agent`/`Task` spawn that carries neither a seam contract (a `handoff.py` packet) nor an explicit `INDEPENDENT:` declaration — stops recursive splits from drifting | off |
| `ORG_CAP_DESTRUCTIVE_OPS` | per-day cap on irreversible ops (rm/DROP/force; scope-weighted, `rm -rf`=3) | `50` |
| `ORG_CAP_EXTERNAL_WRITES` / `ORG_CAP_INFRA_CHANGES` | per-day caps on outbound writes / infra applies | `30` / `20` |
| `ORG_CAP_FILE_MUTATIONS` | per-day cap on overwriting existing files (reversible under VCS — high) | `500` |
| `ORG_HOOK_FAIL_OPEN` | `1` allows on organ error instead of blocking — **dev only** | off (fail-safe) |

The caps are **per-day budgets** (the window rolls daily) and meter **irreversibility, not activity**:
reads, build tooling (`npm`, `pytest`, `git status`), unknown/unfamiliar commands, and new-file
creation are **not** metered — only explicit destructive / external / infra actions draw down a budget.
See [REFERENCE.md](REFERENCE.md) for the full variable, command, event, and troubleshooting reference.

## 4. Sanity-check: a guardrail actually fires

Before founding a company you'll trust to fan out, confirm the teeth are live. With `ORG_LEDGER_ROOT`
set and a low cap, a runaway is blocked at the tool boundary — one quick check, not the headline:

```
export ORG_LEDGER_ROOT=/tmp/myorg/ledger; mkdir -p $ORG_LEDGER_ROOT
export ORG_CAP_DESTRUCTIVE_OPS=2
echo '{"hook_event_name":"PreToolUse","tool_name":"Bash","tool_input":{"command":"rm -rf /tmp/x"}}' \
  | python3 integrations/common/org_hook.py; echo "exit=$?  (2 = blocked)"
```

(For the full certification — including that the block fires for a *spawned subagent's* tool call —
run `/org-verify-guards` once at founding. Caps, the iteration/cycle limits, and the seam gate are
declared in `constitution.yaml`'s `enforcement:` block; the `ORG_CAP_*` env vars above are **dev
overrides** over that spec — see [REFERENCE.md](REFERENCE.md).)

## 5. Run a department (headless)

A "department" is a Claude Code (or Codex) turn pointed at one role's profile. Use the runner —
it projects the role onto the harness and attaches the plugin so the guardrails apply:

```
python3 integrations/runner/run_department.py --harness claude --role <role> \
  --task "…" --ledger $ORG_LEDGER_ROOT --doctrine $ORG_DOCTRINE_ROOT \
  --tools read,write,run_tests --dry-run     # drop --dry-run to actually run
```

## 6. Start the metabolism — one command brings the org to its running state

Once an org is defined (§7) and `ORG_LEDGER_ROOT` + `ORG_ROLE` are set, **run `/org-start`**:

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
one); the org keeps only the monitoring `/loop` can't give it (the missed-tick detector in `/org-tick`).
You usually won't type `/org-start` yourself — on an org session the SessionStart hook prompts the model
to run it. Check on the org any time with **`/org`**.

**Session-scoped:** these `/loop` cycles run while this Claude Code session is open and stop when it
closes. For a genuinely 24/7 org with no session open, use an OS-level cron —
`integrations/claude-code/scheduler-install.sh` (see [SCHEDULER.md](integrations/claude-code/SCHEDULER.md)) —
a separate, explicit setup.

**Check on it any time with `/org`** — one GREEN/AMBER/RED board: what it did, what's in progress, and
whether it needs you. You don't read the ledger; `/org` tells you in plain language. Feed new work in
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

`/org-work` uses `attention.py` to prioritize the whole backlog (situated attention to the org
ranking + problemistic-search boost), **floors an in-zone mandate** so a live instruction is not
starved by low-priority self work, and picks a prefix within the WIP limit. Delegation follows the
decomposition doctrine (docs/03): split only genuinely independent work, never split coupled work,
each child carries a seam contract.

### Session-scoped vs. genuinely 24/7

`/org-start` schedules the cycles **within this session** (Claude Code's `CronCreate` / `/schedule` are
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
- **Let the org draft it** — run **`/org-found <your RFP or brief>`**. The org does its own
  feature inventory, architecture with seam contracts, and a linted `organization.yaml`, then
  **stops and reports up for your review** before anything is built (founding is design; the build
  is the CEO's next call). This is the founding flow, as a command.

`/org-found` is *design only* — you approve the scope. It is the moment the abstract "org" becomes a
**company**: a purpose stated as a business, a feature inventory with an explicit exclude list, and
contracts the lint's O10 tooth checks for coverage (every deliverable is owned and independently
checked — [docs/11](docs/11-sdlc-mold.md) §0, [docs/01](docs/01-requirements.md) J14/S9).

## 8. The company builds and ships — through the forced SDLC

This is the headline. Once you approve the scope and the metabolism is running (§6), the PM loop
(`/org-work`) pulls a backlog item and the company builds it — but it cannot skip a step. Every
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
