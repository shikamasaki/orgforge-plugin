# Architecture

## 1. 最も重要な設計判断

orgforgeはagent実行engineを提供しません。既存harnessが次を提供します。

- model interaction loop
- tool実行とmediation
- subagent
- scheduling
- sandbox
- CI/CD統合

orgforgeが追加するのは組織層です。

- 宣言的なorganizationとconstitution
- roleから各harnessへのprojection
- 強制されたSDLC mold
- ledgerへ残る判断と証拠
- static lintとlive hook

これがR0境界です。既存runtimeを利用し、再実装しません。

## 2. Neutral coreとprojection

```text
template/ + tools/ + integrations/common/
                  |
                  +-- integrations/claude-code/
                  |
                  +-- integrations/codex/
```

neutral fileがsource of truthです。各integrationはinstall後も自己完結するようbundleを持ち、
sync testがneutral sourceとの差を検出します。

## 3. 連動する2つのlifecycle

組織lifecycle:

```text
found → roleをproject → operate → observe → adapt
```

製品lifecycle:

```text
requirements → design → implement → test → integrate → deploy → operate
```

ledgerが両者を接続します。製品の結果が組織学習とresource再配分を起こし、現在の組織構造が
次の成果物の流れを決めます。

## 4. Enforcement境界

live hookは通常のtool callをblockできます。ledgerは不正なphase transitionやprior judgment
不足を拒否できます。static lintは内部矛盾したorganizationを拒否できます。

trusted base:

- host harness
- 有効なhook設定
- local filesystem
- それらを変更できるhuman/administrator

orgforgeはこのbaseを通って動くagentを制約します。base ownerからbase自体を守りません。

## 5. 独立した保証軸

| 軸 | supported core |
|---|---|
| 判断account | 検証済みreceipt: `attested` |
| review品質 | 別model lineage: `cross-harness` |
| writer経路 | host mediation: `process_mediated` |
| 履歴 | hash-chain: tamper-evident |

writer隔離をjudge隔離として扱わず、model差を人物認証として扱わず、署名検証を敵対的な
同一UID排除として扱いません。

## 6. separate-UID writer隔離をコア採用しない理由

別UID writerが守るのはwriter資産だけです。一方でdaemon、privileged install、OS固有service、
dependency provisioning、socket lifecycle、migration、rollbackを追加します。judge key、host
設定、deployment credential、external effectは守りません。

productがサポートするthreat modelに対して費用が見合いません。敵対的な資産保護が必要なら
host platformが境界を提供します。repositoryに実験的writer隔離codeが残っていても、
supported dependencyやcore release gateにはしません。
