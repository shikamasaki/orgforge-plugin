import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
TOOL = REPO / "tools" / "shared_fate.py"


def _compare(tmp_path, left, right, policy):
    paths = []
    for name, value in (("left", left), ("right", right), ("policy", policy)):
        path = tmp_path / f"{name}.json"
        path.write_text(json.dumps(value), encoding="utf-8")
        paths.append(path)
    return subprocess.run([sys.executable, str(TOOL), "compare", "--left", str(paths[0]),
                           "--right", str(paths[1]), "--policy", str(paths[2]), "--json"],
                          capture_output=True, text=True)


def test_must_differ_and_must_match_are_axis_specific(tmp_path):
    left = {"shared_fate": {"model": "m1", "provider": "p1", "baseline": "b1"}}
    right = {"shared_fate": {"model": "m2", "provider": "p1", "baseline": "b1"}}
    policy = {"must_differ": ["model"], "may_share": ["provider"], "must_match": ["baseline"]}
    run = _compare(tmp_path, left, right, policy)
    assert run.returncode == 0
    result = json.loads(run.stdout)
    assert result["independent"] is True
    assert result["vector"]["model"]["status"] == "different"
    assert result["vector"]["provider"]["status"] == "shared"
    assert result["vector"]["baseline"]["status"] == "matched"


def test_same_model_and_context_is_not_independent(tmp_path):
    record = {"shared_fate": {"model": "m1", "context_digest": "c1"}}
    run = _compare(tmp_path, record, record, {"must_differ": ["model", "context_digest"]})
    assert run.returncode == 3
    result = json.loads(run.stdout)
    assert result["independent"] is False
    assert result["blocking_axes"] == ["context_digest", "model"]


def test_missing_axis_never_becomes_different(tmp_path):
    run = _compare(tmp_path, {"shared_fate": {"model": "m1"}},
                   {"shared_fate": {"model": "m2"}}, {"must_differ": ["model", "workspace"]})
    assert run.returncode == 3
    result = json.loads(run.stdout)
    assert result["vector"]["workspace"]["status"] == "unknown"
    assert "workspace" in result["blocking_axes"]


def test_must_match_mismatch_is_not_independence(tmp_path):
    run = _compare(tmp_path, {"baseline": "a"}, {"baseline": "b"}, {"must_match": ["baseline"]})
    assert run.returncode == 3
    assert json.loads(run.stdout)["vector"]["baseline"]["status"] == "different"


def test_policy_overlap_and_unknown_axis_fail_closed(tmp_path):
    for policy in ({"must_differ": ["model"], "must_match": ["model"]},
                   {"must_differ": ["made_up"]}):
        run = _compare(tmp_path, {}, {}, policy)
        assert run.returncode == 2
        assert json.loads(run.stdout)["status"] == "INVALID"


def test_duplicate_json_keys_fail_closed(tmp_path):
    left = tmp_path / "left.json"
    left.write_text('{"model":"m1","model":"m2"}', encoding="utf-8")
    right = tmp_path / "right.json"
    right.write_text('{}', encoding="utf-8")
    policy = tmp_path / "policy.json"
    policy.write_text('{"must_differ":["model"]}', encoding="utf-8")
    run = subprocess.run([sys.executable, str(TOOL), "compare", "--left", str(left),
                          "--right", str(right), "--policy", str(policy)],
                         capture_output=True, text=True)
    assert run.returncode == 2
    assert json.loads(run.stdout)["status"] == "INVALID"
