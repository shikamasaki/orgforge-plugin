# PROJECTION — rendering the articulated organization into each LLM harness's config

This is the layer that turns the *articulated organization* (organization.yaml,
constitution.yaml, ROLE.md, the intent block, the context packs) into the **actual config
files a specific LLM harness reads** — so a department can launch and run. It is the one
harness-specific layer in the repo (docs/09 §2); everything above it is harness-neutral.

Two things get projected, per running department:

1. **The instruction file** — the harness's own convention for "who you are and what your
   job is" (a Claude Code working dir reads `CLAUDE.md`; a Codex working dir reads
   `AGENTS.md`; others have their own). This is the department's projected **profile**.
2. **The model / runtime settings** — which model, effort/thinking, tools/permissions,
   stop conditions, output schema — the knobs the harness exposes. This is
   `role-settings.yaml` below, a neutral settings block projected onto each harness's API.

The neutral sources are canonical; the per-harness files are **generated views, never
hand-edited** (regenerate them, don't fork them — the same discipline the ledger's derived
views follow).

---

## 1. What goes into a department's instruction file (CLAUDE.md / AGENTS.md / …)

The projected instruction file is assembled, in order, from the articulated org:

```
1. INTENT BLOCK        (the goal)          ← organization.yaml information_flow.intent_block,
                                             loaded by reference from its ledger-stamped version
2. THIS ROLE'S JOB     (division of labor) ← ROLE.md instance: mission, duties, the standard
                                             its output must meet, its named checker
3. THIS ROLE'S DOCTRINE (current norms)    ← docs/07, the gate-admitted doctrine file
4. THE DECISION LINE   (what to escalate)  ← the constitution's tier lists, reduced to
                                             "what you may do now / must propose / must hold"
                                             FOR THIS ROLE
5. DISCIPLINE PREAMBLE  (immutable)         ← ROLE.md's charter-protected discipline block, verbatim
6. GRANTED CONTEXT      (need-to-know)      ← the role's scoped context-pack views (docs/08),
                                             written into the working dir as files it reads
```

Items 1–5 are the *content* of the instruction file. Item 6 is *files in the working
directory* the harness can read — "assembling the context pack" is exactly this
file-writing step (docs/09 §2), not a runtime.

