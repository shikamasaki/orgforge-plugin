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

## Assurance Graph status

The current OrgForge adapter exports the v0alpha2 packet only. It does not yet generate an
Assurance Graph. The Graph profile is a separate, formally pinned DR artifact; its reference lock
is `integrations/delegation-resilience/assurance-graph-v0alpha1.lock.json`.

That lock binds the `assurance-graph-v0alpha1.1` tag object, commit, schema digest, and standalone
Graph verifier code digest. It is a consumer-held reference for a future one-way export and does
not claim that OrgForge currently conforms to the Graph profile.

When Graph export is implemented, it must remain derived from OrgForge evidence, fail closed on
missing or contradictory mappings, and never treat `GRAPH_VERIFIED` as recovery capability,
human takeover, deployment approval, or authorization. Until an export and independent exercise
exist, all recovery capability remains `NOT_DEMONSTRATED`.
