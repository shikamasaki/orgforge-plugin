"""A Claude headless judge's verdict is collected from `structured_output`, not from `result`.

`claude -p --output-format json --json-schema ...` returns the answer twice in one envelope:

    structured_output : dict — the schema-validated object the flag produced
    result            : str  — the same content rendered for display

The collector read `result` and re-parsed it, which threw away a validated object to recover it
from a string. That works only while the model emits bare JSON; the moment it wraps the JSON in
any prose, the parse fails and a review that actually ran looks like it returned nothing. In the
field this showed up as the gate "not responding" twice while the CLI itself answered normally
(~6s plain, ~13.5s with a schema) — the verdict was produced and then dropped on the floor.
"""
import json
import sys

import pytest

from conftest import TEMPLATE, TOOLS

sys.path.insert(0, str(TOOLS))
from orgcycle import judge as J  # noqa: E402

SCHEMA = str(TEMPLATE / "schemas" / "gate-verdict.json")
VERDICT = {"verdict": "admit", "why": "the MUSTs were re-derived", "evidence": "npm test: 19 passed"}


class _Proc:
    def __init__(self, stdout, returncode=0, stderr=""):
        self.stdout, self.returncode, self.stderr = stdout, returncode, stderr


def _run(monkeypatch, capsys, envelope, cfg=None):
    monkeypatch.setattr(J.shutil, "which", lambda c: "/usr/bin/true")
    monkeypatch.setattr(J.subprocess, "run", lambda *a, **k: _Proc(envelope))
    rc = J._run_headless("gate", 1, "material", cfg or {"cli": "claude"}, SCHEMA)
    return rc, capsys.readouterr()


def test_structured_output_is_preferred_over_the_display_string(monkeypatch, capsys):
    """Both fields are present and agree: the dict is what gets collected."""
    envelope = json.dumps({"result": json.dumps(VERDICT), "structured_output": VERDICT})
    rc, out = _run(monkeypatch, capsys, envelope)
    assert rc == 0
    assert json.loads(out.out.strip().split("\n")[0]) == VERDICT


def test_prose_wrapped_result_no_longer_loses_the_verdict(monkeypatch, capsys):
    """The regression itself: `result` carries prose around the JSON, structured_output does not.

    Reading `result` here yields something intake cannot parse. Reading structured_output yields
    the verdict, which is the whole point of asking for a schema.
    """
    envelope = json.dumps({
        "result": "Here is my verdict:\n```json\n" + json.dumps(VERDICT) + "\n```\nHope that helps!",
        "structured_output": VERDICT,
    })
    rc, out = _run(monkeypatch, capsys, envelope)
    assert rc == 0
    assert json.loads(out.out.strip().split("\n")[0]) == VERDICT


def test_falls_back_to_result_when_structured_output_is_absent(monkeypatch, capsys):
    """An older CLI has no structured_output. Keep working rather than reporting nothing."""
    envelope = json.dumps({"result": json.dumps(VERDICT)})
    rc, out = _run(monkeypatch, capsys, envelope)
    assert rc == 0
    assert json.loads(out.out.strip().split("\n")[0]) == VERDICT


def test_an_error_envelope_is_announced_rather_than_passed_off_as_a_verdict(monkeypatch, capsys):
    """An envelope can report an error and still carry text; a degraded answer must not look clean."""
    envelope = json.dumps({"result": json.dumps(VERDICT), "structured_output": VERDICT,
                           "is_error": True, "stop_reason": "max_tokens"})
    rc, out = _run(monkeypatch, capsys, envelope)
    assert "envelope reports an error" in out.err
    assert "max_tokens" in out.err


def test_a_non_json_envelope_still_fails_closed(monkeypatch, capsys):
    """Unparseable output yields no verdict — and says why, rather than inventing one."""
    rc, out = _run(monkeypatch, capsys, "not json at all")
    assert rc in (0, 7)
    if rc == 7:
        assert "empty" in out.err or "exit=" in out.err


@pytest.mark.parametrize("empty", ["", "   ", json.dumps({"result": ""})])
def test_empty_output_is_fail_closed(monkeypatch, capsys, empty):
    rc, out = _run(monkeypatch, capsys, empty)
    assert rc == 7, "no verdict must not be reported as success"
