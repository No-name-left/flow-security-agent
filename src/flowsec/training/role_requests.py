from __future__ import annotations

from pydantic import Field

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

from .contracts import EvidenceEnvelope, EvidenceSnapshot, EvidenceStateV1, FrozenModel


class TeacherRequestV2(FrozenModel):
    immutable_verified_train_label: str = Field(min_length=1, repr=False)
    current_stage_evidence: tuple[EvidenceEnvelope, ...]
    available_but_hidden_capabilities: tuple[str, ...] = ()
    controlled_lower_evidence_auxiliary: bool
    response_format: str = Field(default="json_object", pattern=r"^json_object$")


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
