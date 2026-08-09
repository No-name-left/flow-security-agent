from __future__ import annotations

import json

import pytest

from flowsec.runtime.backends import MockSupervisorBackend
from flowsec.runtime.contracts import (
    AgentAction,
    BudgetLimits,
    Capability,
    EvidenceSufficiency,
    FailureCode,
    FinalDecisionType,
    GapDomain,
    GapType,
    SupervisorDecision,
    ToolResult,
    ToolStatus,
    TraceEventType,
)
from flowsec.runtime.policies import DeterministicRuleSupervisor
from flowsec.runtime.tools import KnowledgeRetrievalTool, PacketExpansionTool

from ._helpers import (
    ACTION_GAP,
    capabilities,
    decision,
    default_tools,
    evidence,
    expert_result,
    request,
    runtime,
    runtime_input,
)


def test_initial_sufficient_accepts_fine() -> None:
    orchestrator, _, _ = runtime([expert_result()], DeterministicRuleSupervisor())
    result = orchestrator.run(runtime_input())
    assert result.final_decision.decision_type is FinalDecisionType.FINE
    assert result.final_decision.label == "known.attack"
    assert result.budget.tool_calls == 0


def test_fine_insufficient_coarse_sufficient_backs_off() -> None:
    response = expert_result(sufficiency=EvidenceSufficiency.COARSE_ONLY, fine_label=None)
    orchestrator, _, _ = runtime([response], DeterministicRuleSupervisor())
    result = orchestrator.run(runtime_input())
    assert result.final_decision.decision_type is FinalDecisionType.COARSE


def test_clear_unknown_rejects_unknown() -> None:
    response = expert_result(unknown_score=0.95, valuable=False)
    orchestrator, _, _ = runtime([response], DeterministicRuleSupervisor())
    result = orchestrator.run(runtime_input())
    assert result.final_decision.decision_type is FinalDecisionType.UNKNOWN


def test_unknown_likely_with_valuable_gap_continues_and_rescores() -> None:
    first = expert_result(
        sufficiency=EvidenceSufficiency.INSUFFICIENT,
        gap_type=GapType.PACKET,
        unknown_score=0.9,
    )
    second = expert_result(unknown_score=0.1)
    orchestrator, expert, unknown = runtime([first, second], DeterministicRuleSupervisor())
    result = orchestrator.run(runtime_input())
    assert result.final_decision.decision_type is FinalDecisionType.FINE
    assert len(expert.calls) == 2
    assert unknown.calls == 2


@pytest.mark.parametrize(
    ("action", "parameters"),
    [
        (AgentAction.EXPAND_PACKETS, {"start": 9, "end": 16}),
        (AgentAction.EXPAND_TEMPORAL_CONTEXT, {"window_seconds": 60, "past_only": True}),
        (AgentAction.EXPAND_GRAPH_CONTEXT, {"scope": "local_roles"}),
        (AgentAction.REQUEST_APPLICATION_EVIDENCE, {"protocol": "dns"}),
        (AgentAction.RETRIEVE_KNOWLEDGE, {"query": "attack boundary"}),
    ],
)
def test_each_evidence_action_uses_matching_tool_and_reevaluates(
    action: AgentAction,
    parameters: dict[str, object],
) -> None:
    gap_type, domain = ACTION_GAP[action]
    first = expert_result(
        sufficiency=EvidenceSufficiency.INSUFFICIENT,
        gap_type=gap_type,
        domain=domain,
    )
    supervisor = MockSupervisorBackend(
        [decision(action, request(action, **parameters)), decision(AgentAction.ACCEPT_FINE)]
    )
    tools = default_tools()
    orchestrator, expert, unknown = runtime([first, expert_result()], supervisor, tools=tools)
    result = orchestrator.run(runtime_input())
    selected_tool = next(tool for tool in tools if tool.action is action)
    assert len(selected_tool.requests) == 1
    assert result.budget.tool_calls == 1
    assert result.budget.rag_calls == (1 if action is AgentAction.RETRIEVE_KNOWLEDGE else 0)
    assert len(expert.calls) == 2
    assert unknown.calls == 2


def test_rag_cannot_answer_observational_gap() -> None:
    response = expert_result(
        sufficiency=EvidenceSufficiency.INSUFFICIENT,
        gap_type=GapType.PACKET,
        domain=GapDomain.OBSERVATIONAL,
    )
    supervisor = MockSupervisorBackend(
        [decision(AgentAction.RETRIEVE_KNOWLEDGE, request(AgentAction.RETRIEVE_KNOWLEDGE))]
    )
    orchestrator, _, _ = runtime([response], supervisor, max_invalid_retries=0)
    result = orchestrator.run(runtime_input())
    assert FailureCode.INVALID_ACTION in result.failures
    assert result.budget.rag_calls == 0
    assert result.final_decision.decision_type is FinalDecisionType.ABSTAIN


