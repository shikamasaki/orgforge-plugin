# Reference — configuration, commands, events, troubleshooting

> **Current assurance and supported-operation reference:** [English](docs/en/assurance.md) ·
> [日本語](docs/ja/assurance.md)

The lookup companion to [QUICKSTART.md](QUICKSTART.md) (how to get started) and
[ARCHITECTURE.md](ARCHITECTURE.md) (how the system fits together). This is the flat reference: every
environment variable, every command, the blast-radius caps, the ledger event vocabulary, and the
fixes for the problems people actually hit.

---

## 1. Environment variables

**どれも設定する必要はない。** 0.9.0 以降、org は作業ディレクトリから**発見される**
（`organization.yaml` の隣の `.orgforge/`、バックログは `git remote origin`。`tools/discover.py`）。
以下はすべて**上書き**であり、優先順位は **明示的な引数 > 環境変数 > 発見**。

> **なぜ発見が既定なのか。** 絶対パスで書かれた設定は別のマシンで壊れ、マシンごとに繰り返す
> 手順は飛ばされる。そして飛ばされたとき、ガードレールは ledger を見つけられず**黙って全部を
> 許可する** — 設定忘れの帰結が「無防備」になるのは、ガードレールが持ってはいけない失敗モード。
> 発見はそれを消し、副次的に **1つの環境で複数リポジトリの org を混線なく運用できる**。

> **Spec vs. dev override.** The enforcement knobs — the caps, the window, the iteration/cycle limits,
> and the seam gate — are **declared in the org spec**, in `constitution.yaml`'s `enforcement:` block
> (see §7). That is the source of truth, so *every install of the same org fans out and throttles the
> same way* (reproducibility, docs/11 §0). The `ORG_CAP_*`, `ORG_WINDOW`, `ORG_WINDOW_SINCE`,
> `ORG_MAX_CYCLES`, `ORG_MAX_TOKENS`, and `ORG_REQUIRE_SEAM` variables below are **dev overrides** over
> that spec — for a local run or a test, not the way you configure a real org. Set the value in the
> constitution for anything you want to persist.

### Core

| Variable | What it does | Default |
|---|---|---|
| `ORG_LEDGER_ROOT` | ledger の場所（`ledger.jsonl` + `HEAD`）。**通常は不要** — 発見される。チェックアウトの外に ledger を置く場合や CI で固定する場合のみ設定する。 | *(発見: `<org root>/.orgforge/ledger`)* |
| `ORG_GITHUB_REPO` | バックログの GitHub リポジトリ（`owner/name`）。**通常は不要** — `git remote origin` から解析される。 | *(発見: origin の URL)* |
| `ORG_ROLE` | Which department/role this session is. Keys the doctrine injection, the work-in-progress resume, and the ledger events. | *(unset)* |
| `ORG_DOCTRINE_ROOT` | Directory of per-role `<role>.json` doctrine stores; the SessionStart hook injects this role's doctrine at launch. | *(unset → no doctrine injected)* |
| `ORG_CONVENTIONS_ROOT` | Directory of settled conventions, injected alongside doctrine. | *(unset)* |

### Blast-radius caps (per-day budgets)

The cap bounds **irreversible effect per day** (the window rolls daily — see §5). Override any
dimension with `ORG_CAP_<DIMENSION>`. Defaults are sized so a normal day of real work (including a
research/ML day that deletes and replaces artifacts many times) proceeds untouched, while a runaway
(hundreds of irreversible acts in a day) still trips.

| Variable | Dimension — what it meters | Default (per day) |
|---|---|---|
| `ORG_CAP_DESTRUCTIVE_OPS` | `rm`/`dd`/`DROP`/`--force`/`reset --hard`/… — irreversible deletes & force-writes (scope-weighted: one `rm -rf`/`DROP` counts as 3). **通常の `git push` は対象外** — 追記であって取り消せる。force 系（`--force`/`--delete`/`--mirror`）だけを数える。再生成できる対象（`.orgforge/wt/`・`node_modules`・ビルド成果物）は重み 0 | `150` |
| `ORG_CAP_EXTERNAL_WRITES` | outbound `POST`/`PUT`/`DELETE` (curl/wget with a write verb) | `30` |
| `ORG_CAP_INFRA_CHANGES` | `terraform apply`/`kubectl apply`/`aws`/`gcloud` — changes to real infra | `20` |
| `ORG_CAP_FILE_MUTATIONS` | overwriting an **existing** file (reversible under VCS — high ceiling; new-file creates are never metered) | `500` |
| `ORG_CAP_SHELL_EFFECT` | **deprecated** — the classifier no longer meters "unknown" shell; kept only so an old override is not an error | *(unused)* |

**Not metered at all** (return no charge): reading (`ls`, `cat`, `grep`, `find`, `du`, `stat`, `head`),
build/test tooling (`npm`, `pytest`, `go`, `cargo`, `node`), new-file creation, and any command that
matches none of the destructive/external/infra patterns. "Unknown" is not "dangerous" — only explicit
irreversible patterns draw down a budget.

### Window & tuning

