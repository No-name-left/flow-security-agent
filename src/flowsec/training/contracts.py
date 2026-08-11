from __future__ import annotations

import hashlib
import json
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from flowsec.runtime.contracts import validate_model_visible_value


TRAINING_PROTOCOL_VERSION = "near_pretraining_v1"
EVIDENCE_STATE_SCHEMA_VERSION = "EVIDENCE_STATE_SCHEMA_V1"
APPLICATION_EVIDENCE_VERSION = "APPLICATION_EVIDENCE_V1"
SANITIZED_PAYLOAD_VERSION = "SANITIZED_PAYLOAD_V1"
RAG_EVIDENCE_SCHEMA_VERSION = "RAG_EVIDENCE_SCHEMA_V1"
SFT_CORPUS_VERSION = "NEAR_SFT_CORPUS_V2"
RL_PROMPT_POOL_VERSION = "RL_PROMPT_POOL_V1"


def canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def content_digest(value: Any) -> str:
    payload = value if isinstance(value, str) else canonical_json(value)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class FrozenModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class EvidenceDomain(StrEnum):
    OBSERVATION = "OBSERVATION"
    KNOWLEDGE = "KNOWLEDGE"


class EvidenceTrustV1(StrEnum):
    TRUSTED_OBSERVATION = "TRUSTED_OBSERVATION"
    UNTRUSTED_PAYLOAD = "UNTRUSTED_PAYLOAD"
    UNTRUSTED_KNOWLEDGE = "UNTRUSTED_KNOWLEDGE"


class StageType(StrEnum):
    INITIAL = "initial"
    PACKET = "packet"
    TEMPORAL = "temporal"
    RELATION = "relation"
    APPLICATION = "application"
    PAYLOAD = "payload"
    KNOWLEDGE = "knowledge"
    CONTROLLED_MASK = "controlled_mask"


class EvidenceGapType(StrEnum):
    NONE = "none"
    PACKET = "packet"
    TEMPORAL = "temporal"
    RELATION = "relation"
    APPLICATION = "application"
    PAYLOAD = "payload"
    KNOWLEDGE = "knowledge"
    AMBIGUOUS = "ambiguous"


class EvidenceEnvelope(FrozenModel):
    """One model-visible evidence object with no backend join identity."""

    evidence_id: str = Field(pattern=r"^ev_[a-z0-9_]{8,80}$")
    evidence_type: str = Field(min_length=1, max_length=80)
    domain: EvidenceDomain
    trust: EvidenceTrustV1
    content: dict[str, Any]
    provenance: str = Field(min_length=1, max_length=120)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_safe_projection(self) -> "EvidenceEnvelope":
        validate_model_visible_value(self.model_dump(mode="json"), location="training_evidence")
        if self.domain is EvidenceDomain.KNOWLEDGE and self.trust is not EvidenceTrustV1.UNTRUSTED_KNOWLEDGE:
            raise ValueError("Knowledge evidence must remain explicitly untrusted")
        if self.evidence_type == "sanitized_payload" and self.trust is not EvidenceTrustV1.UNTRUSTED_PAYLOAD:
            raise ValueError("Payload evidence must remain explicitly untrusted")
        return self


class EvidenceSnapshot(FrozenModel):
    """Backend-controlled offline state; only ``evidence`` is model-visible."""

    sample_id: str = Field(pattern=r"^fs1_[0-9a-f]{40}$", repr=False)
    evidence_state_id: str = Field(pattern=r"^state_[0-9a-f]{24}$")
    fine_label: str = Field(min_length=1, repr=False)
    coarse_label: str = Field(min_length=1, repr=False)
    split: str = Field(min_length=1, repr=False)
    ku_role: str = Field(min_length=1, repr=False)
    stage_type: StageType
    classification_supervision_valid: bool
    available_capabilities: tuple[str, ...] = ()
    evidence: tuple[EvidenceEnvelope, ...]
    source_digest: str = Field(pattern=r"^[0-9a-f]{64}$", repr=False)

    @model_validator(mode="after")
    def validate_snapshot(self) -> "EvidenceSnapshot":
        if self.split != "train" or self.ku_role != "K_known":
            raise ValueError("formal Near training snapshots must be K_known TRAIN only")
        identifiers = [item.evidence_id for item in self.evidence]
        if not identifiers or len(identifiers) != len(set(identifiers)):
            raise ValueError("snapshot evidence IDs must be nonempty and unique")
        return self


