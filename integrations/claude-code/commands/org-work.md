---
description: Drive one work cycle for a department — select from its backlog by situated attention, delegate the selected items to subordinates in parallel (one Task each, if the split is genuine), then record completion. This is the PM loop; it ACTS. Pair with /org-tick (read-only health) and /org-discover (backlog generation).
argument-hint: "<role> [wip-limit] [mandate-floor]"
allowed-tools: Bash(*), Read, Write, Edit, Glob, Grep, Agent, Task, WebFetch, WebSearch
---

Drive one **work cycle** for role **$1** against its ledger — the PM loop that turns a backlog into
delegated, recorded work. Read-only health is `/org-tick`; this command acts.

The ledger root is **discovered** (`tools/discover.py`) — no environment variable to set.

**Output language:** read `output_language` from `constitution.yaml` (default `en`) and write **all
human-facing text** — Issue titles/bodies, work-log comments, progress notes, escalations — in that
language, so the CEO reads the org in their own language. Code, ledger event *classes*, and file paths
stay canonical (English identifiers).

!`python3 -c "import sys,yaml; sys.path.insert(0,'${CLAUDE_PLUGIN_ROOT}/tools'); import discover; c=discover.constitution(); print('Org output language:', (yaml.safe_load(open(c)) or {}).get('output_language','en') if c else 'en')" 2>/dev/null || echo "Org output language: en"`

## 1. Select what to work on next (situated attention over the backlog)

The backlog is one queue holding both **mandate** (top-down) and **self** (self-raised) items;
attention.py prioritizes them on one footing, floors an in-zone mandate (zone of acceptance), and
picks a prefix within the WIP limit.

!`python3 "${CLAUDE_PLUGIN_ROOT}/tools/attention.py" select --role "$1" --wip-limit ${2:-2} --mandate-floor ${3:-1.0}`

## 1.5 Learn from prior deaths BEFORE delegating — do not repeat a known failure

