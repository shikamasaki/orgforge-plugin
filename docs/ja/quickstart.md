# Quickstart

このQuickstartはorgforgeのsupported workflowを動かします。daemon、sudo install、別UID、
秘密鍵基盤、privileged writerの設定は不要です。

## 1. Install

Claude Codeで:

```text
/plugin marketplace add <owner>/orgforge-plugin
/plugin install orgforge-plugin@orgforge-plugin
/reload-plugins
```

checkoutを直接使う試験:

```bash
echo "your prompt" | claude -p \
  --plugin-dir integrations/claude-code \
  --allowedTools "Bash,Write,Agent"
```

neutral sourceを変更した場合:

```bash
integrations/claude-code/build.sh
integrations/codex/build.sh
integrations/claude-code/build.sh --check
integrations/codex/build.sh --check
python3 -m pytest tests/ -q
```

## 2. orgを設立または既存repoへ導入

新規org:

```text
/orgforge-plugin:org-init <name> ja
/orgforge-plugin:org-found <RFPまたはbrief>
/orgforge-plugin:org-decompose
```

既存repo:

```text
/orgforge-plugin:org-adopt <残りの要求>
```

`org-adopt`はlocal state準備、既存実装の読解、最小organizationとarchitectureの作成、
現在の負債baseline、readiness doctorまでを1 workflowで完了します。GitHub Issueへの分解は
導入後の任意操作です。

`org-found`はscopeの人間承認で停止します。purposeと不可逆な判断線は人間に残します。

## 3. 通常のguardrail境界を確認

```text
/orgforge-plugin:org-verify-guards
```

保証するのは、有効なhost hookを通る通常のagent tool callが制御されることです。hookを無効化・
交換できるhost ownerはtrusted computing baseに含まれます。

## 4. 運用開始

```text
/orgforge-plugin:org-start
/orgforge-plugin:org
```

成果物は次の順序を通ります。

```text
claim → requirements → design → implement → test → integrate → deploy → operate
```

positive transitionには直前phaseと記録済みjudgmentが必要です。gateとskepticはverdict、
reasoning、evidence、accepted riskを返し、toolが記録します。

## 5. サポートする保証の意味

- local署名receiptは`attested`であり、外部`authenticated`ではない
- `adaptive`は実行中のClaude CodeまたはCodexを検出し、利用可能なら反対側を
  `cross-harness` reviewに使う
- 片方だけ利用する場合はpseudo `same-harness`のgate/skepticへ明示的に縮退する。workflowは
  維持されるが、別model系統によるreviewとは主張しない
- hash chainは改竄を検知するがlocal fileをimmutableにはしない
- `process_mediated`は有効なharnessとhookが通常経路を制御するという意味
- separate-UID writer隔離は不要で、このQuickstartには含めない

production資産を扱う場合、credentialと不可逆権限はCI protected environment、branch
protection、deployment approval、sandbox policy、external secret storageへ置きます。
