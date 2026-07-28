---
description: Initialize a new orgforge org in this directory — create the ledger root, install the constitution/settings, set up the GitHub backlog labels, and verify the guardrails actually bite. Run this once, before /org-found. It sets up the org; it designs nothing.
argument-hint: "[org-name] [output-language: ja|en]"
allowed-tools: Bash(python3 *), Bash(mkdir *), Bash(cp *), Bash(git *), Bash(gh *), Bash(echo *), Bash(printf *), Bash(touch *), Bash(grep *), Bash(sed *), Bash(cat *), Read, Write
---

Stand up a **new org's state** in this directory, so `/org-found` has somewhere to write and the
guardrails have something to enforce against. This is the setup step that used to be a page of manual
`export`s in QUICKSTART; it makes the org's environment reproducible instead of hand-assembled.

Org name: **${1:-(derive from the directory name)}** · output language: **${2:-ja}**

**This command sets up; it does not design.** No RFP is read, no roles are invented, no Issues are
minted. The order is: `/org-init` → `/org-found` (design, CEO approves) → `/org-decompose` (task Issues)
→ `/org-work` (build).

## 1. Where the org's state lives

Two directories, both under the org root (this directory unless the CEO says otherwise):

- **`.orgforge/ledger/`** — the ledger root (`ledger.jsonl` + `HEAD`): the tamper-evident audit and
  enforcement record. **This is not the SSoT** — the SSoT is code + the domain model (conventions +
  the org spec); the ledger holds the receipts and the phase chain the gates read.
- **`.orgforge/doctrine/`, `.orgforge/conventions/`** — the per-role brains and the settled internal
  precedent (the domain-model half of the SSoT), injected at SessionStart.

!`mkdir -p .orgforge/ledger .orgforge/doctrine .orgforge/conventions && echo "created .orgforge/{ledger,doctrine,conventions}"`

The ledger file itself is created on first append — an empty directory is the correct initial state.

## 2. Install the org spec files

Copy the templates in as the org's own, editable copies. `constitution.yaml` is the charter/decision
line; `organization.yaml` is written by `/org-found` (the SKELETON is its starting point, left here so
founding fills it rather than inventing a shape).

!`for f in constitution.yaml sensors.yaml schedule.yaml moves.yaml ledger-schema.yaml role-settings.yaml; do if [ -f "$f" ]; then echo "  kept existing $f (not overwritten)"; elif cp "${CLAUDE_PLUGIN_ROOT}/template/$f" . 2>/dev/null; then echo "  installed $f"; else echo "  FAILED to install $f — template missing at ${CLAUDE_PLUGIN_ROOT}/template/$f"; fi; done; [ -f organization.yaml ] || [ -f organization.SKELETON.yaml ] || cp "${CLAUDE_PLUGIN_ROOT}/template/organization.SKELETON.yaml" organization.SKELETON.yaml 2>/dev/null`

Now set the org's identity in `constitution.yaml` — read it and edit two fields:

- **`output_language: ${2:-ja}`** — every Issue body, spec, work-log comment, and escalation is written
  in this language, so the CEO reads their org in their own language (code, ledger event classes, file
  paths, and the `coverage_row:` trailer stay canonical English).
That is the only field to edit here. The org's **purpose/name** is NOT set in `constitution.yaml` — it
has no such key; `purpose` lives in `organization.yaml`, which `/org-found` writes from the RFP. Note
`${1}` for that step and move on; do not invent a `purpose:` key here (nothing reads it).

## 3. Confirm the org is DISCOVERABLE — no environment setup required

**This step writes nothing.** The org's state is a place on disk (`.orgforge/` beside
`organization.yaml`) and the backlog repo is whatever `git remote origin` points at — both are facts
about the checkout, so the organs and the guardrail hook **find them** rather than being told
(`tools/discover.py`). Nothing to export, no `.envrc`, no `direnv allow`.

That is not a convenience: an org whose state is addressed by `/Users/someone/proj/.orgforge/ledger`
is not portable, and the whole point of putting the full spec in the Issue is that **any** environment
can pick up the work. A setup step that must be repeated per machine is a step that gets skipped — and
when it is skipped, the guardrail finds no ledger and **allows everything**, silently. Discovery
removes that failure mode instead of documenting it.

!`python3 "${CLAUDE_PLUGIN_ROOT}/tools/discover.py" env 2>&1`

Those are the values the organs will resolve on their own; you do **not** need to export them. Env
vars still win when set, for the cases that genuinely need an override (a ledger deliberately kept
outside the checkout, a CI pin) — but the default path needs none of them.

