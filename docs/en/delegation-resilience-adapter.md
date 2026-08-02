# Delegation Resilience v0alpha2 export adapter

`tools/delegation_resilience_export.py export` is a one-way adapter. It reads a completed
OrgForge reviewer-outage exercise report, the constitution, and the scenario; it never reads or
writes an OrgForge ledger, and it never changes those input artifacts.

The fixed lock in `integrations/delegation-resilience/v0alpha2.lock.json` binds the DR tag object,
commit, and verifier code digest. Export resolves the tag references, then imports only from a
path-safe `git archive` of the locked commit in a fresh subprocess. The caller's HEAD, tracked,
staged, untracked, ignored, and stale-cache files therefore cannot affect the DR modules. The
standalone contract test supplies the lock-held code digest as its expected value; the packet's
measured environment digest remains platform-specific evidence rather than an independent code
pin.

## Mapping boundary

| OrgForge input | DR packet representation | Meaning |
| --- | --- | --- |
| exercise report | opaque artifact + source digest | A recorded deterministic exercise observation |
| constitution | opaque artifact + source digest | The declared human decision line and resilience contract |
| reviewer-outage scenario | opaque artifact + source digest | Fault schedule and bounded exercise context |
| adapter lock | mapping artifact | DR identity and `orgforge-reviewer-outage/v0alpha1` mapping version |

No v0alpha2 Transactional Action recovery claim is mapped from these inputs. The packet's claim
mapping is explicitly `none`, and every claim result remains `not_demonstrated`/`UNKNOWN`.
`PACKET_VERIFIED` therefore only proves packet integrity, signature/trust processing, and
reproducibility—not recovery capability, human takeover, deployment approval, or DR conformance
of the OrgForge organization.

The exported standalone verifier is copied from the pinned DR checkout and contains neither
OrgForge imports nor exercise execution code.

## Assurance Graph status: fail-closed stub

The locked DR v0alpha2 commit does not publish a machine-readable Assurance Graph schema, edge
semantics, or graph verifier contract. OrgForge therefore does **not** invent a graph format. The
`tools/delegation_resilience_export.py graph` command fails closed and emits no partial artifact
until a future consumer-held lock declares both `assuranceGraph.schemaRef` and
`assuranceGraph.verifierCodeDigest`.

The intended mapping, once DR defines that contract, is one-way and source-bound:

| OrgForge evidence | Candidate graph element | Required treatment |
| --- | --- | --- |
| actor identity and role record | `actor` | stable mapping plus source artifact digest |
| declared critical function / intent | `intent` or `capability` | declaration only; never inferred support |
| exercise attempt and fault receipt | `attempt` / `exercise` | observed conditions and bounded outcome |
| ledger or exercise observation | `evidence` | epistemic status and sourceRef |
| attestation or signed packet | `attestation` / `artifact` | digest-bound opaque source |
| declared dependency or seam | `dependency` | only when explicitly present in source |

Edges, stable IDs, and recovery-claim results must come from the DR schema and verifier. Missing
evidence, unsupported edge types, duplicate IDs, dangling references, graph digest changes, and
mapping omissions must all fail closed. A successful packet or future graph verification must
leave recovery capability `not_demonstrated` unless DR independently verifies the required claim.

This is intentionally a design boundary, not a new OrgForge assurance claim. The purpose is to
make evidence, dependencies, external effects, and recoverability explainable with tamper
resistance and reproducibility—not to treat the existence of a graph as a guarantee.

The graph-specific negative/contract matrix (duplicate node or edge ID, dangling `sourceRef`,
unmapped evidence, graph mutation digest mismatch, byte-identical regeneration, and standalone
verification) is intentionally gated on that DR-published schema. The adapter already exercises
the trust boundary independently: fixed-object archive import, dirty/untracked/ignored/cache
shadow isolation, strict JSON, consumer-held verifier digest mismatch, and no partial output.
