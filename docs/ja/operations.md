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

## 4. 縮退運転と復旧

dependency障害は、単一のledger-backed state machineで表現します。

| State | 許可される動作 |
|---|---|
| `NORMAL` | 宣言済みworkflowと通常guardrailを適用します。 |
| `DEGRADED` | 観測と安全なresponseを維持します。変更操作にはone-shot宣言が必要で、active adaptive envelope内だけを許可します。merge、deploy、publishは禁止します。 |
| `RECOVERING` | 観測とrecovery protocolだけを許可します。probe成功だけでは解除せず、全tainted artifactが宣言済みrevalidation scopeを通る必要があります。 |
| `HALTED` | 通常作業を停止します。既存のreceipt-backed HALT releaseを正とし、envelopeの失効・消失からeffective HALTを導出する場合もあります。 |

`orgforge operational-state status` はcircuit、所有session、taint、recovery状態を表示します。
recovery authorityとcooldownは`constitution.yaml`で宣言し、stale sessionからの解除は拒否します。
`project --target otel|github-checks`は、別のhealth scoreを作らず同じstate名と件数を外部へ投影します。

acting schedulerを有効にする前に、次を実行します。

```bash
orgforge resilience-exercise reviewer-outage --expect GREEN
```

決定的fixtureは、networkや実repositoryへのwriteを使わず、検知、縮退、独立failover、half-open
probe、taint再検証、circuit close、`NORMAL`復帰を証明しなければなりません。
別のfalse-GREEN fixtureでは、テストがGREENでも変異のpostconditionが成立していなければ
skeptic intakeが拒否することを検証できます。

```bash
orgforge resilience-exercise false-green-mutation --expect GREEN
```

reviewer failoverではなくprovider停止時のcontainmentを検証するには、次を実行します。

```bash
orgforge resilience-exercise provider-outage --expect GREEN
```

`DEGRADED`を維持し、未検証のprovider代替とmergeを拒否し、retry budgetが尽きたときは
人間へ判断を返さなければなりません。

livenessの相関を検証するには、次を実行します。

```bash
orgforge resilience-exercise heartbeat-correlation --expect GREEN
```

`repeated-failure-learning` は、別々の候補で同じ失敗が繰り返されたときに production の
learning organ がエスカレーションし、doctrine への引き渡しコマンドを出すことを確認します。
役割や doctrine の恒久変更は自動では行わず、人間の判断と bounded microexperiment を残します。

```bash
orgforge resilience-exercise repeated-failure-learning --expect GREEN
```

DR verifierへ依存関係の事実だけをexportし、OrgForge側でshared-fateを判定しない演習は次です。

```bash
orgforge resilience-exercise shared-fate-observation --expect GREEN
```

結果はdeclared-equal、declared-different、unknownと欠測だけを含み、独立性判定、support edge、
score、recovery claimは生成しません。意味論の判定はDR verifierが行います。

ledger probeが正常でも、duplicateまたはstaleなheartbeatは`ATTENTION`のままです。

無人運転をread-only-firstで始める場合は、決定的なmachine tickだけを登録します。

```bash
integrations/claude-code/scheduler-install.sh --role supervisor --cycles tick
```

macOSでは`--backend auto`がlaunchd、それ以外ではcronを使います。bounded smoke runが対応する
`tick_planned` receiptを書き、backend readbackが成功して初めてinstall完了です。
`scheduler-status.sh --root "$ORG_LEDGER_ROOT"`で確認できます。persistentな`work`と`discover`は
現在fail closedです。receiptを検証するexecutor adapterが入るまでは、acting周期をattendedな
harness loopだけで実行します。

## 5. Effect cap

destructive operation、external write、infrastructure change、file mutationを上限で制御します。
すべてのshell commandを課金する仕組みではなく、runawayを止めるための仕組みです。

永続設定はconstitutionをsource of truthにします。環境変数はdevelopment overrideです。

## 6. Productionと実資産

実際の権限はhost境界へ置きます。

- CI protected environment
- branch protection
- deployment approval
- cloud IAM
- external secret storage
- harness sandboxとtool permission

orgforgeは統制が出した判断と証拠を記録します。platformのroot credentialを保持・再実装しません。

## 7. Failure handling

- 継続が不可逆effectを生む場合、control stateを読めなければfail-closed
- check失敗は理由を報告し、違う理由の拒否を合格にしない
- write失敗をcontrol成功として報告しない
- exact retryでdurable decisionを重複させない
- 実orgを破壊的test fixtureにしない

## 8. 非サポートのseparate-UID writer実験

通常運用でprivileged writer-install commandを実行しません。別UID writer codeがcandidateや
historyに存在しても実験扱いで、supported productの外です。release、Quickstart、
local development、通常のunattended runには不要です。
