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
    """That org's (org_id, ledger_id). The receipt is matched to **the value the write target
    determines**."""
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
# github_sync was split into tools/ghsync/ (0.22.0). These tests want to see behaviour rather than
# "which module something lives in", so they use a view gathering every module's names into one
# namespace.
# So that `monkeypatch.setattr(GS, "gh", fake)` reaches every module, the gh replacement is
# propagated to each module too (_patch_gh_everywhere below).
sys.path.insert(0, str(REPO / "tools"))
import types as _types
from ghsync import _core as _gh_core, backlog as _gh_backlog, record as _gh_record,     branch as _gh_branch, coverage as _gh_coverage

_GH_MODS = (_gh_core, _gh_backlog, _gh_record, _gh_branch, _gh_coverage)


class _Facade(_types.ModuleType):
    """A unified view of every ghsync module. A setattr propagates to all of them."""

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


def test_repair_body_requires_explicit_confirmation_when_dropping_dependencies(monkeypatch):
    fake = FakeGh(replies={"issue view": (0, json.dumps({"body": "context\n\nDepends on: #9"})),
                           "api user": (0, "octocat\n"), "issue edit": (0, ""),
                           "issue comment": (0, "")})
    monkeypatch.setattr(GS, "gh", fake)
    rc = GS.cmd_repair_body(_ns(repo="o/r", issue=5, body="context", reason="repair"))
    assert rc == 2
    assert not fake.calls_matching("issue edit")

    rc = GS.cmd_repair_body(_ns(repo="o/r", issue=5, body="context", reason="repair",
                                confirm_drop_depends=True))
    assert rc == 0
    assert fake.calls_matching("issue edit")


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
def _git_org(tmp_path, name="r"):
    """The minimal repo that lets query-mode branch resolution (#107) look at a real git."""
    import subprocess
    repo = tmp_path / name
    repo.mkdir()

    def g(*a, cwd=repo):
        return subprocess.run(["git", *a], cwd=cwd, capture_output=True, text=True)

    g("init", "-q", "-b", "main")
    g("config", "user.email", "t@t")
    g("config", "user.name", "t")
    (repo / "s.txt").write_text("s", encoding="utf-8")
    g("add", "-A")
    g("commit", "-qm", "seed")
    g("update-ref", "refs/remotes/origin/main", "main")
    return repo, g


def test_branch_name_is_deterministic_and_off_develop(tmp_path, monkeypatch):
    # (c) no worktree + the derived name EXISTS as a real branch → it is reported (#107:
    # query mode answers with a branch that exists, never with an unverified derivation).
    fake = FakeGh(replies={"issue view": (0, '{"title": "Add login endpoint"}')})
    monkeypatch.setattr(GS, "gh", fake)
    repo, g = _git_org(tmp_path)
    g("branch", "feat/issue-42-add-login-endpoint")
    monkeypatch.chdir(repo)
    import io, contextlib
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = GS.cmd_branch(_ns(repo="o/r", issue=42, create=False, base=None))
    assert rc == 0
    assert buf.getvalue().strip() == "feat/issue-42-add-login-endpoint"


def test_branch_japanese_title_falls_back_to_stable_hash():
    # a Japanese task title (output_language: ja) must NOT collapse to an empty/meaningless slug.
    # Determinism lives in the pure derivation (issue, title) → name; the query command now
    # additionally verifies existence (#107), tested separately below.
    out = [GS.derived_branch_name(6, "領域A: 認証 + プロジェクト") for _ in range(2)]
    assert out[0] == out[1], "same Issue must yield the same branch (reproducible)"
    assert out[0].startswith("feat/issue-6-t") and len(out[0]) > len("feat/issue-6-"), out[0]


def test_derived_branch_name_empty_title_is_genuinely_slugless():
    """#107 rework (3a): a derivation with an unknown title really has no slug. It must not announce
    "the slug is omitted" while printing a phantom name carrying the hash of an empty string
    (te3b0c442…)."""
    assert GS.derived_branch_name(9, "") == "feat/issue-9"


def test_branch_query_reports_worktree_head_not_stale_derived_name(tmp_path, monkeypatch, capsys):
    """#107 (a)(b) Tatekae shape: the Issue worktree's HEAD is `feat/issue-15-login-redirect`
    but the title now derives `feat/issue-15-google` → query mode reports the REAL branch and
    warns about the mismatch instead of silently printing a branch that does not exist."""
    fake = FakeGh(replies={"issue view": (0, '{"title": "Google"}')})
    monkeypatch.setattr(GS, "gh", fake)
    repo, g = _git_org(tmp_path)
    wt = repo / ".orgforge" / "wt" / "issue-15"
    g("worktree", "add", "-q", "-b", "feat/issue-15-login-redirect", str(wt), "main")
    monkeypatch.chdir(repo)
    rc = GS.cmd_branch(_ns(repo="o/r", issue=15, create=False, base=None))
    cap = capsys.readouterr()
    assert rc == 0
    assert cap.out.strip() == "feat/issue-15-login-redirect", \
        f"it reported the derived name rather than the worktree's real HEAD: {cap.out!r}"
    assert "feat/issue-15-google" in cap.err and "feat/issue-15-login-redirect" in cap.err, \
        f"the mismatch between the derived and the real name is not warned about: {cap.err!r}"


