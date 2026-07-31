# Architecture

## 1. The load-bearing choice

orgforge ships no agent execution engine. An existing harness supplies:

- the model interaction loop;
- tool execution and mediation;
- subagents;
- scheduling;
- sandboxing;
- CI/CD integration.

orgforge supplies the missing organizational layer:

- declarative organization and constitution;
- role projection into each harness;
- the forced SDLC mold;
- ledgered decisions and evidence;
- static lint and live hooks.

This is the R0 boundary: use existing runtime machinery instead of rebuilding it.

## 2. Neutral core and projections

```text
template/ + tools/ + integrations/common/
                  |
                  +-- integrations/claude-code/
                  |
                  +-- integrations/codex/
```

The neutral files are the source of truth. Each integration bundles them so the installed plugin is
self-contained. Bundle checks fail when a projection drifts from the neutral source.

## 3. Two coupled lifecycles

The organization lifecycle:

```text
found → project roles → operate → observe → adapt
```

The product lifecycle:

```text
requirements → design → implement → test → integrate → deploy → operate
```

The ledger connects them. Product outcomes trigger organizational learning and reallocation; the
organization's current structure determines how the next product increment moves.

## 4. Enforcement boundary

The live hook can block a normal tool call. The ledger can reject an invalid phase transition or
missing prior judgment. Static lint can reject an internally contradictory organization.

The trusted base includes:

- the host harness;
- enabled hook configuration;
- the local filesystem;
- the human or administrator who can modify them.

orgforge constrains agents operating through that base. It does not defend the base from its owner.

## 5. Independent assurance axes

| Axis | Supported core |
|---|---|
| Identity account | verified receipt: `attested` |
| Review quality | decorrelated model lineage: `cross-harness` |
| Writer path | host mediation: `process_mediated` |
| History | hash-chain: tamper-evident |

No axis may borrow a guarantee from another. A separate writer does not isolate a judge. A different
model does not authenticate a person. A valid signature does not prove hostile same-UID exclusion.

## 6. Why separate-UID writer isolation is not adopted as core

A separate-UID writer protects only writer assets while adding a daemon, privileged installation,
OS-specific service management, dependency provisioning, socket lifecycle, migration, and rollback.
It does not protect judge keys, host configuration, deployment credentials, or external effects.

That cost is not justified by the product's supported threat model. If a deployment requires
adversarial asset protection, the host platform must provide the boundary. The repository may retain
experimental writer-isolation code, but it is not a supported dependency or a core release gate.
