from __future__ import annotations

from copy import deepcopy
import json

import pytest
from pydantic import ValidationError

from flowsec.integrations.llm.contracts import RawLLMResponse, RawUsage
from flowsec.training.contracts import (
    EVIDENCE_STATE_SCHEMA_V2,
    EvidenceDomain,
    EvidenceEnvelope,
    EvidenceFamilyV2,
    EvidenceSnapshot,
    EvidenceStateV2,
    EvidenceTrustV1,
    GapDomainV2,
    RecoverabilityV2,
    StageType,
    TeacherAnnotationV2,
)
from flowsec.training.prompts import (
    teacher_prompt_v3,
    teacher_v2_prompt_v1,
    teacher_v2_prompt_v2,
)
from flowsec.training.role_requests import (
    build_teacher_v2_request,
    evidence_families_from_capabilities,
)
from flowsec.training.teacher import (
    DeepSeekFlashSettings,
    DeepSeekTeacherV2Client,
    TEACHER_V2_CACHE_NAMESPACE,
    annotate_snapshots_v2,
    select_teacher_v2_pilot,
    validate_teacher_v2_annotation,
)
from flowsec.training import teacher as teacher_module


SAMPLE_ID = "fs1_" + "1" * 40
EVIDENCE_ID = "ev_basic_v2_12345678"


def _snapshot(
    *,
    index: int = 1,
    label: str = "Password",
    primary: bool = True,
    capabilities: tuple[str, ...] = ("temporal_context", "application_evidence"),
) -> EvidenceSnapshot:
    return EvidenceSnapshot(
        sample_id=SAMPLE_ID,
        evidence_state_id="state_" + f"{index:024x}",
        fine_label=label,
        coarse_label="Attack",
        split="train",
        ku_role="K_known",
        stage_type=StageType.INITIAL if primary else StageType.CONTROLLED_MASK,
        classification_supervision_valid=primary,
        available_capabilities=capabilities,
        evidence=(
            EvidenceEnvelope(
                evidence_id=EVIDENCE_ID,
                evidence_type="basic_v2",
                domain=EvidenceDomain.OBSERVATION,
                trust=EvidenceTrustV1.TRUSTED_OBSERVATION,
                content={"bounded": True, "packet_count": 8},
                provenance="fixture",
            ),
        ),
        source_digest=f"{index % 16:x}" * 64,
    )


def _sufficient_payload() -> dict[str, object]:
    return {
        "behavior_summary": "The bounded exchange has a distinctive request structure.",
        "supporting_evidence": [
            {"evidence_id": EVIDENCE_ID, "claim": "Eight bounded packets are visible."}
        ],
        "missing_evidence": [],
        "evidence_sufficient": True,
        "primary_gap": None,
        "gap_type": "NONE",
        "recoverability": "ALREADY_SUFFICIENT",
        "teacher_confidence": 0.9,
    }


def _insufficient_payload() -> dict[str, object]:
    return {
        "behavior_summary": "The bounded exchange remains ambiguous.",
        "supporting_evidence": [
            {"evidence_id": EVIDENCE_ID, "claim": "Eight bounded packets are visible."}
        ],
        "missing_evidence": ["TEMPORAL", "APPLICATION"],
        "evidence_sufficient": False,
        "primary_gap": "TEMPORAL",
        "gap_type": "OBSERVATIONAL",
        "recoverability": "RECOVERABLE_WITH_AVAILABLE_TOOLS",
        "teacher_confidence": 0.75,
    }


