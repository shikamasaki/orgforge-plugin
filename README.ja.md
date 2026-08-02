# orgforge-plugin

> **AIコーディング組織のためのレジリエンスエンジニアリング。**

orgforgeはClaude CodeやCodexを置き換えるruntimeではなく、既存coding agentにownership、
workflow gate、独立check、evidence、人間に残す判断を加えるportable governance planeです。
coding-agentを含む開発組織が、変動や制約の下でも必要な成果と人間の統制を維持し、安全に
縮退・停止・復旧し、日常の成功と失敗から適応能力を高められるようにします。

Respond／Monitor／Learn／Anticipateは独立した製品モジュールではなく、相互に関係する能力モデルと
評価レンズです。レジリエンスを単一スコアで自動判定せず、証拠・欠測・confidence・判断主体・
変更結果を検査可能にします。constitutionとworkflowはWork-as-Imagined、ledger・Git・CI・traceは
Work-as-Recorded、agent／humanの説明はWork-as-Reportedであり、Work-as-Doneはそれらの部分観測から
不確実性を明示して推論します。

既存repoへの導入:

```text
/orgforge-plugin:org-adopt
```

sudo、daemon、別OS UID、鍵、branch、GitHub Issue、network accessは不要です。

公式日本語ドキュメントは [`docs/ja/README.md`](docs/ja/README.md) から始まります。

- [Quickstart](docs/ja/quickstart.md)
- [Architecture](docs/ja/architecture.md)
- [保証モデル](docs/ja/assurance.md)
- [運用](docs/ja/operations.md)

Delegation Resilience adapterの説明は[`docs/ja/delegation-resilience-adapter.md`](docs/ja/delegation-resilience-adapter.md)にあります。
固定したDR Assurance Graph v0alpha1とTransactional Action v0alpha2へ、OrgForgeのexercise evidenceを
source-boundな派生artifactとしてexportします。`GRAPH_VERIFIED`はグラフの内部整合性と再現性だけを示し、
recovery capability、human takeover、deployment approvalの実証を意味しません。

英語版は [`docs/en/README.md`](docs/en/README.md) です。両セットはそれぞれ単独で完結します。