def test_multiple_missing_evidence_executes_only_first_planned_action() -> None:
    first = expert_result(sufficiency=EvidenceSufficiency.INSUFFICIENT, gap_type=GapType.PACKET)
    multi = SupervisorDecision(
        action=AgentAction.EXPAND_PACKETS,
        request=request(AgentAction.EXPAND_PACKETS, end=16),
        planned_actions=(
            AgentAction.EXPAND_TEMPORAL_CONTEXT,
            AgentAction.EXPAND_GRAPH_CONTEXT,
        ),
    )
    supervisor = MockSupervisorBackend([multi, decision(AgentAction.ACCEPT_FINE)])
    tools = default_tools()
    orchestrator, _, _ = runtime([first, expert_result()], supervisor, tools=tools)
    orchestrator.run(runtime_input())
    assert len(next(item for item in tools if item.action is AgentAction.EXPAND_PACKETS).requests) == 1
    assert len(next(item for item in tools if item.action is AgentAction.EXPAND_TEMPORAL_CONTEXT).requests) == 0


def test_same_tool_different_request_signatures_are_allowed() -> None:
    missing = expert_result(sufficiency=EvidenceSufficiency.INSUFFICIENT, gap_type=GapType.PACKET)
    supervisor = MockSupervisorBackend(
        [
            decision(AgentAction.EXPAND_PACKETS, request(AgentAction.EXPAND_PACKETS, start=9, end=16)),
            decision(AgentAction.EXPAND_PACKETS, request(AgentAction.EXPAND_PACKETS, start=17, end=24)),
            decision(AgentAction.ACCEPT_FINE),
        ]
    )
    tool = PacketExpansionTool(default_evidence=(evidence("more-packets", gap_type=GapType.PACKET),))
    orchestrator, _, _ = runtime([missing, missing, expert_result()], supervisor, tools=[tool])
    result = orchestrator.run(runtime_input())
    assert result.final_decision.decision_type is FinalDecisionType.FINE
    assert len(tool.requests) == 2
    assert len(set(result.final_state.request_history)) == 2  # type: ignore[union-attr]


def test_identical_request_is_rejected() -> None:
    missing = expert_result(sufficiency=EvidenceSufficiency.INSUFFICIENT, gap_type=GapType.PACKET)
    same = request(AgentAction.EXPAND_PACKETS, end=16)
    supervisor = MockSupervisorBackend(
        [
            decision(AgentAction.EXPAND_PACKETS, same),
            decision(AgentAction.EXPAND_PACKETS, same),
        ]
    )
    orchestrator, _, _ = runtime([missing, missing], supervisor, max_invalid_retries=0)
    result = orchestrator.run(runtime_input())
    assert FailureCode.REPEATED_REQUEST in result.failures
    assert result.budget.tool_calls == 1


def test_unavailable_capability_causes_safe_abstain() -> None:
    missing = expert_result(sufficiency=EvidenceSufficiency.INSUFFICIENT, gap_type=GapType.GRAPH)
    supervisor = MockSupervisorBackend(
        [decision(AgentAction.EXPAND_GRAPH_CONTEXT, request(AgentAction.EXPAND_GRAPH_CONTEXT))]
    )
    orchestrator, _, _ = runtime([missing], supervisor, max_invalid_retries=0)
    result = orchestrator.run(runtime_input(capabilities=capabilities(unavailable=Capability.GRAPH_CONTEXT)))
    assert FailureCode.CAPABILITY_UNAVAILABLE in result.failures
    assert result.final_decision.decision_type is FinalDecisionType.ABSTAIN


def test_tool_unavailable_updates_capability_and_stops_safely() -> None:
    missing = expert_result(sufficiency=EvidenceSufficiency.INSUFFICIENT, gap_type=GapType.PACKET)

    def unavailable(tool_request: object, current: object) -> ToolResult:
        return ToolResult(
            status=ToolStatus.UNAVAILABLE,
            request_signature=tool_request.signature,  # type: ignore[attr-defined]
            error="fixture unavailable",
        )

    tool = PacketExpansionTool(handler=unavailable)
    supervisor = MockSupervisorBackend(
        [decision(AgentAction.EXPAND_PACKETS, request(AgentAction.EXPAND_PACKETS, end=16))]
    )
    orchestrator, _, _ = runtime([missing], supervisor, tools=[tool], max_invalid_retries=0)
    result = orchestrator.run(runtime_input())
    assert FailureCode.CAPABILITY_UNAVAILABLE in result.failures
    assert Capability.PACKET_EXPANSION not in result.final_state.available_capabilities  # type: ignore[union-attr]


