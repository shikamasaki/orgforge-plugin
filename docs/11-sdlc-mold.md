# 11 — The forced SDLC mold: the shape the work is made to travel through

*Part III · Operate — see [the four-part map](README.md).*

> **In one sentence:** an IT business company builds by forcing every deliverable through a
> non-skippable phase chain — requirements → design → implement → test → integrate → deploy → operate — and the
> chain is enforced by the *same* `requires_prior` mechanism the repo already uses to stop a maker
> from grading its own work (docs/03) and a manager from reporting up unverified work (docs/09),
> now generalized from *admission gating* to *phase gating*.

This doc adds no new machinery. It **lifts one mechanism the repo already has** — the ledger's
`requires_prior` idiom — from the two places it lives today to the one place the re-scope needs it:
the software-delivery lifecycle. Read it after docs/03 (which introduces routing and `requires_prior`)
and docs/09 (which instantiates it as spec-before-report-up); this doc generalizes both.

---

## 0. Why a mold, and why *forced*

THEORY §1b states the load-bearing reason: **AI is an amplifier.** Drop it into a process and it
magnifies that process — good and bad equally — and by accelerating the upstream it *degrades
stability* and shifts the binding constraint downstream to review, test, and deploy (DORA 2024–2025).
An amplifier without a mold does not go faster in any way that matters; it produces more, faster, of
whatever it was already producing — including defects that surface at the newly-moved bottleneck.

A human software org survives this because the lifecycle is carried tacitly: an experienced team
*doesn't* start coding before the requirement is understood, *doesn't* ship before the test passes —
not because a gate blocks them but because they'd be embarrassed to. An AI carries nothing it is not
given. Left to infer the lifecycle, an agent will skip straight from a one-line intent to a deploy,
because each local step looks locally reasonable and nothing tacit stops it. So the lifecycle, like
every other tacit organizational thing in this repo, has to be **made explicit and made checkable**.

**The deep purpose of the mold is reproducibility.** Forcing the phase order is not bureaucracy for
its own sake — it is what makes the outcome *converge*. An LLM is non-deterministic: hand the same
intent to two makers (or the same maker twice) and the generated code will differ. That variation is
accepted. What must **not** vary is the *process, the contracts, the gates, and the verification*:
given the same org spec + RFP, whoever founds the company, whenever they run it, the **same phases run
in the same order, the same gates must pass, the same contracts (interfaces, acceptance criteria,
ownership seams) are satisfied, and the same verification fires.** Two people building the same spec
get systems that *satisfy the same contracts and passed the same gates* — even if the code inside
differs. This is *process-and-contract reproducibility*, and it is the whole reason to force a type:
a mold is a shape that makes many pourings come out the same. Everything in this doc — the phase
predicate (§2), the deploy spine (§3), and the reproducibility admission standard (§4a) — exists to
make that convergence hold at two levels: **Level 1**, the org itself (same spec ⇒ same process/gates,
§1–§3); and **Level 2**, the *repositories the org builds* (the dev experience a stranger clones is
the same for everyone, §4a). Non-determinism is confined to the generated code; the mold makes
everything around it reproducible.

Two clarifications the repo's own lessons force:

- **The mold is promoted by doctrine, enforced by lint — never by forced delegation.** The standing
  lesson (docs/03 §6.5, the O8/O9 teeth; the delegation-vs-knowledge resolution) is that *forcing a
  fan-out* is a design error — fan-out is a judgment — while *forcing a checkable invariant* is
  correct. The phase order is a checkable invariant: "no `design_started` without a prior
  `requirements_signed_off`" is a ledger predicate, exactly like "no `result_deployed` without a
  prior `survives`." So the mold is enforced the right way: doctrine says *this is how we build*
  (loaded every cycle), and a lint/hook tooth refuses the few transitions that must not skip.

