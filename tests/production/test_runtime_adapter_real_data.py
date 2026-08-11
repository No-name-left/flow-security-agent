from __future__ import annotations

import json
import os
from collections.abc import Mapping
from pathlib import Path

import pytest

from flowsec.integrations.llm.prompting import (
    TrafficExpertPromptRenderer,
    fixture_traffic_expert_prompt,
)
from flowsec.production.runtime_adapter import (
    PRODUCTION_ASSET_VERSION,
    ProductionApplicationEvidenceTool,
    ProductionGraphContextTool,
    ProductionPacketExpansionTool,
    ProductionParquetEvidenceStore,
    ProductionSafeAdapter,
    ProductionSampleRequest,
    ProductionTemporalContextTool,
)
from flowsec.runtime.contracts import AgentAction, Capability, RuntimePhase, ToolRequest, ToolStatus


ARTIFACT_ROOT_ENV = "ARTIFACT_ROOT"
_REQUIRED_ASSET = Path("manifests/split_revision_completion.json")
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


def _configured_production_root(
    environ: Mapping[str, str] | None = None,
) -> Path | None:
    environment = os.environ if environ is None else environ
    artifact_root = environment.get(ARTIFACT_ROOT_ENV)
    if not artifact_root:
        return None
    return Path(artifact_root).expanduser() / PRODUCTION_ASSET_VERSION


def _production_assets_available(root: Path | None) -> bool:
    if root is None:
        return False
    try:
        return root.is_dir() and (root / _REQUIRED_ASSET).is_file()
    except OSError:
        return False


@pytest.fixture(scope="module")
def real_root() -> Path:
    root = _configured_production_root()
    if not _production_assets_available(root):
        pytest.skip(
            f"Git-external Production v2 assets unavailable; configure {ARTIFACT_ROOT_ENV}"
        )
    assert root is not None
    return root


def _request(sample_id: str) -> ProductionSampleRequest:
    return ProductionSampleRequest(
        sample_id=sample_id,
        dataset="Edge-IIoTset",
        split="train",
        phase=RuntimePhase.TRAIN,
        preset="Near",
    )


def _assert_value_fidelity(actual: object, expected: object) -> None:
    if isinstance(expected, float):
        assert isinstance(actual, (int, float)) and not isinstance(actual, bool)
        assert float(actual) == pytest.approx(expected, rel=0.0, abs=1e-12)
    elif isinstance(expected, dict):
        assert isinstance(actual, dict)
        assert actual.keys() == expected.keys()
        for key in expected:
            _assert_value_fidelity(actual[key], expected[key])
    elif isinstance(expected, list):
        assert isinstance(actual, list)
        assert len(actual) == len(expected)
        for actual_item, expected_item in zip(actual, expected, strict=True):
            _assert_value_fidelity(actual_item, expected_item)
    else:
        assert actual == expected


def test_configured_production_root_is_available_when_required_assets_exist(
    tmp_path: Path,
) -> None:
    root = tmp_path / PRODUCTION_ASSET_VERSION
    required_asset = root / _REQUIRED_ASSET
    required_asset.parent.mkdir(parents=True)
    required_asset.touch()

    configured = _configured_production_root({ARTIFACT_ROOT_ENV: str(tmp_path)})

    assert configured == root
    assert _production_assets_available(configured) is True


def test_production_assets_are_unavailable_when_unconfigured_or_missing(
    tmp_path: Path,
) -> None:
    assert _configured_production_root({}) is None
    missing = _configured_production_root({ARTIFACT_ROOT_ENV: str(tmp_path)})
    assert _production_assets_available(missing) is False


def test_production_assets_are_unavailable_on_permission_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def raise_permission_error(_path: Path) -> bool:
        raise PermissionError(13, "permission denied")

    monkeypatch.setattr(Path, "is_dir", raise_permission_error)

    assert _production_assets_available(Path("/inaccessible")) is False


def test_real_edge_v2_production_to_runtime_smoke_without_model_call(
    real_root: Path,
) -> None:
    store = ProductionParquetEvidenceStore(real_root)
    adapter = ProductionSafeAdapter(store)
    requests = [_request(sample_id) for sample_id in CLASS_SAMPLES.values()]
    requests.append(_request(HAS_PAST_SAMPLE))
    adapter.prefetch(requests)
    renderer = TrafficExpertPromptRenderer(fixture_traffic_expert_prompt())

    adapted_by_id = {}
    observed_l4_protocols = set()
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
        source_row = store.row(
            "initial_model_views",
            dataset="Edge-IIoTset",
            split="train",
            sample_id=sample_id,
            required=True,
        )
        assert source_row is not None
        source = json.loads(source_row["view_json"])
        content = json.loads(adapted.runtime_input.initial_evidence[0].content)
        _assert_value_fidelity(content["packet_sequence"], source["packet_sequence"])
        _assert_value_fidelity(content["session_summary"], source["session_summary"])
        assert content["missing_fields"] == sorted(source["missing_fields"])
        total_packets = (
            source["session_summary"]["initiator_packets"]
            + source["session_summary"]["responder_packets"]
        )
        assert len(content["packet_sequence"]) == min(total_packets, 8)
        observed_l4_protocols.update(
            packet["l4_protocol"] for packet in content["packet_sequence"]
        )
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

    assert observed_l4_protocols == {"TCP", "UDP"}

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
    packet_source_row = store.row(
        "expandable_packet_store",
        dataset="Edge-IIoTset",
        split="train",
        sample_id=CLASS_SAMPLES["Backdoor"],
        required=True,
    )
    assert packet_source_row is not None
    source_expanded = json.loads(packet_source_row["packets_9_16_json"])
    _assert_value_fidelity(
        [
            {key: value for key, value in packet.items() if key != "packet_index"}
            for packet in expanded
        ],
        source_expanded,
    )

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
        _assert_value_fidelity(
            temporal_results[sample_id]["context_stats"],
            json.loads(row["context_stats_json"]),
        )
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
    relation_row = store.row(
        "relation_index",
        dataset="Edge-IIoTset",
        split="train",
        sample_id=CLASS_SAMPLES["Backdoor"],
        required=True,
    )
    assert relation_row is not None
    assert graph["repeated_relation"] is bool(relation_row["previous_pair_sample_ref"])
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
