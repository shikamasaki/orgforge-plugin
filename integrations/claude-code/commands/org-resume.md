---
description: Show a role's work in progress — candidates it started but did not finish, each with its latest progress checkpoint (how far, what's done, the next step, any blocker). The manual counterpart to the automatic SessionStart injection; use it to see and pick up interrupted work after a /clear or a fresh session.
argument-hint: "[role]"
allowed-tools: Bash(python3 *)
---

Recover **work in progress** for role **${1:-(all roles)}** from the ledger — the work that survives a
context wipe. A half-done implementation lives in the ledger's `progress_recorded` checkpoints, not in
the lost conversation, so this shows exactly where a cycle stopped and what its next step is.

Ledger root: `${ORG_LEDGER_ROOT}` (must be set).

## Work in progress (started, not yet completed)

!`python3 "${CLAUDE_PLUGIN_ROOT}/tools/ledger.py" view "${ORG_LEDGER_ROOT}" work_in_progress`

Based on the above, for the target role:
- Each entry is a candidate that was **started but never completed**, with its latest checkpoint —
  `fraction`/`phase` (how far), `done_so_far` (what exists), **`next_step`** (what to do next), and
  `blocked_by` (why it stopped, if it did).
- **Resume from `next_step`, do not restart.** Verify the stated `artifacts`/`done_so_far` still hold,
  then continue the cycle and record the next `progress_recorded` (or `cycle_completed` when finished).
- An entry with **no progress checkpoint** was started but never checkpointed — verify the actual state
  before continuing (it may have done nothing, or done work it failed to record).

Note: on a fresh session the SessionStart hook already injects this automatically, so "just continue"
works without running this command. Use `/org-resume` when you want to see the full in-progress board
explicitly, or to pick a specific interrupted item to resume.