- **The mold is a shape, not a waterfall.** Forcing the phase *order* per deliverable does not force
  big-batch sequential delivery. A deliverable is small (docs/03: near-decomposable units), and each
  small unit travels the full chain quickly and continuously — this is the always-shippable trunk, not
  a six-month cascade. The mold constrains *ordering within a unit of work*, not *batch size* or
  *concurrency across units*. Ten units can each be at a different phase at once (that is the pipeline
  of docs/09's backlog); no single unit may jump its own phases.

---

## 0a. The founding artifacts have FIXED filenames — the rule, not a suggestion

Founding (`/org-found`) runs *before* the phase chain: it turns an RFP into the org's scope and
structure. Its outputs are the base every later phase reads, so they are the one place where **file
names are part of the contract**. If founding writes `architecture.md` one time and `design-overview.md`
the next, nothing downstream can find its input without a human pointing at it — a later command, a
fresh session, or a web harness has to *guess*. That guess is exactly the tacit-not-articulated failure
the repo exists to prevent, and it breaks reproducibility at its root (§0): two foundings from the same
RFP must produce the same *addressable* artifacts, not merely similar prose.

So founding writes **exactly these four files, at the org root, under these exact names**:

| File | SDD/lifecycle role | What it holds |
|---|---|---|
| `REQUIREMENTS.md` | the received brief | the RFP verbatim (or the brief restated), + the one-sentence purpose. The immutable input the rest traces to. |
| `FEATURE-INVENTORY.md` | the 洗い出し | every capability the RFP requires, grouped must / should / nice, + the explicit EXCLUDE list |
| `ARCHITECTURE.md` | **the 全体設計書** — the whole-system design, distinct from any per-task spec | layers/components + the **seam contracts** between them, each in the normalized shape `{deliverable, standard, checker, depends_on}` |
| `coverage-manifest.md` | the RFP→contract coverage map | one row per must-have: `{rfp_capability, owning_role, deliverable, acceptance}` |

Plus `organization.yaml` (the machine-checkable side of the manifest), which already had a fixed name.

Three consequences that make this load-bearing rather than cosmetic:

- **`ARCHITECTURE.md` is the 全体設計書, and it is NOT an SDD artifact.** SDD's three layers (§4b) —
  spec / plan / tasks — live in the *Issue hierarchy* and are per-objective and per-task. `ARCHITECTURE.md`
  sits *above* all of them: it is the whole-system design the objectives are carved out of, authored once
  at founding and amended at reorg. Keeping it a file (not an Issue) is deliberate — it is not disposable
  work surface, it is the standing shape of the system. It does not contradict §4b's "no `plan.md` files":
  that rule forbids **per-task** fragment files, which rot; a single whole-system design does not fragment.
- **Downstream commands address these by name, not by search.** `/org-decompose` reads
  `coverage-manifest.md` + `ARCHITECTURE.md` to mint task Issues; `/org-init` scaffolds their paths. A
  fixed name is what lets a command take the artifact as *input* instead of asking the operator where it is.
- **The names are the same in every org.** A stranger — or an agent with none of the founding context —
  opening any orgforge org finds the design in the same place. That is Level-1 reproducibility (§0)
  applied to the founding artifacts themselves.

`ARCHITECTURE.md` (the org's own repo has one too, describing orgforge) is the whole-system design *of the
product the org builds*, written into the product/org root — not a copy of this repo's file.

---

## 0b. 要求記述の書式は規格に準拠する — 名前だけでなく中身も固定する

§0a は founding 成果物の**ファイル名**を固定した。しかし**中身の書式**を規定しなかったため、
founding のたびにエージェントが構成をその場で発明していた。同じ要求から別の構造の文書が出るなら、
「同じ spec ⇒ 同じプロセス・同じ契約」という §0 の主張は、**要求記述の層で最初から破れている**。
名前を固定して中身を放置するのは、器を揃えて中身を問わないのと同じ。

### 準拠のレベル: ISO/IEC/IEEE 29148:2018 の tailored conformance

同規格 §4.5.2 が正式に認める適合形態を宣言する。**SRS の全20条項（§9.6）は採らない** —
`Memory constraints`・`Site adaptation requirements`・`Logical database requirements` は組込み・
防衛・規制産業向けの条項で、小規模プロダクトでは空欄かボイラープレートにしかならない。
**空欄の節が並ぶ文書は読まれなくなり、やがて更新されなくなる**。採るのは次の4条項:

| 条項 | 内容 | 検査 |
|---|---|---|
| §5.2.4 | 構文規約（主語＋`shall`。`must` は要求と誤解されるので使わない） | 警告 |
| §5.2.5 | 個々の要求の特性9つ（Verifiable / Singular / Unambiguous …） | 一部を機械化 |
| §5.2.6 | 集合の特性5つ（TBD/TBS/TBR を残さない、矛盾・重複がない） | TBD を落とす |
| §5.2.7 | **避けるべき語**（主観語・最上級・抜け穴・全称語・曖昧な接続） | **落とす** |

§5.2.7 が本体である。「使いやすい」「可能であれば」「すべての場合」は、**人によって判定が変わる**
か、**実装しない口実になる**か、**例外の有無が検証されていない**。AIエージェントに渡す文としては
特に危険で、曖昧語は推測の余地としてそのまま実装に流れ込む。

### 併せて採るもの

- **EARS**（Alistair Mavin / Rolls-Royce。Airbus・NASA・Bosch・Intel・Siemens が採用）—
  6パターンと ruleset「**トリガーは最大1つ**」。この制約が**要求の粒度を構文レベルで強制する**。
  学習コストが実質ゼロで、効果が最も大きい。§5.2.5 の *Conforming* も同時に満たす
- **Given-When-Then**（Cucumber 公式仕様の Gherkin から記法だけ借用）— 受入基準。
  要求は EARS、その検証シナリオは GWT という役割分担
- **`[NEEDS CLARIFICATION]` マーカー**（GitHub Spec Kit 由来）— **最重要**。
  曖昧なまま推測で実装されるのを止める。未解決で残っていれば lint が落とす
- **Non-Goals / Alternatives Considered**（Google Design Doc 由来）— スコープクリープを止める
  最も安価な装置

規定は `template/REQUIREMENTS.md`、検査は `tools/req_lint.py`。`/org-found` が両方を呼ぶ。

### なぜ「RFP」をやめたか

RFP (Request for Proposal) は**調達文書**である。発注者が**外部の競合ベンダー**に提案を求め、
**比較評価して契約相手を選ぶ**ために発行する。中核は評価基準・配点・提案書式の指定・契約条項で、
自社開発（実装主体が単一で、内部が可視で、常時交渉可能）ではこれらが**すべて無意味**になる。

ここで書いているものの正確な対応物は 29148 の **StRS (Stakeholder Requirements Specification)**
— 発注側の視点でニーズを記述し、まだ解に踏み込んでいない文書。ファイル名は `REQUIREMENTS.md`
とする（規格の略語を背負わずに済み、誤解がない）。

RFP から借りる価値があるのは**「評価基準を事前に文書化する」規律**だけで、それは自社開発では
「**受入基準を実装前に確定する**」に翻訳される。本テンプレートでは §4（Acceptance）と
§5（Success Criteria）がそれを担い、`coverage-manifest.md` がその契約への写像を担う。

---

## 0c. 人間にしか実行できない作業も Issue にする — 散文に落とさない

§0a は founding 成果物の名前を、§0b は要求記述の書式を固定した。どちらも「org が作るもの」の話で
ある。しかし実際の founding には、**org には構造的に実行できない作業**が必ず混ざる:

- 外部サービスのアカウント作成と課金（Supabase、決済事業者）
- OAuth クライアントの登録、API キーの発行
- ドメイン取得、ストアの開発者登録と審査提出
- GitHub の管理設定（ブランチ保護、シークレット登録）

これらは org のツールでは完結しない。だから **CEO に依頼する**しかないのだが、その依頼が
コマンドの出力する散文にしか現れていなかった。実地の founding で3件が「申し送り」として文章に
書かれ、**Issue にも台帳にも残らなかった**。

### なぜ散文では駄目なのか

| 失われるもの | 具体的に何が起きるか |
|---|---|
| **永続性** | セッションが切れれば消える。`/org-resume` は ledger を読むので復元されない |
| **board の正しさ** | `/org` が「全 Issue ready・GREEN」と出すのに、実際は着手できない |
| **ready の正しさ** | 人間待ちを依存として表現できないので、ブロック済みの task が maker に渡る |
| **coverage の正しさ** | `coverage-check` は「Issue になったか」しか見ない。前提が欠けても 66/66 と出る |

とりわけ最後の例が象徴的で、**ブランチ保護の設定は §4e の機械的拒否層の一部**でありながら
GitHub の管理設定なのでコードでは実現できない。それが散文に消えると、「機械が守るはず」の層に
穴が開いたまま誰も気づかない。

### 規定

**`/org-found` と `/org-decompose` は、人間にしか実行できない前提条件を Issue にすること。**
`github_sync needs-human` がその専用の口で、`orgforge:needs-human` ラベルを立てる。

判定は単純: **org のツールで完結するか。** 完結しないなら人間タスクである。

抽出源は既に手元にある — `REQUIREMENTS.md` の **Open Questions**（「実装前に決める」と自分で
書いたもの）と **Assumptions**（「CEO が用意する」と書いたもの）は 29148 の標準節であり、
機械的に読める場所にある。§0b でその節を必須にしたのは、ここに効かせるためでもある。

立てた Issue は通常の task と同じ形なので、下流を `--blocks` と `Depends on: #N` で縛れる。
人間の作業が close されるまで、依存する task は `ready` に出てこない。

**`/org` の board では RED として最上位に出す。** 「あなたを待っている」ものこそ board の意味で
あり、それが見えないなら board は嘘をついている。

> **人間への依頼は、忘れられると最も長く止まる種類の作業である。** org が自分の作業だけを
> 構造化して人間への依頼を散文に落とすのは、いちばん止まりやすいものをいちばん失われやすい
> 場所に置くということ。逆にすべきである。

---

## 0d. 配管は自動化する、判断は自動化しない

§0a〜§0c は「何を書くか」を固定した。ここは「**誰が打つか**」の話である。

`/org-work` は long らく「こういうイベントを打て」という散文の指示だった。実行するのは
エージェントであり、実地では **Issue 2件あたり11コマンド**を手で叩いていた。18 Issue なら
約90回で、そのうち1回の取り違えで台帳の整合が崩れる。

さらに悪いのは `parent` の扱いだった。フェーズ連鎖は親 objective の admit を継承する（§2）のに、
その値を**人が Issue から目で拾って手打ち**していた。**継承を実装しても、値が手打ちである限り
取り違えが起きる** — 拾えるものを拾わせないのは設計の怠慢である。

### 線引き: 配管か、判断か

| | 例 | 誰が |
|---|---|---|
| **配管**（順序と actor が決まっている） | claim → spec_delegated → phase_started → cycle_started → log → stage / Issue ごとの worktree を切る / seam contract の生成 / 憲章とSPECの注入 / gate の所見を skeptic へ運ぶ / `decide` の雛形 | **ツール**（`org_cycle.py`） |
| **判断**（役割の仕事） | 何を選ぶか / 誰に委ねるか / 分割するか / admit するか / verdict・why・risk / どのミューテーションを試すか | **役割**（自動化しない） |

**`verify` が verdict を埋めないのは、線引きの中でもとりわけ譲れない一点である。** ツールが
verdict を決めた瞬間に gate は形骸化し、admission は「ツールが出した文字列を役割が転記する
儀式」に落ちる。埋めてよいのは**材料**（憲章・SPEC・seam・gate の所見）までで、**結論**は
役割が出す。逆に、材料を毎回人が書き下ろす状態も同じくらい悪い: 検証手順を人が書けば、
書くたびに厳しさが変わり、18 Issue なら18通りの基準になる。基準の出所は `agents/<role>.md`
ただ1つにし、変更はそこ1箇所で効くようにする。

**二重管理はしない — 書くのは1コマンド。** 判断は Issue と台帳の両方に残る（Issue に理由、
台帳に受領証と digest）が、**打つのは1回**である。以前は `decide` が Issue に書き、人が
`ledger append` を別に打つ設計で、運用では片側落ちが繰り返し起きた（反証の記録が台帳に無い、`progress_recorded` が0件）。actor は `--by` で既に
渡っているので、分ける理由が無かった。

順序は **台帳が先、Issue が後**。統制（自己承認拒否・順序違反）は台帳が持っているので、
Issue に書いてから台帳が拒否すると「Issue には admit と書いてあるが台帳には無い」という
最悪の食い違いが外に残る。拒否されるなら、外から見える記録を作る前に止める。

**冪等キーは統制の裏口になってはいけない。** 冪等 no-op は「同じ actor による同じ論理
イベントの再実行」に限る。`(class, natural_key)` だけを見ていたときは、キーさえ一致すれば
actor が違っても no-op になり、DISTINCT_ACTOR も REQUIRES_PRIOR も**評価すらされなかった** —
gate の判定と同じキーを maker が使えば、自己承認が exit 0 で通った。冪等性は再実行を守る
仕組みであって、統制を迂回する経路ではない。

**訂正は第一級のイベントである。** 台帳は追記型なので過去を消せない。誤って書いた記録も、
仕様検証のために書いたプローブも、そこに残り続ける。これを自由記述の注記で済ませると
**機械が読めない** — 検証用のプローブが実判定として集計され、board が「admit 済みだが
skeptic の記録が無い」と現実と食い違う表示を出し続けた。`correction{corrects, kind}` で
無効を宣言し、`kind: probe|mistake` は集計から除外する。`backfill`（後から書いた実判定）と
`superseded`（後続判定で置き換わった）は除外しない — 前者は有効な判定であり、後者は
「同一 deliverable は最新判定が有効」という時系列の解決が扱う領域だからである。

**識別子の揺れで統制が消えてはいけない。** 人間側は Issue 番号（`deliverable` / `issue`）で
書き、強制ロジックは `candidate_id` / `claim_id` を見ていた。同じ仕事を指しているのに片方しか
見ないため、実地では自己承認も、反証を経ない deploy も素通りした。書き手がどのキーを使ったかで
統制の有効性が変わるなら、それは統制ではない。台帳にある対応関係（`pack_manifest_id: "issue-7"`
など）を辿って同一性を解決し、**相関の取れない判定は拒否する**。素通りが最悪なのは、統制が
効いていないことが誰にも見えないまま、ハッシュ連鎖が偽造にお墨付きを与えるからである。

**worktree は「判断で守れない不変条件」の実例である。** 並列 fan-out で、ある Issue のコミットが
`feat/issue-8-settle` に載る事故が実際に起きた。`git checkout` はツリー全体を切り替えるので、
同一ツリーで並列 maker を走らせる限り、注意深さの問題ではなく構造の問題として再発する。
**「毎回正しく判断する」前提の設計は破れる** — だから `begin` が `.orgforge/wt/issue-<N>/` を
物理的に分ける。これは forced invariant であって forced delegation ではない。

これは docs/03 §6.5 の線引きをそのまま踏襲している — **forced delegation は設計エラー、
forced invariant は正しい**。`org_cycle` が自動化したのは後者だけで、fan-out するかどうかも、
admit するかどうかも、依然として役割の判断である。

### 三つの性質

1. **自動解決** — `parent` は Issue の `Parent: #N`（`create` が書く）とネイティブ sub-issue API
   から解決する。`candidate_id` は Issue のトレーラから読む。**人が値を運ばない**
2. **止まったら止まったまま** — 途中で失敗したら、そこから先は打たない。部分適用のまま
   「成功」と報告するのが最悪（台帳の整合が崩れた状態を正常と見せる）
3. **再実行が安全** — 各イベントは natural-key で冪等なので、済んだ分は no-op になる。
   だから「止まったら直して再実行」が成立する

`plan` サブコマンドは**何も実行せず**イベント列だけを印字する。打つ前に確認したいとき用。

---

## 1. The seven phases and what each admits

Each phase produces an artifact the next phase depends on, and each transition is a **gate**: the
next phase may not start until the prior phase's artifact carries an admission verdict in the ledger.
The gate is the generalization of docs/03's `output_to: gate → skeptic` and docs/09's
`conformance_reviewed` — the same `requires_prior` predicate, one row per phase boundary.

| Phase | Produces | Gate to enter the *next* phase (the `requires_prior`) |
|---|---|---|
| **requirements** | a stated intent + acceptance criteria (what "done" and "valuable" mean) | `requirements_signed_off` — the intent is grounded in the purpose (Organ 1), not in volume |
| **design** | an approach + the seams it will touch (`owns:` sets, interfaces) | `design_reviewed` — conforms to the requirement (docs/09 A3 conformance, applied one phase up) |
| **implement** | the deliverable | the maker's own `judge` (docs/03 §3.1.1 — *not* admission) |
| **test** | evidence the deliverable meets the acceptance criteria (its own unit tests green) | `admission_decided{admit}` by the **gate**, then `refutation_attempted{survives}` by the **skeptic** (docs/03) — the existing maker→gate→skeptic chain, per-unit |
| **integrate** | the unit merged into the integration branch (`develop`) and passing the *combined* suite alongside its siblings | `integration_admitted` — the fanned-out siblings build and test **together** green on `develop` (§4c). This is where fan-out fans back in; green CI on `develop` is its machine form |
| **deploy** | the change, live (`develop` → `main`) | `result_deployed` — requires the prior `survives` (today's schema) **and** a healthy reliability budget (docs/05 §reliability-budget); CI/CD is the spine (§3) |
| **operate** | monitoring, corrective fixes, the realized-outcome record | `outcome_recorded` (docs/05 OUTCOME-DELTA) feeds back to requirements — the loop closes |

The important observation: **the repo already implements the two hardest gates.** The
test→integrate→deploy boundary *is* the maker→gate→skeptic chain from docs/03 (`result_deployed` already
requires a prior `survives`). The design→implement conformance *is* docs/09's `conformance_reviewed`.
This doc's job is only to (a) name the phases as a chain so the *earlier* boundaries
(requirements→design, design→implement) get the same `requires_prior` treatment, and (b) give the
deploy and operate phases their home (§3, §4).

---

## 2. Enforcement: the phase-gate tooth (generalizing `requires_prior`)

The ledger already refuses `result_deployed` without a prior `refutation_attempted{survives}`, and
refuses `report_up` without a prior `conforms` (docs/09). The phase mold adds the analogous refusals
for the earlier boundaries, as one uniform predicate:

```
phase_started{deliverable, phase: P}  is INVALID unless
    the ledger holds  phase_admitted{deliverable, phase: prior(P), verdict: pass}
```

where `prior(requirements)=∅` (the first phase needs no predecessor), `prior(design)=requirements`,
and so on. This is deliberately the *same shape* as `result_deployed requires_prior survives` — a
new operator would be a second mechanism to maintain; a reused predicate is one mechanism pointed at
a new set of events.

**Where the tooth lives** follows docs/10's request-vs-enforcement split exactly:

- **Doctrine (the request layer, p<1):** every cycle's context pack carries "we build through the
  phase chain; do not skip." This is where the *norm* lives — it makes the right thing the default and
  is cheap to update as practice evolves (docs/06).
- **The ledger append (the enforcement layer, p=1):** the refusal is enforced at **`ledger.py append`**
  — appending a `phase_started` whose predecessor is not admitted is **rejected** (`REQUIRES_PRIOR`,
  the same code path that rejects `result_deployed` without a `survives`). This is the deterministic
  point where the mold bites: a maker cannot *record* starting a phase out of order, so it cannot
  legitimately do the work — the ledger is the single writer and it refuses. The gate only bites when
  the flow **emits** the phase events, so `/org-work` emits `phase_started` at delegation (docs/org-work
  §2b) and the gate agent emits `phase_admitted` as it clears each phase — without those emits the
  predicate is dormant, which is why the wiring, not just the predicate, is the enforcement.

This is the whole enforcement story: no forced delegation, no new organ, one predicate generalized,
enforced at the ledger append and fired by the work cycle's emits. (An `org_lint` static check that an
org's routing can't reach deploy skipping a predecessor is a possible *additional* belt-and-braces
tooth, but the load-bearing enforcement is the append-time `requires_prior`, not a lint.)

---

## 3. Deploy is a phase, and CI/CD is its spine (R0-consistent)

The deploy phase is where "always-shippable" becomes real, and it is realized on the **host**, not
built by the org — the same R0 discipline as scheduling (docs/08). A software company's deploy spine
is **CI/CD (GitHub Actions)**: the org *declares intent* into a workflow (build, run the test phase's
evidence, gate on `survives` + budget, then release), and the host runs it. The org authors and
maintains the workflow as an owned asset (a maker deliverable, gated like any other); it does not
implement a pipeline runner. GitHub Actions is to the deploy phase what cron/`/loop` is to the
metabolism: a host primitive the org borrows.

This makes the deploy gate concrete and auditable: a green pipeline that includes the `survives`
check and the budget check *is* the machine form of `result_deployed`'s `requires_prior`. The
enforcement is not a hook watching a human — it is the pipeline refusing to release without its
predecessors, on infrastructure the industry already built.

docs/08 gains one delegation row for this (CI/CD + deploy target = host-provided); this doc names why
the deploy phase belongs there.

---

## 4. Operate closes the loop back to requirements

The operate phase is not the end of the line; it is the edge that makes the chain a *loop*. What a
deployed change actually did in the world is recorded (docs/05's OUTCOME-DELTA — the realized outcome
joined to the decision that predicted it), and that record re-enters as evidence for the *next*
requirement: the aspiration levels of problemistic search (docs/09) and the DORA metrics that
navigate to the moving bottleneck (docs/05 §DORA) both read from here. "The system and the
organization grow together" (THEORY §1b, Organ 7) is this edge: operate → requirements is where the
running product teaches the company what to build next, and where a repeatedly-missed outcome becomes
a reshape signal rather than a silent drift.

The reliability/error budget that bounds how fast deploy may fire is an operate-phase instrument and
lives with the other 24/7 operating events in docs/05 (it is a sibling of BLAST-RADIUS-CAP: an
aggregate limit over a window that gates action). This doc only notes that the deploy gate reads it;
the budget mechanism itself is docs/05's.

---

## 4a. Level 2: the repository the org builds must be reproducible for anyone

§1–§4 make the *org's* process reproducible (Level 1). But an IT business company's output is a
**repository**, and a repository is only reproducible if a stranger who clones it gets the same system
the maker did — installs the same dependencies, runs the same tests green, builds the same artifact,
on any machine, on any day. The generated *code* may vary (LLM non-determinism, accepted); the
**dev experience** must not. So the mold forces a **reproducibility admission standard** on the
repositories it produces, checked at the implement → test → integrate → deploy gates exactly like any other
`requires_prior` — a deterministic tooth, not a maker's "I verified it" self-claim.

A candidate deliverable is **not admissible** past the phase named unless its repository carries:

| Artifact | Phase gate | Why it is a reproducibility requirement |
|---|---|---|
| **A committed lockfile + a populated, version-pinned manifest** | implement → test | `clone → install` must resolve to *one* dependency tree on every machine and every day; a manifest with version ranges and no lockfile resolves differently over time (the タテカエ failure: manifest with no deps, no lock). |
| **A pinned toolchain** (`.nvmrc` / `.tool-versions` / `engines`, per-language) | implement → test | the same source transpiles/builds/tests identically only on a pinned runtime; an unpinned node/deno/python floats the result. |
| **A one-command setup and a one-command test, documented in a README** | test → integrate → deploy | "verified end-to-end" must be reproducible *by a stranger from a clean clone*, not asserted by the maker; the **gate re-runs both from a fresh checkout** rather than trusting the claim. |
| **Idempotent, re-runnable migrations + a one-command DB bring-up** | test → integrate → deploy | a second developer must be able to bring up state deterministically; bare `create table` (no `if not exists`, no seed, no apply command) is not re-runnable. |
| **A committed `.env.example` enumerating every required variable (names only)** | test → integrate → deploy | the *set* of required secrets must be discoverable, or a stranger's setup fails with no manifest of what to provide (secrets themselves stay gitignored). |
| **A committed CI workflow (GitHub Actions) that runs setup + test from a clean clone, and is green** | deploy | this **is** the machine form of the deploy gate (§3): a green from-clean pipeline is reproducibility *proven continuously*, not a one-time local pass. The doctrine already names CI/CD (docs/01 J12); this makes it an admission artifact, not an aspiration. |

The enforcement mirrors §2: **doctrine promotes** ("we ship repos anyone can clone-and-run" — in the
maker and gate contracts), and a **deterministic lint tooth enforces** the checklist at each gate.
That tooth is `tools/repro_lint.py` — `repro_lint check <repo> --phase implement|test|deploy` returns
0 (artifacts present) or 10 (HOLD: a required artifact is missing), tagged by the phase that first
requires each artifact, so an implement candidate is held to a lighter bar than a deploy one. It is a
*presence* check (deterministic: same repo ⇒ same verdict); the **deploy** gate additionally re-runs
setup + test from a clean clone (the CI workflow, §3) — presence is the cheap first tooth, the
clean-clone re-run the expensive second. This is what makes two makers, handed the same spec, ship
repositories that are *equally reproducible* — the Level-2 counterpart to the Level-1 phase gate.
Without it, the repo's dev experience is a free maker choice and diverges; with it, "clone → one
command → the same running, tested system" holds for everyone.

---

## 4e. The unread-safe bar — the diff nobody reads must still be safe to merge

§4a makes the repo reproducible for a stranger. This section addresses a different consequence of the
same fan-out: **at parallel-agent throughput, no one reads every diff.** Not the CEO, not a reviewing
agent, not the maker who wrote it. An org running many makers concurrently produces more change per day
than any reader can absorb, and the honest response is not to read faster or to throttle generation —
it is to **make the classes of defect that only a careful reader catches impossible to merge**.

This is the repo's own thesis (docs/03 §6.5) applied one level down. The standing lesson is that
*forcing a judgment* is a design error while *forcing a checkable invariant* is correct. "Review this
diff carefully" is a judgment, and it degrades silently as volume rises — a reviewer who cannot keep up
does not announce it, they skim. "No function exceeds N lines" is an invariant: it is either configured
and enforced, or it is not, and the answer is mechanical.

The bar has four teeth, checked by `repro_lint` at the phase gates (presence of the layer, not its
verdict — running it is CI's job):

| Tooth | Phase | What it stops |
|---|---|---|
| **complexity-bounded** | implement | Unbounded function size / cyclomatic / cognitive complexity / nesting depth. This is the highest-value tooth: an over-long, deeply-nested function is exactly where the defects a reader *would* have caught actually hide, and appending to a working function is the shape an agent produces most readily when the alternative is decomposing. |
| **type-escapes-closed** | implement | Strict typing off, or `any` / `@ts-ignore` / non-null assertions available. A type checker with open escape hatches is advisory: an agent under pressure to turn a build green will reach for them, and the resulting hole is invisible in a diff nobody reads. |
| **tests-present** | test | A repo whose CI proves only that the code compiles. Tests are the artifact that *substitutes* for a reader; without them the pipeline verifies nothing about behavior. |
| **no-inline-suppress** | test | Blanket inline suppressions — `eslint-disable`, `@ts-ignore`, bare `# type: ignore`/`# noqa`. A config-level exception names the file it covers and *why*, and can be audited and expired; an inline one is invisible at review time and immortal. With no reader, it is the cheapest way for an agent to make a bar stop applying. A *targeted* suppression that names its code (`# type: ignore[arg-type]`) is a scoped exception and passes. |
| **dup-dead-code** | deploy | Parallel makers re-solving each other's problems, and superseded code that is never deleted. Neither appears as a failure in any single diff — only a cross-cutting scan sees them, which is precisely what a reader-less pipeline needs. Report-only is the right default (a blocking duplication gate on day one teaches evasion, not decomposition). |
| **multi-os-ci** | deploy | Platform-specific breakage — path case-sensitivity, reserved device names, line endings, fs-watch behaviour. A team on one platform has no other real machine, so the second OS *is* the only reader that catches these. A scheduled daily job on a second OS satisfies it; it need not gate every PR. |

Three disciplines the teeth depend on:

- **Drain, then ratchet.** Turning a strict bar on over a red codebase produces a wall of failures and
  a culture of suppression comments. Land the rule as a warning, drive the count to zero, *then* make
  it an error. A bar that is on and violated everywhere enforces nothing.
- **Exceptions live in the config, with a reason.** An inline `eslint-disable` is invisible at review
  time and immortal — nobody ever deletes one. An exception in the config file carries the file it
  covers and *why*, and it can be audited and removed when the reason expires.
- **The org's own gate is not exempt.** The gate and skeptic (docs/03) are the *judgment* layer, and
  they remain — a different-lineage adversarial reader catches what no linter can (wrong requirement,
  plausible-but-false reasoning). The mechanical layer does not replace them; it removes from their
  plate everything a machine can decide, so the scarce judgment is spent where it is irreplaceable.

The relationship to §4a is worth stating plainly: §4a asks *"can a stranger run this?"* — §4e asks
*"is this safe to merge without anyone reading it?"* An org that fans out needs both, and only the
second one scales with the number of makers.

---

## 4f. Human review is retired — the Issue becomes the audit record

§4e removes the human from *reading the diff*. This section takes the consequence to its end: **there
is no human review step at all.** No person reads the change before it merges — not the CEO, not a
reviewer, not the maker in a second pass. The mechanical bar (§4e), the gate, and the skeptic are the
entire judgment layer, and CI is the only thing standing between a commit and `develop`.

That is a defensible position at fan-out scale — a reviewer who cannot keep up does not announce it,
they skim, and a skimmed review is worse than an honest absence because it launders unread code as
reviewed. But retiring the human removes something real, and pretending otherwise is how this decision
goes wrong. What it removes is the **account**: when a person approves a change, the approval is a
record that someone weighed it. Delete the person and, unless something replaces it, the change merges
with no account of why it was allowed to.

So the trade is explicit: **human review is retired; recording is not optional.** Everything the org
decides and everything it does lands on the task Issue, in enough detail that someone with none of the
originating context can reconstruct the merge months later. Two obligations follow, and neither is
advisory.

### 4f.1 Every judgment is recorded with its reasoning

A verdict without reasoning is a stamp. `admission_decided{verdict: admit}` in the ledger proves a
decision *happened* and is tamper-evident — it does not say what was weighed, what the alternative was,
what evidence was consulted, or what risk was knowingly accepted. With a human in the loop that gap was
survivable because a person remembered. With no human, an unrecorded judgment is indistinguishable from
no judgment at all.

Judgments therefore **double-write**, exactly as a settled convention does (docs/06, conventions.py):
the **ledger gets the receipt** (tamper-evident, machine-queryable, hash-chained), the **Issue gets the
reasoning** (readable, in context, next to the work it judged). The decision lives where it can be
*inferred*; the ledger records that it happened. `github_sync decide` writes the Issue side and rejects
reasoning that is empty, verdict-restating, or padding, and **requires `--evidence` for any admitting
verdict** — an admission with nothing consulted is a stamp however well the prose reads. Be precise
about what that buys: these are **shape** checks, the same class as `repro_lint`'s. They make the
laziest degradations impossible; they cannot tell good reasoning from plausible reasoning. The floor is
enforced, the ceiling is not.

**Who may record a judgment is enforced at the ledger, not asked for.** `admission_decided` and
`refutation_attempted` carry a distinct-actor predicate: the actor recording a verdict must not be the
actor who did the work it judges, and the skeptic must differ from the gate. Without that tooth a maker
could write its own admission and forge the skeptic's `survives`, and the hash chain would then
*launder* the forgery — a forged verdict is tamper-evidently recorded and verifies clean, which reads as
stronger evidence than no record at all. This is the runtime half of O6: `org_lint`'s O6 checks the
*chart* separates maker from checker; a static chart cannot see one process writing both sides at run
time. With no human able to notice, that check has to happen at write time.

What a recorded judgment carries: the **verdict**, the **reasoning** (what was weighed), the
**evidence consulted** (the command run and its real output, the CI run, the `repro_lint` verdict), the
**alternatives rejected and why**, the **standard applied**, and any **risk knowingly accepted**. That
last field matters most: a gate that admits despite a known hole must say so, or the hole becomes a
surprise instead of a decision.

**The reasoning is hashed, because a GitHub comment is not tamper-evident.** The ledger is hash-chained;
an Issue comment is editable and deletable by anyone with write access — including the agents whose work
it judges. Left there alone, an agent could quietly rewrite its own account (dropping the `--risk` it
admitted, say) and `ledger verify` would still report the chain intact: the most control-critical record
in a human-free system, stored in the one place with no integrity property. So `decide` emits a
`reasoning_sha256` over the judgment's fields, prints it in the comment *and* on stdout, and the ledger
receipt carries the same digest. Re-hashing the comment later either matches or it does not.

Two honest limits. This makes tampering **detectable, not impossible** — that is what tamper-evidence
means, and it is the same guarantee the hash chain gives. And detection requires someone to *run* the
comparison: the digest is written today, the periodic re-hash sweep is not yet an organ. Until it is,
the property holds on demand rather than continuously.

### 4f.2 The work log is maximally granular

The Issue is the org's primary work surface (it is terminal-independent and survives a context wipe),
and with review gone it is also the primary audit surface. A log entry that says "progress recorded"
satisfies the letter of logging and records nothing recoverable — it is the failure mode to design
against, not a minor lapse.

Log at every step that changed the world or changed the plan, and record what actually happened:

- **the exact command run**, verbatim and re-runnable — not "ran the tests"
- **what it returned**, the real output including failures. A log that only records successes is a
  fiction, and the failed attempt is usually the most informative entry in the Issue.
- **the files created or changed**
- **the next step** — the field a fresh session resumes from
- **what is blocking**, if anything
- **course changes with their cause**: the approach abandoned and what made it wrong. This is what
  stops the next maker re-deriving the same dead end (it feeds `nearby_deaths`, docs/06).

The bar to hold: **a stranger reading only the Issue can reconstruct what was built, what was tried and
abandoned, what was run, what came back, and why it was allowed to merge** — without the ledger, without
the transcript, and without asking anyone. If they cannot, the log is too thin, whatever its volume.

### 4f.3 The objection this must answer: comprehension debt

docs/12 §1 names the Software Factory's defining failure mode — **comprehension debt**: *run the factory
for months with no human reading output and green tests hide eroding understanding* (Osmani). §4f
prescribes exactly the condition that doc names as the pathology. That has to be argued, not passed over
in silence, because the objection is correct as far as it goes: **green tests are not comprehension.**

What §4f actually claims is narrower than "understanding does not matter." It is that *reading every
diff* was never what produced understanding — at fan-out volume it produces the **appearance** of
understanding, which is worse than its absence because it licenses trust. A reviewer who cannot keep up
skims, and a skimmed diff enters the record as reviewed. Retiring the ritual does not create the debt;
it stops mislabelling it as paid.

But something must actually pay it, and §4f names two things that do — neither of which is "CI is green":

- **The domain model must grow every cycle (§4d).** This is the load-bearing answer. The ledger *rejects*
  a `cycle_completed` that does not state what the cycle did to the domain model — either a settled rule
  co-committed with the code, or an explicit `none_asserted` a skeptic can refute. Comprehension debt is
  precisely the failure to convert work into durable understanding; §4d makes that conversion a
  **write-time precondition of finishing**, not a discipline someone remembers. A factory that cannot
  record a completed cycle without saying what it learned is not accruing the debt Osmani describes.
- **The Issue audit record (§4f.1/§4f.2).** Comprehension is recoverable when the reasoning, the
  alternatives, the accepted risks, and the failed attempts are written down at the moment they were
  live. The bar in §4f.2 — a stranger reconstructs the merge from the Issue alone — *is* a
  comprehension standard, and it is checkable in a way "did someone read it?" never was.

The honest residue: this is an **argued substitution, not a proven one.** docs/12 §5 is right that
orgforge has not run long enough to have met this failure, and §4f does not change that. What §4f does
is make the substitution explicit and falsifiable — if the domain model stops growing (§4d's
`none_asserted` rate climbs) or Issue records thin out toward the floor, the debt is accruing and the
sensor should say so. Treat that as the open question it is; do not treat green CI as its answer.

### 4f.4 What this does not license

Retiring human review removes a *reading* step; it does not remove the *judgment* layer. The gate and
the skeptic remain, and their independence remains load-bearing — O6c's distinct-lineage rule matters
more without a human backstop, not less, because a puppet checker is now the only checker. Nor does it
license skipping a phase: the mold (§2) is unchanged. And the CEO's charter-tier decisions (founding,
irreversible moves, scope) are still human — what is retired is diff review, not governance.

---

## 4d. The domain model must grow every cycle — SDD runs ON a rising context base

The point of SDD in orgforge is not to write specs in a vacuum — it is to implement **on top of a
domain model that is already rich**, so the LLM's context is *raised* before it writes a line, and then
to **raise it further** with what this cycle settled (the user's AI-DLC thesis: context accumulates as a
by-product of work, co-committed with the code, docs/12 §3.3). A cycle that produces code but leaves the
domain model untouched silently lets the context base rot — the same fragment-decay the whole system
exists to prevent, one level down.

So the domain-model update is **forced, not encouraged**. Every `cycle_completed` must carry a
`domain_model` field, and the ledger **rejects the append without it** (the same `requires_prior`
machinery as the phase gate). It is the explicit-negative pattern: either

- `domain_model: {updated: [<convention_ref / domain-model artifact>]}` — this cycle co-committed a
  settled rule / boundary / ubiquitous-language term (via `conventions adopt`, checker-adopted, or an
  ADR/domain-model file in the product repo, co-committed with the code it governs), **or**
- `domain_model: {none_asserted: "<why>"}` — this cycle established no new domain rule (a bugfix, a
  refactor) — an *explicit claim the skeptic can refute* ("you changed the money-split rounding and
  didn't record it").

"Forgot to update the domain model" therefore cannot happen silently: the cycle cannot be recorded
complete without stating what it did to the SSoT's domain-model half (conventions + org spec, docs/12).
That is what makes the context base *compound* — each SDD cycle both consumes the risen model and
raises it for the next, instead of every cycle re-deriving the same ambiguity.

---

## 4b. The spec / plan / tasks layering — SDD, mapped onto the Issue hierarchy

The canonical Spec-Driven Development form (GitHub Spec Kit, AWS Kiro; docs/sources) splits the front of
the lifecycle into **three artifacts**, each a checkpoint before the next: **spec** (WHAT — user stories
+ acceptance criteria), **plan** (HOW — architecture, data model, API contracts, libraries), **tasks**
(the WHAT broken into *atomic, independently-completable units* with dependency order, a parallel marker,
and exact file paths). orgforge adopts this layering — but it does **not** create `spec.md`/`plan.md`/
`tasks.md` *files* (that is the fragment-Spec trap docs/12 §6 forbids; the SSoT is code + the domain
model, not a pile of task files). Instead the three layers **map onto the GitHub Issue hierarchy** the
org already has (docs, web-harness):

| SDD layer | orgforge home | contents |
|---|---|---|
| **spec** (WHAT) | the **objective Issue** (`kind:objective`) | user stories + acceptance criteria in **EARS** (below); tech-stack-agnostic |
| **plan** (HOW) | the objective's **design** (its body / a design comment), admitted at the `design` phase | architecture, data model, API/seam contracts, library choices |
| **tasks** (atomic units) | the **task sub-issues** (`kind:task`), one per atomic unit | each an independently-completable unit (one endpoint/function, not a whole domain), with `depends_on` (order), a boundary (`owns` disjoint from siblings = the `[P]` parallel-safe marker), and its entry files (the exact paths) — the SPEC structure |

**Acceptance criteria use EARS** (Easy Approach to Requirements Syntax) so a MUST is testable and
AI-parseable, not prose: *Ubiquitous* ("the system SHALL log every auth attempt"), *Event* ("**WHEN** a
user submits login **THE system SHALL** validate credentials"), *State* ("**WHILE** a sync runs **THE
system SHALL** show progress"), *Unwanted* ("**IF** validation fails 3× **THEN THE system SHALL** lock
the account"), *Optional* ("**WHERE** MFA is enabled **THE system SHALL** require a TOTP"). The SPEC's
MUST list (template/SPEC.md) is written in these five patterns.

The upshot for granularity (the "split finer" concern): **a task sub-issue is ONE atomic unit**, not a
domain. The discriminator is the `owns` set — split at every seam where sibling `owns` sets are disjoint
and `depends_on` is a pinned one-directional contract (`[P]`-parallel-safe); keep single-threaded only
what needs reciprocal back-and-forth (docs/03 §6.2 — over-splitting coupled work is 17× worse, docs/12
§6). A lint flags an Issue whose acceptance criteria span multiple disjoint `owns` territories as a
re-split candidate (a *shape* check, not a quality judgment).

---

### 分割の判断軸 — SDD の既存ツールが持つもの、持たないもの

タスクへの分割基準を Spec Kit と Kiro の実テンプレートで確認した（原文は docs/sources）。

| | Spec Kit | Kiro | orgforge |
|---|---|---|---|
| 分割の第一軸 | ユーザーストーリー（P1/P2/P3） | design のコンポーネント + 逐次の依存連鎖 | coverage-manifest の must-have 行 |
| 並列の判定 | `[P]` = *"different files, no dependencies"* | 概念なし（逐次前提） | `owns` の交わり（= Spec Kit と同じ判定） |
| 粒度の明文規範 | 実質なし（"exact file path" 必須 + *"not vague"*） | *"Implement X function" rather than "Support X feature"* | 「壊れ方が1種類か」（下記） |
| **過大タスクの検出** | **なし** | **なし**（人間の承認ゲートのみ） | `split-check`（警告） |
| テスト | OPTIONAL（明示要求時のみ） | TDD 既定 | 必須（機械バー docs/11 §4e） |

**`owns` の交わりだけでは足りない、というのが実地で最も高くついた発見である。** これは
Spec Kit の `[P]` と同じ判定であり、**同じ限界を継承していた**: `owns` が `supabase/` に
1つのディレクトリに閉じていた Issue は分割されなかったが、中身は「スキーマの形（型・制約で守る）」と
「認可（攻撃シナリオで守る）」という壊れ方も検証手段も別の2つだった。結果、gate が14回の
判定のうち一度も同じ観点で連続できず、複数のマイグレーションが相互に干渉し、10周を超えても終わらなかった。
同じ日に #8（1つの関数）と #10（CI 設定）は1〜2周で通っている。

そこで軸を1本足す:

> この deliverable が壊れたとき、**壊れ方は1種類か**。検証に必要な手段は**1種類か**。

Kiro の *"Implement X function" rather than "Support X feature"* は、同じことを別の言い方で
述べている — 機能単位ではなく、**1つの壊れ方に対応する単位**に落とせ、ということである。

**過大タスクの検出は、調べた範囲のどのツール・手法も持っていない**（docs/sources）。
Spec Kit の `analyze` に粒度の検査は無く、Kiro は人間の承認ゲートのみ。BMAD は同じ機能要求
（Issue #1471「タスク数が閾値を超えたら分解エージェントを起動」）が**未解決のまま放置**され、
学術側の AQUSA も Estimatable（サイズ過大）の自動化を「意味理解を要する」として明示的に
諦めている。定量的な閾値を持つのは Devin の *"if a task would take you three hours or less"*
だけで、それも事前 lint ではない。人間の diff レビューを廃止した org（§4f）では承認ゲートが
無いので、`github_sync split-check` が起票後に警告を出す — 壊れ方が複数か、認可の要求が
境界だけを定めていないか。**止めない、警告する**: 何を守るべきかは人が決める。

**「同じファイルを触るか」を分割基準にすることは、既存の規範体系ではむしろ反パターンである。**
Humanizing Work の垂直スライスの定義は *"a work item that delivers a valuable change in system
behavior such that you'll probably have to touch multiple architectural layers"* — **複数層に
触ることを肯定的に含む**。層ごとに割る（UI で1つ、DB で1つ）のは independent と valuable に
反する失敗パターンとして名指しされている。Tessl の spec:code 1:1 写像は逆の極で、Fowler の
分析はそれを「コンポーネント横断の合成を制限する」限界として指摘している。

orgforge の `owns` 基準は**衝突の回避**（並列 maker が同じファイルを書かない）には正しいが、
**分割の判断**としてはこれ1本では足りない。だから「壊れ方」の軸を足す。

### 検査を呼ぶかどうかを、検査される側が決めてはいけない

`integrate` は gate の admit と skeptic の survives が台帳にあるかを確認して止める。しかし
**呼ばれなければ何も起きない。** 運用では、質の高い maker 報告を受けた監督が `git merge` で
`develop` に入れ、gate も skeptic も通らないまま複数の deliverable が統合された。台帳は後から
正しく拒否したが、拒否が来たのは**コードが入った後**である。

これは「検査対象そのものの有無で判定するな」と同じ構造で、一段上にある: **道具の中に検査を
足しても、その道具を呼ぶかどうかが呼ぶ側の裁量なら、検査は選択制になる。** 呼ばなかったことを
検出できるのは、呼び出しの外側にある層（PreToolUse フック）だけである。

同じ形の穴が Issue の操作にもあった。`gh issue create` は `dept` / `objective` / `parent` /
冪等キーを付けず、`gh issue close` は `cycle_completed`（`domain_model` を必須とする）を残さない。
organ を通さない書き換えは、記録の必須項目を丸ごと飛ばす。

**hold には打つべきコマンドを必ず添える。** 迂回は速さのためではなく「道具の名前を思い出す
コスト」を払わなかったために起きる。コマンドが目の前にあれば迂回する理由が消える。逆に hold
だけして代替を示さないと、**逃げ道の宣言が覚えられて常用され、迂回が記録に残らないまま
高速化する** — それは hold が無い状態より悪い。

**逃げ道は用意し、通ったことを記録する。** 完全に塞ぐと壊れたときに詰まるので、明示の宣言
（`ORG_ALLOW_MANUAL_MERGE` / `ORG_ALLOW_MANUAL_GH`）で通せるようにし、**その宣言自体を
`bypass_declared` として台帳に残す**。塞げないことを記録する形である。

### 検査は、自分が要求している文面と同じ厳しさで書く

ガードのメッセージが「子プロンプトの**冒頭に1行**書く」と言っているのに、検査は**全文の部分
一致**だった。結果、**否定文が宣言として通った** — 「contract も `INDEPENDENT:` も付けて
いません」がそのまま独立宣言として一致した（実地のプローブ）。

実害のある形は「この作業は independent ではないので contract を付ける」と書いた spawn が
独立宣言と誤判定されることで、**独立宣言は `owns` の宣言を免除する**ので、偶然の一致で免除が
取れる。**検査が文面より緩いと、正しく書いた人だけが厳しい制約を負う。**

同じ穴が seam 側にもあった: `"seam contract"` という**語**を見ていたため、「no seam contract is
attached」が宣言として通った。語ではなく**構造**（`## Your slice` / `Inputs you receive:` /
`Outputs you MUST produce:`）を見る — 構造は否定文に現れない。「`Inputs you receive:` が無い」と
書くことはあっても、コロン付きの見出しを否定文の中に置くことはまずない。

**一般形**: 宣言や約束を検査するなら、**それが現れる位置と形**を見る。散文に混ざりうる語だけを
見ると、その語について語っただけで検査を通過する。この org が繰り返し塞いできた「確かめて
いないことを確かめたかのように述べる」の、**道具側の変種**である。

### 観測経路が値を隠すことがある

`intake` が「本命ケースだけ exit=0」と報告されたが、実装は3経路すべてで 10 を返していた。
原因は**パイプ**で、`| tail` を通すとシェルの終了コードは最後のコマンドのものになる。

**実装が正しくても、観測が違えば同じように誤判断が起きる。** 終了コードで判定させる設計は、
パイプを挟まれた瞬間に無効になる — 機械が拾う判定は**出力の中**にも置く（`INCOMPLETE` の1行）。

### 報告の切断 — 判定として読む前に、形を見る

subagent の turn が**作業の途中で終わる**ことがある: `status` は
completed で返り、`result` は「Now the key attack:」のような宣言1文だけ。`SendMessage` で
再開させると続きを実行して完走したので、**agent が死んだのではなく、報告が成果物の形になる
前に turn が終わっている**。

**危ないのは、それらしく切れた形である。** 「Now the key attack:」なら verdict が無いと分かる
が、「MUST 2 は防がれました」で切れていたら、それを verdict として読んで admit しかねない。
この org が繰り返し検出した「確かめていないことを確かめたかのように述べる」が、**報告の切断**
という経路で成立する — 誰も嘘をついていないのに、記録には確かめた判定が残る。

`org_cycle intake` が役割ごとの必須要素だけを見る（skeptic/gate は verdict と実行の痕跡、
maker はコミットと DoD の実測出力）。**verdict の中身も妥当性も見ない** — 判定は役割の仕事で
あって、見るのは「報告が成果物の形になっているか」だけである。

**「途中で切れたように読める語」を根拠にはしない。** `Now …` `次に…` のような語で判定すると、
丁寧に途中経過を書いた完全な報告を弾く。必須要素が揃っていれば完走とみなし、語は補足として
添えるだけにする。

### 速さを変えるなら、支配的な項を測ってから

「全体的に遅い」に対してモデルや effort を下げるのは、**削る対象が支配的でない限り効かない**。
実運用で測った（n=52、完了通知の `duration_ms`）:

```
maker 486.7s (54%) · gate 260.2s (29%) · skeptic 169.3s (17%)
1周 ≈ 15.3分 ／ 反証による周回 = 214分 / 269分 = 79%
```

**「1回の待ち時間」は21%しかなく、79%は周回数である。** さらに gate/skeptic のモデルを下げれば
判定の質が落ち、周回が増えて**逆に遅くなる**。効くのは分割と完了の定義（§4b）であって、
モデル層ではない。

3つ、判断を誤りかけた点を記録する:

1. **「実装役が過半だから質が足りていない」は誤り。** 最長の1回は数百行の SQL とテスト数十件に
   対応する量で、遅さではなく仕事量だった。同じ成果物で skeptic が「一手隣」を探して見つけられず
   「列挙をやめて述語に置き換えたので原理的に出にくくなっている」と述べた — **maker の設計判断が
   反証を止めた実例**である。
2. **「registrar を下げるのが唯一の安全な候補」も無意味。** 実運用で0回呼ばれており、効果が
   測れない。安全性だけを見て**効果を見ていなかった**。
3. **測れなかったものを判断材料にしない。** `registrar` の所要時間と `org-tick` の挙動は未測定
   であることが明示され、それは判断から外した。

唯一削れたのは**プロンプトの重複**だった（`verify` が gate の最新判定を判定履歴と `prior` の
2箇所で出しており、skeptic 457行のうち46行超が重複していた）。これは実測で見えた項であり、
推測で下げたものではない。

### 監督（supervisor）自身の記録も検査する

この org は **maker の成果物**（`cycle_completed` が薄い `--result` を拒否）と **gate/skeptic の
判定**（`decide` が verdict の言い換えを拒否）を機械で検査している。**監督の記録だけが検査されて
いなかった** — 運用して見ると、監督の失敗の多くが道具の側で捕まえられる形だった。

この org が同じ晩に8回検出した失敗様式は「**確かめていないことを、確かめたかのように述べる**」
であり、それが**成果物 → 判定 → 道具 → 監督**の4層すべてに現れた。**最初の3層には機械の検査が
あり、4層目にだけ無かった。**

| 何が漏れたか | 実測 | 対策 |
|---|---|---|
| rework の発注が台帳に残らない | reject/refuted の多くに対し `rework_requested` が無い（4回 reject されて記録0件の Issue もあった） | `org_cycle rework` を専用コマンドにし、`verify` が reject 時に**判定の記録と同じ場所**でそのコマンドを出す |
| 要約が条件節を落とす | maker の「**このブランチにはまだ無い**」が監督の要約で消え、それが gate への指示に流れて reject 事由になった | `decide --claimed / --verified` に分け、条件節が `--verified` で触れられていなければ警告 |
| 古いパスの流用 | 0.26.0 のリリース後も 0.25.2 のパスを打った | 実行時のバージョンと cwd を stderr に1行 |

**rework の記録漏れは、道具の警告を沈黙させた。** `show` の rework 警告（3回超で出る）は台帳の
`rework_requested` を数えるので、監督が記録しなければ閾値に届かない — **道具は数えられないものを
数えない**。専用コマンドが無く `ledger.py append --payload '{...}'` を手で組む必要があったことも
漏れの一因である（発注は「判定 → 検証 → decide → **発注** → 記録」の順で、発注した subagent の
通知が来ると記録が流れる）。

**この検査は完全ではない。** `--verified` は「確かめた」と書くだけでも通り得るので、実行の痕跡
（コマンド名・出力・exit）を粗く見ているが、それ自体が「コマンド名を書けば通る」形式化を招く。
**塞げないことを正直に記録する**のがこの org の規律である。根拠として、`cycle_completed` が薄い
`--result` を拒否したとき監督は実際に測り直した — 拒否が形式的な壁ではなく行動を変えた実例が
ある一方で、それが常に成り立つ保証は無い。

**worktree の占有ロックは、意図的に入れていない。** 「gate の稼働中に監督が同じ worktree で
変異検査を走らせ、skeptic が偽の失敗を観測した」という実害があり、占有の警告は筋が通る。しかし
同じ晩に gate が異常終了しており、**ロックの解放漏れが新しい詰まりを生む経路が実在する**。
上の3件を入れたあとの再発を見てから判断する — 詰まりを直すために別の詰まりを作らない。

### 指示と権限を食い違わせない

subagent に**渡っていない権限を要求する指示**を書いてはいけない。実地では `agents/gate.md` と
`agents/skeptic.md` が「判定を台帳と Issue の両方に記録せよ」と指示していたが、subagent には
`ORG_GITHUB_REPO` も台帳のパスも渡っていなかった。結果、gate と skeptic が繰り返し、判定を出した
後に「記録は監督に委ねます」と述べて止まり、**一度は判定そのものが台帳に入らないまま失われ
かけた**（監督が `org_cycle show` で気づいて再開させた）。

寄せる先は2つあり、**判定を返すところまでを subagent の責務とする**ほうを採った:

| | 内容 | 判断 |
|---|---|---|
| (a) 記録権限を渡す | subagent に env と書き込み権を渡す | 採らない — 判定者が記録も持つと、独立性の検査（台帳の DISTINCT_ACTOR）が形式化しやすい |
| (b) 責務を判定に絞る | verdict / why / evidence / standard / risk を**返す**まで | **採用** — 記録は監督の仕事。実地でも subagent は判定に集中したほうが質が上がった |

`verify` の出力も分けた: **stdout（subagent に渡す本文）には記録コマンドを載せず**、
「返すもの」の指定だけを置く。監督が打つコマンドは **stderr**（監督向け）に出す。
配管が判定を運べなくなっては本末転倒なので、両方を残しつつ宛先を分ける。

### 道具は「見ていない」ことを言う

`repro_lint` は baseline との差で「この変更で新たに悪化したか」を判定する。baseline が無い
とき、以前は失敗全件に「これらは baseline に無い＝この変更で新たに悪化した」と付けていた —
**読んでいないものについて断定していた**。実地で gate がそれを額面どおり受け取り、既存の
負債を新規の悪化と読んで判定を止めた（対象の Issue は、まさにその項目を緑にする作業だった）。

いまは「baseline が無いので、この変更による悪化か既存の負債かは**判定していない**」と言う。
**何も言わないより、「この道具はここを見ていない」と述べるほうが、判定する側は正しく動ける。**
`/org-init` も baseline を1回取るようにしたので、新規 org が最初の gate 判定でこれを踏むことは
なくなる。

### 新しい検査を入れる前に — 実データで回す

検査（lint / 警告 / 検出器）を足すときは、**合成したテスト文書ではなく、実際に運用中の
成果物で回してから出す**。合成データは検査の設計を反映して作られるので、必ず通る。

実地で2回同じ失敗をした:

- `req_lint` の VOIDDEP（0.25.0 → 0.25.1 で取り下げ）— 合成文書では検出・非検出とも正しく
  動いたが、実際の `REQUIREMENTS.md` にはバッククォート識別子が **0 件**で、**一度も発火
  しなかった**。日本語の要求は「利用者が表示名を変更したとき」と書くのが自然で、識別子記法は
  使わない。
- テスト側の同型（0.22.1）— `CLAUDE_PLUGIN_ROOT` を設定してから呼ぶテストを書いたため、
  **env が無い経路＝実際の使われ方**を検査しておらず、分割で verify が死んだのを見逃した。

どちらも「テストは書いてある・green である」を満たしている。**壊れる場所で検証していない
テストは、無いのと同じ**（この org が製品側で捕まえたのと同じ形が、道具の側にある）。

そして**誤検出しかしない検査は、無いより悪い** — 誤警告は正しい警告まで無効化する（実地では
`complete` の狼少年が Issue コメントの目視統合を招き、台帳側の記録が落ちた）。届かないと
分かった検査は、作り込むより**取り下げて理由を残す**ほうが安い。

### 判定者の血統は、宣言ではなく実行で分かれる

`role-settings.yaml` は skeptic に gate と別の系統を宣言できるが、**同一ハーネスの subagent は
親のモデルを継ぐ**ので、宣言だけでは血統は分かれない。checker が maker と同じ base model なら、
盲点も共有する。分けるには**別のハーネスで実際に走らせる**必要がある。

分ける場合、**judge は2人になる**（同一ハーネスの subagent と、別ハーネスの headless）。ここで
決めておかなければならないのは、**2つの判定が食い違ったときにどう扱うか**である。決めずに二重に
すると、監督が都合のいい方を採る余地が生まれ、**検査を増やしたのに緩くなる**。

採るのは「片方でも否なら否」— 厳しい側に倒す形である。多数決は 1:1 で決まらず、監督の裁量に
戻る。そして **この一致要求は判定を採用する側（`decide`）が持つ**必要がある。判定を並べて見せる
だけなら、それは「検査を呼ぶかどうかを検査される側が決めている」構造に戻る。

**食い違いは異常ではなく、血統を分けた目的である。** 消さずに数えること。

### read-only の judge は、実行を要する MUST を admit できない

judge を read-only で走らせるのは正しい（別ハーネスのガードレールが未検証でも、書けないなら
安全側に倒れる）。ただしその選択には構造的な帰結がある — **テストの連続実行・実 DB への到達・
ビルドを要する MUST は再導出できず、`park` になる。**

`park` は正しい振る舞いである（測れないのに admit しない方が望ましい）。だが判定を回してから
分かるのは無駄なので、**その MUST が admission の荷重を持つなら、判定の前に監督が実測して
evidence として渡す**。道具は判定の前にこれを告げること。

### 1件ごとの検査は、共通因子を見ない

gate・skeptic・repro_lint・intake はすべて **1件ごとの判定**である。1件ずつ正しく効いていても、
「今夜 reject が18回出た、その事由の共通因子は何か」を見る組織が無い。**同じ因子で複数落ちて
いるなら、直すべきは個々の成果物ではなく、その因子を生んでいる側**かもしれない — spec の書き方、
gate に渡している基準、conventions、分割の粒度。

これは判定ではなく**材料の提示**である。どれを直すかは監督が決める。道具が「spec が悪い」と
決めた瞬間、それは judge になる。

**台帳だけでは事由を数えられない。** 判定イベントの payload は `reasoning_sha256` しか持たず、
散文は Issue コメントにしかない。台帳で「どの Issue が何回落ちたか」を確定させ、事由は Issue
から読む。そして**構造があるものを本文検索で当てない** — コメントを丸ごと正規表現に掛けると
maker の報告や rework 指示まで拾い、8因子のうち4つが全 Issue に該当して分布が消える（実測）。

### 拒否できることを確かめて、通せることを確かめない

新しい検査を入れたら、**拒否される側と通る側の両方を実データで回す。** 拒否だけを確かめると、
「何をしても通らない」検査を通してしまう。

実例: 2血統の一致を要求する検査で、片側だけの admit が拒否されることを確認して出した。しかし
**空の台帳ではどちらの順序でも拒否される**ため、その org は admit を1件も記録できなかった。
拒否の確認は「検査が働いている」ことしか示さず、**その検査を満たせる経路が存在するか**は
別の実験である。

受け入れ条件として書くなら「拒否されること」と対で「**空の状態から一巡できること**」を置く。
そして判定関数の単体テストではこれを捕まえられない — **実 CLI を空の台帳から走らせる**。

### 案内するコマンドは、打って効くところまで検査する

拒否のメッセージに「こう打てば直る」と書くなら、**そのコマンドを実際に打って、効くことを
テストする。** メッセージに正しい語が含まれていることの検査では足りない。

実例: 判定の差し替えを拒否するとき `correction` の打ち方を案内していたが、payload の形が
実物と違っていた（`corrects_seq` と書いたが、実物は `corrects: [seq]` と `kind` を要求する）。
**append は成功するので効いたように見え、しかし何も無効化されず、拒否から抜け出せなかった。**

さらに `corrected_seqs` は既定で `probe`/`mistake` だけを除外し、`superseded` は時系列の解決に
委ねている。案内する側がその区別を知らないと、正しい形で打っても効かない。**無効化の意味は
kind ごとに違う** — 消すのか、置き換えるのか、後から補ったのか。

### 「同じものを見たか」を判定の同一性に入れる

複数の judge の一致を要求するなら、**何を判定したのかを一致の条件に入れる。** verdict と役だけで
一致を数えると、別の revision を見た2つの通過が一致になる。

判定対象の同一性は commit SHA より広く取る:

    issue + role + phase + base_sha + reviewed_tree_sha + dirty + requirements_digest

`reviewed_tree_sha` を commit ではなく tree にするのは、同じ内容の commit を作り直しても対象は
変わらないからである。`requirements_digest` を含めるのは、**受け入れ基準が変われば別の判定**
だからである。未コミットの変更（dirty）も隠さない — 「clean だったふり」をしてはいけない。

そして **dirty を差分の要約で表さない。** `git diff HEAD` は未追跡ファイルの内容を含まないので、
`status --porcelain` と併せても「名前は拾うが中身を見ない」形になる。実際に、未追跡ファイルの
内容を丸ごと差し替えても id が一致した。judge が未追跡ファイルを読んで判定していれば、別の
成果物を「同じもの」として一致させられる。

正しくは **一時 index に作業ツリーを読み込んで `git write-tree` する**。`GIT_INDEX_FILE` で別
ファイルを指せば、tracked / staged / unstaged / untracked を1つの tree identity に束ねながら、
**監督の staging 状態を壊さない**。`.gitignore` された生成物は除く — ビルド出力で id が動くと、
同じレビューを2度行えなくなる。

そして **この値を judge に作らせない。** judge が書けるなら、別の成果物を見た2件を「同じものを
見た」と申告して一致を作れる。材料を組む側が一度だけ観測し、judge は運ぶだけにする。

### 早期リターンは、記録も飛ばす

「否は単独で成立する」は正しいが、**早期に返すと副作用の記録も落ちる。** 実例: park / reject を
先に返すようにしたところ、「admit の後から reject が来た」経路で食い違いの記録が残らなくなった。

順序に依存する分岐を入れたら、**両方の順序でテストする。** 片方だけ確かめると通ってしまう。

### 記録の手順が、判定の実行を要求してはいけない

判定を記録するために必要な値を得る手段が「判定をもう一度回すこと」なら、監督はその手順を
飛ばす。実例: 判定対象の id を知るために材料を組むコマンドを打ち、別ハーネスの judge が
実際に起動して数分待たされた（そして打ち切られた）。

**読み取りだけで済む問いには、読み取りだけで答える経路を用意する。**

### 権威を持たない記録を先に置く

一致を要求する検査を「相手が既に居ること」で書くと、初期状態で詰まる。**単独では権威を持たない
記録**を先に置ける形にすれば、順序が問題にならない。

    verdict_provisional   ある血統の判定。単独では何も許可しない
    admission_decided     2件が一致したときに道具が組み立てる

段2で verdict を作るのは配管であって判断ではない（一致という事実の関数）。**道具が新しい判断を
足す箇所が無いこと**が、これが gate の形骸化にならない条件である。

### 安全側の設定は、読めなければ止まる

強い検査モードを設定で選ばせるなら、**その設定を読めないときに弱いモードへ落ちてはいけない。**
落ちると、宣言したはずの層が黙って消え、消えたことに気づく経路が無い。

    except Exception:
        return "same-harness"    # ← これが fail-open である

「org を止めないため」は理由にならない。止まる方が、**分かれていない血統で判定し続けるより
安全である**。読めない理由が当該の行にあるかどうかは、読めない時点では分からない。

### 検証の版は、書く側が付ける

形式の版をクライアントが名指しできるなら、緩い版を指定して検証を素通りできる（downgrade）。
**版は writer が付け、クライアントの指定は拒否する。**

そして **版そのものを hash の対象に入れる。** 入れないと、版を書き換えても検出できないので、
downgrade を拒否したことが意味を持たない。既存の鎖と非互換になるので、**hash が覆う範囲を版
ごとに切り替える** — 版を持たない過去のイベントは従来の範囲で検証し、v1 以降は版を含める。
validator は過去の版を変更せず追加する、という規律の具体形である。

禁止の範囲は広く取りすぎないこと。**版を名指しする値だけ**を禁じる。「スキーマ境界そのものを
記録するイベント」は識別子を payload に持って自然で、それを弾くと記録したい事実が書けなくなる。

### 遡って検証すると、移行できない

新しい検証を入れるとき、**既存の記録に遡って適用すると台帳が読めなくなる。** 検証の対象は新規の
追記だけにし、版を持たない過去は `legacy_unvalidated` として読める状態を保つ。

そして **2つの保証を混ぜない**。「形式が検証済みか」と「誰が書いたか認証済みか」は独立した性質
である。schema を検証しただけで actor も信頼できるという読み違いを招く:

    validation_assurance:  legacy_unvalidated | validated:v1
    identity_assurance:    claimed | observed | attested | authenticated

境界の記録（いつから検証が効いているか）は**補助**に留める。規範的な判定根拠は各イベント自身が
持つ版であって、境界を宣言する1件のイベントではない — それが消えたり複数あったりしたときの
意味論を持ち込まないためである。

### 止めた状態は、警告ではない

「止まった」を記録するだけの仕組みは、止めていない。**止まっている状態は、次の行為が通らない
ことで表される**。記録があるのに行為が通るなら、それは表示にすぎない。

止める判断は **宣言ではなく記録** から読む。宣言（設定や環境変数）で止めると、宣言を消せば動く。

そして **「記録できないなら宣言しない」は、制御としては fail-open である。** 止めるべき状況で
止まらない。記録に失敗した呼び出しは、その呼び出し自体を通さないこと。さらに **次の呼び出しも
止まる**必要がある — そのために、台帳より先に単純なラッチを書く第二経路を持つ。

ラッチは台帳の代わりではない。**手でラッチを消しても、台帳の記録が残っていれば止まり続ける。**
逆に台帳が読めなくてもラッチがあれば止まる。**どちらかが止めていれば止まる**形にする。

**読めないことを「止まっていない」と読まない。** 止まっているか分からないなら止める。

### 全部止めると、復旧できない

止めた状態で通すものを決める。**観測・検証・安全な修復に限る** — 止まった状態を診断できなければ、
何が起きたかも分からない。そして **通常の作業は止める**。通す範囲を広く取ると「止めたが止まって
いない」に戻る。

解除を同じ層に置かないこと。**止めた本人が解除できるなら、止めたことの意味が薄い。** 独立した
承認が要るが、それは行為者の識別が認証されていることに依存する。認証が無い段階では、**解除の
仕組みを作らないほうが正しい** — 作れば、自己申告で解除できる経路になる。

### 統制の判定を、判定対象と同じプロセスで走らせない

判定に使う道具を import すると、**その道具のトップレベルが判定側のプロセスで走る**。差し替え
られた（あるいは壊れた）道具が終了呼び出しを持っていれば、**判定側がそこで「許可」として終わる** —
実測で、hook が何も出力せず exit 0 で通った。

別プロセスで聞き、**終了コードと結果の両方**を見る。統制の判断は、判断される対象の外側で行う。

### 書けた判断だけが allow になる

上限を検査する仕組みを「集計 → 判断 → 記録」の3段に分けると、3つの穴が同時に開く。

- **集計と判断が排他の外にある**ので、並列の呼び出しが同じ合計を読んで**両方通る**。合計は上限を
  超える。
- **記録の失敗を無視する**と、通したのに曝露が残らない。次の呼び出しは合計 0 を見るので、
  **集計する上限が、記憶を持たない個別検査に退化する**。
- **止めた側を記録しない**と、上限が働いたことが残らない。効いていない状態と区別できない。

正しい形は、排他の中で
**スキーマの取得 → 履歴の健全性 → 冪等性の照合 → 合計の算出 → 判断 → 記録 + fsync**
を1つの操作にし、**記録が永続化されたあとにだけ通す**ことである。書けなかったら通さない。
**止めた側の記録に失敗した場合も通さない** — 記録できない拒否を許可に読み替えるのが、いちばん
危ない誤りである。

合計は**書く側が数える**。呼ぶ側が申告できるなら、少なく申告して上限を通れる。壊れた過去の記録は
0 として数えず拒否する — 0 と数えると合計が実際より小さく見える。

**上限の予約に時刻の引数を定義しない。** 窓の外に予約を置けば、窓で集計する上限は迂回できる。
過去を補う権限は通常の記録の側に残す。

### 「誰が」を1つの欄で表さない

行為の主体は、少なくとも3つに分かれる。**判断を形成した主体・それを転記した主体・記録を確定させた
主体**である。1つの欄にまとめると、代理記録がある運用で職務分離が成立しなくなる — 監督が判定を
代理で書けば、観測される主体は常に監督なので、「監督が監督を承認していない」しか言えない。

**職務分離は判断した主体同士を比べる。** 転記した主体を比べてはいけない。

そして **判断した主体は、自己申告では設定できない形にする**。申告できるなら、誰の判断とでも
言える。必要なのは判断者による直接の記録ではなく、**改変不能な判断の receipt** である — それを
第三者が運んでも、判断者の identity は失われない。**代理記録と認証は両立する。**

receipt は判定を特定する値すべてを束縛する（org・対象・役・段階・血統・結論・基準の digest・
理由の digest・署名者・鍵・時刻・形式の版）。**束縛していない値は、後から差し替えられる。**
そして別の org・別の対象・別の血統への再利用を拒否する。

### 鍵が違うことは、主体が違うことではない

共有鍵では、**検証できる側が署名も作れる**。したがって別の共有鍵を使っても示せるのは「鍵が
違う」ことだけで、別の主体・別のプロセス・独立した承認は何も示さない。**それを独立性の根拠に
すると、名前と保証がまた食い違う。**

非対称にすると、判断する側が秘密鍵を持ち、**検証する側は公開鍵だけを持つ** — 検証する側は
判断を作れない。これが「申告より強い」と「認証された」を分ける最初の条件である。

ただし鍵を非対称にしただけでは、**ワークロードは隔離されていない**。同じ利用者が書き手も鍵も
差し替えられるなら、そこはまだ境界ではない。隔離は別の軸として残す。

### 署名が正しいことと、その判定を出してよいことは別

検証が通っても、**その主体がその役・その血統の判定を出す権限を持つか**は別の問いである。
権限は宣言し、宣言の無いものは「許可されていない」と読む（認可の既定は拒否）。

とくに **止めた状態を解除する権限は、止める権限と分ける**。同じ主体が両方を持つなら、独立した
承認という考え方が成り立たない。

### 解除は、記録してから状態を変える

止まった状態を解く手順の順序が、そのまま安全性である。

    確認 → 独立した承認の検証 → 復旧の証拠の検証 → 記録の追記と永続化 → **その後で** 状態を解く

逆順にすると、状態を解いたあとに記録が失敗して、**止まっていた証拠も、止まっている状態も無い**
という最悪の形になる。記録できなかったら、**止まったままにする**。そして同じ承認での再実行が
安全に後片付けを完了できるようにする。

### 保証を1つの強弱値に潰さない

「署名されている」は「独立している」ではない。**同じ主体、あるいは同じ鍵が両方の血統を作れる
なら、それは独立レビューではない。** 潰すと、この誤読がそのまま通る。

少なくとも次を別の軸にする:

    identity assurance      判断者の identity をどこまで確かめたか
    recorder assurance      記録者を観測したのか、申告なのか
    workload isolation      同じプロセス／同じ利用者／別ホストか
    reviewer independence   別の署名者か、別のワークロードか

そして **確かめられていない段階を「確かめた」と呼ばない**。共有鍵で得られるのは、申告より強い
という程度である。**認証と呼べるのは、隔離された書き手・限定された経路・鍵の保護・主体ごとの
認可が揃ったときだけ**である。別プロセスに問い合わせることは、信頼境界ではない。

段階を分けたなら、**弱い段階の結果を「強制」に使わない**。証拠にはなるが、独立性を要求する
根拠にはならない。

### 検査に使う記録は、検査する側だけが書ける

上限や履歴を検査する仕組みは、その検査が読む記録を**自由に書けてはいけない**。実測で、負の曝露を
1件通常の追記で入れるだけで、上限が完全に無効になった（しかも鎖は健全と報告された）。

**記録の種類ごとに「どの操作が書けるか」を宣言する。** これは identity の認証ではない（同じ権限
なら writer を騙れる）が、「通常の経路で偶然にも意図的にも書けてしまう」ことは塞げる。

ただし**既に書かれたものを検証するときは、この規則を適用しない** — 経路は記録に残らないので、
書いた時点でしか確かめられない。適用すると、正しく書かれた記録が「書けないはずのもの」として
拒否され、健全な台帳が壊れていると報告される。

### 再実行と、同じキーの別の要求は違う

冪等キーが一致しても、**要求の内容が違えば再実行ではない**。実測で、少ない量の許可を根拠に
大きな量が通った。キーとは別に**要求内容の digest** を持ち、違えば衝突として拒否する。

そしてキーは**区切り文字での連結ではなく、正規化した組の hash** にする。値に区切り文字が入ると、
別の組が同じキーになる。

### 終了コードだけを信じない

構造化された結果を返す道具を呼ぶなら、**結果を読む**。終了コードだけを見ると、「拒否と言いながら
0 で終わる」実装を通してしまう（実測でそうなった）。

`終了コードが 0` かつ `結果が許可` の**組でしか通さない**。結果が無い・読めない・矛盾している —
すべて拒否側に倒す。ただし「結果が読めない」と「読めた結果が拒否」は別の事象である。前者は環境の
問題なので開発用の逃げ道が効いてよいが、**後者に逃げ道を効かせてはいけない**。

### 無料と宣言したものを、検査で止めない

「これは計量しない」と決めた操作（再生成できる対象の削除など）に、**量を要求する検査をかけると
止まる**。実測で、`node_modules` の削除が「重み 0 なので予約できない」として拒否された — 無料だと
決めたものを止めるのは、設計と真逆の結果である。**計量しないものは、計量の経路に入れない。**

### 止まったことの呼び名を変えない

判断の出所を組み替えたとき、**メッセージの語彙を維持する**。監督も検査も特定の語を探しているので、
中身が同じでも呼び名が変わると「止まったことが見えなくなる」。

### 冪等キーは、識別子1つでは足りない

同じ操作の再実行を二重に数えないためのキーは、**(セッション, 呼び出し, 規則, 記録の種類)** を
束ねる。呼び出しの識別子だけでは、別のセッションや別の規則の間で衝突する。

そして **キーが欠けていれば、計量される操作を拒否する**。同一性を確かめられないなら、二重計上
しないという保証そのものが成り立たない。

「同じ呼び出しで検査が二度走るか」が文書に書かれていないなら、**書かれていないことを「走らない」
と読まない**。キーを付けておけば、走っても数えられる。

### 逃げ道は、記録と引き換えである

塞ぎきれない経路に明示の逃げ道を置くのは正しい。ただし **宣言が記録されるから許される**のであって、
宣言したと言えば許されるのではない。**記録に失敗した迂回は通さない。**

### fail-closed は、故障注入できなければ主張できない

「失敗したら止まる」という性質は、**失敗させてみなければ確かめられない**。正常系だけを試して
「fail-closed にした」と書くのは、検査していないことを検査したと述べることである。

実例: ロックの失敗時に止まる、と書いた。しかし置換が一致せず適用されておらず、判定用の変数は
初期化されるだけで設定されず、逃げ道の環境変数はコードのどこにも無かった。**正常系は通るので、
何も気づかなかった。**

だから故障注入の口を道具に持たせる（`ORG_LEDGER_FORCE_LOCK_FAIL=1` のような）。異常系を
再現できない検査は、書いた本人にも確かめられない。

### 時刻の形式検査は、実在性の検査ではない

`YYYY-MM-DDTHH:MM:SSZ` に合っていても、`2026-99-99T99:99:99Z` は実在しない。**実日時として
parse する。** そして順序を偽れないよう、未来と遠すぎる過去を拒否する — どちらも「いま起きた
こと」を窓の外に置き、窓で集計する上限を迂回できる。

時刻を指定できる経路は、**通常の書き込みから分ける**。名前に意図を出す（`--backfill-ts`）。
同じ引数で「いまを記録する」と「過去を補う」の両方ができると、後者の検査が前者を邪魔する。

そして **時刻を検査するテストに固定日付を書かない。** その時刻が未来から過去に変わった瞬間に
壊れる（実際に、この検査を入れた版で自分のテストがそう壊れた）。いまからの相対で組む。

### 検証規則の欠落は、宣言の欠落と同じくらい静かに効く

設定の差分を「ブロックがあるか」で見てはいけない。**中身の欠落**を見る。検証規則が1つ消えて
いれば、拒否されるべき記録が通り、通ったことは記録に残らない。

そして規則を埋めるときも、**足すだけにする**。ブロックごと差し替えると、org が自分で足した
**厳格な**規則が消える — 実測で、org が加えた `required.progress_recorded: [milestone]` が
修復で失われた。**修復が org 所有の安全設定を弱めるのは、修復ではなく退行である。**

同じ位置に違う値があるときは、自動で上書きしない。org が意図して変えたのか、テンプレートが
変わったのかは道具では判別できないので、**衝突として報告して人に決めさせる**。そして欠落と衝突は
**1つの計算から出す** — 別々に判定すると、片方だけ検出して片方を見落とす（実測でそうなった）。

**設定ブロックの範囲を正規表現で切らない。** `\nkey:\n(?:(?: |\n).*\n)*` は、次のトップレベル
キーの前にあるコメント行やその子行まで飲み込む。実際に、ある置換が別のブロックを丸ごと消し、
**結果は YAML として読めた**ので気づきにくかった。範囲は「インデントの無い次の行」で決める。

### 修復する道具は、途中で止まっても壊さない

設定ファイルを直接上書きする修復は、途中で止まると**その org が何も書けない状態**を作る。
temp → fsync → rename → fsync(dir) で置き換える。修復が壊すのは最悪の形である。

### 厳格化は、可用性事故になりうる

「宣言の無いものを拒否する」を全体に一度にかけると、**宣言と実態の乖離が「組織全体の記録停止」に
変わる**。それは fail-closed ではなく、**既知の移行不備による可用性事故**である。区別すること。

検証は軸を分けて入れる:

    required        宣言したクラスだけ、必須の欠落を拒否
    require_any     相関キーは複数のうち1つでよい（経路によって違う）
    enum / 型       宣言済みの項目は **存在する場合に** 検証
    closed world    厳格化したい少数のクラスだけ、未宣言を拒否

未宣言のものは既定で許し、**乖離として記録する**（見えるようにするが止めない）。統制の中核だけ
最初から厳格にし、乖離しているクラスは**実態を宣言に反映してから**別の移行として厳格化する。

相関キーを1つに固定してはいけない。同じ対象を指すキーが経路によって違うなら、**どれか1つで
足りる**形にする。固定すると正当な書き込みを弾く。

### 所有物のコピーは、配らないと古くなる

org が自分の設定ファイルを所有する設計は正しい（org が自分の形式を決める）。しかし**プラグイン
側が宣言を増やしても、org のコピーは古いまま**である。そこに「宣言の無いものは書けない」検査を
入れると、更新直後に記録が止まる。

だから検査より先に、**差分を診断する道具**と**明示的に埋める道具**を持つ。診断は「使われている
かどうか」を言うこと — 実データで使われているクラスが欠けているなら、緊急度が違う。

そして **埋める側は既存の宣言を書き換えない。** org が実態に合わせて変えた宣言を上書きすると、
検査が実態と食い違う。足すだけにする。

**修復の書き込み前に、結果を検証すること。** この修復の初版は、テンプレートのブロックを丸ごと
挿入して `event_classes` を2つにし、YAML の後勝ちで65クラスの宣言を消した。**修復が壊す**のは
最悪の形なので、書く前に「読めるか」「減っていないか」を確かめる。

### 宣言の無いクラスは、書けても読まれない

台帳に書けるクラスと、schema が宣言しているクラスは、放っておくとずれる。**宣言の無いクラスは
projection にも sensor にも乗らないので、書いても読まれない。** 実際に、道具が書いていた5つの
クラスが宣言されておらず、そのうち2つは実データに5件・23件あった。`show` の警告が沈黙した一因
でもある。

検査を入れるときは、**宣言を実態に合わせる**こと。実データの payload を数えてから書く。
宣言が実態と違えば、検査は嘘になる。

### HEAD は権威ではなく cache である

追記型の記録で、末尾を指すファイルを別に持つなら、**それは log から再構築できる cache として
扱う。** 権威にすると、cache が壊れたときに記録全体が読めなくなる。

ただし **途中の破損を自動修復してはいけない。** torn line、seq の飛び、hash 不一致の上に整合した
HEAD を載せると、壊れていることが分からなくなる。破損は fail-closed で報告する。

### 偽の記録で試験すると、検査を入れたときに露見する

手で組んだイベント（hash の無いもの）で台帳を seed していると、鎖の健全性を検査し始めた瞬間に
落ちる。**それは検査が正しい** — 鎖の無い台帳に追記できてはいけない。試験も実際の追記経路を
通すこと。

### 統制を配るなら、配ったものだけで動くこと

統制の仕組みを配布物にするなら、**その配布物の中だけで完結させる**。元の作業ツリーを参照する形は、
そのツリーが動いた瞬間に統制が消える。しかも消えたことは静かで、通常の操作は成功し続ける。

自己完結を確かめる方法は1つしかない — **元のツリーを一時的に無くして動かす**。参照が残っていれば
そこで落ちる。

### 導入と有効化を、同じことだと思わない

「入れた」と「効いている」は別である。実測した環境では、**配布物を入れて有効にしても、検査の
仕組みは信頼されるまで黙って読み飛ばされた** — 警告も、記録も、何も出ない。「入れたのに効いて
いない」は、この形でいちばん見えにくい。

したがって配布物の説明には、**有効化に何が必要か**と、**有効化されていない状態がどう見えるか**を
書く。「入れれば効く」と読める書き方をしてはいけない。

そして**内容に束縛された署名で信頼を管理する仕組み**では、配布物を更新すると信頼が外れうる。
更新が統制を無効化する経路として、これも書いておく。

### 他所の形式をそのまま持ち込まない

似た形式を採る2つの環境でも、**受け付けるものは違う**。実例として、設定ファイルにコメント用の
キーを1つ入れたところ、片方の環境では通り、もう片方では**ファイル全体を読み飛ばされた**。
統制の設定が丸ごと無効になり、しかも通常の操作は成功し続けた。

移植するときは、**その環境で実際に読ませて確かめる**。形式が似ていることは、同じであることの
証拠にならない。

### 拒否の検証は「1回だけ試して止まる」ことと対で行う

拒否が効いたかを、行為者の最終結果で判定してはいけない。**正しく拒否された後に別の手段で目的を
達成すると、「拒否が効かなかった」と読める**。

検証のときは行為者に「**1回だけ試し、拒否されたら代替手段を使わず終了する**」と指示する。そして
拒否の証拠は、行為者の報告ではなく**対象物が変わっていないこと**と**拒否が記録されていること**で
確かめる。

### 誰に対して強制的なのかを書く

PreToolUse hook として動く道具は、**hook を有効にしたホスト上の agent**に対しては強制的だが、
hook を無効化できるホスト所有者に対しては強制力を持たない。これは欠陥ではなく境界である。

問題になるのは限界そのものではなく、**境界を書かずに「回避不能」と述べること**である。
信頼境界（TCB）と脅威モデルを明示すれば、同じ実装が正しく評価される。

そして境界の内側にも、**認証されていない属性**がある。台帳の `actor` は引数から採られるので、
1つのプロセスが maker と gate を名乗り分けられる。したがって職務分離は「**レビューが行われた
証拠**」であって「誰が行ったかの証明」ではない。血統の分離も同じ性質を持つ — 独立したレビュー
であって、認証された独立性ではない。**ラベルを信頼境界と呼ばないこと。**

### 摘発と、適応の理解を混同しない

監督が正しい道具を使わずに同じ状態変更を行うのは、多くの場合**遅いからではなく、道具の名前を
思い出すコストを払わなかったから**である。それは規律の欠如ではなく**適応**である。

したがって検査を足すときは、**逸脱の摘発**と**適応の構造を残すこと**を分けて設計する。摘発だけを
足すと、次はその検査を形式的に満たすだけの逃げ方が生まれる（`--verified` を必須にすれば「確かめ
た」と書くだけで通るのと同じ）。逃げ道は塞ぎきらず、**逃げたことが記録に残る**形にする
（`bypass_declared`・`judges_disagreed`・`correction`）。

**都合の悪い記録が消せないこと**が、この org の台帳が append-only である理由である。訂正は
削除ではなく `correction` の追記で行う — 消せる記録は、消したい人がいるときに消える。

### 分割の失敗は、しばしば要求の欠落として現れる

10周を超えた Issue の後半は、その Issue の EARS のどれにも対応していない作業だった（メンバー間の
UPDATE / INSERT 権限・同意の表現・前提の凍結 — MUST に1件も無い）。skeptic の言葉では
**「装飾的なテキスト列を守り、金額・支払者・債務の向き・グループ所有権を無防備にしていた」**。

認可を扱う deliverable なのに、MUST が「誰が入れるか」しか定めておらず「入った後に何が
できるか」を定めていない、という偏りは**起票時に検出できる**。切り方の問題として現れる前に、
要求の問題として捕まえるほうが安い。

## 4c. The integration seam — feature → develop → main, and where fan-out fans back in

docs/03 fans work **out** into parallel task sub-issues; the theory it rests on (Lawrence & Lorsch, via
docs/03 §2) warns that **whatever you separate, you must pay to reintegrate**. The `integrate` phase
(§1) is that payment — the point the parallel deliverables come back together and are tested *as a
whole*, before any of them deploys. It is realized on git branches (R0: borrow git/GitHub, build no
runtime):

- **feature branch per task.** Each task sub-issue opens `feat/issue-<N>-<slug>` off `develop`. The
  branch name is deterministic (`github_sync branch --issue N`), so it is reproducible the way Issue
  creation is (docs/11 §0). A task's work happens on its own branch — siblings never collide.
- **`develop` is the integration branch.** A task's per-unit `test` passing (its own suite green) admits
  it to merge into `develop` — **not** into `main`. `main` is release-only.
- **the `integrate` phase gate = green CI on `develop`.** Once siblings have merged, the combined suite
  must build and pass **together** on `develop`. That green run is `integration_admitted` (the same
  `requires_prior` idiom: `result_deployed` may not fire without it). Green CI on `develop` is the
  machine form of the integrate gate, exactly as green CI on `main` is the machine form of deploy (§3).
  This is the state the org is judged against: the work is *merged into `develop` and testable there* —
  not a pile of per-task PRs against `main` that were never assembled. With human diff review retired
  (§4f), this green is not a *precondition* for review — it **is** the verdict, and the reasoning behind
  admitting it lands on the objective Issue like any other judgment.
- **who owns it.** No new "integrator" rank (docs/09 §1 forbids minting PM ranks). The **supervising
  manager's A3 accountability** (docs/09 — "verify subordinate work against its contract") is *extended*
  from per-child conformance to the **cross-deliverable integration test on `develop`**: the manager
  who fanned the work out owns bringing it back together and proving it works assembled.
- **deploy is `develop` → `main`.** Only an integrated, green `develop` promotes to `main` (deploy, §3),
  keeping the trunk always-shippable (docs/11 §0) with the integration buffer in front of it.

So the hand-back a task submits is a **PR against `develop`** (not `main`), and "done" means "merged to
`develop`, integration-green, with the integrate verdict and its reasoning recorded on the Issue" (§4f).
Nobody reads the diff; the assembled, green `develop` plus the recorded judgment is the whole account.

---

## 5. What this doc is, and is not

- It **is** the declaration that an IT business company builds through a fixed phase order, and that
  the order is enforced by generalizing the one `requires_prior` predicate the repo already runs.
- Its **purpose is reproducibility** (§0): the mold makes the process, contracts, gates, and
  verification converge across founders and runs at two levels — the org itself (§1–§3) and the
  repositories it builds (§4a) — while the generated code stays free to vary.
- It is **not** a new runtime, a new organ, or a forced fan-out. The phases are content of Organs 2,
  4, and 6 (THEORY §1b); the enforcement is the existing lint/hook layer; the deploy spine is a host
  primitive (docs/08).
- It deliberately **references rather than restates** docs/03 (routing, the maker→gate→skeptic chain),
  docs/09 (conformance as a phase gate), docs/08 (R0/host delegation), docs/05 (reliability budget,
  DORA, OUTCOME-DELTA), docs/09 (the backlog pipeline), docs/03/16 (decomposition and the
  request-vs-enforcement split). If any of those change, this doc follows — it holds no independent
  copy of their mechanisms, only the one generalization that ties them into a lifecycle.
