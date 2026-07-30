# Changelog

All notable changes to orgforge-plugin. This project follows a pragmatic semver:
minor = new mechanisms/features, patch = fixes, major = breaking articulation changes.

> **0.12.0〜0.22.0 について。** この区間は、実際に org を回して（タテカエという PWA を
> 18 Issue に分解して作らせて）出てきた指摘を、そのまま直し続けた記録である。直した約20件を
> 並べると、ほぼ全部が同じ形をしていた:
>
> ```
> ドキュメントが「こうせよ」と述べる
>   → 守らせる機構が無い / payload のキーが揃わないと無効 / 実行手段が無い
>   → 成功して返る（無言）
>   → 守られない
>   → 検出器も board も「問題なし」と報告する（誤った安心）
> ```
>
> 最後の一段が一番効く。単に守られないだけなら気づけるが、`learning repeats` が clean と言い、
> `complete` が admit 済みでも「まだ」と言い、`log` が成功を返す。**信号が壊れているので、
> 壊れていることが分からない。** これは #7 の split() で捕まえた欠陥（性質が壊れる場所を
> テストが検証していない）と同じ構造で、プラグイン自身の統制層に同じものがあった。
>
> 対策として一貫して選んだのは「無言の素通しをやめる」こと — 拒否するか、少なくとも
> 「効いていない」と言う。0.16.0 の相関キー必須化、0.16.0 の `unknown` 報告、0.18.0 の
> reject 追跡、0.21.0 の冪等キー修正は、すべてこの一点である。

## 0.27.0

**監督（supervisor）自身の記録を機械で検査する。** 実地の依頼書より — この org は maker の
成果物と gate/skeptic の判定を機械で検査しているが、**監督の記録だけ何も検査していなかった**。
1晩の運用で監督の失敗5件のうち4件が、道具の側で捕まえられる形だった。

> この org が同じ晩に8回検出した失敗様式は「確かめていないことを、確かめたかのように述べる」で、
> それが**成果物 → 判定 → 道具 → 監督**の4層すべてに現れた。最初の3層には機械の検査がある。
> **4層目にだけ無い。**

### ① `org_cycle rework` — 記録漏れ28件の対策【最優先】

台帳を数えると reject/refuted **28件**に対し `rework_requested` が記録されていなかった
（1件は4回 reject で記録0件）。**副作用として `show` の rework 警告（0.26.0）が沈黙していた** —
台帳に材料が無いので閾値に届かない。**道具は数えられないものを数えない。**

- `rework_requested` を記録する**専用コマンド**を作った。`ledger.py append --payload '{...}'` を
  手で組む必要があったことが漏れの一因だった
- `verify` が reject/refuted のとき、**判定の記録と同じ場所**でそのコマンドを出す。発注は
  「判定 → 検証 → decide → **発注** → 記録」の順で、発注した subagent の通知が来ると記録が
  流れる。記録のコマンドが目の前にあれば順序が逆転する
- 周回数（何周目か）は自動で埋まる

### ② `decide --claimed / --verified` — 要約が条件節を落とすのを捕まえる

実地の失敗:

```
maker の報告 : 「src/db/client.ts は**このブランチにまだ存在せず** feat/issue-11 側にありました」
監督の要約   : 「maker は推測せず src/db/client.ts の loadEnv() を読んで変数を確定させた」
落ちた条件   : 「**このブランチには無い**」
```

**maker は正直に条件を書いていた。監督が要約で落とした。** その要約が gate への指示にも流れ、
gate は「そのファイルは存在しない」を reject 事由にした。

- `--claimed`（報告されたこと）と `--verified`（監督が自分で走らせて確かめたこと）に分ける
- `--verified` に実行の痕跡（コマンド・出力・`exit=`）が無ければ警告
- **`--claimed` の条件節が `--verified` で触れられていなければ警告**。条件節は種類ごとに束ねる
  （「存在せず」と「存在しない」を別物として扱うと、正しく運んでいるのに警告が出る — 実装当初
  そうなった）
- 拒否ではなく警告。判断は監督の仕事だが、条件を落としたことに気づける材料は要る
- `--claimed` / `--verified` を渡さない旧来の呼び出しは通す（後方互換）

**この検査は完全ではない。** 「確かめた」と書くだけでも通り得るし、痕跡の検査自体が
「コマンド名を書けば通る」形式化を招く。**塞げないことを正直に記録する**（docs/11）。

### ③ 実行時のバージョンと cwd を stderr に1行

```
[orgforge 0.27.0 @ /Users/shikama/tatekae]
```

実地で 0.26.0 のリリース後も **0.25.2 のパスを打っていた**（直前に使ったものを流用した）。
古いパスを打てば次の行で気づく。

**ただしこの1行が、機械可読な出力を壊した。** `ledger view`（JSON を返す）に混ざって
`JSONDecodeError` でテストが落ちた。stderr に書いていても、消費側が `2>&1` で混ぜれば同じ。
`view` / `census` / `digest` では黙り、内部呼び出し（`_run`）では `ORG_QUIET` を立てる。
**人間向けの便利のために、機械が読む出力を壊すのは筋が通らない。**

### ④ worktree の占有ロックは入れていない

「gate の稼働中に監督が同じ worktree で変異検査を走らせ、skeptic が偽の失敗を観測した」という
実害があり、警告は筋が通る。しかし同じ晩に gate が異常終了しており、**ロックの解放漏れが新しい
詰まりを生む経路が実在する**（依頼書も保留を推奨）。①②③を入れたあとの再発を見て判断する —
**詰まりを直すために別の詰まりを作らない。**

317 passed。

---

## 0.26.0

実地の報告3件 — **範囲外の発見を Issue に積み増さない**ための3層。加えて README を書き直した。

### ② skeptic の責務を2段に分けた（最も効く）

`skeptic.md` は「隣接領域を探せ」「articulation の欠陥はより重要」と**無条件に**求めていた。
skeptic は仕事として必ず何かを見つけるので、範囲を切らないと MUST と無関係な発見でも
`refuted` になる。実地では **8周 rework した Issue の4回目以降の発見が、すべて spec の MUST に
書かれていないもの**だった。

| 見つけたもの | 扱い |
|---|---|
| MUST が守ると述べたことが守られていない | `refuted` の根拠。本務 |
| MUST の範囲外の欠陥（実在するが、この Issue が守ると述べていない） | **「Issue 化を推奨」として別に返す**。verdict には数えない |
| どちらか判断が難しい | **skeptic が決めない。両方の読み方を書いて監督に返す** — carve out は監督の判断 |

「MUST の文言は満たすが意図を裏切る」ものは**範囲内**（placebo）である。線引きはそこ。
`verify` の「返すもの」にも `out_of_scope` を足した（憲章だけ直すとプロンプトと食い違う）。
`gate.md` にも同じ線を入れた — 範囲外の欠陥は `reject` の根拠にしない。

### ① SPEC に「完了の判定」を足した

```
- **完了の判定:** 上の MUST が RED→GREEN になった時点で完了とする。
  **着手後に見つかった範囲外の欠陥は、この Issue で直さず別 Issue にする。**
```

`template/SPEC.md` と `/org-decompose` の両方に。**maker・gate・skeptic の3者が同じ完了条件を
見る**のが要点で、spec 側に書かないと3者が別々の終わり方を想定する。

### ③ rework 回数を `show` が警告する

```
周回:     13 周 — 直近3回: 実装の欠陥 / テストの欠陥 / テストの欠陥
          ⚠ rework 8 回 / 判定 13 回 — 3回を超えている。
            **Issue の切り方か、完了の定義を見直す価値がある。**
```

**判定回数ではなく rework の回数で見る。** 最初は `len(rounds) > 5` も条件にしたが、
7周かかって rework 2回で収束した Issue（gate が丁寧に見た結果）まで警告した。実データで
#9（8回）と #11（6回）だけが出て、#7 / #8 / #10 は沈黙する。止めない — 材料を出す。

### README を書き直した — 英語に統一し、331行 → 215行

**私が追記した2節だけが日本語**になっていた（"How to use it" 30/77行、"Status & honesty"
18/51行）。方針を決めずに、その時の会話の言語で書き足した結果である。README は GitHub の入口で
既存の8割が英語なので、英語に統一した（日本語0行）。

取捨選択も直した。"How to use it" が **85行**あり、`worktree` の事故の詳細・`--plan` の挙動・
識別子の相関の設計まで書いていた — それは `REFERENCE.md` と `docs/11` の役割である。README は
**入口**に絞る: これは何か / なぜ org として分解するか / 何が入っているか / どこを読むか /
実運用で何が起きたか。1サイクルの具体的なコマンド列は `QUICKSTART.md` §8 に送る。

`Status & honesty` は残したが、書き方を変えた — 実運用で見つけた欠陥（統制が効いているつもりで
効いていなかった4件）と、統制が働いた実例と、**入れて取り下げた検査2件**を、いずれも短く。
道具の履歴として、入れたものと同じくらい外したものが読めるようにしている。

308 passed。

---

## 0.25.3

**ドキュメントの追随のみ**（挙動の変更なし）。0.12〜0.25.2 で入れた機能のうち、読ませる系の
文書に載っていなかったものを反映した。

| 文書 | 追随していなかったもの |
|---|---|
| **README** | 版表記が v0.22 のまま。`touched` / `split-check` / `--plan` / 「subagent は記録しない」／取り下げた検査2件の記録 |
| **QUICKSTART** | **1つの Issue を実際にどう回すか**（§8 は phase gate の説明だけで、打つコマンドの並びが無かった）。`org-init` が baseline を取ること |
| **REFERENCE** | `split-check` の新しい2検査（(d) 認可の偏り・(e) 壊れ方の数）、`baseline` を `/org-init` が取ること、`verify` の stdout/stderr の宛先の違い |
| **ARCHITECTURE** | ツール表が 0.11 相当（`begin` `complete` `plan` の3つだけ）。`orgcycle/` と `ghsync/` へのパッケージ分割と、その理由 |
| **marketplace の description** | worktree による並列分離、判断の二重記録、起票の粒度検査、baseline との差分 |

**一番の抜けは QUICKSTART だった。** phase gate の理屈は書いてあるのに、
`begin → complete → handback → verify(gate) → verify(skeptic) → integrate` という**実際の並び**が
どこにも無く、導入した人が1サイクルを回せない。ツールを足すたびに REFERENCE には行が増えて
いたが、**通しで読む文書には入っていなかった**。

304 passed（テストの変更なし）。

---

## 0.25.2

実地の報告2件。どちらも**道具が自分の限界を語らなかった / 権限のない相手に指示していた**という形。

### ① `repro_lint` が読んでいない baseline を語っていた（実害が出た）

baseline が無いときも、失敗全件にこう付けていた:

> これらは baseline に無い＝この変更で新たに悪化した、または最初から満たすべきもの。

**読んでいないものについて断定していた。** 実地で gate がこれを額面どおり受け取り、既存の
負債（`develop` 自体が同じ2件で HOLD）を「この変更による悪化」と読んで判定を止めた —
**対象の Issue は、まさにその2件を緑にする作業だった**。

いまはこう言う:

```
HELD: 2 required artifact(s) missing for the implement gate: complexity-bounded, type-escapes-closed.
  **baseline が無い**（探した先: ./.orgforge/repro-baseline.json）ので、
  **この変更による悪化か、採用前からの既存の負債かは判定していない。**
  判定に使うなら、まず基準を取ること: `repro_lint.py baseline .`
```

報告のとおり、**何も言わないより「この道具はここを見ていない」と述べるほうが、判定する側は
正しく動ける**。加えて `/org-init` も baseline を1回取るようにした（`/org-adopt` は既に
取っていた）ので、新規 org が最初の gate 判定でこれを踏むことはなくなる。