| Variable | What it does | Default |
|---|---|---|
| `ORG_WINDOW_SINCE` | Explicit ISO timestamp for the start of the cap window (overrides the rolling daily default). | *(rolling daily)* |
| `ORG_WINDOW` | Set to `all` to opt into a deliberate **all-time** cap (no reset). Use only if you truly want a lifetime budget — otherwise leave unset for the daily reset. | *(rolling daily)* |
| `ORG_REQUIRE_SEAM` | The spawn gate is **on by default**: an `Agent`/`Task` spawn is blocked unless its prompt carries a seam contract or an `INDEPENDENT:` declaration, and a declared `owns:` territory must not collide with a live sibling's claim (concurrent-write prevention). Set to `0`/`false`/`off` to disable it for an ungated dev run. | *(on)* |
| `ORG_MAX_CYCLES` | Per-window cap on a role's loop cycles (each `Agent`/`Task` spawn = one cycle). When set, a spawn that would exceed it is **held** — the enforcement-layer runaway kill ("$3-5, not $180"). Needs `ORG_ROLE`. | *(unset → no cycle cap)* |
| `ORG_MAX_TOKENS` | Per-window cap on a role's cumulative reported tokens (from `cycle_completed`). Same enforcement as `ORG_MAX_CYCLES`. | *(unset → no token cap)* |
| `ORG_ALLOW_MANUAL_MERGE` | `1` で保護ブランチ（`develop`/`main`/`master`）への直接の `git merge`/`rebase`/`cherry-pick` を通す。**通した事実は台帳に `bypass_declared` として残る** — 統合は `org_cycle integrate` を通すのが既定（gate の admit と skeptic の survives を確認する） | *(off — hold する)* |
| `ORG_ALLOW_MANUAL_GH` | `1` で `gh issue create|close|edit|reopen` を通す（同様に台帳に残る）。Claude Code の PreToolUse は Bash より先に走るため、一度だけ通す場合は同じ Bash 呼び出しで `ORG_ALLOW_MANUAL_GH=1 gh issue …`（または `export ORG_ALLOW_MANUAL_GH=1` の次行で `gh issue …`）と宣言する。1呼び出しにつき1件の mutation だけを許し、複数件は個別に宣言・実行・記録する。読み取り（`view`/`list`）と `gh pr *` は元から止めない | *(off — hold する)* |
| `ORG_QUIET` | `1` で「実行中のバージョンと cwd」の1行（stderr）を抑制する。`view`/`census`/`digest` と内部呼び出しでは自動で抑制されるので、通常は不要 | *(off — 1行出す)* |
| `ORG_HOOK_FAIL_OPEN` | `1` allows a tool call when the guardrail organ errors, instead of blocking. **Dev only** — the safe default is fail-closed. | *(off / fail-safe)* |
| `ORG_ALLOW_CATASTROPHIC` | `1` disables the catastrophic denylist (the hard block on `rm -rf /`-class, `mkfs`, `dd`-to-disk, fork bombs). **Disposable sandbox only** — never in an environment with real data. | *(off / catastrophic blocked)* |
| `ORG_NOW_TS` | Pins the hook's "now" (append ts + window boundary). Mainly for tests; leave unset in production so the real clock is used. | *(real UTC now)* |
| `ORG_TOOLS_DIR` | Override the directory the hooks resolve the organ tools from. Set automatically by the plugin bundle; rarely touched by hand. | *(bundled/repo auto-resolve)* |

### Assurance labels

These values describe separate facts; they are not one ascending security score.

| Label | Meaning |
|---|---|
| `claimed` | caller-supplied identity; no verification |
| `observed` | host/writer observation, such as the connecting UID; not the decision-maker |
| `attested` | receipt signature and bound fields verified; the default ceiling for local keys |
| `authenticated` | reserved for externally enforced custody/authentication; not emitted as a default local guarantee |
| `cross-harness` | different model lineage for decorrelated review; not an authenticated principal |
| `process_mediated` | normal writes pass through enabled host mediation |
| `separate_uid` | experimental writer isolation, only after OS permissions are measured |

The plugin controls drift and honest operational error. Separate-UID writer isolation remains an
unsupported experiment, not normal operation. It does not protect judge private keys and is not
required to run the Quickstart or claim the supported guarantees.

---

## 2. Commands (Claude Code slash-commands)

**The commands you use** (the everyday surface):

