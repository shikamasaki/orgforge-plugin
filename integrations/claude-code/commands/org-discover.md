---
description: Generate self-raised backlog items for a department from its own aspiration gaps (problemistic search), and append them to the SAME backlog as source=self. This is how a department improves itself unprompted; it feeds /org-work, it does not execute work.
argument-hint: "<role> [aspiration]"
allowed-tools: Bash(python3 *)
---

Run one **issue-discovery** pass for role **$1** — the problemistic-search half of the department's
autonomy (Cyert & March, docs/09): surface where the role is falling short of its aspiration, and
raise those as **self** backlog items. It only ADDS to the backlog; `/org-work` executes it.

Ledger root: `${ORG_LEDGER_ROOT}` (must be set).

## 1. Surface the gaps (where is this role under-performing its aspiration?)

Attention names two machine signals: a backlog that cannot serve the org's top objective (a coverage
gap), and items whose latest outcome fell below aspiration. Read them:

!`python3 "${CLAUDE_PLUGIN_ROOT}/tools/attention.py" select "${ORG_LEDGER_ROOT}" --role "$1" --aspiration ${2:-0.5}`

Also read the role's recent outcomes and any negative outcome deltas for this department:

!`python3 "${CLAUDE_PLUGIN_ROOT}/tools/ledger.py" census "${ORG_LEDGER_ROOT}"`

## 2. Raise self-items — scoped to THIS role's domain, deduped against the open backlog

From the gaps above, propose backlog items that are **this role's own domain** to improve. For each:

- It must be **within $1's mission/domain** — do not raise work that belongs to another role's domain
  (that is a coverage gap for the registrar/CEO to route, not a self-item to grab; docs/03 §3).
- It must **not duplicate an open backlog item** — check the `selected[]`/`deferred[]` above first.
- Keep it small and independent enough that `/org-work` could later delegate it under one seam
  contract (docs/03 §2).

### 2a. Derive `candidate_id` DETERMINISTICALLY — never invent a free-form id (docs/11 §0, reproducibility F4)

`candidate_id` is the backlog/dedup/WIP key. If you author it freely, running this discovery twice on
the SAME gap mints two different ids → the same spec+ledger yields a different backlog, and two founders
get different candidate sets from one RFP. So the id **must be a function of what the candidate IS**, not
of when or how many times discovery ran. For each self-item, derive it mechanically from three fields:

- **role** — `$1` (the maker/department that owns the item)
- **contract_ref** — the objective this item serves (the same `<objective>` you pass below)
- **gap** — a SHORT one-line description of the gap/deliverable (its identity, not prose). Use the same
  wording you'd put in a title; it is normalized (lowercased, whitespace-collapsed, trimmed) before hashing,
  so casing/spacing differences do not change the id — only a genuinely different gap does.

Compute the id with this exact formula (run it per item, substituting your gap line):

!`echo 'candidate_id := python3 -c '"'"'import hashlib,sys,re; role,contract,gap=sys.argv[1],sys.argv[2],sys.argv[3]; norm=re.sub(r"\s+"," ",gap.strip().lower()); print("cand-"+hashlib.sha256(("\x1f".join([role,contract,norm])).encode()).hexdigest()[:12])'"'"' "'"$1"'" "<objective>" "<one-line gap>"'`

The same (role, contract_ref, gap) always yields the same `cand-…` id; a genuinely different gap yields a
different one. This makes the "don't duplicate an open item" check above enforceable, not just advisory —
the same gap collides on id, and the ledger's natural-key idempotency (step 2b) drops the replay for you.

### 2b. Append each as `candidate_submitted` (source: self) — with the derived id as the natural key

Append with **source: self** so it lands in the same backlog and attention.py prioritizes it against
mandates on one footing. Pass the derived id BOTH as `candidate_id` (in the payload) AND as
`--natural-key`, so a replayed discovery of the same gap is an idempotent no-op at the ledger layer
(the `(class, natural_key)` dedup already lives in ledger.py append) — the backlog stays reproducible
under replay:

!`echo 'For each self-item, append: python3 "'"${CLAUDE_PLUGIN_ROOT}"'/tools/ledger.py" append "'"${ORG_LEDGER_ROOT}"'" --actor "'"$1"'" --class candidate_submitted --natural-key "<derived-cand-id>" --payload {"maker":"'"$1"'","candidate_id":"<derived-cand-id>","contract_ref":"<objective>","source":"self","evidence":[<gap-refs>]}'`

### 2c. Project each candidate onto GitHub as a task sub-issue (only if `ORG_GITHUB_REPO` is set)

If the org is steered through GitHub Issues, mirror each `candidate_submitted` onto a **task Issue**,
linked as a **native sub-issue of its objective's Issue** (created by `/org-found`), so the department's
work shows up under the right objective with progress roll-up. The task's title carries the gap; the
`--parent` is the objective Issue number; `--dept` is this role. Idempotent — a re-discovered gap has
the same title+objective, so `create` no-ops instead of minting a duplicate (docs/11 §0):

!`echo 'For each candidate, project it: python3 "'"${CLAUDE_PLUGIN_ROOT}"'/tools/github_sync.py" create --repo "$ORG_GITHUB_REPO" --kind task --parent <objective-issue-#> --dept "'"$1"'" --objective <objective-id> --title "<one-line gap>" --body "candidate_id: <derived-cand-id>". Skip silently if ORG_GITHUB_REPO is unset. The task Issue is the ledger candidate projected — the ledger stays the SSoT.'`

## Discipline

- **Discovery is bounded, not a fountain.** Raise items that close a real, evidenced gap; do not
  manufacture work to look busy. An empty pass (no gap → no item) is the normal, healthy outcome —
  fail-quiet, exactly like /org-tick.
- Self-items compete with mandates in the SAME backlog; a mandate carries a floor (zone of
  acceptance), so a self-item never starves a live instruction — the PM (attention.py) arbitrates.
- Append only. This command never spawns or executes; it feeds `/org-work`.
