from __future__ import annotations

import json
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest
from pydantic import ValidationError

from flowsec.integrations.llm.prompting import (
    SupervisorPromptRenderer,
    ToolSpecification,
    TrafficExpertPromptRenderer,
    fixture_supervisor_prompt,
    fixture_traffic_expert_prompt,
)
from flowsec.production.runtime_adapter import (
    ADAPTER_VERSION,
    EVIDENCE_SCHEMA_VERSION,
    PAPER_SPLIT_VERSION,
    ProductionApplicationEvidenceTool,
    ProductionGraphContextTool,
    ProductionPacketExpansionTool,
    ProductionParquetEvidenceStore,
    ProductionRuntimeAccessError,
    ProductionRuntimeAdapterError,
    ProductionSafeAdapter,
    ProductionSampleRequest,
    ProductionTemporalContextTool,
)
from flowsec.production.schema import CANONICAL_SCHEMA_VERSION, INITIAL_VIEW_VERSION, canonical_json
from flowsec.production.storage import ProductionCatalog
from flowsec.runtime.backends import (
    MockSupervisorBackend,
    MockTrafficExpertBackend,
    MockUnknownScorer,
)
from flowsec.runtime.contracts import (
    AgentAction,
    BudgetLimits,
    Capability,
    EvidenceSufficiency,
    GapDomain,
    GapType,
    MissingEvidence,
    PredictionCandidate,
    RuntimePhase,
    SupervisorDecision,
    ToolRequest,
    ToolStatus,
    TrafficExpertResult,
    UnknownDecision,
    UnknownState,
)
from flowsec.runtime.orchestrator import RuntimeOrchestrator


EDGE_SAMPLE = "fs1_" + "1" * 40
EDGE_FINAL_SAMPLE = "fs1_" + "2" * 40
IOT_SAMPLE = "fs1_" + "3" * 40
SOURCE_HASH = "a" * 64
CAPTURE_HASH = "b" * 64
IDENTITY_HASH = "c" * 64


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_parquet(root: Path, asset: str, dataset: str, split: str, rows: list[dict]) -> None:
    path = root / asset / f"dataset={dataset}" / f"split={split}"
    path.mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.Table.from_pylist(rows), path / "part-00000.parquet")


def _packet(index: int) -> dict[str, object]:
    return {
        "direction": "initiator_to_responder" if index % 2 else "responder_to_initiator",
        "packet_length": 60 + index,
        "relative_iat": 0.0 if index == 1 else index / 1000,
        "l3_protocol": "IPv4",
        "l4_protocol": "TCP",
        "tcp_flags": 2 if index == 1 else 16,
    }


def _summary() -> dict[str, object]:
    return {
        "duration": 1.25,
        "initiator_packets": 10,
        "responder_packets": 6,
        "initiator_bytes": 1000,
        "responder_bytes": 600,
        "packet_length_stats": {"min": 60.0, "max": 100.0, "mean": 80.0, "std": 5.0},
        "iat_stats": {"min": 0.0, "max": 0.5, "mean": 0.1, "std": 0.05},
        "handshake_state": "ESTABLISHED_OPEN",
    }


def _index_row(
    sample_id: str,
    dataset: str,
    split: str,
    fine: str,
    coarse: str,
) -> dict[str, object]:
    return {
        "schema_version": CANONICAL_SCHEMA_VERSION,
        "sample_id": sample_id,
        "dataset": dataset,
        "split": split,
        "fine_label": fine,
        "coarse_label": coarse,
        "capture_ref_hash": CAPTURE_HASH,
        "source_sha256": SOURCE_HASH,
        "evidence_signature": "d" * 64,
        "exact_signature": "e" * 64,
        "reverse_signature": "f" * 64,
        "near_signature": "0" * 64,
    }