| Command | What it does |
|---|---|
| `/org-init [org-name] [ja\|en]` | **Step 1 — set up.** Create the ledger/doctrine/conventions roots, install the org spec files, ensure `develop` + the backlog labels, then lint the spec, take the `repro_lint` **baseline**（機械バーの現時点を記録する起点 — 無いと「この変更による悪化」と「元からの負債」を区別できない）, and probe that the guardrails actually bite. **No environment setup** — the org is discovered from the working directory (`tools/discover.py`), so nothing is exported and several repos can run from one shell. Idempotent; designs nothing. |
| `/org-found <RFP or brief>` | **Step 2 — design.** Draft the org from a brief and write the five **fixed-name** founding artifacts (docs/11 §0a): `REQUIREMENTS.md`, `FEATURE-INVENTORY.md`, **`ARCHITECTURE.md` (the 全体設計書)**, `coverage-manifest.md`, `organization.yaml` — then stop and report up for scope approval. Design only. |
| `/org-adopt [残りの要求]` | **既存リポジトリへのone-command導入.** 事前の`org-init`は不要。local stateを安全に準備し、実在するコードから`ARCHITECTURE.md`と`organization.yaml`を*読み取って*書き、**未実装分だけ**をmanifestへ載せ、`repro_lint baseline`で既知の負債を記録し、readiness doctorまで同じinvocationで完了する。network、branch、Issue、daemon、sudo、鍵は不要。 |
| `/org-decompose [objective-id]` | **Step 3 — decompose.** Turn the approved `coverage-manifest.md` + `ARCHITECTURE.md` into **atomic SPEC task Issues**, one per independently-completable unit, each a native sub-issue of its objective and each carrying the full spec (so any environment can pick it up). Gated by `coverage-check`: exits non-zero if a must-have never became an Issue. |
| `/org-start [role] [tick] [work] [discover]` | Bring the org to its **running state**: register this session's recurring cycles via the scheduler. Idempotent. The SessionStart hook prompts it for you. |
| `/org-goal <operation> ...` | Operate one **portable persistent objective** across Claude Code and Codex: `start`, `status`, `progress`, `pause`, CAS-protected `resume`, three-observation `block`, evidence-audited `complete`, or `doctor`. SessionStart re-injects unfinished state; it does not claim work continues while the host is closed. |
| `/orgforge-plugin:org` `[role]` | The **status board** — "how's my org?" in one GREEN/AMBER/RED answer (done / in progress with next steps / what needs you), in your language. Read-only. |
| `/org-triage <signal>` | The **front door**: turn an external bug/issue/feedback into a triaged backlog item (or reject it). Feeds `/orgforge-plugin:org-work`. |
| `/org-mandate <subjectA,subjectB> <decision>` | Adjudicate a **mandate conflict** against the constitution's human-authored precedence: precedence applies, both integrate, or escalate. |
| `/orgforge-plugin:org-verify-guards` | Certify the guardrails block — including for a spawned subagent — before trusting the org to fan out unattended. Run once at founding. |

**The internal metabolism** (runs on cadence; you rarely type these):

| Command | What it does |
|---|---|
| `/org-work <role> [wip] [floor]` | The **PM loop**: check deaths + reuse, select by situated attention, delegate genuinely-independent slices in parallel, record progress/completion + reuse + settled conventions. Acts. |
| `/org-discover <role> [aspiration]` | **Problemistic search**: raise `source: self` backlog items from aspiration gaps. Adds only; fail-quiet when there is no gap. |
| `/orgforge-plugin:org-tick` | Read-only **health tick**: due/MISSED checks, machine sensors, chain integrity, stall breakers, repeated-death + domain-model-growth checks. Surfaces, never acts. |
| `/org-resume [role]` | Show a role's **work in progress** with checkpoints — the manual counterpart to the automatic resume injection. |

Scheduling these on a cadence: see [integrations/claude-code/SCHEDULER.md](integrations/claude-code/SCHEDULER.md)
(`/schedule` cron routines for unattended runs, `/loop` for attended ones).

The neutral `orgforge adaptation ...` launcher exposes the same bounded-adaptation contract in both
harnesses. `doctor` validates critical functions, invariants, practices, and envelopes; `status`
distinguishes `proposed | active | expired | reverted | adopted`; `activate`, `authorize`, and
`deviate` enforce trigger evidence, scope, blast radius, retries, expiry, taint, and revalidation;
`outcome` records safe stop, scope reduction, goal abandonment, human handback, and observe-only as
valid outcomes; `experiment` plus receipt-backed `adopt` keeps permanent practice changes human-held.

`orgforge resilience-exercise reviewer-outage --expect RED` runs the bounded Phase-A fault fixture
through production judge preflight, adaptive authorization, and the ephemeral real ledger. The
injected marker must appear in a fault receipt or the exercise is `INVALID`; a no-op fault can never
make it GREEN. Before #45, the sole expected RED gap is the missing `DEGRADED` transition. Output
separates observed facts, acceptable outcome, multi-potential evidence, and remaining human judgment
without producing a resilience score.

---

## 3. The org's files

An org is these source files (templates in `template/`), validated by `tools/org_lint.py`:

| File | What it declares |
|---|---|
| `organization.yaml` | the chart: purpose, latent layers, roles + contracts, separation-of-duties, info-flow scopes |
| `constitution.yaml` | the charter: decision line, invariants, change tiers, mandate precedence, and the **`enforcement:` block** (below) — **no agent edits it** |
| `moves.yaml` | the catalog of legal structural changes, each tiered (delegated / charter / irreversible) |
| `ledger-schema.yaml` | the ledger's event vocabulary + derived views (incl. the backlog and work-in-progress views) |
| `sensors.yaml` | the sensors that trigger reorg moves |
| `role-settings.yaml` | neutral per-role runtime knobs (model tier, tools, budget, stop) — the projection input |
| `ROLE.md` / `SUPERVISOR.md` / `FOUNDER.md` / `PROJECTION.md` | neutral role/supervisor/founder profiles + the projection contract |

### The founding artifacts — FIXED filenames (docs/11 §0a)

