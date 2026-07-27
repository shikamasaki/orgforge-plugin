---
description: Drive one work cycle for a department — select from its backlog by situated attention, delegate the selected items to subordinates in parallel (one Task each, if the split is genuine), then record completion. This is the PM loop; it ACTS. Pair with /org-tick (read-only health) and /org-discover (backlog generation).
argument-hint: "<role> [wip-limit] [mandate-floor]"
allowed-tools: Bash(python3 *), Task
---

Drive one **work cycle** for role **$1** against its ledger — the PM loop that turns a backlog into
delegated, recorded work. Read-only health is `/org-tick`; this command acts.

Ledger root: `${ORG_LEDGER_ROOT}` (must be set).

**Output language:** read `output_language` from `constitution.yaml` (default `en`) and write **all
human-facing text** — Issue titles/bodies, work-log comments, progress notes, escalations — in that
language, so the CEO reads the org in their own language. Code, ledger event *classes*, and file paths
stay canonical (English identifiers).

!`echo "Org output language: $(python3 -c "import yaml,os; print((yaml.safe_load(open(os.environ.get('ORG_CONSTITUTION', os.path.join(os.path.dirname(os.environ['ORG_LEDGER_ROOT'].rstrip('/')),'constitution.yaml')))) or {}).get('output_language','en'))" 2>/dev/null || echo en)"`

## 1. Select what to work on next (situated attention over the backlog)

The backlog is one queue holding both **mandate** (top-down) and **self** (self-raised) items;
attention.py prioritizes them on one footing, floors an in-zone mandate (zone of acceptance), and
picks a prefix within the WIP limit.

!`python3 "${CLAUDE_PLUGIN_ROOT}/tools/attention.py" select "${ORG_LEDGER_ROOT}" --role "$1" --wip-limit ${2:-2} --mandate-floor ${3:-1.0}`

## 1.5 Learn from prior deaths BEFORE delegating — do not repeat a known failure

