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
