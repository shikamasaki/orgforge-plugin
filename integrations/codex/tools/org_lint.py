#!/usr/bin/env python3
"""org_lint — checks the ARTICULATED ORGANIZATION is coherent.

This is the gate every founding/reorg commit passes. The repo's thesis is that designing an
agent org = articulating (in machine-actionable form) the tacit organizational knowledge a
human company runs on (THEORY.md): the goal, the division of labor, the information
flow, and the decision line. This tool checks that articulation is internally consistent —
that the division of labor, the need-to-know information flow, and the decision line the yaml
files write down don't contradict each other. It validates the org chart (organization.yaml),
the charter/decision-line (constitution.yaml), the move catalog (moves.yaml), the ledger
schema, the sensors, and — optionally — the projection's runtime settings (role-settings.yaml)
against the invariants that must hold for the articulation to be coherent:

  SC   schema           — required keys, unique ids, typed fields; absence is failure,
                          never a silent pass
  O1   Goodhart guard   — no agent rewarded on the objective metric; gaming defenses set
  O2   span budget      — active reports within each supervisor's resolvable span
  O2b  regime layers    — every role sits in a layer whose regime matches its own
  O5   ledger custody   — custody/recording are the ledger, not an agent
  O6   separation       — SoD block mandatory; authorization mechanistic, non-implementing;
                          no self-routing; makers never route to a forbidden checker;
                          every organic maker routes to >=1 mechanistic checker; an
                          adversarial checker exists and the gate routes admitted positives
                          to it (the deploy path cannot skip refutation)
  O6c  lineage          — a contract's checker and the authorization holder must not share
                          profile lineage with the makers they judge (anti-puppet-checker)
  O6b  control awake    — control roles (mechanistic layers ∪ SoD holders ∪ contract
                          checkers) never dormant while any organic role is active
  O7   contracts        — every organic maker has a contract naming a mechanistic checker
                          that is not itself
  O8   no doctrine cap  — no control role carries 'implement' together with 'judge'/'review'
                          (an adjudicating authority that also implements collapses maker and
                          checker: domain knowledge pools in the boss, not the field role that
                          owns it — docs/07 §1.1, docs/03 §3). A non-judging clerk that
                          implements (e.g. the registrar authoring diffs the gate admits) is fine.
  O9   no domain owed   — no mechanistic/control role holds a contract.deliverable (a coordinator
                          that owes a domain deliverable swallows a field role's work — the
                          docs/03 §6.5 tooth; catches the implement-without-judge case O8 misses)
  O10  contract cover   — every declared contract.deliverable is covered: (a) a non-empty
                          acceptance standard, (b) owned by EXACTLY ONE role (no deliverable
                          owned by two roles), and (c) a checker distinct from its maker. This
                          is the founding-time COVERAGE gate (docs/11 §0, docs/01 J14/S9): two
                          foundings from the same RFP must satisfy the SAME contracts — each
                          required deliverable owned once, verifiable — even if role NAMES differ.
  CH   charter sanity   — invariants present/true, sunset held, founding_commit charter,
                          no placeholders (SET_ME), queue rules on
  MV   move catalog     — parses, tiers valid, delegated lists cross-match constitution;
                          every cited sensor is defined
  LS   ledger schema    — envelope/classes/views/triggers present; every view referenced
                          by scopes, context packs, or sensors exists
  CP   context packs    — every pack entry is intent_block, doctrine, or a view GRANTED
                          to that role (a pack cannot smuggle an ungranted view)
  CA   cadences         — every loop cadence parses (every_<n>_<min|hours> or a declared
                          on_<trigger>)
  SN   sensors          — each sensor has formula/window/threshold and judge machine|llm;
                          night-preregistered moves are delegated-tier and fed by the sensor
  RS   role-settings    — (optional 6th file) every active role has neutral runtime settings;
                          budgets match the scope grant; model_tier stays neutral (no vendor
                          strings); checkers are restricted to read/verify tools (default-deny,
                          not a blocklist); asset-touching capabilities are never projected into
                          the core runner; the skeptic's model_family differs from the gate's

Usage:  org_lint.py organization.yaml constitution.yaml moves.yaml ledger-schema.yaml sensors.yaml [role-settings.yaml]
The first five files are required; role-settings.yaml is an optional sixth (the projection's
runtime settings). Omitting a required file is a violation, not a shortcut.
Exit 0 = pass, 1 = violations, 2 = usage/parse error.
"""
import os
import re
import sys

import yaml

VALID_REGIMES = {"organic", "mechanistic"}
VALID_TIERS = {"delegated", "charter", "irreversible"}
# the fixed six-function vocabulary (docs/03 §3.1.1). A role's functions: must draw only from
# this set — a typo like `judeg` on the gate, or an invented `seize_admission_authority`, would
# otherwise silently defeat the string-keyed maker/checker checks (O6 keys on these literals).
VALID_FUNCTIONS = {"organize", "decide", "implement", "judge", "review", "operate"}
# moves whose docs promise a load-bearing guard precondition — the lint asserts it is PRESENT
# (the runtime evaluates it). docs/05 §4.4: refound's doctrine-remap + relint guards.
REQUIRED_MOVE_CHECKS = {
    "refound": ["doctrine_remap_covers_every_live_claim", "new_structure_passes_lint"],
}


class Lint:
    def __init__(self):
        self.errs = []

    def fail(self, code, msg):
        self.errs.append(f"[{code}] {msg}")


def load(path, lint, label):
    try:
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except FileNotFoundError:
        lint.fail("SC", f"{label} file not found: {path}")
        return None
    except yaml.YAMLError as e:
        lint.fail("SC", f"{label} is not valid YAML ({path}): {e}")
        return None
    if not isinstance(data, dict):
        lint.fail("SC", f"{label} must be a YAML mapping: {path}")
        return None
    return data


# ── organization.yaml ────────────────────────────────────────────────────────

def lint_org(org, lint):
    roles = check_schema(org, lint)
    if roles is None:
        return None
    check_goodhart(org, lint)
    check_layers_and_span(org, roles, lint)
    control_ids = collect_control_ids(org, roles, lint)
    check_sod(org, roles, control_ids, lint)
    check_no_doctrine_capture(org, roles, control_ids, lint)
    check_no_domain_deliverable(org, roles, control_ids, lint)
    check_contract_coverage(org, roles, lint)
    check_contracts(org, roles, lint)
    check_control_awake(roles, control_ids, lint)
    return roles, control_ids


