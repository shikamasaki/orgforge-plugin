# SPEC — the structure of a task Issue (the per-deliverable spec)

> This is the **structure a task Issue is written in** — orgforge's spec-driven task template. A
> manager delegating a deliverable fills these sections **directly into the deliverable's GitHub task
> Issue body** (`github_sync create --kind task`), so the intent is **explicit and checkable**: the
> subordinate builds to it, and the gate/skeptic verify *against* it (not against a vibe).
> Reproducibility (docs/11 §0) starts here — two makers handed the *same* filled-in spec converge on
> the same contract, even if the code differs.
>
> **This is NOT a separate SSoT file.** The SSoT is **code + the domain model** (conventions + the org
> spec — organization.yaml / constitution.yaml). The ledger is the audit record, not the SSoT — never a
> pile of per-task Spec files (the fragment-Spec trap: task-scoped specs
> lying around never form a coherent context and rot; the user's AI-DLC lesson, docs/12 §3.3). So the
> task spec lives **in the Issue**, and the ledger only *points* at it: `spec_delegated`'s `spec_ref`
> is the **Issue number/URL**, not a `docs/spec/*.md` path. The Issue is the task's working detail
> under the SSoT; the ledger records that a spec was delegated and where it lives. Do **not** create a
> `docs/spec/` file — write these sections into the Issue.
>
> This file is a *template* (the section skeleton), the way `.github/ISSUE_TEMPLATE` is a form — copy
> the headings into a new task Issue and fill them. It is not itself a spec, and it is not committed
> per-deliverable anywhere.
>
> **記入言語 / fill-in language:** write the *content* in the org's `output_language`
> (`constitution.yaml`; e.g. `ja` → 日本語で記入). The section headings below may stay as-is; only the
> filled-in prose follows the setting, so the CEO reads the spec in their language.

## Deliverable
`<one line: what is being built>` — owner role: `<role id>` · contract_ref: `<objective/contract id>` · est: `<S/M/L>`

## Working context (where a fresh maker starts)
> The #1 thing a third party — a different agent, a fresh session with none of the originating context —
> needs to *begin*. `owns:` (below) names the territory; this names the door, the key, and the ignition.
> Without it a stranger stalls before writing a line.
- **repo / branch:** `<clone URL · base branch · the branch to open for this work>`
- **setup + run:** `<the exact one-command setup and the run/test command, AND the dir to run them in —
  e.g. `cd app && npm ci` then `npm test`. Not "install deps" — the literal command a stranger pastes.>`
- **entry files:** `<the 1–3 files to open first (the seam of `owns`), not the whole tree>`

## Intent (why — the purpose this serves)
`<the goal this deliverable advances, grounded in the org's telos — not a metric. Trace it to the RFP.>`

## MUST — acceptance criteria (the bar the gate checks; each must be verifiable)
- [ ] `<a checkable behaviour — "invite link is idempotent", not "auth works">`
- [ ] `<…>`

## Entities / data-model contract (if any)
```
<Entity(field: type, …) — the shape downstream depends on>
```

## Seam contract (what this deliverable OUTPUTS that other deliverables integrate to)
> The four things a delegated task needs so parallel makers don't duplicate or collide (Anthropic
> multi-agent research; docs/sources): a clear **objective**, an **output format**, **tool/source
> guidance**, and a **crisp boundary**. Intent+MUST give the objective; fill the rest here.
- **provides (output format):** `<the interface/data the downstream consumes, in a NAMED shape — a
  function signature, a JSON schema, a table — so an integrator wires to it without guessing>`
- **example (input → output):** `<one concrete case, e.g. `split(¥100, EQUAL, 3) → [34,33,33]` — for
  anything with logic (math, a state machine), one example is worth ten MUST bullets and is a free
  self-test a stranger uses to confirm they read the intent right>`
- **depends_on:** `<#Issue · required state (admitted/merged) · the exact seam I consume from it — a
  link the maker clicks and a state they check, not prose. "領域A" alone doesn't tell them if it's ready.>`
- **owns:** `<the files/territory this deliverable writes — for concurrent-write safety>`
- **boundary (NOT mine):** `<the adjacent work this deliverable must NOT touch — the sibling that owns
  it. Explicit boundaries are what stop two parallel makers from building the same thing differently.>`
- **tools/sources:** `<the specific tools, APIs, or references this maker should use — not "figure it
  out", so siblings don't each re-derive the same search or pick divergent libraries>`

## Verification (how the gate/skeptic confirm the MUSTs — nulls/placebos/forward tests)
- **DoD command (run this to know you're done):** `<the exact command whose green output = these MUSTs
  pass — the SAME command the gate uses — e.g. `cd app && npm test`. "19 tests pass" is not runnable; a
  command is.>`
- `<the concrete test/evidence that proves each MUST — e.g. "an 11th join is rejected at the cap">`
- Reproducibility (docs/11 §4a): the deliverable's repo must clone-and-run the same (lockfile,
  pinned toolchain, one-command setup+test, idempotent migrations, `.env.example`, green CI) — the
  gate runs `repro_lint` against it.

## Decisions fixed by hypothesis (resolve open questions here, don't leave them tacit)
| question | decision |
|---|---|
| `<open point>` | `<the committed choice + why>` |

## Out of scope (explicitly deferred, so "done" is unambiguous)
- `<what this deliverable does NOT do>`
- `<and what already FAILED here — the dead ends a fresh maker must not re-derive (from the org's
  nearby_deaths). e.g. "PayPay recipient-prefill URLは存在しない — API決済は構造的に不可、金額コピー導線で行く">`

## Hand-back (how completion is submitted)
`<the artifact and where — e.g. "PR against `main`; close the Issue with the DoD command's green output
pasted + the CI-green link". The Issue is the work surface; a spec that never says how to put the work
back leaves a stranger inventing a hand-back.>`

---
_SDLC phases (docs/11): requirements → design → implement → test → deploy → operate. This spec is the
`requirements` artifact; the gate admits it (`phase_admitted{phase: requirements}`) before design starts._
