# 07 — Doctrine & Knowledge: Watching the World, Retraining the Professionals

> The organs so far let the organization learn from **its own experience** (the ledger).
> This document adds the organ that lets it learn from **the world**: a continuous watch
> on the external environment (markets, tools, competitors, research), distilled into a
> role-scoped knowledge base, and delivered as each role's **doctrine** — its current
> normative playbook (べき論: *what good practice now is*) — loaded into context on every
> cycle. In human-org terms this is boundary spanning + absorptive capacity + training;
> in Mintzberg's terms it upgrades the org's coordination from supervision toward
> **standardization of skills**.

---

> **Framing (read before the pipeline): this organ is delegated, not a runtime.** Like
> every other organ, the knowledge organ is realized by departments running on **host
> harnesses** (docs/09 §1, docs/01 R0) — the curator and the gate are departments, not
> processes this repo builds. "The pipeline" below describes **work products and their
> routing** — who produces which artifact, and which files land where before a role's
> harness launches — not an execution engine to implement. Where the text says doctrine is
> "loaded into context," that is the **projection writing the current doctrine file into
> the working directory** before launch (docs/09 §2); where it says the curator scans "on a
> cadence," that cadence is a schedule the **host scheduler** realizes (cron / CI trigger /
> the harness's own loop), declared as intent — this repo ships no scheduler (docs/09 §4).

## 1. Two memories, one new layer

An agent organization needs two kinds of memory, and they must not be conflated:

| | **Ledger** (exists since Organ 5) | **Knowledge base** (this organ) |
|---|---|---|
| Records | what *this org* did and learned (episodic) | what *the world* says and how it changed (semantic) |
| Source | internal, trusted by construction | **external, untrusted by default** |
| Form | append-only events | curated items with provenance |
| Reaches a role as | context pack (live state) | **doctrine** (distilled norms) |

**Doctrine** is the layer between the knowledge base and the role: a small, versioned,
per-role document stating what the role should currently believe about its domain and how
it should therefore work — techniques that are now standard, sources that are now stale,
thresholds the market has moved. It is part of the profile family (like ROLE.md) but on a
faster clock: the profile says *what the job is*; the doctrine says *what good practice
in that job currently looks like*. Every cycle's context pack loads: purpose + intent
(docs/08) + contract + **current doctrine** — where "loads" means the projection writes
these files into the role's working directory before its harness launches (docs/09 §2),
not a runtime that streams them in. A role never acts on last quarter's world without
knowing it.

### Why doctrine, organizationally

Mintzberg's professional bureaucracy coordinates by **standardization of skills**: you
don't supervise a surgeon's every cut; you train the surgeon and trust the training. For
agent orgs this is the cheapest span-widener available (docs/02 §3): a supervisor whose
reports carry current, checked doctrine needs fewer corrections per cycle, so effective
span rises and the hierarchy stays flat. Doctrine updates are, literally, **retraining
the professional** — and Cohen & Levinthal's absorptive-capacity result explains why the
knowledge base must be cumulative: an org can only absorb new external knowledge in
proportion to the related knowledge it already holds. A KB that is discarded and rebuilt
per question absorbs nothing.

---

## 2. The pipeline: watch → admit → distill → load

```
external sources ──► curator (organic)          ──► gate (mechanistic)     ──► doctrine store ──► context pack
                     scans on cadence,               admits/rejects against     versioned,          loaded EVERY
                     files intelligence items        provenance & doctrine      per-role,           cycle, within
                     {source, date, confidence},     standard; charter-tier     TTL'd claims        the pack's
                     proposes doctrine diffs         for mechanistic roles                          context budget
```

1. **Watch (curator).** A boundary-spanning department (Tushman: the *gatekeeper* role),
   running like any department on a host harness, scans declared external sources **on a
   cadence** — a schedule the host scheduler realizes (cron / CI trigger / the harness's
   own loop), declared here as intent, not shipped as a scheduler (docs/09 §4) — and files
   **intelligence items** into the knowledge base. Every item carries provenance: source,
   retrieval date, confidence, and the role(s) whose doctrine it may affect. The curator is
   **organic** — what to watch and how to search is exploration — and it *proposes*; it
   never writes doctrine directly.
2. **Admit (gate).** External content is an **untrusted input channel** — the agent-org
   analog of prompt injection and data poisoning. Nothing external enters any role's
   always-loaded context without passing the mechanistic gate: provenance complete,
   claims checked against the doctrine standard, conflicts with existing doctrine
   surfaced rather than silently overwritten. This "gate" is not a runtime interceptor
   sitting on the wire: it is realized **structurally** — the projection routes curator
   output through the gate department before any admitted claim becomes a file the
   consuming role's harness loads (docs/09 §5). Untrusted-until-admitted is a property of
   *which files land where*, not of a live filter. **Doctrine diffs for mechanistic
   (control) roles are charter-tier** — the humans decide what the gate itself is taught,
   for the same reason they own the gate's profile.
