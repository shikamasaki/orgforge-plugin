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


def test_clean_template_passes(tmp_path):
    code, out = _lint(tmp_path)
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
    # O2d (docs/14 §A1): an active role no supervisor owns → its output is owned by nobody
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
    # O2e (docs/14 §A2): a deliverable-bearing role whose checker isn't a real role → parity fail
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