### ② subagent が記録できないのに「記録せよ」と指示していた

`agents/gate.md` と `agents/skeptic.md` は「判定を台帳と Issue の両方に記録せよ」と指示して
いたが、subagent には `ORG_GITHUB_REPO` も台帳のパスも渡っていない。**指示と権限の食い違い**。
実地で gate と skeptic が計7回、判定を出した後に「記録は監督に委ねます」と述べて止まり、
**一度は判定そのものが台帳に入らないまま失われかけた**。

報告にあった2案のうち **(b) 責務を判定に絞る**を採った — 実地でも subagent は判定に集中した
ほうが質が上がっていたし、判定者が記録も持つと独立性の検査（台帳の DISTINCT_ACTOR）が
形式化しやすい。

- `agents/*.md` を「verdict / why / evidence / standard / risk を**返す**まで」に書き換え
- `verify` の **stdout（subagent に渡す本文）から記録コマンドを削除**し、「返すもの」の指定に
- 監督が打つコマンドは **stderr**（監督向け）に出す — 配管が判定を運べなくなっては本末転倒
- skeptic には「撃ったミューテーションの一覧」も返させる（次の周回が同じ場所を撃ち直さない）

### 報告のうち1件は取り下げられた

「バッククォートがシェルに食われる」件は、報告者の再検証でツール側の問題ではないと判明。
**自分の側の誤りを取り下げる報告**は、道具を直すのと同じくらい価値がある — 誤った修正は
別の穴を作る。

304 passed。

---

## 0.25.1

**0.25.0 で入れた VOIDDEP を取り下げた。** 実地の報告: 「VOIDDEP は発火しませんでした。
REQUIREMENTS.md にバッククォート識別子が1つも無いためです」。

確認したところ、そのとおりだった — 実データの識別子は **0 件**。「利用者が表示名を変更した
とき」のように普通の名詞で書くのが自然な日本語であり、テンプレートもそう書かせている。

助詞で区切って「〜を<動詞>」を拾う実装も試したが、`利用者が支出` と `メンバーが支出` が
別物として抽出され、**全件が誤検出**になった。形態素解析を持ち込めば届くが、それは
req_lint の重さを一段変える判断になる。

形式化（QUS の `Complete`）そのものは正しい。**日本語の要求から目的語を切り出せない**という
実装上の壁で、AQUSA が意味理解を要する基準の自動化を諦めているのと同じ場所である。

**誤検出しかしない検査は、無いより悪い。** 0.24.0 で提案4（rework が MUST に対応しているか）を
見送ったのと同じ理由で戻す。狙い（要求の欠落を捕まえる）は `split-check` の「認可が境界だけを
定めていないか」が実データで機能しているので、そちらに寄せる。

再実装するなら**目的語を確実に取れる前提**（英語の要求か、識別子を義務づける記法）が要る。
テストにその条件を残した。

### 私の検証が不十分だった

VOIDDEP は**合成したテスト文書**で「検出する / 誤検出しない」を確認して出した。実際の
REQUIREMENTS.md で回していない。テストが本番と違う形を作れば、壊れる場所で検証していない
ことになる — 0.22.1 で同じ失敗をしたばかりだった。

301 passed（VOIDDEP のテスト3件を取り下げの記録に差し替え）。

---

## 0.25.0

SDD 系ツール・従来手法の分割基準を**一次資料で調べ**（Spec Kit / Kiro に加え、INVEST /
SPIDR / Humanizing Work / QUS / PBR / BMAD / Devin / Tessl / Cursor）、取り入れるべきものを実装した。
出典と原文引用は docs/sources。

### `req_lint` に VOIDDEP — 作る要求が無い対象を更新/削除している

QUS（Lucassen et al., Requirements Engineering 2016）の `Complete` の形式化:

> "to read, update or delete an item one first needs to create it"
> `voidDep(µ1) ↔ depends(av1, av2) ∧ ∄µ2 ∈ U. do2 = do1`

これは実地で踏んだ形（#11 が「誰が入れるか」を定めて「入った後に何ができるか」を定めて
いなかった）の**一般化**でもある。バッククォート付きの識別子だけを見る — 散文から名詞を
切り出すと誤検出が支配的になる。

### 「層/ファイルで割らない」を doctrine に明記

Humanizing Work の垂直スライスの定義は *"a work item that delivers a valuable change in system
behavior such that you'll probably have to touch **multiple architectural layers**"* —
**複数層に触ることを肯定的に含む**。層ごとに割るのは independent でも valuable でもない
失敗パターンとして名指しされている。

つまり **`owns`（同じファイルを触るか）を分割の判断基準にすることは、既存の規範体系では
反パターン**である。`owns` は衝突の回避には正しいが、分割の判断そのものではない。

### INVEST の *Small* の根拠を doctrine に引いた

> "Above this size, and it seems to be too hard to know what's in the story's scope"（Wake 2003）

根拠は見積精度ではなく**スコープの境界が認識できなくなること**。実地の #11 はまさにそれで
5回スコープが変わった。

### 調査で分かった業界の実態

**過大タスクの検出は、調べた範囲のどのツール・手法も持っていない。** Spec Kit の `analyze` の
Detection Passes に粒度の検査は無く、Kiro は人間の承認ゲートのみ。BMAD は同じ機能要求
（Issue #1471）が**未解決のまま放置**され、学術側の AQUSA も Estimatable の自動化を
「意味理解を要する」として明示的に諦めている。定量閾値を持つのは Devin の *"three hours or
less"* だけで、事前 lint ではない。

**「壊れ方が違えば別単位」を規範として明文化した先例も見つからなかった。** PBR が「検証手段を
起点に据える」点で最も近いが、あれは分割ではなく検査の規範である。0.24.0 で足した軸は、
既存手法の空白に置いたことになる。

### 誤検出の確認

0.24.0 の split-check を tatekae の全 Issue（#7〜#20）で回した。**追加した2種が出るのは14件中5件**
（#11 #12 #14 #16 #18）で、内容を確認するといずれも妥当だった — #16 は精算の状態機械で
MUST 15件中認可が1件、#18 は内側に触れているのが「あだ名」だけ（#11 の再現）。
`depends_on` の重複警告（同じ依存が3行出ていた）も直した。

303 passed。

---

## 0.24.0

タテカエ org からの要望書（`/org-decompose` の分割基準）に対応。**実測が明快だった**:

| Issue | 判定回数 | rework | 生んだ migration |
|---|---|---|---|
| #11 中核スキーマと RLS | **14** | **5** | 0007〜0011（相互干渉） |
| #9 PWA シェル | 13 | 7 | — |
| #8 settle() | 3 | 0 | — |
| #10 CI | 2 | 0 | — |

#8 と #10 は1〜2周で通り、#11 は12周でも終わらなかった。

### 分割の軸に「壊れ方」を足した

現行の基準は `owns` の交わり1本で、これは **Spec Kit の `[P]`（"different files, no
dependencies"）と同じ判定**であり、同じ限界を継承していた。#11 は `supabase/` に閉じていたので
分割されなかったが、中身は「スキーマの形（型・制約で守る）」と「認可（攻撃シナリオで守る）」
という**壊れ方も検証手段も別の2つ**だった。

> この deliverable が壊れたとき、**壊れ方は1種類か**。検証に必要な手段は**1種類か**。

Kiro の *"Implement X function" rather than "Support X feature"* が同じことを別の言い方で
述べている。`/org-decompose` の doctrine に書き、`split-check` が起票後に警告する。

### 要求が薄い領域を検出する

#11 の EARS 12件のうち認可を定めたものは4件で、**そのどれも「入った後に何ができるか」を
定めていなかった**（内側に触れていたのは「あだ名」＝装飾的なテキスト列だけ）。金額・支払者・
債務の向き・所有権は無防備で、後半6周の rework は Issue のどの MUST にも対応しなかった。

`split-check` が「境界だけを定めて内側を定めていない」認可要求を警告する。実データで **#11 だけ
2件検出し、#7 / #8 / #9 / #10 は0件**（#9 が長引いたのは分割の問題ではない、という報告とも一致）。

### この Issue が生んだ不可逆な変更の数を出す

#11 は migration を5本生み、それらが相互干渉した（0009 が直したものを 0010 が壊し、0011 が
別の2件を RED にした）。3件以上で `show` が材料を出す。**止めない。**

### 提案4（rework が MUST に対応しているか）は見送った

語彙の重なりで判定してみたが実データで誤検出した — 完了済みの #7 に「スコープ外」と警告し、
本当にスコープ外だった #11 は `expenses` がたまたま一致して素通りした。**誤警告は正しい警告
まで無効化する**ので、届かない検査は入れない。狙い（スコープ外の作業の検出）は `split-check` の
2件と「不可逆 N 件」が別の角度から材料を出している。

### SPEC テンプレートに「その検査が鳴らない場合」を書く欄

#9 の13周の多くは実装ではなく**検査側**の欠陥だった（テストが `sw.ts` を一度も実行していない／
警報が条件分岐で構造的に鳴らない／ミューテーション実行器が構文エラーを SURVIVED と誤読する）。
いずれも「テストは書いてある・green である」を満たしている。**書けないなら、その検査はまだ
何を見ているか分かっていない。**

### 一次ソースの確認

Spec Kit と Kiro の実テンプレートを取得して分割基準を確認した（docs/sources）。
**両者とも「タスクが大きすぎる」ことの検出機構を持たない** — Spec Kit の `analyze` の
Detection Passes に粒度の検査は無く、Kiro は人間の承認ゲートだけである。人間の diff レビューを
廃止した org ではその頼り先が無いので、警告を機械側に置く。

### ついでに直したバグ

`split-check` の関数内 `import re` がモジュールレベルの `re` を隠しており、`owns` が複数
territory のときだけ後半で `NameError` になっていた（今回の追加コードが露出させた）。

300 passed。

---

## 0.23.0

実地の報告5件。**1つ目は私が前に入れた変更が引き金だった。**

### 1. worktree に迷子の台帳ができていた（最優先）

```
begin が作る worktree に .orgforge/ が復元される
  → subagent が worktree 内で ledger を叩くと、そちらに書く（appended seq=1）
  → 実判定が本体の台帳から消える
```

実地で1日3回起き、実判定4件（#10 の survives、#11 の reject×2、#9 の admit）が迷子になった。

**原因は 0.21.0 で doctrine / evidence を git 追跡下に置いたこと。** その結果 worktree にも
`.orgforge/` が復元され、それが `ORG_MARKERS` に当たって親の探索が止まる。「学びは clone した
誰の環境でも効いてほしい」という判断自体は今も正しいと思うが、**探索の前提を壊すことに
気づいていなかった**。

警告で防ぐ設計は破れる（実際 gate が一度踏んだ）ので、構造で防ぐ: worktree の中からは必ず
親を辿る。判定は `git worktree` の実体（`.git` が**ファイル**で `gitdir:` が
`/worktrees/` を指す）で行う — パス名ではなくツリーの性質で見る。

この迷子は二次被害も生んだ。掃除しようとした `rm -rf .orgforge/wt/*/.orgforge` が、追跡下の
doctrine と evidence 19ファイルを巻き添えにした。**そもそも迷子ができなければ起きない。**

### 2. integrate が自分の log 検査に引っかかっていた

0.14.0 で入れた「マイルストーンでは `--command`/`--result` 必須」に integrate 自身が抵触し、
統合は完了するのに Issue へのログだけ落ちていた。**自分で統合テストを走らせて結果を持って
いるのだから、人に書かせる理由が無い。**

### 3. cap が開発そのものを止めていた

実測すると `destructive_ops` が **50/50 で満杯**だった。犯人は `git push` で、一律に破壊的と
して数えていた。その結果 maker が作業を終えたのに push できない。

