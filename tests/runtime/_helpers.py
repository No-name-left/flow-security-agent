from __future__ import annotations

from flowsec.runtime.backends import (
    DeterministicTestUnknownScorer,
    MockSupervisorBackend,
    MockTrafficExpertBackend,
)
from flowsec.runtime.contracts import (
    ACTION_CAPABILITY,
    AgentAction,
    BudgetLimits,
    Capability,
    CapabilityStatus,
    EvidenceItem,
    EvidenceSufficiency,
    GapDomain,
    GapType,
    MissingEvidence,
    PredictionCandidate,
    RuntimeInput,
    SupervisorDecision,
    ToolRequest,
    TrafficExpertResult,
)
from flowsec.runtime.orchestrator import RuntimeOrchestrator
from flowsec.runtime.tools import (
    ApplicationEvidenceTool,
    GraphContextTool,
    KnowledgeRetrievalTool,
    PacketExpansionTool,
    TemporalContextTool,
)


ACTION_GAP = {
    AgentAction.EXPAND_PACKETS: (GapType.PACKET, GapDomain.OBSERVATIONAL),
    AgentAction.EXPAND_TEMPORAL_CONTEXT: (GapType.TEMPORAL, GapDomain.OBSERVATIONAL),
    AgentAction.EXPAND_GRAPH_CONTEXT: (GapType.GRAPH, GapDomain.OBSERVATIONAL),
    AgentAction.REQUEST_APPLICATION_EVIDENCE: (GapType.APPLICATION, GapDomain.OBSERVATIONAL),
    AgentAction.RETRIEVE_KNOWLEDGE: (GapType.KNOWLEDGE, GapDomain.KNOWLEDGE),
}


def evidence(
    evidence_id: str = "initial",
    *,
    gap_type: GapType = GapType.OTHER,
    domain: GapDomain = GapDomain.OBSERVATIONAL,
    model_safe: bool = True,
) -> EvidenceItem:
    return EvidenceItem(
        evidence_id=evidence_id,
        gap_type=gap_type,
        domain=domain,
        content=f"safe synthetic evidence {evidence_id}",
        provenance="synthetic_fixture",
        model_safe=model_safe,
    )


def expert_result(
    *,
    sufficiency: EvidenceSufficiency = EvidenceSufficiency.SUFFICIENT,
    gap_type: GapType | None = None,
    domain: GapDomain | None = None,
    valuable: bool = True,
    fine_label: str | None = "known.attack",
    coarse_label: str | None = "malicious",
    unknown_score: float = 0.1,
) -> TrafficExpertResult:
    missing = ()
    if gap_type is not None:
        if domain is None:
            domain = GapDomain.KNOWLEDGE if gap_type is GapType.KNOWLEDGE else GapDomain.OBSERVATIONAL
        missing = (
            MissingEvidence(
                description=f"need {gap_type.value}",
                gap_type=gap_type,
                domain=domain,
                valuable=valuable,
            ),
        )
    return TrafficExpertResult(
        fine_candidates=(PredictionCandidate(label=fine_label, score=0.8),) if fine_label else (),
        coarse_candidates=(PredictionCandidate(label=coarse_label, score=0.9),) if coarse_label else (),
        short_analysis="synthetic",
        missing_evidence=missing,
        evidence_sufficiency=sufficiency,
        model_signals={"unknown_score": unknown_score},
    )


def capabilities(*, unavailable: Capability | None = None) -> tuple[CapabilityStatus, ...]:
    return tuple(
        CapabilityStatus(capability=item, available=item is not unavailable)
        for item in Capability
    )


def request(action: AgentAction, **parameters: object) -> ToolRequest:
    return ToolRequest(action=action, parameters=parameters)


def decision(action: AgentAction, tool_request: ToolRequest | None = None) -> SupervisorDecision:
    return SupervisorDecision(action=action, request=tool_request, short_reason="synthetic decision")


def default_tools() -> list[object]:
    return [
        PacketExpansionTool(default_evidence=(evidence("packet", gap_type=GapType.PACKET),)),
        TemporalContextTool(default_evidence=(evidence("temporal", gap_type=GapType.TEMPORAL),)),
        GraphContextTool(default_evidence=(evidence("graph", gap_type=GapType.GRAPH),)),
        ApplicationEvidenceTool(default_evidence=(evidence("application", gap_type=GapType.APPLICATION),)),
        KnowledgeRetrievalTool(
            default_evidence=(
                evidence("knowledge", gap_type=GapType.KNOWLEDGE, domain=GapDomain.KNOWLEDGE),
            )
        ),
    ]


def runtime(
    expert_responses: list[TrafficExpertResult | Exception],
    supervisor: object,
    *,
    tools: list[object] | None = None,
    budget: BudgetLimits | None = None,
    **kwargs: object,
) -> tuple[RuntimeOrchestrator, MockTrafficExpertBackend, DeterministicTestUnknownScorer]:
    expert = MockTrafficExpertBackend(expert_responses)
    unknown = DeterministicTestUnknownScorer()
    orchestrator = RuntimeOrchestrator(
        traffic_expert=expert,
        unknown_scorer=unknown,
        supervisor=supervisor,  # type: ignore[arg-type]
        tools=default_tools() if tools is None else tools,  # type: ignore[arg-type]
        budget_limits=budget,
        **kwargs,
    )
    return orchestrator, expert, unknown


def runtime_input(**kwargs: object) -> RuntimeInput:
    values = {
        "sample_id": "sample-1",
        "initial_evidence": (evidence(),),
        "capabilities": capabilities(),
    }
    values.update(kwargs)
    return RuntimeInput.model_validate(values)