def _initial_row(
    sample_id: str,
    split: str,
    label_schema_id: str,
    *,
    extra_view: dict[str, object] | None = None,
) -> dict[str, object]:
    view = {
        "label_schema_id": label_schema_id,
        "packet_sequence": [_packet(index) for index in range(1, 9)],
        "session_summary": _summary(),
        "capabilities": [
            "packet_expand_9_16",
            "relation_context",
            "service_diagnostic",
            "temporal_context",
        ],
        "missing_fields": ["application_evidence", "sanitized_payload"],
    }
    view.update(extra_view or {})
    return {
        "schema_version": CANONICAL_SCHEMA_VERSION,
        "view_version": INITIAL_VIEW_VERSION,
        "sample_id": sample_id,
        "split": split,
        "view_json": canonical_json(view),
    }


def _expanded_row(sample_id: str, split: str) -> dict[str, object]:
    return {
        "schema_version": CANONICAL_SCHEMA_VERSION,
        "sample_id": sample_id,
        "split": split,
        "packets_9_16_json": canonical_json([_packet(index) for index in range(9, 17)]),
        "rag_retrieval_key": "1" * 64,
    }


def _temporal_row(
    sample_id: str,
    split: str,
    *,
    timestamp: float = 100.0,
    latest: float | None = 99.0,
    prior_count: int = 4,
) -> dict[str, object]:
    return {
        "schema_version": CANONICAL_SCHEMA_VERSION,
        "sample_id": sample_id,
        "split": split,
        "timestamp": timestamp,
        "context_latest_timestamp": latest,
        "source_identity_hash": IDENTITY_HASH,
        "destination_identity_hash": "d" * 64,
        "communication_pair_hash": "e" * 64,
        "context_stats_json": canonical_json(
            {
                "window_seconds": 60.0,
                "prior_session_count": prior_count,
                "unique_destination_count": 3,
                "unique_destination_service_category_count": 2,
                "same_destination_distinct_source_count": 1,
                "repeated_pair_count": 2,
                "incomplete_handshake_ratio": 0.25,
                "inter_session_gap": None if not prior_count else 1.0,
                "prior_packets": 20,
                "prior_bytes": 2000,
            }
        ),
    }


def _relation_row(sample_id: str, split: str) -> dict[str, object]:
    return {
        "schema_version": CANONICAL_SCHEMA_VERSION,
        "sample_id": sample_id,
        "split": split,
        "source_identity_hash": IDENTITY_HASH,
        "destination_identity_hash": "d" * 64,
        "communication_pair_hash": "e" * 64,
        "previous_pair_sample_ref": "fs1_" + "9" * 40,
        "model_node_roles": "CURRENT_SOURCE,TARGET_CLUSTER",
    }


def _edge_manifest() -> dict[str, object]:
    def asset(role: str, ku_role: str, preset: str, split: str, labels: list[str]) -> dict:
        return {
            "role": role,
            "ku_role": ku_role,
            "preset": preset,
            "split": split,
            "sample_ids": {
                "asset": "sample_id_index",
                "dataset": "Edge-IIoTset",
                "filter": {"split": split, "fine_label_in": labels},
            },
        }

    return {
        "assets": [
            asset("sft_train", "K_known", "Near", "train_secret", ["Backdoor"]),
            asset("sft_validation", "K_known", "Near", "validation", ["Backdoor"]),
            asset("closed_test", "K_known", "Near", "test", ["Backdoor"]),
            asset("unknown_development", "U_dev", "Near", "validation", ["DDoS_ICMP"]),
            asset("final_unknown", "U_final", "Far", "test", ["Password"]),
        ]
    }


def _iot_manifest() -> dict[str, object]:
    return {
        "assets": [
            {
                "role": "sft_train",
                "ku_role": "K_known",
                "split": "train",
                "sample_ids": {
                    "asset": "sample_id_index",
                    "dataset": "IoT-23",
                    "filter": {"split": "train", "coarse_label_in": ["Benign"]},
                },
            }
        ]
    }