3. **Distill (doctrine diff).** Admitted knowledge lands as a versioned diff to the
   target role's doctrine: small, claim-level, each claim carrying its provenance and a
   **review-by date** (TTL). Doctrine is retrieval-backed (RAG): the doctrine document
   holds the distilled norms and links into the KB, so a role can pull depth on demand
   (docs/08's pull principle) without the whole KB riding in every context window.
4. **Load (context pack).** The role's next cycle — the next time the host launches its
   harness on the schedule — starts with current doctrine in context, within the pack's
   context budget (docs/08 §3). "In context" is again the projection writing the current
   doctrine file into the working directory before launch (docs/09 §2), not a runtime
   assembling it live. Doctrine that outgrows its budget must be re-distilled, not
   truncated silently.

### 2.1 Loading is keyed by role — and there are two load paths

Doctrine is a **directory of per-role files** (`<root>/<role>.json`), so *which* brain a
session gets is decided entirely by **which role it is** — the `ORG_ROLE` a launch declares.
This is what keeps the field narrow-and-deep (docs/08 §1.1): the role name IS the scope of
the brain. Roles are named by trade, not by rank — `eng-manager`, `design-manager`,
`ui-worker`, `api-worker`, `db-worker` are five different brains, and a session loading one
loads only that one. Widen the naming (a single `worker` brain for every trade) and the
specialist thins into a generalist; that is the failure this keying exists to prevent.

Because the harness's SessionStart hook only fires for a **top-level launch** (a fresh
`claude -p` / `codex exec` the host or a runner starts), there are two load paths, and a
department that spawns subordinates must use the right one:

- **Top-level launch → hook injection.** The host/runner sets `ORG_ROLE` + `ORG_DOCTRINE_ROOT`;
  `org_session_start.py` renders `<role>.DOCTRINE.md` and the harness prepends it. Automatic.
- **A spawned subordinate (in-process, via the Agent/subagent tool) does NOT inherit the
  hook.** So the spawning manager, *before* it spawns, builds the child's hand-off packet
  itself — `tools/handoff.py` — and prepends it to the child's task prompt. The packet has
  three parts (see §2.1.1): the child's **slice**, the **seam contract**, and the child's
  **brain scoped to that slice** (`doctrine.py render`, filtered to the child role). The child
  therefore starts holding **its own** role doctrine — the parent's broader brain does not
  leak down. This is a **manager duty**, wired into the manager profile the same way
  spec-driven delegation is.

Either path, the invariant holds: a session runs on the current, gate-admitted doctrine of
**its own role** — never a parent's, never last quarter's.

### 2.1.1 Fix the seam, not the axis (bound recombination, free decomposition)

A recursive org can decompose freely but must recombine cleanly — and the failure mode of
recursive splitting is not *how* work is cut but *the un-owned interface at the cut*: two
siblings each interpret a boundary the parent never pinned, and drift (Conway's law biting
inside the agent tree; Parnas: hide the volatile decision behind an interface). So the load-
bearing thing a manager fixes when it delegates is **not a global decomposition axis** — that
would force one taxonomy top-to-bottom when the right grouping changes by level (Thompson: the
tightest interdependence sits at a different place each level; a company splits by function but
an auth team splits by layer). It is the **seam contract** at each cut:

- **Inputs** the child receives and **Outputs** it must produce (the exact interface siblings
  and the parent integrate against) — a *hard* constraint the child may not renegotiate.
- **Owns / must-not-touch** files, and any **shared invariant** both sides honor.

The **axis** (how to classify the split — by feature, by layer, by phase) is chosen *locally*
by each manager for *its own* slice, derived from its doctrine (Parnas: cut to isolate the
decision most likely to change), and passed down only as advice. Fixing the axis globally is
redundant with the scoped doctrine and can even contradict it; fixing the **seam** is what
makes the pieces compose. Decomposition is free, recombination is bound. A manager that splits
emits a seam contract for **each** child and integrates against those outputs exactly; a child
that splits further does the same for its own children. (This is the design that survived an
adversarial review from organizational-theory, software-architecture, and multi-agent-systems
perspectives — all three rejected a fixed global axis in favor of per-level axis + fixed seam.)

**This is enforced, not merely asked.** A profile that only *requests* "use the hand-off tool"
gets loose compliance — an agent will hand-write a slice and skip the tool when it judges the
skip harmless (observed: a parallel enumeration whose outputs never merge). So the PreToolUse
hook gates the spawn tool itself (`ORG_REQUIRE_SEAM=1`): an `Agent`/`Task` spawn is **blocked**
unless its prompt carries a seam contract (a `handoff.py` packet) **or** an explicit
`INDEPENDENT:` declaration — a non-integrating fan-out whose outputs are never merged. That
distinction is the point: independence is a *legitimate* reason to skip a seam, so the gate asks
the manager to *declare* which case it is, rather than silently omitting the contract. Integrating
children get a seam; independent children get labeled; nothing spawns brain-of-drift by default.

The moves catalog gains `update_doctrine` (see template/moves.yaml); the constitution
gains the knowledge rules (template/constitution.yaml `knowledge:`).

### 2.2 Roles change; the brains are assets that follow (refound)

