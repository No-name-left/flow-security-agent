from __future__ import annotations

import hashlib
import json
import re
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


PROHIBITED_MODEL_VISIBLE_NAMES = frozenset(
    {
        "ground_truth",
        "evaluation_label",
        "dataset_id",
        "dataset_name",
        "capture_id",
        "capture_name",
        "scenario_id",
        "scenario_name",
        "backend_identity",
        "backend_id",
        "source_ip",
        "destination_ip",
        "src_ip",
        "dst_ip",
        "raw_ip",
        "absolute_timestamp",
        "timestamp_absolute",
    }
)
_IPV4_PATTERN = re.compile(r"(?<!\d)(?:\d{1,3}\.){3}\d{1,3}(?!\d)")
_ABSOLUTE_TIME_PATTERN = re.compile(r"\b\d{4}-\d{2}-\d{2}[T ][0-2]\d:[0-5]\d")


def validate_model_visible_value(value: Any, *, location: str) -> None:
    """Reject explicit backend-only identities from a model-visible contract.

    This is a defensive contract check, not a replacement for the Production
    adapter's allow-list projection and privacy review.
    """

    if isinstance(value, dict):
        for key, item in value.items():
            normalized = str(key).casefold().replace("-", "_")
            if normalized in PROHIBITED_MODEL_VISIBLE_NAMES:
                raise ValueError(f"backend-only field in {location}: {key}")
            validate_model_visible_value(item, location=f"{location}.{key}")
        return
    if isinstance(value, (list, tuple, set, frozenset)):
        for index, item in enumerate(value):
            validate_model_visible_value(item, location=f"{location}[{index}]")
        return
    if isinstance(value, str):
        normalized = value.casefold().replace("-", "_")
        if any(name in normalized for name in PROHIBITED_MODEL_VISIBLE_NAMES):
            raise ValueError(f"backend-only marker in {location}")
        if _IPV4_PATTERN.search(value):
            raise ValueError(f"raw IPv4 address in {location}")
        if _ABSOLUTE_TIME_PATTERN.search(value):
            raise ValueError(f"absolute timestamp in {location}")


class RuntimeModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class FrozenRuntimeModel(RuntimeModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class GapDomain(StrEnum):
    OBSERVATIONAL = "observational"
    KNOWLEDGE = "knowledge"


class GapType(StrEnum):
    PACKET = "packet"
    TEMPORAL = "temporal"
    GRAPH = "graph"
    APPLICATION = "application"
    KNOWLEDGE = "knowledge"
    NONE = "none"
    OTHER = "other"


class EvidenceSufficiency(StrEnum):
    INSUFFICIENT = "insufficient"
    COARSE_ONLY = "coarse_only"
    SUFFICIENT = "sufficient"


class UnknownState(StrEnum):
    KNOWN_LIKELY = "known_likely"
    UNCERTAIN = "uncertain"
    UNKNOWN_LIKELY = "unknown_likely"


class AgentAction(StrEnum):
    EXPAND_PACKETS = "expand_packets"
    EXPAND_TEMPORAL_CONTEXT = "expand_temporal_context"
    EXPAND_GRAPH_CONTEXT = "expand_graph_context"
    REQUEST_APPLICATION_EVIDENCE = "request_application_evidence"
    RETRIEVE_KNOWLEDGE = "retrieve_knowledge"
    ACCEPT_FINE = "accept_fine"
    BACKOFF_COARSE = "backoff_coarse"
    REJECT_UNKNOWN = "reject_unknown"
    ABSTAIN = "abstain"


EVIDENCE_ACTIONS = frozenset(
    {
        AgentAction.EXPAND_PACKETS,
        AgentAction.EXPAND_TEMPORAL_CONTEXT,
        AgentAction.EXPAND_GRAPH_CONTEXT,
        AgentAction.REQUEST_APPLICATION_EVIDENCE,
        AgentAction.RETRIEVE_KNOWLEDGE,
    }
)
TERMINAL_ACTIONS = frozenset(set(AgentAction) - EVIDENCE_ACTIONS)


class Capability(StrEnum):
    PACKET_EXPANSION = "packet_expansion"
    TEMPORAL_CONTEXT = "temporal_context"
    GRAPH_CONTEXT = "graph_context"
    APPLICATION_EVIDENCE = "application_evidence"
    KNOWLEDGE_RETRIEVAL = "knowledge_retrieval"


ACTION_CAPABILITY: dict[AgentAction, Capability] = {
    AgentAction.EXPAND_PACKETS: Capability.PACKET_EXPANSION,
    AgentAction.EXPAND_TEMPORAL_CONTEXT: Capability.TEMPORAL_CONTEXT,
    AgentAction.EXPAND_GRAPH_CONTEXT: Capability.GRAPH_CONTEXT,
    AgentAction.REQUEST_APPLICATION_EVIDENCE: Capability.APPLICATION_EVIDENCE,
    AgentAction.RETRIEVE_KNOWLEDGE: Capability.KNOWLEDGE_RETRIEVAL,
}


class EvidenceTrust(StrEnum):
    TRUSTED = "trusted"
    UNTRUSTED_EVIDENCE = "untrusted_evidence"


class ToolStatus(StrEnum):
    SUCCESS = "success"
    UNAVAILABLE = "unavailable"
    FAILURE = "failure"


class RuntimePhase(StrEnum):
    TRAIN = "train"
    VALIDATION = "validation"
    U_DEV = "u_dev"
    TEST = "test"
    U_FINAL = "u_final"


class FeedbackSource(StrEnum):
    GROUND_TRUTH = "ground_truth"
    HUMAN_LABEL = "human_label"
    FEW_SHOT_CONFIRMATION = "few_shot_confirmation"
    VERIFIED_TOOL = "verified_tool"


class FinalDecisionType(StrEnum):
    FINE = "fine"
    COARSE = "coarse"
    UNKNOWN = "unknown"
    ABSTAIN = "abstain"


class FailureCode(StrEnum):
    INVALID_ACTION = "invalid_action"
    CAPABILITY_UNAVAILABLE = "capability_unavailable"
    TOOL_FAILURE = "tool_failure"
    SUPERVISOR_OUTPUT_FAILURE = "supervisor_output_failure"
    TRAFFIC_EXPERT_OUTPUT_FAILURE = "traffic_expert_output_failure"
    UNKNOWN_SCORER_FAILURE = "unknown_scorer_failure"
    BUDGET_EXHAUSTED = "budget_exhausted"
    MAX_ROUNDS_REACHED = "max_rounds_reached"
    REPEATED_REQUEST = "repeated_request"
    NO_STATE_CHANGE = "no_state_change"
    UNSAFE_EVIDENCE = "unsafe_evidence"
    MEMORY_ACCESS_FAILURE = "memory_access_failure"
    MEMORY_WRITE_FAILURE = "memory_write_failure"


class TraceEventType(StrEnum):
    TRAFFIC_EXPERT = "traffic_expert"
    UNKNOWN_SCORER = "unknown_scorer"
    SUPERVISOR = "supervisor"
    TOOL = "tool"
    MEMORY = "memory"
    FAILURE = "failure"
    FINAL = "final"


class CallMetrics(FrozenRuntimeModel):
    abstract_tokens: int = Field(default=0, ge=0)
    abstract_cost: float = Field(default=0.0, ge=0)
    abstract_latency: float = Field(default=0.0, ge=0)


class PredictionCandidate(FrozenRuntimeModel):
    label: str = Field(min_length=1)
    score: float | None = Field(default=None, allow_inf_nan=False)


class SupportingEvidence(FrozenRuntimeModel):
    evidence_id: str = Field(min_length=1)
    statement: str = Field(min_length=1)

    @field_validator("evidence_id", "statement")
    @classmethod
    def validate_statement(cls, value: str) -> str:
        validate_model_visible_value(value, location="supporting_evidence")
        return value


class MissingEvidence(FrozenRuntimeModel):
    description: str = Field(min_length=1)
    gap_type: GapType
    domain: GapDomain
    valuable: bool = True

    @model_validator(mode="after")
    def validate_domain(self) -> "MissingEvidence":
        validate_model_visible_value(self.description, location="missing_evidence.description")
        if self.gap_type is GapType.KNOWLEDGE and self.domain is not GapDomain.KNOWLEDGE:
            raise ValueError("KNOWLEDGE gaps must use the knowledge domain")
        if self.gap_type in {
            GapType.PACKET,
            GapType.TEMPORAL,
            GapType.GRAPH,
            GapType.APPLICATION,
        } and self.domain is not GapDomain.OBSERVATIONAL:
            raise ValueError("observable evidence gaps must use the observational domain")
        return self


class EvidenceItem(FrozenRuntimeModel):
    evidence_id: str = Field(min_length=1)
    gap_type: GapType
    domain: GapDomain
    content: str = Field(min_length=1)
    provenance: str = Field(min_length=1)
    trust: EvidenceTrust = EvidenceTrust.TRUSTED
    model_safe: bool = True
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_model_projection(self) -> "EvidenceItem":
        validate_model_visible_value(self.evidence_id, location="evidence.evidence_id")
        validate_model_visible_value(self.content, location="evidence.content")
        validate_model_visible_value(self.provenance, location="evidence.provenance")
        validate_model_visible_value(self.metadata, location="evidence.metadata")
        return self


class TrafficExpertResult(FrozenRuntimeModel):
    fine_candidates: tuple[PredictionCandidate, ...] = ()
    coarse_candidates: tuple[PredictionCandidate, ...] = ()
    short_analysis: str = ""
    supporting_evidence: tuple[SupportingEvidence, ...] = ()
    missing_evidence: tuple[MissingEvidence, ...] = ()
    evidence_sufficiency: EvidenceSufficiency
    model_signals: dict[str, Any] = Field(default_factory=dict)
    metrics: CallMetrics = Field(default_factory=CallMetrics)

    @field_validator("short_analysis")
    @classmethod
    def validate_analysis(cls, value: str) -> str:
        validate_model_visible_value(value, location="traffic_expert.short_analysis")
        return value

    @field_validator("model_signals")
    @classmethod
    def validate_model_signals(cls, value: dict[str, Any]) -> dict[str, Any]:
        validate_model_visible_value(value, location="traffic_expert.model_signals")
        return value


class UnknownDecision(FrozenRuntimeModel):
    score: float | None = Field(default=None, allow_inf_nan=False)
    state: UnknownState
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("metadata")
    @classmethod
    def validate_metadata(cls, value: dict[str, Any]) -> dict[str, Any]:
        validate_model_visible_value(value, location="unknown.metadata")
        return value


class CapabilityStatus(FrozenRuntimeModel):
    capability: Capability
    available: bool = True
    reason: str | None = None

    @field_validator("reason")
    @classmethod
    def validate_reason(cls, value: str | None) -> str | None:
        if value is not None:
            validate_model_visible_value(value, location="capability.reason")
        return value


class BudgetLimits(FrozenRuntimeModel):
    max_rounds: int = Field(ge=0)
    max_traffic_expert_calls: int = Field(ge=1)
    max_supervisor_calls: int = Field(ge=1)
    max_tool_calls: int = Field(ge=0)
    max_rag_calls: int = Field(ge=0)
    max_abstract_tokens: int = Field(ge=0)
    max_abstract_cost: float = Field(ge=0)
    max_abstract_latency: float = Field(ge=0)


class BudgetState(RuntimeModel):
    limits: BudgetLimits
    rounds: int = Field(default=0, ge=0)
    traffic_expert_calls: int = Field(default=0, ge=0)
    supervisor_calls: int = Field(default=0, ge=0)
    tool_calls: int = Field(default=0, ge=0)
    rag_calls: int = Field(default=0, ge=0)
    abstract_tokens: int = Field(default=0, ge=0)
    abstract_cost: float = Field(default=0.0, ge=0)
    abstract_latency: float = Field(default=0.0, ge=0)

    def can_consume(self, *, kind: str, metrics: CallMetrics | None = None) -> bool:
        metrics = metrics or CallMetrics()
        counters = {
            "traffic_expert": (self.traffic_expert_calls, self.limits.max_traffic_expert_calls),
            "supervisor": (self.supervisor_calls, self.limits.max_supervisor_calls),
            "tool": (self.tool_calls, self.limits.max_tool_calls),
            "rag": (self.rag_calls, self.limits.max_rag_calls),
        }
        if kind in counters and counters[kind][0] >= counters[kind][1]:
            return False
        return (
            self.abstract_tokens + metrics.abstract_tokens <= self.limits.max_abstract_tokens
            and self.abstract_cost + metrics.abstract_cost <= self.limits.max_abstract_cost
            and self.abstract_latency + metrics.abstract_latency <= self.limits.max_abstract_latency
        )

    def consume(self, *, kind: str, metrics: CallMetrics | None = None) -> None:
        metrics = metrics or CallMetrics()
        if not self.can_consume(kind=kind, metrics=metrics):
            raise ValueError(f"budget exhausted for {kind}")
        if kind == "traffic_expert":
            self.traffic_expert_calls += 1
        elif kind == "supervisor":
            self.supervisor_calls += 1
        elif kind == "tool":
            self.tool_calls += 1
        elif kind == "rag":
            self.rag_calls += 1
        else:
            raise ValueError(f"unknown budget kind: {kind}")
        self.abstract_tokens += metrics.abstract_tokens
        self.abstract_cost += metrics.abstract_cost
        self.abstract_latency += metrics.abstract_latency

    def snapshot(self) -> dict[str, Any]:
        return self.model_dump(mode="json")

    def reconcile_metrics(self, *, reserved: CallMetrics, actual: CallMetrics) -> None:
        if (
            actual.abstract_tokens > reserved.abstract_tokens
            or actual.abstract_cost > reserved.abstract_cost
            or actual.abstract_latency > reserved.abstract_latency
        ):
            raise ValueError("actual metrics exceeded the preflight reservation")
        self.abstract_tokens -= reserved.abstract_tokens - actual.abstract_tokens
        self.abstract_cost -= reserved.abstract_cost - actual.abstract_cost
        self.abstract_latency -= reserved.abstract_latency - actual.abstract_latency


class BudgetView(FrozenRuntimeModel):
    limits: BudgetLimits
    rounds: int
    traffic_expert_calls: int
    supervisor_calls: int
    tool_calls: int
    rag_calls: int
    abstract_tokens: int
    abstract_cost: float
    abstract_latency: float

    @classmethod
    def from_state(cls, state: BudgetState) -> "BudgetView":
        return cls.model_validate(state.model_dump())


class ToolRequest(FrozenRuntimeModel):
    action: AgentAction
    parameters: dict[str, Any] = Field(default_factory=dict)

    @field_validator("parameters")
    @classmethod
    def validate_parameters(cls, value: dict[str, Any]) -> dict[str, Any]:
        validate_model_visible_value(value, location="tool_request.parameters")
        try:
            json.dumps(value, sort_keys=True, allow_nan=False)
        except (TypeError, ValueError) as exc:
            raise ValueError("tool request parameters must be finite JSON data") from exc
        return value

    @property
    def signature(self) -> str:
        payload = json.dumps(self.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class ToolResult(FrozenRuntimeModel):
    status: ToolStatus
    request_signature: str
    evidence: tuple[EvidenceItem, ...] = ()
    metrics: CallMetrics = Field(default_factory=CallMetrics)
    error: str | None = None


class VerifiedFeedback(FrozenRuntimeModel):
    verified: bool
    source: FeedbackSource
    summary: str = Field(min_length=1)
    outcome_positive: bool


class ExperienceRecord(FrozenRuntimeModel):
    experience_id: str = Field(min_length=1)
    state_summary: str = Field(min_length=1)
    action: AgentAction
    outcome: str = Field(min_length=1)
    feedback: VerifiedFeedback
    keywords: tuple[str, ...] = ()
    positive: bool = True

    @model_validator(mode="after")
    def validate_retrievable_content(self) -> "ExperienceRecord":
        validate_model_visible_value(self.state_summary, location="experience.state_summary")
        validate_model_visible_value(self.outcome, location="experience.outcome")
        validate_model_visible_value(self.keywords, location="experience.keywords")
        return self


class ValidatedExperienceView(FrozenRuntimeModel):
    experience_id: str
    state_summary: str
    action: AgentAction
    outcome: str
    keywords: tuple[str, ...]
    positive: bool

    @classmethod
    def from_record(cls, record: ExperienceRecord) -> "ValidatedExperienceView":
        return cls(
            experience_id=record.experience_id,
            state_summary=record.state_summary,
            action=record.action,
            outcome=record.outcome,
            keywords=record.keywords,
            positive=record.positive,
        )


class ClassMemoryRecord(FrozenRuntimeModel):
    class_id: str = Field(min_length=1)
    label: str = Field(min_length=1)
    description: str = ""
    supporting_examples: tuple[str, ...] = ()

    @model_validator(mode="after")
    def validate_model_projection(self) -> "ClassMemoryRecord":
        validate_model_visible_value(self.description, location="class_memory.description")
        validate_model_visible_value(self.supporting_examples, location="class_memory.examples")
        return self


class EvidenceState(RuntimeModel):
    sample_id: str = Field(min_length=1)
    evidence: tuple[EvidenceItem, ...]
    traffic_expert_result: TrafficExpertResult
    traffic_expert_history: tuple[TrafficExpertResult, ...] = ()
    unknown_decision: UnknownDecision
    capabilities: tuple[CapabilityStatus, ...]
    budget: BudgetState
    round_index: int = Field(default=0, ge=0)
    request_history: tuple[str, ...] = ()
    action_history: tuple[AgentAction, ...] = ()
    tool_failures: tuple[FailureCode, ...] = ()
    retrieved_experiences: tuple[ExperienceRecord, ...] = ()

    @property
    def available_capabilities(self) -> frozenset[Capability]:
        return frozenset(item.capability for item in self.capabilities if item.available)

    def to_supervisor_view(self) -> "SupervisorView":
        view = SupervisorView(
            evidence=self.evidence,
            traffic_expert_result=self.traffic_expert_result,
            traffic_expert_history=self.traffic_expert_history,
            unknown_decision=self.unknown_decision,
            capabilities=self.capabilities,
            budget=BudgetView.from_state(self.budget),
            round_index=self.round_index,
            request_history=self.request_history,
            action_history=self.action_history,
            tool_failures=self.tool_failures,
            retrieved_experiences=tuple(
                ValidatedExperienceView.from_record(item) for item in self.retrieved_experiences
            ),
        )
        return view.model_copy(deep=True)


class SupervisorView(FrozenRuntimeModel):
    """Read-only, model-visible projection of internal runtime state."""

    evidence: tuple[EvidenceItem, ...]
    traffic_expert_result: TrafficExpertResult
    traffic_expert_history: tuple[TrafficExpertResult, ...]
    unknown_decision: UnknownDecision
    capabilities: tuple[CapabilityStatus, ...]
    budget: BudgetView
    round_index: int
    request_history: tuple[str, ...]
    action_history: tuple[AgentAction, ...]
    tool_failures: tuple[FailureCode, ...]
    retrieved_experiences: tuple[ValidatedExperienceView, ...]

    @property
    def available_capabilities(self) -> frozenset[Capability]:
        return frozenset(item.capability for item in self.capabilities if item.available)


class SupervisorDecision(FrozenRuntimeModel):
    action: AgentAction
    request: ToolRequest | None = None
    short_reason: str = Field(min_length=1, max_length=1000)
    priority: int | None = None
    expected_value: float | None = Field(default=None, allow_inf_nan=False)
    planned_actions: tuple[AgentAction, ...] = ()
    metrics: CallMetrics = Field(default_factory=CallMetrics)

    @field_validator("short_reason")
    @classmethod
    def validate_reason(cls, value: str) -> str:
        validate_model_visible_value(value, location="supervisor.short_reason")
        return value


class TraceEvent(FrozenRuntimeModel):
    step: int = Field(ge=0)
    round_index: int = Field(ge=0)
    event_type: TraceEventType
    summary: dict[str, Any] = Field(default_factory=dict)
    budget_before: dict[str, Any] | None = None
    budget_after: dict[str, Any] | None = None
    failure: FailureCode | None = None
    stop_reason: str | None = None


class FinalDecision(FrozenRuntimeModel):
    decision_type: FinalDecisionType
    action: AgentAction
    label: str | None = None
    reason: str = ""
    unknown_state: UnknownState


class RuntimeInput(FrozenRuntimeModel):
    sample_id: str = Field(min_length=1)
    initial_evidence: tuple[EvidenceItem, ...]
    capabilities: tuple[CapabilityStatus, ...]
    phase: RuntimePhase = RuntimePhase.TEST
    verified_feedback: VerifiedFeedback | None = None
    memory_query: str = ""

    @field_validator("memory_query")
    @classmethod
    def validate_memory_query(cls, value: str) -> str:
        validate_model_visible_value(value, location="runtime_input.memory_query")
        return value


class RuntimeResult(FrozenRuntimeModel):
    sample_id: str
    final_decision: FinalDecision
    final_state: EvidenceState | None
    trace: tuple[TraceEvent, ...]
    budget: BudgetView
    failures: tuple[FailureCode, ...] = ()
    memory_written: bool = False
