---
description: Found an org from an RFP or brief — the org drafts its own feature inventory, architecture, and organization.yaml, then reports up for your review before anything is built. Design-only; you approve the scope.
argument-hint: "<RFP text, or a path to an RFP/brief/design doc>"
allowed-tools: Bash(*), Read, Write, Edit, Glob, Grep, Agent, Task, WebFetch, WebSearch
---

Found a new articulated organization from a brief. This is **Phase 1 — scope + structure only**;
it does NOT build the product. It produces a reviewable `organization.yaml` (+ a feature inventory
and an architecture with the seam contracts between parts), then stops and reports up so you — the
CEO — approve the scope before any build.


> **出力言語:** `constitution.yaml` の `output_language`（既定 `en`）を読み、Issue・spec・人間向けテキストはその言語で書く（コード・ledger のイベント名・パスは英語の正準形のまま）。

## The brief

$ARGUMENTS

(If that is a path, read it. If it is prose, treat it as the RFP verbatim.)

## What to do

You are the CEO's secretary founding the org. Work spec-driven and fail-quiet; delegate breadth,
keep the CEO's decisions minimal. Concretely:

> **FIXED FILENAMES (docs/11 §0a — a rule, not a suggestion).** Founding writes exactly these files, at
> the org root, under exactly these names, because downstream commands (`/org-decompose`, `/org-init`)
> address them **by name** rather than by search, and a stranger opening any orgforge org must find the
> design in the same place:
> `REQUIREMENTS.md` · `FEATURE-INVENTORY.md` · **`ARCHITECTURE.md` (= 全体設計書)** · `coverage-manifest.md` ·
> `organization.yaml`. Do not invent a variant name (`design.md`, `architecture-overview.md`, `.yaml`
> instead of `.md`); a renamed artifact is an unfindable one.

1. **RECEIVE → `REQUIREMENTS.md`（書式はテンプレートに従う。自分で構成を発明しない）**

   受け取ったブリーフを **`${CLAUDE_PLUGIN_ROOT}/template/REQUIREMENTS.md` の骨格に整形して**書く。
   構成をその場で考えてはならない — founding のたびに違う構造の文書が出ると、「同じ spec ⇒ 同じ
   プロセス」という中核主張が要求記述の層で破れる（docs/11 §0b）。

   準拠: **ISO/IEC/IEEE 29148:2018 tailored conformance**（§4.5.2 が認める適合形態）+ **EARS**。
   要求は `FR-001` で採番し EARS の6パターンで書く。受入基準は Given-When-Then。成功基準は
   `SC-001` で採番し**技術非依存・定量的**に。**曖昧な点は推測で埋めず
   `[NEEDS CLARIFICATION: 何が不明か]` と明示する** — エージェントが推測で実装するのが最大の
   失敗モードであり、これが残っていれば下の lint が落とす。

   書いたら**必ず検査する**（必須節の欠落・EARS違反・§5.2.7 の禁止語・未解決マーカー・TBD）。
   **ファイルを書いた後に、あなた自身が Bash で実行すること**:

   ```
   python3 "${CLAUDE_PLUGIN_ROOT}/tools/req_lint.py" check REQUIREMENTS.md
   ```

   > これを `!` の自動実行にしてはならない。`!` ブロックはあなたが作業を始める**前**に一斉に
   > 展開されるので、まだ書いていないファイルを検査しようとして必ず失敗する（実地で判明）。
   > 「書く→検査する」という順序が要る手順は、あなたが順番に実行する。

   落ちたら直して**再実行する**。**検査を通らない要求記述で先に進まないこと** — 曖昧なまま
   設計に入ると、その曖昧さは実装まで伝播して、そこで初めて表面化する。

