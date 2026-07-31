# 保証モデル

## 1. サポートするthreat model

agentは誤り、不完全、迎合、古い前提、確認不足を起こしますが、自分のhostを攻撃する
敵対processとしては扱いません。

コア統制:

- 明示されたroleとcontract
- workflow上のmaker/checker分離
- gateとskeptic
- phase順序の強制
- reasoningとevidenceの記録
- HALTとeffect cap
- reproducibilityとbundle check

orgforgeは敵対processの封じ込め、credential custody、immutableなlocal ledgerを提供しません。
production、資金、公開、credential、規制資産へ影響するdeploymentは、host platformから
sandbox、permission、approval、credential custodyを得る必要があります。これはdeploymentの
責務であり、orgforge機能でもcore release gateでもありません。

## 2. Identity label

| Label | 正確な意味 |
|---|---|
| `claimed` | callerの自己申告 |
| `observed` | host/writerによる観測。判断主体の証明ではない |
| `attested` | receiptと束縛fieldを登録鍵で検証済み |
| `authenticated` | 外部custodyとcaller認証があるdeployment向け予約値 |

同一local UIDが読める非対称秘密鍵は強い改竄検知を提供しますが、敵対的principal境界には
なりません。したがってlocal receiptは`attested`が上限です。

## 3. Reviewer independence

`cross-harness`は異なるmodel lineageによるreviewです。異なるblind spotを持つmodelが、
makerや最初のgateが見落とした欠陥を発見する確率を上げます。

次の意味ではありません。

- 別途認証された人間
- agentから到達不能な署名鍵
- 別OS security principal
- 敵対的な同一UID callerへの耐性

review多様性は品質統制でありidentity security claimではありません。

## 4. Record integrity

ledgerはappend-only規律とhash chainを持ちます。変更を検知し、順序をreplay可能にしますが、
caller-writableなfilesystemをimmutableにはしません。

Git履歴、backup、CI record、host storage controlがledgerを補完します。

## 5. separate-UID writer隔離

separate-UID writer隔離は **supported core featureとして採用しません**。

理由:

- supported product guarantee外のriskを対象にする
- OS固有runtimeと運用複雑性が大きい
- writer資産しか守らない
- 強い資産境界はhost環境の責務
- 必須化すると既存harness/no-new-runtime制約に反する

実験codeやhistorical runbookはsupported guaranteeではありません。個別deploymentで測定せず
`separate_uid`を主張せず、judge custodyとして扱いません。

## 6. Releaseで主張するもの

orgforge releaseが主張できるもの:

- enabled hook下のworkflow enforcement
- 記録されたmaker/gate/skeptic分離
- cross-harnessの非相関review
- attested local receipt
- tamper-evident history
- 人間が保持する不可逆権限

主張しないもの:

- 敵対的な同一UID封じ込め
- local judgeのauthenticated identity
- local agent間の暗号学的独立性
- immutable local ledger
- 標準のseparate-UID writer隔離
