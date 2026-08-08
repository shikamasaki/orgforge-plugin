# REQUIREMENTS — 要求記述のテンプレート（`/org-found` が `REQUIREMENTS.md` として書く）

> **これはテンプレート（節の骨格）であり、それ自体が要求ではない。** `/org-found` は受け取った
> ブリーフをこの構造に整形して org 根の `REQUIREMENTS.md` に書く。`org_lint` が必須節の欠落と
> 文の書き方を機械検査する（docs/11 §0a / §0b）。
>
> **なぜ「RFP」ではないのか:** RFP (Request for Proposal) は**調達文書**で、外部の競合ベンダーに
> 提案を求め、比較評価して契約相手を選ぶためのもの。中核は評価基準・配点・提案書式指定・契約条項
> であり、自社開発では機能しない。ここで書いているのは ISO/IEC/IEEE 29148:2018 の
> **StRS (Stakeholder Requirements Specification)** に相当する — 発注側の視点でニーズを記述し、
> まだ解に踏み込んでいない文書。RFP から借りる価値があるのは「評価基準を事前に文書化する」規律
> だけで、それは本テンプレートでは受入基準（§4）と成功基準（§5）が担っている。
>
> **準拠の宣言:** ISO/IEC/IEEE 29148:2018 の **tailored conformance**（同規格 §4.5.2 が正式に
> 認める適合形態）。SRS の全20条項（§9.6）は採らない — `Memory constraints` や
> `Site adaptation requirements` は組込み・防衛向けの条項で、小規模プロダクトでは空欄が並ぶだけ
> になり、**空欄の節がある文書は読まれなくなり、やがて更新されなくなる**。採るのは §5.2.4（構文
> 規約）、§5.2.5（個々の要求の特性）、§5.2.6（集合の特性）、§5.2.7（避けるべき語）の4条項。

---

## 1. Why — なぜ作るのか

`<顧客視点で1段落。「誰の、どんな状況の、何が変わるのか」。技術ではなく結果を書く。>`

> Amazon の PR-FAQ に倣い、**すでに世に出ているかのように書く**。ここが1段落に収まらない場合、
> 顧客価値が固まっていない兆候なので、要求を書く前に戻ること。

**目的（一文）:** `<この org が存在する理由。メトリクスではなく結果。>`

## 2. Goals / Non-Goals

**Goals:**
- `<達成すべきこと>`

**Non-Goals（やらないと明示する）:**
- `<やらないこと。なぜやらないかも書く>`

> Google の Design Doc 由来。**Non-Goals はスコープクリープを止める最も安価な装置**であり、
> 「書いていない＝やらない」ではなく「書いてある＝やらないと決めた」にすることで、後から
> 「これも要るのでは」を再燃させない。EXCLUDE（§7）との違い: Non-Goals はこのプロダクトの
> 方向性として持たないもの、EXCLUDE は今回のリリースから外すもの。

## 3. Requirements — 要求（EARS 記法・FR-001 で採番）

> **EARS の6パターンのいずれかで書く**（Alistair Mavin, Rolls-Royce。Airbus / NASA / Bosch /
> Intel / Siemens が採用）。ruleset は「前提条件は0個以上、**トリガーは最大1つ**、システム名は
> 1つ、応答は1つ以上」。トリガーが最大1つという制約が、**要求の粒度を構文レベルで強制する**。
>
> | パターン | テンプレート |
> |---|---|
> | Ubiquitous（常時） | `The <システム> shall <応答>` |
> | State Driven（状態駆動） | `While <前提条件>, the <システム> shall <応答>` |
> | Event Driven（事象駆動） | `When <トリガー>, the <システム> shall <応答>` |
> | Optional Feature | `Where <機能が含まれる場合>, the <システム> shall <応答>` |
> | Unwanted Behaviour | `If <トリガー>, then the <システム> shall <応答>` |
> | Complex（複合） | `While <前提>, When <トリガー>, the <システム> shall <応答>` |
>
> **日本語で書く場合**も構文は保つ:「〜のとき、システムは〜すること」。29148 §5.2.4 NOTE 2 は
> ユーザーストーリー形式も許容しているが、**AIエージェントが実装する文脈では EARS を使う** —
> 曖昧語が構文レベルで排除され、誤解釈が激減するため。
>
> **キーワード規約（29148 §5.2.4）:** `shall`＝要求（必須）/ `will`＝事実・将来の宣言（拘束しない）
> / `should`＝選好（要求ではない）/ `may`＝許容。**`must` は使わない**（要求と誤解される）。