`/orgforge-plugin:org-found` writes these four files at the org root under **exactly these names**. The names are part of
the contract, not a convention: `/orgforge-plugin:org-decompose` reads them **by name** as its input, and a stranger
opening any orgforge org finds the design in the same place. A renamed artifact is an unfindable one.

| File | Role |
|---|---|
| `REQUIREMENTS.md` | the received brief, verbatim + the one-sentence purpose — the immutable input everything traces to |
| `FEATURE-INVENTORY.md` | the 洗い出し: every required capability, grouped must / should / nice, + the explicit EXCLUDE list |
| **`ARCHITECTURE.md`** | **the 全体設計書** — the whole-system design: layers/components + seam contracts `{deliverable, standard, checker, depends_on}` |
| `coverage-manifest.md` | the RFP→contract coverage map: one row per must-have `{rfp_capability, owning_role, deliverable, acceptance}` |

**`ARCHITECTURE.md` is deliberately not an SDD artifact.** SDD's spec/plan/tasks (docs/11 §4b) live in
the Issue hierarchy and are per-objective/per-task; the 全体設計書 sits *above* them as the standing shape
of the system, authored once at founding and amended at reorg. That is why it is a file and the task
specs are not — a single whole-system design does not fragment, whereas per-task spec files rot
(the fragment-Spec trap, docs/12 §6).

### The `enforcement:` block (`constitution.yaml`)

The org's enforcement knobs are **declared in the spec**, not left to env vars, so every install of the
same org throttles and fans out the same way (reproducibility, docs/11 §0). The `ORG_*` variables in §1
are **dev overrides** over these values:

```yaml
enforcement:
  caps:                    # per-day blast-radius budgets — a gate HOLDS when the window sum would exceed
    destructive_ops: 150   #   ← overridden by ORG_CAP_DESTRUCTIVE_OPS
    external_writes: 30    #   ← ORG_CAP_EXTERNAL_WRITES
    infra_changes: 20      #   ← ORG_CAP_INFRA_CHANGES
    file_mutations: 500    #   ← ORG_CAP_FILE_MUTATIONS
  window: daily            # daily = per-day budget resetting at UTC midnight; or `all`   ← ORG_WINDOW
  iteration:               # runaway read-think-edit kill, DEFAULT-ON (docs/11 §0; the amplifier failure)
    max_cycles: 50         #   ← ORG_MAX_CYCLES   (null = unlimited)
    max_tokens: 2000000    #   ← ORG_MAX_TOKENS
  seam_gate: on            # the fan-out seam/independence gate, DEFAULT-ON   ← ORG_REQUIRE_SEAM
  catastrophic_denylist: on # rm -rf / , mkfs, fork bomb … — always on; a spec cannot opt a shipped org out
```

Precedence: the spec value is the default; an `ORG_*` env var, if set, overrides it for that run. Set
the value **in the constitution** for anything you want an org to carry to every install.

Validate: `python3 tools/org_lint.py organization.yaml constitution.yaml moves.yaml ledger-schema.yaml sensors.yaml [role-settings.yaml]` (exit 0 = pass, 1 = violations).

`org_lint.py` teeth include **O10 — contract coverage** (docs/11 §0, docs/01 J14/S9): every declared
`contract.deliverable` must be *owned* by a role and *independently checked* by a different role (a
role may not be the checker of its own deliverable, and a deliverable owned by two roles is a
separation-of-duties violation). O10 is the chart side of the RFP-coverage manifest — the guarantee
that the founding contracts cover what the RFP asked for, which is one half of Level-1 reproducibility.

### The reproducibility + unread-safe gate (`repro_lint.py`)

The **Level-2 reproducibility gate** (docs/11 §4a) — checks that a repository the org *builds* is
reproducible for a stranger who clones it, not asserted by the maker — **plus the unread-safe bar**
(docs/11 §4e): at parallel-agent throughput nobody reads every diff, so the defects only a careful
reader catches must be made unmergeable by machine instead. Run **by the gate** at the SDLC
implement/test/deploy phase gates:

```
python3 tools/org_cycle.py  begin    --role R --issue N [--agent A] [--phase implement]
                            # 1サイクル分の配管を1コマンドで: claim → spec_delegated →
                            # phase_started → cycle_started → Issue へ log → stage。
                            # parent と candidate_id は Issue から自動解決（手打ち不要）
                            # worktree（.orgforge/wt/issue-N/）も用意する — 並列 maker を
                            # 同一ツリーで走らせると、あるIssueのコミットが別Issueのブランチに
                            # 載る。--no-worktree で省けるが、並列なら使わないこと
python3 tools/org_cycle.py  complete --role R --issue N --outputs T --command CMD --result OUT
                            (--domain-model-updated REF | --domain-model-none WHY)
                            [--learned "次も効く学び"] [--affects R,R] [--files F]
                            # --command/--result は必須（log が「通った」の言い換えを拒否する）
                            # --learned は doctrine に propose される。admit は gate の仕事
python3 tools/org_cycle.py  verify    --issue N --role gate|skeptic
                            # 判定の材料を組み立てる: seam contract・agents/<role>.md の憲章
                            # （＝検証チェックリスト）・Issue の SPEC/MUST・判定履歴（何周目か）。
                            # skeptic には gate が既に見たことと「gate が撃っていない領域」を渡す。
                            # **verdict / why / risk は埋めない** — 判定は役割が決める。
                            # stdout = subagent に渡す本文（「返すもの」の指定。記録コマンドは
                            # 載せない — subagent に env も台帳のパスも渡っていないため）
                            # stderr = 監督が打つコマンド（返ってきた値を decide に流す）
python3 tools/org_cycle.py  handback  --issue N [--summary S] [--result OUT]
                            # push → develop 宛 PR（body に Closes #N）→ Issue へ log
python3 tools/org_cycle.py  integrate --issue N [--test "npm test"] [--plan]
                            # --plan: 何も実行せず「何を統合するか」を見せる。変更ファイル・
                            # コミット数・**並行 worktree との重複**（衝突の予告）・前提の可否・
                            # **CI を触るなら job 構成と `if:` の有無**（条件付き job に入った
                            # ステップは、YAML が妥当でテストが緑でも一度も走らない）
                            # gate の admit と skeptic の survives が**台帳に**無ければ止まる。
                            # マージ → 統合後テスト → integration_admitted → Issue へ log
python3 tools/org_cycle.py  gc        [--base develop] [--all]
                            # 統合済みの worktree だけ片付ける（未統合・未コミットは残す）
python3 tools/org_cycle.py  intake    --issue N --role gate|skeptic|maker --report TXT
                            # subagent が返した報告が**成果物の形になっているか**を検査する。
                            # `--report -` で標準入力から読む。exit 10 = 不完全（再開させる）
                            # skeptic/gate → verdict と実行の痕跡 · maker → コミットと DoD 出力
                            # **判定はしない** — verdict の中身も妥当性も見ない。
                            # 実地で turn が作業の途中で終わり、宣言1文だけが status=completed で
                            # 返った（「MUST 2 は防がれました」で切れれば verdict と読みかねない）
python3 tools/org_cycle.py  rework    --issue N --after reject|refuted --by WHO --reason TXT
                            [--round N] [--to ROLE]
                            # reject/refuted を受けて rework を発注したことを記録する。
                            # **これを打たないと `show` の rework 警告が沈黙する** — 台帳に
                            # 材料が無いので閾値に届かない（実地で reject/refuted 28件に対し
                            # 記録が無く、警告が黙っていた）。verify が reject 時にこのコマンドを
                            # 判定の記録と同じ場所に出す
python3 tools/org_cycle.py  record    --issue N --event E --verdict V --by WHO --why TXT
                            # 済んだ判定を遡って台帳に記録（backfilled 印が付く）
python3 tools/org_cycle.py  touched   --target T --op OP --by WHO --authority WHY
                            [--name N] [--issue N] [--reversible] [--rollback CMD]
                            # 本番資産への変更（DDL・権限・インフラ）を台帳に残す。
                            # exposure_budget_checked はローカルのファイル操作しか数えない
                            # が、危険なのはむしろ本番側。--authority に「誰の権限で入れたか」
                            # を書く — 後から「あの revoke は誰の判断か」を辿れるように
python3 tools/org_cycle.py  show      --issue N
                            # 1つの Issue の全体像: 実装コミット・worktree・判定履歴
                            # （訂正済み / backfill の印つき）・いま何待ちか・次の一手。
                            # 3周した Issue で「どの周のどの判定か」を追うための視点
python3 tools/org_cycle.py  plan     --role R --issue N   # 何も実行せずイベント列を印字
python3 tools/req_lint.py   check <REQUIREMENTS.md> [--json] [--warn-only]
                            # 要求記述の書式検査（29148 tailored + EARS、docs/11 §0b）
                            # 必須節の欠落 / shall なし / 禁止語 / TBD / 未解決の
                            # [NEEDS CLARIFICATION] を落とす
python3 tools/repro_lint.py check    <repo_dir> [--phase implement|test|deploy] [--json] [--baseline PATH]
python3 tools/repro_lint.py baseline <repo_dir>   # 現時点の失敗を「既知の負債」として記録
                            # **/org-init と /org-adopt が1回取る。** baseline が無いと
                            # 「この変更による悪化」と「元からの負債」を区別できず、check は
                            # その旨を明示する（以前は区別せず断定し、gate が既存の負債を
                            # 新規の悪化と読んで判定を止めた）
```

### その他の organ ツール

上の主要フロー以外にも組織の器官がある。参照する手段が無いと存在に気づけないので列挙する:

```
python3 tools/handoff.py    <child_role> --slice S --inputs I --outputs O [--owns W] [--forbid F]
                            # seam contract（境界契約）＋ その役割にスコープした doctrine を生成。
                            # subagent を spawn するときガードレールがこれを要求する。
                            # ledger root は省略可（発見される）
python3 tools/doctrine.py   propose <root> <role> --claim TXT --source S --confidence 0..1
                                    --retrieved-at DATE --review-by DATE [--affects R,R]
                            # retrieved-at / review-by が無いと gate が admit できない
python3 tools/doctrine.py   admit <root> <role> <claim-id> --by gate
python3 tools/doctrine.py   render|show|stale <root> [<role>]
python3 tools/ledger.py     append --actor A --class correction \
                            --payload '{"corrects":[204,205],"kind":"probe","reason":"...",
                                        "corrected_by":"..."}'
                            # 追記型なので過去は消せない。誤記・検証プローブを「無効」と
                            # **機械が読める形で**宣言する。kind: probe|mistake は status /
                            # learning が除外し、backfill|superseded は除外しない
                            # （後から書いた実判定と、時系列で置き換わったものは別物）
python3 tools/learning.py   repeats <root> [--recurrence N]
                            # 同じ死因の再発を検出。死因は cause / reason / why / checklist_ref
                            # のいずれかで書く。読めなければ clean ではなく unknown と報告する
python3 tools/alignment.py  <root> ...   # 前提・埋没費用・フレームの検査
python3 tools/resource.py   rank <root>  # 資源の優先順位づけ
python3 tools/reconcile.py  <root> ...   # 台帳と外部状態の突き合わせ
python3 tools/harness_probe.py           # ガードレールが実際にブロックするかの検査
python3 tools/status.py     status [--role R]   # 健康ボード（GREEN/AMBER/RED）
python3 tools/attention.py  select --role R [--aspiration N]  # バックログからの選択
python3 tools/conventions.py ...         # 確立した内部先例（ドメインモデルの半分）
python3 tools/org_goal.py status --json  # harness共通の持続Goal。通常はSessionStartが注入した
                                        # stable launcher経由で `orgforge org-goal ...` と呼ぶ
```

Exit `0` = all artifacts required *for that phase* are present · `10` = one or more missing (the gate
should HOLD) · `2` = usage error. Each artifact is tagged with the earliest phase that requires it, so
an implement-phase candidate is held to a lighter bar than a deploy-phase one:

| Phase gate | Requires (presence, not correctness) |
|---|---|
| `implement → test` | a committed lockfile + populated manifest; a pinned toolchain; **§4e** a configured ceiling on function size / complexity / nesting; **§4e** strict typing with `any` / `@ts-ignore` / non-null assertions banned |
| `test → integrate → deploy` | a one-command setup + one-command test documented in a README; idempotent migrations; `.env.example`; **§4e** executable tests |
| `deploy` | a committed CI workflow (GitHub Actions) that runs setup + test from a clean clone, and is green; **§4e** duplication + dead-code scanning wired (report-only is fine) |

The **§4e** rows are the *unread-safe* half: they check that a mechanical rejection layer is configured
(ESLint/biome/ruff/golangci/rubocop bars, `tsconfig` strict, jscpd/knip/ts-prune/vulture), not that it
currently passes — CI runs it. Language-appropriate: a Ruby repo satisfies the complexity bar with
rubocop's `Metrics/MethodLength`, and a repo with no static type layer marks the type check `n/a`
rather than failing it. Two operating rules the bar assumes: **drain then ratchet** (land a strict rule
as a warning, drive violations to zero, *then* make it an error — a rule that is on and violated
everywhere enforces nothing), and **exceptions in the config with a reason**, never an inline
`eslint-disable` (invisible at review time, and nobody ever deletes one).

It checks *presence/shape*, not correctness ("is there a lockfile", not "does install work") — the
gate re-runs setup+test from a clean clone for the correctness half. Presence is the cheap
deterministic first tooth; the clean-clone re-run is the expensive second one the deploy pipeline
performs.

### GitHub Issue projection (`github_sync.py` — the web harness, `integrations/web`)

Projects the org's backlog onto GitHub Issues so an org can be steered from a phone. **SSoT is
unchanged** — the ledger stays authoritative; Issues are its regenerated window (R0: labels are the
lock, the native sub-issue is the hierarchy). Two levels:

- **objective Issue** (`orgforge:kind:objective`) — the big-picture RFP/objective (parent). Created by
  `/orgforge-plugin:org-found` after CEO sign-off.
- **task Issue** (`orgforge:kind:task` + `orgforge:dept:<name>`) — a department's unit of work, linked
  as a **native GitHub sub-issue** of its objective. Created by `/orgforge-plugin:org-decompose` (RFP-derived, one per
  atomic unit, carrying a `coverage_row:` trailer) or by `/orgforge-plugin:org-discover` (self-raised, no trailer).