- **通常の `git push` は対象外**。追記であって取り消せる（revert / 新しいコミット）。
  force 系（`--force`/`--force-with-lease`/`--delete`/`--mirror`）だけを数える
- 既定の cap を 50 → **150** に。重み3の操作（`rm -rf` / `DROP` / `reset --hard`）なら
  50回で到達するので、暴走の歯止めとしては十分に効く

cap が測るのは irreversibility であって活動量ではない。**開発そのものを止めるなら cap の誤用**
である。なお `git commit` と `sed -i` は 0.15.0 の時点で既に対象外だった。

### 4. 周回の性質を `show` に出す

#9 が9周、#11 が12周した。統制は毎回実害のある欠陥を見つけており機能しているが、**いつ収束
するかの見通しが立たない**。回数だけでなく直近3回が何を問題にしているか（実装の欠陥か、
テストの欠陥か）を出す。

```
周回:     9 周 — 直近3回: テストの欠陥 / 実装の欠陥 / 実装の欠陥
```

分類はキーワードによる粗い当て推量で、**判断材料であって判断ではない**。「切れ」とは言わない。

### 5. gate の「撃っていない領域」を skeptic に渡す

gate は毎回 `--risk` に今回撃っていない領域を書く。実地では #9 で gate が「1件も当てていない」
と書いた領域から実バグが出た。人が手で転記していたので配管が運ぶ。

正規表現で断片を切り出す実装を最初に書いたが、重複した断片が並んで読めなくなった。gate は
既に構造化して書いているので、**Known risk の節ごと渡す**形にした。

295 passed。

---

## 0.22.1

