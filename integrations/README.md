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

### Codex: installing the plugin does not enable enforcement

Verified 2026-07 against codex-cli 0.146.0, by installing this plugin and observing what actually
fires. Each of these was measured, not read from a doc — the public plugin docs URL is dead.

| | |
|---|---|
| **Self-contained reference** | `$PLUGIN_ROOT` — the directory Codex unpacks the plugin into. There is **no** `CODEX_PLUGIN_ROOT`; `CLAUDE_PLUGIN_ROOT` exists as an alias for Claude Code compatibility. The install path is version-pinned, so never hardcode it. |
| **Marketplace manifest** | `.agents/plugins/marketplace.json`. A `marketplace.json` at the repo root is **not** read (`marketplace root does not contain a supported manifest`). |
| **Hooks manifest** | `hooks/hooks.json`, referenced from `plugin.json` as `"hooks": "./hooks/hooks.json"`. Codex's parser accepts only `description` and `hooks` — **a `//` comment key makes it warn and skip the entire file**, so the guardrail is silently absent. Claude Code accepts `//`, which is how that mistake got made here. |

**Installing and enabling the plugin does NOT turn enforcement on.** An untrusted hook is
**silently skipped** — no prompt, no warning in `codex exec`, and no ledger entry. Trust is granted
in the interactive TUI (`/hooks`) and stored in `~/.codex/config.toml` as a **content-bound sha256**
(`[hooks.state."<id>"].trusted_hash`), so it cannot be seeded by hand or precomputed. There is no
verified headless path to grant it.

Consequences to plan around:

- **Editing a hook changes its hash, so it can require re-trusting.** A plugin upgrade that touches
  `hooks/hooks.json` may leave enforcement off until the TUI is opened again.
- `--dangerously-bypass-hook-trust` runs enabled hooks without trust. **It is for CI smoke tests
  only and does not count toward any production guarantee** — it proves the hook body works, not
  that a normally-installed Codex is guarded.
- A user-level `~/.codex/hooks.json` without the flag makes `codex exec` **hang** on the interactive
  trust prompt.

### What was measured with the plugin trusted-by-bypass

With `--dangerously-bypass-hook-trust`, in a disposable org against a sentinel file:

- PreToolUse fires for `Bash`; `session_id` and `tool_use_id` are both populated
  (`019fb2da-…`, `call_PoqvYbj5…`) — so the reservation's idempotency key is real, not empty.
- An operation inside the cap runs and leaves an `allow` reservation in the ledger.
- An operation over the cap is denied, **the sentinel is unchanged**, and the `hold` is recorded.
- A torn ledger denies the operation.
- The same `tool_use_id` replayed does not double-count.
- The hook works with the source checkout moved away entirely — nothing outside `$PLUGIN_ROOT`.

Codex was instructed to attempt the operation **once** and stop on refusal without trying another
route; otherwise a correctly-denied call followed by a successful workaround reads as the hook
never firing.

### Verified on the normal path — trusted in the TUI, no bypass

The hooks were then trusted once in the interactive TUI (PreToolUse and SessionStart, against
v0.35.0's exact content) and the same suite re-run with **no `--dangerously-bypass-hook-trust`**:

| | |
|---|---|
| Inside the cap | The delete ran; `seq=1 allow delta=1.0 cap=150` recorded, with a real `session_id` and `tool_use_id` (`call_QeNP88nMRu3P4HX…`) |
| Over the cap | Denied. **Sentinel unchanged**, `seq=2 hold delta=1.0 cap=0` recorded |
| Torn ledger | Denied. Sentinel unchanged |
| Replayed `tool_use_id` | One record, not two |
| **Control: plugin removed** | The same over-cap delete **succeeded** and the ledger did not grow (3 → 3) — so what stopped it in the cases above was this plugin's hook, not something else |
| Re-installed | Trust survived (the content is unchanged) and enforcement came back: denied again, ledger 3 → 4 |

All four reservations are `validated:v1` and the chain replays clean. **This is the guarantee that
counts**: a normally-installed, normally-trusted Codex is gated. The bypass runs above only ever
showed that the hook body works.

One caveat worth restating: trust is bound to the hook file's content, so **shipping a change to
`hooks/hooks.json` can leave enforcement off until it is trusted again**. Re-installing the same
content kept it (measured); changing the content is the case to watch.

## Codex as a judge — a genuinely different lineage

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

### Judge environment preflight

An organization can declare bounded probes under
`constitution.yaml: enforcement.judges.preflights`. Each probe uses an argv list (never a shell
string), requires an explicit `timeout_seconds`, and can be scoped with
`applies_to.issues`, `applies_to.phases`, and `applies_to.roles`. Selectors are ANDed; values inside
one selector are ORed. A failed or timed-out matching probe makes `org_cycle verify` exit 8 before
any headless judge is started. Successful measured evidence (command, exit code, elapsed time,
stdout, and stderr) is included in the judge material. OrgForge does not infer a particular daemon
implementation from the result.

### Stable installed-organ invocation

At SessionStart, each harness atomically binds the organization to its actual bundled tools and
creates a harness-specific launcher under Git's untracked common dir
(`.git/orgforge/runtime/<harness>/bin/orgforge`; a ledger-only non-Git org falls back to
`.orgforge/runtime/<harness>/bin/orgforge`). Session and judge context use that organization-side
launcher instead of a versioned Claude Code or Codex cache path:

```bash
"/absolute/org/.git/orgforge/runtime/claude-code/bin/orgforge" org-cycle verify --issue 11 --role skeptic
"/absolute/org/.git/orgforge/runtime/claude-code/bin/orgforge" github-sync decide --issue 11 ...
"/absolute/org/.git/orgforge/runtime/codex/bin/orgforge" ledger verify
```

The launcher reads the adjacent `installed-organ.json`, so the public invocation stays fixed
while a host restart advances the bound plugin root and version. Ledger mutations compare the
executing tools root with that binding. A different development checkout is rejected with both
paths and the recovery command; read-only inspection remains available. This is drift/provenance
detection within one user account, not a hostile-process security boundary.

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

Both plugin bundles ship the same host-independent redline monitor registry. Before starting or
restarting a long-lived monitor, use its installed script to check the logical instance:

```bash
"<injected launcher>" redline-monitor rearm-check "$ORG_LEDGER_ROOT" \
  --role supervisor --instance redline-supervisor
"<injected launcher>" redline-monitor status "$ORG_LEDGER_ROOT"
```

Only `READY TO ARM` authorizes a replacement. A live/stale record returns `DO NOT REARM`; use
`stop <record-id> --root "$ORG_LEDGER_ROOT"` to request cooperative shutdown of that exact process. This
surface does not depend on Claude TaskList or a Codex session and exposes PID, version, role,
instance, duplicates and old-version orphans while keeping healthy RED polling silent.

```bash
# one department turn, headless — inspect the projected command first:
python3 integrations/runner/run_department.py --harness claude --role gate \
  --task "Review the candidate; admit or reject" --ledger $ORG_LEDGER_ROOT \
  --tools "read,grep,run_tests" --dry-run

# drive the cadence with cron (R0: the schedule's CONTENT is ours, the DRIVE is the host's).
# Use the installed scheduler adapter, not a slash command or the pure planner:
#   integrations/claude-code/scheduler-install.sh --role supervisor --cycles tick
# It selects launchd/cron, runs the deterministic machine checks, persists tick_planned, verifies
# backend readback, and keeps an atomic last-run receipt. Process exit alone is not accepted as proof.
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
