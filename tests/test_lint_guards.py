"""Regression tests for org_lint guards that a docs-vs-implementation audit found missing.

Each test mutates the shipped template exactly as the audit did and asserts org_lint now FAILS
(exit 1). Without these, the guards silently re-drift — the 'described but not enforced' pattern
the repo exists to kill, which had reappeared in the repo's own recent additions.
"""
import copy
import pathlib
import subprocess
import sys

import yaml

REPO = pathlib.Path(__file__).resolve().parent.parent
TOOLS = REPO / "tools"
TPL = REPO / "template"


def _lint(tmp_path, **overrides):
    """Write the 5 core template files (with per-file overrides) to tmp and run org_lint."""
    files = {}
    for name in ("organization", "constitution", "moves", "ledger-schema", "sensors"):
        doc = yaml.safe_load((TPL / f"{name}.yaml").read_text())
        if name in overrides:
            doc = overrides[name](copy.deepcopy(doc))
        p = tmp_path / f"{name}.yaml"
        p.write_text(yaml.safe_dump(doc))
        files[name] = str(p)
    r = subprocess.run([sys.executable, str(TOOLS / "org_lint.py"),
                        files["organization"], files["constitution"], files["moves"],
                        files["ledger-schema"], files["sensors"]],
                       capture_output=True, text=True)
    return r.returncode, r.stdout + r.stderr


def _lint_with_role_settings(tmp_path, mutate=None):
    files = {}
    for name in ("organization", "constitution", "moves", "ledger-schema", "sensors"):
        doc = yaml.safe_load((TPL / f"{name}.yaml").read_text())
        path = tmp_path / f"{name}.yaml"
        path.write_text(yaml.safe_dump(doc))
        files[name] = str(path)
    settings = yaml.safe_load((TPL / "role-settings.yaml").read_text())
    if mutate:
        settings = mutate(settings)
    settings_path = tmp_path / "role-settings.yaml"
    settings_path.write_text(yaml.safe_dump(settings))
    result = subprocess.run(
        [
            sys.executable,
            str(TOOLS / "org_lint.py"),
            files["organization"],
            files["constitution"],
            files["moves"],
            files["ledger-schema"],
            files["sensors"],
            str(settings_path),
        ],
        capture_output=True,
        text=True,
    )
    return result.returncode, result.stdout + result.stderr


def test_clean_template_passes(tmp_path):
    code, out = _lint(tmp_path)
    assert code == 0, out


def test_clean_role_settings_pass_without_runtime_tier(tmp_path):
    code, out = _lint_with_role_settings(tmp_path)
    assert code == 0, out


def test_asset_touching_tools_cannot_be_enabled_by_legacy_tier(tmp_path):
    def mutate(settings):
        settings.setdefault("defaults", {})["tier"] = "B"
        settings["roles"][0]["tier"] = "B"
        settings["roles"][0]["tools"]["allow"].append("deploy")
        return settings

    code, out = _lint_with_role_settings(tmp_path, mutate)
    assert code == 1, out
    assert "asset-touching tools" in out
    assert "host platform" in out


def test_normal_development_network_access_is_allowed(tmp_path):
    def mutate(settings):
        settings["roles"][0]["tools"]["allow"].append("network")
        settings["roles"][0]["tools"]["deny"] = [
            tool for tool in settings["roles"][0]["tools"]["deny"] if tool != "network"
        ]
        return settings

    code, out = _lint_with_role_settings(tmp_path, mutate)
    assert code == 0, out


def test_refound_cannot_be_downgraded_to_delegated(tmp_path):
    # BLOCKER: re-tier refound charter->delegated in BOTH files -> must be caught
    def mv(m):
        for x in m["moves"]:
            if x["id"] == "refound":
                x["tier"] = "delegated"
        return m
    def con(c):
        c["charter"]["items"] = [i for i in c["charter"]["items"] if i != "refound"]
        c.setdefault("delegated", {}).setdefault("structural_moves", []).append("refound")
        return c
    code, out = _lint(tmp_path, moves=mv, constitution=con)
    assert code == 1 and "MV" in out


def test_refound_must_carry_doctrine_remap_guard(tmp_path):
    # MAJOR: deleting refound's guard preconditions must be caught
    def mv(m):
        for x in m["moves"]:
            if x["id"] == "refound":
                x["preconditions"] = [p for p in x["preconditions"]
                                      if not (isinstance(p, dict)
                                              and str(p.get("check", "")).startswith(
                                                  ("doctrine_remap", "new_structure")))]
        return m
    code, out = _lint(tmp_path, moves=mv)
    assert code == 1 and "MV" in out


def test_bogus_function_rejected(tmp_path):
    # MAJOR: a function outside the fixed six-vocabulary must be caught
    def org(o):
        for r in o["roles"]:
            if r["id"] == "miner":
                r["functions"] = r["functions"] + ["seize_admission_authority"]
        return o
    code, out = _lint(tmp_path, organization=org)
    assert code == 1 and "vocabulary" in out


def test_human_judged_move_cannot_be_delegated(tmp_path):
    # a judge:human move re-tiered to delegated (unattended human-only act) must be caught
    def mv(m):
        for x in m["moves"]:
            if x["id"] == "enter_maintenance":     # has a judge:human precondition
                x["tier"] = "delegated"
        return m
    def con(c):
        c.setdefault("delegated", {}).setdefault("structural_moves", []).append("enter_maintenance")
        return c
    code, out = _lint(tmp_path, moves=mv, constitution=con)
    assert code == 1 and "MV" in out


