from __future__ import annotations

import json
from pathlib import Path

import pytest

from flowsec.integrations.llm.prompting import (
    TrafficExpertPromptRenderer,
    fixture_traffic_expert_prompt,
)
from flowsec.production.runtime_adapter import (
    ProductionApplicationEvidenceTool,
    ProductionGraphContextTool,
    ProductionPacketExpansionTool,
    ProductionParquetEvidenceStore,
    ProductionSafeAdapter,
    ProductionSampleRequest,
    ProductionTemporalContextTool,
)
from flowsec.runtime.contracts import AgentAction, Capability, RuntimePhase, ToolRequest, ToolStatus


REAL_ROOT = Path("/root/autodl-tmp/processed/edge_split_revision_v2")
CLASS_SAMPLES = {
    "Normal": "fs1_7374c279f7cd884e1be73f9e08e65191a24c13d4",
    "DDoS_TCP": "fs1_8633c2a117f328502b7583b2c2f5ce539d2c0fef",
    "Port_Scanning": "fs1_3f80712341f43d2e64dd81bcaf54e83f557e2eb1",
    "SQL_injection": "fs1_9e240e26cfbd7fab3343911f89c38d87b22eb409",
    "Backdoor": "fs1_9a1bb97f1b972213939c20c746e810d128d5ec33",
    "MITM": "fs1_b8726027cf36304449de416c85246a0590c92182",
}
NO_PAST_SAMPLE = CLASS_SAMPLES["Backdoor"]
HAS_PAST_SAMPLE = "fs1_c30c9ed71429e81384477f652064609f9bf43ff5"


def _request(sample_id: str) -> ProductionSampleRequest:
    return ProductionSampleRequest(
        sample_id=sample_id,
        dataset="Edge-IIoTset",
        split="train",
        phase=RuntimePhase.TRAIN,
        preset="Near",
    )


@pytest.mark.skipif(not REAL_ROOT.is_dir(), reason="Git-external Production v2 assets unavailable")
def test_real_edge_v2_production_to_runtime_smoke_without_model_call() -> None:
    store = ProductionParquetEvidenceStore(REAL_ROOT)
    adapter = ProductionSafeAdapter(store)
    requests = [_request(sample_id) for sample_id in CLASS_SAMPLES.values()]
    requests.append(_request(HAS_PAST_SAMPLE))
    adapter.prefetch(requests)
    renderer = TrafficExpertPromptRenderer(fixture_traffic_expert_prompt())

    adapted_by_id = {}
    for expected_label, sample_id in CLASS_SAMPLES.items():
        adapted = adapter.adapt(_request(sample_id))
        adapted_by_id[sample_id] = adapted
        index = store.row(
            "sample_id_index",
            dataset="Edge-IIoTset",
            split="train",
            sample_id=sample_id,
            required=True,
        )
        assert index is not None
        assert index["fine_label"] == expected_label
        content = json.loads(adapted.runtime_input.initial_evidence[0].content)
        assert 1 <= len(content["packet_sequence"]) <= 8
        assert content["session_summary"]
        capabilities = {
            item.capability: item.available for item in adapted.runtime_input.capabilities
        }
        assert capabilities[Capability.TEMPORAL_CONTEXT] is True
        assert capabilities[Capability.GRAPH_CONTEXT] is True
        assert capabilities[Capability.APPLICATION_EVIDENCE] is False

        prompt = renderer.render(adapted.runtime_input.initial_evidence)
        visible = json.dumps([item.model_dump(mode="json") for item in prompt], sort_keys=True)
        prohibited_values = (
            sample_id,
            str(index["dataset"]),
            str(index["split"]),
            str(index["fine_label"]),
            str(index["coarse_label"]),
            str(index["source_sha256"]),
            str(index["capture_ref_hash"]),
        )
        assert all(value not in visible for value in prohibited_values)

    packet_sample = adapted_by_id[CLASS_SAMPLES["Backdoor"]]
    packet_tool = next(
        item for item in packet_sample.tools if isinstance(item, ProductionPacketExpansionTool)
    )
    packet_request = ToolRequest(
        action=AgentAction.EXPAND_PACKETS,
        parameters={"start_packet": 9, "end_packet": 16},
    )
    packet_result = packet_tool.execute(
        packet_request, packet_sample.runtime_input.initial_evidence
    )
    assert packet_result.status is ToolStatus.SUCCESS
    expanded = json.loads(packet_result.evidence[0].content)["packet_sequence"]
    assert [item["packet_index"] for item in expanded] == list(range(9, 17))
    assert not set(range(1, 9)).intersection(item["packet_index"] for item in expanded)

    temporal_results = {}
    for sample_id in (NO_PAST_SAMPLE, HAS_PAST_SAMPLE):
        adapted = adapted_by_id.get(sample_id) or adapter.adapt(_request(sample_id))
        row = store.row(
            "temporal_index",
            dataset="Edge-IIoTset",
            split="train",
            sample_id=sample_id,
            required=True,
        )
        assert row is not None
        if row["context_latest_timestamp"] is not None:
            assert float(row["context_latest_timestamp"]) < float(row["timestamp"])
        temporal_tool = next(
            item for item in adapted.tools if isinstance(item, ProductionTemporalContextTool)
        )
        result = temporal_tool.execute(
            ToolRequest(
                action=AgentAction.EXPAND_TEMPORAL_CONTEXT,
                parameters={"past_only": True, "window_seconds": 60.0},
            ),
            adapted.runtime_input.initial_evidence,
        )
        assert result.status is ToolStatus.SUCCESS
        visible = result.evidence[0].model_dump_json()
        assert str(row["source_identity_hash"]) not in visible
        assert str(row["destination_identity_hash"]) not in visible
        assert sample_id not in visible
        temporal_results[sample_id] = json.loads(result.evidence[0].content)
    assert temporal_results[NO_PAST_SAMPLE]["context_stats"]["prior_session_count"] == 0
    assert temporal_results[HAS_PAST_SAMPLE]["context_stats"]["prior_session_count"] > 0

    graph_tool = next(
        item for item in packet_sample.tools if isinstance(item, ProductionGraphContextTool)
    )
    graph_result = graph_tool.execute(
        ToolRequest(action=AgentAction.EXPAND_GRAPH_CONTEXT, parameters={"scope": "local"}),
        packet_sample.runtime_input.initial_evidence,
    )
    assert graph_result.status is ToolStatus.SUCCESS
    graph = json.loads(graph_result.evidence[0].content)
    assert graph["node_roles"] == ["current_source", "target_cluster"]
    assert "identity_hash" not in graph_result.evidence[0].content

    application_tool = next(
        item for item in packet_sample.tools if isinstance(item, ProductionApplicationEvidenceTool)
    )
    application = application_tool.execute(
        ToolRequest(action=AgentAction.REQUEST_APPLICATION_EVIDENCE),
        packet_sample.runtime_input.initial_evidence,
    )
    assert application.status is ToolStatus.UNAVAILABLE
    assert application.evidence == ()
