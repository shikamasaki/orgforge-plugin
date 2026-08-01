# Quickstart — install and run in a few minutes

> **Official standalone versions:** [English](docs/en/quickstart.md) ·
> [日本語](docs/ja/quickstart.md)

The happy path: **found an AI-native IT business company, watch it build and ship a backlog item
through the forced SDLC (requirements → design → implement → test → integrate → deploy → operate), and put it
into continuous operation** — all on a real Claude Code session, with the guardrails actually
enforcing at the tool boundary. It does not require publishing the repo — a private GitHub repo or a
local path both work (see [Distribution](#distribution) at the end).

The company builds through a **non-skippable phase mold** and ships **reproducibly**: same org spec +
RFP ⇒ same process, gates, and contracts, and the repos it produces clone-and-run the same for anyone
(docs/11 §0/§4a). Proving a guardrail blocks is *one step* along the way, not the point — the point is
that the company builds and ships something reproducibly through that mold.

> For the whole-system picture — the ecosystem (neutral core → projection → harness), the organs, and
> the two coupled lifecycles (the org's metabolism and the product's SDLC) — read
> [ARCHITECTURE.md](ARCHITECTURE.md). This quickstart is the hands-on path through it.

> **保証範囲。** このQuickstartは幻覚・迎合・確認不足・phase省略・誤操作を対象にする。
> `cross-harness` は異なるモデル系統によるレビューの非相関化、ローカル署名は `attested`、
> writerは `process_mediated` が既定である。別UID、KMS/HSM、外部judgeは不要であり、
> separate-UID writer isolationはsupported coreへ採用していない実験なので、この手順では使わない。

## 1. Install the plugin

```
/plugin marketplace add <owner>/orgforge-plugin      # GitHub リポジトリを参照する
/plugin install orgforge-plugin@orgforge-plugin      # scope は user を選ぶ（全プロジェクトで有効）
/reload-plugins
```

**ローカルディレクトリ参照（`marketplace add /path/to/orgforge-plugin`）は使わないこと。**
そのマシンでしか動かず、**未コミットの変更がそのまま動いてしまう** — 検証していないコードで
org を動かすことになる。GitHub 参照なら、どのコミットで動いているかが `installed_plugins.json`
に記録される。

プラグインを直したときの手順（GitHub 参照にすると push が必須になる）:

```
integrations/claude-code/build.sh          # バンドルを neutral core から再生成
integrations/claude-code/build.sh --check   # 同期を確認（CI ゲート）
python3 -m pytest tests/ -q                 # テスト
git commit && git push
/plugin marketplace update orgforge-plugin  # セッション側で取り込む
/plugin update orgforge-plugin@orgforge-plugin
```

インストールせずヘッドレスで動かす場合:

```
echo "your prompt" | claude -p --plugin-dir integrations/claude-code \
  --allowedTools "Bash,Write,Agent"
```

マニフェストを触ったら `claude plugin validate integrations/claude-code --strict` で検証する。

## 2. セットアップは不要 — org は発見される

**環境変数を設定する必要はない。** org はディスク上の場所（`organization.yaml` の隣の
`.orgforge/`）であり、バックログのリポジトリは `git remote origin` が指す先。どちらも
チェックアウトを見れば分かる事実なので、organ とガードレールのフックは**自分で見つける**
（`tools/discover.py`）。

これは利便性の話ではない。`/Users/someone/proj/.orgforge/ledger` のような絶対パスで
アドレスされる org は**別のマシンで動かない**。Issue に仕様を全部書く意味は「どの環境でも
拾える」ことにあるので、そこが壊れると設計全体が崩れる。さらに、**マシンごとに繰り返す
セットアップ手順は必ず飛ばされる** — そして飛ばされたとき、ガードレールは ledger を
見つけられず**黙って全部を許可する**。発見はその失敗モードを消す。

副次的な効果として、**1つの環境で複数のリポジトリの org を同時に運用できる**。
`cd` するだけで対象の org が切り替わり、監査記録も blast-radius の予算も混線しない。

```
cd ~/product-a && /orgforge-plugin:org        # product-a の org
cd ~/product-b && /orgforge-plugin:org        # product-b の org（独立）
```

### 上書きが要る場合だけ環境変数を使う

明示的な引数 > 環境変数 > 発見、の順で優先される。既定の経路はどれも要らないが、
ledger を意図的にチェックアウトの外に置く場合や CI で固定する場合には使える。

| 変数 | 用途 | 既定 |
|---|---|---|
| `ORG_LEDGER_ROOT` | ledger を別の場所に置く | 発見（`.orgforge/ledger`） |
| `ORG_GITHUB_REPO` | バックログのリポジトリを固定する | 発見（`git remote origin`） |
| `ORG_ROLE` | このセッションがどの役割か（doctrine 注入と resume のキー） | (なし) |
| `ORG_DOCTRINE_ROOT` / `ORG_CONVENTIONS_ROOT` | 別の場所に置く | 発見（`.orgforge/…`） |
| `ORG_HOOK_FAIL_OPEN` | organ がエラーのとき通す — **開発用のみ** | off（fail-safe） |

**blast-radius のキャップ・反復上限・seam ゲートは `constitution.yaml` の `enforcement:`
ブロックで宣言する**（同じ org はどこにインストールしても同じ強度で効く）。`ORG_CAP_*` などの
環境変数はその**開発用の上書き**であって、org の設定方法ではない。詳細は
[REFERENCE.md](REFERENCE.md)。

## 3. 最初にやること

既存リポジトリへ導入する場合は1コマンド:

```
/orgforge-plugin:org-adopt
```

local state準備、実在codeの読解、最小organization、architecture、remaining-work manifest、
baseline、readiness doctorまでを同じworkflowで完了する。Issue分解は必要な場合だけ後で行う。

新規orgをbriefから設立する場合は3コマンド:

```
/orgforge-plugin:org-init タテカエ ja      # 1. セットアップ（設計はしない）
/orgforge-plugin:org-found REQUIREMENTS.md # 2. 設計 → CEO 承認で停止
/orgforge-plugin:org-decompose             # 3. アトミックな task Issue へ分解
```

> **コマンド名はプラグイン名で修飾する。** 例: `/orgforge-plugin:org-init`。
> 他のプラグインと名前が衝突しないための正式な形。

`/orgforge-plugin:org-init` は**実行時のカレントディレクトリ**に org を作る。プロダクトのリポジトリで
実行すること — ステップ0が場所を表示し、プラグイン自身の開発ツリーなら停止する。

`org-init` は `repro_lint` の **baseline** も1回取る（機械バーの現時点を記録する起点）。これが
無いと、後の gate 判定で「この変更による悪化」と「元からあった負債」を区別できない — 実地では
gate が既存の負債を新規の悪化と読んで判定を止めた。新規リポジトリなら失敗はほぼ無く、それが
正しい出発点になる（以後の悪化が全部見える）。

## 4. Sanity-check: a guardrail actually fires

Before founding a company you'll trust to fan out, confirm the teeth are live. With `ORG_LEDGER_ROOT`
set and a low cap, a runaway is blocked at the tool boundary — one quick check, not the headline:

```
mkdir -p /tmp/myorg/.orgforge/ledger && cd /tmp/myorg   # org として発見される最小構成
export ORG_CAP_DESTRUCTIVE_OPS=2
echo '{"hook_event_name":"PreToolUse","tool_name":"Bash","tool_input":{"command":"rm -rf /tmp/x"}}' \
  | python3 integrations/common/org_hook.py; echo "exit=$?  (2 = blocked)"
```

(For the full certification — including that the block fires for a *spawned subagent's* tool call —
run `/orgforge-plugin:org-verify-guards` once at founding. Caps, the iteration/cycle limits, and the seam gate are
declared in `constitution.yaml`'s `enforcement:` block; the `ORG_CAP_*` env vars above are **dev
overrides** over that spec — see [REFERENCE.md](REFERENCE.md).)

## 5. Run a department (headless)

### Three-minute reviewer-outage exercise

Before enabling an acting scheduler, run the deterministic resilience fixture. It uses a temporary
workspace, local tracker artifact, injected dependency failure, and the real judge-preflight,
adaptive-envelope, and ledger paths; it needs no network, model subscription, credential, or real
repository mutation:

```bash
orgforge resilience-exercise reviewer-outage --expect RED
```

From a source checkout, use `python3 tools/resilience_exercise.py reviewer-outage --expect RED`.
Phase A intentionally reports `RED` only for the missing `DEGRADED` operational-state transition;
safe stop is recorded as an acceptable outcome, not counted as the failure. Issue #45 turns this
same fixture GREEN rather than replacing it with a second test path.

A "department" is a Claude Code (or Codex) turn pointed at one role's profile. Use the runner —
it projects the role onto the harness and attaches the plugin so the guardrails apply:

```
python3 integrations/runner/run_department.py --harness claude --role <role> \
  --task "…" --ledger $ORG_LEDGER_ROOT --doctrine $ORG_DOCTRINE_ROOT \
  --tools read,write,run_tests --dry-run     # drop --dry-run to actually run
```

## 6. Start the metabolism — one command brings the org to its running state

Once an org is defined (§7) and `ORG_LEDGER_ROOT` + `ORG_ROLE` are set, **run `/orgforge-plugin:org-start`**:

```
/org-start [role] [tick-min] [work-min] [discover-hours]     # defaults: supervisor 15 60 6
```

It prints three **`/loop`** invocations that drive this session's cycles, so the org runs itself **while
this session is open**:

```
/loop 15m /org-tick               # monitoring: due/MISSED checks, stalls, repeated deaths
/loop 60m /org-work supervisor    # the PM loop: select, delegate, record
/loop 6h  /org-discover supervisor # raise self-tasks from aspiration gaps
```

The drive is delegated to Claude Code's built-in `/loop` (R0 — borrow the harness's loop, don't build
one); the org keeps only the monitoring `/loop` can't give it (the missed-tick detector in `/orgforge-plugin:org-tick`).
You usually won't type `/orgforge-plugin:org-start` yourself — on an org session the SessionStart hook prompts the model
to run it. Check on the org any time with **`/orgforge-plugin:org`**.

**Session-scoped:** these `/loop` cycles run while this Claude Code session is open and stop when it
closes. For a genuinely 24/7 org with no session open, use an OS-level cron —
`integrations/claude-code/scheduler-install.sh` (see [SCHEDULER.md](integrations/claude-code/SCHEDULER.md)) —
a separate, explicit setup.

**Check on it any time with `/orgforge-plugin:org`** — one GREEN/AMBER/RED board: what it did, what's in progress, and
whether it needs you. You don't read the ledger; `/orgforge-plugin:org` tells you in plain language. Feed new work in
with `/org-triage <a bug/issue/idea>` (or drop it on the backlog); the org works it on its own.

### The three cycles it runs

The running loop is three commands operating on the **one backlog per department** — the
`open_experiments` ledger view — which holds both top-down **mandate** items and self-raised **self**
items on one footing.

```
/org-work <role>       # the PM loop: select from the backlog by attention, delegate the selected
                       #   items to subordinates in PARALLEL (one Task each, where the split is
                       #   genuine), then record cycle_completed. This ACTS.
/org-discover <role>   # problemistic search: surface aspiration gaps and raise them as source:self
                       #   backlog items. Adds to the backlog; never executes. Fail-quiet if no gap.
/org-tick              # read-only health: which checks are due / MISSED, sensors, chain integrity.
```

`/orgforge-plugin:org-work` uses `attention.py` to prioritize the whole backlog (situated attention to the org
ranking + problemistic-search boost), **floors an in-zone mandate** so a live instruction is not
starved by low-priority self work, and picks a prefix within the WIP limit. Delegation follows the
decomposition doctrine (docs/03): split only genuinely independent work, never split coupled work,
each child carries a seam contract.

### Session-scoped vs. genuinely 24/7

`/orgforge-plugin:org-start` schedules the cycles **within this session** (Claude Code's `CronCreate` / `/schedule` are
session-only — they stop when the session closes). That is the right default for an attended or
kept-open session. For an org that must run with **no session open**, install the cadence on the OS
cron with `integrations/claude-code/scheduler-install.sh --role <role>` — see
[SCHEDULER.md](integrations/claude-code/SCHEDULER.md) for the difference and the full wiring.

Either way, `tick.py` detects a **missed check** (a due check with no proof-of-run in the ledger), so
"the scheduler stopped firing" becomes a paged fact, not silent drift — the org checks its own
heartbeat regardless of who fires the cadence.

## 7. Define your own org — two ways in

The plugin is the *engine*; your organization is `organization.yaml` + `constitution.yaml` +
`moves.yaml`, validated by `python3 tools/org_lint.py …`. Two starting points ship with it:

- **Write it yourself** — copy `template/organization.SKELETON.yaml` to `organization.yaml` and
  fill the `<ANGLE_BRACKET>` slots. The control skeleton (supervisor / gate / skeptic / registrar)
  is kept intact — you fill purpose, domain roles, and their contracts. Then lint it and iterate.
- **Let the org draft it** — the three-command path below. The org does its own feature inventory,
  architecture with seam contracts, and a linted `organization.yaml`, then **stops and reports up for
  your review** before anything is built (founding is design; the build is the CEO's next call).

```
/org-init      "タテカエ" ja          # 1. set up:     ledger root, spec files, .envrc, labels, develop, guard probe
/org-found     <RFP or path/to/brief> # 2. design:     the four fixed founding artifacts → STOP for your approval
/org-decompose                        # 3. decompose:  the manifest → atomic SPEC task Issues, coverage-gated
```

**Step 2 writes four files under fixed names** ([docs/11](docs/11-sdlc-mold.md) §0a) — `REQUIREMENTS.md`,
`FEATURE-INVENTORY.md`, **`ARCHITECTURE.md` (the 全体設計書)**, `coverage-manifest.md`, plus
`organization.yaml`. The names are fixed because step 3 reads them *by name*; a renamed artifact is one
no command can find. `/orgforge-plugin:org-found` is *design only* — you approve the scope. It is the moment the abstract
"org" becomes a **company**: a purpose stated as a business, a feature inventory with an explicit exclude
list, and contracts the lint's O10 tooth checks for coverage (every deliverable is owned and
independently checked — [docs/11](docs/11-sdlc-mold.md) §0, [docs/01](docs/01-requirements.md) J14/S9).

**Step 3 is what makes the design workable from anywhere.** `/orgforge-plugin:org-decompose` carves each must-have into
*atomic, independently-completable* task Issues (split wherever sibling `owns` sets are disjoint; keep
reciprocally-coupled work together), fills the full `template/SPEC.md` structure into each Issue body —
clone URL, the literal setup+test commands, entry files, MUSTs in EARS, the seam contract, the DoD
command — and hangs each one under its objective as a native GitHub sub-issue. Because the whole spec
lives *in the Issue*, any environment can claim one and start: a web session, another machine, a fresh
agent with none of your context. It ends on a **coverage gate** (`github_sync coverage-check`) that exits
non-zero if any must-have never became an Issue — the design-to-backlog gap that is otherwise invisible.

## 8. The company builds and ships — through the forced SDLC

This is the headline. Once you approve the scope and the metabolism is running (§6), the PM loop
(`/orgforge-plugin:org-work`) pulls a backlog item and the company builds it — but it cannot skip a step. Every
deliverable travels a **non-skippable phase chain**, enforced not by a prompt but by the ledger's
phase-gate (the same `requires_prior` idiom that makes the skeptic load-bearing):

```
requirements ─▶ design ─▶ implement ─▶ test ─▶ deploy ─▶ operate
     └── each phase emits phase_started; a gate emits phase_admitted{verdict:pass}
         BEFORE the next phase_started is legal (docs/11 §2)
```

What that buys you, concretely:

- **A phase cannot be skipped.** `phase_started{implement}` is *invalid* in the ledger unless a
  `phase_admitted{design, pass}` exists for that deliverable. The mold is data, enforced at write
  time — not a checklist the model can talk its way past ([docs/11](docs/11-sdlc-mold.md) §2).
- **Deploy is a real phase, and CI/CD is its spine.** The deploy gate re-runs setup + tests from a
  **clean clone** and reads a committed GitHub Actions workflow that must be green — shipping is
  continuous, not a one-time local "it worked on my machine" ([docs/11](docs/11-sdlc-mold.md) §3/§4a).
- **Reproducibility is checked, not asserted.** At the implement/test/deploy gates the gate runs
  `tools/repro_lint.py` over the repo the company built — committed lockfile, pinned toolchain,
  one-command setup+test, idempotent migrations, `.env.example`, green CI-from-clean. A repo that a
  stranger can't clone-and-run the same way is **held**, not admitted:

  ```
  python3 tools/repro_lint.py check <repo_dir> --phase deploy   # exit 0 = present · 10 = gate HOLDs
  ```

- **The company then operates.** In the `operate` phase it runs under a **reliability / error
  budget** (a `reliability_budget_checked` event freezes deploys when the budget is burned) and
  navigates by **DORA** metrics (a `dora_snapshot` names the *moving bottleneck* — when generation
  gets cheap the constraint moves downstream to review/test/deploy, and the attention layer steers
  there). See [docs/05](docs/05-lifecycle-operations.md) §reliability-budget / §DORA and
  [docs/11](docs/11-sdlc-mold.md) §4.

### 1つの Issue を回す — 実際に打つコマンド

PM ループ（`/org-work`）の中身は、この並びである。**配管はツールが回し、判断は役割が下す。**

```
org_cycle.py begin     --role R --issue N [--agent A]
  # claim → worktree(.orgforge/wt/issue-N/) → spec_delegated → phase_started → cycle_started
  #   → Issue へ log → stage。parent と candidate_id は Issue から自動解決
  # 着手前の確認（依存が rework 中か・人間の作業待ちが残っていないか）も出す。止めない

  … maker が worktree の中で作る …

org_cycle.py complete  --role R --issue N --outputs T --command CMD --result OUT
                       (--domain-model-updated REF | --domain-model-none WHY) [--learned "学び"]
  # 新しい公開面（SECURITY DEFINER 関数・grant・エンドポイント）が増えていれば、
  #   申告するまで止まる — 認可ホールは「関数を1つ足した」ところから生まれる
  # --learned は doctrine に propose される（admit は gate の仕事）

org_cycle.py handback  --issue N --summary S --result OUT      # push → PR（Closes #N）→ log
org_cycle.py verify    --issue N --role gate                   # 判定の材料を組み立てる
  # stdout = subagent に渡す本文（憲章・SPEC/MUST・判定履歴・「返すもの」の指定）
  # stderr = 監督が打つコマンド（gate が返した値を decide に流す）
  #   → subagent は判定を返すまでが役割。記録は監督が行う

org_cycle.py verify    --issue N --role skeptic                 # gate の admit 後
  # gate が既に見たことと「gate 自身が撃っていないと書いた領域」を引き渡す

org_cycle.py integrate --issue N [--plan]
  # --plan: 何を統合するか・並行 worktree との衝突を先に見せる
  # gate の admit と skeptic の survives が**台帳に**無ければ止まる（exit 4）
```

途中の状態は `org_cycle.py show --issue N` で一望する（判定履歴・周回の性質・いま何待ちか・
不可逆な変更の数）。本番資産（DB の DDL・権限）に触ったら `touched` で誰の権限で入れたかごと
残す。溜まった worktree は `gc`。誤って書いた記録や検証用のプローブは `correction` で無効を
宣言する（追記型なので消せない）。

The org and the system grow together: `operate` closes the loop back to `requirements`
([docs/11](docs/11-sdlc-mold.md) §4), and the doctrine that guides each role is retrained as the
system matures ([docs/06](docs/06-doctrine-and-knowledge.md)).

See [ARCHITECTURE.md](ARCHITECTURE.md) for the whole system and [docs/README.md](docs/README.md) for
the reasoning in four Parts / twelve chapters: `docs/01`–`docs/04` (Foundations), `docs/02`/`docs/03`/`docs/07`/`docs/08`
(Design), `docs/05`/`docs/06`/`docs/09`/`docs/10`/`docs/11` (Operate — lifecycle, doctrine, attention,
loop reliability, the SDLC mold), and `docs/12` (the north star). `demos/S1-founding-rehearsal.md` is a
worked founding; `examples/` holds real runs (doctrine scoping, seam-driven delegation).

## Distribution

Publishing to OSS is **not required**. A Claude Code plugin is installed from a git source or a
local path, so the repo's visibility decides who can install:

- **Public GitHub (OSS):** anyone — `/plugin marketplace add github.com/you/orgforge-plugin`.
- **Private GitHub:** only people with repo access (their git credentials must resolve the clone).
- **Local / hand-delivered:** `/plugin marketplace add /path/to/orgforge-plugin`.

Private and local both work today; make it public only when you want open distribution.
