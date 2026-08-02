"""github_sync — the backlog↔GitHub-Issue projection (integrations/web).

`gh` is the network boundary; we monkeypatch `github_sync.gh` so these tests exercise the org's LOGIC
(the two-level objective/task hierarchy, the idempotent work-log, dependency/kind filtering, sub-issue
linking) without touching GitHub. The one thing we assert is that the org builds the right gh calls and
makes the right decisions from their results — the reproducible, testable part."""
import importlib.util
import hashlib
import json
import os
import pathlib
import sys
import pytest


def _real_ids(org):
    """その org の (org_id, ledger_id)。**書き込み先から決まる値**に receipt を合わせる。"""
    sys.path.insert(0, str(REPO / "tools"))
    import importlib
    led = importlib.import_module("ledger")
    import os as _os
    cwd = _os.getcwd()
    try:
        _os.chdir(org)
        return led._org_and_ledger_id(str(org / ".orgforge" / "ledger"))
    finally:
        _os.chdir(cwd)

REPO = pathlib.Path(__file__).resolve().parent.parent
# github_sync は tools/ghsync/ に分割された（0.22.0）。テストは「どのモジュールに居るか」
# ではなく振る舞いを見たいので、全モジュールの名前を1つの名前空間に集めたビューを使う。
# `monkeypatch.setattr(GS, "gh", fake)` が全モジュールに効くよう、gh の差し替えは
# 各モジュールにも伝播させる（下の _patch_gh_everywhere）。
sys.path.insert(0, str(REPO / "tools"))
import types as _types
from ghsync import _core as _gh_core, backlog as _gh_backlog, record as _gh_record,     branch as _gh_branch, coverage as _gh_coverage

_GH_MODS = (_gh_core, _gh_backlog, _gh_record, _gh_branch, _gh_coverage)


class _Facade(_types.ModuleType):
    """全 ghsync モジュールの統合ビュー。setattr は全モジュールに伝播する。"""

    def __getattr__(self, name):
        for m in _GH_MODS:
            if hasattr(m, name):
                return getattr(m, name)
        raise AttributeError(name)

    def __setattr__(self, name, value):
        hit = False
        for m in _GH_MODS:
            if hasattr(m, name):
                setattr(m, name, value)
                hit = True
        if not hit:
            object.__setattr__(self, name, value)


GS = _Facade("github_sync_facade")


class FakeGh:
    """Record every gh call; reply from a scripted queue keyed by a substring of the joined args."""
    def __init__(self, replies=None):
        self.calls = []
        self.replies = replies or {}

    def __call__(self, args, check=True):
        self.calls.append(args)
        joined = " ".join(args)
        for key, (code, out) in self.replies.items():
            if key in joined:
                return code, out
        return 0, ""

    def calls_matching(self, needle):
        return [c for c in self.calls if needle in " ".join(c)]


def _ns(**kw):
    import argparse
    return argparse.Namespace(**kw)


# ── helpers ──────────────────────────────────────────────────────────────────
def test_issue_number_parsed_from_url():
    assert GS._issue_number("https://github.com/o/r/issues/42") == 42
    assert GS._issue_number("  https://github.com/o/r/issues/7\n") == 7
    assert GS._issue_number("not a url") is None


def test_repair_body_is_reachable_through_cli_dispatch():
    spec = importlib.util.spec_from_file_location("github_sync_cli", REPO / "tools" / "github_sync.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    rc = module.main(["github_sync.py", "repair-body", "--repo", "o/r", "--issue", "5",
                      "--body", "placeholder", "--reason", "repair missing context"])
    assert rc == 2


# ── two-level hierarchy: objective vs task ───────────────────────────────────
def test_create_objective_labels_kind_objective(monkeypatch):
    fake = FakeGh(replies={"issue create": (0, "https://github.com/o/r/issues/10")})
    monkeypatch.setattr(GS, "gh", fake)
    rc = GS.cmd_create(_ns(repo="o/r", title="Ship the settle-up app", body="Objective context",
                           objective="obj1",
                           source=None, depends=None, priority=None, kind="objective",
                           dept=None, parent=None))
    assert rc == 0
    create = fake.calls_matching("issue create")[0]
    assert "orgforge:kind:objective" in create
    assert "orgforge:objective:obj1" in create


def test_create_task_with_parent_links_native_sub_issue(monkeypatch):
    fake = FakeGh(replies={
        "issue list": (0, "[]"),                                   # no existing issue (not a replay)
        "issue create": (0, "https://github.com/o/r/issues/23"),   # the new task's number
        "issues/23": (0, "9999"),                                  # its database id (for sub_issues)
        "sub_issues": (0, ""),                                     # link succeeds
    })
    monkeypatch.setattr(GS, "gh", fake)
    rc = GS.cmd_create(_ns(repo="o/r", title="build money core", body="Task context", objective="obj1",
                           source=None, depends=None, priority=None, kind="task",
                           dept="engineering", parent="10"))
    assert rc == 0
    create = fake.calls_matching("issue create")[0]
    assert "orgforge:kind:task" in create and "orgforge:dept:engineering" in create
    # a native sub-issue POST was made under the parent (#10) with the child's db id
    subs = fake.calls_matching("sub_issues")
    assert subs and "issues/10/sub_issues" in " ".join(subs[0]) and "sub_issue_id=9999" in " ".join(subs[0])


def test_sub_issue_link_treats_already_linked_as_idempotent(monkeypatch):
    # GitHub returns a non-zero + "duplicate sub-issues / one parent" message when the link exists;
    # that is a no-op for us, not a failure (a replayed create must not warn). Regression from a live test.
    for msg in ("Issue may not contain duplicate sub-issues",
                "Sub issue may only have one parent",
                "sub_issue already exists"):
        fake = FakeGh(replies={"issues/9": (0, "12345"), "sub_issues": (1, msg)})
        monkeypatch.setattr(GS, "gh", fake)
        ok, detail = GS._link_sub_issue("o/r", 5, 9)
        assert ok, f"already-linked ({msg!r}) must be idempotent-OK, got: {detail}"


def test_create_is_idempotent_on_existing_open_issue(monkeypatch):
    # an open issue with the same title+objective already exists → no second create
    existing = '[{"number": 5, "title": "build money core", "labels": [{"name": "orgforge:objective:obj1"}]}]'
    fake = FakeGh(replies={"issue list": (0, existing),
                           "issue view": (0, json.dumps({"body": "Task context"}))})
    monkeypatch.setattr(GS, "gh", fake)
    rc = GS.cmd_create(_ns(repo="o/r", title="build money core", body="Task context", objective="obj1",
                           source=None, depends=None, priority=None, kind="task", dept=None, parent=None))
    assert rc == 0
    assert not fake.calls_matching("issue create"), "must NOT create a duplicate"


@pytest.mark.parametrize("body", [None, "", "  \n", "(no body)", "TBD", "placeholder", "x",
                                  "<!-- generated placeholder -->"])
def test_create_rejects_empty_or_placeholder_body_before_github_write(monkeypatch, body):
    fake = FakeGh(); monkeypatch.setattr(GS, "gh", fake)
    rc = GS.cmd_create(_ns(repo="o/r", title="T", body=body, objective=None, source=None,
                           depends=None, priority=None, kind="task", dept=None, parent=None))
    assert rc == 2
    assert not fake.calls


def test_create_existing_placeholder_requires_explicit_repair(monkeypatch, capsys):
    listing = '[{"number": 5, "title": "T", "state": "OPEN", "labels": []}]'
    fake = FakeGh(replies={"issue list": (0, listing),
                           "issue view": (0, json.dumps({"body": "(no body)"}))})
    monkeypatch.setattr(GS, "gh", fake)
    rc = GS.cmd_create(_ns(repo="o/r", title="T", body="Correct context", objective=None,
                           source=None, depends=None, priority=None, kind="task", dept=None,
                           parent=None))
    out = capsys.readouterr().err
    assert rc == 10 and "repair-body" in out and "old_sha256=" in out and "new_sha256=" in out
    assert not fake.calls_matching("issue create") and not fake.calls_matching("issue edit")


def test_create_existing_different_nonempty_body_is_not_silent(monkeypatch, capsys):
    listing = '[{"number": 5, "title": "T", "state": "OPEN", "labels": []}]'
    fake = FakeGh(replies={"issue list": (0, listing),
                           "issue view": (0, json.dumps({"body": "Earlier valid context"}))})
    monkeypatch.setattr(GS, "gh", fake)
    rc = GS.cmd_create(_ns(repo="o/r", title="T", body="Different valid context", objective=None,
                           source=None, depends=None, priority=None, kind="task", dept=None,
                           parent=None))
    out = capsys.readouterr().err
    assert rc == 10 and "differs" in out and "repair-body" in out
    assert "Earlier valid context" not in out and "Different valid context" not in out