class SupportingEvidenceV1(FrozenModel):
    evidence_id: str = Field(pattern=r"^ev_[a-z0-9_]{8,80}$")
    claim: str = Field(min_length=1, max_length=320)

    @field_validator("claim")
    @classmethod
    def validate_claim(cls, value: str) -> str:
        validate_model_visible_value(value, location="evidence_state.supporting_claim")
        return value


class MissingEvidenceV1(FrozenModel):
    type: EvidenceGapType
    description: str = Field(min_length=1, max_length=240)

    @field_validator("description")
    @classmethod
    def validate_description(cls, value: str) -> str:
        validate_model_visible_value(value, location="evidence_state.missing_evidence")
        return value


class EvidenceStateV1(FrozenModel):
    """Frozen LM-branch target. It deliberately contains no fine-class field."""

    behavior_summary: str = Field(min_length=1, max_length=360)
    supporting_evidence: tuple[SupportingEvidenceV1, ...] = ()
    missing_evidence: tuple[MissingEvidenceV1, ...] = ()
    evidence_sufficient: bool
    gap_type: EvidenceGapType

    @model_validator(mode="after")
    def validate_consistency(self) -> "EvidenceStateV1":
        validate_model_visible_value(self.behavior_summary, location="evidence_state.summary")
        if self.evidence_sufficient and self.gap_type not in {
            EvidenceGapType.NONE,
            EvidenceGapType.AMBIGUOUS,
        }:
            raise ValueError("sufficient evidence cannot declare an unresolved typed gap")
        if not self.evidence_sufficient and self.gap_type is EvidenceGapType.NONE:
            raise ValueError("insufficient evidence must declare a gap")
        if self.evidence_sufficient and any(
            item.type is not EvidenceGapType.AMBIGUOUS for item in self.missing_evidence
        ):
            raise ValueError("sufficient evidence cannot retain label-critical missing evidence")
        return self


class TeacherAnnotationV1(EvidenceStateV1):
    teacher_confidence: float = Field(ge=0.0, le=1.0)


def validate_evidence_grounding(
    state: EvidenceStateV1,
    evidence: tuple[EvidenceEnvelope, ...],
) -> None:
    available = {item.evidence_id: item for item in evidence}
    for support in state.supporting_evidence:
        if support.evidence_id not in available:
            raise ValueError(f"support references unavailable evidence: {support.evidence_id}")
        if available[support.evidence_id].domain is EvidenceDomain.KNOWLEDGE:
            raise ValueError("Knowledge evidence cannot be cited as an observed-session fact")


class SFTRecordV1(FrozenModel):
    sample_id: str = Field(pattern=r"^fs1_[0-9a-f]{40}$", repr=False)
    evidence_state_id: str = Field(pattern=r"^state_[0-9a-f]{24}$")
    fine_label: str = Field(min_length=1, repr=False)
    class_index: int = Field(ge=0)
    classification_ce_eligible: bool
    state_role: str = Field(pattern=r"^(primary|auxiliary)$")
    serialized_model_input: str = Field(min_length=1)
    evidence_state_target: EvidenceStateV1
    stage_type: StageType
    available_capability_mask: tuple[str, ...]
    prompt_version: str
    serialization_version: str
    schema_version: str = EVIDENCE_STATE_SCHEMA_VERSION
    teacher_annotation_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    teacher_model: str = Field(min_length=1)
    teacher_prompt_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    teacher_request_id: str = Field(min_length=1)
    source_split: str = Field(default="train", repr=False)
    source_role: str = Field(default="K_known", repr=False)
    dataset_digest: str = Field(pattern=r"^[0-9a-f]{64}$", repr=False)
    session_weight: float = Field(gt=0.0, le=1.0)

    @field_validator("serialized_model_input")
    @classmethod
    def validate_serialized_input(cls, value: str) -> str:
        validate_model_visible_value(value, location="sft.serialized_model_input")
        return value

    @model_validator(mode="after")
    def validate_training_scope(self) -> "SFTRecordV1":
        if self.source_split != "train" or self.source_role != "K_known":
            raise ValueError("SFT record escaped K_known TRAIN scope")
        if (self.state_role == "primary") != self.classification_ce_eligible:
            raise ValueError("only the legal primary state may receive classification CE")
        if self.state_role == "auxiliary" and self.stage_type is not StageType.CONTROLLED_MASK:
            raise ValueError("auxiliary SFT states must use the controlled lower-evidence protocol")
        return self