2. **FEATURE INVENTORY → `FEATURE-INVENTORY.md`.** Enumerate what the brief actually requires, grouped
   and prioritized
   (must / should / nice), and an explicit EXCLUDE list (what a first cut deliberately omits). You
   MAY fan out helper subagents per area to cover breadth — if you do, start each helper's prompt
   with `INDEPENDENT:` (its output is an inventory slice, never merged with a sibling's), so the
   spawn passes the seam gate. Be thorough; this is the 洗い出し.

3. **ARCHITECTURE + SEAMS → `ARCHITECTURE.md` (the 全体設計書).** This file is the **whole-system
   design**, and it is deliberately NOT an SDD artifact: SDD's spec/plan/tasks live in the Issue
   hierarchy (docs/11 §4b) and are per-objective/per-task, while this sits *above* all of them as the
   standing shape of the system — authored once here, amended at reorg. For the must-have set, name the layers/components and the **seam
   contracts** between them (the interface each side depends on) — precise enough that the pieces
   could be built in parallel without drift later. Choose the split axis that fits the work; do not
   force one axis top-to-bottom. Every seam contract MUST carry the normalized shape
   **{deliverable, standard, checker, depends_on}** — `deliverable` = what one side owes, `standard`
   = the acceptance criterion the other side can check it against (a bar, not a vibe), `checker` =
   who admits it (a role DISTINCT from the deliverable's maker — usually the gate), `depends_on` =
   the roles whose output it consumes. A seam with no `standard` or no distinct `checker` is not a
   contract; it is a hope. This normalized shape is what makes two foundings CONVERGE: the pieces
   satisfy the SAME contracts even when the role names differ (docs/11 §0).

4. **ORGANIZATION.YAML + COVERAGE MANIFEST.** Fill `template/organization.SKELETON.yaml` into a
   concrete `organization.yaml`: the purpose, the domain roles (one per component/layer, each with a
   contract {deliverable, standard, checker, depends_on} in the normalized shape from step 3),
   keeping the control skeleton (supervisor / gate / skeptic / registrar) intact.

   Alongside it, emit a normalized **coverage manifest** as **`coverage-manifest.md`** (that exact
   name — `/org-decompose` reads it as its input). For
   EVERY must-have capability/deliverable the RFP names, one row: `{ rfp_capability, owning_role,
   deliverable, acceptance }` — mapping each required must-have onto the SINGLE role that owns it and
   the acceptance criterion its output must meet. The rules the manifest must satisfy (these are what
   make two foundings from the same RFP converge on the SAME contracts, docs/11 §0):
   - every must-have RFP capability appears in exactly one row (nothing required is unowned);
   - each `owning_role` and `deliverable` matches a role + contract in organization.yaml;
   - no deliverable is owned by two rows (exactly-one ownership);
   - each row has a non-empty `acceptance` and a checker distinct from the maker.
   The manifest is the RFP→contract coverage map; organization.yaml is its machine-checkable side.

   Then VALIDATE the chart (O10 mechanically gates coverage: each declared deliverable has a
   non-empty standard, exactly one owner, and a checker != maker):

   Lint the **org's own** spec files, falling back to the plugin templates only for files this org has
   not installed. Linting the pristine templates instead would make the check meaningless: `/org-init`
   copies those four in as the org's editable copies and the CEO edits `constitution.yaml` (purpose,
   `output_language`, clearing `SET_ME`) — so a template-based lint would pass a `SET_ME` the real org
   still carries, and would check O6/O6c/MV cross-references against the *template's* role names rather
   than the ones you just wrote.

   **`organization.yaml` を書いた後に、あなた自身が Bash で実行すること**（`!` の自動実行では
   まだ存在しないファイルを検査してしまう）:

   ```
   set -- organization.yaml
   for f in constitution.yaml moves.yaml ledger-schema.yaml sensors.yaml; do
     if [ -f "$f" ]; then set -- "$@" "$f"; else set -- "$@" "${CLAUDE_PLUGIN_ROOT}/template/$f"; fi
   done
   python3 "${CLAUDE_PLUGIN_ROOT}/tools/org_lint.py" "$@"
   ```

   > `set --` の位置パラメータを使うこと。`A="$A $f"` と文字列に組み立てて `$A` で渡すと、
   > **zsh は単語分割しない**ので全体が1引数として渡り、引数不足で usage が出る（実地で判明）。

   Fix anything the lint fails; a chart that does not lint is not founded. If O10 fires, a
   deliverable is missing its standard, owned twice, or self-checked — fix the contract, not the
   check. Cross-check the manifest against the chart: any must-have with no owning contract is a
   coverage GAP the founding must close before reporting up.

## 人間にしか実行できない前提条件を Issue にする（docs/11 §0c）— 省略しないこと

**org は自分が作れる作業だけを Issue にし、人間に頼むものを散文に落としてはならない。**
実地の founding で3件（Supabase プロジェクト作成 / Google OAuth クライアント登録 / GitHub の
ブランチ保護設定）がセッションの文章の中にしか残らず、Issue にも台帳にも入らなかった。
結果、`/org` は GREEN と表示するのに実際は着手できない、という乖離が起きた。

**人間への依頼こそ、忘れられると最も長く止まる。** 必ず構造化すること。

抽出源はすでに手元にある:

- `REQUIREMENTS.md` の **Open Questions** 節 — 「実装前に決める」と自分で書いたもの
- 同 **Assumptions** 節 — 「CEO が用意する」「アカウントが必要」と書いたもの
- `ARCHITECTURE.md` の技術選択のうち、**外部サービスの登録・鍵の発行**が要るもの
- 起草中に「これは自分にはできない」と気づいたすべて

判定は単純: **org のツールで完結するか。** アカウント作成・課金・OAuth クライアント登録・
ドメイン取得・ストア審査・GitHub の管理設定（ブランチ保護など）は、いずれも人間にしかできない。

該当するものを1件ずつ Issue にする:

```
python3 "${CLAUDE_PLUGIN_ROOT}/tools/github_sync.py" needs-human \
  --title "<人間がやる作業（一行）>" \
  --body "<どこで・何をして・何を返せばよいか。手順まで書く>" \
  --objective "<関連する objective id>" --parent <objective Issue 番号> \
  --blocks "<この作業が終わるまで着手できない Issue 番号>"
```

`--blocks` を書いたら、**その下流 Issue の body に `Depends on: #<この Issue 番号>` を追記する**
こと（正書法はこの literal — 参照の後ろに注釈を足すのは許容されるが、依存は必ず `#番号` の形で。
散文だけの依存は `ready` に見えない、Issue #103）。そうして初めて `ready` が人間待ちを依存として
解釈し、ブロックされた task を maker に渡さなくなる。

5. **REPORT UP for CEO review.** Summarize concisely: the must/should/nice counts, the layers +
   seams, the roles you defined, the **coverage manifest** (every must-have → its one owning role +
   acceptance, with any gaps called out), and the decisions that genuinely need the CEO's sign-off
   (stack choice, the must-have line, anything irreversible)、そして
   **あなたが立てた needs-human Issue の一覧**（これが CEO の作業リストになる）。 **STOP here** — do not build the
   product, and do not mint task Issues. Founding is design; the scope is the CEO's call. Once the CEO
   signs off, the next step is **`/org-decompose`**, which turns `coverage-manifest.md` +
   `ARCHITECTURE.md` into the atomic task Issues — tell the CEO that in your report.

Write all five artifacts — `REQUIREMENTS.md`, `FEATURE-INVENTORY.md`, `ARCHITECTURE.md`, `coverage-manifest.md`,
`organization.yaml` — as files under those exact names (docs/11 §0a) so they can be reviewed, edited,
and addressed by name downstream. Do not touch real assets; this command only drafts the org.

## CEO の承認を台帳に記録する — 口頭で終わらせない

「承認後に objective Issue を作れ」と指示しても、**承認そのものを記録する手段がなかった**ため、
承認された事実がどこにも残らなかった（実地で判明）。founding は charter-tier の決定であり、
docs/05 §1 は「人間の承認が要る」と明記している。それが台帳に無いなら、後から「誰がいつ何を
承認したのか」を辿れない。

CEO の承認を受けたら、**Issue を作る前に**記録すること:

```
python3 "${CLAUDE_PLUGIN_ROOT}/tools/ledger.py" append --actor ceo \
  --class proposal_adjudicated \
  --payload '{"proposal_id":"founding","decision":"approve","human":"<CEO>"}'
```

承認されなかった点があれば `decision: amend` で、何を変えるよう指示されたかを payload に残す。
**承認を受けていないなら、この先に進まないこと** — objective Issue を作るのは承認の投影であって、
承認の代わりではない。

## Project the objectives onto GitHub (only if `ORG_GITHUB_REPO` is set)

If this org is steered through GitHub Issues (the web harness, or a laptop-free workflow), project each
**objective** the founding defined onto a big-picture **objective Issue** — the parent that its
department tasks will hang under. Do this *after* CEO sign-off (the Issue is the projection of an
approved objective, not of a draft), one per objective in the priority ranking:

!`echo 'For each approved objective: python3 "'"${CLAUDE_PLUGIN_ROOT}"'/tools/github_sync.py" create --repo "$ORG_GITHUB_REPO" --kind objective --objective <objective-id> --title "<objective name>" --body "<the acceptance / coverage summary>". This mints the parent Issue (orgforge:kind:objective). Department tasks are created next by /org-decompose as native sub-issues under it (--kind task --parent <this#>), carrying source=mandate and a coverage_row trailer. (/org-discover only adds SELF-raised items later, which are source=self and carry no trailer — it is not the RFP decomposition step.) Skip silently if ORG_GITHUB_REPO is unset — a ledger-only org.'`

The objective Issue is a **projection of the ledger objective** (SSoT unchanged); the sub-issue tree of
department tasks that grows under it is the backlog window, regenerated — never a second source of truth.

## Close the requirements and design phases — or the first task cannot start

**This step is not optional, and skipping it stops the org before it builds anything.** The SDLC mold
(docs/11 §2) rejects `phase_started{implement}` unless `design` was admitted, and `design` unless
`requirements` was. `/org-work` fires `phase_started{implement}` at delegation — so with no phase
history, **task #1 is rejected at the ledger** with a message naming a predecessor that nobody was ever
told to write. Founding is where those two phases genuinely happen, and where their evidence exists:

- **requirements** — the artifact is `REQUIREMENTS.md` + `FEATURE-INVENTORY.md` (what must be built, with the
  must/should/nice line and the explicit EXCLUDE list).
- **design** — the artifact is `ARCHITECTURE.md` + `coverage-manifest.md` + the linted
  `organization.yaml` (the whole-system design and its seam contracts, each must-have owned once).

So after CEO sign-off, walk each objective's deliverable through both phases — **entered, then
admitted** (an admission with no matching start is rejected; a phase cannot be admitted without having
been entered). The `deliverable` must be the SAME identifier `/org-work` will later use — the objective
Issue number if you minted one, otherwise the objective id — written consistently, since the chain keys
on it:

!`echo 'Per objective deliverable D, in this order: for PHASE in requirements design; do python3 "'"${CLAUDE_PLUGIN_ROOT}"'/tools/ledger.py" append --actor supervisor --class phase_started --payload '"'"'{"deliverable":"<D>","phase":"<PHASE>","role":"supervisor"}'"'"'; python3 "'"${CLAUDE_PLUGIN_ROOT}"'/tools/ledger.py" append --actor gate --class phase_admitted --payload '"'"'{"deliverable":"<D>","phase":"<PHASE>","verdict":"pass","admitter":"gate","evidence_ref":"<REQUIREMENTS.md+FEATURE-INVENTORY.md for requirements; ARCHITECTURE.md+coverage-manifest.md+organization.yaml for design>"}'"'"'; done'`

Note the **actors differ**: the supervisor enters the phase, the gate admits it. The ledger enforces
that separation at write time for admissions (docs/11 §4f.1) — the same actor cannot both do the work
and sign it off. Record the admission's reasoning on the objective Issue too (`github_sync decide
--event phase_admitted --verdict pass --why … --evidence "<the artifacts>"`), since no human reviews it.

org が発見できない（`.orgforge/` も `organization.yaml` も無い）場合は、そう言って止まること。
先に `/org-init` をこのディレクトリで実行する必要がある。