def test_repair_body_records_digests_actor_and_reason(monkeypatch):
    fake = FakeGh(replies={"issue view": (0, json.dumps({"body": "(no body)"})),
                           "api user": (0, "octocat\n"), "issue edit": (0, ""),
                           "issue comment": (0, "")})
    monkeypatch.setattr(GS, "gh", fake)
    rc = GS.cmd_repair_body(_ns(repo="o/r", issue=5, body="Correct context",
                                reason="restore missing decomposition context"))
    assert rc == 0
    edit = fake.calls_matching("issue edit")[0]
    assert edit[edit.index("--body") + 1] == "Correct context"
    comment = fake.calls_matching("issue comment")[0]
    audit = comment[comment.index("--body") + 1]
    assert "#5" in audit and "octocat" in audit and "old_sha256" in audit and "new_sha256" in audit
    assert hashlib.sha256(b"(no body)").hexdigest() in audit
    assert hashlib.sha256(b"Correct context").hexdigest() in audit
    assert "restore missing decomposition context" in audit
    assert "(no body)" not in audit and "Correct context" not in audit


def test_repair_body_rolls_back_when_audit_comment_fails(monkeypatch):
    class AuditFailureGh(FakeGh):
        def __call__(self, args, check=True):
            self.calls.append(args)
            joined = " ".join(args)
            if "issue view" in joined:
                return 0, json.dumps({"body": "old context"})
            if "api user" in joined:
                return 0, "octocat"
            if "issue comment" in joined:
                return 1, "comment denied"
            return 0, ""
    fake = AuditFailureGh(); monkeypatch.setattr(GS, "gh", fake)
    rc = GS.cmd_repair_body(_ns(repo="o/r", issue=5, body="new context", reason="repair"))
    assert rc == 2
    edits = fake.calls_matching("issue edit")
    assert len(edits) == 2
    assert edits[0][edits[0].index("--body") + 1] == "new context"
    assert edits[1][edits[1].index("--body") + 1] == "old context"


def test_repair_body_github_update_failure_records_no_success(monkeypatch):
    fake = FakeGh(replies={"issue view": (0, json.dumps({"body": "old context"})),
                           "api user": (0, "octocat"), "issue edit": (1, "edit denied")})
    monkeypatch.setattr(GS, "gh", fake)
    rc = GS.cmd_repair_body(_ns(repo="o/r", issue=5, body="new context", reason="repair"))
    assert rc == 2
    assert not fake.calls_matching("issue comment")


def test_repair_body_same_valid_body_is_idempotent_without_write(monkeypatch):
    fake = FakeGh(replies={"issue view": (0, json.dumps({"body": "valid context\n"}))})
    monkeypatch.setattr(GS, "gh", fake)
    rc = GS.cmd_repair_body(_ns(repo="o/r", issue=5, body="valid context", reason="replay"))
    assert rc == 0
    assert not fake.calls_matching("issue edit") and not fake.calls_matching("issue comment")


# ── work-log: idempotent per ledger event id ─────────────────────────────────
def test_log_posts_a_comment_with_hidden_marker(monkeypatch):
    fake = FakeGh(replies={"issue view": (0, '{"comments": []}'), "issue comment": (0, "")})
    monkeypatch.setattr(GS, "gh", fake)
    rc = GS.cmd_log(_ns(repo="o/r", issue=23, event="progress_recorded",
                        detail="core money math done", phase="implement", event_id="evABC"))
    assert rc == 0
    comment = fake.calls_matching("issue comment")[0]
    body = comment[comment.index("--body") + 1]
    assert "progress_recorded" in body and "implement" in body
    assert "<!-- orgforge:event:evABC -->" in body


def test_log_is_idempotent_when_event_already_logged(monkeypatch):
    # the Issue already has a comment carrying this event id → no second comment
    existing = '{"comments": [{"body": "**cycle_started**\\n\\n<!-- orgforge:event:evABC -->"}]}'
    fake = FakeGh(replies={"issue view": (0, existing)})
    monkeypatch.setattr(GS, "gh", fake)
    rc = GS.cmd_log(_ns(repo="o/r", issue=23, event="cycle_started",
                        detail=None, phase=None, event_id="evABC",
                        command="npm test", result="Test Files 1 passed | Tests 54 passed (54)"))
    assert rc == 0
    assert not fake.calls_matching("issue comment"), "must NOT double-post the same milestone"


# ── ready: tasks by default, objectives excluded ─────────────────────────────
def test_branch_name_is_deterministic_and_off_develop(monkeypatch):
    fake = FakeGh(replies={"issue view": (0, '{"title": "Add login endpoint"}')})
    monkeypatch.setattr(GS, "gh", fake)
    import io, contextlib
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = GS.cmd_branch(_ns(repo="o/r", issue=42, create=False, base=None))
    assert rc == 0
    assert buf.getvalue().strip() == "feat/issue-42-add-login-endpoint"


def test_branch_japanese_title_falls_back_to_stable_hash(monkeypatch):
    # a Japanese task title (output_language: ja) must NOT collapse to an empty/meaningless slug
    fake = FakeGh(replies={"issue view": (0, '{"title": "領域A: 認証 + プロジェクト"}')})
    monkeypatch.setattr(GS, "gh", fake)
    import io, contextlib
    out = []
    for _ in range(2):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            GS.cmd_branch(_ns(repo="o/r", issue=6, create=False, base=None))
        out.append(buf.getvalue().strip())
    assert out[0] == out[1], "same Issue must yield the same branch (reproducible)"
    assert out[0].startswith("feat/issue-6-t") and len(out[0]) > len("feat/issue-6-"), out[0]


def test_slug_helper_distinct_titles_differ():
    assert GS._slug("領域A: 認証") != GS._slug("領域B: 支出")
    assert GS._slug("Add login") == GS._slug("Add login")


def test_split_check_flags_owns_spanning_territories(monkeypatch):
    body = "## Seam\\n- **owns:** `app/auth/`, `app/billing/`\\n"
    fake = FakeGh(replies={"issue view": (0, '{"body": "' + body + '", "title": "big"}')})
    monkeypatch.setattr(GS, "gh", fake)
    import io, contextlib
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = GS.cmd_split_check(_ns(repo="o/r", issue=9))
    assert rc == 10 and "territories" in buf.getvalue(), buf.getvalue()


def test_split_check_clean_on_single_territory(monkeypatch):
    body = "## Seam\\n- **owns:** `app/packages/auth/`\\n"
    fake = FakeGh(replies={"issue view": (0, '{"body": "' + body + '", "title": "ok"}')})
    monkeypatch.setattr(GS, "gh", fake)
    import io, contextlib
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = GS.cmd_split_check(_ns(repo="o/r", issue=9))
    assert rc == 0 and "shape OK" in buf.getvalue(), buf.getvalue()


def test_split_check_flags_prose_must_not_in_ears(monkeypatch):
    # a MUST section written as prose ("auth works") with no EARS keyword must be flagged
    body = json.dumps({"body": "## MUST\n- [ ] auth works\n- **owns:** `app/auth/`\n", "title": "t"})
    fake = FakeGh(replies={"issue view": (0, body)})
    monkeypatch.setattr(GS, "gh", fake)
    import io, contextlib
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = GS.cmd_split_check(_ns(repo="o/r", issue=9))
    assert rc == 10 and "EARS" in buf.getvalue(), buf.getvalue()


def test_split_check_clean_when_must_is_ears(monkeypatch):
    body = json.dumps({"body": "## MUST\n- [ ] WHEN login THE system SHALL validate\n"
                               "- **owns:** `app/auth/`\n", "title": "t"})
    fake = FakeGh(replies={"issue view": (0, body)})
    monkeypatch.setattr(GS, "gh", fake)
    import io, contextlib
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = GS.cmd_split_check(_ns(repo="o/r", issue=9))
    assert rc == 0, buf.getvalue()


def test_ready_lists_tasks_and_excludes_objectives(monkeypatch):
    listing = ('[{"number": 1, "title": "t", "labels": [{"name": "orgforge:kind:task"}], "body": ""},'
               ' {"number": 2, "title": "o", "labels": [{"name": "orgforge:kind:objective"}], "body": ""}]')
    fake = FakeGh(replies={"issue list": (0, listing)})
    monkeypatch.setattr(GS, "gh", fake)
    import io, contextlib
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = GS.cmd_ready(_ns(repo="o/r", kind="task"))
    assert rc == 0
    out = buf.getvalue()
    assert '"ready": [1]' in out, out   # only the task, not the objective


# ── the decomposition coverage gate (docs/11 §0a) ────────────────────────────
# /org-found's O10 lint proves each must-have has ONE owning contract (design layer). coverage-check is
# the same guarantee one layer down: every must-have must have reached a task Issue, traced by the
# `coverage_row:` trailer /org-decompose writes. A must-have designed but never decomposed is silently
# unbuilt — the hardest gap to see, so it must FAIL, not warn.
MANIFEST = (
    "# Coverage manifest\n\n"
    "| rfp_capability | owning_role | deliverable | acceptance |\n"
    "|---|---|---|---|\n"
    "| 割り勘計算 | settlement | split engine | WHEN 3人でEQUAL分割 THE system SHALL 端数を先頭に寄せる |\n"
    "| OAuthログイン | identity | auth service | WHEN OAuth completes THE system SHALL create one account |\n"
    "| <placeholder row> | x | y | z |\n"
)


def _manifest_file(tmp_path, text=MANIFEST):
    p = tmp_path / "coverage-manifest.md"
    p.write_text(text, encoding="utf-8")
    return str(p)


