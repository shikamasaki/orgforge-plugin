---
description: One-command adoption for an existing repository — prepare local orgforge state, read the real code, write the minimal organization and architecture, record remaining work and the current baseline, then verify readiness. No prior /org-init required.
argument-hint: "[残りの要求 or ブリーフへのパス]"
allowed-tools: Bash(*), Read, Write, Edit, Glob, Grep, Agent, Task, WebFetch, WebSearch
---

**すでにコードがあるリポジトリ**を1回のコマンドでorgforgeの管理下に入れる。
入力はRFPではなく **実在するコード**である。

このコマンドは導入を途中で別commandへhandoffしない。local state準備、現状読解、最小chart、
architecture、remaining-work manifest、baseline、doctorまでを同じinvocationで完了する。

**通常導入で行わないこと:** network access、GitHub Issue作成、branch作成、daemon、sudo、
credential設定。GitHub backlogへのprojectionは導入後の任意操作であり、導入成功の条件ではない。

`/org-found` をそのまま既存リポジトリに使ってはいけない。あれは「これから作るもの」を設計する
コマンドで、実在のディレクトリ構造を見ない。結果 `ARCHITECTURE.md` が実際のコードと食い違い、
`owns:` の territory が存在しないパスを指し、**下流の全タスクが嘘の地図の上を走る**。

> **出力言語:** `constitution.yaml` の `output_language` を読み、人間向けテキストはその言語で書く。

## 0. どこに導入するのか — 書き込む前に確認する

!`python3 "${CLAUDE_PLUGIN_ROOT}/tools/adopt.py" inspect .`

上が目的のリポジトリでなければ止める。コミット数が 0 なら新規リポジトリなので
**`/org-found` を使うこと**（このコマンドは既存コードを読む前提で、読むものが無い）。

## 1. local stateを安全に準備する

orgが無ければ、この会話の人間向け言語に合わせて`ja`または`en`を選び、次を実行する。
既存fileは上書きされないので、再実行は修復として安全である。

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/tools/adopt.py" prepare . --language <ja|en>
```

`<ja|en>`を会話の言語で置き換えてBash実行する。英語を使っている場合は**最初から**`en`を選ぶ。
既存`constitution.yaml`がある場合、prepareはその言語設定を変更しない。

### 1a. 既存orgforge運用を更新する

`inspect`が`existing org: yes`なら、既存ledgerを捨てて初期化してはいけない。まずschemaを
追加方向だけで更新し、hash chainを再検証する:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/tools/ledger.py" schema --fix
python3 "${CLAUDE_PLUGIN_ROOT}/tools/ledger.py" schema
python3 "${CLAUDE_PLUGIN_ROOT}/tools/ledger.py" verify
```

次に既存`role-settings.yaml`を読む。`defaults.tier: A|B`は廃止済みなので削除し、makerには
`read/write/edit/grep/run_tests/web_read/network`を明示する。gate/skepticはread-onlyを保ち、
`deploy/secrets/asset_movement/external_publish/production_deploy`をどのroleのallowにも入れない。
これらの保護はrole policyではなくhost platformのcredential custodyとapprovalが担う。
`constitution.yaml`にTier A/Bごとの封じ込め保証が残っていれば、同じhost責務へ書き換える。

この更新は既存eventを書き換えない。`legacy_unvalidated`は履歴上そのまま残し、新規eventだけを
現行schemaで検証する。`ledger.jsonl`、`HEAD`、event件数、tip hashが更新前後で不変であることを
確認してから先へ進む。

## 2. 既存コードを読む — 設計するのではなく、**現状を記述する**

ここが `/org-found` との本質的な違い。コードが正であり、文書はその写像である。

まず構造を把握する（隠しディレクトリと vendor を除く）:

!`find . -maxdepth 2 -type d -not -path '*/.*' -not -path '*/node_modules*' -not -path '*/vendor*' 2>/dev/null | head -30`

!`echo "--- 言語構成 ---"; git ls-files 2>/dev/null | sed -n 's/.*\.\([a-z]*\)$/\1/p' | sort | uniq -c | sort -rn | head -8`

次に、以下を**読んで**から書く（推測しない）:

- **README** — 作者の意図。目的を書き起こす一次資料
- **依存マニフェスト**（package.json / pyproject.toml / go.mod …）— 技術選択は**既に決まっている**
- **ディレクトリの実体** — これが `owns:` の territory になる。論理的に美しい分割ではなく、
  実在するパスを使う
- **テスト** — 何が保証されていて何がされていないかの最も正直な記録
- **最近のコミット** (`git log --oneline -30`) — いま何が動いているか

### 2a. `ARCHITECTURE.md` を書く（docs/11 §0a の固定名）

**現状の記述**として書く。「こうあるべき」ではない。含めるもの:

- 技術スタック — 既に採用されているもの（変えたいなら別途 CEO 判断。ここでは記述に徹する）
- 層とコンポーネント — 実在するディレクトリに対応させる
- データモデル — スキーマ/マイグレーション/型定義から読み取る
- **シーム契約** `{deliverable, standard, checker, depends_on}` — ここだけは新規に**決める**
  必要がある。既存コードには「誰が何を保証するか」が書かれていないことが多いため。
  ただし `owns:` は実在パスから取ること
- **既知の負債** — 動いているが直したい箇所。ここに書いておくと後で `nearby_deaths` に効く

### 2b. `organization.yaml` を書く

役割はディレクトリ構造から導く。`owns:` が互いに素になるように分ける
（重なると並行作業で衝突する）。既存の分割が既に互いに素でないなら、それ自体が発見であり、
`ARCHITECTURE.md` の負債として記録する。

