# orgforge — 日本語ドキュメント

このディレクトリはorgforgeの公式日本語ドキュメントです。各ページは日本語版だけで理解・運用
できるように完結しており、英語版を参照しなくても利用できます。

> **指示書を、監査可能な開発組織へ。**

## orgforgeとは

orgforgeはClaude CodeやCodexなど、既存のcoding-agent harnessへ組織運営の骨格を加える
薄い制御層です。人間の組織が暗黙に持つ次の情報を、AIが実行できる形で明文化します。

- 組織が何を達成しようとしているか
- どの役割が何を所有するか
- 各役割へ何の情報を渡すか
- どの判断を人間に残すか
- 成果物がどのSDLC phaseを通るか
- admit・integrate・deploy・operateの前に何の証拠を要求するか

orgforgeはhost harnessを置き換えません。loop、scheduler、tool mediation、sandbox、CI/CDは
既存harnessの機能を利用します。

最大の差別化は**共進化**です。プロダクトをbuild・operateして得た証拠から、role ownership、
contract、context flow、checkの変更をboundedなproposalとして作ります。組織を固定promptのまま
放置せず、プロダクトと一緒に育てます。ただしpurpose、constitutionの境界、不可逆判断は人間に
残します。

## 製品の構成

orgforgeは次の6機能を小さく組み合わせます。

1. **Organization compiler** — 実在するcodeから最小のownershipとchecker構造を作る
2. **Workflow governance** — SDLC順序とacceptance barを明示し、機械検査する
3. **Evidence ledger** — 判断・検証・effectを記録し、後から作業を再構成できるようにする
4. **Harness adapters** — 同じneutral organizationをClaude CodeとCodexへ投影する
5. **Operational insight** — status、drift、cap、HALT、remaining workを表示する
6. **Organization evolution** — 観測したbottleneckと失敗から、判断線を守った構造変更を提案する

`org-goal`は明示したobjectiveをClaude Code／Codexの再起動をまたいで持続させます。progress、
next action、blocker観測、完了証拠、所有host sessionは共通ledgerへ置きます。Codex native Goalは
同期されるadapter projectionであり、Claude CodeはSessionStartとsession-scoped loopで再開します。
どちらもhostが閉じている間の実行を主張しません。

既存repoでは`/orgforge-plugin:org-adopt`が1回のbounded workflowでlocal導入を完了します。
sudo、daemon、別OS UID、鍵、branch、GitHub Issue、network accessは不要です。

## サポートする保証

orgforgeは通常のagent運用で支配的な次の失敗を対象にします。

- 幻覚と古い前提
- 迎合的な同意
- 検証やSDLC phaseの省略
- 誤った自己承認
- tool effectの暴走
- 判断の消失と監査不能

標準で主張する保証:

| 軸 | サポートする保証 |
|---|---|
| 判断identity | `attested` |
| review多様性 | `cross-harness` = 異なるmodel系統による非相関review |
| writer経路 | `process_mediated` |
| ledger | 改竄検知。immutableではない |

同一UIDの敵対process封じ込め、外部認証されたjudge identity、local agent間の暗号学的独立性は
主張しません。

## コアに含めないもの

- 独自agent runtimeやscheduler
- 常駐remote judge service
- mTLS judge基盤
- KMS、HSM、PKCS#11、Secure Enclave統合
- ClaudeとCodexの別OS UID化
- separate-UID writer隔離をrelease前提にすること

標準は**trusted developer mode**です。development roleはfilesystem、shell、network、
dependency、docs/API、通常のGit連携を都度承認なしで使います。Claudeは
`--dangerously-skip-permissions`、Codexはapproval/sandbox bypassを使います。production
credentialを置かない、信頼済みの開発機・repoだけで使ってください。deploy、credential、外部公開、
production操作をroleへ渡さないという宣言は維持しますが、これはgovernance ruleであり、
敵対processの封じ込めではありません。実操作はhost platformのprotected environmentで行います。

production、資金、外部公開、規制資産を扱うorgでは、host platformのprotected environment、
credential custody、sandbox、approval、auditを利用します。orgforgeはその判断と証拠を記録し、
platform自体を再実装しません。

## ドキュメント

- [Quickstart](quickstart.md) — サポート対象のworkflowを導入する
- [Architecture](architecture.md) — neutral core、host projection、ledger、SDLC mold
- [保証モデル](assurance.md) — 主張する保証と主張しない保証
- [運用](operations.md) — 日常運用、gate、HALT、cap、人間判断

repository rootと従来の`docs/`にある英日混在文書は、長文の設計記録として残します。表現が
競合する場合は、この日本語セットと対応する英語セットを現在の公式仕様とします。