def test_evidence_state_v2_closed_vocabulary_and_valid_states() -> None:
    assert tuple(item.value for item in EvidenceFamilyV2) == (
        "PACKET_PAYLOAD",
        "APPLICATION",
        "TEMPORAL",
        "RELATION",
        "KNOWLEDGE",
    )
    assert tuple(item.value for item in GapDomainV2) == (
        "OBSERVATIONAL",
        "KNOWLEDGE",
        "MIXED",
        "NONE",
    )
    assert tuple(item.value for item in RecoverabilityV2) == (
        "ALREADY_SUFFICIENT",
        "RECOVERABLE_WITH_AVAILABLE_TOOLS",
        "NOT_RECOVERABLE_FROM_AVAILABLE_NETWORK_EVIDENCE",
    )

    sufficient = TeacherAnnotationV2.model_validate(_sufficient_payload())
    assert sufficient.primary_gap is None
    assert sufficient.missing_evidence == ()

    mixed = EvidenceStateV2(
        evidence_sufficient=False,
        missing_evidence=(EvidenceFamilyV2.RELATION, EvidenceFamilyV2.KNOWLEDGE),
        primary_gap=EvidenceFamilyV2.RELATION,
        gap_type=GapDomainV2.MIXED,
        recoverability=RecoverabilityV2.NOT_RECOVERABLE_FROM_AVAILABLE_NETWORK_EVIDENCE,
    )
    assert mixed.gap_type is GapDomainV2.MIXED


@pytest.mark.parametrize(
    ("changes", "error"),
    (
        ({"missing_evidence": ["TEMPORAL"]}, "sufficient evidence cannot retain"),
        ({"primary_gap": "TEMPORAL"}, "null primary gap"),
        ({"gap_type": "OBSERVATIONAL"}, "gap_type NONE"),
        (
            {"recoverability": "RECOVERABLE_WITH_AVAILABLE_TOOLS"},
            "recoverability ALREADY_SUFFICIENT",
        ),
        (
            {
                "evidence_sufficient": False,
                "recoverability": "RECOVERABLE_WITH_AVAILABLE_TOOLS",
            },
            "at least one missing family",
        ),
    ),
)
def test_evidence_state_v2_rejects_inconsistent_sufficient_contract(
    changes: dict[str, object], error: str
) -> None:
    payload = {**_sufficient_payload(), **changes}
    payload.pop("teacher_confidence")
    with pytest.raises(ValidationError, match=error):
        EvidenceStateV2.model_validate(payload)


@pytest.mark.parametrize(
    ("changes", "error"),
    (
        ({"missing_evidence": ["TEMPORAL", "TEMPORAL"]}, "families must be unique"),
        ({"primary_gap": "RELATION"}, "must belong to missing_evidence"),
        ({"gap_type": "KNOWLEDGE"}, "disagrees with missing evidence domain"),
        ({"recoverability": "ALREADY_SUFFICIENT"}, "cannot be ALREADY_SUFFICIENT"),
    ),
)
def test_evidence_state_v2_rejects_invalid_multi_gap_contract(
    changes: dict[str, object], error: str
) -> None:
    payload = {**_insufficient_payload(), **changes}
    payload.pop("teacher_confidence")
    with pytest.raises(ValidationError, match=error):
        EvidenceStateV2.model_validate(payload)


def test_evidence_state_v2_requires_unique_support_ids() -> None:
    payload = _insufficient_payload()
    payload["supporting_evidence"] = [
        {"evidence_id": EVIDENCE_ID, "claim": "First claim."},
        {"evidence_id": EVIDENCE_ID, "claim": "Second claim."},
    ]
    with pytest.raises(ValidationError, match="supporting evidence IDs must be unique"):
        TeacherAnnotationV2.model_validate(payload)


def test_teacher_v2_request_is_versioned_closed_and_identity_safe() -> None:
    snapshot = _snapshot(
        capabilities=(
            "packet_expansion",
            "request_sanitized_payload",
            "application_evidence",
            "TEMPORAL",
            "graph_context",
            "knowledge_retrieval",
        )
    )
    request = build_teacher_v2_request(snapshot)
    assert request.evidence_state_schema_version == EVIDENCE_STATE_SCHEMA_V2
    assert request.available_but_hidden_capabilities == tuple(EvidenceFamilyV2)
    rendered = request.model_dump_json()
    assert SAMPLE_ID not in rendered
    assert all(token not in rendered for token in ('"split"', '"ku_role"', "pcap"))
    with pytest.raises(ValueError, match="unsupported Teacher-v2 capability"):
        evidence_families_from_capabilities(("free_form_tool",))


