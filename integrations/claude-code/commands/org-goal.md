---
description: Operate the repository's portable, ledger-backed OrgForge Goal across Claude Code and Codex sessions. Supports start, status, progress, pause, resume, block, complete, host-sync, and doctor without pretending a closed host keeps executing.
argument-hint: "<start|status|progress|pause|resume|block|complete|doctor> [arguments]"
allowed-tools: Bash(*), Read, Glob, Grep
---

Operate the persistent goal with arguments: **$ARGUMENTS**.

Use the exact stable `orgforge` launcher injected by SessionStart and run:

`"<injected launcher>" org-goal $ARGUMENTS --json`

Do not substitute `${CLAUDE_PLUGIN_ROOT}`, a plugin-cache path, or a development checkout. If the
SessionStart contract is absent, ask the user to restart Claude Code so the installed organ can bind.

Apply these rules:

- `start` fails when an unfinished goal exists; do not overwrite it.
- A new session must `resume --reason "..."` before progress, block, pause, or completion. A concurrent
  resume that loses compare-and-swap stays rejected.
- `progress` records verified work and a concrete next step.
- `block` records one real observation. Only three consecutive observations of the same blocker make
  the goal blocked; do not manufacture retries in one turn.
- `complete` requires at least one resolvable `file:<path>`, `git:<commit>`, or `ledger:<seq>` proof.
- Claude Code has no native Goal state. The ledger is normative; never report native synchronization.
- On an unfinished goal, offer `/loop 30m /org-goal status` for periodic attention while this session
  stays open. State explicitly that the loop ends with the host and is not background execution.

Report the resulting status, objective, next step, blocker count, and any `resume_required` state.
