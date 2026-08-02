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

## 4. Graceful degradation and recovery

Dependency failure is represented by one ledger-backed state machine:

| State | Permitted behavior |
|---|---|
| `NORMAL` | Declared workflow and ordinary guardrails apply. |
| `DEGRADED` | Observation and safe responses remain available. A mutating action needs a one-shot declaration and must be inside the active adaptive envelope. Merge, deploy, and publish are forbidden. |
| `RECOVERING` | Only observation and the recovery protocol remain. A successful probe is not enough: every tainted artifact must pass its declared revalidation scope. |
| `HALTED` | Normal work is stopped. Existing receipt-backed HALT release remains authoritative; an expired or missing envelope can also derive an effective HALT. |

`orgforge operational-state status` shows circuits, the owning session, taint, and recovery state.
Recovery authority and cooldown come from `constitution.yaml`; a stale session cannot release the
state. `project --target otel|github-checks` preserves the same state names and counts for external
systems instead of inventing a separate health score.

Before enabling an acting scheduler, run:

```bash
orgforge resilience-exercise reviewer-outage --expect GREEN
```

The deterministic fixture must prove detection, degradation, independent failover, half-open probe,
taint revalidation, circuit closure, and return to `NORMAL` without network or real-repository writes.
Run the separate false-GREEN fixture to prove that a passing test cannot admit a mutation whose
postcondition was never established:

```bash
orgforge resilience-exercise false-green-mutation --expect GREEN
```

To verify provider containment rather than reviewer failover, run:

```bash
orgforge resilience-exercise provider-outage --expect GREEN
```

It must retain `DEGRADED`, deny an unverified provider substitution and merge, and return the
retry decision to a human when the declared retry budget is exhausted.

To exercise liveness correlation, run:

```bash
orgforge resilience-exercise heartbeat-correlation --expect GREEN
```

The repeated-failure-learning exercise feeds three distinct candidate failures through the
production learning organ. It must escalate the recurring cause and print a doctrine handoff,
while leaving permanent role/doctrine changes to a human and a bounded microexperiment.

```bash
orgforge resilience-exercise repeated-failure-learning --expect GREEN
```

Duplicate or stale heartbeats remain `ATTENTION` even when a single ledger probe is healthy.

For unattended read-only-first operation, install the deterministic machine tick:

```bash
integrations/claude-code/scheduler-install.sh --role supervisor --cycles tick
```

On macOS `--backend auto` uses launchd; elsewhere it uses cron. Installation is complete only after a
bounded smoke run writes a matching `tick_planned` receipt and backend readback succeeds. Inspect it
with `scheduler-status.sh --root "$ORG_LEDGER_ROOT"`. Persistent `work` and `discover` currently fail
closed; run those acting cycles only through an attended harness loop until a receipt-verifying
executor adapter exists.

## 5. Effect caps

Caps bound destructive operations, external writes, infrastructure changes, and file mutations.
They are designed to stop runaway behavior, not to meter every shell command.

Use the constitution as the persistent source of truth. Environment variables are development
overrides, not the normal configuration mechanism.

## 6. Production and real assets

Keep actual authority at the host boundary:

- CI protected environments;
- branch protection;
- deployment approvals;
- cloud IAM;
- external secret storage;
- harness sandbox and tool permissions.

orgforge should record the decision and evidence that those controls produced. It should not hold
or recreate the platform's root credentials.

## 7. Failure handling

- An unreadable control state fails closed when continuing could create an irreversible effect.
- A failed check must report why it failed; a rejection for the wrong reason is not evidence.
- A failed write must not be reported as a successful control decision.
- Exact retries must not duplicate durable decisions.
- The real organization is never used as a destructive test fixture.

## 8. Unsupported separate-UID writer experiment

Do not run privileged writer-install commands as part of normal operation. Separate-UID writer code,
if present in a candidate or historical change, is experimental and outside the supported product.
It is not required for release, Quickstart, local development, or ordinary unattended runs.
