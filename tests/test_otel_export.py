import json
from pathlib import Path

from tools.otel_export import export


def test_deterministic_correlation_and_missing_trace(tmp_path: Path):
    events = [
        {"seq": 1, "id": "e1", "ts": "2026-01-01T00:00:00Z", "class": "phase_admitted",
         "hash": "h1", "payload": {"issue": 4, "phase": "test", "evidence_digest": "sha256:x"}},
        {"seq": 2, "id": "e2", "ts": "2026-01-01T00:01:00Z", "class": "cycle_completed",
         "hash": "h2", "payload": {"trace_id": "t1", "span_id": "s1", "parent_span_id": "p1"}},
    ]
    (tmp_path / "ledger.jsonl").write_text("\n".join(json.dumps(x) for x in events) + "\n")
    assert export(str(tmp_path)) == export(str(tmp_path))
    spans = export(str(tmp_path))["scopeSpans"][0]["spans"]
    assert spans[0]["missingCorrelation"] is True
    assert spans[1]["traceId"] == "t1"
    assert export(str(tmp_path))["resource"]["attributes"]["orgforge.semantic_disposition"] == "observation_only"