**`organization.yaml` を書いた後に、あなた自身が Bash で実行すること**（`!` の自動実行では
まだ存在しないファイルを検査してしまう）:

```
python3 "${CLAUDE_PLUGIN_ROOT}/tools/org_lint.py" organization.yaml constitution.yaml moves.yaml ledger-schema.yaml sensors.yaml role-settings.yaml
```

lint が通るまで直す。通らない chart は導入されていない。

## 3. `coverage-manifest.md` — **未実装のものだけ**を載せる

`/org-found` の manifest は「全 must-have」だが、途中導入では**もう実装済みのものがある**。
実装済みを行に入れると `coverage-check` が GAP と判定し、動いているものを作り直す Issue が生える。

各要求について、コードを見て判定する:

| 状態 | manifest への扱い |
|---|---|
| **実装済み・テストあり** | 行に**入れない**。代わりに `ARCHITECTURE.md` に現状として記述 |
| **実装済み・テストなし** | 行に**入れる**（deliverable = 「Xのテストを書く」）。テストのない機能は保証がない |
| **部分実装** | 行に入れる。deliverable は**残りの差分だけ**を書く（全体を作り直さない） |
| **未実装** | 行に入れる。`/org-found` と同じ |

$ARGUMENTS が与えられていれば、それが「これから作るもの」の入力。無ければ README と
Issue/TODO から未実装分を拾う。

## 4. 機械バーの現状を baseline として記録する（docs/11 §4e）

**これが途中導入の要。** 既存コードは §4e のバー（複雑度上限・型の逃げ道封鎖・重複スキャン・
マルチOS CI）をまず満たさない。バーが存在する前に書かれたのだから当然で、これは欠陥ではなく
**開始地点**である。

初日から全部 error にすると赤の壁ができ、予測どおり「抑制コメントで黙らせる」文化が育つ
——**バーを無効化する形でバーを満たす**という最悪の結末になる。だから採用時点の失敗を
「既知の負債」として記録し、以後は**新たな失敗だけ**を止める:

!`echo '現状を測る: python3 "'"${CLAUDE_PLUGIN_ROOT}"'/tools/repro_lint.py" check . --phase deploy'`

!`echo 'baseline を記録: python3 "'"${CLAUDE_PLUGIN_ROOT}"'/tools/repro_lint.py" baseline .'`

記録後は `.orgforge/repro-baseline.json` が生まれ、以降の `repro_lint check` は:

- **既知の負債** → ▲ で報告するが**ブロックしない**（作業が進む）
- **baseline に無い失敗** → ✗ で**ブロック**（この変更で壊した＝止める）
- **負債が返済された** → 「締め直せ」と促す。`baseline` を再実行すると以後その項目は保護される

**baseline は免罪符ではない。** 期限のない免除でもない。返済すべき負債の一覧であり、
`/org-discover` が拾うべき自己起票のネタでもある。新しい失敗を baseline に吸収させるのは
「壊した」を「許容する」に書き換える操作で、ツールが警告する。

## 5. 導入の判断を残す（docs/11 §4f）

`ARCHITECTURE.md`に、なぜこのrole境界を採用し、どの負債をbaselineへ置いたかを短く残す。
GitHub remoteと認証が利用可能で、**人間がIssue projectionを求めた場合だけ**objective Issueへ
同じ判断を投影する:

!`echo 'python3 "'"${CLAUDE_PLUGIN_ROOT}"'/tools/github_sync.py" create --kind objective --title "<既存リポジトリの orgforge 導入>" --body "<ARCHITECTURE の要約 + 既知の負債 + manifest の方針>"'`

!`echo 'python3 "'"${CLAUDE_PLUGIN_ROOT}"'/tools/github_sync.py" decide --issue <N> --event scope_decided --verdict admit --by supervisor --why "<既存コードのどこを現状として受け入れ、何を未実装として manifest に載せたか、その判断根拠>" --evidence "<repro_lint の baseline 結果、テストの実行結果>" --risk "<受け入れた既知の負債>"'`

## 6. 1回の承認とdoctor

次を人間へ一度だけ提示し、accept/reviseを求める:

- 読み取った現状（層・技術スタック・実在する owns）
- **既知の負債**（repro_lint baseline の中身）とその返済方針
- manifest に載せた未実装分の件数と、載せなかった実装済みの件数
- 最小chartとchecker境界
- orgforgeが有効にするもの／有効にしないもの

reviseならこのinvocation内で修正する。accept後に:

!`python3 "${CLAUDE_PLUGIN_ROOT}/tools/adopt.py" doctor .`

`READY`になるまで不足を直す。最後に次だけを報告する:

- `ADOPTED`
- setup所要時間
- 作成したfile
- enabled: workflow order / maker-checker separation / evidence ledger / human-held irreversible actions
- not enabled: hostile-process containment / credential isolation / immutable storage
- 次の通常作業をそのまま依頼できること

`/org-decompose`は大きな既存backlogをGitHub Issueへ展開したい場合だけの任意commandであり、
導入完了のために人間へ実行を要求しない。

## 規律

- **コードが正、文書は写像。** 現状と食い違う `ARCHITECTURE.md` は無いより悪い（嘘の地図）
- **動いているものを作り直さない。** 実装済みは manifest に入れない
- **負債を隠さない。** baseline は「見なかったことにする」ではなく「記録して返す」ための道具
- **設計しない、記述する。** 変えたい点があれば負債として記録し、CEO の判断を仰ぐ