def production_root(tmp_path: Path, *, initial_extra: dict[str, object] | None = None) -> Path:
    root = tmp_path / "production"
    manifests = root / "manifests"
    _write_json(
        manifests / "canonical_schema_v1.json",
        {"schema_version": CANONICAL_SCHEMA_VERSION},
    )
    _write_json(
        manifests / "split_revision_completion.json",
        {
            "SPLIT_REVISION_STATUS": "PASS_WITH_LIMITATIONS",
            "U_FINAL_ISOLATION": "PASS",
            "LABEL_PROVENANCE_FINAL_GATE": "PASS",
        },
    )
    _write_json(manifests / "edge_split_manifest.json", {"policy": PAPER_SPLIT_VERSION})
    _write_json(manifests / "source_checksum_manifest.json", {"config_hash": "4" * 64})
    _write_json(
        manifests / "production_statistics.json",
        {"asset_metadata": {"application_evidence": {"rows": 0}}},
    )
    _write_json(
        manifests / "leakage_audit.json",
        {
            "LEAKAGE_AUDIT_OK": True,
            "items": [
                {"name": "future context", "status": "PASS"},
                {"name": "cross-split temporal context", "status": "PASS"},
                {"name": "U_final development leakage", "status": "PASS"},
            ],
        },
    )
    _write_json(manifests / "training_asset_manifest_edge.json", _edge_manifest())
    _write_json(manifests / "training_asset_manifest_iot23.json", _iot_manifest())
    _write_json(manifests / "edge_label_schema.json", {"id": "edge_native_v1"})
    _write_json(manifests / "iot23_label_schema.json", {"id": "iot23_native_v1"})
    _write_json(root / "application_evidence" / "_EMPTY.json", {"rows": 0})

    edge_split = "train_secret"
    _write_parquet(
        root,
        "sample_id_index",
        "Edge-IIoTset",
        edge_split,
        [_index_row(EDGE_SAMPLE, "Edge-IIoTset", edge_split, "Backdoor", "Malware")],
    )
    _write_parquet(
        root,
        "initial_model_views",
        "Edge-IIoTset",
        edge_split,
        [_initial_row(EDGE_SAMPLE, edge_split, "edge_native_v1", extra_view=initial_extra)],
    )
    _write_parquet(
        root,
        "expandable_packet_store",
        "Edge-IIoTset",
        edge_split,
        [_expanded_row(EDGE_SAMPLE, edge_split)],
    )
    _write_parquet(
        root,
        "temporal_index",
        "Edge-IIoTset",
        edge_split,
        [_temporal_row(EDGE_SAMPLE, edge_split)],
    )
    _write_parquet(
        root,
        "relation_index",
        "Edge-IIoTset",
        edge_split,
        [_relation_row(EDGE_SAMPLE, edge_split)],
    )

    _write_parquet(
        root,
        "sample_id_index",
        "Edge-IIoTset",
        "test",
        [_index_row(EDGE_FINAL_SAMPLE, "Edge-IIoTset", "test", "Password", "CredentialAccess")],
    )
    _write_parquet(
        root,
        "initial_model_views",
        "Edge-IIoTset",
        "test",
        [_initial_row(EDGE_FINAL_SAMPLE, "test", "edge_native_v1")],
    )
    _write_parquet(
        root,
        "expandable_packet_store",
        "Edge-IIoTset",
        "test",
        [_expanded_row(EDGE_FINAL_SAMPLE, "test")],
    )
    _write_parquet(
        root,
        "temporal_index",
        "Edge-IIoTset",
        "test",
        [_temporal_row(EDGE_FINAL_SAMPLE, "test")],
    )
    _write_parquet(
        root,
        "relation_index",
        "Edge-IIoTset",
        "test",
        [_relation_row(EDGE_FINAL_SAMPLE, "test")],
    )

    _write_parquet(
        root,
        "sample_id_index",
        "IoT-23",
        "train",
        [_index_row(IOT_SAMPLE, "IoT-23", "train", "Benign", "Benign")],
    )
    _write_parquet(
        root,
        "initial_model_views",
        "IoT-23",
        "train",
        [_initial_row(IOT_SAMPLE, "train", "iot23_native_v1")],
    )
    _write_parquet(
        root,
        "expandable_packet_store",
        "IoT-23",
        "train",
        [_expanded_row(IOT_SAMPLE, "train")],
    )
    _write_parquet(
        root,
        "temporal_index",
        "IoT-23",
        "train",
        [_temporal_row(IOT_SAMPLE, "train")],
    )
    _write_parquet(
        root,
        "relation_index",
        "IoT-23",
        "train",
        [_relation_row(IOT_SAMPLE, "train")],
    )
    return root