def check_schema(org, lint):
    raw = org.get("roles")
    if not isinstance(raw, list) or not raw:
        lint.fail("SC", "organization.yaml has no roles: list — nothing to lint")
        return None
    roles, seen = {}, set()
    for i, r in enumerate(raw):
        if not isinstance(r, dict) or "id" not in r:
            lint.fail("SC", f"roles[{i}] has no id")
            continue
        rid = r["id"]
        if rid in seen:
            lint.fail("SC", f"duplicate role id '{rid}' — ambiguous charts don't lint")
            continue
        seen.add(rid)
        if r.get("regime") not in VALID_REGIMES:
            lint.fail("SC", f"role '{rid}' regime must be one of {sorted(VALID_REGIMES)}")
        if not isinstance(r.get("active", None), bool):
            lint.fail("SC", f"role '{rid}' needs active: true|false (a bare bool — "
                            f"strings like \"false\" are truthy and lie)")
        for fn in r.get("functions", []) or []:
            if fn not in VALID_FUNCTIONS:
                lint.fail("SC", f"role '{rid}' function '{fn}' is not in the fixed vocabulary "
                                f"{sorted(VALID_FUNCTIONS)} (docs/03 §3.1.1) — an invented or "
                                f"mistyped function silently defeats the string-keyed SoD checks")
        roles[rid] = r
    return roles


def is_active(role):
    return role.get("active") is True


def check_goodhart(org, lint):
    metric = org.get("objective_metric", {})
    if metric.get("reward_agents_on_this") is not False:
        lint.fail("O1", "objective_metric.reward_agents_on_this must be present and false — "
                        "a proxy handed out as reward is a Goodhart trap (THEORY.md Organ 1)")
    defenses = metric.get("gaming_defenses")
    if not isinstance(defenses, list) or not defenses:
        lint.fail("O1", "objective_metric.gaming_defenses must be a non-empty list "
                        "(nulls, placebos, forward tests — docs/04 §2)")


def check_layers_and_span(org, roles, lint):
    layers = org.get("structure", {}).get("layers", [])
    covered = set()
    for layer in layers:
        regime = layer.get("regime")
        if regime not in VALID_REGIMES:
            lint.fail("O2b", f"layer '{layer.get('name', '?')}' needs a regime "
                             f"({sorted(VALID_REGIMES)}) — an unregimed layer exempts "
                             f"its members from every regime check")
            continue
        members = list(layer.get("departments", []))
        if "role" in layer:
            members.append(layer["role"])
        for dep in members:
            covered.add(dep)
            role = roles.get(dep)
            if role is None:
                lint.fail("O2b", f"layer '{layer.get('name')}' references unknown role '{dep}'")
            elif role.get("regime") != regime:
                lint.fail("O2b", f"role '{dep}' is {role.get('regime')} but sits in "
                                 f"{regime} layer '{layer.get('name')}'")
    for rid in roles:
        if rid not in covered:
            lint.fail("O2b", f"role '{rid}' belongs to no layer — unlayered roles escape "
                             f"the organic/mechanistic regime checks")

    default_span = org.get("structure", {}).get("span", {}).get("default_effective_span")
    for r in roles.values():
        reports = r.get("supervises", [])
        if not reports:
            continue
        span = r.get("effective_span", default_span)
        if not isinstance(span, int):
            lint.fail("O2", f"supervisor '{r['id']}' has no resolvable integer span "
                            f"(set structure.span.default_effective_span or "
                            f"effective_span on the role) — an absent span is an "
                            f"unbounded one")
            continue
        unknown = [x for x in reports if x not in roles]
        for x in unknown:
            lint.fail("O2", f"supervisor '{r['id']}' supervises unknown role '{x}'")
        active = [x for x in reports if x in roles and is_active(roles[x])]
        if len(active) > span:
            lint.fail("O2", f"supervisor '{r['id']}' has {len(active)} active reports "
                            f"> effective span {span}. 選択肢は2つ: (a) この数を実際に見られる"
                            f"理由があるなら structure.span.default_effective_span を "
                            f"{len(active)} に宣言し、なぜ見られるのかをコメントで残す; "
                            f"(b) 階層が本当に要るなら charter-tier の add_layer を出す。"
                            f"(a) を先に検討すること — 契約を持たない中間管理ロールを足すのは "
                            f"docs/03 §6.5（coordinator は deliverable を持たない）と緊張する "
                            f"(docs/02 §3)")


def collect_control_ids(org, roles, lint):
    """Control set = mechanistic layers ∪ every mechanistic role ∪ SoD holders ∪
    contract checkers. Layer membership alone is spoofable by omission."""
    control = set()
    for layer in org.get("structure", {}).get("layers", []):
        if layer.get("regime") == "mechanistic":
            control.update(layer.get("departments", []))
            if "role" in layer:
                control.add(layer["role"])
    for rid, r in roles.items():
        if r.get("regime") == "mechanistic":
            control.add(rid)
        checker = (r.get("contract") or {}).get("checker")
        if checker:
            control.add(checker)
    sod = org.get("separation_of_duties", {})
    if sod.get("authorization") is not None:
        control.add(sod["authorization"])
    for pair in sod.get("maker_checker_forbidden_pairs", []):
        if isinstance(pair, dict) and pair.get("checker_must_not_be"):
            pass  # forbidden names are exclusions, not members
    return {c for c in control if c in roles}


# scale moves — the ones that (de)activate/reshape a department. A manager may execute one only
# within its span-of-authority (docs/02 §scale-authority): the target must lie in the transitive
# closure of the requester's `supervises:`. A section-chief scales its section; a dept-head
# supervises section-chiefs and thus, transitively, their sections — "the same authority, only the
# scope differs." add_layer mints new authority, so it stays charter-tier and is NOT in this set.
SCALE_MOVES = {"activate_department", "deactivate_department", "adjust_context_scope"}


def check_scale_scope(org, roles, control_ids, mv, lint):
    """O2c — hierarchical scale authority. (1) every scale move must carry the
    requester_scope_covers_target precondition (the lint guarantees the guard is PRESENT; the
    runtime evaluates the closure against the ledgered initiator, docs/08). (2) no organic
    manager's supervises-closure may contain a control role — else a dept-head could deactivate
    the control skeleton 'within its span'."""
    def closure(rid, seen=None):
        seen = seen if seen is not None else set()
        for x in roles.get(rid, {}).get("supervises", []) or []:
            if x not in seen:
                seen.add(x)
                closure(x, seen)
        return seen

    for m in (mv.get("moves", []) if mv else []):
        if m.get("id") in SCALE_MOVES:
            checks = [pc.get("check") for pc in m.get("preconditions", []) or []
                      if isinstance(pc, dict)]
            if "requester_scope_covers_target" not in checks:
                lint.fail("O2c", f"scale move '{m['id']}' lacks the "
                                 f"requester_scope_covers_target precondition — scaling with no "
                                 f"span-of-authority check lets any manager scale any department "
                                 f"(docs/02 §scale-authority)")
    # regime guard: an organic manager must never have a control role in its scale reach
    for rid, r in roles.items():
        if r.get("regime") == "organic":
            crossed = control_ids.intersection(closure(rid))
            if crossed:
                lint.fail("O2c", f"organic role '{rid}' supervises-closure reaches control "
                                 f"role(s) {sorted(crossed)} — a dept-head could deactivate the "
                                 f"control skeleton within its span (regime boundary, docs/03)")