def test_branch_query_fails_closed_when_derived_branch_missing(tmp_path, monkeypatch, capsys):
    """#107 (d) no worktree and the derived name is NOT a real branch → non-zero, and the
    message names the derived name and how to fix (never silently trust a non-existent name)."""
    fake = FakeGh(replies={"issue view": (0, '{"title": "Add login endpoint"}')})
    monkeypatch.setattr(GS, "gh", fake)
    repo, _ = _git_org(tmp_path)
    monkeypatch.chdir(repo)
    rc = GS.cmd_branch(_ns(repo="o/r", issue=42, create=False, base=None))
    cap = capsys.readouterr()
    assert rc != 0, "it printed a non-existent derived name as a success"
    assert "feat/issue-42-add-login-endpoint" in cap.err, \
        f"it does not name which derived name does not exist: {cap.err!r}"
    assert "--worktree" in cap.err, f"the fix is not written: {cap.err!r}"


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
    # A DoD command is required by default (a SPEC without one gives the gate no target and the
    # rounds do not converge). What this test wants to see is the singleness of the territory, so it
    # checks with the DoD satisfied.
    body = ("## Seam\\n- **owns:** `app/packages/auth/`\\n"
            "- **DoD command:** `npm test -- auth`\\n")
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


def test_split_check_requires_a_dod_command_by_default(monkeypatch):
    """A SPEC with no runnable DoD command gives the gate no target.

    The gate is told to re-derive rather than trust the maker, so without a command to run it
    designs the verification itself — differently on every round. That is what makes a review
    rally diverge instead of converge (issue #170 ran 12 rounds). On by default; ORG_REQUIRE_DOD=0
    stands it down.
    """
    monkeypatch.delenv("ORG_REQUIRE_DOD", raising=False)
    body = json.dumps({"body": "## MUST\n- [ ] WHEN login THE system SHALL validate\n"
                               "- **owns:** `app/auth/`\n", "title": "t"})
    fake = FakeGh(replies={"issue view": (0, body)})
    monkeypatch.setattr(GS, "gh", fake)
    rc, out = _quiet(GS.cmd_split_check, _ns(repo="o/r", issue=9))
    assert rc == 10 and "DoD command" in out, out


def test_split_check_clean_when_must_is_ears(monkeypatch):
    body = json.dumps({"body": "## MUST\n- [ ] WHEN login THE system SHALL validate\n"
                               "- **owns:** `app/auth/`\n"
                               "- **DoD command:** `npm test -- auth`\n", "title": "t"})
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
    """decide now writes to the ledger too (0.21.0 ended the double typing), so each test is given a
    disposable ledger root. A real org's ledger is not dirtied."""
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


# ── giving human tasks a structure (docs/11 §0c) ────────────────────────────
# The org filed only the work it could do itself as Issues and let what it needed from a human fall
# into prose. In a founding in the field, three of them (creating Supabase, registering the OAuth
# client, setting branch protection) survived only in the session's text, producing the gap where
# /org reported GREEN while work could not actually be started.
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
    """When a human looks at this Issue, why it came to them must be clear."""
    fake = FakeGh(replies={"issue create": (0, "https://github.com/o/r/issues/25"),
                           "issue list": (0, "[]")})
    monkeypatch.setattr(GS, "gh", fake)
    _quiet(GS.cmd_needs_human, _ns(repo="o/r", title="T", body="B", objective=None,
                                   parent=None, blocks="10,11"))
    body = fake.calls_matching("issue create")[0][
        fake.calls_matching("issue create")[0].index("--body") + 1]
    assert "only the CEO (a human) can carry out" in body
    assert "#10" in body and "#11" in body     # what it blocks is visible


def test_needs_human_is_idempotent(monkeypatch):
    """A re-run does not file it twice (redoing a founding does not multiply them)."""
    listing = ('[{"number": 25, "title": "T", "state": "OPEN", "labels": []}]')
    fake = FakeGh(replies={"issue list": (0, listing)})
    monkeypatch.setattr(GS, "gh", fake)
    rc, out = _quiet(GS.cmd_needs_human, _ns(repo="o/r", title="T", body=None, objective=None,
                                             parent=None, blocks=None))
    assert rc == 0
    assert not fake.calls_matching("issue create")


def test_split_check_ignores_digits_in_prose(monkeypatch):
    """A number in the prose of a `depends_on` line is not misread as a dependency.

    The "1" of 「実装コードは1行も入らない」 ("not one line of implementation code goes in") was read
    as #1 and a dependency that did not exist was warned about (found in the field). Only the #N shape
    counts as a dependency."""
    body = json.dumps({"body": "## MUST\n- [ ] WHEN x THE system SHALL y\n"
                               "- **owns:** `app/a/`\n"
                               "- **DoD command:** `npm test -- a`\n"
                               "- **depends_on:** なし。実装コードは1行も入らない\n", "title": "t"})
    fake = FakeGh(replies={"issue view": (0, body)})
    monkeypatch.setattr(GS, "gh", fake)
    rc, out = _quiet(GS.cmd_split_check, _ns(repo="o/r", issue=9))
    assert rc == 0, out
    assert "#1" not in out


