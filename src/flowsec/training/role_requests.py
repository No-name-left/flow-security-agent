from __future__ import annotations

from pydantic import Field, model_validator

from flowsec.runtime.contracts import (
    AgentAction,
    BudgetView,
    CapabilityStatus,
    EvidenceItem,
    FailureCode,
    SupervisorView,
    TrafficExpertResult,
    UnknownDecision,
    ValidatedExperienceView,
)

from .contracts import (
    EVIDENCE_STATE_SCHEMA_V2,
    EvidenceEnvelope,
    EvidenceFamilyV2,
    EvidenceSnapshot,
    EvidenceStateV1,
    FrozenModel,
)


class TeacherRequestV2(FrozenModel):
    immutable_verified_train_label: str = Field(min_length=1, repr=False)
    current_stage_evidence: tuple[EvidenceEnvelope, ...]
    available_but_hidden_capabilities: tuple[str, ...] = ()
    controlled_lower_evidence_auxiliary: bool
    response_format: str = Field(default="json_object", pattern=r"^json_object$")


class TeacherRequestV3(FrozenModel):
    """Typed request for logical Teacher-v2 / Evidence State v2."""

    immutable_verified_train_label: str = Field(min_length=1, repr=False)
    current_stage_evidence: tuple[EvidenceEnvelope, ...]
    available_but_hidden_capabilities: tuple[EvidenceFamilyV2, ...] = ()
    controlled_lower_evidence_auxiliary: bool
    evidence_state_schema_version: str = Field(
        default=EVIDENCE_STATE_SCHEMA_V2,
        pattern=r"^EVIDENCE_STATE_SCHEMA_V2$",
    )
    response_format: str = Field(default="json_object", pattern=r"^json_object$")

    @model_validator(mode="after")
    def validate_unique_capabilities(self) -> "TeacherRequestV3":
        if len(self.available_but_hidden_capabilities) != len(
            set(self.available_but_hidden_capabilities)
        ):
            raise ValueError("Teacher-v2 capability families must be unique")
        return self


# The logical role is Teacher-v2; the request contract is the third repository request version.
TeacherV2RequestV1 = TeacherRequestV3


_CAPABILITY_TO_EVIDENCE_FAMILY_V2: dict[str, EvidenceFamilyV2] = {
    "packet": EvidenceFamilyV2.PACKET_PAYLOAD,
    "packet_expansion": EvidenceFamilyV2.PACKET_PAYLOAD,
    "expand_packets": EvidenceFamilyV2.PACKET_PAYLOAD,
    "payload": EvidenceFamilyV2.PACKET_PAYLOAD,
    "sanitized_payload": EvidenceFamilyV2.PACKET_PAYLOAD,
    "request_sanitized_payload": EvidenceFamilyV2.PACKET_PAYLOAD,
    "application": EvidenceFamilyV2.APPLICATION,
    "application_evidence": EvidenceFamilyV2.APPLICATION,
    "request_application_evidence": EvidenceFamilyV2.APPLICATION,
    "temporal": EvidenceFamilyV2.TEMPORAL,
    "temporal_context": EvidenceFamilyV2.TEMPORAL,
    "expand_temporal_context": EvidenceFamilyV2.TEMPORAL,
    "relation": EvidenceFamilyV2.RELATION,
    "graph": EvidenceFamilyV2.RELATION,
    "graph_context": EvidenceFamilyV2.RELATION,
    "expand_graph_context": EvidenceFamilyV2.RELATION,
    "knowledge": EvidenceFamilyV2.KNOWLEDGE,
    "knowledge_retrieval": EvidenceFamilyV2.KNOWLEDGE,
    "retrieve_knowledge": EvidenceFamilyV2.KNOWLEDGE,
    **{item.value.casefold(): item for item in EvidenceFamilyV2},
}


