"""Local contract checks that do not require a delegation-resilience checkout."""

from tools.assurance_graph_export import _build_graph


def test_exporter_never_invents_support_edges():
    graph = _build_graph(
        report_raw=b'{"report":true}',
        constitution_raw=b"constitution: test\n",
        scenario_raw=b"scenario: test\n",
        observed_at="2026-08-03T00:00:00Z",
    )
    assert not any(edge["type"] == "supports" for edge in graph["edges"])
    claims = [node for node in graph["nodes"] if node["type"] == "claim"]
    assert claims and all(node["attributes"]["status"] == "NOT_DEMONSTRATED" for node in claims)
