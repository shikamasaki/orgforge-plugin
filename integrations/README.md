# integrations — running the articulated org on a real harness

The `tools/*.py` organs are harness-neutral (they read the ledger and exit `0`=allow / `10`=escalate).
This directory is the **projection layer** (PROJECTION.md, docs/08) that makes them *actually fire*
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
                           #   and injects them as context — the "load" step of docs/06 / docs/05.
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

The repo ships a marketplace manifest at `.claude-plugin/marketplace.json` pointing at the plugin
in `integrations/claude-code/`. The plugin is **self-contained**: `build.sh` bundles the organ
`tools/`, the hook `scripts/`, and the `template/` data files into the plugin root, because a
Claude Code plugin can only reference paths under `${CLAUDE_PLUGIN_ROOT}` (external paths are not
copied to the install cache). Regenerate the bundle after editing the neutral source:

```bash
integrations/claude-code/build.sh            # sync neutral source -> plugin bundle
integrations/claude-code/build.sh --check    # CI gate: fail if the bundle drifted
claude plugin validate integrations/claude-code --strict   # verify the manifest (passes)
```

Install from the marketplace (local path works for testing):

```bash
/plugin marketplace add /path/to/orgforge-plugin      # or the git URL
/plugin install orgforge-plugin@orgforge-plugin
```

Or load it directly for a headless run without installing:

```bash
echo "your prompt" | ORG_LEDGER_ROOT=/path/to/ledger \
  claude -p --plugin-dir integrations/claude-code --allowedTools "Bash"
```

**Verified on the real CLI (v2.1.211):** `--plugin-dir` loads the plugin, the `PreToolUse` hook
fires with the real event JSON, and Claude Code **honors the hook's `deny` + exit 2** — a tool
call is actually blocked and the reason reaches the model. (Confirmed both that the hook fires and
that a `deny` blocks; the blast-radius rule blocks an over-cap external write specifically.)

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

### Codex as a judge — a genuinely different lineage

`template/role-settings.yaml` declares `skeptic: model_family: family-B` — a different family from
the gate and the maker, because an adversarial checker on the same base model shares their blind
spots (docs/03 §3). Inside one harness a subagent inherits the parent's model, so that declaration
had no effect. Running the judge on **another harness** is what makes the lineage real.

```bash
# 1. build the prompt (the seam gate reads a referenced file, so a path works too)
python3 tools/org_cycle.py verify --issue 11 --role skeptic > /tmp/sk11.md

# 2. run it headless, with the verdict shape enforced by the schema
codex exec --sandbox read-only -m gpt-5.5   --output-schema template/schemas/skeptic-verdict.json   -o /tmp/sk11.json "$(cat /tmp/sk11.md)" </dev/null

# 3. check the report has the shape its role owes before reading it as a judgment
python3 tools/org_cycle.py intake --issue 11 --role skeptic --report - < /tmp/sk11.json
```

Two layers, deliberately: `--output-schema` enforces the *shape* of the verdict (a report cannot
come back missing `verdict` or `evidence`), and `intake` checks the *content* (a field present but
empty is still incomplete). A judge runs `--sandbox read-only`, so it cannot write regardless of
whether the Codex hook is wired.

Verified against Codex CLI 0.146.0 with a ChatGPT account, where two things bit:

- **`gpt-5-codex` is rejected** — *"not supported when using Codex with a ChatGPT account."*
  Confirm a model name with `codex exec -m <m> "Reply OK"` before writing it into a config.
- **Structured Outputs requires every property in `required`** when `additionalProperties: false`.
  An optional field is expressed as `"type": ["string", "null"]`, not by omission from `required`.
- `codex exec` reads stdin, so a non-interactive call needs `</dev/null`; outside a git repo it
  needs `--skip-git-repo-check`.

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
