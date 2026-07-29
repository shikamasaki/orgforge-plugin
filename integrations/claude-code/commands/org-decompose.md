---
description: Turn the approved founding design (coverage-manifest.md + ARCHITECTURE.md) into the atomic SPEC task Issues — one per independently-completable unit, each a native sub-issue of its objective, each carrying the full spec so any environment can pick it up. The bridge between /org-found (design) and /org-work (execution).
argument-hint: "[objective-id] [--dry-run]"
allowed-tools: Bash(python3 *), Bash(echo *), Bash(test *), Read, Agent
---

Decompose the **approved** founding design into the backlog: every must-have in the coverage manifest
becomes one or more **atomic task Issues**, written in the SPEC structure, hung under its objective
Issue. This is the step between `/org-found` (which designs and stops) and `/org-work` (which executes);
without it the design never becomes workable units, and the must-haves sit unowned.

This command projects onto GitHub Issues, so it needs an org to write into and a backlog repo to write
to. Both are **discovered** from the working directory (`tools/discover.py`) — no environment setup.
Check them up front, not one failing `create` at a time: with no repo, every Issue creation fails at
`gh` *after* you have drafted full SPEC bodies for the whole manifest.

!`D="${CLAUDE_PLUGIN_ROOT}/tools/discover.py"; LR="$(python3 "$D" ledger 2>/dev/null)"; GR="$(python3 "$D" repo 2>/dev/null)"; missing=""; [ -n "$LR" ] || missing="$missing ORG(ledger)"; [ -n "$GR" ] || missing="$missing GitHub-remote"; if [ -n "$missing" ]; then echo "STOP —$missing not discoverable from $(pwd). Run /org-init here first (and add a git remote if the backlog is missing)."; else echo "preconditions OK — ledger: $LR · backlog repo: $GR"; fi`

If that prints **STOP**, stop and tell the CEO. Do not proceed to draft specs against an unset repo.

**このコマンドは実行時のカレントディレクトリの org に対して働く。** 上の行が別の org を指しているなら、
セッションが目的のリポジトリにいない — そのまま進めると他所の org に Issue を切る。止めて場所を直すこと。

> **出力言語:** `constitution.yaml` の `output_language`（既定 `en`）を読み、Issue 本文・spec・人間向け
> テキストはその言語で書く（コード・ledger のイベント名・パス・`coverage_row:` トレーラの値は英語の
> 正準形のまま — トレーラは機械照合キーなので manifest の表記と1文字も違えてはならない）。

## 0. Preconditions — read the FIXED founding artifacts (docs/11 §0a)

These filenames are fixed by rule, so this command addresses them by name rather than asking you where
they are. Read them now:

- **`coverage-manifest.md`** — the input. One row per must-have: `{rfp_capability, owning_role,
  deliverable, acceptance}`. This is the work list; nothing outside it is RFP-derived scope.
- **`ARCHITECTURE.md`** — the 全体設計書. The layers/components and the **seam contracts**
  `{deliverable, standard, checker, depends_on}`. This is where each task's `provides` / `depends_on` /
  `owns` / boundary come from — do not re-derive them, *read* them.
- **`organization.yaml`** — which role owns what (the machine-checkable side of the manifest).
- **`REQUIREMENTS.md`** — for tracing intent when a manifest row is terse.

If `coverage-manifest.md` or `ARCHITECTURE.md` is missing, **STOP**: founding is incomplete, or it wrote
variant filenames. Run `/org-found` (or rename the artifacts to the canonical names) — do not improvise a
decomposition from the RFP alone, because then the coverage check below has nothing to verify against.

Also confirm the CEO **approved** the founding. Decomposition mints real Issues; doing it on an
unapproved draft floods the backlog with work the CEO may cut.

## 1. Carve each manifest row into ATOMIC units