The org's accumulated failures are its most valuable context (docs/06). Before spawning, read what
already died near this work and what caused it, so a selected item that would repeat a known death is
reshaped or dropped — not re-attempted blindly. This is how accumulated learning lifts output quality
(the org's core purpose); skipping it is how the same mistake gets mass-produced.

!`python3 "${CLAUDE_PLUGIN_ROOT}/tools/ledger.py" view nearby_deaths`
!`python3 "${CLAUDE_PLUGIN_ROOT}/tools/ledger.py" view death_causes`

For each selected item, check it against the deaths above:
- If it matches a **prior death** (same approach that already failed/was refuted/retired), do NOT
  re-attempt it as-is — reshape it to avoid the known cause, or drop it and say why. Carry the relevant
  death cause into the child's seam contract so the worker starts knowing what to avoid.
- If it's genuinely new territory, proceed. Silence here (no relevant deaths) is fine.

## 1.6 Reuse before you rebuild — check the parts inventory

The factory compounds assets; a worker that re-authors from scratch what the org already built wastes
the multiplier and diverges from a working part (the divergence sensor only catches that *after* the
fact). Before delegating an item that needs a component, check what already exists:

!`python3 "${CLAUDE_PLUGIN_ROOT}/tools/ledger.py" view reusable_modules`
!`python3 "${CLAUDE_PLUGIN_ROOT}/tools/ledger.py" view parts_inventory`

For each selected item:
- If a reusable module/part already covers part of it, the child's seam contract must say **"reuse
  `<module>`; do not rebuild it"** — the worker imports the existing asset and only writes the novel
  delta. Record in the child's `inputs` which parts it reuses.
- If nothing fits, author it — but if the new part is itself reusable, that is what enters
  `reusable_modules` on completion, seeding the next cycle. Building the base is not enough; the base
  must be *pulled from* (SPLE proactive reuse), or it's a library nobody imports.

## 2. Delegate the selected items — in parallel, but only where the split is genuine

Read the `selected[]` above. Then apply the **decomposition doctrine (docs/03)** before spawning:

- **One `Task` per selected item that is a genuinely independent unit.** Emit them in a SINGLE message
  (multiple Task calls) so they run concurrently — this is the parallel fan-out. Do NOT call them one
  at a time.
- **Do not fan out reciprocally-coupled work** (docs/03 §6.2, docs/09 §granularity): if two selected
  items must constantly adjust to each other, keep them in one Task. Fineness follows *independence*,
  bounded by coordination cost — not a target depth.
- **Each child Task MUST carry a seam contract** (its slice, inputs, outputs, and the files it `owns`
  vs `must-not-touch`) — the spawn guardrail blocks a contract-less spawn, and the `owns`/`forbid`
  fields are what stop two siblings from redoing each other's work (docs/06 §2.1.1, docs/04 §6).
- **Route by domain, don't swallow it** (docs/03 §3): an item whose domain belongs to a subordinate
  role goes to that role, so its knowledge accrues to that role's doctrine — never absorbed here.
- If an item is your OWN-domain tightly-coupled work, implementing it yourself is fine (docs/09).
- **Each child works on its OWN feature branch off `develop`** (the branch policy, docs/11 §4c): the
  child opens `feat/issue-<N>-<slug>` — deterministic, so siblings never collide. Get the exact name
  from `github_sync branch --repo "$ORG_GITHUB_REPO" --issue <N>` (or `--create` to cut it). A task's
  work lands on its branch; it does NOT commit to `develop`/`main` directly.

### 2b. `org_cycle` runs the plumbing — do not type the events by hand

The SDLC phase gates (docs/11 §2) take effect **only once the events are actually typed**. That
sequence (claim → spec_delegated → phase_started → cycle_started → log to the Issue → stage) is
**plumbing whose order and actor are already settled**, not a judgment. Typed by hand it comes to
eleven commands per two Issues, around ninety across eighteen, and one mistake breaks the ledger's
consistency (found in the field).

**Type one command per Issue you start:**

```
python3 "${CLAUDE_PLUGIN_ROOT}/tools/org_cycle.py" begin \
  --role $1 --issue <task Issue number> --agent <the role that actually builds>
```

This runs the seven steps in the right order with the right actor. **`parent` resolves from the
Issue automatically** — a human used to pick "#7's parent is #1" out by eye and type it in, while
`create` writes `Parent: #N` into the body and it can simply be read. As long as it is typed by
hand one gets mistaken for another, and the implementation of parent inheritance (docs/11 §2) does
nothing. `candidate_id` is read from the Issue's trailer too.

To look before typing, replace `begin` with `plan` — it **runs nothing** and prints only the
sequence of events.

**`begin` prepares a worktree too (docs/11 §4c).** It cuts a working tree dedicated to that Issue
at `.orgforge/wt/issue-<N>/`. Running several makers over one tree in a parallel fan-out puts
**one Issue's commits on another Issue's branch** — an accident that actually happened, and since
`git checkout` switches the whole tree, it is certain to recur for as long as parallel work shares
one tree. A design that assumes "judge correctly every time" breaks, so they are separated
physically. Have makers work in `.orgforge/wt/issue-<N>/`.

Running a single item sequentially, `--no-worktree` skips it. **Do not use it when running in
parallel.**

**`begin` and `plan` also print the pre-start checks.** Whether a dependency is in rework, and
whether anything is still waiting on a human (needs-human). **They do not stop you** — the
judgment is yours, but there is nothing to judge from without the material. What is built on a
broken premise ends up on the side the gate rejects later. `--no-check` skips it.

### 2c. See the whole picture of one Issue — `show`

```
python3 "${CLAUDE_PLUGIN_ROOT}/tools/org_cycle.py" show --issue <N>
```

The implementation commits, the worktree, **the judgment history (who judged what in which round,
marked corrected / backfilled)**, what it now waits on, and the next move, all at a glance. It
stops an Issue three rounds in from becoming "which round's judgment am I even reading". In the
field both the missing refutation on #8 and the missing reject on #11 would have been found
immediately from this vantage point.

### 2d. Void a mistaken record or a verification probe with `correction`

The ledger is append-only, so the past cannot be erased. **A free-text note is unreadable by
machine**, and neither status nor learning can exclude it (in the field four verification probes
appeared on the board as real judgments):

```
python3 "${CLAUDE_PLUGIN_ROOT}/tools/ledger.py" append --actor <role> --class correction \
  --payload '{"corrects":[<seq>,...],"kind":"probe|mistake|backfill|superseded",
              "reason":"<why it is void>","corrected_by":"<by whom>"}'
```

`probe` (for verification, not a real judgment) and `mistake` (a mis-entry) are excluded from the
counts. `backfill` is "a real judgment written afterwards" and is not excluded; `superseded` is
handled by resolving to the latest judgment.

**Where it stopped, nothing beyond that was typed.** A refusal from the ledger means an order
violation: satisfy the precondition and run it again. Each event is idempotent by natural key, so
**re-running is safe** (what is done becomes a no-op).

> **This is not forced delegation.** What was automated is only "plumbing whose order and actor
> are already settled"; **what to choose, whom to delegate to, and whether to admit are not**
> (docs/03 §6.5 — forced delegation is a design error, a forced invariant is right). The judgment
> stays yours.

## 3. Record work as you go — so nothing is lost to a context wipe

The backlog is the org's memory. Work that lives only in this session's context is **gone** on `/clear`
or a crash (docs/01 R−1: the org acts only on what is written).

**One command at completion too:**

```
python3 "${CLAUDE_PLUGIN_ROOT}/tools/org_cycle.py" complete \
  --role $1 --issue <N> --agent <role> --outputs "<what was built>" \
  --command "<the DoD command (verbatim)>" --result "<its real output, failures included>" \
  [--files "<the files changed>"] \
  (--domain-model-updated "<a reference to the domain rule established>" \
   | --domain-model-none "<the reason nothing was established>")
```

**Where public surface has grown, you cannot complete until you declare it.** If a SECURITY
DEFINER function, a grant, an RLS policy, an endpoint, or an export has newly appeared, it lists
them and stops (in order of danger; tests, type definitions, and scripts are excluded, and the
worktree's uncommitted content is read too). Declare it with
`--new-surface "<surface>: <who can call it / what it can do>"`, or deny it with
`--new-surface-none "<reason>"`. **An authorization hole is born where "one function was
added"** — `join_group` in the field was exactly that: nothing made it mechanically visible to
anyone that one more SECURITY DEFINER had appeared.

`--command` and `--result` are **required**. The `log` side refuses a paraphrase of "it passed".
It is checked for the same reason `decide` checks `--why` — in the field the checked `decide` ran
3,500-5,900 characters and the unchecked `log` 276-473, producing the asymmetry where **only the
judgments in an Issue were auditable**. A human keeps a prose instruction; a tool keeps a required
argument.

Choosing `--domain-model-none` lists the public types and exports that grew in that cycle and asks
back "are these not the domain's vocabulary?" (it does not judge; it only stops things walking
past).
At completion it also cleans up the worktree `begin` created (leaving it with a warning where
there are uncommitted changes).

**Leave a learning that holds for the next cycle with `--learned`.** It is proposed to doctrine
and, once the gate admits it, enters the brain of whoever takes the next Issue (`handoff.py`
distributes it per role). The admit is the gate's job — nobody canonises their own learning. In
the field doctrine stayed empty while **the same failure repeated three times** ("a property test
is meaningless unless it verifies at the place that breaks"). docs/06 writes that accumulated
failure is the most valuable context there is, yet the mouth for accumulating it was not connected
to the cycle.

### 3a-2b. Leave a record when you touch a production asset — `touched`

```
python3 "${CLAUDE_PLUGIN_ROOT}/tools/org_cycle.py" touched \
  --target "supabase:<project>" --op revoke --name "<the subject>" \
  --by <role> --authority "<under whose authority>" --issue <N> \
  [--reversible --rollback "<how to undo it>"]
```

`exposure_budget_checked` counts local file operations but counts neither DDL against a remote DB
nor a privilege change in production. **The latter is what is actually dangerous**, and it costs
more to undo. In the field two migrations and a privilege revoke went into the production DB while
nothing was left in the ledger, so "under whose authority did that revoke go in" could not be
traced. `--authority` is the field for exactly that.

### 3a-3. Sweep up what has accumulated — `gc`

```
python3 "${CLAUDE_PLUGIN_ROOT}/tools/org_cycle.py" gc
```

It removes only integrated worktrees. **Anything unintegrated or uncommitted is left**  (whether
something would be missed is not the plumbing's call). Verification worktrees created outside
`.orgforge/wt/` (in a scratchpad and the like) are picked up too, as long as git knows about them
— reading only where the plumbing creates them leaves orphans forever.

### 3b-3. Check that the report you got back has the shape of a deliverable — `intake`

**Put a subagent's report through this before reading it as a judgment.**

```
python3 "${CLAUDE_PLUGIN_ROOT}/tools/org_cycle.py" intake --issue <N> \
  --role gate|skeptic|maker --report "<the report you got back>"
```

In the field **a turn ended mid-work** three times in one night. `status` returned completed and
`result` held a single declarative sentence like "Now the key attack:". Resuming with
`SendMessage` ran the rest to completion, so **the agent did not die — the turn ended before the
report took the shape of a deliverable**.

**The dangerous shape is the one you cannot notice.** "Now the key attack:" is visibly missing a
verdict, but **a report cut off at "MUST 2 is defended" could be read as a verdict and admitted**.
The "stating something unverified as though it were verified" this org has detected again and
again arrives through the path of a truncated report.

It reads only the elements each role must carry (skeptic/gate → a verdict and a trace of what was
run; maker → commits and the measured output of the DoD). **It reads neither the content nor the
soundness of the verdict** — judging is the role's work. On exit 10, prompt for the rest with
`SendMessage` and **do not read that report as a judgment**.

### 3a-3b. Record a rework once you commission it — `rework`

```
python3 "${CLAUDE_PLUGIN_ROOT}/tools/org_cycle.py" rework --issue <N> \
  --after reject|refuted --by <your role> --reason "<what the maker is to fix, in one line>" \
  --root <a DEATH_ROOTS class> --round <which round>
```

`--root` is required. Do not omit the root-cause-of-death class (`placebo_test`, `contract_gap`,
`context_stale`, `tool_boundary`, `identity`, `dependency`, `resource`, `other`) — record it in a
form recurrence learning can use.

**Without typing this, `show`'s rework warning goes silent** — the warning counts
`rework_requested` in the ledger, and with no record it never reaches the threshold. In the field
there were no records against **twenty-eight** rejects and refutations (one Issue had four rejects
and zero records), and the warning stayed quiet. **A tool does not count what it cannot count.**

Commissioning runs "receive the judgment → verify → `decide` → **commission** → record", and the
record gets washed away when the notification from the commissioned subagent arrives. Where
`verify` returns reject/refuted, this command is printed in **the same place** as the judgment's
record, so you can commission with the recording command right in front of you.

### 3a-4. Record a judgment already made, retroactively — `record`

```
python3 "${CLAUDE_PLUGIN_ROOT}/tools/org_cycle.py" record --issue <N> \
  --event integration_admitted --verdict pass --by <role> \
  --why "<what was read, and what decided it>"
```

The ledger is append-only, so the past is not rewritten. It carries `backfilled: true` and stays
distinguishable from a record made at the time.
In the field the finding "eight of the ten failures after the merge were false positives from the
worktree scan; #7 had zero defects" was left nowhere — **that separation is exactly what one most
wants later**, so a way back is left open.

### 3a-2. Open the PR — `handback`

```
python3 "${CLAUDE_PLUGIN_ROOT}/tools/org_cycle.py" handback --issue <N> \
  --summary "<what was built>" --result "<the DoD's real output>" \
  [--files "<the files changed>"]
```

It pushes the feature branch, opens a PR based on `develop`, and links it to the Issue by putting
**`Closes #N`** in the body. In the field no step for opening a PR existed anywhere, and the
result was **zero PRs**, direct integration by `git merge`, and integrated Issues left OPEN. The
premise of operating on GitHub did not hold. It does not decide whether to merge — the plumbing
ends at opening the PR.

`domain_model` is **required** (docs/11 §4d). The ledger refuses it, so it cannot be omitted — if
the cycle did nothing to the domain model, write why (it becomes a claim the skeptic can refute).

**Interim progress** (the end of a phase, a block, before running out of budget) is noted with
`github_sync log`:

### 3a. The GitHub Issue is the MAIN work-log — so work isn't session- or terminal-bound

When the org is steered through GitHub (`ORG_GITHUB_REPO` set — the default for any laptop-free /
multi-terminal / web-harness run), **the task Issue is the PRIMARY surface for the spec and the
work-log**, because the ledger is a local file (`.orgforge/ledger/`) that a phone or a different machine
or a fresh web session cannot see — it is terminal-bound. The Issue is not: anyone, anywhere, picks up
the work from it. So the primacy is **Issue-first**:

- **The spec lives in the Issue body** (the SPEC structure — already how a task is created).
- **The work-log lives as Issue comments.** At each of the three milestones, post the comment to the
  Issue **first** — that is the record a human and the next session read to know where the work stands.
- **The ledger gets the RECEIPT** of the same milestone — for audit, `requires_prior` enforcement, and
  crash-safe resume — but it is the *secondary* record here, not the place a human watches. (SSoT is
  unchanged: neither Issue nor ledger is the SSoT — the code + domain model the work produces is.)

Post the milestone to the Issue, keyed by the same natural id so a replay logs it **once** (the comment
carries a hidden `orgforge:event:<id>` marker; `log` no-ops on a duplicate — docs/11 §0):

!`echo 'Log the milestone to the Issue (the main work-log): python3 "'"${CLAUDE_PLUGIN_ROOT}"'/tools/github_sync.py" log --repo "$ORG_GITHUB_REPO" --issue <N> --event cycle_started|progress_recorded|phase_admitted|cycle_completed [--phase <sdlc-phase>] [--detail "<what happened>"] [--command "<the exact command run>"] [--result "<its real output, failures included>"] [--files "<files changed>"] [--next-step "<what a fresh session resumes from>"] [--blocked-by "<blocker>"] --event-id <id>. THEN write the ledger receipt (audit/resume). A ledger-only run (no ORG_GITHUB_REPO) keeps the work-log in the ledger instead.'`

### 3b. Log at MAXIMUM granularity — no human reads the diff (docs/11 §4f)

Human diff review is **retired**: nobody reads the change before it merges. That makes the Issue the
org's audit record, not merely a status board, and it raises the logging bar sharply. `"progress
recorded"` satisfies the letter of logging and records nothing recoverable — that is the failure mode
to design against.

Log at **every step that changed the world or changed the plan**, not only at the three milestones, and
record what actually happened:

- **the exact command**, verbatim and re-runnable (`--command`) — never "ran the tests"
- **what it returned** (`--result`), the real output **including failures**. A log of only successes is
  a fiction, and the failed attempt is usually the most informative entry on the Issue.
- **files changed** (`--files`), the **next step** (`--next-step`), the **blocker** (`--blocked-by`)
- **course changes with their cause** — the approach abandoned and what made it wrong. This is what
  stops the next maker re-deriving the same dead end (it feeds `nearby_deaths`).

The bar: **a stranger reading only this Issue can reconstruct what was built, what was tried and
abandoned, what was run, what came back, and why it merged** — without the ledger, without the
transcript, without asking anyone. If they cannot, the log is too thin regardless of its volume.

### 3b-2. `org_cycle verify` assembles the material for calling gate / skeptic too

After `complete` comes the admission, but **do not write the verification procedure out afresh
each time**. Each writing shifts the gate's strictness, so eighteen Issues means eighteen
standards. The standard should have one source, `agents/gate.md`, and a state where that goes
unused while a human writes the procedure is the same as having no standard at all.

```
python3 "${CLAUDE_PLUGIN_ROOT}/tools/org_cycle.py" verify --issue <N> --role gate
# once the gate admits
python3 "${CLAUDE_PLUGIN_ROOT}/tools/org_cycle.py" verify --issue <N> --role skeptic
```

Hand the output to the subagent. **Paste it into the body, or write it to a file and reference
that** — where the body carries no seam contract, the seam guard **reads the file the prompt
points at itself** and verifies it (limited to under the org root and the temporary directory).
It used to accept the body only, which meant pasting a 264-line contract every time and crowding
the maker's context. "The content behind a reference cannot be guaranteed" holds only while the
guard does not read it; reading it makes it guaranteeable. What is assembled is the following, and
**all of it is plumbing**:

- the **seam contract**, by calling `handoff.py` internally (six hand-typed arguments disappear)
- **the charter in `agents/<role>.md`** = injecting the verification checklist (← this is the
  crux: the standard is pinned to one place)
- embedding the Issue's **SPEC / MUSTs** (the very thing being verified)
- **the judgment history** (which round, and the full text of every prior reason) — without it the
  gate **treats every round as the first**. The count takes the larger of the ledger and the
  Issue (so one side of a double record going missing never understates it)
- **stating what to return** (verdict / why / evidence / standard / risk). **No recording command
  is included** — a subagent is given neither `ORG_GITHUB_REPO` nor the ledger path, so including
  one puts the instructions at odds with the permissions (in the field this happened seven times:
  a judgment was produced, then "I leave the recording to the supervisor", and once the judgment
  came close to being lost). The command the supervisor types goes to **stderr**
- the skeptic is automatically handed **what the gate already looked at** and **the areas the gate
  itself wrote it had not fired at this time**. Without them the same mutations get repeated to no
  purpose, and the unfired areas stay unfired by anyone (in the field a real bug came out of an
  area the gate had written it "had not hit once").
  It only carries them: the plumbing decides neither their soundness nor what to try next.

> **`verify` holds no judging logic whatsoever.** The verdict, the why, the risk, and which
> mutation to try are decided by gate / skeptic. **The moment a tool decides the verdict the gate
> becomes a formality**, so that line is not crossed (docs/03 §6.5 — a forced invariant is right;
> a forced judgment is the disappearance of judgment).

### 3c. Record every JUDGMENT with its reasoning — a verdict alone is a stamp

With no human approving, an unrecorded judgment is indistinguishable from no judgment. So every verdict
**double-writes**: the ledger takes the receipt (tamper-evident), the Issue takes the reasoning (where it
can actually be inferred later). This applies to the gate's admission, the skeptic's refutation attempt,
each `phase_admitted`, the integrate verdict, and any consequential design/scope/trade-off call:

!`echo 'Per judgment: python3 "'"${CLAUDE_PLUGIN_ROOT}"'/tools/github_sync.py" decide --repo "$ORG_GITHUB_REPO" --issue <N> --event admission_decided|refutation_attempted|phase_admitted|integration_admitted|design_decided|tradeoff_decided|rework_requested --verdict <admit|reject|pass|rework|survives|refuted> --why "<the REASONING: what was weighed, what decided it>" --by <role> [--phase <p>] [--root <a DEATH_ROOTS class>] [--evidence "<command output / CI run / repro_lint verdict>"] [--alternatives "<what was rejected and why>"] [--standard "<the bar applied>"] [--risk "<a known risk knowingly accepted>"] --event-id <ledger event id>'`

Require `--root` on `rework_requested` and `refutation_attempted`, so an unclassified cause of
death never flows through in a form nobody can reconstruct later.

`decide` **writes to both the Issue and the ledger in one command** (0.21.0). It used to print a
template for a human to type `ledger append` from, and in the field one side went missing three
times. The ledger comes first — if a control refuses, it stops before any outward record is
created on the Issue (exit 4).

`decide` **rejects a `--why` that merely restates the verdict** — the degradation back into a rubber
stamp is closed at the tool. Record the `--risk` honestly: a gate that admits despite a known hole must
say so, or the hole becomes a surprise instead of a decision.

## 4. Fan the work back in — integrate on `develop` before it's "done"

Fanning out (§2) is only half the loop; the parallel siblings must **come back together and be tested
as a whole** before any of them deploys (docs/11 §4c — whatever you separate, you pay to reintegrate).
As the supervising manager you own this integrate phase (your A3, extended to cross-deliverable):

- Each child's per-unit `test` passing (its own suite green on its feature branch) admits it to **open a
  PR against `develop`** — not `main`. The PR is created by `org_cycle.py handback --issue <N>`
  (do not type `gh pr create` by hand — in the field that left zero PRs).
- The merge, the post-integration test, and the record are `org_cycle.py integrate --issue <N>`:

```
python3 "${CLAUDE_PLUGIN_ROOT}/tools/org_cycle.py" integrate --issue <N> [--test "npm test"]
```

  With `--plan` it **runs nothing** and shows first what would be integrated (the files changed,
  the commit count) and **whether another worktree running in parallel touches the same files**.
  For an integration that touches a CI workflow it also prints **the job structure and whether an
  `if:` is present** — a step that lands in a conditional job **never runs once**, even with valid
  YAML and green tests (it happens when a merge resolves the CI file by union). It does not read
  the YAML's meaning, so confirming where the step landed is the supervisor's job. In the field
  ten failures after integrating #7 cost time to separate out (eight were false positives from the
  worktree scan) — a conflict is cheaper found before integration than after.

  **It stops unless the gate's admit and the skeptic's survives are both in the ledger**
  (exit 4).

  **You cannot put work into develop directly with `git merge`.** PreToolUse holds a `merge`,
  `rebase`, or `cherry-pick` on a protected branch (`develop`/`main`/`master`) — `integrate`
  checks nothing unless it is called, so **the hook is the only thing that can detect it not being
  called**. For the same reason it holds `gh issue create|close|edit` (bypassing the organ leaves
  out `dept`, `objective`, `parent`, and the idempotency key, and `cycle_completed`'s
  `domain_model` goes missing).
  When something breaks and you are stuck, `ORG_ALLOW_MANUAL_MERGE=1` /
  `ORG_ALLOW_MANUAL_GH=1` let it through.
  A one-off GH bypass is declared in the same Bash call, as
  `ORG_ALLOW_MANUAL_GH=1 gh issue …` (PreToolUse runs before Bash does).
  Run exactly one Issue mutation per call — declare several separately, so `bypass_declared` and
  the mutation are recorded one to one.
  **The fact that it was let through stays in the ledger as `bypass_declared`.** A comment on the
  Issue with nothing in the ledger is "not recorded" — in the field work was integrated with not
  one refutation_attempted in the ledger, and no `integration_admitted` was recorded either. One
  side of the double record going missing is the failure that actually happens, so the ledger is
  what is read here. It does not decide whether to merge (only reconciles the preconditions).
- Then run the **combined** suite on `develop`: the siblings must build and pass **together**, not just
  each alone. Green CI on `develop` is the integrate gate (`integration_admitted`) — the machine form.
- Only an integrated, green `develop` is **"done"**: nobody reads the diff (docs/11 §4f), so the
  assembled green `develop` *is* the verdict. A pile of per-task PRs against `main` that were never
  assembled is NOT done.
- Record `integration_admitted` (the receipt) **and post the judgment with its reasoning** to the
  objective Issue (`github_sync decide --repo "$ORG_GITHUB_REPO" --issue <objective#> --event integration_admitted --verdict pass|fail --why …
  --evidence "<the combined CI run>"`), so the fan-in has an account and not just a timestamp. Promotion `develop → main` (deploy, docs/11 §3) is a later, separate gate.

!`echo 'Integrate: for each green child, python3 "'"${CLAUDE_PLUGIN_ROOT}"'/tools/github_sync.py" branch --repo "$ORG_GITHUB_REPO" --issue <N> gives its feature branch; merge them to develop, run the combined suite on develop (green = integration_admitted), then log it to the objective Issue. Skip if this org has a single deliverable (nothing to integrate).'`

## Discipline — work only from the backlog

**Always work an item that is on the backlog.** If you are about to implement something that is not a
`candidate_submitted` item, submit it first (as `/org-discover` does) — otherwise the work is invisible
to the org and unrecoverable after a wipe. Pull from the backlog, record as you go; do not do untracked
work on the side.

When you submit such an item, derive its `candidate_id` DETERMINISTICALLY (do not invent a free-form id)
so the backlog stays reproducible (docs/11 §0) — the same gap must always produce the same id:

!`echo 'candidate_id := python3 "'"${CLAUDE_PLUGIN_ROOT}"'/tools/github_sync.py" candidate-id --role "'"$1"'" --contract "<objective-id>" --gap "<one-line gap>"'`

**Never hand-compute this or paste a shell one-liner.** The fields are joined on a unit separator that a
shell `echo` silently eats; without it the id degrades to bare concatenation and different items collide
onto one id — whereupon the second item's ledger append is swallowed as an idempotent "replay" and the
work never enters the backlog at all.

then append with that id as BOTH `candidate_id` and `--natural-key` (idempotent under replay):

!`echo 'python3 "'"${CLAUDE_PLUGIN_ROOT}"'/tools/ledger.py" append --actor "'"$1"'" --class candidate_submitted --natural-key "<derived-cand-id>" --payload '"'"'{"maker":"'"$1"'","candidate_id":"<derived-cand-id>","contract_ref":"<objective>","source":"self","evidence":[<gap-refs>]}'"'"''`

## Discipline — recording and delegation

- **Parallelism is a judgment, not a mandate.** Fan out genuinely-parallel work; keep coupled work
  single-threaded. Over-fanning inflates your own conformance-review span toward rubber-stamping
  (docs/04 §1) — the opposite of the goal.
- If attention.py printed **ESCALATE** (backlog cannot serve the top objective, or WIP saturated by
  stalled work), do NOT spawn to paper over it — surface the escalation; it is coverage/stall, not a
  work item.
- Take no asset-touching action here beyond spawning the delegated cycles and recording their results.