def test_orphan_role_fails_attribution_closure(tmp_path):
    # O2d (docs/09 §A1): an active role no supervisor owns → its output is owned by nobody
    def org(o):
        for r in o["roles"]:
            if r["id"] == "supervisor":
                r["supervises"] = [x for x in r["supervises"] if x != "miner"]
        return o
    code, out = _lint(tmp_path, organization=org)
    assert code == 1 and "O2d" in out


def test_double_supervised_role_fails_attribution(tmp_path):
    # O2d: two managers cannot both be accountable for one subordinate. Add a sub-supervisor that
    # also supervises miner, so miner is owned by two.
    def org(o):
        # give an existing role a supervises that overlaps supervisor's (registrar supervises miner too)
        for r in o["roles"]:
            if r["id"] == "registrar":
                r["supervises"] = ["miner"]
        return o
    code, out = _lint(tmp_path, organization=org)
    assert code == 1 and "O2d" in out


def test_contract_checker_must_exist_parity(tmp_path):
    # O2e (docs/09 §A2): a deliverable-bearing role whose checker isn't a real role → parity fail
    def org(o):
        for r in o["roles"]:
            if r.get("contract", {}).get("deliverable"):
                r["contract"]["checker"] = "ghost_checker"
                break
        return o
    code, out = _lint(tmp_path, organization=org)
    # only fires if some role has a contract.deliverable; the shipped template's makers may not —
    # so accept either the O2e failure or a clean pass if no deliverable-bearing role exists.
    if "deliverable" in (TPL / "organization.yaml").read_text():
        assert code == 1 and "O2e" in out


def test_o8_control_role_that_adjudicates_and_implements_is_capture(tmp_path):
    # O8 (docs/07 §1.1, docs/03 §3): a control role that JUDGES/REVIEWS and also IMPLEMENTs collapses
    # maker and checker — domain knowledge would pool in the boss (doctrine capture). Give the gate
    # (functions: [judge]) an extra `implement` → must fail O8.
    def org(o):
        for r in o["roles"]:
            if r["id"] == "gate":
                r["functions"] = r["functions"] + ["implement"]
        return o
    code, out = _lint(tmp_path, organization=org)
    assert code == 1 and "O8" in out


def test_o8_does_not_fire_on_a_non_judging_clerk_that_implements(tmp_path):
    # The registrar is mechanistic and carries `implement` (it authors reorg diffs as a Maker the
    # gate admits — docs/05 §2.6, "approves nothing, ever"). It does NOT judge/review, so it is a
    # clerk, not capture. The shipped template must stay clean of O8 — a guard against the tooth
    # regressing into the coarse "any control implement" false positive that flagged the registrar.
    code, out = _lint(tmp_path)
    assert code == 0, out
    assert "O8" not in out


def test_o9_mechanistic_role_may_not_own_a_domain_deliverable(tmp_path):
    # O9 (docs/03 §6.5): a control role that owes a contract.deliverable swallows a field role's domain
    # work. Give the supervisor a deliverable → must fail. Catches the implement-without-judge case O8 misses.
    def org(o):
        for r in o["roles"]:
            if r["id"] == "supervisor":
                r["functions"] = ["organize", "implement"]
                r["contract"] = {"deliverable": "the login API", "checker": "gate"}
        return o
    code, out = _lint(tmp_path, organization=org)
    assert code == 1 and "O9" in out


def test_o9_does_not_fire_on_the_clean_template(tmp_path):
    # no mechanistic role in the shipped template owes a domain deliverable — O9 must stay clean.
    code, out = _lint(tmp_path)
    assert code == 0 and "O9" not in out


# ── O10 (docs/11 §0, §4a) — the founding coverage gate: contracts converge across founders ──
def _first_maker_with_contract(o):
    for r in o["roles"]:
        c = r.get("contract") or {}
        if c.get("deliverable") and c.get("standard"):
            return r
    return None


def test_o10_deliverable_without_acceptance_standard_fails(tmp_path):
    # a deliverable with no acceptance bar is unverifiable → two founders "satisfy" it differently.
    def org(o):
        r = _first_maker_with_contract(o)
        r["contract"].pop("standard", None)
        return o
    code, out = _lint(tmp_path, organization=org)
    assert code == 1 and "O10" in out, out


def test_o10_deliverable_owned_by_two_roles_fails(tmp_path):
    # the same deliverable declared under two roles → ownership is not reproducible.
    def org(o):
        makers = [r for r in o["roles"] if (r.get("contract") or {}).get("deliverable")]
        if len(makers) >= 2:
            makers[1]["contract"]["deliverable"] = makers[0]["contract"]["deliverable"]
        return o
    code, out = _lint(tmp_path, organization=org)
    assert code == 1 and "O10" in out, out


def test_o10_self_check_fails(tmp_path):
    # checker must be distinct from the maker (reuses the SoD rule) — a self-checked deliverable
    # has no independent bar, so its "acceptance" is not reproducible across founders.
    def org(o):
        r = _first_maker_with_contract(o)
        r["contract"]["checker"] = r["id"]
        return o
    code, out = _lint(tmp_path, organization=org)
    assert code == 1 and "O10" in out, out


def test_o10_does_not_fire_on_the_clean_template(tmp_path):
    # the shipped template already declares {deliverable, standard, checker!=maker}, owned once — clean.
    code, out = _lint(tmp_path)
    assert code == 0 and "O10" not in out
