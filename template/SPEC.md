# SPEC — the per-deliverable specification a manager delegates DOWN

> This is the **spec template** orgforge is spec-driven *around*. A manager writing a `spec_delegated`
> event (docs/09 §spec-driven) fills this out for the deliverable it is delegating, so the intent is
> **explicit and checkable** — the subordinate builds to it, and the gate/skeptic verify *against* it
> (not against a vibe). The spec is the SSoT for "what this deliverable must be"; the code is a
> projection of it. Reproducibility (docs/11 §0) starts here: two makers handed the *same* spec
> converge on the same contract, even if the code differs.
>
> Copy this file per deliverable (e.g. `docs/spec/<deliverable>.md`), fill every section, reference it
> by `spec_ref` in the `spec_delegated` event, and project it into the deliverable's task Issue.
>
> **記入言語 / fill-in language:** write the *content* in the org's `output_language`
> (`constitution.yaml`; e.g. `ja` → 日本語で記入). The section headings below may stay as-is; only the
> filled-in prose follows the setting, so the CEO reads the spec in their language.

## Deliverable
`<one line: what is being built>` — owner role: `<role id>` · contract_ref: `<objective/contract id>`

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
- **provides:** `<the interface/data the downstream consumes>`
- **depends_on:** `<upstream deliverables/specs this needs first>`
- **owns:** `<the files/territory this deliverable writes — for concurrent-write safety>`

## Verification (how the gate/skeptic confirm the MUSTs — nulls/placebos/forward tests)
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

---
_SDLC phases (docs/11): requirements → design → implement → test → deploy → operate. This spec is the
`requirements` artifact; the gate admits it (`phase_admitted{phase: requirements}`) before design starts._
