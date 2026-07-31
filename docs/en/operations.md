# Operations

## 1. Normal operation

Run orgforge on the existing host harness with:

- hooks enabled;
- the organization and constitution committed;
- the ledger discoverable from the working directory;
- protected CI/CD for deployment;
- human approval for charter and irreversible actions.

No privileged daemon or separate writer UID is required.

## 2. Daily flow

```text
intake → claim → work → gate → skeptic → integrate → deploy → operate
```

The tools handle plumbing and recording. Roles make judgments. A judgment must include:

- verdict;
- reasoning;
- executed evidence;
- standard applied;
- alternatives considered;
- accepted residual risk.

## 3. HALT

HALT is an operational brake. While active, normal work is blocked and only observation, verification,
safe repair, and authorized release paths remain.

Release requires a separately registered approver, a bound asymmetric receipt, and recovery evidence.
This is workflow separation and attestation, not hostile key custody.

If recording the release fails, HALT remains active.

## 4. Effect caps

Caps bound destructive operations, external writes, infrastructure changes, and file mutations.
They are designed to stop runaway behavior, not to meter every shell command.

Use the constitution as the persistent source of truth. Environment variables are development
overrides, not the normal configuration mechanism.

## 5. Production and real assets

Keep actual authority at the host boundary:

- CI protected environments;
- branch protection;
- deployment approvals;
- cloud IAM;
- external secret storage;
- harness sandbox and tool permissions.

orgforge should record the decision and evidence that those controls produced. It should not hold
or recreate the platform's root credentials.

## 6. Failure handling

- An unreadable control state fails closed when continuing could create an irreversible effect.
- A failed check must report why it failed; a rejection for the wrong reason is not evidence.
- A failed write must not be reported as a successful control decision.
- Exact retries must not duplicate durable decisions.
- The real organization is never used as a destructive test fixture.

## 7. Unsupported separate-UID writer experiment

Do not run privileged writer-install commands as part of normal operation. Separate-UID writer code,
if present in a candidate or historical change, is experimental and outside the supported product.
It is not required for release, Quickstart, local development, or ordinary unattended runs.