def test_teacher_v2_validator_enforces_grounding_recoverability_and_label_isolation() -> None:
    snapshot = _snapshot()
    assert validate_teacher_v2_annotation(_insufficient_payload(), snapshot).primary_gap is (
        EvidenceFamilyV2.TEMPORAL
    )

    unavailable = deepcopy(_insufficient_payload())
    unavailable["primary_gap"] = "RELATION"
    unavailable["missing_evidence"] = ["RELATION"]
    with pytest.raises(ValueError, match="lacks an available capability"):
        validate_teacher_v2_annotation(unavailable, snapshot)

    false_terminal = deepcopy(_insufficient_payload())
    false_terminal["recoverability"] = (
        "NOT_RECOVERABLE_FROM_AVAILABLE_NETWORK_EVIDENCE"
    )
    with pytest.raises(ValueError, match="conflicts with an available capability"):
        validate_teacher_v2_annotation(false_terminal, snapshot)

    bad_support = deepcopy(_insufficient_payload())
    bad_support["supporting_evidence"] = [
        {"evidence_id": "ev_missing_12345678", "claim": "Unavailable."}
    ]
    with pytest.raises(ValueError, match="support references unavailable evidence"):
        validate_teacher_v2_annotation(bad_support, snapshot)

    leaked = deepcopy(_insufficient_payload())
    leaked["behavior_summary"] = "This confirms the Password class."
    with pytest.raises(ValueError, match="class verdict"):
        validate_teacher_v2_annotation(leaked, snapshot)

    flood_observation = deepcopy(_insufficient_payload())
    flood_observation["behavior_summary"] = (
        "Repeated SYN-only exchanges form a concentrated flood-like pattern."
    )
    assert validate_teacher_v2_annotation(
        flood_observation, _snapshot(label="DDoS_TCP")
    ).evidence_sufficient is False

    password_observation = deepcopy(_insufficient_payload())
    password_observation["behavior_summary"] = (
        "Credential parameters confirm a password submission."
    )
    assert validate_teacher_v2_annotation(
        password_observation, _snapshot(label="Password")
    ).evidence_sufficient is False

    scanning_observation = deepcopy(_insufficient_payload())
    scanning_observation["behavior_summary"] = (
        "Short failed exchanges form a scan-like pattern."
    )
    assert validate_teacher_v2_annotation(
        scanning_observation, _snapshot(label="Vulnerability_scanner")
    ).evidence_sufficient is False

    assert validate_teacher_v2_annotation(
        _sufficient_payload(), _snapshot(primary=False)
    ).evidence_sufficient is True


def test_teacher_v2_declassification_changes_only_explicit_fine_label_text() -> None:
    payload = _sufficient_payload()
    payload["behavior_summary"] = (
        "Repeated requests are consistent with DDoS_HTTP behavior and a SYN flood."
    )
    normalized, changed = teacher_module._declassify_teacher_v2_payload(
        payload, "DDoS_HTTP"
    )
    assert changed is True
    assert "DDoS_HTTP" not in normalized["behavior_summary"]
    assert "SYN flood" in normalized["behavior_summary"]
    assert normalized["evidence_sufficient"] == payload["evidence_sufficient"]
    assert normalized["missing_evidence"] == payload["missing_evidence"]


def test_teacher_v2_schema_canonicalization_preserves_core_sufficiency() -> None:
    payload = _sufficient_payload()
    payload.update(
        {
            "missing_evidence": ["TEMPORAL", "TEMPORAL"],
            "primary_gap": "TEMPORAL",
            "gap_type": "OBSERVATIONAL",
            "recoverability": "RECOVERABLE_WITH_AVAILABLE_TOOLS",
            "supporting_evidence": [
                payload["supporting_evidence"][0],
                payload["supporting_evidence"][0],
            ],
        }
    )
    normalized, changes = teacher_module._canonicalize_teacher_v2_payload(payload)
    assert normalized["evidence_sufficient"] is True
    assert normalized["missing_evidence"] == []
    assert normalized["primary_gap"] is None
    assert normalized["gap_type"] == "NONE"
    assert normalized["recoverability"] == "ALREADY_SUFFICIENT"
    assert len(normalized["supporting_evidence"]) == 1
    assert set(changes) == {
        "DEDUPLICATE_SUPPORTING_EVIDENCE_ID",
        "DEDUPLICATE_MISSING_EVIDENCE_FAMILY",
        "CANONICALIZE_SUFFICIENT_STATE",
    }


