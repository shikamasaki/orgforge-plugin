---
description: Triage an external signal (a bug report, an issue, a piece of feedback) into the backlog — the factory's front door. Turns raw incoming work into a labeled backlog item without a per-task prompt, compressing the human's input to one signal. Feeds /org-work; does not execute.
argument-hint: "<signal text, or an issue/bug reference>"
allowed-tools: Bash(python3 *)
---

The factory's **front door** (docs/12 §5 #6). An external signal — **$1** — becomes a triaged backlog
item so the org can work it unattended. The human's input is compressed to *handing over the signal*;
triage does the rest. This is what makes orgforge a factory (work flows in from the world) rather than a
workshop (a human types every task).

Ledger root: `${ORG_LEDGER_ROOT}` (must be set).

## 1. Read the signal and the current state

Understand the incoming signal (**$1**). Then read what the org already knows, so triage doesn't
duplicate open work or re-open a known death:

!`python3 "${CLAUDE_PLUGIN_ROOT}/tools/ledger.py" view "${ORG_LEDGER_ROOT}" open_experiments`
!`python3 "${CLAUDE_PLUGIN_ROOT}/tools/ledger.py" view "${ORG_LEDGER_ROOT}" death_causes`

## 2. Triage — classify, then mint (or reject) a backlog item

Decide, from the signal:
- **Is it actionable and in scope?** If it's noise, a duplicate of an open item, or out of the org's
  purpose, do NOT mint an item — say why and stop. Not every signal becomes work.
- **Is it a known death?** If the signal asks for something the org already tried and retired, surface
  that (don't re-open blindly); a human decides whether to override.
- **What department's domain is it?** Route it to the owning role (docs/03 §3 — domain work to the
  domain role), not to a coordinator.

For an actionable, novel, in-scope signal, mint a backlog item as a **mandate** (a top-down instruction
entering from outside), so attention.py floors it appropriately (zone of acceptance):

!`echo 'Append the triaged item: python3 "'"${CLAUDE_PLUGIN_ROOT}"'/tools/ledger.py" append "'"${ORG_LEDGER_ROOT}"'" --actor triage --class candidate_submitted --payload {"maker":"<owning-role>","candidate_id":"<id>","contract_ref":"<objective>","source":"mandate","evidence":["<the signal ref>"]}'`

## 3. Report

State what you did: minted a backlog item (which role, what objective), or rejected the signal (noise /
duplicate / known-death / out-of-scope) with the reason. The item now flows through `/org-work` like any
other backlog entry.

## Unattended intake (the host wires the source)

To ingest automatically (R0 — the org ships no ingestion service, the host feeds it): a host cron runs,
e.g., `gh issue list --label orgforge:ready --json ...` and pipes each new issue to `claude -p "/org-triage <issue>"`.
The human's whole input is then **applying one label** (`orgforge:ready`) to an issue — the y-hirakaw
"instruction compressed to one label." orgforge supplies the triage; the host supplies the feed.