def edge_request(**updates: object) -> ProductionSampleRequest:
    values: dict[str, object] = {
        "sample_id": EDGE_SAMPLE,
        "dataset": "Edge-IIoTset",
        "split": "train_secret",
        "phase": RuntimePhase.TRAIN,
        "preset": "Near",
    }
    values.update(updates)
    return ProductionSampleRequest.model_validate(values)


def test_initial_evidence_is_allow_listed_typed_and_versioned(tmp_path: Path) -> None:
    adapted = ProductionSafeAdapter(
        ProductionParquetEvidenceStore(production_root(tmp_path))
    ).adapt(edge_request())
    evidence = adapted.runtime_input.initial_evidence[0]
    content = json.loads(evidence.content)
    assert len(content["packet_sequence"]) == 8
    assert content["session_summary"] == _summary()
    assert content["evidence_schema_version"] == EVIDENCE_SCHEMA_VERSION
    assert "label_schema_id" not in content
    assert "capabilities" not in content
    assert evidence.evidence_id.startswith("ev_")
    assert EDGE_SAMPLE not in evidence.model_dump_json()
    assert adapted.backend_provenance.adapter_version == ADAPTER_VERSION
    assert PAPER_SPLIT_VERSION == adapted.backend_provenance.paper_split_version


def test_sensitive_backend_values_never_reach_evidence_or_prompt(tmp_path: Path) -> None:
    adapter = ProductionSafeAdapter(ProductionParquetEvidenceStore(production_root(tmp_path)))
    adapted = adapter.adapt(edge_request())
    renderer = TrafficExpertPromptRenderer(fixture_traffic_expert_prompt())
    prompt = renderer.render(adapted.runtime_input.initial_evidence)
    visible = json.dumps(
        {
            "evidence": [
                item.model_dump(mode="json")
                for item in adapted.runtime_input.initial_evidence
            ],
            "prompt": [item.model_dump(mode="json") for item in prompt],
        },
        sort_keys=True,
    )
    prohibited_values = (
        EDGE_SAMPLE,
        "Edge-IIoTset",
        "train_secret",
        "Backdoor",
        "Malware",
        SOURCE_HASH,
        CAPTURE_HASH,
        "192.0.2.123",
        "2031-01-01T01:02:03Z",
        "/secret/source/capture.pcap",
        "U_final",
    )
    assert all(value not in visible for value in prohibited_values)

    raw_record = {
        "sample_id": EDGE_SAMPLE,
        "dataset": "Edge-IIoTset",
        "fine_label": "Backdoor",
        "coarse_label": "Malware",
        "split": "train_secret",
        "ku_role": "K_known",
        "capture_id": "capture-secret",
        "raw_ip": "192.0.2.123",
        "absolute_timestamp": "2031-01-01T01:02:03Z",
        "source_path": "/secret/source/capture.pcap",
    }
    with pytest.raises((TypeError, ValidationError)):
        adapter.adapt(raw_record)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "mutation",
    (
        "missing_packet_sequence",
        "missing_summary_duration",
        "missing_packet_relative_iat",
        "null_packet_length",
    ),
)
def test_required_initial_evidence_fields_fail_closed(
    tmp_path: Path, mutation: str
) -> None:
    root = production_root(tmp_path)
    row = _initial_row(EDGE_SAMPLE, "train_secret", "edge_native_v1")
    view = json.loads(row["view_json"])
    if mutation == "missing_packet_sequence":
        del view["packet_sequence"]
    elif mutation == "missing_summary_duration":
        del view["session_summary"]["duration"]
    elif mutation == "missing_packet_relative_iat":
        del view["packet_sequence"][0]["relative_iat"]
    else:
        view["packet_sequence"][0]["packet_length"] = None
    row["view_json"] = canonical_json(view)
    _write_parquet(
        root,
        "initial_model_views",
        "Edge-IIoTset",
        "train_secret",
        [row],
    )
    adapter = ProductionSafeAdapter(ProductionParquetEvidenceStore(root))
    with pytest.raises(ProductionRuntimeAdapterError):
        adapter.adapt(edge_request())