def evidence_families_from_capabilities(
    capabilities: tuple[str, ...],
) -> tuple[EvidenceFamilyV2, ...]:
    """Project legacy/action capability names into the closed v2 family vocabulary."""

    projected: list[EvidenceFamilyV2] = []
    for capability in capabilities:
        key = str(getattr(capability, "value", capability)).strip().casefold()
        try:
            family = _CAPABILITY_TO_EVIDENCE_FAMILY_V2[key]
        except KeyError as exc:
            raise ValueError(f"unsupported Teacher-v2 capability: {key}") from exc
        if family not in projected:
            projected.append(family)
    return tuple(projected)


class DeterministicJudgeCheckSummaryV1(FrozenModel):
    schema_valid: bool
    evidence_ids_valid: bool
    forbidden_field_count: int = Field(ge=0)
    deterministic_notes: tuple[str, ...] = ()


class JudgeRequestV1(FrozenModel):
    current_evidence: tuple[EvidenceEnvelope, ...]
    current_rollout: EvidenceStateV1
    deterministic_checks: DeterministicJudgeCheckSummaryV1
    response_format: str = Field(default="json_object", pattern=r"^json_object$")


class SupervisorRequestV1(FrozenModel):
    evidence: tuple[EvidenceItem, ...]
    traffic_expert_result: TrafficExpertResult
    traffic_expert_history: tuple[TrafficExpertResult, ...]
    unknown_decision: UnknownDecision
    capabilities: tuple[CapabilityStatus, ...]
    budget: BudgetView
    round_index: int = Field(ge=0)
    request_history: tuple[str, ...]
    action_history: tuple[AgentAction, ...]
    tool_failures: tuple[FailureCode, ...]
    validated_experiences: tuple[ValidatedExperienceView, ...]


def build_teacher_request(snapshot: EvidenceSnapshot) -> TeacherRequestV2:
    if snapshot.split != "train" or snapshot.ku_role != "K_known":
        raise ValueError("Teacher is limited to K_known TRAIN snapshots")
    return TeacherRequestV2(
        immutable_verified_train_label=snapshot.fine_label,
        current_stage_evidence=snapshot.evidence,
        available_but_hidden_capabilities=snapshot.available_capabilities,
        controlled_lower_evidence_auxiliary=(snapshot.stage_type.value == "controlled_mask"),
    )


def build_teacher_v2_request(snapshot: EvidenceSnapshot) -> TeacherRequestV3:
    if snapshot.split != "train" or snapshot.ku_role != "K_known":
        raise ValueError("Teacher-v2 is limited to K_known TRAIN snapshots")
    return TeacherRequestV3(
        immutable_verified_train_label=snapshot.fine_label,
        current_stage_evidence=snapshot.evidence,
        available_but_hidden_capabilities=evidence_families_from_capabilities(
            snapshot.available_capabilities
        ),
        controlled_lower_evidence_auxiliary=(
            snapshot.stage_type.value == "controlled_mask"
        ),
    )


def build_judge_request(
    evidence: tuple[EvidenceEnvelope, ...],
    rollout: EvidenceStateV1,
    deterministic_checks: DeterministicJudgeCheckSummaryV1,
) -> JudgeRequestV1:
    return JudgeRequestV1(
        current_evidence=evidence,
        current_rollout=rollout,
        deterministic_checks=deterministic_checks,
    )


def build_supervisor_request(state: SupervisorView) -> SupervisorRequestV1:
    safe = SupervisorView.model_validate(state.model_dump(mode="python"))
    return SupervisorRequestV1(
        evidence=safe.evidence,
        traffic_expert_result=safe.traffic_expert_result,
        traffic_expert_history=safe.traffic_expert_history,
        unknown_decision=safe.unknown_decision,
        capabilities=safe.capabilities,
        budget=safe.budget,
        round_index=safe.round_index,
        request_history=safe.request_history,
        action_history=safe.action_history,
        tool_failures=safe.tool_failures,
        validated_experiences=safe.retrieved_experiences,
    )