The org's accumulated failures are its most valuable context (docs/06). Before spawning, read what
already died near this work and what caused it, so a selected item that would repeat a known death is
reshaped or dropped — not re-attempted blindly. This is how accumulated learning lifts output quality
(the org's core purpose); skipping it is how the same mistake gets mass-produced.

!`python3 "${CLAUDE_PLUGIN_ROOT}/tools/ledger.py" view "${ORG_LEDGER_ROOT}" nearby_deaths`
!`python3 "${CLAUDE_PLUGIN_ROOT}/tools/ledger.py" view "${ORG_LEDGER_ROOT}" death_causes`

For each selected item, check it against the deaths above:
- If it matches a **prior death** (same approach that already failed/was refuted/retired), do NOT
  re-attempt it as-is — reshape it to avoid the known cause, or drop it and say why. Carry the relevant
  death cause into the child's seam contract so the worker starts knowing what to avoid.
- If it's genuinely new territory, proceed. Silence here (no relevant deaths) is fine.

## 1.6 Reuse before you rebuild — check the parts inventory

The factory compounds assets; a worker that re-authors from scratch what the org already built wastes
the multiplier and diverges from a working part (the divergence sensor only catches that *after* the
fact). Before delegating an item that needs a component, check what already exists:

!`python3 "${CLAUDE_PLUGIN_ROOT}/tools/ledger.py" view "${ORG_LEDGER_ROOT}" reusable_modules`
!`python3 "${CLAUDE_PLUGIN_ROOT}/tools/ledger.py" view "${ORG_LEDGER_ROOT}" parts_inventory`

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

## 3. Record work as you go — so nothing is lost to a context wipe

The backlog is the org's memory. Work that lives only in this session's context is **gone** on `/clear`
or a crash (docs/01 R−1: the org acts only on what is written). So a cycle records itself at three
points, keyed by `candidate_id`:

1. **On starting an item** — append `cycle_started {role, candidate_id, pack_manifest_id}`. This marks
   the item in-flight and ties every later record to it.
2. **At each milestone** (and before you might stop — end of a phase, hitting a blocker, low on budget)
   — append `progress_recorded {role, candidate_id, fraction, phase, done_so_far, next_step, blocked_by,
   artifacts}`. `next_step` is the load-bearing field: it is what a fresh session resumes from.
3. **On finishing** — append `cycle_completed {role, candidate_id, outputs, reused, ...}` so the item
   drains from the backlog, and record in `reused` which existing modules/parts this cycle pulled from
   (empty if it authored everything) — so reuse is a visible, auditable fact, not an invisible discipline.
4. **Grow the SSoT/domain model IN THE SAME cycle** — if this work established or changed a domain rule,
   a boundary, or a naming/convention (ubiquitous language), record it NOW as a convention, not as a
   deferred separate task (a separate task gets postponed and the context base rots — the co-commit
   discipline). This is how the org's inferability rises over time and how the same clarity is amplified
   next cycle instead of the same ambiguity. A convention is proposed here and adopted by a checker
   (never self-adopted):

!`echo 'Record the cycle (never fabricate completion): python3 "'"${CLAUDE_PLUGIN_ROOT}"'/tools/ledger.py" append "'"${ORG_LEDGER_ROOT}"'" --actor "'"$1"'" --class cycle_started|progress_recorded|cycle_completed --payload {role,candidate_id,...}. AND, in the same cycle, if a domain rule/boundary/naming was settled: python3 "'"${CLAUDE_PLUGIN_ROOT}"'/tools/conventions.py" adopt "'"${ORG_CONVENTIONS_ROOT:-$ORG_LEDGER_ROOT}"'" --scope <area> --choice "<the settled rule>" --owner "'"$1"'" --by checker. Checkpoint BEFORE you risk stopping.'`

### 3b. Project each milestone onto the GitHub Issue (work-log — the user's requirement)

If this task is being run through a GitHub Issue (the web harness, or a local session working an Issue —
`ORG_GITHUB_REPO` set and the Issue number known from the claim), **mirror each of the three milestones
above onto the Issue as a work-log comment, at the same moment you append it to the ledger**, so the
human watching from a phone sees progress accrue without opening the ledger. The ledger stays the SSoT;
the comment is its projection. Pass the ledger event's `id` as `--event-id` so a replayed/retried cycle
logs the milestone **once** (the comment carries a hidden `orgforge:event:<id>` marker and `log` no-ops
on a duplicate — docs/11 §0 reproducibility applied to the projection too):

!`echo 'On each milestone, also project it to the Issue: python3 "'"${CLAUDE_PLUGIN_ROOT}"'/tools/github_sync.py" log --repo "$ORG_GITHUB_REPO" --issue <N> --event cycle_started|progress_recorded|phase_admitted|cycle_completed [--phase <sdlc-phase>] [--detail "<next_step or done_so_far>"] --event-id <the ledger event id>. Skip silently if ORG_GITHUB_REPO is unset (a ledger-only run).'`

## Discipline — work only from the backlog

**Always work an item that is on the backlog.** If you are about to implement something that is not a
`candidate_submitted` item, submit it first (as `/org-discover` does) — otherwise the work is invisible
to the org and unrecoverable after a wipe. Pull from the backlog, record as you go; do not do untracked
work on the side.

When you submit such an item, derive its `candidate_id` DETERMINISTICALLY (do not invent a free-form id)
so the backlog stays reproducible (docs/11 §0) — the same gap must always produce the same id:

!`echo 'candidate_id := python3 -c '"'"'import hashlib,sys,re; role,contract,gap=sys.argv[1],sys.argv[2],sys.argv[3]; norm=re.sub(r"\s+"," ",gap.strip().lower()); print("cand-"+hashlib.sha256(("\x1f".join([role,contract,norm])).encode()).hexdigest()[:12])'"'"' "'"$1"'" "<objective>" "<one-line gap>"'`

then append with that id as BOTH `candidate_id` and `--natural-key` (idempotent under replay):

!`echo 'python3 "'"${CLAUDE_PLUGIN_ROOT}"'/tools/ledger.py" append "'"${ORG_LEDGER_ROOT}"'" --actor "'"$1"'" --class candidate_submitted --natural-key "<derived-cand-id>" --payload {"maker":"'"$1"'","candidate_id":"<derived-cand-id>","contract_ref":"<objective>","source":"self","evidence":[<gap-refs>]}'`

## Discipline

- **Parallelism is a judgment, not a mandate.** Fan out genuinely-parallel work; keep coupled work
  single-threaded. Over-fanning inflates your own conformance-review span toward rubber-stamping
  (docs/04 §1) — the opposite of the goal.
- If attention.py printed **ESCALATE** (backlog cannot serve the top objective, or WIP saturated by
  stalled work), do NOT spawn to paper over it — surface the escalation; it is coverage/stall, not a
  work item.
- Take no asset-touching action here beyond spawning the delegated cycles and recording their results.