def check_manager_accountability(org, roles, lint):
    """O2d/O2e — manager accountability (docs/09). O2d: attribution closure — every active
    non-supervisor role is owned by exactly one supervisor (the RACI single-Accountable invariant
    over the supervises: graph; no orphan whose result nobody owns, no two managers claiming one
    subordinate). O2e: parity gate — a role held to a contract.deliverable must hold the authority
    to produce it (its checker is reachable; a supervised integration dependency is in its
    closure). Accountability without matching authority is a mis-designed job (docs/09 §A2)."""
    supervisors = {rid: set(r.get("supervises", []) or []) for rid, r in roles.items()
                   if r.get("supervises")}
    # O2d — attribution closure
    for rid, r in roles.items():
        if rid in supervisors:
            continue                       # a supervisor is owned by its own parent, checked below
        if not is_active(r):
            continue
        owners = [s for s, subs in supervisors.items() if rid in subs]
        if len(owners) == 0:
            lint.fail("O2d", f"active role '{rid}' is in no supervisor's supervises: list — its "
                             f"output is owned by nobody up the chain (docs/09 §A1: exactly one "
                             f"accountable supervisor per role)")
        elif len(owners) > 1:
            lint.fail("O2d", f"role '{rid}' is supervised by {sorted(owners)} — two managers "
                             f"cannot both be accountable for one subordinate (docs/09 §A1)")
    # O2e — parity gate: a contract-bearing role must hold the authority for its deliverable
    def closure(rid, seen=None):
        seen = seen if seen is not None else set()
        for x in roles.get(rid, {}).get("supervises", []) or []:
            if x not in seen:
                seen.add(x)
                closure(x, seen)
        return seen
    for rid, r in roles.items():
        contract = r.get("contract") or {}
        if not contract.get("deliverable"):
            continue
        checker = contract.get("checker")
        if checker and checker not in roles:
            lint.fail("O2e", f"role '{rid}' is accountable for a deliverable but its checker "
                             f"'{checker}' is not a defined role — accountability without a "
                             f"reachable checker (parity, docs/09 §A2)")
        # a declared integration dependency this role must roll up must be in its supervises-closure
        for dep in contract.get("integrates", []) or []:
            if dep not in closure(rid):
                lint.fail("O2e", f"role '{rid}' must integrate '{dep}' for its deliverable but "
                                 f"'{dep}' is not in its supervises-closure — it is accountable "
                                 f"for output it has no authority to direct or reject (parity, "
                                 f"docs/09 §A2)")


def check_sod(org, roles, control_ids, lint):
    sod = org.get("separation_of_duties")
    if not isinstance(sod, dict):
        lint.fail("O6", "separation_of_duties block is missing — an org without a "
                        "declared SoD map has no control system to audit (docs/03 §3.1)")
        return
    for duty in ("authorization", "custody", "recording"):
        if duty not in sod:
            lint.fail("O6", f"separation_of_duties.{duty} is missing — all three "
                            f"incompatible duties must be assigned")
    for duty in ("custody", "recording"):
        if sod.get(duty) in roles:
            lint.fail("O5", f"{duty} is held by agent '{sod[duty]}' — it must be the "
                            f"ledger (a protected store, not a member)")

    auth = sod.get("authorization")
    auth_role = roles.get(auth) if auth else None
    if auth is not None and auth_role is None:
        lint.fail("O6", f"authorization holder '{auth}' is not a declared role")
    if auth_role is not None:
        if auth_role.get("regime") != "mechanistic":
            lint.fail("O6", f"authorization holder '{auth}' must be mechanistic — an "
                            f"organic gate self-organizes toward its own dissolution "
                            f"(docs/03 §3.2)")
        if "implement" in auth_role.get("functions", []):
            lint.fail("O6", f"authorization holder '{auth}' also implements — maker and "
                            f"checker have collapsed into one agent")

    # Self-routing: universal, not only for declared pairs.
    for rid, r in roles.items():
        if rid in r.get("output_to", []):
            lint.fail("O6", f"role '{rid}' routes output to itself — self-verification "
                            f"is not verification (docs/04 §5)")

    # Forbidden pairs: the maker must not route to the named forbidden checker,
    # and must not hold the authorization duty.
    for pair in sod.get("maker_checker_forbidden_pairs", []):
        maker = pair.get("maker")
        forbidden = pair.get("checker_must_not_be")
        maker_role = roles.get(maker)
        if maker_role is None:
            lint.fail("O6", f"forbidden-pair maker '{maker}' is not a declared role")
            continue
        if forbidden in maker_role.get("output_to", []):
            lint.fail("O6", f"maker '{maker}' routes output to '{forbidden}', which its "
                            f"forbidden-pair entry bars from checking it")
        if maker == auth:
            lint.fail("O6", f"maker '{maker}' holds the authorization duty")

    # Every organic maker must route to at least one mechanistic checker.
    for rid, r in roles.items():
        if r.get("regime") != "organic" or not r.get("output_to"):
            continue
        checkers = [t for t in r["output_to"]
                    if roles.get(t, {}).get("regime") == "mechanistic"]
        if not checkers:
            lint.fail("O6", f"organic maker '{rid}' routes to no mechanistic checker — "
                            f"its output enters trusted state unchecked")

    # The adversarial review path must be wired: the authorization holder (gate) must route
    # admitted positives to an independent adversarial checker (skeptic) before deploy. The
    # ledger schema makes result_deployed require a `survives` verdict; this ensures the org
    # actually has a role positioned to produce one, and that the gate hands off to it.
    # Without this, the skeptic is a role no admitted result ever reaches.
    skeptics = [rid for rid, r in roles.items()
                if r.get("regime") == "mechanistic"
                and "review" in (r.get("functions") or [])
                and rid != auth]
    if not skeptics:
        lint.fail("O6", "no adversarial checker (a mechanistic role with function 'review', "
                        "distinct from the authorization holder) — admitted positives would "
                        "deploy without the refutation the ledger schema requires (docs/03 §3)")
    elif auth_role is not None:
        reachable = set(auth_role.get("output_to", []))
        if not (reachable & set(skeptics)):
            lint.fail("O6", f"authorization holder '{auth}' does not route admitted positives to "
                            f"any adversarial checker {skeptics} — the deploy path skips "
                            f"refutation the ledger schema requires (result_deployed needs a "
                            f"prior 'survives'). Add the skeptic to '{auth}'.output_to.")