def test_unallowlisted_initial_field_is_rejected_by_default(tmp_path: Path) -> None:
    root = production_root(tmp_path, initial_extra={"raw_ip": "192.0.2.123"})
    adapter = ProductionSafeAdapter(ProductionParquetEvidenceStore(root))
    with pytest.raises(ProductionRuntimeAdapterError, match="schema mismatch"):
        adapter.adapt(edge_request())


def test_packet_expansion_is_limited_to_9_16_and_deduplicated(tmp_path: Path) -> None:
    adapted = ProductionSafeAdapter(
        ProductionParquetEvidenceStore(production_root(tmp_path))
    ).adapt(edge_request())
    tool = next(item for item in adapted.tools if isinstance(item, ProductionPacketExpansionTool))
    request = ToolRequest(
        action=AgentAction.EXPAND_PACKETS,
        parameters={"start_packet": 9, "end_packet": 16},
    )
    result = tool.execute(request, adapted.runtime_input.initial_evidence)
    assert result.status is ToolStatus.SUCCESS
    content = json.loads(result.evidence[0].content)
    assert [item["packet_index"] for item in content["packet_sequence"]] == list(range(9, 17))
    assert tool.execute(
        request, (*adapted.runtime_input.initial_evidence, *result.evidence)
    ).status is ToolStatus.FAILURE
    illegal = ToolRequest(
        action=AgentAction.EXPAND_PACKETS,
        parameters={"start_packet": 9, "end_packet": 17},
    )
    assert (
        tool.execute(illegal, adapted.runtime_input.initial_evidence).status
        is ToolStatus.FAILURE
    )


def test_production_adapter_and_bound_tool_run_through_runtime(tmp_path: Path) -> None:
    adapted = ProductionSafeAdapter(
        ProductionParquetEvidenceStore(production_root(tmp_path))
    ).adapt(edge_request())
    packet_request = ToolRequest(
        action=AgentAction.EXPAND_PACKETS,
        parameters={"start_packet": 9, "end_packet": 16},
    )
    traffic_expert = MockTrafficExpertBackend(
        [
            TrafficExpertResult(
                evidence_sufficiency=EvidenceSufficiency.INSUFFICIENT,
                missing_evidence=(
                    MissingEvidence(
                        description="need the next packet segment",
                        gap_type=GapType.PACKET,
                        domain=GapDomain.OBSERVATIONAL,
                    ),
                ),
            ),
            TrafficExpertResult(
                fine_candidates=(PredictionCandidate(label="Backdoor", score=0.8),),
                coarse_candidates=(PredictionCandidate(label="Malware", score=0.9),),
                evidence_sufficiency=EvidenceSufficiency.SUFFICIENT,
            ),
        ]
    )
    supervisor = MockSupervisorBackend(
        [
            SupervisorDecision(
                action=AgentAction.EXPAND_PACKETS,
                request=packet_request,
                short_reason="packet interaction is incomplete",
            ),
            SupervisorDecision(
                action=AgentAction.ACCEPT_FINE,
                short_reason="the expanded packet evidence is sufficient",
            ),
        ]
    )
    runtime = RuntimeOrchestrator(
        traffic_expert=traffic_expert,
        unknown_scorer=MockUnknownScorer(
            [
                UnknownDecision(state=UnknownState.KNOWN_LIKELY),
                UnknownDecision(state=UnknownState.KNOWN_LIKELY),
            ]
        ),
        supervisor=supervisor,
        budget_limits=BudgetLimits(
            max_rounds=1,
            max_traffic_expert_calls=2,
            max_supervisor_calls=2,
            max_tool_calls=1,
            max_rag_calls=0,
            max_abstract_tokens=0,
            max_abstract_cost=0,
            max_abstract_latency=0,
        ),
        tools=adapted.tools,
        allowed_request_parameters={
            AgentAction.EXPAND_PACKETS: (packet_request.parameters,)
        },
        memory_retrieval_limit=0,
    )
    result = runtime.run(adapted.runtime_input)
    assert result.final_decision.label == "Backdoor"
    assert result.final_state is not None
    assert len(result.final_state.evidence) == 2
    assert result.final_state.evidence[1].gap_type is GapType.PACKET
    assert len(traffic_expert.calls) == 2
    supervisor_prompt = SupervisorPromptRenderer(
        fixture_supervisor_prompt(),
        ToolSpecification(allowed_actions=(AgentAction.EXPAND_PACKETS,)),
    ).render(supervisor.states[0])
    supervisor_visible = json.dumps(
        [item.model_dump(mode="json") for item in supervisor_prompt], sort_keys=True
    )
    assert all(
        value not in supervisor_visible
        for value in (
            EDGE_SAMPLE,
            "Edge-IIoTset",
            "train_secret",
            "K_known",
            "Backdoor",
            "Malware",
            SOURCE_HASH,
            CAPTURE_HASH,
        )
    )


