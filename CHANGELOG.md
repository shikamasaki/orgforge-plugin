# Changelog

All notable changes to orgforge-plugin. This project follows a pragmatic semver:
minor = new mechanisms/features, patch = fixes, major = breaking articulation changes.

## 0.2.0

Hierarchical doctrine, refounding, delegation seams, and an operating-phase spine —
plus a redesigned blast-radius cap that no longer blocks normal work.

### Added
- **Hierarchical per-role doctrine hand-off** (`tools/handoff.py`). A manager hands each
  subordinate a packet: the child's slice, a **seam contract** (inputs/outputs/owns/forbid), and
  **doctrine scoped to that slice** — so knowledge narrows going down and splits by trade
  (`ui-worker` ≠ `api-worker` ≠ `db-worker`), and a parent's broader brain never leaks down. The
  runner (`run_department.py`) wires `ORG_DOCTRINE_ROOT` + `--plugin-dir` so a top-level launch
  fires the doctrine-injection hook automatically. (docs/07 §2.1)
- **Doctrine remap for refounding** (`doctrine.py remap`). When roles are renamed / split /
  merged, every live claim follows as an asset; a claim that maps to nothing **blocks** the
  refound rather than being silently lost. (docs/06 §4.4, docs/07 §2.2)
- **Spawn seam-contract gate** (`ORG_REQUIRE_SEAM=1`). An `Agent`/`Task` spawn is blocked unless
  its prompt carries a seam contract or an explicit `INDEPENDENT:` declaration — recursive splits
  can't drift on an un-owned interface. (docs/07 §2.1.1)
- **Silence-consent gate** (`guardrails.py consent`). A reversible backlog action rides the
  delegated tier (silence = consent, proceeds); an irreversible one (deploy/spend/destroy/…) holds
  for an explicit human ack. (docs/06 §2.1)
- **STALE-REFERENCE auto-trigger** (`guardrails.py staleref --auto`). Derives the trigger event +
  bound roles from the ledger's latest reference change, so a central re-prioritization propagates
  to departments without hand-fed arguments. (docs/11 §2.3, docs/12 §3.1)
- **DEPENDENCY-STALL dependency edges** (`reconcile.py stall`). Reads `work_claimed.depends_on`
  edges to report who a blocked role awaits, which downstream roles are impacted, and the
  lowest-common-owner to route to — instead of cycle timing alone. (docs/11 §2.4)
- **QUICKSTART.md** — install, the one required setting, guardrail tuning, and a verified
  "prove it blocks" snippet.

### Changed
- **Blast-radius cap now meters irreversibility, not activity.** The old flat "every file write
  costs 1 against a cap of 3" blocked a normal build at its 4th file. Now: creating a new file
  (decided by a filesystem stat), reads, and build tooling (`npm`, `pytest`, `git commit`) are
  **not metered**; the scarce low caps are reserved for `destructive_ops` (scope-weighted —
  `rm -rf` = 3), `external_writes`, `infra_changes`; overwriting an existing file is
  `file_mutations` (high cap 200). A 300-file build proceeds; `rm -rf` still hard-stops. New caps
  are tunable via `ORG_CAP_*`. (docs/11 §2.1)

### Docs
- Operating-phase flow integrated into existing homes (no new file): the two-level backlog
  (org-wide ranking + per-dept next-task) in docs/12 §3.1; the registrar as org-wide priority
  owner in docs/06 §2.6; reversible-vs-irreversible consent in docs/06 §2.1.
- New `examples/`: `doctrine-scoping` (per-role brains that narrow + refound remap), and
  `seam-descent-run` (an org self-driving scoped hand-offs end to end).

Every change ships with regression tests (76 green) and passes the payload-schema drift guard.

## 0.1.0

Initial template: the articulated organization as installable Claude Code features — PreToolUse
guardrails that block, SessionStart doctrine injection, per-department subagents, organ tools
(ledger, guardrails, doctrine, reconcile, resource, attention, learning), and organ slash-commands.
Verified on the real CLI (v2.1.211).
