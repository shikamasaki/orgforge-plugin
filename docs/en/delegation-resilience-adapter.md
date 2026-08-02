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

## Assurance Graph export

The consumer lock now pins the separate DR Assurance Graph v0alpha1 profile while retaining the
transactional-action v0alpha2 packet profile. `graph` resolves only the pinned
`assurance-graph-v0alpha1` tag object and commit, imports from its path-safe archive, checks the
consumer-held schema and verifier digests, and runs the standalone DR verifier before emitting any
output. A schema/verifier or digest mismatch emits no partial artifact.

The current mapping is deliberately minimal and source-bound:

| OrgForge evidence | Candidate graph element | Required treatment |
| --- | --- | --- |
| actor identity and role record | `actor` | stable mapping plus source artifact digest |
| declared critical function / intent | `intent` or `capability` | declaration only; never inferred support |
| exercise attempt and fault receipt | `attempt` / `exercise` | observed conditions and bounded outcome |
| ledger or exercise observation | `evidence` | epistemic status and sourceRef |
| attestation or signed packet | `attestation` / `artifact` | digest-bound opaque source |
| declared dependency or seam | `dependency` | only when explicitly present in source |

The adapter currently emits only the explicit reviewer-outage `exercise`, its observed report
`evidence`/`artifact`, and the schema-defined `produces_artifact` relationship. It emits no actor,
claim, capability, dependency, external effect, or inferred edge when the OrgForge source does not
declare one. Missing evidence, unsupported edge types, duplicate IDs, dangling references, graph
digest changes, and mapping omissions fail closed in the pinned DR verifier. Graph verification
leaves recovery capability `not_demonstrated`; graph existence is never a recovery claim.

This is intentionally a design boundary, not a new OrgForge assurance claim. The purpose is to
make evidence, dependencies, external effects, and recoverability explainable with tamper
resistance and reproducibility—not to treat the existence of a graph as a guarantee.

The adapter tests duplicate/invalid JSON and digest failures at the trust boundary, deterministic
byte-identical regeneration, source immutability, standalone verification, and the DR verifier's
duplicate/dangling/mutation checks. `GRAPH_VERIFIED` only means the derived graph is internally
valid and reproducible; it does not demonstrate recovery capability or human takeover.