def check_no_doctrine_capture(org, roles, control_ids, lint):
    """O8 — no doctrine capture (docs/07 §1.1, docs/03 §3/§5). A control role that BOTH judges/reviews
    AND implements has collapsed maker and checker into one seat: it produces a domain deliverable and
    also sits in judgment of domain output, so domain knowledge pools in the boss instead of accruing
    to the field role's own role-keyed brain (docs/06 §2.1). "The boss needs to know whether the
    specialist's output is on-purpose, not what the specialist knows" — docs/07 §1.1.

    The tooth fires ONLY on a control role that carries `implement` TOGETHER WITH `judge` or `review`.
    That conjunction is the real capture: an authority (judge/review) that also implements. It is the
    generalization of O6's existing "authorization holder must not implement" from one seat to every
    judging/reviewing control seat. A control CLERK that implements without judging (e.g. the registrar
    authors reorg diffs as a Maker whose output the gate admits — docs/05 §2.6 "approves nothing,
    ever") is NOT capture: it produces no domain doctrine and holds no admission authority, so it is
    left alone. Domain-work routing itself stays a runtime concern (seam contract owns/forbid +
    role-keyed doctrine); this tooth only forbids the maker/checker collapse in the chart."""
    for rid in sorted(control_ids):
        fns = set(roles.get(rid, {}).get("functions") or [])
        if "implement" in fns and ({"judge", "review"} & fns):
            adjudicating = sorted({"judge", "review"} & fns)
            lint.fail("O8", f"control role '{rid}' carries 'implement' together with {adjudicating} — "
                            f"a judging/reviewing authority that also implements collapses maker and "
                            f"checker into one seat (doctrine capture): domain knowledge pools in the "
                            f"boss instead of the field role that owns it (docs/07 §1.1, docs/03 §3). "
                            f"A control role that adjudicates must not also implement a domain.")


def check_no_domain_deliverable(org, roles, control_ids, lint):
    """O9 — a mechanistic/control role produces NO domain deliverable (docs/03 §6.5, the tooth docs/03
    named and left unimplemented). O8 catches the implement+judge COLLAPSE; O9 catches the quieter case
    O8 misses: a coordinator that merely *implements a domain deliverable* without judging — a supervisor
    with functions [organize, implement] and a contract.deliverable passes O8 but is exactly the
    'coordinator swallowing domain work' docs/03 §3 warns against. A control role coordinates, routes, and
    reviews; the domain deliverable belongs to the field role, so its knowledge accrues there (docs/07
    §1.1 no doctrine capture). A control role authoring org-mechanism work products (the registrar's reorg
    diffs) is NOT a domain deliverable — those are routed to the gate as candidates, not owed as a
    contract.deliverable — so it does not carry one and passes."""
    for rid in sorted(control_ids):
        r = roles.get(rid, {})
        deliverable = (r.get("contract") or {}).get("deliverable")
        if deliverable:
            lint.fail("O9", f"control role '{rid}' (mechanistic/control set) holds a "
                            f"contract.deliverable ({str(deliverable)[:50]!r}) — a coordinator that owes a "
                            f"domain deliverable swallows work that belongs to a field role, so domain "
                            f"knowledge pools in the boss instead of accruing to the role that owns it "
                            f"(doctrine capture, docs/07 §1.1, docs/03 §6.5). A control role coordinates and "
                            f"reviews; it does not owe a domain deliverable — route it to a domain role.")


def _norm_deliverable(text):
    """Normalize a deliverable string for owner-collision comparison: lowercased, collapsed
    whitespace. Two foundings may word a role differently; the deliverable string is what the
    coverage gate compares, so a founder cannot smuggle the SAME deliverable under two roles
    by re-casing or re-spacing it."""
    return re.sub(r"\s+", " ", str(text).strip().lower())


def check_contract_coverage(org, roles, lint):
    """O10 — contract COVERAGE (docs/11 §0, docs/01 J14/S9). org_lint validates SoD/span/contract
    STRUCTURE, but structure alone lets two foundings from the same RFP disagree on which work is
    owned and to what bar. This tooth makes coverage MECHANICAL, not a founder's judgment: for every
    declared contract.deliverable, (a) it carries a non-empty acceptance STANDARD (a deliverable with
    no bar is unverifiable — two founders would 'meet' it differently); (b) it is owned by EXACTLY ONE
    role (a deliverable claimed by two roles has no single accountable owner — the same convergence
    failure docs/11 forbids); and (c) its checker is DISTINCT from its maker (an unverifiable-by-others
    contract, reusing the maker!=checker rule the SoD machinery enforces elsewhere). We accept LLM
    variation in role NAMES/wording; we pin the CONTRACTS. This does NOT invent a required deliverable
    set (the RFP names those) — it checks that every deliverable the chart DOES declare is covered
    once, with a bar, verifiably. The coverage MANIFEST the founder emits (org-found.md) is what maps
    RFP must-haves onto these contracts; O10 gates the chart side of that manifest."""
    owners = {}   # normalized deliverable -> [role ids owning it]
    for rid, r in roles.items():
        contract = r.get("contract")
        if not isinstance(contract, dict):
            continue
        deliverable = contract.get("deliverable")
        if not deliverable or not str(deliverable).strip():
            continue
        owners.setdefault(_norm_deliverable(deliverable), []).append(rid)

        # (a) non-empty acceptance standard
        standard = contract.get("standard")
        if not standard or not str(standard).strip():
            lint.fail("O10", f"role '{rid}' owns deliverable "
                             f"{str(deliverable)[:50]!r} with no acceptance standard — a "
                             f"deliverable with no bar is unverifiable, so two foundings from "
                             f"the same RFP would 'satisfy' it differently (coverage, docs/11 §0). "
                             f"Add contract.standard: the bar its output must meet.")

        # (c) checker distinct from maker (reuse the maker!=checker rule from SoD)
        checker = contract.get("checker")
        if not checker or not str(checker).strip():
            lint.fail("O10", f"role '{rid}' owns deliverable {str(deliverable)[:50]!r} with no "
                             f"contract.checker — an unchecked deliverable has no owner-independent "
                             f"acceptance (coverage, docs/11 §0). Name the checker that admits it.")
        elif checker == rid:
            lint.fail("O10", f"role '{rid}' names itself as the checker of its own deliverable "
                             f"{str(deliverable)[:50]!r} — self-verification is not verification, "
                             f"so the contract is not owner-independently satisfiable (coverage, "
                             f"docs/11 §0). Route it to a distinct checker.")

    # (b) exactly one owning role per deliverable
    for deliverable, rids in sorted(owners.items()):
        if len(rids) > 1:
            lint.fail("O10", f"deliverable {deliverable[:50]!r} is owned by {sorted(rids)} — a "
                             f"deliverable claimed by two roles has no single accountable owner, so "
                             f"the same RFP requirement is covered inconsistently across foundings "
                             f"(coverage, docs/11 §0). Exactly one role owns each contract.")


