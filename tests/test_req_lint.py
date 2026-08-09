"""req_lint — checking that requirements are written to the standard (docs/11 §0b).

docs/11 §0a fixed the *file names* of the founding artifacts but prescribed nothing about *the format
of their content*. As a result the structure was invented afresh at every founding and the same
requirements produced documents of different structure — the central claim, "same spec ⇒ same
process", was broken at the layer where requirements are written. This check closes that hole.

Conformance: tailored conformance to ISO/IEC/IEEE 29148:2018 (the form §4.5.2 recognises) + EARS.
"""
import pathlib
import subprocess
import sys

REPO = pathlib.Path(__file__).resolve().parent.parent
TOOL = REPO / "tools" / "req_lint.py"

VALID = """# 要求
## 1. Why
立替の清算が滞留せずに完了する。
## 2. Goals / Non-Goals
Goals: 清算が完了する
Non-Goals: 家計簿機能は持たない
## 3. Requirements
| ID | 要求 |
|---|---|
| FR-001 | When a user submits a payment report, the system shall mark it as pending |
| FR-002 | 受領側が7日間応答しないとき、システムは自動で支払い済みとすること |
## 4. Acceptance
FR-001: Given 未払い When 送金報告 Then 確認待ちになる
## 5. Success Criteria
| SC-001 | 清算完了率 90% 以上 |
## 6. Constraints
金額は integer（円）
## 7. Out of Scope
PayPay API決済（既知の死）
"""


def run(tmp_path, text, *args):
    p = tmp_path / "REQUIREMENTS.md"
    p.write_text(text, encoding="utf-8")
    r = subprocess.run([sys.executable, str(TOOL), "check", str(p), *args],
                       capture_output=True, text=True)
    return r.returncode, r.stdout + r.stderr


def test_valid_document_passes(tmp_path):
    code, out = run(tmp_path, VALID)
    assert code == 0, out
    assert "conforms" in out