def test_temporal_and_graph_tools_emit_only_real_anonymous_summaries(tmp_path: Path) -> None:
    adapted = ProductionSafeAdapter(
        ProductionParquetEvidenceStore(production_root(tmp_path))
    ).adapt(edge_request())
    temporal = next(
        item for item in adapted.tools if isinstance(item, ProductionTemporalContextTool)
    )
    temporal_request = ToolRequest(
        action=AgentAction.EXPAND_TEMPORAL_CONTEXT,
        parameters={"past_only": True, "window_seconds": 60.0},
    )
    temporal_result = temporal.execute(temporal_request, adapted.runtime_input.initial_evidence)
    assert temporal_result.status is ToolStatus.SUCCESS
    temporal_visible = temporal_result.evidence[0].model_dump_json()
    assert '"past_only":true' in temporal_visible
    assert IDENTITY_HASH not in temporal_visible
    assert "100.0" not in temporal_visible

    graph = next(item for item in adapted.tools if isinstance(item, ProductionGraphContextTool))
    graph_request = ToolRequest(
        action=AgentAction.EXPAND_GRAPH_CONTEXT,
        parameters={"scope": "local"},
    )
    graph_result = graph.execute(graph_request, adapted.runtime_input.initial_evidence)
    graph_content = json.loads(graph_result.evidence[0].content)
    assert graph_content["node_roles"] == ["current_source", "target_cluster"]
    assert graph_content["repeated_relation"] is True
    assert IDENTITY_HASH not in graph_result.evidence[0].model_dump_json()
    assert "fs1_" not in graph_result.evidence[0].model_dump_json()


def test_future_temporal_context_is_rejected_during_admission(tmp_path: Path) -> None:
    root = production_root(tmp_path)
    _write_parquet(
        root,
        "temporal_index",
        "Edge-IIoTset",
        "train_secret",
        [_temporal_row(EDGE_SAMPLE, "train_secret", timestamp=100.0, latest=100.0)],
    )
    adapter = ProductionSafeAdapter(ProductionParquetEvidenceStore(root))
    with pytest.raises(ProductionRuntimeAdapterError, match="strictly past-only"):
        adapter.adapt(edge_request())