def check_contracts(org, roles, lint):
    auth = (org.get("separation_of_duties") or {}).get("authorization")
    for rid, r in roles.items():
        lineage = r.get("profile_lineage")
        if not lineage:
            lint.fail("SC", f"role '{rid}' has no profile_lineage — lineage is how the "
                            f"lint detects puppet checkers (O6c)")
        if r.get("regime") != "organic" or not r.get("output_to"):
            continue
        contract = r.get("contract")
        if not isinstance(contract, dict) or not contract.get("checker"):
            lint.fail("O7", f"organic maker '{rid}' has no contract naming its checker — "
                            f"contracts are how departments work independently toward "
                            f"the RFP (docs/05 §1, step 3)")
            continue
        checker = contract["checker"]
        checker_role = roles.get(checker)
        if checker == rid:
            lint.fail("O7", f"'{rid}' names itself as its contract's checker")
        elif checker_role is None:
            lint.fail("O7", f"'{rid}' names unknown checker '{checker}'")
        else:
            if checker_role.get("regime") != "mechanistic":
                lint.fail("O7", f"'{rid}' contract checker '{checker}' is not mechanistic")
            if (checker_role.get("profile_lineage")
                    and checker_role.get("profile_lineage") == r.get("profile_lineage")):
                lint.fail("O6c", f"checker '{checker}' shares profile lineage "
                                 f"'{r.get('profile_lineage')}' with maker '{rid}' — a "
                                 f"cloned checker rubber-stamps by construction")
        if auth and roles.get(auth, {}).get("profile_lineage") \
                and roles[auth].get("profile_lineage") == r.get("profile_lineage"):
            lint.fail("O6c", f"authorization holder '{auth}' shares profile lineage with "
                             f"maker '{rid}'")


def check_control_awake(roles, control_ids, lint):
    organic_active = sorted(r["id"] for r in roles.values()
                            if r.get("regime") == "organic" and is_active(r))
    if not organic_active:
        return
    for cid in sorted(control_ids):
        if not is_active(roles[cid]):
            lint.fail("O6b", f"control role '{cid}' is dormant while organic roles "
                             f"{organic_active} are active — SoD disabled by a "
                             f"scheduling decision (docs/02 §3)")


# ── constitution.yaml ────────────────────────────────────────────────────────

REQUIRED_INVARIANTS = ["ledger_append_only", "no_knowledge_outside_ledger",
                       "control_never_dormant_while_exploring", "maker_never_own_checker",
                       "no_agent_writes_this_file"]


def walk_for_placeholder(node, path, lint):
    if isinstance(node, str) and "SET_ME" in node:
        lint.fail("CH", f"placeholder left unset at {path} — an unset charter is not a "
                        f"charter")
    elif isinstance(node, dict):
        for k, v in node.items():
            walk_for_placeholder(v, f"{path}.{k}", lint)
    elif isinstance(node, list):
        for i, v in enumerate(node):
            walk_for_placeholder(v, f"{path}[{i}]", lint)


def lint_constitution(con, lint):
    inv = con.get("invariants", [])
    present = {}
    if isinstance(inv, dict):
        present = inv
    elif isinstance(inv, list):
        for item in inv:
            if isinstance(item, dict):
                present.update(item)
    for key in REQUIRED_INVARIANTS:
        if present.get(key) is not True:
            lint.fail("CH", f"constitution invariant '{key}' missing or not true")

    charter_items = (con.get("charter") or {}).get("items", []) or []
    if "founding_commit" not in charter_items:
        lint.fail("CH", "founding_commit is not a charter item — an org must not be "
                        "born without human sign-off (docs/05 §1)")
    held = (con.get("irreversible") or {}).get("held_actions", []) or []
    if "sunset" not in held:
        lint.fail("CH", "sunset is not on the irreversible hold list — an org must not "
                        "adjudicate its own death (docs/05 §4.3)")
    rules = (con.get("charter") or {}).get("queue_rules", {}) or {}
    for rule in ("one_concern_per_proposal", "one_open_proposal_per_subject",
                 "dedup_identical_diffs"):
        if rules.get(rule) is not True:
            lint.fail("CH", f"charter.queue_rules.{rule} must be true — the approval "
                            f"queue is floodable without it (docs/05 §2.2)")
    if rules.get("batch_adjudication_of_charter_items") is not False:
        lint.fail("CH", "charter.queue_rules.batch_adjudication_of_charter_items must "
                        "be false")
    # Judge preflight is an enforcement contract, not an arbitrary shell snippet. Validate it at
    # founding/lint time as well as immediately before dispatch, so an unbounded or ambiguous
    # probe does not wait until the first real review to stop the organization.
    try:
        from orgcycle.preflight import (PreflightConfigError, declared_preflights,
                                        parse_probes)
        parse_probes(declared_preflights(con), "*", "*", "*")
    except PreflightConfigError as exc:
        lint.fail("PF", f"judge preflight contract invalid: {exc}")
    # mandate_precedence (docs/05 §6.4): the human-authored ordering reconcile.py mandate reads.
    mp = con.get("mandate_precedence")
    if mp is None:
        lint.fail("CH", "constitution has no mandate_precedence — with none, every genuine "
                        "mandate conflict (two depts each in-authority, decisions that can't "
                        "both stand) either pages the human or resolves by merge-order accident "
                        "(docs/05 §6.4). Declare who governs.")
    elif not isinstance(mp.get("order"), list) or len(mp.get("order", [])) < 2:
        lint.fail("CH", "constitution.mandate_precedence.order must list >= 2 mandates in "
                        "governing order (earlier wins) — a one-item or missing order resolves "
                        "nothing")
    walk_for_placeholder(con, "constitution", lint)
    return charter_items


# ── moves.yaml ───────────────────────────────────────────────────────────────

def lint_moves(mv, con, lint):
    moves = mv.get("moves")
    if not isinstance(moves, list) or not moves:
        lint.fail("MV", "moves.yaml has no moves: list")
        return
    by_id = {}
    for m in moves:
        mid = m.get("id")
        if not mid:
            lint.fail("MV", "a move has no id")
            continue
        if mid in by_id:
            lint.fail("MV", f"duplicate move id '{mid}'")
        by_id[mid] = m
        if m.get("tier") not in VALID_TIERS:
            lint.fail("MV", f"move '{mid}' tier must be one of {sorted(VALID_TIERS)}")
        for pc in m.get("preconditions", []) or []:
            if isinstance(pc, dict) and "judgment" in pc \
                    and pc.get("judge") not in ("human", "llm"):
                lint.fail("MV", f"move '{mid}' has a judgment precondition without "
                                f"judge: human|llm — undecided judgments default to "
                                f"nobody, which means the maker")

    if con is None:
        return
    declared = (con.get("delegated") or {}).get("structural_moves", []) or []
    for mid in declared:
        m = by_id.get(mid)
        if m is None:
            lint.fail("MV", f"constitution delegates '{mid}' but moves.yaml has no such "
                            f"move — a phantom power is an ungoverned one")
        elif m.get("tier") != "delegated":
            lint.fail("MV", f"constitution delegates '{mid}' but moves.yaml tiers it "
                            f"'{m.get('tier')}' — the two files disagree on authority")
    for mid, m in by_id.items():
        if m.get("tier") == "delegated" and mid not in declared:
            lint.fail("MV", f"move '{mid}' is delegated in moves.yaml but absent from "
                            f"the constitution's delegated list — no tier, no legality")
    # the CHARTER direction (was unchecked — a charter move could be silently re-tiered to
    # delegated and pass, downgrading e.g. `refound`, the whole-org teardown, to an unattended
    # act). Every id in charter.items that is ALSO a move must be tiered charter or irreversible;
    # and a move whose id sits in charter.items may never be delegated.
    charter_items = set((con.get("charter") or {}).get("items", []) or [])
    for mid in charter_items:
        m = by_id.get(mid)
        if m is not None and m.get("tier") not in ("charter", "irreversible"):
            lint.fail("MV", f"move '{mid}' is a charter item in constitution.yaml but moves.yaml "
                            f"tiers it '{m.get('tier')}' — a charter power silently downgraded to "
                            f"{m.get('tier')} escapes human sign-off (docs/05)")
    # a move carrying a `judge: human` precondition is human-held by construction — it may not be
    # delegated (which would let an agent execute it unattended).
    for mid, m in by_id.items():
        human_judged = any(isinstance(pc, dict) and pc.get("judge") == "human"
                           for pc in m.get("preconditions", []) or [])
        if human_judged and m.get("tier") == "delegated":
            lint.fail("MV", f"move '{mid}' has a judge:human precondition but is tiered "
                            f"'delegated' — a human-judged act cannot run unattended")
    # named moves whose docs call out a load-bearing guard must actually carry it — otherwise the
    # guard the docs promise ("the one the move guards explicitly", docs/05 §4.4) is silently
    # absent. Modeled on O2c's scale-move presence check.
    for mid, required in REQUIRED_MOVE_CHECKS.items():
        m = by_id.get(mid)
        if m is None:
            continue
        checks = [pc.get("check") for pc in m.get("preconditions", []) or []
                  if isinstance(pc, dict)]
        for req in required:
            if req not in checks:
                lint.fail("MV", f"move '{mid}' lacks its required guard precondition '{req}' — "
                                f"the docs name this the guard that protects the asset "
                                f"structure-change can lose; without it the move is unguarded")


