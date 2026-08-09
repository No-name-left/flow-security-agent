from __future__ import annotations

from .contracts import (
    ACTION_CAPABILITY,
    AgentAction,
    CallMetrics,
    EvidenceSufficiency,
    GapType,
    SupervisorDecision,
    SupervisorView,
    ToolRequest,
    UnknownState,
)


DEFAULT_GAP_ACTIONS: dict[GapType, AgentAction] = {
    GapType.PACKET: AgentAction.EXPAND_PACKETS,
    GapType.TEMPORAL: AgentAction.EXPAND_TEMPORAL_CONTEXT,
    GapType.GRAPH: AgentAction.EXPAND_GRAPH_CONTEXT,
    GapType.APPLICATION: AgentAction.REQUEST_APPLICATION_EVIDENCE,
    GapType.KNOWLEDGE: AgentAction.RETRIEVE_KNOWLEDGE,
}


class DeterministicRuleSupervisor:
    """Configurable reproducible baseline, not the final learned Agent policy."""

    def __init__(
        self,
        gap_actions: dict[GapType, AgentAction] | None = None,
        request_parameters: dict[AgentAction, dict[str, object]] | None = None,
    ):
        self.gap_actions = dict(gap_actions or DEFAULT_GAP_ACTIONS)
        self.request_parameters = dict(request_parameters or {})

    def estimate(self, state: SupervisorView) -> CallMetrics:
        return CallMetrics()

    def decide(self, state: SupervisorView) -> SupervisorDecision:
        for gap in state.traffic_expert_result.missing_evidence:
            action = self.gap_actions.get(gap.gap_type)
            if not gap.valuable or action is None or action not in ACTION_CAPABILITY:
                continue
            if ACTION_CAPABILITY[action] not in state.available_capabilities:
                continue
            request = ToolRequest(
                action=action,
                parameters=self.request_parameters.get(action, {}),
            )
            if request.signature in state.request_history:
                continue
            return SupervisorDecision(
                action=action,
                request=request,
                short_reason=f"configured action for {gap.gap_type.value} gap",
            )

        result = state.traffic_expert_result
        if (
            state.unknown_decision.state is UnknownState.UNKNOWN_LIKELY
            and not any(item.valuable for item in result.missing_evidence)
        ):
            action = AgentAction.REJECT_UNKNOWN
        elif (
            state.unknown_decision.state is UnknownState.KNOWN_LIKELY
            and result.evidence_sufficiency is EvidenceSufficiency.SUFFICIENT
            and result.fine_candidates
        ):
            action = AgentAction.ACCEPT_FINE
        elif result.evidence_sufficiency is EvidenceSufficiency.COARSE_ONLY and result.coarse_candidates:
            action = AgentAction.BACKOFF_COARSE
        else:
            action = AgentAction.ABSTAIN
        return SupervisorDecision(action=action, short_reason="deterministic terminal rule")
