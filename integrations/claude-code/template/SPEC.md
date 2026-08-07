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

> **This is a TASK spec — one atomic, independently-completable unit** (docs/11 §4b), not a whole domain.
> The objective Issue holds the *spec* (WHAT + EARS) and the *plan* (HOW — architecture/data-model); this
> task sub-issue is one *task* off that plan. **Single-unit assertion:** a fresh maker can take this green
> without another open Issue landing first (every `depends_on` below is already merged to `develop`). If
> it needs a sibling still in flight, it is too coarse — split it.

## Working context (where a fresh maker starts)
> The #1 thing a third party — a different agent, a fresh session with none of the originating context —
> needs to *begin*. `owns:` (below) names the territory; this names the door, the key, and the ignition.
> Without it a stranger stalls before writing a line.
- **repo / feature branch:** `<clone URL · open `feat/issue-<N>-<slug>` off `develop` (the org's branch
  policy, docs/11 §4c; `github_sync branch --issue <N>` prints the exact name)>`
- **setup + run:** `<the exact one-command setup and the run/test command, AND the dir to run them in —
  e.g. `cd app && npm ci` then `npm test`. Not "install deps" — the literal command a stranger pastes.>`
- **entry files:** `<the 1–3 files to open first (the seam of `owns`), not the whole tree>`

## Intent (why — the purpose this serves)
`<the goal this deliverable advances, grounded in the org's telos — not a metric. Trace it to the RFP.>`

## MUST — acceptance criteria in EARS (testable, not prose)
> Write each criterion in **EARS** (Easy Approach to Requirements Syntax) so it is testable and
> AI-parseable — one of five patterns, not "auth works" (docs/11 §4b):
> · *Ubiquitous:* "The system SHALL …" · *Event:* "**WHEN** … **THE system SHALL** …" ·
> *State:* "**WHILE** … **THE system SHALL** …" · *Unwanted:* "**IF** … **THEN THE system SHALL** …" ·
> *Optional:* "**WHERE** <feature> **THE system SHALL** …".
- [ ] `<WHEN a user submits the invite link twice THE system SHALL create exactly one membership>`
- [ ] `<IF an 11th member joins THEN THE system SHALL reject with a cap error>`
- [ ] `<…>`

## Entities / data-model contract (if any)
```
<Entity(field: type, …) — the shape downstream depends on>
```

> The three sections below are where **a human and an AI agree on what is being built**. They are
> required for work that touches the domain surface declared in `constitution.yaml`
> (`enforcement.domain_surface.paths`); `github_sync split-check` reports them missing and `ready`
> withholds the Issue until they are filled. Elsewhere they are optional.
>
> Reviewing a diff means hunting for mistakes, and a miss passes silently. Reviewing these means
> checking whether two parties describe the same thing — a mismatch is *visible*, and the reading
> cost tracks the domain, not the volume of generated code. That is the only review that survives an
> agent writing ten times more code.

## ドメインモデル / Domain model (the vocabulary and invariants this deliverable touches)
- **Entity:** `<Expense(id, payer: UserId, amount: Money, shares: Share[])>`
- **不変条件 / invariant:** `<sum(shares.amount) == amount — 例外なし>`
- **この Issue で変わるもの / what this Issue changes:** `<Expense に remainder_recipients: UserId[] を追加>`
- **変えないもの / what it must not change:** `<既存の money/split 不変条件>`

## ユースケースシナリオ / Use-case scenarios (who does what, and what results)
- **主 / main:** `<支出者が3人グループに¥100を均等割りする → 34/33/33 に分かれ、余り1円の受領者が記録される>`
- **代替 / alternate:** `<余りが出ない → 受領者は空>`
- **失敗 / failure:** `<グループ外の利用者が登録を試みる → 拒否され、理由が伝わる>`

## 認可規則 / Authorization (who is protected from whom)
> **ドメインの一部であって、技術的セキュリティではない。** 「誰が誰の支出を見てよいか」は
> ライブラリでは決まらない。ここが薄いと、守られるのは装飾的な項目だけになる — 実地では
> 12件の MUST のうち認可を定めたのは2件で、その1件が「あだ名」だった。金額・支払者・
> 債務の向き・グループ所有権は無防備のまま通っていた。
- **守る資産 / assets protected:** `<金額 / 支払者 / 債務の向き / グループ所有権>`
- **規則 / rules (EARS):** `<IF 非メンバーが支出を登録する THEN THE system SHALL 拒否する>`
- **守らないもの / deliberately unprotected:** `<あだ名 — 装飾的で、漏れても損害が無い>`

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
- **完了の判定:** 上の MUST が RED→GREEN になった時点で完了とする。**着手後に見つかった
  範囲外の欠陥は、この Issue で直さず別 Issue にする。** 直すべきものが増え続ける Issue は、
  gate が毎回「どこを見るか」から始めることになり、収束しない — 実地では8周 rework した Issue の
  4回目以降の発見が、すべてこの MUST に書かれていないものだった。範囲外の欠陥は skeptic が
  「Issue 化を推奨」として返し、スコープを切るかどうかは監督が決める（`agents/skeptic.md`）。