When the RFP or the work reveals the org is shaped wrong, the CEO/human may **refound** —
tear down the role structure and re-found with new roles, *assets intact* (docs/06 §4.4).
Doctrine is one of those assets: a role's accumulated brain is not discarded because the role
is renamed, split, or merged. `doctrine.py remap --map {old: new | [new,...]}` performs the
re-routing that `refound`'s `doctrine_remap` declares and `org_lint`'s
`doctrine_remap_covers_every_live_claim` checks:

- **Rename / merge** (`old -> new`): every live claim moves to the new role.
- **Split** (`old -> [n1, n2]`): each claim routes to the target(s) named in its
  `affected_roles` — the scope tag decides where each piece of the brain lands.
- **Orphan guard:** a live claim that maps to no target **blocks the refound** (exit 2) rather
  than vanishing; `--allow-orphans` instead surfaces them to `UNROUTED.json` for a human to
  place. No brain is ever silently lost — the same principle as "nothing external becomes
  doctrine without admission," run in reverse.

---

## 3. Failure modes (and who catches them)

- **Doctrine poisoning.** A hostile or wrong external source steers a role via its
  always-loaded context — the highest-leverage injection point in the whole org, which is
  exactly why admission is mechanistic and provenance is mandatory. This is enforced
  **structurally**, not by a runtime interceptor: for every org (Tier A) the projection
  guarantees curator output reaches a role's loaded files only after the gate department
  admits it — separation of duties realized as which files land in which working directory
  (docs/01 §5, docs/09 §5); for asset-touching orgs (Tier B) the **host environment** adds
  the sandboxing and custody the tier requires. Countermeasure: the gate's doctrine
  standard + the skeptic on any doctrine diff that would *loosen* a standard or contradict
  ledger experience.
- **Doctrine capture (self-serving doctrine).** A maker proposes doctrine for itself that
  weakens its own discipline ("current best practice is lighter verification"). Any
  doctrine diff touching a role's discipline block, admission-relevant thresholds, or a
  control role is **charter-tier**, not delegated — the two-layer law applied to
  knowledge.
- **Staleness.** Doctrine without TTLs rots silently and the org confidently applies last
  year's world. Every claim carries review-by; the `doctrine_stale` sensor fires the
  curator on expiry.
- **Bloat.** Doctrine that grows unboundedly eats the context budget and buries the
  contract (attention poverty, docs/08). The budget is the forcing function: over-budget
  doctrine must be re-distilled.
- **Silo.** Knowledge admitted for one role that another role needed — Conway's law on
  the KB. Countermeasure: intelligence items declare affected roles; the curator's
  contract includes cross-role routing; the divergence sensor catches duplicated
  discovery.

---

## 4. What stays honest

The Maker/Checker line runs through knowledge exactly as through work: **curator proposes,
gate admits, no role writes its own doctrine.** This line is held **structurally** — by
which department admits and which files the projection then writes into which working
directory (Tier-A separation of duties), backed for asset-touching orgs by the host
environment's custody and sandboxing (Tier B) — not by a runtime this repo builds
(docs/01 §5, docs/09 §5). The knowledge base, like the ledger, is custody-protected (no
agent owns its own record of what the world says). And doctrine is
subordinate to purpose: a doctrine claim can say *how* the market now works, never *what
the organization is for* — telos revision is Organ 1 and stays human (docs/06 §2.5).

---

## Sources

- Tushman, M. 1977 — "Special Boundary Roles in the Innovation Process," *ASQ*
  (boundary spanning / gatekeepers).
- Cohen, W. & Levinthal, D. 1990 — "Absorptive Capacity," *ASQ*.
- Nonaka, I. & Takeuchi, H. 1995 — *The Knowledge-Creating Company* (SECI;
  externalization of tacit knowledge — what distillation is).
- Polanyi, M. 1966 — *The Tacit Dimension*.
- Aguilar, F. 1967 — *Scanning the Business Environment* (environmental scanning).
- Mintzberg — standardization of skills (professional bureaucracy), as cited in
  docs/sources.md.

*Status: this document is a design for how the knowledge organ **maps onto host-run
departments** — the curator, gate, and doctrine store are departments a host harness
launches on a schedule, and "the pipeline" names their work products and routing, not a
runtime to build (docs/09 §1, docs/01 R0). The **doctrine store, admission gate, render,
and stale check are now running code** — [`tools/doctrine.py`](../tools/doctrine.py) — a
file-backed per-role store that enforces the invariants above: no anonymous doctrine
(mandatory provenance), untrusted-until-admitted (admit by the gate only, never the maker),
a review-by TTL surfaced by `stale`, and render-admitted-only within a token budget
(over-budget re-distills, never silent-truncates). What the tool does **not** ship is the
scheduler or the curator's watch itself — those are the host-run agents that *call* it on a
cadence (R0). The pipeline and its failure modes are this repo's synthesis; the
organizational anchors are the citations above. The untrusted-input treatment of external
knowledge is a security stance, not a theorem, and it is realized structurally (Tier A) or
by the host environment (Tier B), not by a bespoke interceptor — treat the whole organ as a
design hypothesis to verify against a running system.*
