#!/usr/bin/env python3
"""org_lint — checks the ARTICULATED ORGANIZATION is coherent.

This is the gate every founding/reorg commit passes. The repo's thesis is that designing an
agent org = articulating (in machine-actionable form) the tacit organizational knowledge a
human company runs on (THEORY.md; docs/11): the goal, the division of labor, the information
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
                          every organic maker routes to >=1 mechanistic checker
  O6c  lineage          — a contract's checker and the authorization holder must not share
                          profile lineage with the makers they judge (anti-puppet-checker)
  O6b  control awake    — control roles (mechanistic layers ∪ SoD holders ∪ contract
                          checkers) never dormant while any organic role is active
  O7   contracts        — every organic maker has a contract naming a mechanistic checker
                          that is not itself
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
                          budgets match the scope grant; tiers A|B and model_tier neutral
                          (no vendor strings); no checker is granted write/implement

Usage:  org_lint.py organization.yaml constitution.yaml moves.yaml ledger-schema.yaml sensors.yaml [role-settings.yaml]
The first five files are required; role-settings.yaml is an optional sixth (the projection's
runtime settings). Omitting a required file is a violation, not a shortcut.
Exit 0 = pass, 1 = violations, 2 = usage/parse error.
"""
import re
import sys

import yaml

VALID_REGIMES = {"organic", "mechanistic"}
VALID_TIERS = {"delegated", "charter", "irreversible"}


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
    check_contracts(org, roles, lint)
    check_control_awake(roles, control_ids, lint)
    return roles


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
                            f"> effective span {span} — widen span via context or file "
                            f"a charter-tier add_layer proposal (docs/02 §3)")


def collect_control_ids(org, roles, lint):
    """Control set = mechanistic layers ∪ every mechanistic role ∪ SoD holders ∪
    contract checkers. Layer membership alone is spoofable by omission (review finding)."""
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

    # Self-routing: universal, not only for declared pairs (review finding).
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
                            f"the RFP (docs/06 §1.3)")
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
                             f"scheduling decision (docs/05 §3)")


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
                        "born without human sign-off (docs/06 §1)")
    held = (con.get("irreversible") or {}).get("held_actions", []) or []
    if "sunset" not in held:
        lint.fail("CH", "sunset is not on the irreversible hold list — an org must not "
                        "adjudicate its own death (docs/06 §4.3)")
    rules = (con.get("charter") or {}).get("queue_rules", {}) or {}
    for rule in ("one_concern_per_proposal", "one_open_proposal_per_subject",
                 "dedup_identical_diffs"):
        if rules.get(rule) is not True:
            lint.fail("CH", f"charter.queue_rules.{rule} must be true — the approval "
                            f"queue is floodable without it (docs/06 §2.2)")
    if rules.get("batch_adjudication_of_charter_items") is not False:
        lint.fail("CH", "charter.queue_rules.batch_adjudication_of_charter_items must "
                        "be false")
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
                            f"— an unbudgeted pack is an unbounded one (docs/08 §2.4)")
    for r in org.get("roles", []):
        rid = r.get("id", "?")
        for item in r.get("context_pack", []) or []:
            if item in ("intent_block", "doctrine"):
                continue
            if item not in views:
                lint.fail("LS", f"role '{rid}' context_pack names undefined view '{item}'")
            elif item not in grants_by_role.get(rid, set()):
                lint.fail("CP", f"role '{rid}' context_pack includes view '{item}' it has "
                                f"no scope grant for — packs cannot smuggle ungranted "
                                f"views (docs/08 §2.2)")
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
                                f"feed — night patterns must be exact (docs/06 §2.4)")
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

VALID_TIERS_RS = {"A", "B"}


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
    every role present, budgets matching the scope grant, tiers valid, checkers not
    granted write/implement, and no vendor model strings leaking into the neutral layer."""
    raw = rs.get("roles")
    if not isinstance(raw, list) or not raw:
        lint.fail("RS", "role-settings.yaml has no roles: list")
        return
    org_roles = {r["id"]: r for r in (org or {}).get("roles", []) if isinstance(r, dict) and "id" in r}
    budgets = _scope_budgets(org or {})
    seen = set()
    for i, s in enumerate(raw):
        if not isinstance(s, dict) or "role" not in s:
            lint.fail("RS", f"role-settings roles[{i}] has no role")
            continue
        rid = s["role"]
        seen.add(rid)
        if org_roles and rid not in org_roles:
            lint.fail("RS", f"role-settings names '{rid}', absent from organization.yaml — "
                            f"the settings articulate a role the org chart doesn't declare")
        tier = s.get("tier", (rs.get("defaults", {}) or {}).get("tier"))
        if tier is not None and tier not in VALID_TIERS_RS:
            lint.fail("RS", f"role '{rid}' tier must be A or B (docs/01 §5)")
        mt = s.get("model_tier")
        if mt is not None and mt not in ("judge", "worker", "cheap"):
            lint.fail("RS", f"role '{rid}' model_tier must be judge|worker|cheap (a NEUTRAL "
                            f"tier, not a vendor model — docs/11 §2)")
        # budget must match the org's scope grant (or the info-flow articulation is inconsistent)
        b = s.get("context_budget_tokens")
        if rid in budgets and b is not None and budgets[rid] is not None and b != budgets[rid]:
            lint.fail("RS", f"role '{rid}' context_budget_tokens {b} != its scope grant "
                            f"{budgets[rid]} in organization.yaml — the information budget is "
                            f"articulated in two places and they disagree (docs/08)")
        # a checker/authorization holder must not be granted write/implement in its settings
        allow = ((s.get("tools") or {}).get("allow")) or []
        is_control = org_roles.get(rid, {}).get("regime") == "mechanistic"
        auth = (org.get("separation_of_duties") or {}).get("authorization") if org else None
        if (is_control or rid == auth) and ("write" in allow or "implement" in allow):
            lint.fail("RS", f"control role '{rid}' is granted write/implement in role-settings — "
                            f"a checker that can implement is a maker checking its own work (Organ 6)")
    # every ACTIVE org role should have settings (dormant ones may be omitted)
    if org_roles:
        for rid, r in org_roles.items():
            if r.get("active") is True and rid not in seen:
                lint.fail("RS", f"active role '{rid}' has no role-settings block — its runtime "
                                f"knobs (model tier, stop, tools) are un-articulated")


# ── entry ────────────────────────────────────────────────────────────────────

def main(argv):
    if len(argv) not in (6, 7):
        print(__doc__)
        return 2
    lint = Lint()
    org = load(argv[1], lint, "organization.yaml")
    con = load(argv[2], lint, "constitution.yaml")
    mv = load(argv[3], lint, "moves.yaml")
    ls = load(argv[4], lint, "ledger-schema.yaml")
    sn = load(argv[5], lint, "sensors.yaml")
    rs = load(argv[6], lint, "role-settings.yaml") if len(argv) == 7 else None
    if org is not None:
        if "roles" not in org:
            lint.fail("SC", f"{argv[1]} does not look like an organization.yaml "
                            f"(no roles key) — check argument order: org constitution "
                            f"moves ledger-schema sensors")
        else:
            lint_org(org, lint)
    if con is not None:
        lint_constitution(con, lint)
    if mv is not None:
        lint_moves(mv, con, lint)
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
    if lint.errs:
        print(f"org_lint: {len(lint.errs)} violation(s)")
        for e in lint.errs:
            print("  " + e)
        return 1
    print("org_lint: pass — the chart obeys its own theory")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