# ── in the field: log had no check, and only the judgments grew thick ───────
# On the same Issue, what went through decide ran 3,506-5,894 characters and the logs 276-473. Only
# the side with a check is thick.
def test_log_milestone_requires_command_and_result(monkeypatch):
    """A milestone log requires --command / --result (the same thinking as decide)."""
    fake = FakeGh(replies={"issue view": (0, '{"comments": []}')})
    monkeypatch.setattr(GS, "gh", fake)
    rc = GS.cmd_log(_ns(repo="o/r", issue=7, event="cycle_completed",
                        detail="実装した", phase=None, event_id="e1",
                        command=None, result=None))
    assert rc == 2, "a milestone log with no --command passed"
    assert not fake.calls_matching("issue comment")


def test_log_rejects_result_that_only_says_it_worked(monkeypatch):
    """A --result that merely paraphrases "it passed" is rejected. Without the real output nothing
    can be reconstructed."""
    fake = FakeGh(replies={"issue view": (0, '{"comments": []}')})
    monkeypatch.setattr(GS, "gh", fake)
    rc = GS.cmd_log(_ns(repo="o/r", issue=7, event="cycle_completed",
                        detail="実装した", phase=None, event_id="e2",
                        command="npm test", result="ok"))
    assert rc == 2, "a --result that is not real output passed"


def test_log_progress_stays_cheap(monkeypatch):
    """No check is applied to an interim note (progress_recorded) — being able to note things
    lightly matters too."""
    fake = FakeGh(replies={"issue view": (0, '{"comments": []}')})
    monkeypatch.setattr(GS, "gh", fake)
    rc = GS.cmd_log(_ns(repo="o/r", issue=7, event="progress_recorded",
                        detail="調査中", phase=None, event_id="e3",
                        command=None, result=None))
    assert rc == 0, "block even the light notes and nothing interim gets written at all"


# ── 0.24.0: add "how it breaks" and "a lopsided set of protected things" to the split
#    criteria ──
def test_split_check_flags_multiple_failure_modes(monkeypatch):
    """Even with the same `owns`, a different way of breaking and a different means of verification
    make it a different Issue.

    #11 in the field was closed under supabase/ and so was not split by the owns criterion, while its
    content held two separate ways of breaking: "the shape of the schema (types, constraints)" and
    "authorization (attack scenarios)".
    Five migrations ended up interfering with each other, and twelve rounds did not finish it.
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
    assert "it can break in" in out


def test_split_check_flags_boundary_only_authz(monkeypatch):
    """Warn about requirements that set only the boundary and never the inside.

    「非メンバーが」 ("a non-member") is about the boundary. Counting it as inside by substring voids
    the check entirely.
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
    assert "what can be done once inside" in out, out


def test_split_check_does_not_flag_a_single_concern(monkeypatch):
    """An Issue with a single concern draws no warning (#8 and #10 in the field passed in one or two
    rounds)."""
    body = ("## MUST\n"
            "- WHEN 支出が3人で割られる THE system SHALL 合計が一致する配分を返す\n"
            "- IF 端数が出る THEN THE system SHALL 決定的な順序で配る\n"
            "- The system SHALL 同一入力に対し同一の結果を返す\n"
            "- The system SHALL 負の負担額を返さない\n")
    fake = FakeGh(replies={"issue view": (0, json.dumps({"body": body, "title": "t"}))})
    monkeypatch.setattr(GS, "gh", fake)
    rc, out = _quiet(GS.cmd_split_check, _ns(repo="o/r", issue=7))
    assert "it can break in" not in out and "what can be done once inside" not in out, out


# ── 0.27.0: the supervisor's record is machine-checked too (the fourth layer alone had no
#    check) ──
def _cv(**kw):
    base = dict(repo="o/r", issue=5, event="design_decided", verdict="pass",
                why="what was weighed and what decided it — a real account here",
                by="supervisor", phase=None, evidence="npm test → 27 passed",
                alternatives=None, standard=None, risk=None, event_id="ev-cv",
                claimed=None, verified=None)
    base.update(kw)
    return _ns(**base)


def test_verified_without_a_trace_of_running_is_flagged(monkeypatch, capsys):
    """Writing "confirmed" is not the same as having confirmed.

    In the field this org detected "stating something unverified as though it were verified" eight
    times. That failure mode then appeared in **the side doing the detecting** — the supervisor.
    """
    fake = CommentGh(); monkeypatch.setattr(GS, "gh", fake)
    GS.cmd_decide(_cv(claimed="maker が client.ts を読んだと報告", verified="確認した"))
    err = capsys.readouterr().err
    assert "trace of anything actually run" in err, err


def test_dropped_condition_in_the_summary_is_flagged(monkeypatch, capsys):
    """Warn where a qualifier in --claimed goes untouched by --verified.

    #32 in the field: the maker honestly wrote 「このブランチにまだ存在せず」 ("it does not exist on
    this branch yet"), the supervisor's summary dropped that qualifier, and the loss flowed into the
    instructions to the gate and became a reason for rejection.
    """
    fake = CommentGh(); monkeypatch.setattr(GS, "gh", fake)
    GS.cmd_decide(_cv(claimed="src/db/client.ts はこのブランチに存在せず feat/issue-11 側にある",
                      verified="npm test → 27 passed"))
    err = capsys.readouterr().err
    assert "carries a qualifier" in err, err