For each must-have row (filter to `$1`'s objective if an objective-id was given), decide how many task
Issues it becomes. The doctrine (docs/11 §4b, docs/03 §6.2):

- **One task = one independently-completable unit** — one endpoint, one function, one screen, one
  migration. Not a domain, not "the auth system".
- **Split at every seam where sibling `owns` sets are disjoint.** Disjoint `owns` ⇒ the two units are
  `[P]` parallel-safe ⇒ they are separate Issues. Spec Kit の `[P]`（"different files, no
  dependencies"）と同じ判定である。
- **`owns` が同じでも、壊れ方と検証手段が違えば別 Issue。** これは `owns` の交わりでは
  captured されない軸で、実地で最も高くついた（下記）。問うべきは:

  > この deliverable が壊れたとき、**壊れ方は1種類か**。検証に必要な手段は**1種類か**。

  2種類以上なら分割候補。実地の #11（中核スキーマと RLS）は `supabase/` に閉じていたため
  `owns` 基準では分割されなかったが、中身は「スキーマの形（型・制約で守る）」と
  「認可（攻撃シナリオで守る）」という**壊れ方も検証手段も別の2つ**だった。結果、gate が
  毎回「どこを見るか」の探索から始め、migration 5本が相互に干渉し（0009 が直したものを
  0010 が壊し、0011 が別の2件を RED にした）、**12周しても終わらなかった**。同じ日に
  #8（1つの関数）と #10（CI 設定）は1〜2周で通っている。

  Kiro の規範が同じことを別の言い方でしている — タスクは *"Implement X function" rather than
  "Support X feature"*。機能単位ではなく、**1つの壊れ方に対応する単位**に落とす。
- **Do NOT split reciprocally-coupled work.** If two candidate units must constantly adjust to each
  other, they are ONE Issue — over-splitting coupled work costs far more than it saves (docs/12 §6).
- **Order by dependency.** A unit that consumes another's seam records `depends_on: #<issue>` and the
  state it needs (`merged to develop`). Create the depended-upon Issue first so the number exists.

**要求そのものが薄くないかを、切る前に見る。** 分割の失敗は、しばしば要求の欠落として現れる。
実地の #11 は EARS 12件のうち認可を定めたものが4件で、そのどれも「入った後に何ができるか」を
定めていなかった（内側に触れていたのは「あだ名」＝装飾的なテキスト列だけ）。**金額・支払者・
債務の向き・グループ所有権は無防備**で、後半6周の rework は Issue のどの MUST にも対応しない
作業になった。この deliverable が扱う資産に対し、MUST が**誰から誰を**守ると定めているか —
片側しか定めていないなら、要求を書き足してから切ること。`github_sync split-check` が起票後に
同じ検査をするが、**起票時に気づけるならそのほうが安い**。

Lean toward **finer** splits when in doubt about independent units (a coarse task produces 大味 output),
and toward **keeping together** when the coupling is genuine. You MAY fan out helper subagents to draft
several rows' task-sets concurrently — prefix each with `INDEPENDENT:` so the spawn passes the seam gate,
and give each helper one row (never two helpers on the same row, or they mint duplicate Issues).

## 2. Derive each task's `candidate_id` deterministically (reproducibility F4)

Same rule as `/org-discover`: the id is a function of *what the task is*, never of when it was minted, so
re-running decomposition on the same manifest is idempotent rather than duplicating the backlog.

Derive it with the organ — **do not hand-compute it or paste a shell one-liner**; the fields are joined
on a unit separator that a shell `echo` silently eats, and losing it makes different tasks collide onto
one id (whereupon the second task's ledger append is swallowed as a "replay" and it never enters the
backlog at all):

!`echo 'Per task: python3 "'"${CLAUDE_PLUGIN_ROOT}"'/tools/github_sync.py" candidate-id --role "<owning_role>" --contract "<objective-id>" --gap "<one-line task title>"'`

Append each as a backlog candidate, using the derived id as the natural key (a replay is a ledger-layer
no-op):

!`echo 'Per task: python3 "'"${CLAUDE_PLUGIN_ROOT}"'/tools/ledger.py" append --actor supervisor --class candidate_submitted --natural-key "<cand-id>" --payload '"'"'{"maker":"<owning_role>","candidate_id":"<cand-id>","contract_ref":"<objective-id>","source":"mandate","evidence":["coverage-manifest.md:<rfp_capability>"]}'"'"''`

`source: mandate` — an RFP-derived task is top-down scope, unlike `/org-discover`'s self-raised items, so
attention.py floors it correctly against self-items.

## 3. Write the FULL SPEC into each Issue body — this is what makes it environment-independent

Read `${CLAUDE_PLUGIN_ROOT}/template/SPEC.md` and fill **every** section for this task. The Issue body is
the *only* context a maker in another environment gets — a web session, a different machine, a fresh
agent with none of this conversation. A body that is a bare id or a one-line title is an empty shell.

The sections that carry the environment-independence (do not skimp on these):

- **Working context** — the clone URL, the exact `feat/issue-<N>-<slug>` branch (from
  `github_sync branch --issue <N>`), the literal one-command setup + test commands *and the directory to
  run them in*, and the 1–3 entry files. A stranger pastes these and is running.
- **MUST in EARS** — every acceptance criterion as WHEN/WHILE/IF/WHERE…SHALL. Carry the manifest row's
  `acceptance` in verbatim as one of them; prose like "auth works" is not a bar.
- **Seam contract** — `provides` (the named output shape), one worked `example` (input → output),
  `depends_on` (#Issue + required state + the exact seam consumed), `owns` (disjoint from siblings),
  `boundary` (the adjacent work that is NOT this task's), `tools/sources`. Take these from
  `ARCHITECTURE.md`'s seam contracts.
- **Verification** — the exact DoD command whose green output means done (the same command the gate runs).
- **Out of scope** — including prior deaths, so a fresh maker does not re-derive a known dead end:

!`python3 "${CLAUDE_PLUGIN_ROOT}/tools/ledger.py" view nearby_deaths 2>/dev/null || echo "（まだ死が記録されていない — 初回 founding では正常）"`

Two trailers at the bottom of every body, for machine traceability:

```
candidate_id: <cand-id>
coverage_row: <rfp_capability verbatim from coverage-manifest.md>
```

The **`coverage_row:` trailer is load-bearing** — step 5's coverage gate matches on it exactly. Copy the
capability cell character-for-character; a paraphrase reads as an orphan and fails the gate. Do not
translate it, even when the rest of the body is in the org's `output_language`: it is a machine key, not
prose. Markdown decoration around the label (`**coverage_row:**`, `` `coverage_row:` ``, a list bullet)
is tolerated by the parser, but the **value** must be the bare capability text.

Every RFP-derived task must carry one: an `orgforge:mandate` task with no trailer now fails the gate
(it would otherwise float unattached to any requirement while the manifest still reads green).

## 4. Create the Issues — as native sub-issues of their objective

!`echo 'Per task: python3 "'"${CLAUDE_PLUGIN_ROOT}"'/tools/github_sync.py" create --repo "$ORG_GITHUB_REPO" --kind task --parent <objective-issue-#> --dept "<owning_role>" --objective "<objective-id>" --source mandate --title "<one-line task title>" --depends "<dep issue numbers, comma-separated>" --body "<the FILLED SPEC.md + the two trailers>"'`

`create` is idempotent on (title, objective) across **open and closed** Issues: re-running decomposition
returns the existing Issue rather than minting a duplicate, and re-asserts the parent link. Closed
counts too — a delivered task is closed, and re-minting it would duplicate finished work and re-open
settled scope. This is what makes the re-run safe as a repair step after a manifest amendment.

**Pass `--depends` AND write the SPEC's `depends_on:` line — they are not redundant.** `--depends`
appends a `Depends on: #N` line that `github_sync ready` parses to decide whether a task is *workable*
(it withholds an Issue whose dependency is still open). The SPEC's `- **depends_on:**` bullet is the
*human/maker-facing* contract — which seam is consumed and in what state — and is what `split-check`
reads. Omit `--depends` and a blocked task will be handed to a maker as ready; omit the SPEC line and the
maker gets no idea what they're waiting on.

Then shape-check each new Issue — it warns (exit 10) when a task is too coarse (`owns` spanning
territories), depends on something still open, or has non-EARS acceptance:

!`echo 'Per created issue: python3 "'"${CLAUDE_PLUGIN_ROOT}"'/tools/github_sync.py" split-check --repo "$ORG_GITHUB_REPO" --issue <N>'`

Fix what it flags by **re-splitting the Issue**, not by loosening the spec.

## 4b. 人間にしか実行できない前提条件を Issue にする（docs/11 §0c）— 省略しないこと

**org は自分が作れる作業だけを Issue にし、人間に頼むものを散文に落としてはならない。**
起草中に「これは #N の範囲外」と気づいたものを含む。実地の founding で3件（Supabase プロジェクト作成 / Google OAuth クライアント登録 / GitHub の
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
こと。そうして初めて `ready` が人間待ちを依存として解釈し、ブロックされた task を maker に
渡さなくなる。

## 5. The coverage gate — prove no must-have was dropped

This is the check that makes decomposition trustworthy: `/org-found`'s O10 proved every must-have has one
owning *contract*; this proves every must-have reached at least one *task Issue*. A must-have that never
became an Issue is silently unbuilt, and nothing downstream would ever notice.

**task Issue を作り終えた後に、あなた自身が Bash で実行すること**（`!` の自動実行では
Issue がまだ1件も無い時点で走り、必ず全件 GAP になる）:

```
python3 "${CLAUDE_PLUGIN_ROOT}/tools/github_sync.py" coverage-check --manifest coverage-manifest.md
```

**Exit 10 = a gap.** Decompose the listed must-haves and re-run until it exits 0. Do not report the
decomposition complete while a GAP line is printed — an uncovered must-have is the one failure this whole
command exists to prevent. (Orphan-trailer warnings mean a typo'd `coverage_row:`; fix the trailer.)

## 6. Report up

Summarize for the CEO: how many task Issues per objective, which manifest rows fanned into several units
and why, which were deliberately kept as one (the coupled ones), the dependency order (what must land
first), and the coverage-check result — **`N/N` rows covered**, or the remaining gaps.

Then tell them the next step: the backlog is now workable from anywhere —
`/org-work <role>` locally, or claiming an Issue from any other environment
(`github_sync claim --issue N --agent <you>`), because each Issue carries its own full spec.

## Discipline

- **Decompose from the manifest, not from imagination.** Every RFP-derived task traces to a
  `coverage_row`. Work that has no manifest row is either a `/org-discover` self-item or scope creep.
- **This command creates and records; it does not build.** No implementation here — `/org-work` executes.
- **Re-running is safe.** Deterministic ids + idempotent `create` mean a second pass fills gaps rather
  than duplicating the backlog. That is what makes it usable as a repair step after a manifest amendment.