def test_teacher_v2_prompt_and_client_use_only_v2_contract_with_bounded_repair() -> None:
    historical = teacher_v2_prompt_v1()
    prompt = teacher_v2_prompt_v2()
    assert historical.version == "TEACHER_V2_PROMPT_V1"
    assert prompt.version == "TEACHER_V2_PROMPT_V2"
    assert prompt.digest != teacher_prompt_v3().digest
    assert prompt.output_contract["gap_type"] == "OBSERVATIONAL|KNOWLEDGE|MIXED|NONE"
    assert "primary_gap" in prompt.output_contract
    assert "recoverability" in prompt.output_contract

    class QueueTransport:
        def __init__(self) -> None:
            self.payloads = [
                {**_insufficient_payload(), "primary_gap": "RELATION"},
                _insufficient_payload(),
            ]
            self.requests = []

        def send(self, request):
            self.requests.append(request)
            return RawLLMResponse(
                structured_payload=self.payloads.pop(0),
                provider="deepseek",
                model_id="fixture-teacher-v2",
                request_id="fixture-v2-request",
                usage=RawUsage(input_tokens=10, output_tokens=10, total_tokens=20),
            )

    transport = QueueTransport()
    annotation, audit = DeepSeekTeacherV2Client(
        transport, settings=DeepSeekFlashSettings(model_id="fixture-teacher-v2")
    ).annotate(_snapshot())
    assert annotation.primary_gap is EvidenceFamilyV2.TEMPORAL
    assert audit["repair_used"] is True
    assert audit["transport_attempt_count"] == 2
    assert audit["evidence_state_schema_version"] == EVIDENCE_STATE_SCHEMA_V2
    assert len(transport.requests) == 2
    assert all(
        request.prompt.prompt_version == "TEACHER_V2_PROMPT_V2"
        for request in transport.requests
    )
    repair = transport.requests[1].model_dump_json()
    assert "allowed_evidence_families" in repair
    assert "available_capability_families" in repair


def test_teacher_v2_pilot_selector_is_deterministic_and_bounded() -> None:
    labels = ("Normal", "DDoS_TCP", "MITM", "Password")
    snapshots = [
        _snapshot(
            index=index,
            label=labels[index % len(labels)],
            primary=index % 3 != 0,
            capabilities=("temporal_context",)
            if index % 2
            else ("application_evidence", "graph_context"),
        )
        for index in range(1, 61)
    ]
    selected = select_teacher_v2_pilot(snapshots, target=20)
    reversed_selected = select_teacher_v2_pilot(list(reversed(snapshots)), target=20)
    assert len(selected) == 20
    assert [item.evidence_state_id for item in selected] == [
        item.evidence_state_id for item in reversed_selected
    ]
    assert len({item.fine_label for item in selected}) == len(labels)
    with pytest.raises(ValueError, match="20..50"):
        select_teacher_v2_pilot(snapshots, target=19)
    with pytest.raises(ValueError, match="20..50"):
        select_teacher_v2_pilot(snapshots, target=51)
    with pytest.raises(ValueError, match="duplicate evidence_state_id"):
        select_teacher_v2_pilot([snapshots[0], snapshots[0]], target=20)


