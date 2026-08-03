import json

from tools.github_checks_projection import project


def test_projection_preserves_unknown_and_never_admits(tmp_path):
    event = {"seq": 2, "class": "phase_admitted", "payload": {"phase": "test", "verdict": "unknown",
                                                                  "missing": ["independent_review"]}}
    (tmp_path / "ledger.jsonl").write_text(json.dumps(event) + "\n")
    result = project(str(tmp_path))
    assert result["projection_only"] is True
    assert result["admission_decision"] is None
    assert result["checks"][0]["conclusion"] == "neutral"
    assert "independent_review" in result["checks"][0]["output"]["text"]