```
github_sync.py create --repo R --kind objective --objective <id> --title T                # the parent
github_sync.py create --repo R --kind task --parent <objective#> --dept D --objective <id> --title T
github_sync.py claim  --repo R --issue N --agent A     # exit 10 if already claimed (concurrent-write lock)
github_sync.py stage  --repo R --issue N --stage ready|in-progress|blocked|needs-human|done
github_sync.py log    --repo R --issue N --event E [--phase P] [--detail T] --event-id <ledger id>
                      [--command "<verbatim>"] [--result "<real output>"] [--files F]
                      [--next-step S] [--blocked-by B]
github_sync.py decide --repo R --issue N --event <judgment> --verdict V --why "<the reasoning>"
                              # --claimed（報告されたこと）と --verified（監督が自分で走らせて確かめたこと）を分けて書く。
                              # --verified に実行の痕跡が無い / --claimed の条件節が --verified で触れられていないと警告
                              # （実地で「このブランチには無い」が要約で消え、gate の reject 事由になった）
                      [--by ROLE] [--phase P] [--evidence E] [--alternatives A]
                      [--standard S] [--risk K] --event-id <ledger id>
github_sync.py ready  --repo R [--kind task|objective|any]   # tasks only by default (objectives are parents)
github_sync.py branch --repo R --issue N [--create] [--worktree] [--no-worktree] [--base B]
                              # the deterministic feat/issue-N-<slug>
                              # **.orgforge/wt/issue-* がある org では --create が worktree を作る**
                              # — メインのブランチは動かさない（実地でメインが develop から
                              #   離れ、develop での統合テストが別 Issue のブランチ上で走りかけた）
                              # あえてメインで切り替えるなら --no-worktree
github_sync.py split-check    --repo R --issue N   # exit 10: 起票の SHAPE 検査（警告のみ）
                              # (a) owns が複数 territory (b) depends_on が OPEN
                              # (c) 受入基準が EARS でない
                              # (d) 認可の MUST が「入った後に何ができるか」を定めていない
                              # (e) 壊れ方が2種類以上ある（owns が同じでも別 Issue の候補）
                              # (d)(e) は実地で12周した Issue を本文だけから検出した — docs/11 §4b
github_sync.py needs-human --title T --body B [--objective O] [--parent N] [--blocks 10,11]
                      # 人間にしか実行できない前提条件を Issue にする（docs/11 §0c）
github_sync.py coverage-check --repo R [--manifest coverage-manifest.md]   # exit 10: a must-have has no Issue
```

- **`log`** appends a **work-log comment** on each milestone (`cycle_started`, `progress_recorded`,
  `phase_admitted`, `cycle_completed`), so progress accrues on the Issue as it happens. **Idempotent**:
  the comment carries a hidden `<!-- orgforge:event:<id> -->` marker keyed to the ledger event id, so a
  replay logs each milestone once (docs/11 §0). `/orgforge-plugin:org-work` calls it at each of its three record points.
  Since **human diff review is retired** (docs/11 §4f), the Issue is the org's audit record, so `log`
  takes the fields that make an entry reconstructable by someone who was never in the session:
  `--command` (verbatim, re-runnable), `--result` (**the real output, failures included** — a log of
  only successes is a fiction), `--files`, `--next-step`, `--blocked-by`.
- **`decide`** records a **judgment with its reasoning** on the Issue. A ledger verdict proves a
  decision *happened*; it does not say what was weighed. With no human approving, an unrecorded
  judgment is indistinguishable from no judgment — so judgments **double-write**: the ledger takes the
  tamper-evident receipt, the Issue takes the account (verdict, `--why` the reasoning, `--evidence`
  consulted, `--alternatives` rejected, `--standard` applied, `--risk` knowingly accepted). It
  **refuses a `--why` that merely restates the verdict** and refuses a non-judgment event class, so the
  degradation back into a rubber stamp is closed at the tool rather than left to discipline. The gate
  and skeptic call it on every admission and refutation attempt.
- Labels: `orgforge:claimed:<agent>` · `orgforge:{ready,in-progress,blocked,needs-human,done}` ·
  `orgforge:kind:{objective,task}` · `orgforge:dept:<name>` · `orgforge:objective:<id>` ·
  `orgforge:{mandate,self}` · `orgforge:off-ranking`.
- **`coverage-check`** is the **decomposition coverage gate** (docs/11 §0a). `/orgforge-plugin:org-found`'s O10 lint
  proves each must-have has exactly one owning *contract*; this proves each one reached at least one
  *task Issue*. It matches the manifest's `rfp_capability` against the `coverage_row:` trailer in each
  task Issue body — so a must-have that was designed but never decomposed (silently unbuilt, the hardest
  gap to see) exits 10. Task Issues with no trailer are reported as a note, not a failure: self-raised
  `/orgforge-plugin:org-discover` items legitimately have none.
- All three creation paths are **idempotent**: `create` no-ops when an open Issue with the same
  title+objective exists, so a re-run/replay never mints a duplicate. `ORG_GITHUB_REPO` unset ⇒ a
  ledger-only run (the projection is skipped silently).

---

## 4. Ledger events you'll touch most

The backlog and progress live in the ledger. The events that drive the metabolism:

| Event | Payload (key fields) | Meaning |
|---|---|---|
| `candidate_submitted` | `maker, candidate_id, contract_ref, source: mandate\|self` | a backlog item enters (top-down mandate or self-raised) |
| `cycle_started` | `role, candidate_id, pack_manifest_id` | a role began working a specific backlog item |
| `progress_recorded` | `role, candidate_id, fraction, phase, done_so_far, next_step, blocked_by, artifacts` | a **checkpoint** — the memory of "how far", so a context wipe doesn't lose it |
| `goal_started / goal_progressed / goal_resumed / goal_completed` | `goal_id, session_id, objective/summary/next_step/evidence` | one portable objective and its session ownership. Resume uses the prior session as a compare-and-swap expectation; completion accepts only resolvable `file:`, `git:`, or `ledger:` evidence. |
| `goal_blocker_observed / goal_blocked` | `goal_id, session_id, blocker, occurrences, evidence` | a blocker observation; only the third consecutive observation of the same blocker transitions the goal to `blocked`. |
| `goal_host_synced` | `goal_id, harness, native_state, assurance` | the explicitly-assured projection into a host-native Goal; never the portable source of truth. |
| `cycle_completed` | `role, candidate_id, outputs, …` | the item is done and drains from the backlog |
| `exposure_budget_checked` | `dimension, committed_so_far, delta_requested, cap, decision` | one blast-radius cap decision (allow / hold) |