def test_capability_mapping_is_truthful_and_application_is_unavailable(tmp_path: Path) -> None:
    adapted = ProductionSafeAdapter(
        ProductionParquetEvidenceStore(production_root(tmp_path))
    ).adapt(edge_request())
    status = {item.capability: item for item in adapted.runtime_input.capabilities}
    assert status[Capability.PACKET_EXPANSION].available is True
    assert status[Capability.TEMPORAL_CONTEXT].available is True
    assert status[Capability.GRAPH_CONTEXT].available is True
    assert status[Capability.APPLICATION_EVIDENCE].available is False
    assert status[Capability.KNOWLEDGE_RETRIEVAL].available is False
    application = next(
        item for item in adapted.tools if isinstance(item, ProductionApplicationEvidenceTool)
    )
    result = application.execute(
        ToolRequest(action=AgentAction.REQUEST_APPLICATION_EVIDENCE),
        adapted.runtime_input.initial_evidence,
    )
    assert result.status is ToolStatus.UNAVAILABLE
    assert result.error == "CAPABILITY_UNAVAILABLE"


def test_u_final_requires_outer_authorization_and_cannot_enter_other_phases(tmp_path: Path) -> None:
    adapter = ProductionSafeAdapter(ProductionParquetEvidenceStore(production_root(tmp_path)))
    values = {
        "sample_id": EDGE_FINAL_SAMPLE,
        "dataset": "Edge-IIoTset",
        "split": "test",
        "preset": "Far",
    }
    with pytest.raises(ProductionRuntimeAccessError):
        ProductionSampleRequest.model_validate({**values, "phase": RuntimePhase.U_FINAL})
    with pytest.raises(ProductionRuntimeAccessError):
        adapter.adapt(
            ProductionSampleRequest.model_validate({**values, "phase": RuntimePhase.TRAIN})
        )
    with pytest.raises(ProductionRuntimeAccessError):
        adapter.adapt(
            ProductionSampleRequest.model_validate({**values, "phase": RuntimePhase.TEST})
        )
    allowed = adapter.adapt(
        ProductionSampleRequest.model_validate(
            {
                **values,
                "phase": RuntimePhase.U_FINAL,
                "final_evaluation_authorized": True,
            }
        )
    )
    assert allowed.runtime_input.phase is RuntimePhase.U_FINAL
    assert allowed.backend_provenance.ku_role == "U_final"
    assert "U_final" not in allowed.runtime_input.initial_evidence[0].model_dump_json()


def test_same_version_and_sample_are_deterministic(tmp_path: Path) -> None:
    adapter = ProductionSafeAdapter(ProductionParquetEvidenceStore(production_root(tmp_path)))
    first = adapter.adapt(edge_request())
    second = adapter.adapt(edge_request())
    assert first.runtime_input == second.runtime_input
    assert first.backend_provenance == second.backend_provenance
    assert first.runtime_input.model_dump_json() == second.runtime_input.model_dump_json()


def test_iot_production_contract_remains_compatible(tmp_path: Path) -> None:
    adapter = ProductionSafeAdapter(ProductionParquetEvidenceStore(production_root(tmp_path)))
    adapted = adapter.adapt(
        ProductionSampleRequest(
            sample_id=IOT_SAMPLE,
            dataset="IoT-23",
            split="train",
            phase=RuntimePhase.TRAIN,
        )
    )
    assert adapted.runtime_input.phase is RuntimePhase.TRAIN
    assert len(adapted.runtime_input.initial_evidence) == 1
    assert adapted.backend_provenance.manifest_role == "sft_train"


def test_raw_catalog_and_raw_row_cannot_enter_prompt_renderer(tmp_path: Path) -> None:
    renderer = TrafficExpertPromptRenderer(fixture_traffic_expert_prompt())
    with pytest.raises(TypeError, match="typed EvidenceItem"):
        renderer.render(({"fine_label": "Backdoor"},))  # type: ignore[arg-type]
    catalog = ProductionCatalog(tmp_path / "catalog.sqlite")
    try:
        with pytest.raises(TypeError, match="typed EvidenceItem"):
            renderer.render((catalog,))  # type: ignore[arg-type]
    finally:
        catalog.close()
