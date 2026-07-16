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
(docs/08) + contract + **current doctrine**. A role never acts on last quarter's world
without knowing it.

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

1. **Watch (curator).** A boundary-spanning department (Tushman: the *gatekeeper* role)
   scans declared external sources on a cadence and files **intelligence items** into the
   knowledge base. Every item carries provenance: source, retrieval date, confidence, and
   the role(s) whose doctrine it may affect. The curator is **organic** — what to watch
   and how to search is exploration — and it *proposes*; it never writes doctrine
   directly.
2. **Admit (gate).** External content is an **untrusted input channel** — the agent-org
   analog of prompt injection and data poisoning. Nothing external enters any role's
   always-loaded context without passing the mechanistic gate: provenance complete,
   claims checked against the doctrine standard, conflicts with existing doctrine
   surfaced rather than silently overwritten. **Doctrine diffs for mechanistic (control)
   roles are charter-tier** — the humans decide what the gate itself is taught, for the
   same reason they own the gate's profile.
3. **Distill (doctrine diff).** Admitted knowledge lands as a versioned diff to the
   target role's doctrine: small, claim-level, each claim carrying its provenance and a
   **review-by date** (TTL). Doctrine is retrieval-backed (RAG): the doctrine document
   holds the distilled norms and links into the KB, so a role can pull depth on demand
   (docs/08's pull principle) without the whole KB riding in every context window.
4. **Load (context pack).** The role's next cycle starts with current doctrine in
   context, within the pack's context budget (docs/08 §3). Doctrine that outgrows its
   budget must be re-distilled, not truncated silently.

The moves catalog gains `update_doctrine` (see template/moves.yaml); the constitution
gains the knowledge rules (template/constitution.yaml `knowledge:`).

---

## 3. Failure modes (and who catches them)

- **Doctrine poisoning.** A hostile or wrong external source steers a role via its
  always-loaded context — the highest-leverage injection point in the whole org, which is
  exactly why admission is mechanistic and provenance is mandatory. Countermeasure: the
  gate's doctrine standard + the skeptic on any doctrine diff that would *loosen* a
  standard or contradict ledger experience.
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
gate admits, no role writes its own doctrine.** The knowledge base, like the ledger, is
custody-protected (no agent owns its own record of what the world says). And doctrine is
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

*Status: the pipeline and its failure modes are this repo's synthesis; the organizational
anchors are the citations above. The untrusted-input treatment of external knowledge is a
security stance, not a theorem — treat the whole organ as a design hypothesis to verify
against a running system.*
