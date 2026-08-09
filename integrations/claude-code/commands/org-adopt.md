---
description: One-command adoption for an existing repository — prepare local orgforge state, read the real code, write the minimal organization and architecture, record remaining work and the current baseline, then verify readiness. No prior /org-init required.
argument-hint: "[the remaining requirements, or a path to a brief]"
allowed-tools: Bash(*), Read, Write, Edit, Glob, Grep, Agent, Task, WebFetch, WebSearch
---

Bring **a repository that already has code** under orgforge in a single command.
The input is not an RFP but **the code that actually exists**.

This command does not hand adoption off to another command partway. Preparing local state,
reading the current state, the minimal chart, the architecture, the remaining-work manifest, the
baseline, and the doctor all complete within the same invocation.

**What ordinary adoption does not do:** network access, creating GitHub Issues, creating branches,
daemons, sudo, or configuring credentials. Projecting onto a GitHub backlog is optional after
adoption and is not a condition of adoption succeeding.

Do not use `/org-found` as-is on an existing repository. That command designs "what is going to be
built" and never looks at the directory structure that exists. The result is an `ARCHITECTURE.md`
at odds with the actual code, `owns:` territories pointing at paths that do not exist, and **every
downstream task running on a false map**.

> **Output language:** read `output_language` from `constitution.yaml` and write human-facing text
> in that language.

## 0. Where is this being adopted — confirm before writing

!`python3 "${CLAUDE_PLUGIN_ROOT}/tools/adopt.py" inspect .`

If the above is not the intended repository, stop. A commit count of 0 means a new repository, so
**use `/org-found`** (this command presupposes existing code to read, and there is none).

## 1. Prepare local state safely

Where there is no org, pick `ja` or `en` to match this conversation's human-facing language and run
the following. Existing files are not overwritten, so re-running is safe as a repair.

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/tools/adopt.py" prepare . --language <ja|en>
```

Replace `<ja|en>` with the conversation's language and run it through Bash. If you are working in
English, pick `en` **from the start**. Where a `constitution.yaml` already exists, prepare does not
change its language setting.

### 1a. Update an existing orgforge deployment

If `inspect` reports `existing org: yes`, do not discard the existing ledger and initialise. First
update the schema in the additive direction only, then re-verify the hash chain:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/tools/ledger.py" schema --fix
python3 "${CLAUDE_PLUGIN_ROOT}/tools/ledger.py" schema
python3 "${CLAUDE_PLUGIN_ROOT}/tools/ledger.py" verify
```

Next read the existing `role-settings.yaml`. `defaults.tier: A|B` is retired, so remove it and
state `read/write/edit/grep/run_tests/web_read/network` explicitly for makers. Keep gate and
skeptic read-only, and put `deploy/secrets/asset_movement/external_publish/production_deploy` in no
role's allow list.
Those protections are carried by the host platform's credential custody and approval, not by role
policy. If `constitution.yaml` still carries per-tier containment guarantees for A/B, rewrite them
onto the same host responsibility.

This update does not rewrite existing events. `legacy_unvalidated` stays in the history as it is,
and only new events are validated against the current schema. Confirm that `ledger.jsonl`, `HEAD`,
the event count, and the tip hash are unchanged before and after, then proceed.

## 2. Read the existing code — **describe the current state** rather than design one

This is the essential difference from `/org-found`. The code is authoritative; the documents are
its projection.

First take in the structure (excluding hidden directories and vendor):

!`find . -maxdepth 2 -type d -not -path '*/.*' -not -path '*/node_modules*' -not -path '*/vendor*' 2>/dev/null | head -30`

!`echo "--- language mix ---"; git ls-files 2>/dev/null | sed -n 's/.*\.\([a-z]*\)$/\1/p' | sort | uniq -c | sort -rn | head -8`

Then **read** the following before writing (do not guess):

- **the README** — the author's intent. The primary source for writing down the purpose
- **the dependency manifests** (package.json / pyproject.toml / go.mod …) — the technology choices
  are **already made**
- **the directories as they are** — these become the `owns:` territories. Use the paths that
  exist, not a logically elegant split
- **the tests** — the most honest record of what is guaranteed and what is not
- **the recent commits** (`git log --oneline -30`) — what is moving right now

### 2a. Write `ARCHITECTURE.md` (the fixed name from docs/11 §0a)

Write it as **a description of the current state**, not of how things ought to be. Include:

- the technology stack — what is already adopted (changing it is a separate CEO decision; here,
  stay strictly descriptive)
- the layers and components — mapped onto directories that exist
- the data model — read from the schema, the migrations, and the type definitions
- **the seam contracts** `{deliverable, standard, checker, depends_on}` — this is the one part that
  has to be **decided** anew, since existing code rarely records who guarantees what.
  Take `owns:` from paths that exist, though
- **the known debt** — what works but you want fixed. Writing it here feeds `nearby_deaths` later

### 2b. Write `organization.yaml`

Derive the roles from the directory structure. Split so that the `owns:` sets are disjoint
(overlaps collide under parallel work). If the existing split is already not disjoint, that is
itself a finding — record it as debt in `ARCHITECTURE.md`.