# ── ledger-schema.yaml ───────────────────────────────────────────────────────

def lint_ledger_schema(ls, lint):
    for key in ("envelope", "event_classes", "views", "triggers"):
        if not isinstance(ls.get(key), dict) or not ls.get(key):
            lint.fail("LS", f"ledger-schema.yaml has no {key} — the ledger's vocabulary "
                            f"is incomplete")
    env = ls.get("envelope", {})
    for key in ("fields", "write_control"):
        if key not in env:
            lint.fail("LS", f"ledger-schema envelope has no {key}")
    wc = env.get("write_control", {})
    if wc.get("append_only") is not True:
        lint.fail("LS", "ledger-schema write_control.append_only must be true")
    classes = set(ls.get("event_classes", {}) or {})
    for vid, view in (ls.get("views", {}) or {}).items():
        for cls in (view or {}).get("from", []):
            if cls != "*" and cls not in classes:
                lint.fail("LS", f"view '{vid}' derives from undeclared event class '{cls}'")
    return set(ls.get("views", {}) or {}), set(ls.get("triggers", {}) or {})


CADENCE_TIMER = re.compile(r"^every_\d+_(min|hours)$")


def lint_org_against_schema(org, views, triggers, lint):
    grants_by_role = {}
    for grant in ((org.get("information_flow", {}) or {}).get("scopes", {}) or {}) \
            .get("grants", []) or []:
        role = grant.get("role")
        grants_by_role[role] = set(grant.get("views", []))
        for v in grant.get("views", []):
            if v not in views:
                lint.fail("LS", f"scope grant for '{role}' references undefined view '{v}'")
        if not isinstance(grant.get("pack_budget_tokens"), int):
            lint.fail("CP", f"scope grant for '{role}' has no integer pack_budget_tokens "
                            f"— an unbudgeted pack is an unbounded one (docs/07 §2.4)")
    # the universal pack items (carried by every role WITHOUT a per-role grant) are DECLARED in
    # information_flow.universal_pack_items — read them, don't hardcode, so the code and the
    # articulation cannot silently disagree (the CP authority-control hole: a pack item that is
    # injected but not granted unenforces deny-by-default).
    universal = set((org.get("information_flow", {}) or {}).get("universal_pack_items",
                                                                 ["intent_block", "doctrine"]))

    # VW — スキーマが定義したビューを、実際にツールが引けるか。
    # これが無いと lint は「articulation は整合している」と GREEN を出しながら、実行時に
    # context_pack が1つも引けないという状態を通してしまう。実地でそれが起きた:
    # gate の context_pack 3件と skeptic の 2件がすべて未実装で、SoD の checker が
    # 判断材料を取得できないのに lint は pass していた。**articulation と実装の乖離を
    # 検出できないことが穴の本体**なので、ここで閉じる。
    _unresolvable = _views_not_implemented(views)
    for vid in _unresolvable:
        lint.fail("VW", f"ledger-schema が定義するビュー '{vid}' を ledger.py が引けない — "
                        f"これを context_pack に持つロールは実行時に判断材料を取得できない。"
                        f"スキーマと実装の乖離であって、articulation の問題ではない")
    for r in org.get("roles", []):
        rid = r.get("id", "?")
        for item in r.get("context_pack", []) or []:
            if item in universal:
                continue
            if item not in views:
                lint.fail("LS", f"role '{rid}' context_pack names undefined view '{item}'")
            elif item not in grants_by_role.get(rid, set()):
                lint.fail("CP", f"role '{rid}' context_pack includes view '{item}' it has "
                                f"no scope grant for — packs cannot smuggle ungranted "
                                f"views (docs/07 §2.2)")
        cadence = (r.get("loop") or {}).get("cadence")
        if cadence is None:
            lint.fail("CA", f"role '{rid}' has no loop.cadence")
        elif not CADENCE_TIMER.match(str(cadence)):
            if str(cadence).startswith("on_"):
                if str(cadence)[3:] not in triggers:
                    lint.fail("CA", f"role '{rid}' cadence '{cadence}' binds to no "
                                    f"declared trigger (ledger-schema triggers)")
            else:
                lint.fail("CA", f"role '{rid}' cadence '{cadence}' matches neither "
                                f"every_<n>_<min|hours> nor on_<trigger>")


# ── sensors.yaml ─────────────────────────────────────────────────────────────

def lint_sensors(sn, mv, views, lint):
    sensors = sn.get("sensors")
    if not isinstance(sensors, list) or not sensors:
        lint.fail("SN", "sensors.yaml has no sensors: list")
        return set()
    moves_by_id = {m.get("id"): m for m in (mv or {}).get("moves", []) or []}
    ids = set()
    for s in sensors:
        sid = s.get("id")
        if not sid:
            lint.fail("SN", "a sensor has no id")
            continue
        if sid in ids:
            lint.fail("SN", f"duplicate sensor id '{sid}'")
        ids.add(sid)
        for key in ("formula", "window", "threshold"):
            if not s.get(key):
                lint.fail("SN", f"sensor '{sid}' has no {key} — an unmeasurable sensor "
                                f"is a vibe, and vibes don't gate moves")
        if s.get("judge") not in ("machine", "llm"):
            lint.fail("SN", f"sensor '{sid}' judge must be machine|llm")
        for v in s.get("source_views", []) or []:
            if v not in views:
                lint.fail("SN", f"sensor '{sid}' reads undefined view '{v}'")
        feeds = s.get("feeds_moves", []) or []
        for mid in feeds:
            if mid not in moves_by_id:
                lint.fail("SN", f"sensor '{sid}' feeds unknown move '{mid}'")
        for mid in s.get("preregistered_for_night", []) or []:
            if mid not in feeds:
                lint.fail("SN", f"sensor '{sid}' preregisters move '{mid}' it does not "
                                f"feed — night patterns must be exact (docs/05 §2.4)")
            elif moves_by_id.get(mid, {}).get("tier") != "delegated":
                lint.fail("SN", f"sensor '{sid}' preregisters non-delegated move '{mid}' "
                                f"for unattended nights — charter moves queue, always")
    return ids