def test_carrying_the_condition_through_is_silent(monkeypatch, capsys):
    """It stays quiet where the qualifier is carried. A different inflection (存在せず / 存在しない)
    must not produce a false positive."""
    fake = CommentGh(); monkeypatch.setattr(GS, "gh", fake)
    GS.cmd_decide(_cv(claimed="client.ts はこのブランチに存在せず feat/issue-11 側にある",
                      verified="git ls-files src/db/client.ts → 出力なし（存在しないことを確認）"))
    err = capsys.readouterr().err
    assert "carries a qualifier" not in err, err


def test_legacy_calls_without_claimed_verified_still_pass(monkeypatch, capsys, tmp_path):
    """An older call passing neither --claimed nor --verified still passes (backward
    compatible)."""
    led = tmp_path / "led"; led.mkdir()
    monkeypatch.setenv("ORG_LEDGER_ROOT", str(led))
    fake = CommentGh(); monkeypatch.setattr(GS, "gh", fake)
    rc = GS.cmd_decide(_cv())
    assert rc == 0
    assert "trace of anything actually run" not in capsys.readouterr().err


# ── 0.30.0: integration_admitted presupposes an admit from the gate ─────────
def test_integration_admitted_requires_a_gate_admit(monkeypatch, tmp_path, capsys):
    """`integration_admitted = pass` used to pass on an Issue that had been through neither the gate
    nor the skeptic.

    The ledger already runs this same check against `phase_started` (implement is refused unless
    design was admitted). **The quality of the maker's report is no substitute for an admit.**
    """
    led = tmp_path / "led"; led.mkdir()
    monkeypatch.setenv("ORG_LEDGER_ROOT", str(led))
    fake = CommentGh(); monkeypatch.setattr(GS, "gh", fake)
    rc = GS.cmd_decide(_cv(issue=42, event="integration_admitted", verdict="pass"))
    assert rc == 4, "an integration record passed with no admit from the gate"
    err = capsys.readouterr().err
    assert "no admit from the gate" in err
    assert "verify" in err and "--role gate" in err, "the command to type is not shown"
    assert not fake.posted, "it must not be recorded on the Issue either"


def test_integration_admitted_passes_after_an_admit(monkeypatch, tmp_path):
    """With an admit, it passes."""
    led = tmp_path / "led2"; led.mkdir()
    # **Seed with a real append.** Placing a hand-written fake event (with no hash / prev_hash) is
    # correctly refused by Writer Phase 0's soundness check — appending to a ledger with no chain
    # must not be possible.
    # That the tests had been running against a fake ledger only came to light once Phase 0 went
    # in.
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
    assert rc == 0, "an integration with an admit was rejected"


# ══ H1 — separate who judged, who recorded, and who settled it ══════════════
# **`actor` mixed all three.** Where a supervisor proxy-records a judge's judgment, the observed
# actor is always the supervisor, so a separation of duties comparing actors can only say "the
# supervisor did not approve the supervisor". decision_by is settled **only from a verified
# receipt**.

import subprocess as _sp


def _h1_org(tmp_path):
    """A disposable org where a receipt can be verified. The working tree is fixed so the subject
    does not move."""
    org = tmp_path / "org"
    (org / ".orgforge" / "ledger").mkdir(parents=True)
    (org / ".orgforge" / "trust").mkdir(parents=True)
    import shutil as _sh
    _sh.copy(REPO / "template" / "ledger-schema.yaml", org / "ledger-schema.yaml")
    (org / "constitution.yaml").write_text(
        "enforcement:\n  judges:\n    lineage: cross-harness\n", encoding="utf-8")
    (org / "REQUIREMENTS.md").write_text("MUST: A\n", encoding="utf-8")
    # **Untrack the ledger and the trust store** — content changing during a run moves the subject
    # and it stops matching the receipt (a consequence of review_subject bundling the whole working
    # tree).
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


_H1_WHY = ("the gate's reason for its judgment. It writes the range it independently re-derived, "
           "and the specific place that decided it.")


def _h1_setup(tmp_path, keys=(("k-gate", "gate-signer"),)):
    org = _h1_org(tmp_path)
    for kid, sid in keys:
        # **The H1 tests check Compatibility Mode.** 0.38.0 made keygen's default asymmetric
        # (Authenticated Mode), so the shared key is stated explicitly.
        r = _tool(org, "identity.py", "keygen", "--key-id", kid, "--signer-id", sid,
                  "--shared-secret")
        assert r.returncode == 0, r.stdout + r.stderr
    sys.path.insert(0, str(REPO / "tools"))
    from orgcycle._core import review_subject
    from ghsync.record import _reasoning_digest
    subj = review_subject(7, "gate", "implement", cwd=str(org))[0]
    dig = _reasoning_digest(_H1_WHY, "the trace that was read", "", "", "")
    import hashlib as _h
    reqd = _h.sha256((org / "REQUIREMENTS.md").read_bytes()).hexdigest()[:16]
    return org, subj, dig, reqd