**0.22.0 のリファクタで `verify` が壊れていた。** 実地の報告: gate / skeptic の両方が
「agents/*.md が見つからない（探した先: None）」で使えない。

原因は `tools/` → `tools/orgcycle/` と階層が1つ深くなったこと。各所に散っていた
`os.path.dirname(os.path.abspath(__file__))` のうち **2箇所で直し漏れ**が出た:

- `_agents_dir` — 憲章を見失い、**verify が gate/skeptic とも死ぬ**（検証基準の唯一の出所）
- `_seam` — `handoff.py` を見失い、seam contract が生成できない

`show` の「実装:」行は 0.22.0 で直していたので再発しなかった。**直したのは踏んだ1箇所だけで、
同じ形の残りを洗っていなかった。**

### 基点を1箇所に集約した

`__file__` からのパス解決は各パッケージ **`HERE` のみ**。基点が散っていると、階層が変わる
たびに直し漏れが起きる。テストで1箇所であることを強制する。

### テストが緑のまま壊れていた理由

`test_verify_finds_charter_in_bundled_layout` は `CLAUDE_PLUGIN_ROOT` を設定してから呼んで
おり、**env が無い経路＝実際の使われ方を検査していなかった**。env の有無の両方を見る形に
直し、さらに「ヘルパ単体」ではなく **verify の出力に憲章と Boundary contract が入ること**を
見るテストを足した。実地の症状は「verify が使えない」であって「`_role_charter` が None を
返す」ではない。

壊れる場所で検証していないテストは無いのと同じ — #7 の split() で捕まえたのと同じ形を、
テスト側でやっていた。ミューテーション（0.22.0 の壊れた形に戻す）で2件が落ちることを確認済み。

291 passed。

---

## 0.22.0

**リファクタ。呼び出し方は変えず、中を分ける。** `org_cycle.py` が1440行・11サブコマンド、
`github_sync.py` が1176行・12サブコマンドまで肥大していた。実際、1440行のファイルを見ながら
`_new_public_surfaces`（0.20.0）の設計を2回外している — 全体が見えていなかった。

```
org_cycle.py    1440行 → 149行 + tools/orgcycle/{_core,cycle,judge,ship,inspect}.py
github_sync.py  1176行 → 197行 + tools/ghsync/{_core,backlog,record,branch,coverage}.py
tests/          1834行 → conftest.py + test_{ledger,orgcycle,status,organs}.py
```

`python3 tools/org_cycle.py begin ...` のまま。ドキュメントも実地の手順も無変更。

### 分割が2回、同じ穴を持ち込んだ

`HERE`（ツールのパス基点）。`tools/orgcycle/` に移した瞬間、`_gh_sync` が `github_sync.py` を
見失い、`_branch_for` が slug 無しのブランチ名を返して、**`show` の実装行と `integrate --plan` の
変更一覧が黙って空になった**。エラーは出ない — 組み立て系のツールは「見つからない」を静かに
素通りするため。実地で `show` を叩いていなければ気づいていない。

`github_sync` 側にも同じ形が2箇所あり、そちらは `record.py` が `ledger.py` を見失う。つまり
**0.21.0 で塞いだばかりの「判断が Issue にだけ残る」片側落ちが、分割によって再発する**ところ
だった。移す前に潰した。パスの基点は分割で最初に壊れる場所である。

`build.sh` が `tools/*.py` しか同期せず、サブパッケージがバンドルに入らない穴も同時に出た
（プラグインとして入れた瞬間に ImportError）。

### テストの検出力を実測した

`HERE` を壊れた形に戻すミューテーションで、`test_core_HERE_points_at_tools` と
`test_bundle_includes_subpackages` が落ちることを確認。テストがあることと、テストが壊れた実装を
検出できることは別。

288 passed。

---

## 0.21.0

**二重管理をやめる。** 実地の方針: 「外だしできるものは外だししたほうがいい。二重管理はまじで
やめたほうがいい。GitHub Issue に全てのログが残るほうが、ユーザーにとっても見やすいし、
SaaS みたいな考えで保守性も高い」。

### 判断の記録を2回打たせるのをやめた

`decide` が Issue に書き、人が `ledger append` を別に打つ設計だった。**実地で片側落ちが3回**:
#8 の refutation が台帳に0件 / #11 の1回目の reject が台帳に無い / `progress_recorded` が0件。
actor は `--by` で既に渡っているので、分ける理由が無かった。

順序は **台帳が先、Issue が後**。統制（自己承認拒否・順序違反）は台帳が持っているので、Issue に
書いてから拒否されると「Issue には admit と書いてあるが台帳には無い」という食い違いが**外に**
残る。拒否されるなら、外から見える記録を作る前に止める（exit 4）。

### 冪等キーが統制の裏口だった（この検証で発見）

`(class, natural_key)` だけを見ていたため、**キーさえ一致すれば actor が違っても no-op** になり、
`DISTINCT_ACTOR` も `REQUIRES_PRIOR` も評価すらされなかった。gate の判定と同じキー
`admission_decided-11` を maker が使うと、自己承認が exit 0 で通る。

- 冪等 no-op は「同じ actor の再実行」に限る。別 actor が同じキーを使ったら拒否
- `decide` のキーを `{event}-{issue}-{digest}` に。`{event}-{issue}` だと**2周目の判定が
  1周目と衝突して no-op** になり、同じ穴を踏む

冪等性は再実行を守る仕組みであって、統制を迂回する経路ではない。

### 検証中の事故

プローブ掃除の一括削除で、#11 の gate 判定3件を誤って消した。台帳に理由と digest が残っていた
ので Issue に復元した。「台帳は派生」という方針とは逆向きに台帳が救いになった形で、二重に
持つこと自体の価値も同時に示している。**外出しの方向は変えないが、台帳は「統制と復旧のための
派生」として維持する。**

---

## 0.20.0

**実地の指摘: 「verify が rework の履歴を渡さない」。** 264行のプロンプトに「この Issue は既に
2回 reject されている」が入っておらず、gate は毎回**初回判定として扱っていた**。3周目の #7 で
「前回見落とした点を今回どう確認したか」を明示させたら質が上がった、という観察がある。

`show` が既に判定履歴を持っていたので、`verify` がそれを埋め込む。回数は**台帳と Issue の
多い方**を採る — 台帳だけだと「2回目」と言ってしまい（1回目が台帳に無い）、過少に伝えると
gate が「ほぼ初回」として扱う。

### `integrate --plan` — 衝突の予告

#7 の統合後に10件失敗し、切り分けに時間を使った（8件が worktree 走査の偽陽性）。何を統合するか・
**並行 worktree が同じファイルを触っていないか**を先に見せる。

### `asset_touched` — 本番資産への変更を残す口

`exposure_budget_checked` はローカルのファイル操作しか数えない。実際に危険なのは本番 DB への
DDL や権限変更で、実地ではマイグレーション2本と `revoke` が入ったのに台帳に何も残らず、
**「あの revoke は誰の権限で入ったのか」が辿れなかった**。`--authority` がその欄。

### `public_surface_declared` — 何を外に晒したか

`domain_model` は「領域規則を決めたか」を問うが「何を外に晒したか」は誰も見ていなかった。
**認可ホールは「関数を1つ足した」ところから生まれる**（実地の `join_group`）。complete が
新しい公開面を検出したら、申告するまで止まる。

検出の設計で2回外した: テストヘルパを拾いすぎて肝心の1件が10件に埋もれ、SECURITY DEFINER を
ファイル単位で見ていたため定義が後ろの関数が29位に沈んだ。**拾いすぎは、見落としと同じくらい
悪い。**

---

## 0.19.0

実務で「無くて困った」ものを実装した。

### `org_cycle show --issue N`

`gh issue view` と台帳の grep と `status.py` を別々に叩く必要があった。#7 が3周したとき
「どの周のどの判定を見ているのか」が分からなくなる。実装コミット・worktree・判定履歴
（訂正済み / backfill の印つき）・いま何待ちか・次の一手を一望する。

### `correction` を第一級イベントに

台帳は追記型なので過去を消せない。自由記述の注記では**機械が読めず**、実地では検証プローブ
4件が実判定として集計され、board が現実と食い違った。`kind: probe|mistake` は集計から除外し、
`backfill`（後から書いた実判定）と `superseded`（時系列の解決が扱う）は除外しない。

### board に判定理由を出す

件数だけでは CEO に何も伝わらない。理由は台帳に無く Issue コメント側にある（設計どおり）ので、
board が Issue から引く。

### `begin` / `plan` の着手前チェック

依存が rework 中か、人間の作業待ちが残っていないか。**止めない — 見せる**。判断は人の仕事だが、
材料が無ければ判断のしようがない。

### seam contract の参照渡し

0.12.1 で「ガードが本文を見るのは正しい」と書いたが、**保証できないのはガードが読まなければの
話**だった。読めば保証できる。264行を毎回貼る必要が無くなり maker の context が空く。読む範囲は
org のルート配下と一時ディレクトリ、512KB まで。

---

## 0.18.0

**判定は最新が有効。** `status.py` が集合で持っていたため、reject が後から来ても admit が
消えなかった。実地の #11 で `admit(216) → reject(218)` の順に記録されたのに board が RED を
出し続けた。追記型の台帳では「一度でも admit があった」と「いま admit されている」は別物。

reject されたまま放置されているものも board に出す（RED ではなく AMBER — 差し戻しは正常な
過程だが、rework が止まっていることには気づける必要がある）。

`verify` の雛形にあった未定義の `$P` を絶対パスにした。**貼っても動かない雛形は打たれないか、
打ち間違えられる** — 台帳側の記録が落ちた一因。

---

## 0.17.0

**0.16.0 の修正が実地では効いていなかった。** `deliverable` で書いた自己 admit が通っていた
（seq 208）:

```
cycle_started(seq 74) : candidate_id="cand-0677...", pack_manifest_id="issue-7"
admission_decided     : deliverable="7", issue=7
                        → 共有する識別子が1つも無く、_same_work が相関できない
```

**テストが実地の形を再現していなかった** — `cycle_started` に `issue` を入れて書いていたので
直接の共有 ID があり、穴が見えなかった。テストが本番と違う形を作れば「壊れる場所で検証して
いない」ことになる。#7 で学んだのと同じ失敗を、テスト側でやっていた。

直し方: 人に同じキーを書かせず、**台帳にある対応関係を辿る**。`pack_manifest_id: "issue-7"` /
`contract_ref` が橋になるので、union-find で推移的に解決する。どう繋がったかを出す —
「同じ仕事だ」と言われた側が納得も反論もできないメッセージは、拒否の理由になっていない。

未検証だった統制（skeptic の自己反証拒否・`report_up`/`conformance_reviewed` の順序・
alignment/resource/reconcile）を実測し、テストに固定した。**使っていない機能は壊れていても
分からない。**

---

## 0.16.0

**無言の素通しをやめる。** 実装済みの統制が、payload のキーが揃わないと黙って無効になっていた。

```python
if key is None:
    return None    # nothing to correlate on; the payload-shape check is elsewhere
```

この "elsewhere" は存在しなかった。実地の台帳で maker が自分の #7 を admit でき（seq 204）、
存在しない deliverable 999 を deploy できた（seq 205）。

- 識別子を束ねて相関する（`candidate_id` / `claim_id` / `deliverable` / `issue`）
- **相関キーが1つも無い判定は拒否する。** 相関できない判定は「検証を通った判定」ではない
- `result_deployed` が `claim_id == candidate_id` だけを見ていたため、実地の refutation 2件と
  相関できず `null == null` が一致し、**deploy ゲートが丸ごと無効**だった

### 検出器が「学習が使われている」と嘘をついていた

`learning.py repeats` が `payload.cause` しか読まず、`rework_requested` は対象ですらなかった。
**同じ失敗を3回した org に対して clean と報告していた。** `reason` / `why` も読み、死因が1件も
読めないときは `clean` ではなく `unknown` と言う — 「繰り返していない」と「見えていない」は
別で、混同すると誤った安心になる。嘘をつく検出器は無いより悪い。

一致は文字列で見るという限界も明示する。実地の2件は「端数の偏り」「テスト硬化」と別の言葉で
書かれていたが根は同じだった。

---

## 0.15.0

### `log` が台帳に何も書いていなかった

Issue に7回の作業記録がある一方、`progress_recorded` は **0件**。`work_in_progress` ビューが
空になるため `/org-resume` が中断から復帰できない状態だった。

### 学びの蓄積口がサイクルに繋がっていなかった

`doctrine/` も `conventions/` も空。真因は道具の不整合で、`propose` は `retrieved_at` /
`review_by` を省略できるのに `admit` はそれを必須にする — **素直に使うと admit で必ず詰まる**。
`complete --learned` が provenance を埋めて propose し、admit は gate の仕事。
tatekae の実知見5件を投入して、skeptic の brain に3件・persistence_schema に1件が実際に届くことを
確認した。

### 予算 cap が日常の後片付けだけを止めていた

1日5回発火して5件とも実害ゼロ（worktree / node_modules / scratchpad）。**cap が測るのは
irreversibility であって活動量ではない**ので、再生成できる対象は重み 0 にした。`src/` も `/` も
親への遡上も重いまま。

`gc`（worktree の片付け）、`record`（済んだ判定の backfill）、`begin` が `attention_allocated` を
打つ、も同時に入れた。

---

## 0.14.0

**実測が示したのは「検査のある場所だけが厚くなる」という一つの形。** 同じ Issue の中で
`decide` 経由の判定は 3,506〜5,894字、検査の無い `log` は 276〜473字だった。

- マイルストーンの `log` は `--command` / `--result` を必須にし、「通った」の言い換えを拒否する。
  途中の刻み（`progress_recorded`）は検査しない — 軽く刻めることも同じくらい大事
- **PR を作る手段が無かった。** `/org-work` §4 は「feature ブランチ → PR → develop」と書いて
  いたのに、実地では PR ゼロ件・`git merge` で直接統合・統合済み Issue が OPEN のまま。
  `handback` が push → PR（body に `Closes #N`）→ Issue へ log
- `begin` の log に branch / worktree / parent / candidate_id を自動で入れる。人が書いた276字には
  ブランチ名も worktree のパスも無かったが、**org_cycle は両方知っていた**

---

## 0.13.0

**統合直前の穴。** 台帳を数えたら `refutation_attempted` が **0件**。Issue にはコメントがあった
ので、二重記録の片側だけが落ちていた。`requires_prior` は `result_deployed` にしか掛かっておらず、
統合はその手前なので何も止めなかった。

- `_refutation_for()` を admission と同じ強度で実装
- `org_cycle integrate` — 前提照合 → マージ → 統合後テスト → `integration_admitted` → Issue へ log。
  前提が欠けたら exit 4 で止め、マージ手順に入らない
- `status.py` が「admit 済みだが skeptic の記録が無い」を **RED** で出す。tatekae で #8 が実際に
  RED として表面化した
- **`repro_lint` が一度も走っていなかった** — パス解決ができず gate が `--risk` に「未実行」と
  書いていた。誰も diff を読まない前提で機械的拒否層が丸ごと効いていない状態。`verify` が
  絶対パスを埋める
- `--risk` が書き得になっていたので、台帳に `risk_accepted` を運ばせ board に出す。skeptic には
  gate が書いた Known risk を抜き出して「まずここを潰せ」と渡す
- `--domain-model-none` のとき、増えた公開型/エクスポートを列挙して問い返す（判定はしない）
- `complete` が worktree を片付ける（未コミットなら残して警告）

---

## 0.12.1

- `complete` の「gate の admission がまだ」が**嘘だった** — 362行目は台帳を一切見ておらず、
  `rc==0` なら常に同じ文言を出していた。実際に照合するようにし、`deliverable` と
  `payload.issue` の両方で引く。見つからない時は「近い記録: seq N に admission_decided が
  あるが deliverable=... で一致しない」と示す
- seam contract をファイルで渡すと spawn が HELD される件は、ガードではなく `verify` の案内側を
  直した（0.19.0 でガード側を直し、参照渡しを許すようにした）

---

## 0.12.0

### 案5: worktree 分離の強制（切迫していた方）

実地の報告: 「並列 fan out で #7 のコミットが `feat/issue-8-settle` に載る事故が起きました。
同一ツリーで並列 maker を走らせる限り再発します。**『毎回正しく判断する』前提の設計は破れる**、
という実例になりました」。

`git checkout` はツリー全体を切り替えるので、注意深さの問題ではなく構造の問題として再発する。
`begin` が `.orgforge/wt/issue-<N>/` を自動で用意する。**判断ではなく物理で分ける** —
forced invariant であって forced delegation ではない。

### 案2: `verify` — 配管だけを引き受け、判定は委ねる

実地の報告: 「検証手順をプロンプトに書き下ろす作業が一番重い。毎回書き直しで、私の書き方で
gate の厳しさが変わる。18 Issue なら18回書き、そのたびに基準がブレます」。

`org_cycle verify --issue N --role gate|skeptic` が組み立てるのは**材料だけ**:
handoff の seam contract・**`agents/<role>.md` の憲章（＝検証チェックリスト）**・Issue の
SPEC/MUST・`decide` の雛形。skeptic には gate が既に見たことを引き渡す（渡さないと同じ
ミューテーションを繰り返す）。

**verdict / why / risk / どのミューテーションを試すかは持たない。ツールが verdict を決めた
瞬間に gate は形骸化する。** テストで固定した。

### ついでに直した実バグ

- `handoff.py` は root 省略時の discovery が**未実装**で TypeError で落ちていた。ヘルパは
  「省略時は自動発見」と謳っていたので、6引数の手打ちは仕様ではなく、ただ壊れていた
- `_agents_dir` がバンドル配置（`agents/` が `tools/` の兄弟）で憲章を見失っていた

---

## 0.11.0

**配管を自動化する（docs/11 §0d）。** 実地の指摘: 「なんか手で作業しているように見える」。
そのとおりだった — `/org-work` は「こういうイベントを打て」という散文の指示で、実行するのは
エージェントだった。**Issue 2件あたり11コマンド**、18 Issue なら約90回の手打ちで、1回の
取り違えで台帳の整合が崩れる。

とりわけ `parent` が問題だった。0.10.1 でフェーズ連鎖の親継承を実装したのに、**その値を人が
Issue から目で拾って手打ち**していた。値が手打ちである限り取り違えが起き、継承の実装が活きない。

### `tools/org_cycle.py`（新規）

```
org_cycle.py begin    --role R --issue N [--agent A]
  → claim / spec_delegated / phase_started / cycle_started / Issue へ log / stage を
    正しい順序と actor で一括実行。parent と candidate_id は Issue から自動解決
org_cycle.py complete --role R --issue N --outputs T (--domain-model-updated|--domain-model-none)
org_cycle.py plan     --role R --issue N     # 何も実行せずイベント列を印字
```

三つの性質:

1. **自動解決** — `parent` は Issue の `Parent: #N`（`create` が書く）と sub-issue API から。
   `candidate_id` は Issue のトレーラから。**人が値を運ばない**
2. **止まったら止まったまま** — 途中失敗ならそこから先は打たない。部分適用を「成功」と
   報告するのが最悪（台帳が壊れた状態を正常に見せる）
3. **再実行が安全** — 各イベントは natural-key で冪等。「止まったら直して再実行」が成立する

### 線引き: 配管は自動化する、判断は自動化しない

自動化したのは**順序と actor が決まっている配管**だけ。**何を選ぶか・誰に委ねるか・分割するか・
admit するかは自動化していない** — docs/03 §6.5 の「forced delegation は設計エラー、
forced invariant は正しい」をそのまま踏襲する。

### ドキュメント

ARCHITECTURE のツール表が14件のままで、実際の20件と乖離していた（`github_sync` `status`
`discover` `req_lint` `org_cycle` が未掲載）。README/REFERENCE にも `org_cycle` と
`needs-human` を追加。

テスト 218 → 221件。
## 0.10.1

**タテカエ org の申し送り（改訂版）に全件対応。** A-1 は `/org-work` が起動せず、しかも
**lint が GREEN を出す**という組み合わせで、報告のとおり最も重い。

### A-1【重大】views の実装がスキーマの半分しかなかった

`ledger.py` が13件をハードコードしていた一方、`ledger-schema.yaml` は26件を宣言していた。実害:

- `/org-work` が `parts_inventory` を引けず、**コマンド全体が起動しなかった**
- **gate の context_pack 3件と skeptic の 2件がすべて未実装**だった。`organization.yaml` が
  「gate はこの3つを見て admit する」と宣言していても実行時に1つも引けない。SoD（maker≠checker）は
  中核主張なのに、**checker が判断材料を取得できなかった**
- それでも `org_lint` は pass した。CP 検査は「スキーマに定義があるか」しか見ず、
  **「ツールが実装しているか」を見ていなかった**

対処は報告の提案1のとおり: **`VIEW_FROM` を廃し、`ledger-schema.yaml` の `views:` を読む。**
view を足すのに Python を触る必要がなくなり、**乖離が構造的に起きなくなった**。あわせて
`org_lint` に **VW 検査**（スキーマの全ビューをツールが引けるか）を足した — 提案2の
「lint が実装との乖離を検出できないのが本質的な穴」への対処で、安全網として残す。

### B-2 フェーズ連鎖が objective と task で分断されていた

founding は objective 単位で requirements/design を admit するが、`/org-work` は task Issue 番号を
`deliverable` にする。別の文字列なので連鎖せず、指示どおり進めても task が弾かれた。

task ごとに再 admit させるのは同じ設計を N 回 admit するセレモニーにしかならない。**設計は
objective の単位で起きた**のだから、`phase_started` の payload に `parent` を書けば
**親の admit を継承する**ようにした。親を持たない deliverable は従来どおり自分の admit だけを見る。

### B-4 CEO 承認を台帳に記録する手順を追加

「承認後に objective Issue を作れ」と指示しながら、承認そのものを記録する手段がなかった。
founding は charter-tier（docs/05 §1）なのに、承認された事実がどこにも残らない。
`proposal_adjudicated{proposal_id: founding, decision: approve, human}` を打つ手順を
`/org-found` に追加した（既存スキーマのまま）。

### あわせて: コマンドの env 依存を全廃

`${ORG_LEDGER_ROOT}` を渡していた箇所（10コマンド・24箇所）を discovery に置き換えた。0.9.0 で
ツール側は対応済みだったが、コマンド側が env を渡し続けていたので、設定が無い環境で壊れていた。

そのうち2箇所は **`${ORG_CONVENTIONS_ROOT:-$ORG_LEDGER_ROOT}` というフォールバック**で、
conventions を ledger ディレクトリに書き込む混入バグでもあった（監査記録に別種のデータが混ざる）。
`conventions.py` / `doctrine.py` を discovery 対応にして、フォールバック自体を消した。

### A-2 / A-3 / A-4 / B-1 / B-3

0.10.0 で対応済み（`split-check` の `#N` 限定、SKELETON の必須キー追加、`on_candidate_arrival` の
実例、`needs-human`、O2 メッセージ）。A-4 の cadence 表記は SKELETON のコメントで示している。

テスト 213 → 218件。
## 0.10.0

**人間にしか実行できない作業を Issue にする（docs/11 §0c）。** タテカエ org の founding〜decompose
を通しで走らせたセッションからの申し送りに基づく。

### 問題: org は自分が作れるものだけを Issue にしていた

実地の founding で3件が**セッションの散文にしか存在しなかった** — Supabase プロジェクト作成、
Google OAuth クライアント登録、GitHub のブランチ保護設定。いずれも org のツールでは完結しない
作業で、Issue にも台帳にも残らなかった。結果:

- セッションが切れれば消える（`/org-resume` は ledger を読むので復元されない）
- `/org` が「66/66 被覆・GREEN」と出すのに、実際は人間待ちで着手できない
- `ready` が人間待ちを依存として表現できず、ブロック済みの task を maker に渡す
- `coverage-check` は「Issue になったか」しか見ないので前提が欠けても通る

`orgforge:needs-human` ラベルは `/org-init` が作っていたのに、**それを立てる手順がどのコマンドにも
無く、使用実績は 0 件**だった。仕組みだけあって使う道がなかった。

とりわけブランチ保護は **§4e の機械的拒否層の一部**でありながら GitHub の管理設定なので
コードでは実現できない。散文に消えると「機械が守るはず」の層に穴が開いたまま誰も気づかない。

### 対処

- **`github_sync needs-human`**（新規）— 人間タスクを Issue にする専用の口。`--blocks` で
  下流を縛れ、`Depends on: #N` を書けば `ready` がブロック済み task を返さなくなる
- **`/org-found` と `/org-decompose` に抽出手順を追加** — 抽出源は既存の
  `REQUIREMENTS.md` の Open Questions / Assumptions（29148 の標準節。§0b でこれを必須にしたのは
  ここに効かせるためでもある）。判定は「org のツールで完結するか」
- **`/org` の board が needs-human を RED として最上位に出す** — 「あなたを待っている」ものこそ
  board の意味であり、それが見えないなら board は嘘をついている。GitHub が見られない環境では
  黙って飛ばす（board 自体は落とさない）

### 同じ申し送りにあった細かい修正

- **`split-check` が散文中の数字を依存と誤検出していた** — 「実装コードは1行も入らない」の「1」が
  `#1` として解釈された。`#N` の形だけを依存とみなすよう修正
- **`organization.SKELETON.yaml` が lint 必須項目を含んでいなかった** — そのまま埋めると初回
  lint で 31 violations が出た。`gaming_defenses` / SoD の `authorization`・`recording` /
  `structure.span` / layer の `departments:` キー / gate・skeptic の `loop` を、コメント付きの
  空欄として追加。特に `departments:`（`roles:` ではない）は例が無いと必ず間違える
- **`org_lint` O2 のメッセージが中間管理職の追加を勧めていた** — span 超過時の選択肢に
  「span を宣言し直す」を先に並べた。契約を持たない coordinator を足すのは docs/03 §6.5 と緊張する

## 0.9.4

**`!` ブロックは「エージェントが作業する前」に一斉展開される — 書いた後に走る検査を `!` に
置いてはならない。** 設計上の欠陥で、3コマンドが該当した。

`/org-found REQUIREMENTS.md` が次で落ちた:

```
req_lint: REQUIREMENTS.md がない。/org-found が REQUIREMENTS.md を書いたか確認すること
```

ファイルは実在していた。`!` ブロックはコマンドが**展開される時点**で実行されるので、
「REQUIREMENTS.md を書く → 検査する」という順序が原理的に成立しない。検査は必ず
「まだ書かれていないファイル」に対して走る。

該当箇所（すべて「書いた後に走るべき検査」）:

- `/org-found` の `req_lint`（REQUIREMENTS.md を書いた後）
- `/org-found` の `org_lint`（organization.yaml を書いた後）
- `/org-adopt` の `org_lint`（同上）
- `/org-decompose` の `coverage-check`（task Issue を作った後 — `!` だと Issue 0件の
  時点で走り、必ず全件 GAP になる）

いずれも `!` を外し、**エージェント自身が Bash で実行する**手順に変えた（コードブロックで
提示し、なぜ `!` にできないかも書き添えた）。

あわせて `/org-decompose` の `nearby_deaths` が `${ORG_LEDGER_ROOT}` に依存していたのを
discovery に変更（0.9.0 でツール側は対応済みだったが、コマンド側が env を渡していた）。

**判定基準:** `!` に置いてよいのは**前提の確認**（場所・発見結果・既存ファイルの状態）だけ。
そのコマンドの作業結果に依存する検査は、エージェントが順に実行する。

## 0.9.3

**zsh が変数を単語分割しないため、0.9.2 の修正が別の形で壊れていた。**

0.9.2 でシェル関数を消した際、引数を文字列に組み立てて渡す形にした:

```sh
A=organization.yaml; for f in …; do A="$A $f"; done
python3 org_lint.py $A          # ← zsh では引数1個として渡る
```

`sh`/`bash` は `$A` を空白で分割するが、**zsh は分割しない**（SH_WORD_SPLIT が既定 off）。
Claude Code のシェルは zsh なので、5ファイル分の文字列が**1引数**として渡り、
`org_lint` が「引数が足りない」と判断して usage を出して exit 2 になった。

位置パラメータ（`set -- "$@" "$f"`）に置き換えた。これは sh/bash/zsh のいずれでも
正しく複数引数として渡る。

**`!` ブロックのシェルは zsh である。** 変数に組み立てた引数リストを裸で渡してはならない。

## 0.9.2

**`/org-found` が引数を2つ以上受け取ると lint が壊れるバグを修正。**

`!` ブロック内でシェル関数を定義し、その中で `$1` を使っていた:

```
pick() { [ -f "$1" ] && echo "$1" || echo "${CLAUDE_PLUGIN_ROOT}/template/$1"; }
```

**関数内の `$1` は、関数の引数ではなくコマンドの第1引数に先に展開される。**
`/org-found REQUIREMENTS.md DECISIONS.md` と呼ぶと `pick constitution.yaml` が
`DECISIONS.md` を返し、4ファイルすべてが同じ誤ったパスを指した:

```
[SC] constitution.yaml file not found: .../template/DECISIONS.md
[SC] moves.yaml file not found:        .../template/DECISIONS.md
[SC] ledger-schema.yaml file not found: .../template/DECISIONS.md
[SC] sensors.yaml file not found:      .../template/DECISIONS.md
```

シェル関数を使わない形（`for` ループで組み立てる）に置き換えた。他のコマンドに同じ
パターンが無いことも確認済み。**`!` ブロックの中でシェル関数を定義しないこと** —
コマンド引数と衝突する。

## 0.9.1

**ドキュメントを 0.9.0 の実態に合わせ、`/org-init` の誤爆を機械的に止める。** 機能追加はない
patch リリースだが、**バージョンを上げないと `/plugin update` がキャッシュを更新しない** —
同じ version 番号のままドキュメントやコマンドを直しても、利用者には届かない（実地で判明）。

### 直したドキュメントの齟齬（実地で判明した4点）

- **コマンド名が未修飾だった** — 正しくは `/orgforge-plugin:org-init`。README / QUICKSTART /
  REFERENCE / ARCHITECTURE の24箇所を修正。他のプラグインと名前が衝突しないための正式な形
- **インストール手順が directory 参照のままだった** — ローカルディレクトリ参照はそのマシンで
  しか動かず、**未コミットの変更がそのまま動く**（検証していないコードで org を動かすことになる）。
  GitHub 参照に書き換え、push が必須になる開発フローも明記
- **「`ORG_LEDGER_ROOT` は必須」が 0.9.0 で嘘になっていた** — 発見が既定なので通常は不要。
  REFERENCE の env var 節を「すべて上書き」に書き直し、優先順位（明示的な引数 > 環境変数 >
  発見）と、なぜ発見が既定かを明記。QUICKSTART §2 も「セットアップは不要」に全面改稿
- README に `org-adopt` が無かった

### `/org-init` の誤爆ガードを機械判定に

ステップ0が「場所を表示する」だけで判断を人任せにしていたため、**プラグイン自身の開発ツリーを
org 化する事故を2回起こした**（`.orgforge/` + テンプレ7点 + `develop` ブランチ + GitHub ラベル
9件。いずれも復旧済み）。`.claude-plugin/marketplace.json` か `integrations/claude-code/commands`
の存在で機械的に判定し、**⛔ STOP を出して以降のステップを止める**ようにした。
「これは表示ではなく指示である」ことも明記 — 表示は読み飛ばされる。

## 0.9.0

**An org is a place on disk, not a shell environment — and the founding→backlog path is now a complete,
gated chain.** Two themes: the flow from an RFP to workable Issues got its missing steps and its
coverage gate, and human diff review was retired in exchange for a mandatory, tamper-evident record.
Alongside them, the setup that used to be a page of `export`s is gone entirely.

### Zero-setup discovery — `.envrc` is no longer part of the flow
`ORG_LEDGER_ROOT` / `ORG_GITHUB_REPO` used to be the only way the organs and the guardrail hook knew
where the org was. That had three costs, and the third is the serious one:

- **Not portable.** A state root written as `/Users/someone/proj/.orgforge/ledger` is wrong on the next
  machine — while the whole point of putting the full spec in the Issue is that *any* environment can
  pick up the work.
- **One org per shell.** A single exported variable cannot serve two checkouts, so running orgforge in
  several repositories from one environment either cross-contaminated the audit record and the
  blast-radius budget, or required direnv.
- **Silent permissiveness.** A session that had not sourced `.envrc` found no ledger — and the
  guardrail with no ledger **allows everything**. The failure mode of a forgotten setup step was an
  ungated session, which is the one failure mode a guardrail must not have.

New `tools/discover.py` resolves the org from the working directory: `.orgforge/` beside
`organization.yaml` (walking up, so subdirectories work), and the backlog repo parsed from
`git remote origin` (locally — no `gh`, no network). Precedence is **explicit argument > environment
variable > discovery**, so every existing override still wins. `_organ.resolve_root()` funnels it
through the one read path all organs share; `root` became optional on 43 tool commands and `--repo`
on 9; both hooks discover instead of requiring env. `/org-init` no longer writes `.envrc` — it
*verifies discovery works* instead. Multi-repo operation from one shell is now the default rather
than a configuration.

### Everything below shipped in this release


**The founding→backlog path is now a complete, gated chain.** Previously `/org-found` designed the
org and stopped, and the only way to get task Issues was `/org-discover`, whose input is a role's
*aspiration gaps* — so nothing turned the RFP's must-haves into workable units, and setting up a new
org was a page of manual `export`s. Two new commands close both ends, and a new gate proves the middle.

### New: `/org-init` — the setup step
Creates the ledger/doctrine/conventions roots, installs the org spec files, writes `.envrc` (including
a detected `ORG_GITHUB_REPO`), ensures the backlog label vocabulary and the `develop` branch, then
lints the spec and runs the harness probe so a session can't believe it is guarded when it isn't.
Idempotent — safe to re-run to repair a half-set-up org. Designs nothing.

### New: `/org-decompose` — RFP/全体設計書 → atomic SPEC task Issues
The missing bridge between design and execution. Reads the approved `coverage-manifest.md` +
`ARCHITECTURE.md`, carves each must-have into *independently-completable* units (split where sibling
`owns` sets are disjoint; keep reciprocally-coupled work together), fills the full `template/SPEC.md`
structure into each Issue body, and hangs each under its objective as a native GitHub sub-issue.
Because the whole spec lives in the Issue — clone URL, literal setup/test commands, entry files, MUSTs
in EARS, seam contract, DoD command — a task can be claimed and started from **any** environment.
Uses the same deterministic `candidate_id` derivation as `/org-discover`, so re-running fills gaps
rather than duplicating the backlog. RFP-derived tasks are `source: mandate`; self-raised ones stay
with `/org-discover`.

### New tooth: `github_sync coverage-check` — the decomposition coverage gate
`/org-found`'s O10 lint proves each must-have has exactly one owning *contract* (design layer). This
proves each one reached at least one *task Issue* (backlog layer), matching the manifest's
`rfp_capability` against a `coverage_row:` trailer in each Issue body. A must-have that was designed
but never decomposed is silently unbuilt — the hardest gap to see — so it now exits 10 instead of
passing unnoticed. A paraphrased trailer is reported as an orphan (it would otherwise mask a real
gap); Issues with no trailer are a note, not a failure, since `/org-discover` items legitimately have
none. Eight tests cover the gate, including the closed-Issue and unparsable-manifest cases.

### Rule: the founding artifacts have FIXED filenames (docs/11 §0a)
`/org-found` now writes exactly `RFP.md`, `FEATURE-INVENTORY.md`, **`ARCHITECTURE.md` (the 全体設計書)**,
`coverage-manifest.md`, and `organization.yaml` — under those exact names, as a rule rather than a
convention. Downstream commands address them **by name**; a renamed artifact is an unfindable one, and
variant names break Level-1 reproducibility at its root. `ARCHITECTURE.md` is explicitly **not** an SDD
artifact: SDD's spec/plan/tasks live in the Issue hierarchy (§4b) and are per-objective/per-task, while
the 全体設計書 sits above them as the standing whole-system design — which is why it is a file while task
specs are not (a single whole-system design doesn't fragment; per-task spec files rot, docs/12 §6).

### New bar: unread-safe (docs/11 §4e) — the diff nobody reads must still be safe to merge
§4a asks *"can a stranger run this?"*; §4e asks *"is this safe to merge without anyone reading it?"* At
parallel-agent throughput no one reads every diff — not the CEO, not a reviewing agent, not the maker —
and a reviewer who cannot keep up does not announce it, they skim. So the defect classes only a careful
reader catches are made **unmergeable by machine** instead. `repro_lint` gained four teeth, checking
that the rejection layer is *configured* (running it is CI's job):

- **complexity-bounded** (implement) — a ceiling on function size / cyclomatic / cognitive complexity /
  nesting. The highest-value tooth: over-long nested functions are where unread defects hide, and
  appending to a working function is what an agent does when the alternative is decomposing.
- **type-escapes-closed** (implement) — strict typing on, `any` / `@ts-ignore` / non-null assertions
  banned. Open escape hatches make a type checker advisory; an agent pushed to turn a build green
  reaches for them, and the hole is invisible in an unread diff.
- **tests-present** (test) — tests are what *substitutes* for a reader; a green CI with no tests proves
  only that the code compiles.
- **dup-dead-code** (deploy) — jscpd/knip/ts-prune/vulture. Parallel makers re-solve each other's
  problems and orphan superseded code; neither shows up in any single diff. Report-only by default.

Language-appropriate (rubocop's `Metrics/MethodLength` satisfies the complexity bar; a repo with no
static type layer marks the type check `n/a`). The doctrine records the two operating rules the bar
depends on — **drain then ratchet** (a rule that is on and violated everywhere enforces nothing) and
**exceptions in the config with a reason**, never inline `eslint-disable` — and states plainly that this
does *not* replace the gate/skeptic: the mechanical layer clears everything a machine can decide so the
scarce different-lineage judgment is spent where it is irreplaceable.

### Human diff review is RETIRED — the Issue becomes the audit record (docs/11 §4f)
§4e removed the human from *reading* the diff; §4f takes the consequence to its end: **there is no human
review step.** No person reads the change before it merges. The mechanical bar, the gate, and the
skeptic are the entire judgment layer. That is defensible at fan-out scale — a reviewer who cannot keep
up does not announce it, they skim, and a skimmed review launders unread code as reviewed — but it
removes the **account** of why a change was allowed. So the trade is explicit: **review is retired;
recording is not optional.**

- **`github_sync decide`** (new) — records a judgment **with its reasoning** on the task Issue.
  Judgments now double-write, the way settled conventions already do: the ledger takes the
  tamper-evident receipt, the Issue takes the account — `--why` (what was weighed), `--evidence`
  (commands run and their real output, CI runs, `repro_lint` verdicts), `--alternatives` rejected,
  `--standard` applied, and `--risk` knowingly accepted. It **refuses a `--why` that merely restates
  the verdict** and refuses non-judgment event classes, so the slide back into a rubber stamp is closed
  at the tool. Every posted decision carries an explicit "no human reviewed this change" notice.
- **`github_sync log` enriched** — `--command` (verbatim, re-runnable), `--result` (**the real output,
  failures included**), `--files`, `--next-step`, `--blocked-by`. A log of only successes is a fiction,
  and the failed attempt is usually the most informative entry on the Issue. Backwards compatible: all
  new fields are optional.
- **The gate and skeptic now post their reasoning**, not just ledger verdicts. The skeptic must write
  *who this fails for and under what conditions* **even when the work survives** — a bare `survives` is
  worthless to whoever audits the merge later. The gate must record `--risk` honestly: admitting despite
  a known hole is a legitimate decision only if it is written down.
- **The logging bar in `/org-work` and `template/SPEC.md`**: log at every step that changed the world or
  changed the plan, including course changes with their cause (feeding `nearby_deaths`). The stated bar
  — *a stranger reading only the Issue can reconstruct what was built, what was tried and abandoned,
  what was run, what came back, and why it merged, without the ledger or the transcript.*
- **What this does not license** (stated in §4f so it cannot drift): the *judgment* layer stays — O6c's
  distinct-lineage rule matters **more** without a human backstop, since a puppet checker is now the
  only checker. Phases are still non-skippable. And the CEO's charter-tier decisions (founding,
  irreversible moves, scope) remain human — what is retired is diff review, not governance.

### Other
- `role-settings.yaml` is now bundled into the plugin template dir (`/org-init` scaffolds it).
- `template/SPEC.md` documents the `candidate_id:` / `coverage_row:` trailers, and now carries the §4e
  bar in its Verification section so makers configure it rather than discovering it at the gate.
- **`github_sync candidate-id`** — the deterministic id derivation moved out of each command's prose
  into the organ. The echoed one-liner it replaces lost its `\x1f` field separator to shell escaping,
  so different items collided onto one id and the second one's ledger append was silently swallowed as
  a "replay" — it never entered the backlog. Both `/org-decompose` and `/org-discover` now call the tool.
- `create`'s idempotency search now covers **closed** Issues: a delivered task is closed, so an
  open-only search re-minted every completed task on the documented re-run/repair path.
- `/org-init` no longer truncates `.envrc` (a repair run was wiping `ORG_GITHUB_REPO`, silently
  demoting a GitHub-backed org to ledger-only) and no longer reports "installed" for files it kept.
- `/org-found`'s lint now reads the **org's own** spec files, falling back to plugin templates only for
  what the org hasn't installed — it was validating pristine templates while the org ran on edited
  copies, so a `SET_ME` left in the real `constitution.yaml` could never be caught.
- `coverage-check` hardening: a table *following* the manifest no longer inherits its header (an
  EXCLUDE list was being read as must-haves, which would have made the org build the scope the CEO
  cut); bold/backticked trailers now match; and an `orgforge:mandate` task with no trailer now fails
  instead of passing as a note.

## 0.8.0

**orgforge is a plugin for standing up and running an AI-native IT business company** — not merely
"an organization." The company decides what to build as a business, builds through a forced
non-skippable SDLC, ships via CI/CD, operates under a reliability budget, navigates by DORA to the
moving bottleneck, and grows the system and the org together. This release re-scopes the whole
project to that definition, restructures the docs, and — most importantly — makes the process
**reproducible**: same org spec + RFP ⇒ same process, gates, contracts, and verification, and the
repositories the company builds clone-and-run the same for anyone.

### Docs — restructured into 4 Parts × 12 chapters (was 18 flat files)
- Consolidated the docs from 18 → 12 chapters, grouped into four Parts (Foundations / Design /
  Operate / North star) with a new `docs/README.md` map. The chapter skeleton is now stable: new
  material is added as a section inside a chapter, not as a new file. Merges: former operating-events
  + proxy-stack folded into **05 Operating a Running Company**; decomposition folded into **03**;
  manager-accountability folded into **09**; elastic-org folded into **02**. The S1 founding rehearsal
  moved to `demos/`.
- **THEORY §1b** — a new layer over the neutral organization definition: the org this template stands
  up is an IT business company, filling Organ 1 with a business telos and specializing Organs 2/4/6/7
  with the SDLC, CI/CD, reliability budget, and DORA. The AI-as-amplifier thesis is stated here.
- **docs/11 — The forced SDLC mold** (new chapter): the non-skippable phase chain
  (requirements→design→implement→test→integrate→deploy→operate), enforced by generalizing the `requires_prior`
  predicate from admission-gating to phase-gating. §0 states reproducibility as the deep purpose;
  §4a is the Level-2 reproducibility admission standard for the repos the org builds.

### Reproducibility & idempotency (the release's core)
- **SDLC phase gate (F1).** New ledger events `phase_started` / `phase_admitted`; `ledger.py`
  `REQUIRES_PRIOR` now enforces the phase order (a phase cannot start until its predecessor is
  admitted), so the same spec runs the same phases in the same order for every founder and run.
- **Idempotent ledger append (F3).** `ledger.py append --natural-key` no-ops a replay/retry of the
  same logical event, so exposure/cycle/WIP counts no longer drift with how many times a hook fired.
- **Spec-declared enforcement (F5).** Caps, budget window, iteration limits, and the seam gate now
  live in `constitution.yaml`'s `enforcement:` block (hash-chained, agent-unwritable), so every
  install of the same org enforces the SAME gates. `ORG_CAP_*` / `ORG_WINDOW` / `ORG_MAX_*` /
  `ORG_REQUIRE_SEAM` are demoted to DEV OVERRIDES. The iteration cap is now default-on.
- **Deterministic backlog (F4).** `candidate_id` is now a hash of (role, contract_ref, normalized
  gap), so the same RFP yields the same backlog; attention tie-breaks on it, not append order.
- **Idempotent projections (F2, F9).** `github_sync create` no-ops when an open Issue already matches;
  `conventions adopt` no-ops on an identical (scope, choice).
- **Real clock in the tick (F6).** `/org-tick` now uses the host UTC clock, not a frozen literal date
  and a zero counter, so missed-check detection depends on ledger state, not operator-passed args.
- **Founding coverage gate (F8).** New lint tooth **O10**: every declared deliverable must carry a
  non-empty acceptance standard, be owned by exactly one role, and have a checker distinct from its
  maker — so two foundings from the same RFP converge on the same contracts. `/org-found` now emits a
  coverage manifest.
- **Level-2 repo reproducibility (`tools/repro_lint.py`).** A deterministic gate checking a generated
  repo is clone-and-run reproducible: committed lockfile, pinned toolchain, one-command setup+test in
  a README, idempotent migrations, `.env.example`, and a CI workflow green from a clean clone. The
  **gate** and **maker** agent doctrines now require it.
- **DORA + reliability budget.** New ledger events `reliability_budget_checked` / `dora_snapshot`
  fold into docs/05 as operating instruments (error budget bounds deploy velocity; DORA four keys
  navigate to the moving bottleneck).

### SDD canonical form + branch model + integration phase (post-0.8.0 fold)
Deep-dived Spec-Driven Development (GitHub Spec Kit / AWS Kiro) and folded the canonical form in,
mapped onto the Issue hierarchy (no fragment `spec/plan/tasks` files — SSoT stays code + domain model):
- **SDD 3 layers → Issue hierarchy** (docs/11 §4b): objective Issue = **spec** (WHAT) + **plan** (HOW);
  task sub-issue = one **atomic task** (dep order, disjoint `owns` = the `[P]` parallel marker, entry
  files). Acceptance criteria now in **EARS** (WHEN/WHILE/IF/WHERE…SHALL).
- **Branch model + integration phase** (docs/11 §4c): feature branch per task (`feat/issue-N-slug` off
  `develop`) → merge to **`develop`** → a new **`integrate` phase** (the 7th) where the fanned-out
  siblings build+test **together** (green CI on `develop` = `integration_admitted`) → deploy is
  `develop`→`main`. The ledger now enforces `deploy` requires `integrate` (fan-out must fan back in).
  Owned by the supervising manager's A3, extended to cross-deliverable.
- **New github_sync commands:** `branch` (deterministic feature-branch name, Japanese-title safe) and
  `split-check` (shape warning if a task's `owns` spans territories or a dep is still open).
- **SPEC strengthened** for the third-party/no-context maker: Working context (repo/branch/setup-run/
  entry files), a runnable DoD command, a worked input→output example, actionable `depends_on`, a
  single-unit assertion, prior-deaths, and a Hand-back that targets `develop`.

### SSoT corrected — code + domain model, not the ledger
The ledger was wrongly called the SSoT. Corrected repo-wide: **SSoT = code + the domain model**
(conventions + org spec); the ledger is the **audit / requires_prior-enforcement / crash-safe-resume
record** (it holds the *receipt* of a decision, not the decision — which co-commits to code/conventions).
The GitHub Issue is the **main, terminal-independent work surface** (spec + work-log); a local ledger
is terminal-bound. `conventions` elevated to "the domain model". SPEC is the Issue structure, never a
`docs/spec/*.md` file (the fragment-Spec trap).

### Tests
- 144 passing (was 114): phase-gate (incl. integrate), ledger idempotency, spec-declared caps,
  `repro_lint` (incl. monorepo-CI), the O10 founding-coverage tooth, `github_sync` two-level Issues,
  work-log idempotency, deterministic branch naming, and `split-check` all have regression coverage.

## 0.6.0

Loop reliability — the failure modes a practitioner hits building an autonomous loop, checked against
the code and closed where the code fell short.

### Added
- **docs/10 — Loop reliability.** Why an unattended loop survives: a loop pass is a series system, so
  `n` decisions at accuracy `p` succeed `p^n` (10×0.95 ≈ 60%) — cut the decision *count* before
  sharpening steps (Barlow & Proschan 1965). Load-bearing constraints belong in the **enforcement layer**
  (hooks/lint, deterministic), not the request layer (prompts, probabilistic); a **subagent doesn't
  inherit the parent's prompt**, so cross-fan-out control must be a hook (with the honest caveat that the
  child's call reaching the hook is a harness property). State is **explicit in the ledger**, not context;
  trust is **staged read-only-first**. Grounded in the loop-engineering literature (docs/sources.md §16,
  r_kaga and y-hirakaw).
- **Catastrophic denylist** (`org_hook.py`). A verification pass found that the blast-radius cap — a
  *daily budget* — could not stop a single unrecoverable command: at the default cap, `rm -rf /` passed
  (weight 3, ~16 before the budget tripped). The denylist now **hard-blocks** the catastrophic class
  (`rm -rf /`/`~`/root-glob, `mkfs`, `dd` to a raw block device, fork bombs) regardless of budget and
  even with no ledger configured. Deliberately narrow — ordinary `rm -rf ./build` / `node_modules` stay
  cap-metered, not blocked. Sandbox opt-out: `ORG_ALLOW_CATASTROPHIC=1`.

### Fixed
- **docs/10 subagent-gating claim made honest.** The doc had asserted the hook "gates every subagent at
  every depth" as a plugin property; whether a subagent's tool call reaches `PreToolUse` is a *harness*
  property. The doc now states the plugin is correct-by-construction (verdict from the raw call + ledger,
  no inherited context) and requires a harness that fires the event for subagents — the docs/08 host
  contract, not a reimplementation.

## 0.7.2

Close "unattended ≠ unobservable" by delegating the escalation transport to the harness — the last
R0 replacement the audit found (loop→/loop and this notification transport were the two big ones).

### Added
- **Escalation reaches the user.** orgforge detects escalations but shipped no notify transport (R0 —
  the host delivers them); Claude Code *is* the host, so it now uses:
  - `/org-tick` sends a **PushNotification** on a genuine escalation only (a MISS, a tripped stall, a
    repeated death, an unproven rollback, a broken chain) — never on a healthy tick (fail-quiet).
  - `status.py redline` prints one line ONLY when the org is RED (silent when healthy), purpose-built
    for a persistent **Monitor** to push the moment a RED appears — so a RED never waits for the next
    tick. `/org-start` and SCHEDULER.md document arming it.

An R0 audit confirmed the rest is already delegated or correctly self-built: the drive is `/loop`; the
ledger (hash-chained audit spine), the doctrine/conventions admit-gate, the single-writer backlog, and
the judgment organs stay self-built — `memory`/`TaskList` lack the audit/gate/provenance those need.

## 0.7.1

Simplify the drive: delegate it to Claude Code's `/loop`, keep only the monitoring.

### Changed
- **`/org-start` drives with `/loop`, not CronCreate.** The drive — firing each cycle on a cadence — is
  now delegated to Claude Code's built-in `/loop` (R0: borrow the harness's loop, don't build one).
  `/org-start` prints three invocations (`/loop 15m /org-tick`, `/loop 60m /org-work`, `/loop 6h
  /org-discover`) — no cron expressions, no CronList idempotency dance. The SessionStart nudge and
  QUICKSTART/SCHEDULER updated to match.
- **The monitoring stays with the org.** `/loop` fires a command but can't judge whether a *due org
  check* ran; `tick.py`'s missed-check detection (a due check with no `verify_event` = MISS) is the
  org-specific part `/loop` can't provide, so it stays — "the loop stopped" is still a detected fact,
  not silence (docs/10). Delegate the drive, keep the monitor.
- OS cron (`scheduler-install.sh`) demoted to the one case `/loop` can't cover: running 24/7 with no
  session open. For everyday attended/kept-open runs, the three `/loop`s are the whole drive.

## 0.7.0

The ideal-state build-out (docs/12): a six-opinion synthesis defined what orgforge is *for* — a
spec-driven factory whose product is a verifying unattended loop and whose yield is a compounding
context base. This release closes the enumerated gap in three layers.

### Layer 1 — the loop can't run away (all enforcement-layer)
- **Concurrent-write prevention.** The seam/independence spawn gate is now **default-on** (opt out with
  `ORG_REQUIRE_SEAM=0`), and a spawn declaring `owns:` territory that collides with a live sibling's
  claim is refused — turning reconcile's post-hoc scan into a spawn-time precondition (single-writer
  ownership, prevented not detected).
- **Iteration/token/spend cap in the hook** (`guardrails.py cycles`, `ORG_MAX_CYCLES`/`ORG_MAX_TOKENS`)
  — the runaway kill ("$3-5, not $180") the blast-radius cap couldn't make.
- **Circuit breaker on non-progress** (`guardrails.py stall`) — trips a wedged cycle (identical output
  twice, or flat fraction) and frees its slot, over the `progress_recorded` stream it already writes.
- **O9 no-domain-deliverable lint tooth** — a mechanistic/control role may hold no contract.deliverable
  (the docs/03 §6.5 tooth, now implemented; catches the implement-without-judge case O8 misses).
- **Harness-capability probe** (`tools/harness_probe.py`, `/org-verify-guards`) — certify PreToolUse
  fires for a spawned subagent before trusting the org to fan out.

### The heart — learning accumulates and is used; the domain model grows
- **Learning feeds forward and is measured.** `/org-work` checks each item against `nearby_deaths` /
  `death_causes` before delegating; `learning.py repeats` escalates a death cause that reappears (the
  org re-made a recorded mistake) so "learning lifts quality" is a checked fact.
- **Reuse fires.** `/org-work` consults `reusable_modules` / `parts_inventory` before authoring, and
  `cycle_completed.reused` records what was pulled — reuse is now visible, not a library nobody imports.
- **The SSoT / domain model grows during operation.** `/org-work` settles domain rules IN the work
  cycle (co-commit, not a deferred task); `conventions.py growth` reports the domain model's size so
  rising inferability is a checked fact.

### Layer 2 — a factory, not a workshop
- **External-signal front door** (`/org-triage`) — a bug/issue/feedback becomes a triaged backlog item;
  the host feeds it from an issue tracker (SCHEDULER.md), compressing the human's input to one label.

### Layer 3 — anyone can use it
- **One status board** (`/org`, `tools/status.py`) — "how's my org?" in one glanceable GREEN/AMBER/RED
  answer, in the user's language, without reading the ledger. Command surface reframed: the few you use
  (`/org-found`, `/org-start`, `/org`, `/org-triage`) vs the internal metabolism (`/org-work` etc.) that
  runs on cadence.
- **Version drift fixed** (plugin.json / README now agree).

### Lower-priority reliability
- **Bounded retry/backoff** on a transient organ failure (`_run_organ`) so one flake doesn't hard-block
  an overnight run; a clean verdict is never retried.
- **Proven-rollback** (`guardrails.py rollback`) — a reversible action with no declared undo escalates,
  so silence-consent never trusts an untested reversibility claim.

## 0.5.1

Follow the quickstart, get a running org — the metabolism starts in-session without hunting for how.

### Added
- **`/org-start`** — one idempotent command brings the org to its running state in the current session:
  it registers the recurring cycles (`/org-tick`, `/org-work`, `/org-discover`) via Claude Code's
  `CronCreate`, checking `CronList` first so it never double-registers. Session-scoped (stops when the
  session closes; OS cron via `scheduler-install.sh` is the 24/7 path).
- **SessionStart nudge to start the org.** On an org session (ledger + role set), the SessionStart hook
  now injects a prompt asking the model to run `/org-start` — so the org starts on its own at the top of
  the session. A hook cannot call `CronCreate` itself (SessionStart hooks cannot invoke tools), so this
  is an instruction the model acts on, with `/org-start` as the guaranteed manual fallback. Non-org
  sessions get no nudge.

### Changed
- **QUICKSTART §6 rewritten** around `/org-start` as the start step, and corrected the "unattended 24/7"
  claim: in-session scheduling is session-only; the OS cron is the genuinely-unattended path.

## 0.5.0

The scheduler is real now, not just documented. Previously SCHEDULER.md described how one *could*
wire the cadence but nothing actually registered it — so nothing ran unattended.

### Added
- **`scheduler-install.sh` / `scheduler-uninstall.sh`** — one command installs the org's metabolism
  on the **OS cron**, so it runs 24/7 with no Claude Code session open. It writes crontab entries that
  invoke `claude -p "/org-tick" | "/org-work <role>" | "/org-discover <role>"` headless, with the
  plugin attached (hooks + doctrine injection fire) and ORG_* env inlined; output streams to
  `$ORG_LEDGER_ROOT/cron.log`; each entry is tagged `# orgforge:<role>` for clean removal. `--dry-run`
  previews the lines; intervals of 60+ minutes become valid hourly cron expressions (no invalid `*/60`).

### Changed
- **SCHEDULER.md corrected.** The in-session schedulers (`/schedule`, `/loop`) are **session-only** —
  they stop when Claude Code exits and are not "unattended." The doc now states this plainly and points
  to the OS-cron install for a genuinely 24/7 org (docs/08 §4 names "a cron" first for this reason).

## 0.4.3

### Fixed
- **`2>/dev/null` and `> /dev/null` are no longer charged as destructive.** The redirect-to-absolute-path
  check (`(\||>>?)\s*/`) fired on stderr suppression and `/dev/null` sinks, so a read-only search like
  `grep -r foo . 2>/dev/null` was metered as a destructive op and drained the daily budget — the reason
  the cap had to be raised repeatedly. The check now excludes `/dev/*` sinks and stderr redirects and
  matches only a genuine overwrite of a system path (`> /etc/…`, `>> /usr/…`). Real system-path
  overwrites and pipe-to-shell stay destructive; `2>/dev/null`, `> /dev/null 2>&1`, and relative-path
  redirects (`> out.log`, `>> ./local.txt`) draw down nothing.

## 0.4.2

Stop the guardrail from taxing benign work, right-size the caps for real days, and ship a proper
reference so operators aren't reading source to configure the thing.

### Fixed
- **Unknown/read-only shell is no longer metered.** The classifier used to charge a `shell_effect`
  budget for any command it couldn't classify — so benign work (`git status`, `find`, `du`, an
  unfamiliar CLI) quietly drained the daily budget until the cap blocked everything, a false-positive
  deadlock. Now "unknown" is not "dangerous": only explicit destructive / external / infra patterns
  draw down a budget; reads, build tooling, and unclassified shell draw down nothing. (Also fixes a
  2-word benign-match bug where `git status` exactly could slip the allowlist.)

### Changed
- **Right-sized per-day caps.** With the daily rolling window (0.4.0), the caps are per-day budgets;
  the old floor of 3 was a hand-count that a research/ML day blew through immediately. New defaults:
  `destructive_ops` 3→**50**, `external_writes` 3→**30**, `infra_changes` 3→**20**, `file_mutations`
  200→**500**. Still trips a genuine runaway (hundreds of irreversible acts/day); no longer blocks a
  normal day. `ORG_CAP_SHELL_EFFECT` is deprecated (unused; kept so an old override is not an error).

### Added
- **`REFERENCE.md`** — the flat lookup operators were missing: every environment variable (with
  defaults), every command, the org's files, the ledger events you touch most, and a troubleshooting
  section for the problems people actually hit (cap deadlock, benign-flagged commands, missing
  injection, updating the plugin). Linked from README and QUICKSTART; QUICKSTART's env table updated
  to the new defaults.

## 0.4.1

Work-in-progress survives a context wipe. Half-done work now lives in the ledger, not in the
conversation, so `/clear` or a fresh session no longer loses "how far did we get."

### Added
- **Progress checkpoints** (`ledger-schema.yaml`). `cycle_started`/`cycle_completed` gain a
  `candidate_id` (in-flight is now per-item, not just a per-role count), and a new
  `progress_recorded {role, candidate_id, fraction, phase, done_so_far, next_step, blocked_by,
  artifacts}` event records "how far / what's done / the next step / any blocker" at each milestone.
- **`work_in_progress` view** (`ledger.py`). Resolves the candidates started-but-not-completed, each
  with its latest checkpoint — the recovery source after a context wipe.
- **Automatic resume injection** (`org_session_start.py`). The SessionStart hook now injects the role's
  work in progress alongside its doctrine — so a fresh session (after `/clear`, a crash, or a scheduled
  wake) picks up from `next_step` automatically, with no `/org-resume` needed. "Just continue" works.
- **`/org-resume`** — the manual counterpart: show a role's in-progress board and pick up an item.

### Changed
- **`/org-work` records as it goes.** The PM loop now checkpoints keyed by `candidate_id`
  (started → progress at each milestone → completed), and states the discipline explicitly: work only
  items that are on the backlog; submit first if it isn't, so nothing is invisible/unrecoverable.

## 0.4.0

The running metabolism: a department now has a driven backlog, a PM loop that delegates in
parallel, a self-improvement loop, and a scheduler wired to the harness's own loop — plus the
knowledge-aggregation guarantee made load-bearing, and two guardrail deadlocks fixed. Aligns the
plugin version with the autonomous-founding narrative the docs already describe (v0.3/v0.4).

### Added
- **Driven backlog with two intake paths** (`ledger-schema.yaml`, `attention.py`). `candidate_submitted`
  gains `source: mandate|self`; top-down instructions and self-raised tasks share one backlog
  (`open_experiments`) and are prioritized on one footing. An in-ranking **mandate rides a floor**
  (zone of acceptance, Simon 1947) so a live instruction is never starved by low-priority self work;
  an off-ranking mandate gets no floor (a visible drift signal). (docs/09)
- **The PM loop** (`/org-work <role>`). Select from the backlog by situated attention, delegate the
  selected items to subordinates **in parallel** (one `Task` each, where the split is genuine), record
  `cycle_completed`. Parallelism is a judgment, not a mandate.
- **The discovery loop** (`/org-discover <role>`). Problemistic search raises `source: self` backlog
  items from aspiration gaps, scoped to the role's own domain; append-only, fail-quiet when there is
  no gap. (docs/09)
- **Decomposition doctrine** (`docs/03`, projected into `ROLE.md`). How a manager splits an assignment,
  grounded in Parnas (information hiding), Simon (near-decomposability), Thompson (interdependence),
  Becker & Murphy (coordination cost), Conway. Never split reciprocal work; cut at the design secret;
  each child carries a seam contract; route another role's domain to that role.
- **Scheduler wiring** (`integrations/claude-code/SCHEDULER.md`). Realize `schedule.yaml`'s cadences on
  Claude Code's own scheduler (`/schedule`, `/loop`) — R0-conformant ("the harness's own loop"), no R0
  change, wiring confined to the integration layer.
- **`ARCHITECTURE.md`** — the whole-system map: ecosystem (neutral core → projection → harness, organs,
  enforcement vs advisory) and lifecycle (founding → projection → operation → guardrails → evolution).

### Changed
- **O8 no-doctrine-capture lint tooth** (`org_lint.py`). No control role may carry `implement` together
  with `judge`/`review` — a coordinator that produces a domain deliverable collapses maker and checker
  and pools domain knowledge in the boss instead of the field role that owns it (docs/07 §1.1, docs/03
  §3). Generalizes O6's "authorization holder must not implement" to every adjudicating seat.

### Fixed
- **Word-boundary destructive classification** (`org_hook.py`). The blast-radius classifier tested
  destructive tokens as substrings (`"rm " in cmd`, `"-f " in cmd`), so a path like `.../fx-ml-platform/…`
  or a flag like `grep -f` was miscounted as destructive and eventually blocked every command. Now
  tokenizes and matches on word boundaries; operators/dotted calls stay on tight-anchored regex.
- **Rolling-window deadlock** (`org_hook.py`). The blast-radius window was hardcoded to `1970-01-01`
  (all-time) while appended events were stamped `1970` too — read-window and write-ts diverged, so
  committed exposure accumulated forever and the cap eventually **blocked every edit**. Now a rolling
  **daily** window (both the append ts and the read window share one `_now_ts` clock); the budget
  resets each day with no operator action. `ORG_WINDOW=all` opts back into an all-time cap deliberately.

## 0.2.0

Hierarchical doctrine, refounding, delegation seams, and an operating-phase spine —
plus a redesigned blast-radius cap that no longer blocks normal work.

### Added
- **Hierarchical per-role doctrine hand-off** (`tools/handoff.py`). A manager hands each
  subordinate a packet: the child's slice, a **seam contract** (inputs/outputs/owns/forbid), and
  **doctrine scoped to that slice** — so knowledge narrows going down and splits by trade
  (`ui-worker` ≠ `api-worker` ≠ `db-worker`), and a parent's broader brain never leaks down. The
  runner (`run_department.py`) wires `ORG_DOCTRINE_ROOT` + `--plugin-dir` so a top-level launch
  fires the doctrine-injection hook automatically. (docs/06 §2.1)
- **Doctrine remap for refounding** (`doctrine.py remap`). When roles are renamed / split /
  merged, every live claim follows as an asset; a claim that maps to nothing **blocks** the
  refound rather than being silently lost. (docs/05 §4.4, docs/06 §2.2)
- **Spawn seam-contract gate** (`ORG_REQUIRE_SEAM=1`). An `Agent`/`Task` spawn is blocked unless
  its prompt carries a seam contract or an explicit `INDEPENDENT:` declaration — recursive splits
  can't drift on an un-owned interface. (docs/06 §2.1.1)
- **Silence-consent gate** (`guardrails.py consent`). A reversible backlog action rides the
  delegated tier (silence = consent, proceeds); an irreversible one (deploy/spend/destroy/…) holds
  for an explicit human ack. (docs/05 §2.1)
- **STALE-REFERENCE auto-trigger** (`guardrails.py staleref --auto`). Derives the trigger event +
  bound roles from the ledger's latest reference change, so a central re-prioritization propagates
  to departments without hand-fed arguments. (docs/05 §5.1.3, docs/09 §3.1)
- **DEPENDENCY-STALL dependency edges** (`reconcile.py stall`). Reads `work_claimed.depends_on`
  edges to report who a blocked role awaits, which downstream roles are impacted, and the
  lowest-common-owner to route to — instead of cycle timing alone. (docs/05 §5.2)
- **QUICKSTART.md** — install, the one required setting, guardrail tuning, and a verified
  "prove it blocks" snippet.

### Changed
- **Blast-radius cap now meters irreversibility, not activity.** The old flat "every file write
  costs 1 against a cap of 3" blocked a normal build at its 4th file. Now: creating a new file
  (decided by a filesystem stat), reads, and build tooling (`npm`, `pytest`, `git commit`) are
  **not metered**; the scarce low caps are reserved for `destructive_ops` (scope-weighted —
  `rm -rf` = 3), `external_writes`, `infra_changes`; overwriting an existing file is
  `file_mutations` (high cap 200). A 300-file build proceeds; `rm -rf` still hard-stops. New caps
  are tunable via `ORG_CAP_*`. (docs/05 §2.1)

### Docs
- Operating-phase flow integrated into existing homes (no new file): the two-level backlog
  (org-wide ranking + per-dept next-task) in docs/09 §3.1; the registrar as org-wide priority
  owner in docs/05 §2.6; reversible-vs-irreversible consent in docs/05 §2.1.
- New `examples/`: `doctrine-scoping` (per-role brains that narrow + refound remap), and
  `seam-descent-run` (an org self-driving scoped hand-offs end to end).

Every change ships with regression tests (76 green) and passes the payload-schema drift guard.

## 0.1.0

Initial template: the articulated organization as installable Claude Code features — PreToolUse
guardrails that block, SessionStart doctrine injection, per-department subagents, organ tools
(ledger, guardrails, doctrine, reconcile, resource, attention, learning), and organ slash-commands.
Verified on the real CLI (v2.1.211).
