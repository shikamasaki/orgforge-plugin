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

`tools/assurance_graph_export.py export` is a second one-way adapter, separate from the v0alpha2
packet exporter, which stays byte-for-byte unchanged. It reads the same three OrgForge inputs plus
an explicit `--observed-at` UTC timestamp (the report protocol records no time of its own), and
emits a graph packet: `graph.json`, the locked DR verifier's `verification-result.json`, the
source artifacts, and a standalone copy of the pinned Graph verifier.

The lock is `integrations/delegation-resilience/assurance-graph-v0alpha1.lock.json`. It binds the
`assurance-graph-v0alpha1.1` tag object, commit, schema digest, and standalone Graph verifier code
digest — the same values DR's own release lock publishes at that commit. Export resolves the tag
references against the DR checkout, then runs the Graph verifier only from a path-safe
`git archive` of the locked commit in a fresh subprocess; schema and verifier code digests are
recomputed from that archive and must match the lock, or no output is written.

Mapping rules, in addition to the v0alpha2 boundary above:

- Nodes and edges read directly from a source artifact (the exercise, its report evidence, the
  constitution artifact, the reviewer and harness dependencies, the declared shared-fate and
  depends_on relations) are `observed`.
- Everything the adapter itself introduces — the recovery claim node and every `supports` /
  `depends_on` edge into it — is `derived`, never `observed`. The claim requests only
  `NOT_DEMONSTRATED`.
- The locked verifier therefore keeps the claim at `NOT_DEMONSTRATED` for two independent
  reasons (derived support, shared-fate dependencies). The exporter additionally fails closed if
  any claim result requests or verifies anything else.

`GRAPH_VERIFIED` only proves graph structure, source-artifact digests, references, and
reproducibility. It is not recovery capability, human takeover, deployment approval, or
authorization; those remain `NOT_DEMONSTRATED` until a facilitated human drill and a real-world
recovery exercise exist.
