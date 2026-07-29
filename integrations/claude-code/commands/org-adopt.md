---
description: 既存リポジトリに orgforge を後付けする — 実在するコードから ARCHITECTURE.md と organization.yaml を「読み取って」書き、未実装分だけを coverage-manifest に載せ、機械バーの現状を baseline として記録する。/org-found の途中導入版。
argument-hint: "[残りの要求 or ブリーフへのパス]"
allowed-tools: Bash(python3 *), Bash(echo *), Bash(git *), Bash(ls *), Bash(find *), Read, Write, Agent
---

**すでにコードがあるリポジトリ**を orgforge の管理下に入れる。`/org-found` の途中導入版であり、
違いは入力が RFP ではなく **実在するコード**である点にある。

`/org-found` をそのまま既存リポジトリに使ってはいけない。あれは「これから作るもの」を設計する
コマンドで、実在のディレクトリ構造を見ない。結果 `ARCHITECTURE.md` が実際のコードと食い違い、
`owns:` の territory が存在しないパスを指し、**下流の全タスクが嘘の地図の上を走る**。

> **出力言語:** `constitution.yaml` の `output_language` を読み、人間向けテキストはその言語で書く。

## 0. どこに導入するのか — 書き込む前に確認する

!`echo "  導入先: $(pwd)"; echo "  remote: $(git remote get-url origin 2>/dev/null || echo '(なし)')"; echo "  追跡ファイル数: $(git ls-files 2>/dev/null | wc -l | tr -d ' ')"; echo "  コミット数: $(git rev-list --count HEAD 2>/dev/null || echo 0)"`

上が目的のリポジトリでなければ止める。コミット数が 0 なら新規リポジトリなので
**`/org-found` を使うこと**（このコマンドは既存コードを読む前提で、読むものが無い）。

## 1. まず `/org-init` が済んでいること

!`D="${CLAUDE_PLUGIN_ROOT}/tools/discover.py"; R="$(python3 "$D" root 2>/dev/null)"; if [ -n "$R" ]; then echo "  org root: $R"; echo "  ledger  : $(python3 "$D" ledger)"; echo "  repo    : $(python3 "$D" repo 2>/dev/null || echo '(GitHubリモートなし=ledger-only)')"; else echo "  STOP — org が見つからない。先に /org-init をここで実行すること。"; fi`

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
python3 "${CLAUDE_PLUGIN_ROOT}/tools/org_lint.py" organization.yaml constitution.yaml moves.yaml ledger-schema.yaml sensors.yaml
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

## 5. 導入の判断を記録する（docs/11 §4f）

人間の diff レビューは廃止されているので、**なぜこの形で導入したか**が記録されないと後から辿れない。
objective Issue を立て、そこに記録する:

!`echo 'python3 "'"${CLAUDE_PLUGIN_ROOT}"'/tools/github_sync.py" create --kind objective --title "<既存リポジトリの orgforge 導入>" --body "<ARCHITECTURE の要約 + 既知の負債 + manifest の方針>"'`

!`echo 'python3 "'"${CLAUDE_PLUGIN_ROOT}"'/tools/github_sync.py" decide --issue <N> --event scope_decided --verdict admit --by supervisor --why "<既存コードのどこを現状として受け入れ、何を未実装として manifest に載せたか、その判断根拠>" --evidence "<repro_lint の baseline 結果、テストの実行結果>" --risk "<受け入れた既知の負債>"'`

## 6. CEO に報告して止まる

`/org-found` と同じく**設計のみ**。報告する内容:

- 読み取った現状（層・技術スタック・実在する owns）
- **既知の負債**（repro_lint baseline の中身）とその返済方針
- manifest に載せた未実装分の件数と、載せなかった実装済みの件数
- CEO の判断が要るもの（スタックを変えるか、負債のどれを優先返済するか）

承認後は `/org-decompose` から通常フロー。

## 規律

- **コードが正、文書は写像。** 現状と食い違う `ARCHITECTURE.md` は無いより悪い（嘘の地図）
- **動いているものを作り直さない。** 実装済みは manifest に入れない
- **負債を隠さない。** baseline は「見なかったことにする」ではなく「記録して返す」ための道具
- **設計しない、記述する。** 変えたい点があれば負債として記録し、CEO の判断を仰ぐ
