"""A goal appears on GitHub, or says out loud that it did not.

`org_goal` used to write `goal_started` / `goal_completed` to the ledger and nowhere else. An agent
could start a goal, implement, commit, push, open a PR, and complete the goal with **no Issue at
any point**, then truthfully report "recorded in OrgForge" — because it was, in a local ledger only
the host that wrote it can read. Everyone else saw nothing.

It also routed around every check that exists on the Issue path. `split-check` and `ready` are what
require EARS acceptance, a runnable DoD command, counterexamples and the domain sections; they run
on Issues. A goal that never becomes an Issue is never asked for any of them, which is how a
proof-of-concept was built and "completed" with no spec at all.

The projection is best-effort by design — a goal exists to survive a lost session, so an
unconfigured `gh` must not prevent recording one. What it must never do is degrade **silently**.
"""
import sys

import pytest

from conftest import TOOLS

sys.path.insert(0, str(TOOLS))
import goal_issue  # noqa: E402

GOAL = "goal-1bdc1a24c9b6"


class _Gh:
    """A scripted `gh`, recording what was asked of it."""

    def __init__(self, *, existing=None, create_fails=None):
        self.calls, self.existing, self.create_fails = [], existing, create_fails

    def __call__(self, args, timeout=30):
        self.calls.append(args)
        if args[:2] == ["issue", "list"]:
            body = f"<!-- orgforge:goal:{GOAL} -->" if self.existing else ""
            return 0, f'[{{"number": {self.existing or 0}, "body": "{body}"}}]'
        if args[:2] == ["issue", "create"]:
            if self.create_fails:
                return 1, self.create_fails
            return 0, "https://github.com/o/r/issues/42\n"
        if args[:2] == ["issue", "view"]:
            return 0, '{"comments": []}'
        return 0, ""


def _install(monkeypatch, gh):
    monkeypatch.setattr(goal_issue, "_gh", gh)


# ── the projection itself ────────────────────────────────────────────────────
def test_starting_a_goal_opens_an_objective_issue(monkeypatch):
    gh = _Gh()
    _install(monkeypatch, gh)
    number, detail = goal_issue.open_goal_issue("o/r", GOAL, "build the thing", "codex")
    assert number == 42 and "42" in detail
    created = [c for c in gh.calls if c[:2] == ["issue", "create"]]
    assert created, "no Issue was created"


def test_the_issue_tells_the_reader_where_the_work_goes(monkeypatch):
    """An objective with no route to a task Issue is how the work drifted off GitHub again."""
    gh = _Gh()
    _install(monkeypatch, gh)
    goal_issue.open_goal_issue("o/r", GOAL, "build the thing", "codex")
    body = next(c for c in gh.calls if c[:2] == ["issue", "create"])[
        next(c for c in gh.calls if c[:2] == ["issue", "create"]).index("--body") + 1]
    assert "github-sync create --kind task" in body
    assert "org-cycle begin" in body
    assert "split-check" in body, "the reader must know the spec check lives on the task Issue"


def test_projection_is_idempotent(monkeypatch):
    """A resumed session must not mint a second objective for the same goal."""
    gh = _Gh(existing=7)
    _install(monkeypatch, gh)
    number, detail = goal_issue.open_goal_issue("o/r", GOAL, "build the thing", "codex")
    assert number == 7 and "already" in detail
    assert not [c for c in gh.calls if c[:2] == ["issue", "create"]]


# ── the label that broke this before ─────────────────────────────────────────
def test_the_objective_label_stays_within_github_s_limit():
    """`--objective` becomes a label, and GitHub refuses one over 50 characters."""
    label = f"orgforge:objective:{goal_issue.objective_label_id(GOAL)}"
    assert len(label) <= 50, label


def test_the_label_id_is_stable_for_a_goal():
    assert goal_issue.objective_label_id(GOAL) == goal_issue.objective_label_id(GOAL)
    assert goal_issue.objective_label_id(GOAL) != goal_issue.objective_label_id("goal-otherid00")


# ── degrading loudly ─────────────────────────────────────────────────────────
def test_a_failed_creation_returns_the_reason(monkeypatch):
    _install(monkeypatch, _Gh(create_fails="HTTP 422: name is too long"))
    number, detail = goal_issue.open_goal_issue("o/r", GOAL, "build the thing", "codex")
    assert number is None
    assert "too long" in detail, "the caller must be able to report WHY, not just that it failed"


def test_commenting_without_a_projected_issue_says_so(monkeypatch):
    _install(monkeypatch, _Gh())          # issue list finds nothing
    ok, detail = goal_issue.comment_on_goal_issue("o/r", GOAL, "Progress", "did a thing")
    assert not ok and GOAL in detail


@pytest.mark.parametrize("env", [{}, {"ORG_GITHUB_REPO": "o/r"}])
def test_repo_resolution_prefers_an_explicit_value(monkeypatch, env):
    for key in ("ORG_GITHUB_REPO", "GH_REPO"):
        monkeypatch.delenv(key, raising=False)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    assert goal_issue.repo_slug("explicit/repo") == "explicit/repo"


def test_org_goal_reports_the_projection_outcome():
    """org_goal must surface the result, or a ledger-only goal looks identical to a projected one."""
    source = (TOOLS / "org_goal.py").read_text(encoding="utf-8")
    assert '"issue": projection' in source
    assert "_project_start" in source and "_project_close" in source
    # and the degraded case has to name its consequence, not just fail quietly
    assert "recorded in the ledger only" in source