def lint_moves_cite_defined_sensors(mv, sensor_ids, lint):
    for m in (mv or {}).get("moves", []) or []:
        for pc in m.get("preconditions", []) or []:
            if isinstance(pc, dict) and "sensor" in pc \
                    and pc["sensor"] not in sensor_ids:
                lint.fail("MV", f"move '{m.get('id')}' cites undefined sensor "
                                f"'{pc['sensor']}' — define it in sensors.yaml")


# ── role-settings.yaml (optional 6th file — the projection's neutral runtime settings) ──

# A checker only reads and re-derives; anything outside this allowlist makes it a maker.
# This is default-deny, not a blocklist — a renamed write tool cannot slip past.
CHECKER_ALLOWED_TOOLS = {"read", "run_tests", "web_read"}

# Capabilities that touch protected assets or publish irreversible effects. Ordinary development
# network access is intentionally not here: dependency resolution, documentation, APIs, and normal
# git collaboration are part of development. The host still owns deployment credentials and final
# production/publication authority.
ASSET_TOUCHING_TOOLS = {"deploy", "secrets", "asset_movement",
                        "external_publish", "production_deploy"}


def _scope_budgets(org):
    """role -> pack_budget_tokens from information_flow.scopes.grants."""
    out = {}
    for g in ((org.get("information_flow", {}) or {}).get("scopes", {}) or {}) \
            .get("grants", []) or []:
        if isinstance(g, dict) and "role" in g:
            out[g["role"]] = g.get("pack_budget_tokens")
    return out


def lint_role_settings(rs, org, lint):
    """RS — the articulated runtime settings must be coherent with the org chart:
    every role present, budgets matching the scope grant, checkers restricted to read/verify
    tools (default-deny, not a blocklist), asset-touching capabilities kept outside the core
    runner, the adversarial checker decorrelated from the maker/gate it judges, and no vendor
    model strings leaking into the neutral layer."""
    raw = rs.get("roles")
    if not isinstance(raw, list) or not raw:
        lint.fail("RS", "role-settings.yaml has no roles: list")
        return
    org_roles = {r["id"]: r for r in (org or {}).get("roles", []) if isinstance(r, dict) and "id" in r}
    budgets = _scope_budgets(org or {})
    auth = (org.get("separation_of_duties") or {}).get("authorization") if org else None
    families = {}   # role -> model_family, for the decorrelation check
    seen = set()
    for i, s in enumerate(raw):
        if not isinstance(s, dict) or "role" not in s:
            lint.fail("RS", f"role-settings roles[{i}] has no role")
            continue
        rid = s["role"]
        seen.add(rid)
        if s.get("model_family"):
            families[rid] = s["model_family"]
        if org_roles and rid not in org_roles:
            lint.fail("RS", f"role-settings names '{rid}', absent from organization.yaml — "
                            f"the settings articulate a role the org chart doesn't declare")
        mt = s.get("model_tier")
        if mt is not None and mt not in ("judge", "worker", "cheap"):
            lint.fail("RS", f"role '{rid}' model_tier must be judge|worker|cheap (a NEUTRAL "
                            f"tier, not a vendor model)")
        # budget must match the org's scope grant (or the info-flow articulation is inconsistent)
        b = s.get("context_budget_tokens")
        if rid in budgets and b is not None and budgets[rid] is not None and b != budgets[rid]:
            lint.fail("RS", f"role '{rid}' context_budget_tokens {b} != its scope grant "
                            f"{budgets[rid]} in organization.yaml — the information budget is "
                            f"articulated in two places and they disagree (docs/07)")

        allow = set(((s.get("tools") or {}).get("allow")) or [])
        org_role = org_roles.get(rid, {})
        # A checker of OTHERS' work is the authorization holder (gate) or a MECHANISTIC
        # adversarial reviewer (skeptic — mechanistic + 'review'). An organic maker's own
        # 'review' function is self-review of its own output, not checking others, so it is
        # not subject to the read-only allowlist. The supervisor coaches and the registrar
        # authors diffs (Maker of reorg diffs, gate-admitted) — neither is an admission checker.
        is_mechanistic = org_role.get("regime") == "mechanistic"
        is_checker = rid == auth or (is_mechanistic and "review" in (org_role.get("functions") or []))

        # A checker is DEFAULT-DENY: only read/verify tools. A renamed write tool
        # ("edit_files", "publish") is not on the allowlist, so it cannot slip past —
        # unlike a blocklist of the literal words write/implement.
        if is_checker:
            escapes = allow - CHECKER_ALLOWED_TOOLS
            if escapes:
                lint.fail("RS", f"checker role '{rid}' is granted non-verification tools "
                                f"{sorted(escapes)} — a checker may only read and re-derive "
                                f"(allowed: {sorted(CHECKER_ALLOWED_TOOLS)}); anything else "
                                f"makes it a maker checking its own work (Organ 6)")

        # Asset-touching execution belongs to the host platform's protected environment.
        # Granting it to a core role would turn governance metadata into a credential-bearing
        # runtime, which is explicitly outside orgforge's product boundary.
        asset_caps = allow & ASSET_TOUCHING_TOOLS
        if asset_caps:
            lint.fail("RS", f"role '{rid}' is granted asset-touching tools {sorted(asset_caps)} "
                            f"— orgforge's core runner never receives deploy, credential, "
                            f"publication, or production authority. Record the decision and "
                            f"evidence here, but execute it in the host platform's protected "
                            f"environment.")

    # Correlated-failure defense: the adversarial checker (skeptic) must not run the SAME
    # model family as the maker/gate it judges — same model, same blind spots. Only checked
    # when model_family is declared; declaring it is how you opt into decorrelation.
    skeptic_fam = families.get("skeptic")
    if skeptic_fam is not None:
        # decorrelate from the gate AND from every maker whose work reaches the skeptic — docs/03
        # says "maker/gate", not gate alone. A maker that routes to the gate (output_to: gate) is
        # judged transitively by the skeptic; if it declares the skeptic's family, same blind spots.
        judged = {"gate"}
        for r in org.get("roles", []):
            outs = r.get("output_to", []) or []
            if "gate" in outs and r.get("regime") == "organic":
                judged.add(r.get("id"))
        for other in sorted(judged):
            if other != "skeptic" and families.get(other) == skeptic_fam:
                lint.fail("RS", f"skeptic and '{other}' share model_family '{skeptic_fam}' — an "
                                f"adversarial checker on the same base model shares the maker/gate's "
                                f"blind spots (a different prompt is not a different error "
                                f"distribution). Give the skeptic a different model_family.")

    # every ACTIVE org role should have settings (dormant ones may be omitted)
    if org_roles:
        for rid, r in org_roles.items():
            if r.get("active") is True and rid not in seen:
                lint.fail("RS", f"active role '{rid}' has no role-settings block — its runtime "
                                f"knobs (model tier, stop, tools) are un-articulated")