def test_teacher_v2_bulk_is_durable_resumable_seedable_and_digest_bound(tmp_path) -> None:
    class QueueTransport:
        def __init__(self, payloads: list[dict[str, object]]) -> None:
            self.payloads = list(payloads)
            self.requests = []

        def send(self, request):
            self.requests.append(request)
            if not self.payloads:
                raise AssertionError("unexpected provider call")
            return RawLLMResponse(
                structured_payload=self.payloads.pop(0),
                provider="deepseek",
                model_id="fixture-teacher-v2",
                request_id=f"fixture-{len(self.requests)}",
                usage=RawUsage(input_tokens=10, output_tokens=10, total_tokens=20),
            )

    settings = DeepSeekFlashSettings(model_id="fixture-teacher-v2", max_attempts=1)
    first = _snapshot(index=101)
    second = _snapshot(index=102)

    pilot_transport = QueueTransport([_sufficient_payload()])
    pilot_root = tmp_path / "pilot"
    pilot_manifest = annotate_snapshots_v2(
        [first],
        pilot_root,
        client=DeepSeekTeacherV2Client(pilot_transport, settings=settings),
        concurrency=1,
    )
    assert pilot_manifest["status"] == "PASS"
    assert pilot_manifest["cache_namespace"] == TEACHER_V2_CACHE_NAMESPACE
    assert pilot_manifest["cost"] == "UNKNOWN"
    assert pilot_manifest["valid_first_pass_count"] == 1
    assert pilot_manifest["repair_attempt_count"] == 0
    assert pilot_manifest["transport_attempt_count"] == 1
    assert pilot_manifest["schema_response_attempt_count"] == 1

    bulk_transport = QueueTransport([_insufficient_payload()])
    bulk_root = tmp_path / "bulk"
    bulk_manifest = annotate_snapshots_v2(
        [first, second],
        bulk_root,
        client=DeepSeekTeacherV2Client(bulk_transport, settings=settings),
        concurrency=1,
        seed_cache_roots=(pilot_root / "cache",),
    )
    assert bulk_manifest["counts"] == {"PASS": 1, "CACHED": 1, "QUARANTINE": 0}
    assert len(bulk_transport.requests) == 1
    partial = json.loads((bulk_root / "partial_manifest.json").read_text())
    assert partial["status"] == "COMPLETE"
    assert partial["completed"] == 2 and partial["remaining"] == 0
    seeded_record = json.loads(
        (bulk_root / "records" / f"{first.evidence_state_id}.json").read_text()
    )
    assert seeded_record["cache_namespace"] == TEACHER_V2_CACHE_NAMESPACE
    assert seeded_record["evidence_state_schema_version"] == EVIDENCE_STATE_SCHEMA_V2
    assert seeded_record["cost"] == "UNKNOWN"

    no_call_transport = QueueTransport([])
    resumed = annotate_snapshots_v2(
        [first, second],
        bulk_root,
        client=DeepSeekTeacherV2Client(no_call_transport, settings=settings),
        concurrency=1,
    )
    assert resumed["counts"] == {"PASS": 0, "CACHED": 2, "QUARANTINE": 0}
    assert no_call_transport.requests == []

    old_key = json.loads(
        (bulk_root / "cache" / f"{second.evidence_state_id}.json").read_text()
    )["cache_key"]
    changed_second = second.model_copy(update={"source_digest": "e" * 64})
    changed_transport = QueueTransport([_insufficient_payload()])
    changed = annotate_snapshots_v2(
        [first, changed_second],
        bulk_root,
        client=DeepSeekTeacherV2Client(changed_transport, settings=settings),
        concurrency=1,
    )
    assert changed["counts"] == {"PASS": 1, "CACHED": 1, "QUARANTINE": 0}
    assert len(changed_transport.requests) == 1
    new_record = json.loads(
        (bulk_root / "cache" / f"{second.evidence_state_id}.json").read_text()
    )
    assert new_record["evidence_state_digest"] == "e" * 64
    assert new_record["cache_key"] != old_key

    with pytest.raises(ValueError, match="duplicate evidence_state_id"):
        annotate_snapshots_v2(
            [first, first],
            tmp_path / "duplicate",
            client=DeepSeekTeacherV2Client(QueueTransport([]), settings=settings),
            concurrency=1,
        )
