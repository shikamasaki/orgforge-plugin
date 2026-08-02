# Assurance Model

## 1. Supported threat model

Agents may be wrong, incomplete, overly agreeable, stale, or careless, but they are not modeled as
hostile processes attacking their own host.

Core controls:

- explicit roles and contracts;
- maker/checker separation in the workflow;
- gate and skeptic review;
- phase-order enforcement;
- reasoning and evidence records;
- HALT and effect caps;
- reproducibility and bundle checks.

orgforge does not provide hostile-process containment, credential custody, or an immutable local
ledger. Deployments that affect production, funds, publication, credentials, or regulated assets
must obtain those protections from the host platform. They are deployment responsibilities, not
orgforge features or core release gates.

## 2. Identity labels

| Label | Exact meaning |
|---|---|
| `claimed` | supplied by the caller |
| `observed` | observed by the host/writer, but not a judgment identity |
| `attested` | receipt and bound fields verified against a registered key |
| `authenticated` | reserved for externally enforced custody and caller authentication |

A locally readable asymmetric private key can produce strong tamper evidence, but it does not create
an adversarial principal boundary. Local receipts therefore stop at `attested`.

## 3. Reviewer independence

`cross-harness` means the work was reviewed by a different model lineage. Its value is reduced
correlation: a second model family has different blind spots and can catch errors missed by the
maker and first gate.

It does not mean:

- a separately authenticated human;
- an unreachable signing key;
- a separate OS security principal;
- resistance to a hostile same-UID caller.

Review diversity remains valuable as a quality control, not an identity security claim.

`tools/shared_fate.py` makes this limitation explicit as an axis vector rather than a single
independence score. A task policy declares `must_differ`, `may_share`, and `must_match` axes;
missing values remain `unknown` and are never counted as different. This first step is a pure
evidence projection. The joint-admission writer must consume the same policy before a vector can
authorize a joint result.

`adaptive` routing derives the primary from the running agent (`Claude Code` or `Codex`), not from a
static preference in `organization.yaml`. If the opposite product is locally available it selects
that product. If only one product is available it resolves to `same-harness`, emits a degradation
notice, and records no cross-harness claim. Codex uses its offline login status; macOS Claude Code
uses the presence of its Keychain credential without reading the secret. Explicit
`ORGFORGE_CLAUDE_AVAILABLE=false` and corresponding Codex overrides cover other platforms and
special authentication setups.

## 4. Record integrity

The ledger is append-only by convention and hash-chained. The chain detects modification and makes
the recorded sequence replayable. It does not make a caller-writable filesystem immutable.

Git history, backups, CI records, and host storage controls complement the ledger.

## 5. Separate-UID writer isolation

Separate-UID writer isolation is **not adopted as a supported core feature**.

Reasons:

- it addresses a risk outside the supported product guarantees;
- it introduces substantial OS-specific runtime and operational complexity;
- it protects only writer assets;
- stronger asset boundaries already belong to the host environment;
- making it mandatory would violate the existing-harness/no-new-runtime product constraint.

Experimental code or historical runbooks do not constitute a supported guarantee. Do not claim
`separate_uid` unless a deployment independently measures it, and do not treat it as judge custody.

## 6. Release claims

An orgforge release may claim:

- enforced workflow under enabled hooks;
- recorded maker/gate/skeptic separation;
- decorrelated cross-harness review;
- attested local receipts;
- tamper-evident history;
- human-held irreversible authority.

It may not claim:

- hostile same-UID containment;
- authenticated local judge identity;
- cryptographic independence between local agents;
- immutable local ledger storage;
- separate-UID writer isolation by default.
