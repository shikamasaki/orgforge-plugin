# Quickstart — install and run in a few minutes

This gets the org-first-agents guardrails **actually blocking inside a real Claude Code session**,
then points you at how to run a department. It does not require publishing the repo — a private
GitHub repo or a local path both work (see [Distribution](#distribution) at the end).

## 1. Install the plugin

The plugin lives in `integrations/claude-code/` and is self-contained (its `build.sh` bundles the
neutral `tools/`, `scripts/`, and `template/` into the plugin root). From a Claude Code session:

```
/plugin marketplace add /path/to/org-first-agents      # a local clone works; or the git URL
/plugin install org-first-agents@org-first-agents
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

Drive it on a cadence with cron (R0: the schedule's *content* is yours, the *drive* is the host's):

```
*/30 * * * *  python3 tools/tick.py plan $ORG_LEDGER_ROOT template/schedule.yaml --now-min $(date +%s)
```

`tick.py` reports which checks are due and **detects a missed one** (a due check with no
proof-of-run), so "the cron stopped firing" becomes a paged fact, not silent drift.

## 6. Define your own org — two ways in

The plugin is the *engine*; your organization is `organization.yaml` + `constitution.yaml` +
`moves.yaml`, validated by `python3 tools/org_lint.py …`. Two starting points ship with it:

- **Write it yourself** — copy `template/organization.SKELETON.yaml` to `organization.yaml` and
  fill the `<ANGLE_BRACKET>` slots. The control skeleton (supervisor / gate / skeptic / registrar)
  is kept intact — you fill purpose, domain roles, and their contracts. Then lint it and iterate.
- **Let the org draft it** — run **`/org-found <your RFP or brief>`**. The org does its own
  feature inventory, architecture with seam contracts, and a linted `organization.yaml`, then
  **stops and reports up for your review** before anything is built (founding is design; the build
  is the CEO's next call). This is the founding flow, as a command.

See `docs/01`–`docs/09` for the design, `docs/10` for a worked founding, and `examples/` for real
runs (doctrine scoping, seam-driven delegation).

## Distribution

Publishing to OSS is **not required**. A Claude Code plugin is installed from a git source or a
local path, so the repo's visibility decides who can install:

- **Public GitHub (OSS):** anyone — `/plugin marketplace add github.com/you/org-first-agents`.
- **Private GitHub:** only people with repo access (their git credentials must resolve the clone).
- **Local / hand-delivered:** `/plugin marketplace add /path/to/org-first-agents`.

Private and local both work today; make it public only when you want open distribution.