def _cov(monkeypatch, tmp_path, issues, manifest=MANIFEST):
    import io, contextlib
    fake = FakeGh(replies={"issue list": (0, json.dumps(issues))})
    monkeypatch.setattr(GS, "gh", fake)
    buf, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(err):
        rc = GS.cmd_coverage_check(_ns(repo="o/r", manifest=_manifest_file(tmp_path, manifest)))
    return rc, buf.getvalue() + err.getvalue()


def test_manifest_parser_reads_named_columns_and_skips_placeholders(tmp_path):
    rows = GS._manifest_rows(_manifest_file(tmp_path))
    assert [r["rfp_capability"] for r in rows] == ["割り勘計算", "OAuthログイン"]
    assert rows[0]["owning_role"] == "settlement"
    assert "SHALL" in rows[0]["acceptance"]


def test_coverage_check_passes_when_every_must_have_reached_an_issue(monkeypatch, tmp_path):
    issues = [{"number": 11, "state": "OPEN", "body": "coverage_row: 割り勘計算"},
              {"number": 12, "state": "OPEN", "body": "coverage_row: OAuthログイン"}]
    rc, out = _cov(monkeypatch, tmp_path, issues)
    assert rc == 0, out
    assert "2/2" in out


def test_coverage_check_fails_on_a_must_have_with_no_task_issue(monkeypatch, tmp_path):
    """The gate's whole reason to exist: a designed-but-undecomposed must-have must exit non-zero."""
    issues = [{"number": 11, "state": "OPEN", "body": "coverage_row: 割り勘計算"}]
    rc, out = _cov(monkeypatch, tmp_path, issues)
    assert rc == 10, out
    assert "COVERAGE GAP" in out and "OAuthログイン" in out


def test_coverage_check_flags_a_paraphrased_trailer_as_an_orphan(monkeypatch, tmp_path):
    """A trailer must match the manifest cell verbatim — a paraphrase would otherwise hide a real gap."""
    issues = [{"number": 11, "state": "OPEN", "body": "coverage_row: 割り勘計算"},
              {"number": 13, "state": "OPEN", "body": "coverage_row: OAuthろぐいん"}]
    rc, out = _cov(monkeypatch, tmp_path, issues)
    assert rc == 10, out
    assert "ORPHAN" in out and "OAuthログイン" in out   # the gap is still reported, not masked


def test_coverage_check_tolerates_self_raised_issues_without_a_trailer(monkeypatch, tmp_path):
    """/org-discover items legitimately carry no coverage_row — a note, never a failure."""
    issues = [{"number": 11, "state": "OPEN", "body": "coverage_row: 割り勘計算"},
              {"number": 12, "state": "OPEN", "body": "coverage_row: OAuthログイン"},
              {"number": 99, "state": "OPEN", "body": "a self-raised refactor, no trailer"}]
    rc, out = _cov(monkeypatch, tmp_path, issues)
    assert rc == 0, out
    assert "#99" in out   # surfaced as a note


def test_coverage_check_counts_a_closed_issue_as_covered(monkeypatch, tmp_path):
    """Coverage asks 'did it become work?', not 'is it still open' — a shipped must-have is covered."""
    issues = [{"number": 11, "state": "CLOSED", "body": "coverage_row: 割り勘計算"},
              {"number": 12, "state": "CLOSED", "body": "coverage_row: OAuthログイン"}]
    rc, out = _cov(monkeypatch, tmp_path, issues)
    assert rc == 0, out


def test_coverage_check_errors_when_the_manifest_has_no_parsable_rows(monkeypatch, tmp_path):
    """A manifest under a variant name/shape must be a loud error, never a silent 0/0 pass."""
    rc, out = _cov(monkeypatch, tmp_path, [], manifest="# design doc\n\nno table here\n")
    assert rc == 2, out
    assert "rfp_capability" in out


def test_coverage_check_missing_manifest_is_an_error_not_a_pass(monkeypatch, tmp_path):
    import io, contextlib
    monkeypatch.setattr(GS, "gh", FakeGh())
    buf, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(err):
        rc = GS.cmd_coverage_check(_ns(repo="o/r", manifest=str(tmp_path / "nope.md")))
    assert rc == 2


# ── coverage gate: the review-found defects, as regressions ──────────────────
def test_manifest_parser_ignores_a_table_that_follows_the_manifest(tmp_path):
    """/org-found emits an EXCLUDE list alongside the manifest. If a trailing table inherited the
    manifest's header, its rows would read as must-haves — and since the decomposer works until
    coverage-check is green, the org would build exactly the scope the CEO cut."""
    text = MANIFEST + ("\n## Excluded from the first cut\n\n"
                       "| capability | reason |\n|---|---|\n"
                       "| Group splitting | deferred to v2 |\n| Receipt OCR | out of scope |\n")
    rows = GS._manifest_rows(_manifest_file(tmp_path, text))
    caps = [r["rfp_capability"] for r in rows]
    assert caps == ["割り勘計算", "OAuthログイン"], caps
    assert "Receipt OCR" not in caps and "capability" not in caps


def test_coverage_check_matches_a_bold_wrapped_trailer(monkeypatch, tmp_path):
    """An agent writing the body in the org's output_language may bold the label. Splitting the raw
    line would leave a leading space and report a GAP for a row that IS covered."""
    issues = [{"number": 11, "state": "OPEN", "labels": [], "body": "**coverage_row:** 割り勘計算"},
              {"number": 12, "state": "OPEN", "labels": [], "body": "- `coverage_row:` OAuthログイン"}]
    rc, out = _cov(monkeypatch, tmp_path, issues)
    assert rc == 0, out


def test_coverage_check_fails_a_mandate_task_with_no_trailer(monkeypatch, tmp_path):
    """A MISSING trailer on an RFP-derived task is invisible to the row-side check when another Issue
    covers the same row — so it must fail on the Issue side, like a mistyped one does."""
    issues = [{"number": 11, "state": "OPEN", "labels": [{"name": "orgforge:mandate"}],
               "body": "coverage_row: 割り勘計算"},
              {"number": 12, "state": "OPEN", "labels": [{"name": "orgforge:mandate"}],
               "body": "coverage_row: OAuthログイン"},
              {"number": 13, "state": "OPEN", "labels": [{"name": "orgforge:mandate"}],
               "body": "an RFP task whose trailer was forgotten"}]
    rc, out = _cov(monkeypatch, tmp_path, issues)
    assert rc == 10, out
    assert "UNTRACED MANDATE" in out and "#13" in out


def test_coverage_check_still_tolerates_a_self_labelled_task_with_no_trailer(monkeypatch, tmp_path):
    issues = [{"number": 11, "state": "OPEN", "labels": [{"name": "orgforge:mandate"}],
               "body": "coverage_row: 割り勘計算"},
              {"number": 12, "state": "OPEN", "labels": [{"name": "orgforge:mandate"}],
               "body": "coverage_row: OAuthログイン"},
              {"number": 13, "state": "OPEN", "labels": [{"name": "orgforge:self"}],
               "body": "a self-raised refactor"}]
    rc, out = _cov(monkeypatch, tmp_path, issues)
    assert rc == 0, out


def test_create_does_not_remint_a_closed_delivered_issue(monkeypatch):
    """`stage done` CLOSES a task. An open-only idempotency search would re-mint every delivered task
    on the documented 're-run after a manifest amendment' repair path."""
    listing = ('[{"number": 42, "title": "split engine", "state": "CLOSED",'
               ' "labels": [{"name": "orgforge:objective:obj1"}]}]')
    fake = FakeGh(replies={"issue list": (0, listing),
                           "issue view": (0, json.dumps({"body": "Delivered task context"}))})
    monkeypatch.setattr(GS, "gh", fake)
    import io, contextlib
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = GS.cmd_create(_ns(repo="o/r", title="split engine", body="Delivered task context",
                               objective="obj1",
                               source="mandate", depends=None, priority=None, kind="task",
                               dept="settlement", parent=None))
    assert rc == 0
    assert not fake.calls_matching("issue create"), "re-minted a delivered task"
    assert "CLOSED" in buf.getvalue()


def test_stage_ready_reopens_a_closed_issue_before_labeling(monkeypatch):
    snapshot = '{"state":"CLOSED","labels":[{"name":"orgforge:done"}]}'
    fake = FakeGh(replies={"issue view": (0, snapshot)})
    monkeypatch.setattr(GS, "gh", fake)

    rc = GS.cmd_stage(_ns(repo="o/r", issue=42, stage="ready"))

    assert rc == 0
    reopen = fake.calls_matching("issue reopen")
    edit = fake.calls_matching("issue edit")
    assert len(reopen) == 1
    assert len(edit) == 1
    assert fake.calls.index(reopen[0]) < fake.calls.index(edit[0])
    assert "orgforge:ready" in edit[0]
    assert "orgforge:done" in edit[0]


def test_stage_ready_keeps_an_open_issue_open(monkeypatch):
    snapshot = '{"state":"OPEN","labels":[{"name":"orgforge:in-progress"}]}'
    fake = FakeGh(replies={"issue view": (0, snapshot)})
    monkeypatch.setattr(GS, "gh", fake)

    rc = GS.cmd_stage(_ns(repo="o/r", issue=42, stage="ready"))

    assert rc == 0
    assert not fake.calls_matching("issue reopen")
    assert len(fake.calls_matching("issue edit")) == 1