def _h1_receipt(org, subj, dig, reqd, key_id="k-gate", role="gate",
                lineage="same-harness", verdict="admit", issue="7", out="r.json"):
    # **org_id / ledger_id are determined by the write target.** The receipt is matched to them —
    # without that it is correctly refused as "a receipt from another org" (0.39.5 completed the
    # binding).
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
            "--evidence", "the trace that was read"]
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
    """`decision_by` comes only from a receipt. No CLI argument declares it."""
    org, subj, dig, reqd = _h1_setup(tmp_path)
    rc = _h1_receipt(org, subj, dig, reqd)
    r = _h1_prov(org, subj, rc)
    assert r.returncode == 0, r.stdout + r.stderr
    pl = _h1_events(org)[0]["payload"]
    assert pl["decision_by"] == "gate-signer"
    assert pl["identity_assurance"] == "attested"     # a shared key, so not authenticated
    assert pl["signer_id"] == "gate-signer" and pl["key_id"] == "k-gate"
    # **Not written into the payload — the writer verified the receipt and generated it** (0.39.4)
    # There must be no path for declaring decision_by on the CLI
    h = _tool(org, "github_sync.py", "provisional", "--help")
    assert "--decision-by" not in h.stdout


def test_recorded_by_is_observed_and_decision_by_survives_proxy_recording(tmp_path):
    """**A proxy recording does not lose the judge's identity.**

    Even where a supervisor records it from a different session, `decision_by` stays the judge. That
    is what "proxy recording and authentication coexist" amounts to.
    """
    org, subj, dig, reqd = _h1_setup(tmp_path)
    rc = _h1_receipt(org, subj, dig, reqd)
    env = dict(_h1_env(org), ORG_SESSION_ID="supervisor-session-99")
    r = _h1_prov(org, subj, rc, env=env)
    assert r.returncode == 0, r.stdout + r.stderr
    pl = _h1_events(org)[0]["payload"]
    assert pl["decision_by"] == "gate-signer"          # still the judge
    assert pl["recorded_by"] == "session:supervisor-session-99"
    assert pl["recorder_assurance"] == "observed"


def test_receipt_cannot_be_replayed_into_another_judgment(tmp_path):
    """Reuse against a different issue / subject / lineage is refused."""
    org, subj, dig, reqd = _h1_setup(tmp_path)
    rc = _h1_receipt(org, subj, dig, reqd)
    for kw in ({"issue": "9"}, {"lineage": "cross-harness"}, {"verdict": "reject"}):
        r = _h1_prov(org, subj, rc, **kw)
        assert r.returncode == 4, f"it passed with {kw}: {r.stdout + r.stderr}"
        assert "does not match" in (r.stdout + r.stderr)
    assert _h1_events(org) == []


def test_tampering_with_a_receipt_is_refused(tmp_path):
    """Rewriting a bound value makes the signature stop matching."""
    org, subj, dig, reqd = _h1_setup(tmp_path)
    rc = _h1_receipt(org, subj, dig, reqd)
    d = json.loads(rc.read_text(encoding="utf-8"))
    d["signer_id"] = "someone-else"
    rc.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    r = _h1_prov(org, subj, rc)
    assert r.returncode == 4
    both = r.stdout + r.stderr
    assert "signature does not match" in both or "does not match" in both


def test_a_revoked_key_is_refused(tmp_path):
    """A receipt from a revoked key is not accepted."""
    org, subj, dig, reqd = _h1_setup(tmp_path)
    rc = _h1_receipt(org, subj, dig, reqd)
    assert _tool(org, "identity.py", "revoke", "--key-id", "k-gate",
                 "--reason", "a check").returncode == 0
    r = _h1_prov(org, subj, rc)
    assert r.returncode == 4
    assert "has been revoked" in (r.stdout + r.stderr)


def test_unreadable_trust_store_does_not_record_the_judgment(tmp_path):
    """**"Unreadable" is never read as "trustworthy".** Where the judging principal cannot be
    confirmed, nothing is recorded."""
    org, subj, dig, reqd = _h1_setup(tmp_path)
    rc = _h1_receipt(org, subj, dig, reqd)
    env = dict(_h1_env(org), ORG_TRUST_STORE="/nonexistent/keys.json")
    r = _h1_prov(org, subj, rc, env=env)
    assert r.returncode == 4
    assert "trust store" in (r.stdout + r.stderr)
    assert _h1_events(org) == []


def test_without_a_receipt_identity_stays_claimed(tmp_path):
    """With no receipt it stays `claimed` — **nothing is promoted.**"""
    org, subj, dig, reqd = _h1_setup(tmp_path)
    r = _h1_prov(org, subj, None, role="skeptic", verdict="survives", issue="11")
    assert r.returncode == 0, r.stdout + r.stderr
    pl = _h1_events(org)[0]["payload"]
    assert pl["identity_assurance"] == "claimed"
    assert pl["decision_by"] == "skeptic"          # the legacy actor equivalent (declared)


def test_same_signer_on_both_lineages_is_not_independent_review(tmp_path):
    """**Signed or not, if one signer can produce both, it is not independent review.**

    The agreement still holds, but it is recorded as `reviewer_independence = same_signer` and
    warned about. It must not be counted as evidence of independence.
    """
    org, subj, dig, reqd = _h1_setup(tmp_path)
    r1 = _h1_receipt(org, subj, dig, reqd, lineage="same-harness", out="r1.json")
    r2 = _h1_receipt(org, subj, dig, reqd, lineage="cross-harness", out="r2.json")
    assert _h1_prov(org, subj, r1, lineage="same-harness").returncode == 0
    r = _h1_prov(org, subj, r2, lineage="cross-harness")
    assert r.returncode == 0, r.stdout + r.stderr
    both = r.stdout + r.stderr
    assert "the same signer signed both" in both
    adm = _h1_events(org, "admission_decided")
    assert len(adm) == 1
    assert adm[0]["payload"]["reviewer_independence"] == "same_signer"


