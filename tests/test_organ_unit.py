"""Unit tests for the shared tools/_organ.py substrate."""
import io
import json
import os
import pathlib
import sys
from contextlib import redirect_stdout

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "tools"))
import _organ  # noqa: E402


def test_constants():
    assert _organ.ESCALATE == 10
    assert _organ.OK == 0


def test_ledger_path():
    assert _organ.ledger_path("/x") == os.path.join("/x", "ledger.jsonl")


def test_read_events_missing_is_empty(tmp_path):
    assert _organ.read_events(str(tmp_path)) == []


def test_read_events_skips_blanks_and_parses(tmp_path):
    log = tmp_path / "ledger.jsonl"
    log.write_text('{"seq":1,"class":"a"}\n\n  \n{"seq":2,"class":"b"}\n')
    evs = _organ.read_events(str(tmp_path))
    assert [e["seq"] for e in evs] == [1, 2]
    assert all(isinstance(e, dict) for e in evs)


def test_emit_event_exact_stdout():
    buf = io.StringIO()
    with redirect_stdout(buf):
        _organ.emit_event("my_class", {"k": "v", "n": 1})
    out = buf.getvalue()
    assert out == 'LEDGER-EVENT {"class": "my_class", "payload": {"k": "v", "n": 1}}\n'


def test_emit_event_non_ascii_literal():
    buf = io.StringIO()
    with redirect_stdout(buf):
        _organ.emit_event("c", {"msg": "気まずい"})
    assert "気まずい" in buf.getvalue()   # ensure_ascii=False keeps it literal