**The forced-SDLC phase gate** (docs/11 §2) — the mold is enforced *in the ledger*, via `requires_prior`:

| Event | Payload (key fields) | Meaning |
|---|---|---|
| `phase_started` | `deliverable, phase: requirements\|design\|implement\|test\|deploy\|operate, role` | a deliverable entered a phase. **Invalid** unless a `phase_admitted{prior(phase), verdict:pass}` exists for it (`prior(requirements)=∅`) — this is what makes a phase un-skippable. |
| `phase_admitted` | `deliverable, phase, verdict: pass\|rework\|reject, evidence_ref, admitter` | a gate ruled on a phase; a `pass` is the precondition the *next* `phase_started` requires. |

**The operate instruments** (docs/05 §reliability-budget / §DORA, docs/11 §4):

| Event | Payload (key fields) | Meaning |
|---|---|---|
| `reliability_budget_checked` | `service, slo, window_id, budget_total, budget_burned, budget_remaining, deploy_verdict: allow\|freeze, caused_by_event` | the SRE error budget the deploy gate reads. Silent while healthy; surfaces on the transition to `freeze`; a fast burn escalates as a systemic regression. |
| `dora_snapshot` | `window_id, deploy_frequency, lead_time_p50, change_fail_rate, mttr_p50, inferred_bottleneck: design\|review\|test\|deploy\|operate, delta_vs_prior` | DORA's four keys computed from the ledger's own events; names the **moving bottleneck**. Escalates only when a key regresses past a systemic threshold or the bottleneck moves. |

Views (read with `python3 tools/ledger.py view <root> <view>`):
- `open_experiments` — the backlog (submitted, not yet completed).
- `work_in_progress` — started-but-not-completed candidates with their latest checkpoint (the resume source).
- `goal_state` — the folded persistent objective, owning session, progress, blockers, completion evidence, and per-host synchronization.

**Idempotent append** (docs/11 §0 reproducibility): `ledger.py append … --natural-key <key>` makes a
write **idempotent** — if an event of the same class with that natural key already exists in history,
the append is a **no-op (exit 0)** instead of a duplicate. A retried tick or a replayed phase
transition lands the same event once, so the log is a deterministic function of the spec + actions
(the same guarantee the phase-gate needs to be reproducible).

---

## 5. Troubleshooting

**"org guardrail HELD this … `committed_so_far … > cap`" — everything is blocked.**
The daily budget for a dimension is spent. First check it is not a stale window: the cap resets daily
by default, so a restart usually clears yesterday's exhaustion. If real work legitimately exceeds the
default in one day, raise that dimension's cap — e.g. `ORG_CAP_DESTRUCTIVE_OPS=100`. Do **not** set
`ORG_WINDOW=all` to escape a block (that removes the daily reset and re-creates the deadlock).

**A benign command (`ls`, `git status`, `find`, an unfamiliar CLI) seems to draw down the budget.**
It shouldn't anymore — only explicit destructive/external/infra patterns are metered; unknown and
read-only shell are not. If you see this, you are on an old plugin version — update it (§ below) and
restart.

**A read-only search with `2>/dev/null` (or `> /dev/null`) is flagged as destructive.**
Fixed — the redirect check now excludes `/dev/*` sinks and stderr redirects, so `grep … 2>/dev/null`
and `cmd > /dev/null 2>&1` are not metered; only a real overwrite of a system path (`> /etc/…`) is.
Update the plugin and restart. (Before the fix, this was the most common cause of a slowly-draining
`destructive_ops` budget.)

**A path like `.../fx-ml-platform/...` was flagged as a destructive `rm`.**
Fixed by word-boundary matching — update the plugin and restart. The classifier tokenizes now, so a
path containing `rm`/`form`/`-f` bytes is not mistaken for the `rm` command.

**Doctrine / work-in-progress isn't injected at session start.**
The SessionStart injection needs `ORG_ROLE` and `ORG_LEDGER_ROOT` (and `ORG_DOCTRINE_ROOT` for
doctrine). Confirm all three are set in your settings.

**Updating the plugin after a fix.**
```
claude plugin update orgforge-plugin@orgforge-plugin --scope <project|user>
```
Then **restart Claude Code** — "Restart to apply changes" means the new hook code is not live until you do.

**A due check reports MISS.**
`tick.py` found no proof-of-run for a check that was due — the scheduler may be down. It is a paged
fact by design (silence must not read as success), not a bug in the org.

**A catastrophic command was hard-blocked (`HARD-BLOCKED`), not just budget-metered.**
`rm -rf /`-class deletes, `mkfs`, `dd` to a raw disk, and fork bombs are blocked unconditionally — the
blast-radius cap is a daily budget and cannot stop a single unrecoverable command, so these are refused
regardless of budget and even with no ledger. Ordinary deletes (`rm -rf ./build`, `node_modules`) are
NOT hard-blocked (only cap-metered). To run such a command in a disposable sandbox, set
`ORG_ALLOW_CATASTROPHIC=1` — never in an environment with real data.