def test_tool_failure_is_recorded_and_stops_safely() -> None:
    missing = expert_result(sufficiency=EvidenceSufficiency.INSUFFICIENT, gap_type=GapType.PACKET)

    def failed(tool_request: object, current: object) -> ToolResult:
        return ToolResult(
            status=ToolStatus.FAILURE,
            request_signature=tool_request.signature,  # type: ignore[attr-defined]
            error="synthetic failure",
        )

    tool = PacketExpansionTool(handler=failed)
    supervisor = MockSupervisorBackend(
        [decision(AgentAction.EXPAND_PACKETS, request(AgentAction.EXPAND_PACKETS, end=16))]
    )
    orchestrator, _, _ = runtime([missing], supervisor, tools=[tool], max_invalid_retries=0)
    result = orchestrator.run(runtime_input())
    assert FailureCode.TOOL_FAILURE in result.failures
    assert result.final_state.tool_failures == (FailureCode.TOOL_FAILURE,)  # type: ignore[union-attr]


def test_tool_result_signature_mismatch_is_rejected() -> None:
    missing = expert_result(sufficiency=EvidenceSufficiency.INSUFFICIENT, gap_type=GapType.PACKET)

    def mismatched(tool_request: object, current: object) -> ToolResult:
        return ToolResult(status=ToolStatus.SUCCESS, request_signature="wrong-signature")

    tool = PacketExpansionTool(handler=mismatched)
    supervisor = MockSupervisorBackend(
        [decision(AgentAction.EXPAND_PACKETS, request(AgentAction.EXPAND_PACKETS, end=16))]
    )
    orchestrator, _, _ = runtime([missing], supervisor, tools=[tool])
    result = orchestrator.run(runtime_input())
    assert FailureCode.TOOL_FAILURE in result.failures


def test_rag_result_cannot_masquerade_as_observational_evidence() -> None:
    missing = expert_result(
        sufficiency=EvidenceSufficiency.INSUFFICIENT,
        gap_type=GapType.KNOWLEDGE,
        domain=GapDomain.KNOWLEDGE,
    )

    def wrong_domain(tool_request: object, current: object) -> ToolResult:
        return ToolResult(
            status=ToolStatus.SUCCESS,
            request_signature=tool_request.signature,  # type: ignore[attr-defined]
            evidence=(evidence("fake-packet", gap_type=GapType.PACKET),),
        )

    tool = KnowledgeRetrievalTool(handler=wrong_domain)
    supervisor = MockSupervisorBackend(
        [decision(AgentAction.RETRIEVE_KNOWLEDGE, request(AgentAction.RETRIEVE_KNOWLEDGE))]
    )
    orchestrator, _, _ = runtime([missing], supervisor, tools=[tool])
    result = orchestrator.run(runtime_input())
    assert FailureCode.UNSAFE_EVIDENCE in result.failures


def test_invalid_action_request_mismatch_is_rejected() -> None:
    missing = expert_result(sufficiency=EvidenceSufficiency.INSUFFICIENT, gap_type=GapType.PACKET)
    supervisor = MockSupervisorBackend(
        [
            decision(
                AgentAction.EXPAND_PACKETS,
                request(AgentAction.EXPAND_TEMPORAL_CONTEXT, window=60),
            )
        ]
    )
    orchestrator, _, _ = runtime([missing], supervisor, max_invalid_retries=0)
    result = orchestrator.run(runtime_input())
    assert FailureCode.INVALID_ACTION in result.failures


def test_repeated_invalid_supervisor_output_stops_safely() -> None:
    supervisor = MockSupervisorBackend([object(), object()])
    orchestrator, _, _ = runtime([expert_result()], supervisor, max_invalid_retries=1)
    result = orchestrator.run(runtime_input())
    assert result.failures.count(FailureCode.SUPERVISOR_OUTPUT_FAILURE) == 2
    assert result.final_decision.decision_type is FinalDecisionType.ABSTAIN


def test_supervisor_exception_is_a_safe_output_failure() -> None:
    supervisor = MockSupervisorBackend([RuntimeError("bad provider")])
    orchestrator, _, _ = runtime([expert_result()], supervisor, max_invalid_retries=0)
    result = orchestrator.run(runtime_input())
    assert FailureCode.SUPERVISOR_OUTPUT_FAILURE in result.failures


def test_tool_budget_exhaustion_abstains_before_execution() -> None:
    missing = expert_result(sufficiency=EvidenceSufficiency.INSUFFICIENT, gap_type=GapType.PACKET)
    supervisor = MockSupervisorBackend(
        [decision(AgentAction.EXPAND_PACKETS, request(AgentAction.EXPAND_PACKETS, end=16))]
    )
    budget = BudgetLimits(max_tool_calls=0, max_rag_calls=0)
    tools = default_tools()
    orchestrator, _, _ = runtime([missing], supervisor, tools=tools, budget=budget)
    result = orchestrator.run(runtime_input())
    assert FailureCode.BUDGET_EXHAUSTED in result.failures
    assert result.budget.tool_calls == 0