`ORG_REQUIRE_SEAM` is on by default in the constitution's `enforcement:` block: it blocks a subagent
spawn carrying neither a seam contract nor an explicit `INDEPENDENT:` declaration — the tooth that
stops recursive fan-out from drifting.

If the line for `ORG_GITHUB_REPO` is missing above, this checkout has no GitHub remote: the org is
**ledger-only** and work cannot be claimed from another environment. Add a remote (`gh repo create
--source=.`) before `/org-decompose`, or accept a single-machine org.

## 4. The branch model (docs/11 §4c)

Work lands `feat/issue-<N>-<slug>` → `develop` → `main`. `develop` must exist before the first task,
or every hand-back PR targets the wrong base:

!`git rev-parse --verify develop >/dev/null 2>&1 && echo "develop exists" || { git rev-parse --verify HEAD >/dev/null 2>&1 && git branch develop && echo "created develop" || echo "no commits yet — create develop after the first commit"; }`

## 5. The backlog labels

Pre-create the label vocabulary so the first `create`/`claim` doesn't race on label creation, and so the
CEO sees a coherent set in the GitHub UI from the start (skip with no repo).

The repo is read **from `.envrc`**, not from the shell: step 3 just *wrote* that file, and this session's
shell has not sourced it (direnv loads on the next `cd`). Reading the live env var here would find it
unset on a first run and skip label creation entirely — while printing a reassuring "ledger-only".

!`REPO="$(sed -n 's/^export ORG_GITHUB_REPO="\{0,1\}\([^"]*\)"\{0,1\}$/\1/p' .envrc 2>/dev/null | tail -1)"; REPO="${REPO:-${ORG_GITHUB_REPO:-}}"; if [ -n "$REPO" ]; then fail=0; for spec in ready:1d76db in-progress:fbca04 blocked:b60205 needs-human:d93f0b done:0e8a16 kind:objective:0e8a16 kind:task:bfd4f2 mandate:fbca04 self:c5def5; do name="orgforge:${spec%:*}"; color="${spec##*:}"; if gh label create "$name" --repo "$REPO" --color "$color" --force >/dev/null 2>&1; then echo "  $name"; else echo "  FAILED $name"; fail=$((fail+1)); fi; done; if [ "$fail" -eq 0 ]; then echo "labels ensured on $REPO"; else echo "WARNING: $fail label(s) FAILED on $REPO — fix gh auth / repo access BEFORE /org-decompose, or the first create races on label creation"; fi; else echo "no ORG_GITHUB_REPO — ledger-only org, skipping labels (set it in .envrc to enable the cross-environment backlog)"; fi`

## 6. Verify the org spec lints, and the guardrails actually bite

An org whose spec doesn't lint is not initialized — it just has files. **Expected here:** exactly one
violation, `[SC] organization.yaml file not found` — the chart is written by `/org-found`, so its absence
at init time is the correct pre-founding state. Any *other* violation is a real problem to fix now (a
`SET_ME` left in `constitution.yaml`, a broken sensor or move). Report which case you got.

!`python3 "${CLAUDE_PLUGIN_ROOT}/tools/org_lint.py" organization.yaml constitution.yaml moves.yaml ledger-schema.yaml sensors.yaml 2>&1 | tail -20`

Then confirm the enforcement layer actually reaches this session — that the hooks are installed and can
block, rather than being configured-but-inert:

!`python3 "${CLAUDE_PLUGIN_ROOT}/tools/harness_probe.py" --hook "${CLAUDE_PLUGIN_ROOT}/scripts/org_hook.py" --tools "${CLAUDE_PLUGIN_ROOT}/tools" 2>&1 | tail -15`

If the probe reports the guardrails cannot block, say so plainly in the report — an org that believes it
is guarded but isn't is worse than one that knows it is unguarded.

## 7. Report up and hand off

Tell the CEO, briefly: where the ledger lives, the output language, whether the GitHub backlog is wired
(and to what repo) or the org is ledger-only, whether `develop` exists, and the lint/probe result.

Then the next step: **`/org-found "<the RFP, or a path to the brief>"`** — which writes the five fixed
founding artifacts (`RFP.md`, `FEATURE-INVENTORY.md`, `ARCHITECTURE.md` = the 全体設計書,
`coverage-manifest.md`, `organization.yaml`; docs/11 §0a) and stops for approval.

## Discipline

- **Idempotent.** Re-running never clobbers an existing `constitution.yaml`, ledger, or branch — it
  fills what is missing and reports what it kept. Safe to re-run to repair a half-set-up org.
- **Sets up, never designs.** If the CEO passed an RFP to this command, do not read it as scope — point
  them at `/org-found`.