class NearValidationRecordV1(FrozenModel):
    sample_id: str = Field(pattern=r"^fs1_[0-9a-f]{40}$", repr=False)
    fine_label: str = Field(min_length=1, repr=False)
    class_index: int = Field(ge=0)
    serialized_model_input: str = Field(min_length=1)
    prompt_version: str
    serialization_version: str
    source_split: str = Field(default="validation", repr=False)
    source_role: str = Field(default="K_known", repr=False)
    dataset_digest: str = Field(pattern=r"^[0-9a-f]{64}$", repr=False)

    @field_validator("serialized_model_input")
    @classmethod
    def validate_serialized_input(cls, value: str) -> str:
        validate_model_visible_value(value, location="validation.serialized_model_input")
        return value

    @model_validator(mode="after")
    def validate_scope(self) -> "NearValidationRecordV1":
        if self.source_split != "validation" or self.source_role != "K_known":
            raise ValueError("validation record escaped K_known validation scope")
        return self


class RLPromptRecordV1(FrozenModel):
    prompt_id: str = Field(pattern=r"^rlp_[0-9a-f]{24}$")
    evidence_state_id: str = Field(pattern=r"^state_[0-9a-f]{24}$")
    sample_id: str = Field(pattern=r"^fs1_[0-9a-f]{40}$", repr=False)
    fine_label: str = Field(min_length=1, repr=False)
    stage_type: StageType
    classification_supervision_valid: bool
    serialized_model_input: str = Field(min_length=1)
    source_split: str = Field(default="train", repr=False)
    source_role: str = Field(default="K_known", repr=False)

    @field_validator("serialized_model_input")
    @classmethod
    def validate_serialized_input(cls, value: str) -> str:
        validate_model_visible_value(value, location="rl.serialized_model_input")
        return value

    @model_validator(mode="after")
    def validate_scope(self) -> "RLPromptRecordV1":
        if self.source_split != "train" or self.source_role != "K_known":
            raise ValueError("RL prompt escaped K_known TRAIN scope")
        return self


class JudgeRewardV1(FrozenModel):
    grounding: float = Field(ge=0.0, le=1.0)
    evidence_sufficiency: float = Field(ge=0.0, le=1.0)
    missing_evidence_quality: float = Field(ge=0.0, le=1.0)
    gap_correctness: float = Field(ge=0.0, le=1.0)
    hallucination_avoidance: float = Field(ge=0.0, le=1.0)
    backoff_appropriateness: float = Field(ge=0.0, le=1.0)
    reliability_note: str = Field(min_length=1, max_length=240)


class SupervisorActionV1(StrEnum):
    EXPAND_PACKETS = "expand_packets"
    EXPAND_TEMPORAL_CONTEXT = "expand_temporal_context"
    EXPAND_GRAPH_CONTEXT = "expand_graph_context"
    REQUEST_APPLICATION_EVIDENCE = "request_application_evidence"
    REQUEST_SANITIZED_PAYLOAD = "request_sanitized_payload"
    RETRIEVE_KNOWLEDGE = "retrieve_knowledge"
    RECLASSIFY = "reclassify"
    ACCEPT_FINE = "accept_fine"
    BACKOFF_COARSE = "backoff_coarse"
    REJECT_UNKNOWN = "reject_unknown"
    ABSTAIN = "abstain"


class SupervisorDecisionV1(FrozenModel):
    action: SupervisorActionV1
    target: str = Field(min_length=1, max_length=160)
    short_reason: str = Field(min_length=1, max_length=240)

    @field_validator("target", "short_reason")
    @classmethod
    def validate_safe_text(cls, value: str) -> str:
        validate_model_visible_value(value, location="supervisor_decision")
        return value
