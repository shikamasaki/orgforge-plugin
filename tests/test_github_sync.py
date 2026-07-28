"""github_sync — the backlog↔GitHub-Issue projection (integrations/web).

`gh` is the network boundary; we monkeypatch `github_sync.gh` so these tests exercise the org's LOGIC
(the two-level objective/task hierarchy, the idempotent work-log, dependency/kind filtering, sub-issue
linking) without touching GitHub. The one thing we assert is that the org builds the right gh calls and
makes the right decisions from their results — the reproducible, testable part."""
import importlib.util
import json
import pathlib

REPO = pathlib.Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("github_sync", REPO / "tools" / "github_sync.py")
GS = importlib.util.module_from_spec(spec)
spec.loader.exec_module(GS)


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


# ── two-level hierarchy: objective vs task ───────────────────────────────────
def test_create_objective_labels_kind_objective(monkeypatch):
    fake = FakeGh(replies={"issue create": (0, "https://github.com/o/r/issues/10")})
    monkeypatch.setattr(GS, "gh", fake)
    rc = GS.cmd_create(_ns(repo="o/r", title="Ship the settle-up app", body=None, objective="obj1",
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
    rc = GS.cmd_create(_ns(repo="o/r", title="build money core", body=None, objective="obj1",
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
    fake = FakeGh(replies={"issue list": (0, existing)})
    monkeypatch.setattr(GS, "gh", fake)
    rc = GS.cmd_create(_ns(repo="o/r", title="build money core", body=None, objective="obj1",
                           source=None, depends=None, priority=None, kind="task", dept=None, parent=None))
    assert rc == 0
    assert not fake.calls_matching("issue create"), "must NOT create a duplicate"


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
                        detail=None, phase=None, event_id="evABC"))
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
