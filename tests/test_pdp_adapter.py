from tools.pdp_adapter import prepare, record


def test_external_decision_is_recorded_without_local_claim():
    req = prepare("policy/v1", {"principal": "agent", "action": "read"})
    out = record(req, {"decision": "allow"}, "pdp-1", "sha256:policy")
    assert out["response"]["decision"] == "allow"
    assert out["orgforge_decision"] is None
    assert out["dr_claim"] is None