def test_stage_ready_stops_when_reopen_fails(monkeypatch):
    snapshot = '{"state":"CLOSED","labels":[{"name":"orgforge:done"}]}'
    fake = FakeGh(replies={"issue view": (0, snapshot),
                           "issue reopen": (1, "permission denied")})
    monkeypatch.setattr(GS, "gh", fake)

    rc = GS.cmd_stage(_ns(repo="o/r", issue=42, stage="ready"))

    assert rc == 2
    assert not fake.calls_matching("issue edit"), "reopen failure must not claim a ready transition"


def test_stage_ready_recloses_when_relabel_fails_after_reopen(monkeypatch):
    snapshot = '{"state":"CLOSED","labels":[{"name":"orgforge:done"}]}'
    fake = FakeGh(replies={"issue view": (0, snapshot),
                           "issue edit": (1, "label API unavailable")})
    monkeypatch.setattr(GS, "gh", fake)

    rc = GS.cmd_stage(_ns(repo="o/r", issue=42, stage="ready"))

    assert rc == 2
    assert len(fake.calls_matching("issue reopen")) == 1
    assert len(fake.calls_matching("issue close")) == 1


def test_stage_ready_reports_partial_failure_when_compensating_close_fails(monkeypatch):
    snapshot = '{"state":"CLOSED","labels":[{"name":"orgforge:done"}]}'
    fake = FakeGh(replies={"issue view": (0, snapshot),
                           "issue edit": (1, "label API unavailable"),
                           "issue close": (1, "close API unavailable")})
    monkeypatch.setattr(GS, "gh", fake)

    rc = GS.cmd_stage(_ns(repo="o/r", issue=42, stage="ready"))

    assert rc == 10
    assert len(fake.calls_matching("issue close")) == 1


def test_stage_done_does_not_close_an_already_closed_issue_again(monkeypatch):
    snapshot = '{"state":"CLOSED","labels":[{"name":"orgforge:done"}]}'
    fake = FakeGh(replies={"issue view": (0, snapshot)})
    monkeypatch.setattr(GS, "gh", fake)

    rc = GS.cmd_stage(_ns(repo="o/r", issue=42, stage="done"))

    assert rc == 0
    assert not fake.calls_matching("issue reopen")
    assert not fake.calls_matching("issue close")


# ── the audit record: judgments + granular work log (docs/11 §4f) ────────────
# Human diff review is retired, so an unrecorded judgment is indistinguishable from no judgment, and a
# terse work log records nothing recoverable. Both degradations are closed at the tool, not left to
# discipline.
class CommentGh(FakeGh):
    """A FakeGh that accumulates posted comments and serves them back on `issue view`."""
    def __init__(self):
        super().__init__()
        self.posted = []

    def __call__(self, args, check=True):
        self.calls.append(args)
        if args[:2] == ["issue", "view"]:
            return 0, json.dumps({"comments": [{"body": b} for b in self.posted]})
        if args[:2] == ["issue", "comment"]:
            self.posted.append(args[args.index("--body") + 1])
            return 0, "ok"
        return 0, ""


@pytest.fixture(autouse=True)
def _isolated_ledger(tmp_path, monkeypatch):
    """decide は台帳にも書くようになったので（0.21.0 で二重打ちをやめた）、
    テストごとに使い捨ての台帳ルートを与える。実 org の台帳を汚さない。"""
    monkeypatch.setenv("ORG_LEDGER_ROOT", str(tmp_path / "led"))
    yield


def _decide_ns(**kw):
    base = dict(repo="o/r", issue=5, event="admission_decided", verdict="admit",
                why="all three MUSTs have failing-then-passing tests; the placebo was rejected",
                by="gate", phase=None, evidence="npm test → 19 passed", alternatives=None,
                standard=None, risk=None, event_id="ev-1")
    base.update(kw)
    return _ns(**base)


def _quiet(fn, *a):
    import io, contextlib
    buf, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(err):
        rc = fn(*a)
    return rc, buf.getvalue() + err.getvalue()


def test_decide_rejects_a_why_that_restates_the_verdict(monkeypatch):
    """A bare 'admitted' is the rubber stamp this command exists to prevent."""
    fake = CommentGh(); monkeypatch.setattr(GS, "gh", fake)
    rc, out = _quiet(GS.cmd_decide, _decide_ns(why="admitted"))
    assert rc == 2, out
    assert not fake.posted


def test_decide_rejects_a_non_judgment_event(monkeypatch):
    fake = CommentGh(); monkeypatch.setattr(GS, "gh", fake)
    rc, out = _quiet(GS.cmd_decide, _decide_ns(event="progress_recorded"))
    assert rc == 2 and not fake.posted
    assert "judgment class" in out


def test_decide_posts_verdict_reasoning_and_the_no_human_notice(monkeypatch):
    fake = CommentGh(); monkeypatch.setattr(GS, "gh", fake)
    rc, _ = _quiet(GS.cmd_decide, _decide_ns(
        why="全MUSTに対応するテストが緑。11人目の参加がcapエラーで拒否されることを実機確認した。",
        evidence="npm test → 19 passed", alternatives="末尾寄せ案は既存規約と矛盾するため却下",
        standard="端数は先頭に寄せる", risk="並行joinのレースは未検証", phase="test"))
    assert rc == 0
    body = fake.posted[0]
    for expected in ("admission_decided", "`admit`", "Why (the reasoning)", "Evidence consulted",
                     "Alternatives considered", "Standard applied", "Known risk accepted",
                     "No human reviewed this change"):
        assert expected in body, f"{expected!r} missing from:\n{body}"


def test_decide_is_idempotent_on_replay(monkeypatch):
    fake = CommentGh(); monkeypatch.setattr(GS, "gh", fake)
    _quiet(GS.cmd_decide, _decide_ns())
    rc, out = _quiet(GS.cmd_decide, _decide_ns())
    assert rc == 0 and len(fake.posted) == 1, out


def test_decide_records_a_rejection_too(monkeypatch):
    fake = CommentGh(); monkeypatch.setattr(GS, "gh", fake)
    rc, _ = _quiet(GS.cmd_decide, _decide_ns(
        verdict="reject", why="EARS MUST 2 has no test; the placebo output passes the letter of the "
                              "criterion while failing its intent."))
    assert rc == 0 and "`reject`" in fake.posted[0]


def _log_ns(**kw):
    base = dict(repo="o/r", issue=5, event="progress_recorded", detail="実装中", phase="implement",
                event_id="ev-9", command=None, result=None, files=None, next_step=None,
                blocked_by=None)
    base.update(kw)
    return _ns(**base)


def test_progress_receipt_uses_declared_blocked_by_field(monkeypatch):
    """The projection must not emit the undeclared legacy ``blocker`` key."""
    captured = {}

    class Result:
        returncode = 0
        stdout = "appended seq=1\n"
        stderr = ""

    def fake_run(args, **kwargs):
        captured["args"] = args
        return Result()

    monkeypatch.delenv("ORG_WRITER_SOCKET", raising=False)
    monkeypatch.setattr(_gh_record.subprocess, "run", fake_run)
    ok, out = GS._append_progress_receipt(
        _log_ns(blocked_by="reviewer unavailable", next_step="retry with Codex"))
    assert ok, out
    args = captured["args"]
    payload = json.loads(args[args.index("--payload") + 1])
    assert payload["blocked_by"] == "reviewer unavailable"
    assert "blocker" not in payload


def test_log_records_the_command_and_its_real_output(monkeypatch):
    """A log of only successes is a fiction — a failing result must round-trip verbatim."""
    fake = CommentGh(); monkeypatch.setattr(GS, "gh", fake)
    rc, _ = _quiet(GS.cmd_log, _log_ns(
        command="cd app && npm test -- split.test.ts",
        result="FAIL split.test.ts:14 — expected [34,33,33] got [33,33,34]\n1 failed, 18 passed",
        files="app/src/settlement/split.ts", next_step="reduceの初期値を修正",
        blocked_by="なし"))
    assert rc == 0
    body = fake.posted[0]
    assert "cd app && npm test -- split.test.ts" in body
    assert "1 failed, 18 passed" in body          # the failure is recorded, not smoothed over
    assert "Next step" in body and "Files" in body


def test_log_without_the_detail_fields_still_works(monkeypatch):
    """Backwards compatible: the enriched fields are optional, so existing callers keep working."""
    fake = CommentGh(); monkeypatch.setattr(GS, "gh", fake)
    rc, _ = _quiet(GS.cmd_log, _log_ns())
    assert rc == 0 and "progress_recorded" in fake.posted[0]


# ── the review-found defects in the audit layer, as regressions ──────────────
def test_stable_key_is_identical_across_processes():
    """hash() is salted per interpreter, so a CLI marker built from it never dedups across runs —
    the 'logs once, never twice' guarantee would hold only within one process."""
    import subprocess as sp
    outs = {sp.run([sys.executable, "-c",
                    "import sys;sys.path.insert(0,'tools');"
                    "from ghsync._core import _stable_key;"
                    "print(_stable_key('progress_recorded','did a thing','implement'))"],
                   capture_output=True, text=True, cwd=str(REPO)).stdout.strip() for _ in range(3)}
    assert len(outs) == 1 and outs != {""}, outs


