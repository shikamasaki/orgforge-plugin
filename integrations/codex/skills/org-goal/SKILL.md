---
name: org-goal
description: Start, inspect, resume, progress, complete, pause, or block a repository's persistent OrgForge goal and reconcile it with Codex's native Goal. Use when the user explicitly asks to set or continue a goal, asks Codex to keep working across sessions, invokes org-goal, or resumes an OrgForge-governed objective after restart.
---

# Operate the persistent OrgForge goal

Treat the OrgForge ledger as the portable source of truth and Codex's native Goal as a host
projection. Use the exact stable `orgforge` launcher injected by SessionStart. If that contract is
absent, stop and ask for a Codex session restart; never substitute a checkout or cache path.

Every CLI operation below must include `--json`. Parse `host_action`; do not infer that a native Goal
changed merely because the ledger changed.

## Start

1. Run `"<launcher>" org-goal start "<concrete objective>" --json`.
2. Only after the ledger accepts it, call native `create_goal` with the same objective.
3. Record the observed result with `org-goal host-sync --state active --assurance observed --json`.
   Add `--native-ref <threadId>` when the native result exposes one.
4. If native creation fails, record `host-sync --state failed --assurance observed --detail "..."` and
   report the degraded state. Keep the portable goal; do not silently delete or replace it.

Never overwrite an unfinished portable or native Goal. If Codex reports an existing native Goal,
call `get_goal`; reuse it only when its objective matches exactly. Otherwise record the mismatch and
stop for user direction.

## Inspect or resume

- Run `org-goal status --json`, then call `get_goal` and compare objective and state.
- When `resume_required` is true, run
  `org-goal resume --reason "<why this session is taking over>" --json` first. The ledger performs a
  compare-and-swap against the prior session; do not retry a lost race as a blind overwrite.
- If this Codex thread has no native Goal, call `create_goal` with the recovered objective, then record
  `host-sync`. If a conflicting native Goal exists, record `failed` and stop.

## Record progress

Run:

`org-goal progress --summary "<verified work>" --next-step "<concrete next action>" [--evidence <ref>] --json`

Do this at meaningful milestones and before a likely context boundary. Do not write plans as completed
work. Evidence references for progress are informative; completion evidence is validated separately.

## Complete

1. Confirm the objective is genuinely achieved and no required work remains.
2. Supply at least one resolvable proof: `file:<path>`, `git:<commit>`, or `ledger:<seq>`.
3. Run `org-goal complete --summary "..." --evidence <ref> --json`. The ledger audits that the proof
   exists before accepting completion.
4. Only after acceptance, call native `update_goal` with status `complete`, then record
   `host-sync --state complete --assurance observed`.

Never complete because a budget is low or work is being stopped.

## Block or pause

- Use `org-goal block --reason "..." --evidence "..." --json` only after observing the same blocker in
  the current turn. The third consecutive observation changes the portable state to `blocked`; only
  then call native `update_goal` with status `blocked` and record `host-sync`.
- Use `org-goal pause --reason "..." --next-step "..." --json` for an intentional, recoverable pause.
  Codex has no equivalent paused state, so do not claim native synchronization.
- Resume a blocked goal only after user direction or evidence that the external condition changed.

The plugin provides no execution while the Codex host is closed. Persistence means the objective,
evidence, owner session, and next action survive and are re-injected at SessionStart.