**After writing `organization.yaml`, run this yourself through Bash** (the automatic `!` execution
would check a file that does not exist yet):

```
python3 "${CLAUDE_PLUGIN_ROOT}/tools/org_lint.py" organization.yaml constitution.yaml moves.yaml ledger-schema.yaml sensors.yaml role-settings.yaml
```

Fix until the lint passes. A chart that does not pass is not adopted.

## 3. `coverage-manifest.md` — list **only what is unimplemented**

`/org-found`'s manifest lists "every must-have", but in a mid-life adoption **some of it is
already implemented**. Putting the implemented rows in makes `coverage-check` report a GAP, and
Issues sprout to rebuild things that work.

Decide per requirement, by reading the code:

| state | how the manifest treats it |
|---|---|
| **implemented, tested** | **no row**. Describe it as current state in `ARCHITECTURE.md` instead |
| **implemented, untested** | **a row** (deliverable = "write tests for X"). An untested feature carries no guarantee |
| **partly implemented** | a row. The deliverable states **only the remaining difference** (do not rebuild the whole) |
| **unimplemented** | a row, exactly as in `/org-found` |

Where $ARGUMENTS is given, that is the input for "what is going to be built". Otherwise pick the
unimplemented parts out of the README and the Issues/TODOs.

## 4. Record the current state of the machine bar as a baseline (docs/11 §4e)

**This is the crux of a mid-life adoption.** Existing code will not meet §4e's bar (a complexity
ceiling, closing the type escape hatches, a duplication scan, multi-OS CI) to begin with. It was
written before the bar existed, so of course it does not — that is not a defect but **the starting
point**.

Making everything an error on day one builds a wall of red and, predictably, grows a culture of
silencing it with suppression comments — the worst possible ending, where **the bar is met by
disabling the bar**. So the failures present at adoption are recorded as "known debt", and from
then on **only new failures** are stopped:

!`echo 'measure the current state: python3 "'"${CLAUDE_PLUGIN_ROOT}"'/tools/repro_lint.py" check . --phase deploy'`

!`echo 'record the baseline: python3 "'"${CLAUDE_PLUGIN_ROOT}"'/tools/repro_lint.py" baseline .'`

Once recorded, `.orgforge/repro-baseline.json` exists and every later `repro_lint check`:

- **known debt** → reports it with ▲ but **does not block** (work proceeds)
- **a failure not in the baseline** → **blocks** with ✗ (this change broke it, so stop)
- **debt repaid** → prompts you to "tighten again". Re-running `baseline` protects that item from
  then on

**A baseline is not an indulgence**, nor an exemption without end. It is the list of debt to be
repaid, and material for `/org-discover` to file against itself. Absorbing a new failure into the
baseline is the operation of rewriting "broke it" into "tolerated", and the tool warns about it.

## 5. Leave the adoption decision on record (docs/11 §4f)

Leave a short note in `ARCHITECTURE.md` on why these role boundaries were adopted and which debt
was placed in the baseline. Where a GitHub remote and credentials are available **and only where a
human asked for the Issue projection**, project the same decision onto an objective Issue:

!`echo 'python3 "'"${CLAUDE_PLUGIN_ROOT}"'/tools/github_sync.py" create --kind objective --title "<adopting orgforge into an existing repository>" --body "<a summary of ARCHITECTURE + the known debt + the manifest policy>"'`

!`echo 'python3 "'"${CLAUDE_PLUGIN_ROOT}"'/tools/github_sync.py" decide --issue <N> --event scope_decided --verdict admit --by supervisor --why "<which parts of the existing code were accepted as current state, what went onto the manifest as unimplemented, and the grounds for that>" --evidence "<the repro_lint baseline result, the test run>" --risk "<the known debt accepted>"'`

## 6. One approval, then the doctor

Present the following to the human exactly once and ask for accept/revise:

- the current state as read (the layers, the technology stack, the owns that exist)
- **the known debt** (the content of the repro_lint baseline) and the policy for repaying it
- how many unimplemented items went onto the manifest, and how many implemented ones did not
- the minimal chart and the checker boundaries
- what orgforge enables and what it does not

On revise, fix it within this invocation. After accept:

!`python3 "${CLAUDE_PLUGIN_ROOT}/tools/adopt.py" doctor .`

Fix what is missing until it reports `READY`. Finally report only the following:

- `ADOPTED`
- how long the setup took
- the files created
- enabled: workflow order / maker-checker separation / evidence ledger / human-held irreversible actions
- not enabled: hostile-process containment / credential isolation / immutable storage
- that the next ordinary piece of work can be commissioned as-is

`/org-decompose` is an optional command, only for expanding a large existing backlog into GitHub
Issues; do not require a human to run it in order to complete adoption.

## Discipline

- **The code is authoritative; the documents are its projection.** An `ARCHITECTURE.md` at odds
  with the current state is worse than none (a false map)
- **Do not rebuild what works.** What is implemented does not go on the manifest
- **Do not hide debt.** A baseline is a tool for "record it and repay it", not for "pretend it was
  never seen"
- **Do not design; describe.** Where you want something changed, record it as debt and ask for the
  CEO's decision