| ID | 要求（EARS） | 根拠 |
|---|---|---|
| FR-001 | `<When ... the system shall ...>` | `<なぜ必要か>` |

> **曖昧な箇所は推測で埋めず `[NEEDS CLARIFICATION: 何が不明か]` と明示する**（GitHub Spec Kit
> 由来）。エージェントが推測で実装するのが最大の失敗モードであり、未解決のまま残っていれば
> lint が落とす。

## 4. Acceptance — 受入基準（Given-When-Then）

> 各要求に対し、**実装前に**検証シナリオを書く。Gherkin（Cucumber 公式仕様）の記法を借用する
> が、ツールチェーンの導入は任意。これが RFP から借りるべき唯一の本質 —「評価基準を事前に
> 文書化する」ことの、自社開発における翻訳。

```
FR-001:
  Given <前提>
  When  <操作>
  Then  <観測可能な結果>
```

## 5. Success Criteria — 成功基準（SC-001 で採番）

> **技術非依存かつ定量的**であること（Spec Kit 由来）。「速い」ではなく「95パーセンタイルで
> 200ms 以内」。実装方法に言及しない。

| ID | 成功基準 |
|---|---|
| SC-001 | `<定量的・技術非依存>` |

## 6. Constraints / Non-Functional — 制約と非機能要求

> ISO/IEC 25010:2023 の9特性（Functional suitability / Performance efficiency / Compatibility /
> **Interaction capability**（旧 Usability）/ Reliability / Security / Maintainability /
> **Flexibility**（旧 Portability）/ **Safety**（2023 で新設））を**一度なぞって、該当するものだけ
> 書く**。全特性を埋めるのは過剰。決済や個人情報を扱うなら Safety と Security は必ず見ること。

- `<制約>`

## 7. Out of Scope / Assumptions / Open Questions

**Out of Scope（今回やらない）:**

| 除外するもの | 理由 |
|---|---|
| `<X>` | `<なぜ外すか。既知の失敗なら「既知の死。再調査しないこと」と明記>` |

> **既知の死を書き残すことが最も価値がある。** 「調べたが構造的に不可能だった」を書いておかないと、
> 別のエージェントが同じ調査を再実行して同じ結論に到達し、時間を溶かす。

**Assumptions（前提。崩れたら要求が変わる）:**
- `<前提>`

**Open Questions（未決。実装前に決める必要がある）:**
- `<問い>`

---

## 付録: レビューチェックリスト（29148 §5.2.5 / §5.2.6 / §5.2.7）

`org_lint` が機械検査するものと、人が見るものの両方を含む。

**個々の要求（§5.2.5 — 9特性）:**
Necessary（必要）/ Appropriate（抽象度が適切、設計を不要に制約しない）/ Unambiguous（一意に
解釈できる）/ Complete（他を見ずに理解できる）/ **Singular（単一の能力のみ)** / Feasible（実現
可能）/ **Verifiable（検証可能）** / Correct（元のニーズの正確な表現）/ Conforming（テンプレートに従う）

**要求の集合（§5.2.6 — 5特性):**
Complete（TBD/TBS/TBR を含まない）/ Consistent（矛盾・重複がなく、単位と用語が統一）/ Feasible
（"affordable" を含む）/ Comprehensible / Able to be validated

**避けるべき語（§5.2.7 — lint が落とす）:**

| 種類 | 例 |
|---|---|
| 最上級 | best, most, 最高の, 最適な |
| 主観語 | user friendly, easy to use, cost effective, 使いやすい, 分かりやすい |
| 曖昧な代名詞 | it, this, that（何を指すか不明な場合） |
| 曖昧な副詞・形容詞 | almost always, significant, minimal, ほぼ, 十分に, 適切に |
| 曖昧な接続 | `and/or`, および/または |
| 非検証語 | provide support, but not limited to, as a minimum, 等をサポートする |
| 比較句 | better than, より良い |
| 抜け穴 | if possible, as appropriate, 可能であれば, 必要に応じて |
| 全称語 | all, always, never, every, すべて, 常に, 決して |
| 不完全な参照 | 版数・日付のない外部文書参照 |
