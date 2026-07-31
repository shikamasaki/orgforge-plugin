# 運用

## 1. 標準運用

既存host harness上で次を満たして運用します。

- hook有効
- organizationとconstitutionをcommit
- working directoryからledgerを発見可能
- deploymentはprotected CI/CD
- charterと不可逆操作は人間承認

privileged daemonや別writer UIDは不要です。

## 2. 日常flow

```text
intake → claim → work → gate → skeptic → integrate → deploy → operate
```

toolは配管と記録を担当し、roleが判断します。judgmentには次を含めます。

- verdict
- reasoning
- 実行したevidence
- 適用したstandard
- 採用しなかったalternative
- 受容したresidual risk

## 3. HALT

HALTは運用上のbrakeです。active中は通常作業をblockし、観測、検証、安全な修復、認可済み解除
だけを残します。

releaseでは、別登録approver、対象に束縛された非対称receipt、recovery evidenceを要求します。
これはworkflow separationとattestationであり、敵対的なkey custodyではありません。

解除記録に失敗した場合はHALTを維持します。

## 4. Effect cap

destructive operation、external write、infrastructure change、file mutationを上限で制御します。
すべてのshell commandを課金する仕組みではなく、runawayを止めるための仕組みです。

永続設定はconstitutionをsource of truthにします。環境変数はdevelopment overrideです。

## 5. Productionと実資産

実際の権限はhost境界へ置きます。

- CI protected environment
- branch protection
- deployment approval
- cloud IAM
- external secret storage
- harness sandboxとtool permission

orgforgeは統制が出した判断と証拠を記録します。platformのroot credentialを保持・再実装しません。

## 6. Failure handling

- 継続が不可逆effectを生む場合、control stateを読めなければfail-closed
- check失敗は理由を報告し、違う理由の拒否を合格にしない
- write失敗をcontrol成功として報告しない
- exact retryでdurable decisionを重複させない
- 実orgを破壊的test fixtureにしない

## 7. 非サポートのseparate-UID writer実験

通常運用でprivileged writer-install commandを実行しません。別UID writer codeがcandidateや
historyに存在しても実験扱いで、supported productの外です。release、Quickstart、
local development、通常のunattended runには不要です。
