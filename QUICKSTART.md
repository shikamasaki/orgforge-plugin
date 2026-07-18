# Quickstart — install and run in a few minutes

This gets the orgforge-plugin guardrails **actually blocking inside a real Claude Code session**,
then walks the lifecycle: define an org, launch a department, drive the running metabolism. It does
not require publishing the repo — a private GitHub repo or a local path both work (see
[Distribution](#distribution) at the end).

> For the whole-system picture — the ecosystem (neutral core → projection → harness), the organs, and
> the full founding → operation → evolution lifecycle — read [ARCHITECTURE.md](ARCHITECTURE.md).
> This quickstart is the hands-on path through it.

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
| `ORG_CAP_DESTRUCTIVE_OPS` | cap on irreversible ops (rm/DROP/force; scope-weighted, `rm -rf`=3) | `3` |
| `ORG_CAP_EXTERNAL_WRITES` / `ORG_CAP_INFRA_CHANGES` | caps on outbound writes / infra applies | `3` |
| `ORG_CAP_FILE_MUTATIONS` | cap on overwriting existing files (reversible under VCS — high) | `200` |
| `ORG_CAP_SHELL_EFFECT` | cap on unclassifiable shell (fail-safe metered) | `8` |
| `ORG_HOOK_FAIL_OPEN` | `1` allows on organ error instead of blocking — **dev only** | off (fail-safe) |

The caps meter **irreversibility, not activity**: creating new files, reads, and build tooling
(`npm`, `pytest`, `git commit`) are not metered, so a normal build proceeds; only destructive /
external / overwrite actions draw down a budget (docs/11 §2.1).

## 4. Prove a guardrail actually fires

With `ORG_LEDGER_ROOT` set and a low cap, a runaway is blocked at the tool boundary:

```
export ORG_LEDGER_ROOT=/tmp/myorg/ledger; mkdir -p $ORG_LEDGER_ROOT
export ORG_CAP_DESTRUCTIVE_OPS=2
echo '{"hook_event_name":"PreToolUse","tool_name":"Bash","tool_input":{"command":"rm -rf /tmp/x"}}' \
  | python3 integrations/common/org_hook.py; echo "exit=$?  (2 = blocked)"
```

## 5. Run a department (headless)

A "department" is a Claude Code (or Codex) turn pointed at one role's profile. Use the runner —
it projects the role onto the harness and attaches the plugin so the guardrails apply:

```
python3 integrations/runner/run_department.py --harness claude --role <role> \
  --task "…" --ledger $ORG_LEDGER_ROOT --doctrine $ORG_DOCTRINE_ROOT \
  --tools read,write,run_tests --dry-run     # drop --dry-run to actually run
```

## 6. Drive the metabolism (the running loop)

Once an org is defined (§7) and departments can launch (§5), the running loop is three commands. They
operate on the **one backlog per department** — the `open_experiments` ledger view — which holds both
top-down **mandate** items and self-raised **self** items on one footing.

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
decomposition doctrine (docs/15): split only genuinely independent work, never split coupled work,
each child carries a seam contract.

### Run it unattended, on the harness's own scheduler

`template/schedule.yaml` declares the cadences as **data**; the host realizes them. On Claude Code,
use its built-in scheduler (which docs/09 names as "the harness's own loop" — R0-conformant, no
external cron needed):

```
/schedule   # register a recurring run of /org-tick (base interval) and /org-work <role> (per its
            #   loop.cadence), and /org-discover <role> (slower) — the unattended 24/7 metabolism
/loop       # or run a command on a fixed interval within an attended session you want to watch
```

See [integrations/claude-code/SCHEDULER.md](integrations/claude-code/SCHEDULER.md) for the full
wiring. `tick.py` still detects a **missed check** (a due check with no proof-of-run in the ledger),
so "the scheduler stopped firing" becomes a paged fact, not silent drift — the org checks its own
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

See [ARCHITECTURE.md](ARCHITECTURE.md) for the whole system, `docs/01`–`docs/09` for the core design,
`docs/10` for a worked founding, `docs/11`–`docs/15` for the operating organs (events, attention,
proxy-stack, manager accountability, decomposition), and `examples/` for real runs (doctrine scoping,
seam-driven delegation).

## Distribution

Publishing to OSS is **not required**. A Claude Code plugin is installed from a git source or a
local path, so the repo's visibility decides who can install:

- **Public GitHub (OSS):** anyone — `/plugin marketplace add github.com/you/orgforge-plugin`.
- **Private GitHub:** only people with repo access (their git credentials must resolve the clone).
- **Local / hand-delivered:** `/plugin marketplace add /path/to/orgforge-plugin`.

Private and local both work today; make it public only when you want open distribution.
