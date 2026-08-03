# Platform adapter contracts

This document narrows the remaining platform roadmap issues (#40--#44). These
adapters are observation and projection boundaries. They are not additional
decision engines and they do not extend the semantics of Delegation
Resilience.

## Non-negotiable boundary

OrgForge must not derive or assert any of the following:

- the meaning of `supports`;
- a `shared-fate` result;
- `SUPPORTED` from a graph shape;
- a DR recovery claim from an OrgForge `recovered` state; or
- an OrgForge score from a DR verifier result.

Missing or unverifiable information is preserved as missing or
`not_demonstrated`. An adapter failure is fail-closed and produces no partial
decision artifact.

## Bounded roadmap slices

### #40 — Spec Kit / BMAD artifacts

Import is limited to an immutable source artifact: bytes, digest, sourceRef,
producer, and an explicit mapping version. The artifact is opaque to OrgForge.
No phase completion, approval, ownership, recovery, or DR edge is inferred
from Markdown or JSON content. Semantic validation remains with the producer
or an explicitly invoked external verifier.

### #41 — backend SPI

The first SPI is a fake adapter used by contract tests. It exposes only
deterministic lifecycle, observation, and error behavior. Runtime scheduling,
retry policy, and admission remain outside the SPI until a real second backend
exists. A backend cannot produce DR claims.

### #42 — OpenTelemetry

The exporter correlates ledger event IDs with trace/span IDs and source
artifact digests. It may include timestamps, invocation metadata, and explicit
missingness. It emits no resilience score, shared-fate decision, supports edge,
or recovery claim. Redaction and absent-correlation behavior are tested.

### #43 — GitHub Checks

Checks are a projection sink. They publish phase/gate/evidence presence and
links, including unknown and not-demonstrated states. A Check conclusion is
never treated as an independent admission or DR verdict; the ledger and
external verifier remain authoritative.

### #44 — OPA / Cedar

The adapter serializes a declared policy input and records the external PDP
decision, issuer, policy digest, and request/response provenance. OrgForge does
not reimplement policy semantics or translate a PDP result into a local score,
recovery claim, supports, or shared-fate result. Timeout, malformed response,
and issuer mismatch fail closed.

## Evidence contract shared by all adapters

Every exported item must carry a stable sourceRef and the digest of the source
artifact used to produce it. Inputs are read-only. Serialization is canonical
and deterministic. A consumer can independently reproduce the bytes and
verify the source binding without importing OrgForge's working tree.

The adapter reports what was observed, what was absent, and what was delegated.
It does not claim that an export is proof of recovery. The purpose is to make
delegated work explainable and reproducible under change, not to manufacture a
new assurance signal.