**Manager duty — hand each subordinate a scoped brain AND a seam contract (docs/07 §2.1).**
Item 3 (this role's doctrine) is auto-injected by the SessionStart hook only for a *top-level*
launch. A manager that spawns subordinates in-process (the Agent/subagent tool) must build the
hand-off itself with `tools/handoff.py`, prepended to the child's prompt. The packet fixes
(a) the child's **slice**, (b) the **seam contract** — inputs/outputs/owns/forbid, the hard
interface the manager later integrates against; this, not a global decomposition axis, is what
makes siblings compose (docs/07 §2.1.1), and (c) the child's **brain scoped to its slice**
(only doctrine whose `affected_roles` name the child role, so the manager's broader brain does
not leak down). The child role is named by trade (`ui-worker`, not `worker`). A manager profile
states this as an explicit step, the same way it states spec-driven delegation; omitting the
seam is how recursive splits drift, omitting the brain is how subordinates run brain-blank.

**Harness mapping (the only thing that changes per harness):**

| Harness | Instruction file | Notes |
|---|---|---|
| Claude Code | `CLAUDE.md` in the working dir | read on launch as project instructions |
| Codex | `AGENTS.md` in the working dir | Codex's own convention |
| *(others)* | that harness's instruction-file convention | one row per harness you target |

*Open decision (docs/01 §7 #1):* whether to author the neutral profile under a
harness-neutral filename (e.g. `PROFILE.md`) and generate `CLAUDE.md`/`AGENTS.md` from it,
or to lead with one convention and treat the others as fallback. Either way the **neutral
`ROLE.md` instance is the source of truth**; the per-harness file is a rendered view.

---

## 2. `role-settings.yaml` — the neutral model/runtime settings, projected per harness

Each role declares its runtime knobs **once, harness-neutrally**; the projection maps them
onto whatever the host harness/API actually exposes. Keep this neutral — do not hard-code
one vendor's parameter names here; the mapping table (§3) does that.

```yaml
# role-settings.yaml — neutral runtime settings for ONE role. Projected onto the host harness.
role: miner
model_tier: worker          # judge | worker | cheap — a NEUTRAL tier, mapped to a concrete
                            # model per harness (§3). Do NOT name a vendor model here.
model_family: family-A      # NEUTRAL family label (§3 maps it to a concrete vendor family).
                            # Only relative distinctness matters: the adversarial checker
                            # (skeptic) must declare a DIFFERENT family from the gate/maker it
                            # judges — same base model, same blind spots. The lint enforces it.
effort: medium              # low | medium | high — reasoning depth intent; mapped per harness
context_budget_tokens: 20000  # must match this role's information_flow.scopes grant (docs/08)
stop:
  goal: "candidate submitted to the gate"   # the verifiable stop condition (loop delegated to host)
  max_iterations: 8                          # a cap the host loop enforces
tools:                       # capability scope — the deontic articulation (who MAY do what)
  allow: [read, write, run_tests]
  deny:  [network, deploy, secrets]          # tier-appropriate; asset-touching needs a Tier-B host
output:
  format: files              # files | json_schema — how the deliverable is returned
  # json_schema: { ... }     # when the contract wants a structured, validatable deliverable
tier: A                      # A (drift-only) | B (asset-touching) — selects host isolation (docs/01 §5)
```

`role-settings.yaml` is itself part of the *articulated organization*: `tools.allow/deny`
is the **deontic dimension** (who may do what — the access-control articulation that MAS
theory unifies with structure), `stop`/`context_budget_tokens` articulate the
metabolism and the information budget, and `model_tier`/`effort` articulate how much
capability this role's work warrants (risk-calibration, docs/01 §5 — a cheap reversible
role does not need the judge tier).

---

## 3. The harness mapping table (the only vendor-specific file)

One table per harness maps the neutral settings to that harness's concrete config. This is
the *only* place a vendor's model names and parameter shapes appear — swap harnesses by
swapping this table, nothing else.

```yaml
# harness-map.<harness>.yaml — maps NEUTRAL role-settings onto ONE harness's actual config.
harness: <harness-name>
instruction_file: CLAUDE.md            # or AGENTS.md, etc.
model_tier:                            # neutral tier -> concrete model for THIS harness
  judge:  <the strongest model this harness offers>
  worker: <a mid model>
  cheap:  <a fast/cheap model>
model_family:                          # neutral family label -> a concrete vendor model family,
  family-A: <one vendor family>        # so the skeptic (family-B) really is a different base model
  family-B: <a DIFFERENT vendor family>  # from the gate/maker (family-A) — decorrelates blind spots
effort:                                # neutral effort -> this harness's control
  low: ...   medium: ...   high: ...
tools:                                 # neutral capability names -> this harness's tool ids/permissions
  read: ...  write: ...  run_tests: ...  network: ...  deploy: ...  secrets: ...
tier_isolation:                        # how THIS host provides Tier-A vs Tier-B isolation
  A: <ordinary working-dir sandbox>
  B: <sandboxed env with credential custody — REQUIRED for asset-touching roles (docs/01 §5)>
```

Filling in the concrete model names / parameter shapes for a given harness is deliberately
left to the adopter, because those are the parts that change fastest — hard-coding them in
the neutral layer is exactly the harness-coupling this repo forbids (docs/01 C1). The
neutral `role-settings.yaml` + this per-harness map is the whole projection contract.

---

## 4. What the projection MUST preserve (or the articulation is broken)

The projection is a *rendering*, so it must not lose or alter the articulated org:

- **The decision line survives.** A role's projected instruction file must give it exactly
  its delegated bounds — no more. It may not grant a maker the authority to admit its own
  work (the separation the lint checks structurally must hold at launch, docs/09 §5).
- **Need-to-know survives.** Only the role's granted views are written into its working dir
  (docs/08). The projection cannot smuggle context a role wasn't granted — that would
  re-tacit-ify the information flow the org just articulated.
- **The discipline preamble survives verbatim.** Item 5 is charter-protected; the
  projection copies it, never edits it.
- **Tier isolation matches the role's tier.** A Tier-B (asset-touching) role must be
  projected onto a host that provides the sandboxing/custody its tier requires (docs/01
  §5); projecting it onto a bare working dir is a safety break, not a convenience.

*Status: the projection contract (this file, `role-settings.yaml`, and the per-harness map)
is specified here; wiring it for a concrete harness is the adopter's step and the founding
rehearsal (docs/10) did it by hand. Automating the render is the remaining build item flagged
in docs/01 §7 #1.*