def test_distinct_signers_are_recorded_as_independent(tmp_path):
    """A different signer per lineage gives `distinct_signer`."""
    org, subj, dig, reqd = _h1_setup(tmp_path,
                                     keys=(("k-gate", "gate-signer"), ("k-two", "second-signer")))
    r1 = _h1_receipt(org, subj, dig, reqd, key_id="k-gate", lineage="same-harness", out="r1.json")
    r2 = _h1_receipt(org, subj, dig, reqd, key_id="k-two", lineage="cross-harness", out="r2.json")
    assert _h1_prov(org, subj, r1, lineage="same-harness").returncode == 0
    assert _h1_prov(org, subj, r2, lineage="cross-harness").returncode == 0
    adm = _h1_events(org, "admission_decided")
    assert adm and adm[0]["payload"]["reviewer_independence"] == "distinct_signer"


def test_separation_of_duties_compares_decision_by_not_recorded_by(tmp_path):
    """**The separation of duties compares `decision_by` values.** Comparing recorded_by makes every
    proxy recording a violation."""
    sys.path.insert(0, str(REPO / "tools"))
    import importlib
    led = importlib.import_module("ledger")
    hist = [{"class": "cycle_completed", "actor": "supervisor",
             "payload": {"deliverable": "7", "decision_by": "maker-alice",
                         "recorded_by": "session:sup"}}]
    ev = {"class": "admission_decided", "actor": "supervisor",
          "payload": {"deliverable": "7", "verdict": "admit",
                      "decision_by": "maker-alice", "recorded_by": "session:sup"}}
    assert led._distinct_actor_violation(ev, hist), "a maker can admit its own work"
    # A different judge passes (even where the recorder is the same)
    ev["payload"]["decision_by"] = "gate-signer"
    assert led._distinct_actor_violation(ev, hist) is None, (
        "a proxy recording is being treated as a violation")


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
    # the carve-out invariant: "a carve-out depends on its origin" holds without exception — so the
    # create
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
    rc = GS.cmd_park(_ns(repo="o/r", issue=42, why=None))
    assert rc == 0
    assert not fake.calls_matching("issue edit") and not fake.calls_matching("issue comment")


def test_park_already_parked_still_records_a_new_why(monkeypatch):
    # gate residual (#103 rework): a --why on an already-parked issue must not be silently
    # dropped — the reason is the part a later unparker needs.
    fake = FakeGh(replies={"--json labels": (0, '{"labels": [{"name": "orgforge:parked"}]}')})
    monkeypatch.setattr(GS, "gh", fake)
    rc = GS.cmd_park(_ns(repo="o/r", issue=42, why="also blocked by the API freeze"))
    assert rc == 0
    assert not fake.calls_matching("issue edit"), "label is already there — no relabel"
    comments = fake.calls_matching("issue comment 42")
    assert comments and any("API freeze" in " ".join(c) for c in comments), fake.calls


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


def test_ready_reports_unverifiable_withholds_machine_readably(monkeypatch, capsys):
    # gate rework (#103): withholding on an unverifiable dependency while emitting exactly
    # {"ready": []} is indistinguishable from "no ready work" — during partial gh degradation
    # the org silently stalls with no observable cause, the same machine-invisible-state class
    # this issue exists to kill. The withhold must be VISIBLE: machine-readably in the JSON
    # (additive field) and loudly on stderr, naming the issue and the dep.
    listing = ('[{"number": 1, "title": "t", "labels": [{"name": "orgforge:kind:task"}],'
               ' "body": "Depends on: #9"}]')
    fake = FakeGh(replies={"issue list": (0, listing),
                           "issue view 9": (1, "gh: Not Found")})
    monkeypatch.setattr(GS, "gh", fake)
    rc = GS.cmd_ready(_ns(repo="o/r", kind="task"))
    captured = capsys.readouterr()
    assert rc == 0
    out = json.loads(captured.out)
    assert out["ready"] == [] and out["withheld_unverifiable"] == [1], out
    assert "WARN" in captured.err and "#1" in captured.err and "#9" in captured.err, captured.err


# ── #103 rework 2 (skeptic): no token containing a ref is ever silently dropped ──────────────
# The refutation: `Depends on: #63 (main に統合されるまで着手不能)` — the exact hand-written
# form the org's own docs instruct (org-decompose.md §4b) — failed the old fullmatch token
# filter and was DROPPED: ready [1], zero queries, silent stderr. OBS-051 on the documented path.

def _task_listing(*issues):
    return json.dumps([{"number": n, "title": f"t{n}",
                        "labels": [{"name": "orgforge:kind:task"}], "body": b}
                       for n, b in issues])