def test_max_rounds_stops_before_second_evidence_action() -> None:
    packet_missing = expert_result(
        sufficiency=EvidenceSufficiency.INSUFFICIENT,
        gap_type=GapType.PACKET,
    )
    temporal_missing = expert_result(
        sufficiency=EvidenceSufficiency.INSUFFICIENT,
        gap_type=GapType.TEMPORAL,
    )
    supervisor = MockSupervisorBackend(
        [
            decision(AgentAction.EXPAND_PACKETS, request(AgentAction.EXPAND_PACKETS, end=16)),
            decision(
                AgentAction.EXPAND_TEMPORAL_CONTEXT,
                request(AgentAction.EXPAND_TEMPORAL_CONTEXT, window=60),
            ),
        ]
    )
    orchestrator, _, _ = runtime(
        [packet_missing, temporal_missing],
        supervisor,
        budget=BudgetLimits(max_rounds=1),
    )
    result = orchestrator.run(runtime_input())
    assert FailureCode.MAX_ROUNDS_REACHED in result.failures
    assert result.budget.rounds == 1


def test_known_becomes_unknown_after_new_evidence() -> None:
    first = expert_result(
        sufficiency=EvidenceSufficiency.INSUFFICIENT,
        gap_type=GapType.PACKET,
        unknown_score=0.1,
    )
    second = expert_result(unknown_score=0.9, valuable=False)
    supervisor = MockSupervisorBackend(
        [
            decision(AgentAction.EXPAND_PACKETS, request(AgentAction.EXPAND_PACKETS, end=16)),
            decision(AgentAction.REJECT_UNKNOWN),
        ]
    )
    orchestrator, _, unknown = runtime([first, second], supervisor)
    result = orchestrator.run(runtime_input())
    assert unknown.calls == 2
    assert result.final_decision.decision_type is FinalDecisionType.UNKNOWN


def test_unknown_becomes_known_after_new_evidence() -> None:
    first = expert_result(
        sufficiency=EvidenceSufficiency.INSUFFICIENT,
        gap_type=GapType.PACKET,
        unknown_score=0.9,
    )
    second = expert_result(unknown_score=0.1)
    supervisor = MockSupervisorBackend(
        [
            decision(AgentAction.EXPAND_PACKETS, request(AgentAction.EXPAND_PACKETS, end=16)),
            decision(AgentAction.ACCEPT_FINE),
        ]
    )
    orchestrator, _, unknown = runtime([first, second], supervisor)
    result = orchestrator.run(runtime_input())
    assert unknown.calls == 2
    assert result.final_decision.decision_type is FinalDecisionType.FINE


def test_traffic_expert_failure_abstains_safely() -> None:
    supervisor = MockSupervisorBackend([])
    orchestrator, _, _ = runtime([RuntimeError("bad expert")], supervisor)
    result = orchestrator.run(runtime_input())
    assert FailureCode.TRAFFIC_EXPERT_OUTPUT_FAILURE in result.failures
    assert result.final_state is None


def test_model_unsafe_initial_evidence_is_rejected_before_model_call() -> None:
    supervisor = MockSupervisorBackend([])
    orchestrator, expert, _ = runtime([expert_result()], supervisor)
    result = orchestrator.run(runtime_input(initial_evidence=(evidence(model_safe=False),)))
    assert FailureCode.UNSAFE_EVIDENCE in result.failures
    assert expert.calls == []


def test_trace_is_complete_and_excludes_truth_or_raw_content() -> None:
    first = expert_result(sufficiency=EvidenceSufficiency.INSUFFICIENT, gap_type=GapType.PACKET)
    supervisor = MockSupervisorBackend(
        [
            decision(AgentAction.EXPAND_PACKETS, request(AgentAction.EXPAND_PACKETS, end=16)),
            decision(AgentAction.ACCEPT_FINE),
        ]
    )
    orchestrator, _, _ = runtime([first, expert_result()], supervisor)
    result = orchestrator.run(runtime_input())
    event_types = {event.event_type for event in result.trace}
    assert {
        TraceEventType.TRAFFIC_EXPERT,
        TraceEventType.UNKNOWN_SCORER,
        TraceEventType.SUPERVISOR,
        TraceEventType.TOOL,
        TraceEventType.FINAL,
    }.issubset(event_types)
    assert all(event.budget_before is not None and event.budget_after is not None for event in result.trace)
    serialized = json.dumps([item.model_dump(mode="json") for item in result.trace])
    assert "ground_truth" not in serialized
    assert "safe synthetic evidence" not in serialized
