#!/usr/bin/env python3
"""org_lint — the audit gate every founding/reorg commit must pass.

Checks an organization.yaml (and optionally its constitution.yaml) against the
invariants the theory says must hold mechanically, not by anyone's restraint:

  O1  Goodhart guard      — no agent is rewarded on the objective metric
  O2  span budget         — no supervisor's ACTIVE reports exceed effective span
  O2b regime consistency  — layer regime matches each member role's regime
  O5  ledger custody      — custody/recording are the ledger, not an agent
  O6  separation of duties— no maker routes output to itself; authorization is
                            mechanistic and never held by an implementing role
  O6b control-never-dormant — while any organic role is active, the supervisor
                            and every control-layer role are active
  CH  charter sanity      — constitution invariants present and set true

Usage:  org_lint.py path/to/organization.yaml [path/to/constitution.yaml]
Exit 0 = pass, 1 = violations found.
"""
import sys

import yaml


def fail(msgs, code, msg):
    msgs.append(f"[{code}] {msg}")


def lint_org(org):
    errs = []
    roles = {r["id"]: r for r in org.get("roles", [])}
    layers = org.get("structure", {}).get("layers", [])
    sod = org.get("separation_of_duties", {})

    # O1 — Goodhart guard
    metric = org.get("objective_metric", {})
    if metric.get("reward_agents_on_this") is not False:
        fail(errs, "O1", "objective_metric.reward_agents_on_this must be false — "
             "a proxy handed out as reward is a Goodhart trap (THEORY.md Organ 1)")

    # O2 — span budget over ACTIVE reports only (dormant departments cost no span)
    span = org.get("structure", {}).get("span", {}).get("default_effective_span")
    for r in roles.values():
        reports = r.get("supervises", [])
        if not reports:
            continue
        active = [x for x in reports if roles.get(x, {}).get("active", True)]
        r_span = r.get("effective_span", span)
        if r_span is not None and len(active) > r_span:
            fail(errs, "O2", f"supervisor '{r['id']}' has {len(active)} active reports "
                 f"> effective span {r_span} — widen span via context or file a "
                 f"charter-tier add_layer ringi (docs/02 §3)")
        for x in reports:
            if x not in roles:
                fail(errs, "O2", f"supervisor '{r['id']}' supervises unknown role '{x}'")

    # O2b — layer regime must match member regime
    for layer in layers:
        for dep in layer.get("departments", []) + (
            [layer["role"]] if "role" in layer else []
        ):
            role = roles.get(dep)
            if role is None:
                fail(errs, "O2b", f"layer '{layer['name']}' references unknown role '{dep}'")
            elif role.get("regime") != layer.get("regime"):
                fail(errs, "O2b", f"role '{dep}' is {role.get('regime')} but sits in "
                     f"{layer.get('regime')} layer '{layer['name']}'")

    # O5 — custody and recording live in the ledger, not in any agent
    for duty in ("custody", "recording"):
        holder = sod.get(duty)
        if holder in roles:
            fail(errs, "O5", f"{duty} is held by agent '{holder}' — it must be the "
                 f"ledger (a protected store, not a member)")

    # O6 — separation of duties
    auth = sod.get("authorization")
    if auth is not None:
        auth_role = roles.get(auth)
        if auth_role is None:
            fail(errs, "O6", f"authorization holder '{auth}' is not a declared role")
        else:
            if auth_role.get("regime") != "mechanistic":
                fail(errs, "O6", f"authorization holder '{auth}' must be mechanistic — "
                     f"an organic gate self-organizes toward its own dissolution (docs/03 §3.2)")
            if "implement" in auth_role.get("functions", []):
                fail(errs, "O6", f"authorization holder '{auth}' also implements — "
                     f"maker and checker have collapsed into one agent")
    for pair in sod.get("maker_checker_forbidden_pairs", []):
        maker = pair.get("maker")
        forbidden = pair.get("checker_must_not_be")
        maker_role = roles.get(maker)
        if maker_role is None:
            fail(errs, "O6", f"forbidden-pair maker '{maker}' is not a declared role")
            continue
        if forbidden in maker_role.get("output_to", []) and forbidden == maker:
            fail(errs, "O6", f"'{maker}' routes output to itself")
        if maker == auth:
            fail(errs, "O6", f"maker '{maker}' holds the authorization duty")

    # O6b — control never dormant while exploration is active
    organic_active = [r["id"] for r in roles.values()
                      if r.get("regime") == "organic" and r.get("active", True)]
    if organic_active:
        control_ids = set()
        for layer in layers:
            if layer.get("regime") == "mechanistic":
                control_ids.update(layer.get("departments", []))
                if "role" in layer:
                    control_ids.add(layer["role"])
        for cid in sorted(control_ids):
            if not roles.get(cid, {}).get("active", True):
                fail(errs, "O6b", f"control role '{cid}' is dormant while organic roles "
                     f"{organic_active} are active — SoD disabled by scheduling (docs/05 §3)")
    return errs


def lint_constitution(con):
    errs = []
    inv = con.get("invariants", [])
    required = ["ledger_append_only", "no_knowledge_outside_ledger",
                "control_never_dormant_while_exploring", "maker_never_own_checker",
                "no_agent_writes_this_file"]
    present = {}
    for item in inv:
        if isinstance(item, dict):
            present.update(item)
    for key in required:
        if present.get(key) is not True:
            fail(errs, "CH", f"constitution invariant '{key}' missing or not true")
    held = con.get("irreversible", {}).get("held_actions", [])
    if "sunset" not in held:
        fail(errs, "CH", "sunset is not on the irreversible hold list — "
             "an org must not adjudicate its own death (docs/06 §4.3)")
    return errs


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 2
    errs = []
    with open(argv[1]) as f:
        errs += lint_org(yaml.safe_load(f))
    if len(argv) > 2:
        with open(argv[2]) as f:
            errs += lint_constitution(yaml.safe_load(f))
    if errs:
        print(f"org_lint: {len(errs)} violation(s)")
        for e in errs:
            print("  " + e)
        return 1
    print("org_lint: pass — the chart obeys its own theory")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