def test_decide_rejects_padding_and_repetition_but_accepts_japanese():
    """A pure length bound fails both ways: it passes 'admit admit admit' and rejects real Japanese
    reasoning (CJK carries ~2-3x the information per codepoint, and the org's default language is ja)."""
    reject = ["admit admit admit admit admit", "The verdict is admit. Admit.",
              "aaaaaaaaaaaaaaaaaaaaaaaaaaaa", "....................",
              "it looks fine to me okay ok"]
    accept = ["テスト全通過のため許可した", "全テスト通過を確認。cap近傍の並行joinは未検証",
              "Placebo rejected; all three MUSTs covered by failing-then-passing tests"]
    for w in reject:
        assert GS._reasoning_defect(w, "admit", "admission_decided"), f"should reject: {w!r}"
    for w in accept:
        assert GS._reasoning_defect(w, "admit", "admission_decided") is None, f"should accept: {w!r}"


def test_decide_requires_evidence_for_an_admitting_verdict(monkeypatch):
    """An admission with nothing consulted is a stamp however well the prose reads."""
    fake = CommentGh(); monkeypatch.setattr(GS, "gh", fake)
    rc, out = _quiet(GS.cmd_decide, _decide_ns(evidence=None))
    assert rc == 2 and not fake.posted
    assert "--evidence is required" in out


def test_decide_allows_a_rejection_without_evidence(monkeypatch):
    """A reject/refuted verdict blocks nothing downstream, so it is not held to the admit-side bar."""
    fake = CommentGh(); monkeypatch.setattr(GS, "gh", fake)
    rc, _ = _quiet(GS.cmd_decide, _decide_ns(
        verdict="reject", evidence=None,
        why="MUST 2 has no test and the placebo output passes the letter of the criterion"))
    assert rc == 0 and len(fake.posted) == 1


# ── 人間タスクの構造化（docs/11 §0c）────────────────────────────────────────
# org は自分が作れる作業だけを Issue にし、人間に頼むものを散文に落としていた。実地の founding で
# 3件（Supabase 作成 / OAuth クライアント登録 / ブランチ保護設定）がセッションの文章にしか残らず、
# /org が GREEN と出すのに実際は着手できない、という乖離が起きた。
def test_needs_human_creates_a_labeled_issue(monkeypatch):
    fake = FakeGh(replies={"issue create": (0, "https://github.com/o/r/issues/25"),
                           "issue list": (0, "[]")})
    monkeypatch.setattr(GS, "gh", fake)
    rc, out = _quiet(GS.cmd_needs_human, _ns(repo="o/r", title="Supabase を作る", body="手順…",
                                             objective="obj1", parent=None, blocks=None))
    assert rc == 0, out
    create = fake.calls_matching("issue create")[0]
    assert "orgforge:needs-human" in create
    assert "orgforge:kind:task" in create


def test_needs_human_body_says_the_org_cannot_do_it(monkeypatch):
    """人間がこの Issue を見たとき、なぜ自分に回ってきたのかが分かること。"""
    fake = FakeGh(replies={"issue create": (0, "https://github.com/o/r/issues/25"),
                           "issue list": (0, "[]")})
    monkeypatch.setattr(GS, "gh", fake)
    _quiet(GS.cmd_needs_human, _ns(repo="o/r", title="T", body="B", objective=None,
                                   parent=None, blocks="10,11"))
    body = fake.calls_matching("issue create")[0][
        fake.calls_matching("issue create")[0].index("--body") + 1]
    assert "CEO（人間）にしか実行できない" in body
    assert "#10" in body and "#11" in body     # 何をブロックしているかが見える


def test_needs_human_is_idempotent(monkeypatch):
    """再実行で二重に立てない（founding をやり直しても増えない）。"""
    listing = ('[{"number": 25, "title": "T", "state": "OPEN", "labels": []}]')
    fake = FakeGh(replies={"issue list": (0, listing)})
    monkeypatch.setattr(GS, "gh", fake)
    rc, out = _quiet(GS.cmd_needs_human, _ns(repo="o/r", title="T", body=None, objective=None,
                                             parent=None, blocks=None))
    assert rc == 0
    assert not fake.calls_matching("issue create")


def test_split_check_ignores_digits_in_prose(monkeypatch):
    """`depends_on` 行の散文中の数字を依存と誤検出しない。

    「実装コードは1行も入らない」の「1」が #1 として解釈され、存在しない依存が警告された
    （実地で判明）。#N の形だけを依存とみなす。"""
    body = json.dumps({"body": "## MUST\n- [ ] WHEN x THE system SHALL y\n"
                               "- **owns:** `app/a/`\n"
                               "- **depends_on:** なし。実装コードは1行も入らない\n", "title": "t"})
    fake = FakeGh(replies={"issue view": (0, body)})
    monkeypatch.setattr(GS, "gh", fake)
    rc, out = _quiet(GS.cmd_split_check, _ns(repo="o/r", issue=9))
    assert rc == 0, out
    assert "#1" not in out


# ── 実地: log に検査が無く、判定だけが厚くなった ─────────────────────────
# 同じ Issue で decide 経由は 3,506〜5,894字、log は 276〜473字。検査のある側だけが厚い。
def test_log_milestone_requires_command_and_result(monkeypatch):
    """マイルストーンの log は --command / --result を要求する（decide と同じ思想）。"""
    fake = FakeGh(replies={"issue view": (0, '{"comments": []}')})
    monkeypatch.setattr(GS, "gh", fake)
    rc = GS.cmd_log(_ns(repo="o/r", issue=7, event="cycle_completed",
                        detail="実装した", phase=None, event_id="e1",
                        command=None, result=None))
    assert rc == 2, "--command 無しのマイルストーン log が通った"
    assert not fake.calls_matching("issue comment")


def test_log_rejects_result_that_only_says_it_worked(monkeypatch):
    """--result が「通った」の言い換えなら弾く。実出力でなければ再構成できない。"""
    fake = FakeGh(replies={"issue view": (0, '{"comments": []}')})
    monkeypatch.setattr(GS, "gh", fake)
    rc = GS.cmd_log(_ns(repo="o/r", issue=7, event="cycle_completed",
                        detail="実装した", phase=None, event_id="e2",
                        command="npm test", result="ok"))
    assert rc == 2, "実出力でない --result が通った"


def test_log_progress_stays_cheap(monkeypatch):
    """途中の刻み（progress_recorded）には検査を掛けない — 軽く刻めることも大事。"""
    fake = FakeGh(replies={"issue view": (0, '{"comments": []}')})
    monkeypatch.setattr(GS, "gh", fake)
    rc = GS.cmd_log(_ns(repo="o/r", issue=7, event="progress_recorded",
                        detail="調査中", phase=None, event_id="e3",
                        command=None, result=None))
    assert rc == 0, "軽い刻みまで塞いだら、途中経過が書かれなくなる"


# ── 0.24.0: 分割基準に「壊れ方」と「守る対象の偏り」を足す ────────────────
def test_split_check_flags_multiple_failure_modes(monkeypatch):
    """`owns` が同じでも、壊れ方と検証手段が違えば別 Issue。

    実地の #11 は supabase/ に閉じていたため owns 基準では分割されなかったが、中身は
    「スキーマの形（型・制約）」と「認可（攻撃シナリオ）」という別々の壊れ方だった。
    結果 migration 5本が相互干渉し、12周しても終わらなかった。
    """
    body = ("## MUST\n"
            "- The system SHALL 全テーブルで ROW LEVEL SECURITY を有効にする\n"
            "- IF 非メンバーが SELECT する THEN THE system SHALL 拒否する\n"
            "- The system SHALL 金額の列を integer で定義し float を用いない\n"
            "- The system SHALL migration を冪等にする\n"
            "- The system SHALL SUM(shares.amount) = expenses.amount を制約で検査する\n"
            "- The system SHALL 端数の配分で合計が一致することを保証する\n")
    fake = FakeGh(replies={"issue view": (0, json.dumps({"body": body, "title": "t"}))})
    monkeypatch.setattr(GS, "gh", fake)
    rc, out = _quiet(GS.cmd_split_check, _ns(repo="o/r", issue=11))
    assert rc == 10, out
    assert "壊れ方が" in out


def test_split_check_flags_boundary_only_authz(monkeypatch):
    """境界だけを定めて内側を定めていない要求を警告する。

    「非メンバーが」は境界の話。部分一致で内側に数えると検査が丸ごと無効になる。
    """
    body = ("## MUST\n"
            "- The system SHALL 全テーブルで ROW LEVEL SECURITY を有効にする\n"
            "- IF 非メンバーが行を SELECT する THEN THE system SHALL 拒否する\n"
            "- WHEN メンバーが自分のあだ名を変更する THE system SHALL 許可する\n"
            "- The system SHALL 表示名を profiles に持つ\n"
            "- The system SHALL joined_at を持つ\n"
            "- The system SHALL archived_at を立てる\n"
            "- The system SHALL left_at を立てる\n")
    fake = FakeGh(replies={"issue view": (0, json.dumps({"body": body, "title": "t"}))})
    monkeypatch.setattr(GS, "gh", fake)
    rc, out = _quiet(GS.cmd_split_check, _ns(repo="o/r", issue=11))
    assert "入った後に何ができるか" in out, out


