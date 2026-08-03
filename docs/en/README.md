# orgforge — English Documentation

This is the official English documentation for orgforge. Every page in this directory is written
to stand on its own; the reader does not need the Japanese set to understand or operate the plugin.

> **Turn agent instructions into an accountable software team.**

## What orgforge is

orgforge is a thin organizational control layer for existing coding-agent harnesses such as Claude
Code and Codex. It turns the tacit operating knowledge of a software organization into explicit,
machine-actionable structure:

- what the organization is trying to achieve;
- which role owns each deliverable;
- what information each role receives;
- which decisions remain human-held;
- which SDLC phases a deliverable must pass;
- what evidence must exist before work is admitted, integrated, deployed, or operated.

The product does **not** replace the host harness. It uses the harness's loop, scheduler, tool
mediation, sandbox, and CI/CD substrate.

Its main differentiator is co-evolution: evidence from building and operating the product can
produce bounded, reviewable proposals to change role ownership, contracts, context flow, and
checks. The organization grows with the product instead of remaining a static prompt bundle.
Purpose, constitutional bounds, and irreversible decisions remain human-held.

## Product shape

orgforge combines six small, composable capabilities:

1. **Organization compiler** — derive a minimal ownership and checking structure from real code.
2. **Workflow governance** — make SDLC order and acceptance bars explicit and machine-checkable.
3. **Evidence ledger** — record decisions, checks, and effects so work can be reconstructed.
4. **Harness adapters** — apply the same neutral organization through Claude Code and Codex.
5. **Operational insight** — report status, drift, caps, HALT state, and remaining work.
6. **Organization evolution** — turn measured bottlenecks and failures into reviewable structural
   changes while preserving the human-held decision line.

`org-goal` keeps one explicit objective portable across Claude Code and Codex restarts. The shared
ledger holds its progress, next action, blocker observations, completion evidence, and owning host
session. Codex's native Goal is a reconciled adapter projection; Claude Code resumes through
SessionStart and may use a session-scoped loop. Neither adapter claims execution while its host is
closed.

For an existing repository, `/orgforge-plugin:org-adopt` performs local adoption in one bounded
workflow. It does not require sudo, a daemon, separate OS users, keys, a branch, a GitHub Issue, or
network access.

## Supported assurance

orgforge is designed to catch the failures that dominate normal agent operation:

- hallucination and stale assumptions;
- sycophantic agreement;
- skipped verification or skipped SDLC phases;
- accidental self-admission;
- unbounded tool effects;
- lost decisions and unauditable work.

The default claims are:

| Axis | Supported claim |
|---|---|
| Judgment identity | `attested` |
| Review diversity | `cross-harness` means decorrelated model review |
| Writer path | `process_mediated` |
| Ledger | tamper-evident, not immutable |

orgforge does not claim hostile same-UID containment, externally authenticated judge identity, or
cryptographic independence between local agents.

## What is not part of the core

The following are deliberately not required by the core product:

- a custom agent runtime or scheduler;
- a resident remote judge service;
- mTLS judge infrastructure;
- KMS, HSM, PKCS#11, or Secure Enclave integration;
- separate OS users for Claude and Codex;
- separate-UID writer isolation as a release prerequisite.

The default is **trusted developer mode**: development roles can use the filesystem, shell, network,
dependencies, documentation, APIs, and normal Git collaboration without per-command approval.
Claude uses `--dangerously-skip-permissions`; Codex uses its approval/sandbox bypass. Use this only
on a trusted development machine and repository with no production credentials. The organization
still declares deploy, credential, external-publication, and production authority out of scope, but
that declaration is a governance rule—not hostile-process containment. The host platform performs
those actions through protected environments and approval mechanisms.

Organizations that touch production, money, external publication, or regulated assets should use
the host platform's protected environments, credential custody, sandboxing, approvals, and audit
facilities. orgforge records and coordinates those controls; it does not reimplement the platform.

## Documentation

- [Quickstart](quickstart.md) — install and run the supported workflow.
- [Architecture](architecture.md) — the neutral core, host projection, ledger, and SDLC mold.
- [Assurance Model](assurance.md) — exact meanings of claims and non-claims.
- [Operations](operations.md) — daily operation, gates, HALT, caps, and human decisions.
- [Platform adapter contracts](platform-adapter-contracts.md) — bounded contracts for artifact, backend, OTel, Checks, and external-PDP adapters.

The older mixed-language documents at the repository root and in `docs/` remain design history and
long-form rationale. When wording conflicts, this English set and the matching Japanese set define
the current supported product.
