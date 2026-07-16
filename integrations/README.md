# integrations — running the articulated org on a real harness

The `tools/*.py` organs are harness-neutral (they read the ledger and exit `0`=allow / `10`=escalate).
This directory is the **projection layer** (PROJECTION.md, docs/09) that makes them *actually fire*
as direct features of a real coding-agent harness — so a guardrail **blocks a real tool call**, a
department **runs headless and unattended**, and doctrine **loads into context** every cycle. Two
harnesses are wired; the core stays neutral.

The load-bearing discovery (verified 2026-07 against the official docs): **Claude Code and Codex
share the same `PreToolUse` hook contract** — exit `2` (or a `permissionDecision: "deny"` JSON)
blocks the tool call. So one neutral adapter serves both.

## Layout

```
integrations/
  common/
    org_hook.py            # THE guardrail bridge. A PreToolUse hook (both harnesses call it):
                           #   reads the tool call + the ledger, runs the relevant organ, and
                           #   BLOCKS (exit 2 / deny-JSON) when the organ escalates. Fail-safe:
                           #   an unevaluable guardrail blocks, never silently allows.
    org_session_start.py   # A SessionStart hook (both): renders the role's doctrine + conventions
                           #   and injects them as context — the "load" step of docs/07 / docs/13.
  claude-code/
    .claude-plugin/plugin.json   # a Claude Code PLUGIN bundling the below (install once)
    hooks/hooks.json             # wires org_hook.py (PreToolUse) + org_session_start (SessionStart)
    agents/*.md                  # per-department subagents (gate, skeptic, registrar, …)
    commands/*.md                # organ slash-commands (/org-tick, /org-mandate)
  codex/
    hooks.json             # the SAME org_hook.py, wired to Codex's PreToolUse (drop at .codex/)
    config.toml            # Codex harness-map: neutral role-settings -> model/sandbox/approval
    AGENTS.md.tmpl         # the per-department instruction-file projection for Codex
  runner/
    run_department.py      # launch ONE role as a headless `claude -p` / `codex exec` turn
                           #   from its neutral settings. Ships no scheduler (R0) — cron/tick drives.
```

## Claude Code — install as a plugin

```bash
# from a marketplace or a local path; the plugin bundles hooks + agents + commands
/plugin install project org-first-agents        # checks into the repo for the team
```

Set the org's state location so the guardrails have something to judge against:

```bash
export ORG_LEDGER_ROOT=/path/to/your/org/ledger      # holds ledger.jsonl
export ORG_CAP_EXTERNAL_WRITES=3                      # tune the blast-radius caps per dimension
export ORG_DOCTRINE_ROOT=/path/to/doctrine ORG_CONVENTIONS_ROOT=/path/to/conventions ORG_ROLE=<role>
```

Now a `Bash`/`Write`/`Edit` that would cross a blast-radius cap is **denied before it runs**, and
each session starts with the role's current doctrine loaded. Organ checks are available as
`/org-tick` (metabolism health) and `/org-mandate` (adjudicate a mandate conflict). Departments are
`gate`, `skeptic`, `registrar` subagents. For enforcement the user can't disable, ship the hook via
**managed settings** (Managed > Local > Project > Plugin > User).

## Codex — drop the config into `.codex/`

```bash
cp integrations/codex/hooks.json   <repo>/.codex/hooks.json
cp integrations/codex/config.toml  <repo>/.codex/config.toml
# per-department prompt: put an AGENTS.md (from AGENTS.md.tmpl) in each dept's working dir
export ORG_LEDGER_ROOT=/path/to/ledger
```

Codex's `PreToolUse` hook calls the **same** `org_hook.py`, so the identical guardrail blocks
identical actions. In unattended CI, either register the hook as **managed** or run with
`--dangerously-bypass-hook-trust` (Codex requires hooks to be trusted). Tool availability is set by
`sandbox_mode` + MCP rather than an allowlist; the *block* is the hook, same as Claude Code.

## Running unattended (both harnesses)

```bash
# one department turn, headless — inspect the projected command first:
python3 integrations/runner/run_department.py --harness claude --role gate \
  --task "Review the candidate; admit or reject" --ledger $ORG_LEDGER_ROOT \
  --tools "read,grep,run_tests" --dry-run

# drive the cadence with cron (R0: the schedule's CONTENT is ours, the DRIVE is the host's):
#   */30 * * * *  python3 tools/tick.py plan $ORG_LEDGER_ROOT template/schedule.yaml --now-min $(...)
# tick.py says which checks are due and DETECTS a missed one (a due check with no proof-of-run) —
# so "the cron stopped firing" becomes a paged fact, not silent drift.
```

## What is neutral vs. what is per-harness (the R0 line)

| | ships in the repo (neutral) | the host provides |
|---|---|---|
| the guardrail's decision | `tools/*.py` + `common/org_hook.py` | the PreToolUse hook event that calls it |
| the schedule's content | `template/schedule.yaml` + `tools/tick.py` | the cron/CI that fires the tick |
| a role's profile | `organization.yaml` + `role-settings.yaml` | the instruction-file convention (CLAUDE.md / AGENTS.md) |
| doctrine content | `tools/doctrine.py` + the store | the SessionStart hook that injects it |

No bespoke runtime, no shipped scheduler, no vendor lock — the org is articulated once and projected
onto whichever harness runs each department. Adding a third harness is one more folder here, not a
change to the organs.