def test_split_check_does_not_flag_a_single_concern(monkeypatch):
    """関心事が1つの Issue は警告しない（実地の #8 / #10 は1〜2周で通った）。"""
    body = ("## MUST\n"
            "- WHEN 支出が3人で割られる THE system SHALL 合計が一致する配分を返す\n"
            "- IF 端数が出る THEN THE system SHALL 決定的な順序で配る\n"
            "- The system SHALL 同一入力に対し同一の結果を返す\n"
            "- The system SHALL 負の負担額を返さない\n")
    fake = FakeGh(replies={"issue view": (0, json.dumps({"body": body, "title": "t"}))})
    monkeypatch.setattr(GS, "gh", fake)
    rc, out = _quiet(GS.cmd_split_check, _ns(repo="o/r", issue=7))
    assert "壊れ方が" not in out and "入った後に" not in out, out


# ── 0.27.0: 監督の記録も機械で検査する（4層目にだけ検査が無かった）──────────
def _cv(**kw):
    base = dict(repo="o/r", issue=5, event="design_decided", verdict="pass",
                why="what was weighed and what decided it — a real account here",
                by="supervisor", phase=None, evidence="npm test → 27 passed",
                alternatives=None, standard=None, risk=None, event_id="ev-cv",
                claimed=None, verified=None)
    base.update(kw)
    return _ns(**base)


def test_verified_without_a_trace_of_running_is_flagged(monkeypatch, capsys):
    """「確認した」と書くだけでは確かめたことにならない。

    実地でこの org は「確かめていないことを確かめたかのように述べる」を8回検出した。
    その失敗様式が**検出する側（監督）**に現れた。
    """
    fake = CommentGh(); monkeypatch.setattr(GS, "gh", fake)
    GS.cmd_decide(_cv(claimed="maker が client.ts を読んだと報告", verified="確認した"))
    err = capsys.readouterr().err
    assert "痕跡" in err, err


def test_dropped_condition_in_the_summary_is_flagged(monkeypatch, capsys):
    """--claimed の条件節が --verified で触れられていないなら警告する。

    実地の #32: maker は「このブランチにまだ存在せず」と正直に書いたが、監督の要約が
    その条件を落とし、それが gate への指示に流れて reject 事由になった。
    """
    fake = CommentGh(); monkeypatch.setattr(GS, "gh", fake)
    GS.cmd_decide(_cv(claimed="src/db/client.ts はこのブランチに存在せず feat/issue-11 側にある",
                      verified="npm test → 27 passed"))
    err = capsys.readouterr().err
    assert "条件節" in err, err


def test_carrying_the_condition_through_is_silent(monkeypatch, capsys):
    """条件を運んでいれば黙る。語尾の違い（存在せず / 存在しない）で誤検出しないこと。"""
    fake = CommentGh(); monkeypatch.setattr(GS, "gh", fake)
    GS.cmd_decide(_cv(claimed="client.ts はこのブランチに存在せず feat/issue-11 側にある",
                      verified="git ls-files src/db/client.ts → 出力なし（存在しないことを確認）"))
    err = capsys.readouterr().err
    assert "条件節" not in err, err


def test_legacy_calls_without_claimed_verified_still_pass(monkeypatch, capsys, tmp_path):
    """--claimed / --verified を渡さない旧来の呼び出しは通す（後方互換）。"""
    led = tmp_path / "led"; led.mkdir()
    monkeypatch.setenv("ORG_LEDGER_ROOT", str(led))
    fake = CommentGh(); monkeypatch.setattr(GS, "gh", fake)
    rc = GS.cmd_decide(_cv())
    assert rc == 0
    assert "痕跡" not in capsys.readouterr().err


# ── 0.30.0: integration_admitted は gate の admit を前提とする ──────────────
def test_integration_admitted_requires_a_gate_admit(monkeypatch, tmp_path, capsys):
    """gate も skeptic も通っていない Issue に `integration_admitted = pass` が通っていた。

    台帳は `phase_started` に対して既に同じ検査をしている（design が admit されていなければ
    implement を拒否）。**maker の報告の質は admit の代わりにならない。**
    """
    led = tmp_path / "led"; led.mkdir()
    monkeypatch.setenv("ORG_LEDGER_ROOT", str(led))
    fake = CommentGh(); monkeypatch.setattr(GS, "gh", fake)
    rc = GS.cmd_decide(_cv(issue=42, event="integration_admitted", verdict="pass"))
    assert rc == 4, "gate の admit なしに統合の記録が通った"
    err = capsys.readouterr().err
    assert "gate の admit が無い" in err
    assert "verify" in err and "--role gate" in err, "打つべきコマンドが示されていない"
    assert not fake.posted, "Issue にも記録してはいけない"