# ── entry ────────────────────────────────────────────────────────────────────

CADENCE_ANY = re.compile(r"^(every_\d+_(min|hours)|on_[a-z_]+)$")


def lint_schedule(sched, ls, sn, lint):
    """Guardrail for the LLM-owned schedule.yaml (docs/05 §5): keep its edits R0-safe and
    night-safe, and keep the missed-tick guard well-formed. The registrar EDITS cadences; this
    is what stops an edit from becoming an unsatisfiable or fail-open schedule."""
    checks = sched.get("checks", [])
    if not checks:
        lint.fail("SCH", "schedule.yaml has no checks — nothing would ever be planned")
        return
    base = sched.get("base_interval", "")
    if not CADENCE_ANY.match(base) or not base.startswith("every_"):
        lint.fail("SCH", f"schedule base_interval '{base}' must be an every_<n>_min|hours timer")
    def to_min(c):
        m = re.match(r"every_(\d+)_min$", c)
        if m: return int(m.group(1))
        m = re.match(r"every_(\d+)_hours$", c)
        if m: return int(m.group(1)) * 60
        return None
    base_min = to_min(base) or 5
    classes = set((ls.get("event_classes", {}) if ls else {}) or {})
    # night allowlist: which (sensor->move) pairs may run at night (sensors.yaml)
    night_moves = set()
    for s in (sn.get("sensors", []) if sn else []):
        for mv in (s.get("preregistered_for_night", []) or []):
            night_moves.add(mv)
    seen = set()
    for c in checks:
        cid = c.get("id")
        if not cid or cid in seen:
            lint.fail("SCH", f"schedule check id missing or duplicated: {cid!r}")
        seen.add(cid)
        cadence = c.get("cadence", "")
        if not CADENCE_ANY.match(cadence):
            lint.fail("SCH", f"check '{cid}' cadence '{cadence}' is not a known form "
                             f"(every_<n>_min|hours or on_<event>)")
        cmin = to_min(cadence)
        if cmin is not None and cmin < base_min:
            lint.fail("SCH", f"check '{cid}' cadence {cadence} ({cmin}m) is finer than "
                             f"base_interval {base_min}m — the host cron can NEVER fire it; "
                             f"unsatisfiable schedule (docs/05 §5)")
        # verify_event must name a real ledger class, or the missed-tick guard can't detect a miss
        ve = c.get("verify_event")
        if not ve:
            lint.fail("SCH", f"check '{cid}' has no verify_event — a check with no ledger "
                             f"proof-of-run cannot be missed-tick-detected ('it was supposed "
                             f"to run' would stay a silent excuse, docs/05 §5.6)")
        elif classes and ve not in classes:
            lint.fail("SCH", f"check '{cid}' verify_event '{ve}' is not a declared ledger "
                             f"event class — the missed-tick guard would never match it")
        if "night_safe" not in c:
            lint.fail("SCH", f"check '{cid}' must declare night_safe (true|false) — an "
                             f"undeclared night policy defaults to fail-OPEN, which the "
                             f"constitution forbids (delegated.night is fail-safe)")
    # missed_tick policy must exist and be well-formed — it IS the anti-silent-skip guardrail
    mt = sched.get("missed_tick")
    if not isinstance(mt, dict) or "escalate_after_consecutive" not in mt:
        lint.fail("SCH", "schedule.yaml missing a missed_tick policy with "
                         "escalate_after_consecutive — without it a schedule the host "
                         "silently stopped firing would never be detected (docs/05 §5.6)")


def _views_not_implemented(schema_views):
    """スキーマの views のうち、ledger.py が引けないものを返す。

    ledger.py はスキーマの `views:` を読むので通常は空になる。空でないなら、スキーマが壊れて
    いるか ledger.py が読めていないかで、どちらも実行時に context_pack が引けない状態を意味する。"""
    try:
        here = os.path.dirname(os.path.abspath(__file__))
        sys.path.insert(0, here)
        import ledger
        impl = set(ledger._view_from())
    except Exception:
        return []          # ledger.py を読めない環境では黙って飛ばす（lint 自体は落とさない）
    if not impl:
        return []          # スキーマが読めていない場合はここでは判定しない
    return sorted(set(schema_views) - impl)


def main(argv):
    if len(argv) not in (6, 7, 8):
        print(__doc__)
        return 2
    lint = Lint()
    org = load(argv[1], lint, "organization.yaml")
    con = load(argv[2], lint, "constitution.yaml")
    mv = load(argv[3], lint, "moves.yaml")
    ls = load(argv[4], lint, "ledger-schema.yaml")
    sn = load(argv[5], lint, "sensors.yaml")
    # optional 7th/8th files: role-settings.yaml and schedule.yaml, in either order —
    # distinguished by content (schedule has a `checks` key; role-settings has `role`/`tools`).
    rs = sched = None
    for extra in argv[6:]:
        doc = load(extra, lint, os.path.basename(extra))
        if isinstance(doc, dict) and "checks" in doc:
            sched = doc
        elif doc is not None:
            rs = doc
    if org is not None:
        if "roles" not in org:
            lint.fail("SC", f"{argv[1]} does not look like an organization.yaml "
                            f"(no roles key) — check argument order: org constitution "
                            f"moves ledger-schema sensors")
        else:
            _org_roles, _org_control = lint_org(org, lint)
    if con is not None:
        lint_constitution(con, lint)
    if mv is not None:
        lint_moves(mv, con, lint)
        if org is not None and "roles" in org:
            check_scale_scope(org, _org_roles, _org_control, mv, lint)
    if org is not None and "roles" in org and _org_roles is not None:
        check_manager_accountability(org, _org_roles, lint)
    views, triggers = (set(), set())
    if ls is not None:
        views, triggers = lint_ledger_schema(ls, lint)
        if org is not None and "roles" in org:
            lint_org_against_schema(org, views, triggers, lint)
    if sn is not None:
        sensor_ids = lint_sensors(sn, mv, views, lint)
        if mv is not None:
            lint_moves_cite_defined_sensors(mv, sensor_ids, lint)
    if rs is not None and org is not None and "roles" in org:
        lint_role_settings(rs, org, lint)
    if sched is not None:
        lint_schedule(sched, ls, sn, lint)
    if lint.errs:
        print(f"org_lint: {len(lint.errs)} violation(s)")
        for e in lint.errs:
            print("  " + e)
        return 1
    print("org_lint: pass — the articulation is internally consistent "
          "(runtime enforcement is the host's; see docs/08)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