def test_ready_verifies_annotated_dependency_tokens(monkeypatch):
    fake = FakeGh(replies={"issue list": (0, _task_listing(
        (1, "Depends on: #63 (main に統合されるまで着手不能)"))),
        "issue view 63": (0, '{"state": "OPEN"}')})
    rc, ready = _ready(monkeypatch, fake)
    assert rc == 0 and ready == [], ready
    assert fake.calls_matching("issue view 63"), "the annotated ref was never verified"


def test_ready_verifies_and_joined_dependency_refs(monkeypatch):
    fake = FakeGh(replies={"issue list": (0, _task_listing((1, "Depends on: #63 and #64"))),
                           "issue view 63": (0, '{"state": "OPEN"}'),
                           "issue view 64": (0, '{"state": "CLOSED"}')})
    rc, ready = _ready(monkeypatch, fake)
    assert rc == 0 and ready == [], ready


@pytest.mark.parametrize("header", ["Depends On : #9", "Depends-on: #9", "**Depends on:** #9",
                                    "- Depends on: #9", "> Depends on: #9", "depends_on: #9"])
def test_ready_recognizes_depends_header_variants(monkeypatch, header):
    fake = FakeGh(replies={"issue list": (0, _task_listing((1, header))),
                           "issue view 9": (0, '{"state": "OPEN"}')})
    rc, ready = _ready(monkeypatch, fake)
    assert rc == 0 and ready == [], (header, ready)


def test_ready_annotated_unverifiable_dependency_is_reported(monkeypatch, capsys):
    fake = FakeGh(replies={"issue list": (0, _task_listing((1, "Depends on: #9 (integration)"))),
                           "issue view 9": (1, "gh: Not Found")})
    monkeypatch.setattr(GS, "gh", fake)
    rc = GS.cmd_ready(_ns(repo="o/r", kind="task"))
    captured = capsys.readouterr()
    out = json.loads(captured.out)
    assert rc == 0 and out["ready"] == [] and out["withheld_unverifiable"] == [1], out
    assert "#9" in captured.err, captured.err


def test_ready_depends_none_is_an_explicit_no_dep_declaration(monkeypatch):
    # zero refs on a Depends-on line = explicit "no dependencies": silent, no queries, ready
    fake = FakeGh(replies={"issue list": (0, _task_listing((1, "Depends on: none")))})
    rc, ready = _ready(monkeypatch, fake)
    assert rc == 0 and ready == [1], ready
    assert not fake.calls_matching("issue view"), "a no-dep declaration must not be queried"


def test_create_warns_when_depends_none_but_prose_references_issues(monkeypatch, capsys):
    # `Depends on: none` must not suppress the prose-ref WARN — the declaration says "no deps"
    # while the prose says otherwise; that contradiction is exactly what to surface.
    fake = FakeGh(replies={"issue create": (0, "https://github.com/o/r/issues/90")})
    monkeypatch.setattr(GS, "gh", fake)
    rc = GS.cmd_create(_create_ns(body="Depends on: none\n\nNeeds parts produced by #63."))
    assert rc == 0
    err = capsys.readouterr().err
    assert "WARN" in err and "#63" in err, err


def test_create_does_not_warn_on_github_closing_keywords(monkeypatch, capsys):
    # Fixes/Closes/Resolves #N is a closing reference, not a dependency — a false-positive WARN
    # trains operators to ignore the real one.
    fake = FakeGh(replies={"issue create": (0, "https://github.com/o/r/issues/91")})
    monkeypatch.setattr(GS, "gh", fake)
    rc = GS.cmd_create(_create_ns(body="Fixes #12 by adding a regression guard.\nCloses #13."))
    assert rc == 0
    assert "WARN" not in capsys.readouterr().err


def test_ready_open_dependency_withhold_is_not_reported_as_unverifiable(monkeypatch, capsys):
    # an OPEN dependency is a normal, healthy withhold — it must NOT trip the degradation alarm
    listing = ('[{"number": 1, "title": "t", "labels": [{"name": "orgforge:kind:task"}],'
               ' "body": "Depends on: #9"}]')
    fake = FakeGh(replies={"issue list": (0, listing),
                           "issue view 9": (0, '{"state": "OPEN"}')})
    monkeypatch.setattr(GS, "gh", fake)
    rc = GS.cmd_ready(_ns(repo="o/r", kind="task"))
    captured = capsys.readouterr()
    assert rc == 0
    out = json.loads(captured.out)
    assert out["ready"] == [] and out["withheld_unverifiable"] == [], out
    assert "WARN" not in captured.err, captured.err
    # ...but the withhold is still OBSERVABLE (info line, not an alarm): empty-because-waiting
    # must be distinguishable from empty-because-nothing on stderr (skeptic, #103 rework 2)
    assert "#9" in captured.err, captured.err


# ── review-response: a response has to point AT something (Issue #67 of domain-spec-notes) ──
# The responses there cited SKEPTIC-001/002 while nothing on the Issue defined those ids, so
# "addressed" was unfalsifiable from the outside. `--review` was validated on its shape alone.

_REVIEW_COMMENT = (
    "### 🧪 verdict_provisional — `refuted` (same-harness)\n"
    "**review_subject_id:** `abc123`\n\n"
    "SKEPTIC-001: the template cannot express required relations.\n"
    "<!-- orgforge:provisional:same-harness:deadbeef -->")