def test_integration_admitted_passes_after_an_admit(monkeypatch, tmp_path):
    """admit があれば通す。"""
    led = tmp_path / "led2"; led.mkdir()
    # **実際の append で seed する。** 手書きの偽イベント（hash / prev_hash 無し）を置くと、
    # Writer Phase 0 の健全性検査が正しく拒否する — 鎖の無い台帳に追記できてはいけない。
    # 偽の台帳で試験していたことは、Phase 0 を入れて初めて露見した。
    import subprocess as _sp
    r = _sp.run([sys.executable, str(REPO / "tools" / "ledger.py"), "append", str(led),
                 "--actor", "gate", "--class", "admission_decided",
                 "--payload", json.dumps({"issue": 42, "deliverable": "42",
                                          "verdict": "admit"})],
                capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    monkeypatch.setenv("ORG_LEDGER_ROOT", str(led))
    fake = CommentGh(); monkeypatch.setattr(GS, "gh", fake)
    rc = GS.cmd_decide(_cv(issue=42, event="integration_admitted", verdict="pass"))
    assert rc == 0, "admit 済みの統合が弾かれた"


# ══ H1 — 判断した主体・記録した主体・確定した主体を分ける ══════════════════════
# **`actor` は3つを混ぜていた。** 監督が judge の判定を代理で記録する運用では、観測される
# actor は常に監督なので、actor 同士を比べる職務分離は「監督が監督を承認していない」しか
# 言えない。decision_by は **検証済み receipt からのみ** 確定する。

import subprocess as _sp


def _h1_org(tmp_path):
    """receipt を検証できる使い捨て org。subject が動かないよう作業ツリーを固定する。"""
    org = tmp_path / "org"
    (org / ".orgforge" / "ledger").mkdir(parents=True)
    (org / ".orgforge" / "trust").mkdir(parents=True)
    import shutil as _sh
    _sh.copy(REPO / "template" / "ledger-schema.yaml", org / "ledger-schema.yaml")
    (org / "constitution.yaml").write_text(
        "enforcement:\n  judges:\n    lineage: cross-harness\n", encoding="utf-8")
    (org / "REQUIREMENTS.md").write_text("MUST: A\n", encoding="utf-8")
    # **台帳と trust store を追跡から外す** — 実行で中身が変わると subject が動き、
    # receipt と一致しなくなる（review_subject が作業ツリー全体を束ねる設計の帰結）。
    (org / ".gitignore").write_text(".orgforge/\n", encoding="utf-8")
    for c in (["init", "-q"], ["config", "user.email", "t@t"], ["config", "user.name", "t"],
              ["add", "-A"], ["-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "i"]):
        _sp.run(["git", *c], cwd=org, check=True, capture_output=True)
    return org


def _h1_env(org):
    return dict(os.environ, ORG_TRUST_STORE=str(org / ".orgforge" / "trust" / "keys.json"),
                ORG_LEDGER_ROOT=str(org / ".orgforge" / "ledger"))


def _tool(org, script, *args, env=None):
    return _sp.run([sys.executable, str(REPO / "tools" / script), *args],
                   cwd=org, capture_output=True, text=True, env=env or _h1_env(org))


_H1_WHY = ("gate の判定理由。独立に再導出した範囲と、判定の決め手になった具体的な箇所を"
           "書いている。")


def _h1_setup(tmp_path, keys=(("k-gate", "gate-signer"),)):
    org = _h1_org(tmp_path)
    for kid, sid in keys:
        # **H1 の試験は Compatibility Mode を検査している。** 0.38.0 で keygen の既定が
        # 非対称（Authenticated Mode）になったので、共有鍵を明示する。
        r = _tool(org, "identity.py", "keygen", "--key-id", kid, "--signer-id", sid,
                  "--shared-secret")
        assert r.returncode == 0, r.stdout + r.stderr
    sys.path.insert(0, str(REPO / "tools"))
    from orgcycle._core import review_subject
    from ghsync.record import _reasoning_digest
    subj = review_subject(7, "gate", "implement", cwd=str(org))[0]
    dig = _reasoning_digest(_H1_WHY, "見た証跡", "", "", "")
    import hashlib as _h
    reqd = _h.sha256((org / "REQUIREMENTS.md").read_bytes()).hexdigest()[:16]
    return org, subj, dig, reqd


def _h1_receipt(org, subj, dig, reqd, key_id="k-gate", role="gate",
                lineage="same-harness", verdict="admit", issue="7", out="r.json"):
    # **org_id / ledger_id は書き込み先から決まる。** receipt もそれに合わせる —
    # 合わせないと「別 org の receipt」として正しく拒否される（0.39.5 で束縛を完全化）。
    _oid, _lid = _real_ids(org)
    r = _tool(org, "identity.py", "receipt", "--org-id", _oid, "--ledger-id", _lid,
              "--subject", subj, "--issue", issue, "--role", role, "--phase", "implement",
              "--lineage", lineage, "--verdict", verdict, "--event-class", "verdict_provisional",
            "--requirements-digest", reqd,
              "--reasoning-sha256", dig, "--issued-at", "2026-07-30T12:00:00Z",
              "--key-id", key_id)
    assert r.returncode == 0, r.stdout + r.stderr
    p = org / out
    p.write_text(r.stdout.strip(), encoding="utf-8")
    return p


def _h1_prov(org, subj, receipt=None, role="gate", lineage="same-harness",
             verdict="admit", issue="7", env=None):
    args = ["provisional", "--issue", issue, "--role", role, "--lineage", lineage,
            "--verdict", verdict, "--subject", subj, "--why", _H1_WHY,
            "--evidence", "見た証跡"]
    if receipt:
        args += ["--receipt", str(receipt)]
    return _tool(org, "github_sync.py", *args, env=env)


def _h1_events(org, cls="verdict_provisional"):
    f = org / ".orgforge" / "ledger" / "ledger.jsonl"
    if not f.exists():
        return []
    return [json.loads(l) for l in f.read_text(encoding="utf-8").splitlines()
            if l.strip() and json.loads(l)["class"] == cls]


def test_decision_by_comes_from_a_verified_receipt(tmp_path):
    """`decision_by` は receipt からのみ。CLI に申告する引数は存在しない。"""
    org, subj, dig, reqd = _h1_setup(tmp_path)
    rc = _h1_receipt(org, subj, dig, reqd)
    r = _h1_prov(org, subj, rc)
    assert r.returncode == 0, r.stdout + r.stderr
    pl = _h1_events(org)[0]["payload"]
    assert pl["decision_by"] == "gate-signer"
    assert pl["identity_assurance"] == "attested"     # 共有鍵なので authenticated ではない
    assert pl["signer_id"] == "gate-signer" and pl["key_id"] == "k-gate"
    # **payload に書いたのではなく、書き手が receipt を検証して生成した**（0.39.4）
    # CLI で decision_by を申告する経路が無いこと
    h = _tool(org, "github_sync.py", "provisional", "--help")
    assert "--decision-by" not in h.stdout


def test_recorded_by_is_observed_and_decision_by_survives_proxy_recording(tmp_path):
    """**代理記録でも判断者の identity は失われない。**

    監督が別 session で記録しても `decision_by` は judge のまま。それが「代理記録と認証は
    両立する」の中身である。
    """
    org, subj, dig, reqd = _h1_setup(tmp_path)
    rc = _h1_receipt(org, subj, dig, reqd)
    env = dict(_h1_env(org), ORG_SESSION_ID="supervisor-session-99")
    r = _h1_prov(org, subj, rc, env=env)
    assert r.returncode == 0, r.stdout + r.stderr
    pl = _h1_events(org)[0]["payload"]
    assert pl["decision_by"] == "gate-signer"          # judge のまま
    assert pl["recorded_by"] == "session:supervisor-session-99"
    assert pl["recorder_assurance"] == "observed"


def test_receipt_cannot_be_replayed_into_another_judgment(tmp_path):
    """別の issue / subject / 血統への再利用を拒否する。"""
    org, subj, dig, reqd = _h1_setup(tmp_path)
    rc = _h1_receipt(org, subj, dig, reqd)
    for kw in ({"issue": "9"}, {"lineage": "cross-harness"}, {"verdict": "reject"}):
        r = _h1_prov(org, subj, rc, **kw)
        assert r.returncode == 4, f"{kw} で通った: {r.stdout + r.stderr}"
        assert "一致しない" in (r.stdout + r.stderr)
    assert _h1_events(org) == []


def test_tampering_with_a_receipt_is_refused(tmp_path):
    """束縛した値を書き換えると署名が合わない。"""
    org, subj, dig, reqd = _h1_setup(tmp_path)
    rc = _h1_receipt(org, subj, dig, reqd)
    d = json.loads(rc.read_text(encoding="utf-8"))
    d["signer_id"] = "someone-else"
    rc.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    r = _h1_prov(org, subj, rc)
    assert r.returncode == 4
    both = r.stdout + r.stderr
    assert "署名が一致しない" in both or "一致しない" in both


def test_a_revoked_key_is_refused(tmp_path):
    """失効した鍵の receipt は受け付けない。"""
    org, subj, dig, reqd = _h1_setup(tmp_path)
    rc = _h1_receipt(org, subj, dig, reqd)
    assert _tool(org, "identity.py", "revoke", "--key-id", "k-gate",
                 "--reason", "検査").returncode == 0
    r = _h1_prov(org, subj, rc)
    assert r.returncode == 4
    assert "失効している" in (r.stdout + r.stderr)


def test_unreadable_trust_store_does_not_record_the_judgment(tmp_path):
    """**読めないことを「信頼できる」と読まない。** 判断の主体を確かめられないなら記録しない。"""
    org, subj, dig, reqd = _h1_setup(tmp_path)
    rc = _h1_receipt(org, subj, dig, reqd)
    env = dict(_h1_env(org), ORG_TRUST_STORE="/nonexistent/keys.json")
    r = _h1_prov(org, subj, rc, env=env)
    assert r.returncode == 4
    assert "trust store" in (r.stdout + r.stderr)
    assert _h1_events(org) == []


def test_without_a_receipt_identity_stays_claimed(tmp_path):
    """receipt が無ければ `claimed` のまま — **昇格しない。**"""
    org, subj, dig, reqd = _h1_setup(tmp_path)
    r = _h1_prov(org, subj, None, role="skeptic", verdict="survives", issue="11")
    assert r.returncode == 0, r.stdout + r.stderr
    pl = _h1_events(org)[0]["payload"]
    assert pl["identity_assurance"] == "claimed"
    assert pl["decision_by"] == "skeptic"          # legacy actor 相当（申告）


def test_same_signer_on_both_lineages_is_not_independent_review(tmp_path):
    """**署名されていても、同じ signer が両方を作れるなら独立レビューではない。**

    一致は成立するが、`reviewer_independence = same_signer` として記録され、警告される。
    独立性の証拠として数えてはいけない。
    """
    org, subj, dig, reqd = _h1_setup(tmp_path)
    r1 = _h1_receipt(org, subj, dig, reqd, lineage="same-harness", out="r1.json")
    r2 = _h1_receipt(org, subj, dig, reqd, lineage="cross-harness", out="r2.json")
    assert _h1_prov(org, subj, r1, lineage="same-harness").returncode == 0
    r = _h1_prov(org, subj, r2, lineage="cross-harness")
    assert r.returncode == 0, r.stdout + r.stderr
    both = r.stdout + r.stderr
    assert "同じ signer が両方に署名している" in both
    adm = _h1_events(org, "admission_decided")
    assert len(adm) == 1
    assert adm[0]["payload"]["reviewer_independence"] == "same_signer"


def test_distinct_signers_are_recorded_as_independent(tmp_path):
    """血統ごとに別の signer なら `distinct_signer`。"""
    org, subj, dig, reqd = _h1_setup(tmp_path,
                                     keys=(("k-gate", "gate-signer"), ("k-two", "second-signer")))
    r1 = _h1_receipt(org, subj, dig, reqd, key_id="k-gate", lineage="same-harness", out="r1.json")
    r2 = _h1_receipt(org, subj, dig, reqd, key_id="k-two", lineage="cross-harness", out="r2.json")
    assert _h1_prov(org, subj, r1, lineage="same-harness").returncode == 0
    assert _h1_prov(org, subj, r2, lineage="cross-harness").returncode == 0
    adm = _h1_events(org, "admission_decided")
    assert adm and adm[0]["payload"]["reviewer_independence"] == "distinct_signer"


def test_separation_of_duties_compares_decision_by_not_recorded_by(tmp_path):
    """**職務分離は `decision_by` 同士を比べる。** recorded_by を比べると代理記録が全て違反になる。"""
    sys.path.insert(0, str(REPO / "tools"))
    import importlib
    led = importlib.import_module("ledger")
    hist = [{"class": "cycle_completed", "actor": "supervisor",
             "payload": {"deliverable": "7", "decision_by": "maker-alice",
                         "recorded_by": "session:sup"}}]
    ev = {"class": "admission_decided", "actor": "supervisor",
          "payload": {"deliverable": "7", "verdict": "admit",
                      "decision_by": "maker-alice", "recorded_by": "session:sup"}}
    assert led._distinct_actor_violation(ev, hist), "maker が自分の仕事を admit できている"
    # 判断者が別なら通る（記録者が同じでも）
    ev["payload"]["decision_by"] = "gate-signer"
    assert led._distinct_actor_violation(ev, hist) is None, "代理記録が違反扱いになっている"


# ── Issue #103: machine-readable dependencies, parked state, honest ready gating ─────────────
# Observed in Tatekae (OBS-051): `ready` returned 30 items including 4 whose dependency existed
# only as prose (the carve-out path had no --depends propagation), a "[PARKED]" title with no
# machine vocabulary, and an integration-waiting Issue. A maker was handed unstartable work.

def _ready(monkeypatch, fake, kind="task"):
    import io, contextlib
    monkeypatch.setattr(GS, "gh", fake)
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = GS.cmd_ready(_ns(repo="o/r", kind=kind))
    return rc, json.loads(buf.getvalue())["ready"]


def _create_ns(**kw):
    base = dict(repo="o/r", title="carved-out task", body="Task context", objective=None,
                source=None, depends=None, priority=None, kind="task", parent=None,
                carved_from=None)
    base.update(kw)
    return _ns(**base)


def test_create_carved_from_appends_machine_readable_depends_on(monkeypatch):
    # the carve-out invariant: 「carve out 先は元に依存する」は例外なく成り立つ — so the create
    # path must WRITE it, not leave it to prose (Issue #103).
    fake = FakeGh(replies={"issue create": (0, "https://github.com/o/r/issues/80")})
    monkeypatch.setattr(GS, "gh", fake)
    rc = GS.cmd_create(_create_ns(body="Out-of-scope find during rework of the CI floor.",
                                  carved_from="63"))
    assert rc == 0
    create = fake.calls_matching("issue create")[0]
    body = create[create.index("--body") + 1]
    assert "Depends on: #63" in body, body


def test_create_carved_from_merges_with_explicit_depends_without_duplicates(monkeypatch):
    fake = FakeGh(replies={"issue create": (0, "https://github.com/o/r/issues/81")})
    monkeypatch.setattr(GS, "gh", fake)
    rc = GS.cmd_create(_create_ns(body="Carved out with an extra dependency.",
                                  depends="7", carved_from="63"))
    assert rc == 0
    body = fake.calls_matching("issue create")[0]
    body = body[body.index("--body") + 1]
    dep_lines = [l for l in body.splitlines() if l.lower().startswith("depends on:")]
    assert dep_lines == ["Depends on: #7, #63"], dep_lines
    # already listed in --depends → no duplicate ref on the line
    rc = GS.cmd_create(_create_ns(title="second carve", body="Dup-declared dependency.",
                                  depends="63", carved_from="63"))
    assert rc == 0
    body = fake.calls_matching("issue create")[1]
    body = body[body.index("--body") + 1]
    dep_lines = [l for l in body.splitlines() if l.lower().startswith("depends on:")]
    assert dep_lines == ["Depends on: #63"], dep_lines


def test_create_warns_on_prose_issue_refs_without_depends_line(monkeypatch, capsys):
    # the prose-dependency trap: the body names other issues but declares no Depends on: line.
    # WARN loudly, still create — do NOT auto-parse prose into dependencies (guessing is worse).
    fake = FakeGh(replies={"issue create": (0, "https://github.com/o/r/issues/82")})
    monkeypatch.setattr(GS, "gh", fake)
    rc = GS.cmd_create(_create_ns(body="Needs ci/test-floor.json produced by #63; wire it in."))
    assert rc == 0
    err = capsys.readouterr().err
    assert "WARN" in err and "#63" in err and "Depends on" in err, err
    assert fake.calls_matching("issue create"), "the warning must not block the create"


def test_create_does_not_warn_when_dependency_is_declared(monkeypatch, capsys):
    fake = FakeGh(replies={"issue create": (0, "https://github.com/o/r/issues/83")})
    monkeypatch.setattr(GS, "gh", fake)
    rc = GS.cmd_create(_create_ns(body="Needs ci/test-floor.json produced by #63; wire it in.",
                                  carved_from="63"))
    assert rc == 0
    assert "WARN" not in capsys.readouterr().err


# ── parked: a machine-readable vocabulary instead of "[PARKED]" title prose ──────────────────
def test_park_adds_label_and_comments_why(monkeypatch):
    fake = FakeGh(replies={"--json labels": (0, '{"labels": []}')})
    monkeypatch.setattr(GS, "gh", fake)
    rc = GS.cmd_park(_ns(repo="o/r", issue=42, why="parts live only in an unmerged worktree"))
    assert rc == 0
    edits = fake.calls_matching("issue edit 42")
    assert edits and "orgforge:parked" in edits[0] and "--add-label" in edits[0], fake.calls
    comments = fake.calls_matching("issue comment 42")
    assert comments and any("unmerged worktree" in " ".join(c) for c in comments), fake.calls


def test_park_is_idempotent_when_already_parked(monkeypatch):
    fake = FakeGh(replies={"--json labels": (0, '{"labels": [{"name": "orgforge:parked"}]}')})
    monkeypatch.setattr(GS, "gh", fake)
    rc = GS.cmd_park(_ns(repo="o/r", issue=42, why="again"))
    assert rc == 0
    assert not fake.calls_matching("issue edit") and not fake.calls_matching("issue comment")


def test_unpark_removes_label_and_comments_why(monkeypatch):
    fake = FakeGh(replies={"--json labels": (0, '{"labels": [{"name": "orgforge:parked"}]}')})
    monkeypatch.setattr(GS, "gh", fake)
    rc = GS.cmd_unpark(_ns(repo="o/r", issue=42, why="worktree merged; parts exist on main"))
    assert rc == 0
    edits = fake.calls_matching("issue edit 42")
    assert edits and "--remove-label" in edits[0] and "orgforge:parked" in edits[0], fake.calls
    assert any("worktree merged" in " ".join(c) for c in fake.calls_matching("issue comment 42"))


def test_unpark_is_idempotent_when_not_parked(monkeypatch):
    fake = FakeGh(replies={"--json labels": (0, '{"labels": []}')})
    monkeypatch.setattr(GS, "gh", fake)
    rc = GS.cmd_unpark(_ns(repo="o/r", issue=42, why=None))
    assert rc == 0
    assert not fake.calls_matching("issue edit")


# ── ready: excludes every non-startable state ────────────────────────────────────────────────
def test_ready_excludes_parked_issues(monkeypatch):
    listing = ('[{"number": 1, "title": "t", "labels": [{"name": "orgforge:kind:task"}], "body": ""},'
               ' {"number": 2, "title": "p", "labels": [{"name": "orgforge:kind:task"},'
               ' {"name": "orgforge:parked"}], "body": ""}]')
    rc, ready = _ready(monkeypatch, FakeGh(replies={"issue list": (0, listing)}))
    assert rc == 0 and ready == [1], ready


def test_ready_excludes_claimed_and_in_progress_issues(monkeypatch):
    # claimed = existing behavior (verify); in-progress alongside a stale ready label = the
    # 7-rounds-reworked, integration-waiting Issue that was listed as untouched (Issue #103).
    listing = ('[{"number": 1, "title": "t", "labels": [{"name": "orgforge:kind:task"}], "body": ""},'
               ' {"number": 2, "title": "c", "labels": [{"name": "orgforge:kind:task"},'
               ' {"name": "orgforge:claimed:bob"}], "body": ""},'
               ' {"number": 3, "title": "w", "labels": [{"name": "orgforge:kind:task"},'
               ' {"name": "orgforge:in-progress"}], "body": ""}]')
    rc, ready = _ready(monkeypatch, FakeGh(replies={"issue list": (0, listing)}))
    assert rc == 0 and ready == [1], ready


def test_ready_withholds_when_any_of_multiple_depends_lines_is_open(monkeypatch):
    # the old parser kept only the LAST "Depends on:" line — an open dependency on an earlier
    # line was silently dropped and the issue listed as ready.
    body = "context\\nDepends on: #5\\nmore context\\nDepends on: #7"
    listing = ('[{"number": 1, "title": "t", "labels": [{"name": "orgforge:kind:task"}],'
               f' "body": "{body}"}}]')
    fake = FakeGh(replies={"issue list": (0, listing),
                           "issue view 5": (0, '{"state": "OPEN"}'),
                           "issue view 7": (0, '{"state": "CLOSED"}')})
    rc, ready = _ready(monkeypatch, fake)
    assert rc == 0 and ready == [], ready


def test_ready_lists_when_all_depends_lines_are_closed(monkeypatch):
    body = "context\\nDepends on: #5\\nmore context\\nDepends on: #7"
    listing = ('[{"number": 1, "title": "t", "labels": [{"name": "orgforge:kind:task"}],'
               f' "body": "{body}"}}]')
    fake = FakeGh(replies={"issue list": (0, listing),
                           "issue view 5": (0, '{"state": "CLOSED"}'),
                           "issue view 7": (0, '{"state": "CLOSED"}')})
    rc, ready = _ready(monkeypatch, fake)
    assert rc == 0 and ready == [1], ready


def test_ready_withholds_when_a_dependency_cannot_be_verified(monkeypatch):
    # a declared dependency whose state is UNKNOWN is not proof of startability — honest gating
    # withholds rather than handing a maker maybe-blocked work.
    listing = ('[{"number": 1, "title": "t", "labels": [{"name": "orgforge:kind:task"}],'
               ' "body": "Depends on: #9"}]')
    fake = FakeGh(replies={"issue list": (0, listing),
                           "issue view 9": (1, "gh: Not Found")})
    rc, ready = _ready(monkeypatch, fake)
    assert rc == 0 and ready == [], ready
