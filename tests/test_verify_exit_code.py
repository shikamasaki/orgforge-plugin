"""A cross-harness dispatch that produced no verdict exits non-zero.

`_run_headless` already diagnosed an empty or malformed child result on stderr — added in 2.5.1.
But `cmd_verify` ended with a bare `return 0`, so that diagnosis was discarded one frame above the
caller: a supervisor reading the exit code saw success, printed the handoff, and moved on with
nothing recorded.

In the field this looked like the child completing and the verdict vanishing (#201). The verdict
never existed; the only signal that said so was thrown away.

Same-harness runs still return 0 — there is no child to fail, and the subagent material on stderr
is the deliverable.
"""
import sys

from conftest import TOOLS

sys.path.insert(0, str(TOOLS))
from orgcycle import judge as J  # noqa: E402

SOURCE = (TOOLS / "orgcycle" / "judge.py").read_text(encoding="utf-8")


def test_an_empty_child_result_is_reported_as_no_verdict(monkeypatch, capsys):
    """The behaviour the exit code has to carry: rc 7 means nothing was judged."""
    class _Empty:
        returncode, stdout, stderr = 0, "", ""

    monkeypatch.setattr(J.shutil, "which", lambda c: "/usr/bin/true")
    monkeypatch.setattr(J.subprocess, "run", lambda *a, **k: _Empty())
    schema = str(TOOLS.parent / "template" / "schemas" / "gate-verdict.json")
    rc = J._run_headless("gate", 182, "material", {"cli": "claude"}, schema)
    err = capsys.readouterr().err
    assert rc == 7
    assert "exit=0" in err and "stdout=0B" in err, "the diagnosis must survive for the operator"


def test_verify_keeps_the_headless_result():
    """Without this, rc 7 dies inside cmd_verify and the caller sees success."""
    assert "_headless_rc = rc" in SOURCE, (
        "the result of _run_headless is not captured; a failed dispatch cannot reach the caller"
    )
    assert "return _headless_rc" in SOURCE, (
        "cmd_verify must return the dispatch result, not an unconditional 0"
    )


def test_the_same_harness_default_is_success():
    """A same-harness org has no child to fail; it must keep exiting 0."""
    assert "_headless_rc = 0" in SOURCE
    assert SOURCE.index("_headless_rc = 0") < SOURCE.index('if _lineage == "cross-harness":'), \
        "the default has to be set before the branch, or same-harness raises NameError"


def test_the_reason_is_recorded_next_to_the_change():
    """The next reader has to know why this is not simply `return 0`."""
    tail = SOURCE[SOURCE.index("return _headless_rc") - 900:SOURCE.index("return _headless_rc")]
    assert "#201" in tail
    assert "exit 0" in tail


def test_the_collector_still_prefers_the_validated_object():
    """Guards against fixing the exit code while regressing the 2.5.1 collection fix."""
    assert "structured_output" in SOURCE