def _rr_ns(**kw):
    base = dict(repo="o/r", issue=67, review="abc123", finding="SKEPTIC-001", status="addressed",
                response="Added required_relations to the normative schema and propagated it.",
                evidence="commit b51c76b; make test: 10 passed; rg required_relations: 5 hits.",
                by="maker", blocked_by=None)
    base.update(kw)
    return _ns(**base)


def _issue_with(*comment_bodies):
    return json.dumps({"comments": [{"body": b, "url": f"https://gh/c/{i}"}
                                    for i, b in enumerate(comment_bodies)]})


def test_review_response_refuses_a_finding_that_was_never_written(monkeypatch, capsys):
    """**A response cannot answer a finding nobody recorded.** Without this, `addressed` is a claim
    no reviewer can check — which is how #67 came to carry responses to undefined ids."""
    fake = FakeGh(replies={"issue view": (0, _issue_with("unrelated chatter"))})
    monkeypatch.setattr(GS, "gh", fake)
    rc = GS.cmd_review_response(_rr_ns())
    assert rc == 2
    assert "never written down" in capsys.readouterr().err
    assert fake.calls_matching("issue comment") == [], "it must not post an unanchored response"


def test_review_response_carries_the_finding_and_links_back(monkeypatch, capsys):
    """**Carry the finding, not just its id.** A reader of the response alone could otherwise see
    only `SKEPTIC-001 (addressed)` with no way to tell what was addressed."""
    fake = FakeGh(replies={"issue view": (0, _issue_with(_REVIEW_COMMENT))})
    monkeypatch.setattr(GS, "gh", fake)
    assert GS.cmd_review_response(_rr_ns()) == 0
    body = " ".join(fake.calls_matching("issue comment")[0])
    assert "The finding being answered" in body
    assert "cannot express required relations" in body, "the finding text itself is missing"
    assert "https://gh/c/0" in body, "there is no link back to the review"


def test_review_response_matches_on_the_finding_id_too(monkeypatch):
    """A review comment carries its review_subject_id; the finding id may live only in the prose.
    Either is a real anchor, so either resolves."""
    fake = FakeGh(replies={"issue view": (0, _issue_with(_REVIEW_COMMENT))})
    monkeypatch.setattr(GS, "gh", fake)
    assert GS.cmd_review_response(_rr_ns(review="a-subject-id-not-in-the-comment")) == 0
    assert fake.calls_matching("issue comment")


def test_review_response_does_not_quote_another_response_as_the_review(monkeypatch, capsys):
    """A previous response mentions the same ids. Quoting it back would make a response look like
    the finding it answers, and the chain would anchor to nothing."""
    prior = ("### ↪ Review response — `SKEPTIC-001` (addressed)\n"
             "**Review:** `abc123`\n<!-- orgforge:review-response:abc123:SKEPTIC-001:addressed -->")
    fake = FakeGh(replies={"issue view": (0, _issue_with(prior))})
    monkeypatch.setattr(GS, "gh", fake)
    rc = GS.cmd_review_response(_rr_ns(status="deferred"))
    assert rc == 2, "the only match was another response — that is not an anchor"
    assert "never written down" in capsys.readouterr().err


# ── review-findings: a rally you cannot count is a rally you cannot end ──────────────────────
# Findings used to be ids inside a judge's prose, so nothing could say how many were open or
# which had been answered. Every round therefore read as whack-a-mole.

_VERDICT_WITH_FINDINGS = (
    '### verdict_provisional — `reject`\n'
    '{"findings": [{"id": "GATE-001", "claim": "required relations are not expressible"},'
    ' {"id": "GATE-002", "claim": "the standards ledger is incomplete"}]}')


def test_review_findings_counts_what_is_still_open(monkeypatch, capsys):
    answered = ("### ↪ Review response — `GATE-001` (addressed)\n"
                "<!-- orgforge:review-response:abc:GATE-001:addressed -->")
    fake = FakeGh(replies={"issue view": (0, _issue_with(_VERDICT_WITH_FINDINGS, answered))})
    monkeypatch.setattr(GS, "gh", fake)
    assert GS.cmd_review_findings(_ns(repo="o/r", issue=67)) == 0
    captured = capsys.readouterr()
    out = json.loads(captured.out)
    assert (out["raised"], out["answered"], out["open"]) == (2, 1, 1)
    assert [f["id"] for f in out["open_findings"]] == ["GATE-002"]
    assert "GATE-002" in captured.err, "the open finding must be visible without reading JSON"


def test_review_findings_reports_answers_to_findings_that_were_never_recorded(monkeypatch, capsys):
    """**"raised: 0, answered: 7" is not a clean sheet, it is a blind spot.** That is the real
    state of domain-spec-notes #67: the findings existed only as prose inside a verdict."""
    answered = ("### ↪ Review response — `SKEPTIC-001` (addressed)\n"
                "<!-- orgforge:review-response:abc:SKEPTIC-001:addressed -->")
    fake = FakeGh(replies={"issue view": (0, _issue_with(answered))})
    monkeypatch.setattr(GS, "gh", fake)
    assert GS.cmd_review_findings(_ns(repo="o/r", issue=67)) == 0
    captured = capsys.readouterr()
    assert json.loads(captured.out)["answered_but_never_raised"] == ["SKEPTIC-001"]
    assert "no finding recorded" in captured.err