- Reproducibility (docs/11 §4a): the deliverable's repo must clone-and-run the same (lockfile,
  pinned toolchain, one-command setup+test, idempotent migrations, `.env.example`, green CI) — the
  gate runs `repro_lint` against it.
- **Every new test must be proven to go RED.** Before claiming a test covers a MUST, break the thing it
  tests and confirm it fails; then restore. A test that passes against broken code does not exist, and
  with no human reading the diff nothing else will notice — an agent writing tests to satisfy a coverage
  bar produces exactly this. Record the red output in the work log (`log --result`), not just the green.
- **その検査が「鳴らない場合」を1つ書く。** `<この検証が、対象が壊れているのに通ってしまう
  条件を1つ挙げる — 例「Supabase が落ちていると 46 件が skip され、RLS の穴があっても green」>`
  テストを RED にできても、**その検査が対象に届いていない**ことは起こる。実地の #9 は13周
  かかったが、その多くは実装ではなく検査側の欠陥だった: テストが `sw.ts` を一度も実行して
  いなかった／警報が条件分岐で構造的に鳴らなかった／ミューテーション実行器が構文エラーを
  SURVIVED と誤読した／ブラウザ検査が「offline.html でないこと」しか見ていなかった。
  いずれも「テストは書いてある・green である」を満たしている。**書けないなら、その検査は
  まだ何を見ているか分かっていない。**
- **Pass environment dependencies as arguments** — the clock, the home directory, the **platform**, the
  filesystem root. Not `process.platform` read deep inside a function, but a parameter. This is what
  makes platform and time-dependent behaviour testable *without* that platform, and it is why the
  multi-OS bar is affordable: most of the coverage comes from arguments, not from more CI runners.
- **Unread-safe (docs/11 §4e):** nobody reads every diff at fan-out scale, so the repo must carry a
  mechanical rejection layer — a configured ceiling on function size/complexity/nesting, strict typing
  with `any`/`@ts-ignore` banned, executable tests, and duplication/dead-code scanning (report-only is
  fine). `repro_lint` checks these at the same gates. Do not turn a strict rule on over a red codebase:
  land it as a warning, drive the count to zero, then ratchet it to an error. Exceptions belong in the
  config file **with a reason**, never as an inline `eslint-disable`.

## Decisions fixed by hypothesis (resolve open questions here, don't leave them tacit)
| question | decision |
|---|---|
| `<open point>` | `<the committed choice + why>` |

## Out of scope (explicitly deferred, so "done" is unambiguous)
- `<what this deliverable does NOT do>`
- `<and what already FAILED here — the dead ends a fresh maker must not re-derive (from the org's
  nearby_deaths). e.g. "PayPay recipient-prefill URLは存在しない — API決済は構造的に不可、金額コピー導線で行く">`

## Trailers (machine traceability — keep these last, verbatim)
```
candidate_id: <cand-…, derived deterministically from (role, contract_ref, one-line gap)>
coverage_row: <the rfp_capability cell from coverage-manifest.md, CHARACTER-FOR-CHARACTER>
```
> `coverage_row:` is load-bearing for RFP-derived tasks: `github_sync coverage-check` matches it exactly
> against the founding manifest to prove no must-have was dropped between design and backlog (docs/11
> §0a). A paraphrase reads as an orphan and leaves a real gap invisible; **do not translate the value**
> even when the rest of this Issue is written in the org's `output_language` — it is a machine key.
> Decoration around the label (`**coverage_row:**`, backticks, a bullet) is tolerated; the value must be
> the bare capability text. An `orgforge:mandate` task with NO trailer fails the gate. **Self-raised**
> items from `/org-discover` (`orgforge:self`) have no `coverage_row:` — that is expected, not a violation.

## Hand-back (how completion is submitted)
`<a PR against `develop` (NOT `main`) per the org's branch policy (docs/11 §4c): the task's feature
branch → PR → `develop`; close the Issue with the DoD command's green output pasted + the develop-CI
link. "Done" = merged to `develop` and integration-green there — not a PR against `main`.>`

> **No human reads this diff (docs/11 §4f).** Human review is retired, so this Issue is the audit
> record and it must stand on its own. Before closing, the Issue must carry: (a) the **work log** at
> full granularity — every command run *verbatim* with its **real output including failures**, files
> changed, and every course change with what caused it; and (b) every **judgment with its reasoning** —
> the gate's admission, the skeptic's refutation attempt, each phase transition (`github_sync decide`).
> The bar: a stranger reading only this Issue can reconstruct what was built, what was tried and
> abandoned, what was run, what came back, and **why it was allowed to merge** — without the ledger,
> without the transcript, without asking anyone.

---
_SDLC phases (docs/11): requirements → design → implement → test → integrate → deploy → operate. This spec is the
`requirements` artifact; the gate admits it (`phase_admitted{phase: requirements}`) before design starts._