def test_template_conforms_to_its_own_rules(tmp_path):
    """A template that defines the rules must not violate them.

    The banned words line up in the appendix checklist as "examples", so a naive check always fails —
    producing the absurdity that the better a document explains the rules, the more violations it
    has."""
    r = subprocess.run([sys.executable, str(TOOL), "check",
                        str(REPO / "template" / "REQUIREMENTS.md")],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr


# ── the required sections ───────────────────────────────────────────────────
def test_missing_section_is_held(tmp_path):
    code, out = run(tmp_path, VALID.replace("## 7. Out of Scope\nPayPay API決済（既知の死）\n", ""))
    assert code == 10
    assert "out-of-scope" in out


def test_japanese_headings_are_accepted(tmp_path):
    """A heading may be in either Japanese or English. A strict match would not survive use."""
    ja = (VALID.replace("## 4. Acceptance", "## 4. 受入基準")
               .replace("## 5. Success Criteria", "## 5. 成功基準")
               .replace("## 6. Constraints", "## 6. 制約")
               .replace("## 7. Out of Scope", "## 7. スコープ外"))
    code, out = run(tmp_path, ja)
    assert code == 0, out


# ── EARS ─────────────────────────────────────────────────────────────────────
def test_requirement_without_shall_is_held(tmp_path):
    bad = VALID.replace(
        "| FR-001 | When a user submits a payment report, the system shall mark it as pending |",
        "| FR-001 | システムはユーザーに通知する |")
    code, out = run(tmp_path, bad)
    assert code == 10 and "EARS" in out


def test_japanese_shall_form_is_accepted(tmp_path):
    """The Japanese 「〜すること」 is accepted as the equivalent of shall."""
    ja = VALID.replace(
        "| FR-001 | When a user submits a payment report, the system shall mark it as pending |",
        "| FR-001 | 送金報告を受けたとき、システムは確認待ちにすること |")
    code, out = run(tmp_path, ja)
    assert code == 0, out


def test_acceptance_scenarios_are_not_checked_as_requirements(tmp_path):
    """GWT is the correct notation for acceptance criteria. Having no shall is not a violation."""
    code, out = run(tmp_path, VALID)
    assert code == 0
    assert "Given" not in out or "EARS" not in out


# ── §5.2.7 the words to avoid ───────────────────────────────────────────────
def test_subjective_word_is_held(tmp_path):
    code, out = run(tmp_path, VALID.replace("立替の清算が滞留せずに完了する。",
                                            "使いやすいアプリを作る。"))
    assert code == 10 and "subjective" in out


def test_loophole_word_is_held(tmp_path):
    """「可能であれば」 ("if possible") becomes an excuse not to implement."""
    bad = VALID.replace("| FR-002 | 受領側が7日間応答しないとき、システムは自動で支払い済みとすること |",
                        "| FR-002 | 可能であれば、システムは自動で支払い済みとすること |")
    code, out = run(tmp_path, bad)
    assert code == 10 and "loophole" in out


def test_universal_and_ambiguous_conjunction_are_held(tmp_path):
    bad = VALID.replace(
        "| FR-001 | When a user submits a payment report, the system shall mark it as pending |",
        "| FR-001 | When a user logs in and/or registers, the system shall always create an account |")
    code, out = run(tmp_path, bad)
    assert code == 10
    assert "vague conjunction" in out or "universal" in out


def test_must_keyword_warns_but_does_not_hold(tmp_path):
    """`must` should be avoided as it is mistaken for a requirement (§5.2.4), but this stays a
    warning."""
    doc = VALID.replace("金額は integer（円）", "金額は integer（円）。この制約は must 満たす")
    code, out = run(tmp_path, doc)
    assert "MUST" in out
    assert code == 0, "must is a warning, not a violation"


# ── §5.2.6 Complete ──────────────────────────────────────────────────────────
def test_tbd_is_held(tmp_path):
    code, out = run(tmp_path, VALID.replace("金額は integer（円）", "TBD"))
    assert code == 10 and "TBX" in out


# ── from Spec Kit: the unresolved marker (the most important) ───────────────
def test_unresolved_clarification_marker_is_held(tmp_path):
    """The most important tooth, there so nothing is implemented while ambiguous. An agent filling
    the gaps by guessing is the largest failure mode."""
    bad = VALID.replace("金額は integer（円）",
                        "[NEEDS CLARIFICATION: 通貨は円だけか?]")
    code, out = run(tmp_path, bad)
    assert code == 10 and "CLARIFICATION" in out


# ── operation ───────────────────────────────────────────────────────────────
def test_warn_only_does_not_hold(tmp_path):
    """For the drain early after adoption (docs/11 §4e). It reports violations but exits 0."""
    code, out = run(tmp_path, VALID.replace("立替の清算が滞留せずに完了する。",
                                            "使いやすいアプリを作る。"), "--warn-only")
    assert code == 0
    assert "subjective" in out


def test_missing_file_is_a_usage_error(tmp_path):
    r = subprocess.run([sys.executable, str(TOOL), "check", str(tmp_path / "nope.md")],
                       capture_output=True, text=True)
    assert r.returncode == 2


def test_no_requirements_at_all_is_held(tmp_path):
    """A document with no requirements at all is not a statement of requirements."""
    empty = "\n".join(l for l in VALID.split("\n") if "FR-0" not in l)
    code, out = run(tmp_path, empty)
    assert code == 10 and "not one requirement statement" in out


# ── VOIDDEP was withdrawn at 0.25.1 (the object cannot be extracted from a Japanese
#    requirement) ──
# A REQUIREMENTS.md in the field held zero backtick identifiers, and the check never once fired.
# Splitting on particles was tried too, and `利用者が支出` and `メンバーが支出` came out as different
# things, making every finding a false positive.
def test_voiddep_is_not_reintroduced_without_a_way_to_extract_objects():
    """Leave the reason it was withdrawn. Reimplementing it presupposes that the object can be
    obtained reliably."""
    src = (REPO / "tools" / "req_lint.py").read_text(encoding="utf-8")
    if "VOIDDEP" in src and '"code": "VOIDDEP"' in src:
        # To revive it, show by test that it fires on a Japanese requirement (with no identifiers)
        assert False, ("to bring VOIDDEP back, show by test that it fires on a Japanese requirement "
                       "that uses no identifiers — last time it went in without that and never "
                       "once fired")
