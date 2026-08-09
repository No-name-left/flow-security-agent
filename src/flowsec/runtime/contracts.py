from __future__ import annotations

import hashlib
import json
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


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
    UNSAFE_EVIDENCE = "unsafe_evidence"


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
    score: float | None = None


class SupportingEvidence(FrozenRuntimeModel):
    evidence_id: str = Field(min_length=1)
    statement: str = Field(min_length=1)


class MissingEvidence(FrozenRuntimeModel):
    description: str = Field(min_length=1)
    gap_type: GapType
    domain: GapDomain
    valuable: bool = True

    @model_validator(mode="after")
    def validate_domain(self) -> "MissingEvidence":
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


class TrafficExpertResult(FrozenRuntimeModel):
    fine_candidates: tuple[PredictionCandidate, ...] = ()
    coarse_candidates: tuple[PredictionCandidate, ...] = ()
    short_analysis: str = ""
    supporting_evidence: tuple[SupportingEvidence, ...] = ()
    missing_evidence: tuple[MissingEvidence, ...] = ()
    evidence_sufficiency: EvidenceSufficiency
    model_signals: dict[str, Any] = Field(default_factory=dict)
    metrics: CallMetrics = Field(default_factory=CallMetrics)


class UnknownDecision(FrozenRuntimeModel):
    score: float | None = None
    state: UnknownState
    metadata: dict[str, Any] = Field(default_factory=dict)


class CapabilityStatus(FrozenRuntimeModel):
    capability: Capability
    available: bool = True
    reason: str | None = None


class BudgetLimits(FrozenRuntimeModel):
    max_rounds: int = Field(default=3, ge=0)
    max_traffic_expert_calls: int = Field(default=4, ge=1)
    max_supervisor_calls: int = Field(default=8, ge=1)
    max_tool_calls: int = Field(default=3, ge=0)
    max_rag_calls: int = Field(default=1, ge=0)
    max_abstract_tokens: int = Field(default=100_000, ge=0)
    max_abstract_cost: float = Field(default=100.0, ge=0)
    max_abstract_latency: float = Field(default=100_000.0, ge=0)


class BudgetState(RuntimeModel):
    limits: BudgetLimits = Field(default_factory=BudgetLimits)
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


class ToolRequest(FrozenRuntimeModel):
    action: AgentAction
    parameters: dict[str, Any] = Field(default_factory=dict)

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
    source: str = Field(min_length=1)
    summary: str = Field(min_length=1)


class ExperienceRecord(FrozenRuntimeModel):
    experience_id: str = Field(min_length=1)
    state_summary: str = Field(min_length=1)
    action: AgentAction
    outcome: str = Field(min_length=1)
    feedback: VerifiedFeedback
    keywords: tuple[str, ...] = ()
    positive: bool = True


class ClassMemoryRecord(FrozenRuntimeModel):
    class_id: str = Field(min_length=1)
    label: str = Field(min_length=1)
    description: str = ""
    supporting_examples: tuple[str, ...] = ()


class EvidenceState(RuntimeModel):
    sample_id: str = Field(min_length=1)
    evidence: tuple[EvidenceItem, ...]
    traffic_expert_result: TrafficExpertResult
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


class SupervisorDecision(FrozenRuntimeModel):
    action: AgentAction
    request: ToolRequest | None = None
    short_reason: str = ""
    priority: int | None = None
    expected_value: float | None = None
    planned_actions: tuple[AgentAction, ...] = ()
    metrics: CallMetrics = Field(default_factory=CallMetrics)


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


class RuntimeResult(FrozenRuntimeModel):
    sample_id: str
    final_decision: FinalDecision
    final_state: EvidenceState | None
    trace: tuple[TraceEvent, ...]
    budget: BudgetState
    failures: tuple[FailureCode, ...] = ()
    memory_written: bool = False
