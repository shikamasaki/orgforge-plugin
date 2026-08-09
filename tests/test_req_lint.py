"""req_lint — 要求記述が標準に適合しているかの検査（docs/11 §0b）。

docs/11 §0a は founding 成果物の *ファイル名* を固定したが、*中身の書式* を規定していなかった。
その結果 founding のたびに構成が発明され、同じ要求から違う構造の文書が出る — 「同じ spec ⇒
同じプロセス」という中核主張が要求記述の層で破れていた。この検査がその穴を塞ぐ。

準拠: ISO/IEC/IEEE 29148:2018 tailored conformance（§4.5.2 が認める適合形態）+ EARS。
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
    """規約を定義したテンプレートが、その規約に違反していてはならない。

    付録のチェックリストには禁止語が「例」として並ぶので、素朴に検査すると必ず落ちる —
    規約を正しく説明している文書ほど違反数が多くなるという不合理が起きる。"""
    r = subprocess.run([sys.executable, str(TOOL), "check",
                        str(REPO / "template" / "REQUIREMENTS.md")],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr


# ── 必須セクション ───────────────────────────────────────────────────────────
def test_missing_section_is_held(tmp_path):
    code, out = run(tmp_path, VALID.replace("## 7. Out of Scope\nPayPay API決済（既知の死）\n", ""))
    assert code == 10
    assert "out-of-scope" in out


def test_japanese_headings_are_accepted(tmp_path):
    """見出しは日英どちらでもよい。厳密一致にすると実用に耐えない。"""
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
    """日本語の「〜すること」は shall 相当として認める。"""
    ja = VALID.replace(
        "| FR-001 | When a user submits a payment report, the system shall mark it as pending |",
        "| FR-001 | 送金報告を受けたとき、システムは確認待ちにすること |")
    code, out = run(tmp_path, ja)
    assert code == 0, out


def test_acceptance_scenarios_are_not_checked_as_requirements(tmp_path):
    """受入基準は GWT で書くのが正しい。shall が無いのは違反ではない。"""
    code, out = run(tmp_path, VALID)
    assert code == 0
    assert "Given" not in out or "EARS" not in out


# ── §5.2.7 避けるべき語 ──────────────────────────────────────────────────────
def test_subjective_word_is_held(tmp_path):
    code, out = run(tmp_path, VALID.replace("立替の清算が滞留せずに完了する。",
                                            "使いやすいアプリを作る。"))
    assert code == 10 and "subjective" in out


def test_loophole_word_is_held(tmp_path):
    """「可能であれば」は実装しない口実になる。"""
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
    """`must` は要求と誤解されるので避けるべき（§5.2.4）だが、警告に留める。"""
    doc = VALID.replace("金額は integer（円）", "金額は integer（円）。この制約は must 満たす")
    code, out = run(tmp_path, doc)
    assert "MUST" in out
    assert code == 0, "must は警告であって違反ではない"


# ── §5.2.6 Complete ──────────────────────────────────────────────────────────
def test_tbd_is_held(tmp_path):
    code, out = run(tmp_path, VALID.replace("金額は integer（円）", "TBD"))
    assert code == 10 and "TBX" in out


# ── Spec Kit 由来: 未解決マーカー（最重要）────────────────────────────────────
def test_unresolved_clarification_marker_is_held(tmp_path):
    """曖昧なまま実装させないための最重要の歯。エージェントが推測で埋めるのが最大の失敗モード。"""
    bad = VALID.replace("金額は integer（円）",
                        "[NEEDS CLARIFICATION: 通貨は円だけか?]")
    code, out = run(tmp_path, bad)
    assert code == 10 and "CLARIFICATION" in out


# ── 運用 ─────────────────────────────────────────────────────────────────────
def test_warn_only_does_not_hold(tmp_path):
    """導入初期の drain 用（docs/11 §4e）。違反は報告するが exit 0。"""
    code, out = run(tmp_path, VALID.replace("立替の清算が滞留せずに完了する。",
                                            "使いやすいアプリを作る。"), "--warn-only")
    assert code == 0
    assert "subjective" in out


def test_missing_file_is_a_usage_error(tmp_path):
    r = subprocess.run([sys.executable, str(TOOL), "check", str(tmp_path / "nope.md")],
                       capture_output=True, text=True)
    assert r.returncode == 2


def test_no_requirements_at_all_is_held(tmp_path):
    """要求が1件もない文書は要求記述ではない。"""
    empty = "\n".join(l for l in VALID.split("\n") if "FR-0" not in l)
    code, out = run(tmp_path, empty)
    assert code == 10 and "not one requirement statement" in out


# ── VOIDDEP は 0.25.1 で取り下げた（日本語の要求から目的語を切り出せない）──────
# 実地の REQUIREMENTS.md にバッククォート識別子は 0 件で、検査が一度も発火しなかった。
# 助詞で区切る実装も試したが `利用者が支出` と `メンバーが支出` が別物になり全件誤検出。
def test_voiddep_is_not_reintroduced_without_a_way_to_extract_objects():
    """取り下げた理由を残す。再実装するなら、目的語を確実に取れる前提が要る。"""
    src = (REPO / "tools" / "req_lint.py").read_text(encoding="utf-8")
    if "VOIDDEP" in src and '"code": "VOIDDEP"' in src:
        # 復活させるなら、日本語の要求（識別子なし）で発火することをテストで示すこと
        assert False, ("VOIDDEP を戻すなら、識別子を使わない日本語の要求で発火することを"
                       "テストで示すこと — 前回はそれをせずに入れ、一度も発火しなかった")
