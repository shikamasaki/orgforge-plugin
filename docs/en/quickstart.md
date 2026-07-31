# Quickstart

This quickstart runs the supported orgforge workflow. It requires no daemon, sudo installation,
separate UID, private-key infrastructure, or privileged writer setup.

## 1. Install

In Claude Code:

```text
/plugin marketplace add <owner>/orgforge-plugin
/plugin install orgforge-plugin@orgforge-plugin
/reload-plugins
```

For a checkout-based test:

```bash
echo "your prompt" | claude -p \
  --plugin-dir integrations/claude-code \
  --allowedTools "Bash,Write,Agent"
```

After changing neutral source files, regenerate and check both bundles:

```bash
integrations/claude-code/build.sh
integrations/codex/build.sh
integrations/claude-code/build.sh --check
integrations/codex/build.sh --check
python3 -m pytest tests/ -q
```

## 2. Found or adopt an organization

For a new organization:

```text
/orgforge-plugin:org-init <name> ja
/orgforge-plugin:org-found <RFP or brief>
/orgforge-plugin:org-decompose
```

For an existing repository, use `org-adopt` instead of `org-found`:

```text
/orgforge-plugin:org-adopt <remaining requirements>
```

`org-adopt` performs local setup, reads the existing implementation, writes the minimal
organization and architecture, records the current debt baseline, and runs its readiness doctor in
one workflow. GitHub Issue decomposition is optional after adoption.

`org-found` stops for human scope approval. The human-held purpose and irreversible decision line
are not delegated.

## 3. Verify the normal guardrail boundary

```text
/orgforge-plugin:org-verify-guards
```

The supported claim is that enabled host hooks mediate normal agent tool calls. The host owner can
disable or replace those hooks and is part of the trusted computing base.

## 4. Start work

```text
/orgforge-plugin:org-start
/orgforge-plugin:org
```

The running flow is:

```text
claim → requirements → design → implement → test → integrate → deploy → operate
```

Each positive transition requires the prior phase and its recorded judgment. A gate or skeptic
returns a verdict, reasoning, evidence, and accepted risk; the plumbing records it.

## 5. What the supported guarantees mean

- A signed local receipt is `attested`, not externally `authenticated`.
- `adaptive` detects the running Claude Code or Codex host and uses the other product for
  `cross-harness` review when available.
- With one subscription, it explicitly falls back to pseudo `same-harness` gate/skeptic roles. That
  keeps the workflow usable but does not claim a second model lineage.
- The ledger hash chain detects rewriting; it does not make local files immutable.
- `process_mediated` means the enabled harness and hooks enforce the normal path.
- Separate-UID writer isolation is not required and is not part of this quickstart.

For production assets, keep credentials and irreversible authority in the host platform:
protected CI environments, branch protection, deployment approvals, sandbox policy, and external
secret storage.
