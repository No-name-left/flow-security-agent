from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from flowsec.runtime.backends import MockSupervisorBackend, MockTrafficExpertBackend
from flowsec.runtime.contracts import (
    AgentAction,
    CallMetrics,
    EvidenceSufficiency,
    EvidenceTrust,
    ExperienceRecord,
    FeedbackSource,
    FailureCode,
    FinalDecisionType,
    GapDomain,
    GapType,
    RuntimeInput,
    RuntimePhase,
    SupportingEvidence,
    SupervisorDecision,
    ToolResult,
    ToolStatus,
    UnknownDecision,
    UnknownState,
    VerifiedFeedback,
)
from flowsec.runtime.memory import InMemoryExperienceStore
from flowsec.runtime.orchestrator import RuntimeOrchestrator
from flowsec.runtime.tools import KnowledgeRetrievalTool, PacketExpansionTool

from ._helpers import (
    capabilities,
    decision,
    evidence,
    expert_result,
    request,
    runtime,
    runtime_input,
    synthetic_budget_limits,
)


@pytest.mark.parametrize(
    "unsafe_value",
    [
        {"dataset_id": "hidden"},
        {"capture_id": "capture-1"},
        {"backend_identity": "row-10"},
        {"raw_ip": "masked"},
    ],
)
def test_model_visible_evidence_rejects_backend_only_metadata(
    unsafe_value: dict[str, str],
) -> None:
    with pytest.raises(ValidationError, match="backend-only"):
        evidence().model_copy(update={"metadata": unsafe_value}).__class__.model_validate(
            {**evidence().model_dump(), "metadata": unsafe_value}
        )


@pytest.mark.parametrize(
    "unsafe_content",
    ["source 192.168.1.10", "observed 2026-08-09T12:30:00", "ground_truth=attack"],
)
def test_model_visible_evidence_rejects_raw_identity_text(unsafe_content: str) -> None:
    values = evidence().model_dump()
    values["content"] = unsafe_content
    with pytest.raises(ValidationError):
        evidence().__class__.model_validate(values)


def test_model_signals_and_unknown_metadata_reject_backend_identity() -> None:
    values = expert_result().model_dump()
    values["model_signals"] = {"backend_identity": "row-1"}
    with pytest.raises(ValidationError):
        expert_result().__class__.model_validate(values)
    with pytest.raises(ValidationError):
        UnknownDecision(
            score=0.5,
            state=UnknownState.UNCERTAIN,
            metadata={"capture_id": "capture-1"},
        )


def test_runtime_revalidates_bypassed_initial_evidence() -> None:
    crafted = evidence().model_copy(update={"metadata": {"capture_id": "hidden"}})
    supervisor = MockSupervisorBackend([])
    orchestrator, expert, _ = runtime([expert_result()], supervisor)
    crafted_input = runtime_input().model_copy(update={"initial_evidence": (crafted,)})
    result = orchestrator.run(crafted_input)
    assert FailureCode.UNSAFE_EVIDENCE in result.failures
    assert expert.calls == []


def test_runtime_revalidates_bypassed_traffic_expert_output() -> None:
    crafted = expert_result().model_copy(
        update={"model_signals": {"backend_identity": "hidden"}}
    )
    supervisor = MockSupervisorBackend([])
    orchestrator, _, _ = runtime([crafted], supervisor)
    result = orchestrator.run(runtime_input())
    assert FailureCode.TRAFFIC_EXPERT_OUTPUT_FAILURE in result.failures


def test_runtime_revalidates_bypassed_unknown_output() -> None:
    class UnsafeUnknown:
        def score(self, result: object, context: object) -> UnknownDecision:
            return UnknownDecision(
                state=UnknownState.UNCERTAIN,
                metadata={},
            ).model_copy(update={"metadata": {"dataset_id": "hidden"}})

    supervisor = MockSupervisorBackend([])
    orchestrator = RuntimeOrchestrator(
        traffic_expert=MockTrafficExpertBackend([expert_result()]),
        unknown_scorer=UnsafeUnknown(),
        supervisor=supervisor,
        budget_limits=synthetic_budget_limits(),
        memory_retrieval_limit=3,
    )
    result = orchestrator.run(runtime_input())
    assert FailureCode.UNKNOWN_SCORER_FAILURE in result.failures


def test_runtime_revalidates_bypassed_supervisor_output() -> None:
    crafted = decision(AgentAction.ACCEPT_FINE).model_copy(
        update={"short_reason": "ground_truth says accept"}
    )
    supervisor = MockSupervisorBackend([crafted])
    orchestrator, _, _ = runtime(
        [expert_result()],
        supervisor,
        max_invalid_retries=0,
    )
    result = orchestrator.run(runtime_input())
    assert FailureCode.SUPERVISOR_OUTPUT_FAILURE in result.failures


def test_runtime_revalidates_bypassed_tool_evidence() -> None:
    missing = expert_result(
        sufficiency=EvidenceSufficiency.INSUFFICIENT,
        gap_type=GapType.PACKET,
    )
    crafted = evidence("crafted", gap_type=GapType.PACKET).model_copy(
        update={"metadata": {"raw_ip": "hidden"}}
    )
    tool = PacketExpansionTool(default_evidence=(crafted,))
    supervisor = MockSupervisorBackend(
        [decision(AgentAction.EXPAND_PACKETS, request(AgentAction.EXPAND_PACKETS, end=16))]
    )
    orchestrator, _, _ = runtime([missing], supervisor, tools=[tool])
    result = orchestrator.run(runtime_input())
    assert FailureCode.TOOL_FAILURE in result.failures
    assert result.budget.rounds == 0


def test_memory_query_rejects_backend_only_identity() -> None:
    with pytest.raises(ValidationError):
        RuntimeInput(
            sample_id="sample",
            initial_evidence=(evidence(),),
            capabilities=capabilities(),
            memory_query="dataset_id hidden",
        )


def test_tool_request_rejects_raw_ip_parameter() -> None:
    with pytest.raises(ValidationError):
        request(AgentAction.EXPAND_GRAPH_CONTEXT, target="10.0.0.8")


def test_supervisor_view_excludes_sample_identity_and_raw_feedback() -> None:
    stored = ExperienceRecord(
        experience_id="verified-1",
        state_summary="packet evidence was insufficient",
        action=AgentAction.EXPAND_PACKETS,
        outcome="packet expansion improved classification",
        feedback=VerifiedFeedback(
            verified=True,
            source=FeedbackSource.GROUND_TRUTH,
            summary="ground_truth label was used only by the backend verifier",
            outcome_positive=True,
        ),
        keywords=("packet",),
    )
    memory = InMemoryExperienceStore([stored])
    supervisor = MockSupervisorBackend([decision(AgentAction.ACCEPT_FINE)])
    orchestrator, _, _ = runtime(
        [expert_result()],
        supervisor,
        experience_memory=memory,
    )
    orchestrator.run(runtime_input(memory_query="packet"))
    visible = supervisor.states[0].model_dump(mode="json")
    assert "sample_id" not in visible
    assert "feedback" not in visible["retrieved_experiences"][0]
    assert "ground_truth" not in json.dumps(visible)


def test_supervisor_view_is_frozen_and_cannot_change_runtime_budget() -> None:
    class MutatingSupervisor:
        def estimate(self, state: object) -> CallMetrics:
            return CallMetrics()

        def decide(self, state: object) -> SupervisorDecision:
            state.budget.rounds = 99  # type: ignore[attr-defined,misc]
            return decision(AgentAction.ACCEPT_FINE)

    orchestrator, _, _ = runtime(
        [expert_result()],
        MutatingSupervisor(),
        max_invalid_retries=0,
    )
    result = orchestrator.run(runtime_input())
    assert FailureCode.SUPERVISOR_OUTPUT_FAILURE in result.failures
    assert result.budget.rounds == 0


def test_nested_supervisor_mutation_cannot_alias_runtime_evidence() -> None:
    class NestedMutatingSupervisor:
        def estimate(self, state: object) -> CallMetrics:
            return CallMetrics()

        def decide(self, state: object) -> SupervisorDecision:
            state.evidence[0].metadata["fixture_mutation"] = True  # type: ignore[attr-defined]
            return decision(AgentAction.ACCEPT_FINE)

    orchestrator, _, _ = runtime([expert_result()], NestedMutatingSupervisor())
    result = orchestrator.run(runtime_input())
    assert result.final_state.evidence[0].metadata == {}  # type: ignore[union-attr]


def test_runtime_result_budget_is_an_immutable_detached_snapshot() -> None:
    supervisor = MockSupervisorBackend([decision(AgentAction.ACCEPT_FINE)])
    orchestrator, _, _ = runtime([expert_result()], supervisor)
    result = orchestrator.run(runtime_input())
    with pytest.raises(ValidationError):
        result.budget.rounds = 99  # type: ignore[misc]
    result.final_state.budget.rounds = 1  # type: ignore[union-attr]
    assert result.budget.rounds == 0


def test_traffic_expert_receives_detached_model_safe_evidence() -> None:
    class MutatingExpert:
        def estimate(self, visible_evidence: object) -> CallMetrics:
            return CallMetrics()

        def evaluate(self, visible_evidence: object) -> object:
            visible_evidence[0].metadata["fixture_mutation"] = True  # type: ignore[index]
            return expert_result()

    supervisor = MockSupervisorBackend([decision(AgentAction.ACCEPT_FINE)])
    orchestrator = RuntimeOrchestrator(
        traffic_expert=MutatingExpert(),
        unknown_scorer=runtime([expert_result()], supervisor)[2],
        supervisor=supervisor,
        budget_limits=synthetic_budget_limits(),
        memory_retrieval_limit=3,
    )
    result = orchestrator.run(runtime_input())
    assert result.final_state.evidence[0].metadata == {}  # type: ignore[union-attr]


def test_unvalidated_memory_retrieval_is_dropped_before_supervisor() -> None:
    unverified = ExperienceRecord(
        experience_id="bad-memory",
        state_summary="unverified state",
        action=AgentAction.ABSTAIN,
        outcome="unverified outcome",
        feedback=VerifiedFeedback(
            verified=False,
            source=FeedbackSource.VERIFIED_TOOL,
            summary="not actually verified",
            outcome_positive=False,
        ),
    )

    class UnsafeMemory:
        def retrieve(self, context: str, *, limit: int, filters: object = None) -> tuple[ExperienceRecord, ...]:
            return (unverified,)

        def add(self, item: ExperienceRecord) -> None:
            raise AssertionError("write not expected")

    supervisor = MockSupervisorBackend([decision(AgentAction.ACCEPT_FINE)])
    orchestrator, _, _ = runtime(
        [expert_result()],
        supervisor,
        experience_memory=UnsafeMemory(),
    )
    result = orchestrator.run(runtime_input())
    assert FailureCode.MEMORY_ACCESS_FAILURE in result.failures
    assert supervisor.states[0].retrieved_experiences == ()


@pytest.mark.parametrize(
    "malformed",
    [
        {"action": "invent_new_action", "short_reason": "invalid action"},
        {"action": AgentAction.ACCEPT_FINE.value},
        {
            "action": AgentAction.ACCEPT_FINE.value,
            "short_reason": "try to replace expert label",
            "final_fine_label": "invented.class",
        },
    ],
)
def test_malformed_or_label_creating_supervisor_outputs_are_rejected(
    malformed: dict[str, object],
) -> None:
    supervisor = MockSupervisorBackend([malformed])
    orchestrator, _, _ = runtime([expert_result()], supervisor, max_invalid_retries=0)
    result = orchestrator.run(runtime_input())
    assert FailureCode.SUPERVISOR_OUTPUT_FAILURE in result.failures
    assert result.final_decision.decision_type is FinalDecisionType.ABSTAIN


def test_terminal_action_cannot_carry_a_tool_request() -> None:
    bad = SupervisorDecision(
        action=AgentAction.ACCEPT_FINE,
        request=request(AgentAction.EXPAND_PACKETS, end=16),
        short_reason="terminal action with hidden continuation",
    )
    supervisor = MockSupervisorBackend([bad])
    orchestrator, _, _ = runtime([expert_result()], supervisor, max_invalid_retries=0)
    result = orchestrator.run(runtime_input())
    assert FailureCode.INVALID_ACTION in result.failures
    assert result.budget.tool_calls == 0


def test_future_temporal_context_request_is_rejected() -> None:
    missing = expert_result(
        sufficiency=EvidenceSufficiency.INSUFFICIENT,
        gap_type=GapType.TEMPORAL,
    )
    supervisor = MockSupervisorBackend(
        [
            decision(
                AgentAction.EXPAND_TEMPORAL_CONTEXT,
                request(
                    AgentAction.EXPAND_TEMPORAL_CONTEXT,
                    window=60,
                    past_only=False,
                    include_future=True,
                ),
            )
        ]
    )
    orchestrator, _, _ = runtime([missing], supervisor, max_invalid_retries=0)
    result = orchestrator.run(runtime_input())
    assert FailureCode.INVALID_ACTION in result.failures
    assert result.budget.tool_calls == 0


def test_request_parameter_allowlist_is_enforced_when_configured() -> None:
    missing = expert_result(
        sufficiency=EvidenceSufficiency.INSUFFICIENT,
        gap_type=GapType.PACKET,
    )
    supervisor = MockSupervisorBackend(
        [decision(AgentAction.EXPAND_PACKETS, request(AgentAction.EXPAND_PACKETS, end=32))]
    )
    orchestrator, _, _ = runtime(
        [missing],
        supervisor,
        max_invalid_retries=0,
        allowed_request_parameters={AgentAction.EXPAND_PACKETS: ({"end": 16},)},
    )
    result = orchestrator.run(runtime_input())
    assert FailureCode.INVALID_ACTION in result.failures
    assert result.budget.tool_calls == 0


def test_rag_must_preserve_untrusted_knowledge_evidence_type() -> None:
    missing = expert_result(
        sufficiency=EvidenceSufficiency.INSUFFICIENT,
        gap_type=GapType.KNOWLEDGE,
        domain=GapDomain.KNOWLEDGE,
    )
    trusted_knowledge = evidence(
        "knowledge-fixture",
        gap_type=GapType.KNOWLEDGE,
        domain=GapDomain.KNOWLEDGE,
        trust=EvidenceTrust.TRUSTED,
    )
    tool = KnowledgeRetrievalTool(default_evidence=(trusted_knowledge,))
    supervisor = MockSupervisorBackend(
        [decision(AgentAction.RETRIEVE_KNOWLEDGE, request(AgentAction.RETRIEVE_KNOWLEDGE))]
    )
    orchestrator, _, _ = runtime([missing], supervisor, tools=[tool])
    result = orchestrator.run(runtime_input())
    assert FailureCode.UNSAFE_EVIDENCE in result.failures


def test_unknown_likely_cannot_be_forced_to_accept_fine() -> None:
    supervisor = MockSupervisorBackend([decision(AgentAction.ACCEPT_FINE)])
    orchestrator, _, _ = runtime(
        [expert_result(unknown_score=0.95)],
        supervisor,
        max_invalid_retries=0,
    )
    result = orchestrator.run(runtime_input())
    assert FailureCode.INVALID_ACTION in result.failures
    assert result.final_decision.decision_type is FinalDecisionType.ABSTAIN


def test_insufficient_evidence_cannot_be_forced_to_accept_fine() -> None:
    response = expert_result(
        sufficiency=EvidenceSufficiency.INSUFFICIENT,
        gap_type=GapType.PACKET,
    )
    supervisor = MockSupervisorBackend([decision(AgentAction.ACCEPT_FINE)])
    orchestrator, _, _ = runtime([response], supervisor, max_invalid_retries=0)
    result = orchestrator.run(runtime_input())
    assert FailureCode.INVALID_ACTION in result.failures
    assert result.final_decision.decision_type is FinalDecisionType.ABSTAIN


def test_uncertain_insufficient_state_abstains_instead_of_becoming_unknown() -> None:
    response = expert_result(
        sufficiency=EvidenceSufficiency.INSUFFICIENT,
        fine_label=None,
        coarse_label=None,
        unknown_score=0.5,
    )
    from flowsec.runtime.policies import DeterministicRuleSupervisor

    orchestrator, _, _ = runtime([response], DeterministicRuleSupervisor())
    result = orchestrator.run(runtime_input())
    assert result.final_decision.decision_type is FinalDecisionType.ABSTAIN


def test_reason_is_audit_text_and_cannot_override_structured_action() -> None:
    supervisor = MockSupervisorBackend(
        [
            SupervisorDecision(
                action=AgentAction.REJECT_UNKNOWN,
                short_reason="accept fine despite this contradictory prose",
            )
        ]
    )
    orchestrator, _, _ = runtime([expert_result(unknown_score=0.95)], supervisor)
    result = orchestrator.run(runtime_input())
    assert result.final_decision.decision_type is FinalDecisionType.UNKNOWN
    assert result.final_decision.label is None


def test_tool_preflight_budget_blocks_execution() -> None:
    missing = expert_result(
        sufficiency=EvidenceSufficiency.INSUFFICIENT,
        gap_type=GapType.PACKET,
    )
    tool = PacketExpansionTool(estimate_metrics=CallMetrics(abstract_cost=2.0))
    supervisor = MockSupervisorBackend(
        [decision(AgentAction.EXPAND_PACKETS, request(AgentAction.EXPAND_PACKETS, end=16))]
    )
    orchestrator, _, _ = runtime(
        [missing],
        supervisor,
        tools=[tool],
        budget=synthetic_budget_limits(max_abstract_cost=1.0),
    )
    result = orchestrator.run(runtime_input())
    assert FailureCode.BUDGET_EXHAUSTED in result.failures
    assert tool.requests == []


def test_expert_preflight_budget_blocks_call() -> None:
    expert = MockTrafficExpertBackend(
        [expert_result()],
        estimate_metrics=CallMetrics(abstract_tokens=11),
    )
    supervisor = MockSupervisorBackend([decision(AgentAction.ACCEPT_FINE)])
    orchestrator = RuntimeOrchestrator(
        traffic_expert=expert,
        unknown_scorer=runtime([expert_result()], supervisor)[2],
        supervisor=supervisor,
        budget_limits=synthetic_budget_limits(max_abstract_tokens=10),
        memory_retrieval_limit=3,
    )
    result = orchestrator.run(runtime_input())
    assert FailureCode.BUDGET_EXHAUSTED in result.failures
    assert expert.calls == []


def test_supervisor_preflight_budget_blocks_call() -> None:
    supervisor = MockSupervisorBackend(
        [decision(AgentAction.ACCEPT_FINE)],
        estimate_metrics=CallMetrics(abstract_tokens=11),
    )
    orchestrator, _, _ = runtime(
        [expert_result()],
        supervisor,
        budget=synthetic_budget_limits(max_abstract_tokens=10),
    )
    result = orchestrator.run(runtime_input())
    assert FailureCode.BUDGET_EXHAUSTED in result.failures
    assert supervisor.states == []


def test_failed_expert_attempt_consumes_declared_preflight_budget() -> None:
    estimate = CallMetrics(abstract_tokens=3, abstract_cost=0.5)
    expert = MockTrafficExpertBackend([RuntimeError("fixture failure")], estimate_metrics=estimate)
    supervisor = MockSupervisorBackend([])
    orchestrator = RuntimeOrchestrator(
        traffic_expert=expert,
        unknown_scorer=runtime([expert_result()], supervisor)[2],
        supervisor=supervisor,
        budget_limits=synthetic_budget_limits(),
        memory_retrieval_limit=3,
    )
    result = orchestrator.run(runtime_input())
    assert result.budget.traffic_expert_calls == 1
    assert result.budget.abstract_tokens == 3
    assert result.budget.abstract_cost == 0.5


def test_successful_call_reconciles_preflight_reservation_to_actual_metrics() -> None:
    actual = CallMetrics(abstract_tokens=2, abstract_cost=0.25)
    response = expert_result().model_copy(update={"metrics": actual})
    expert = MockTrafficExpertBackend(
        [response],
        estimate_metrics=CallMetrics(abstract_tokens=5, abstract_cost=1.0),
    )
    supervisor = MockSupervisorBackend([decision(AgentAction.ACCEPT_FINE)])
    orchestrator = RuntimeOrchestrator(
        traffic_expert=expert,
        unknown_scorer=runtime([expert_result()], supervisor)[2],
        supervisor=supervisor,
        budget_limits=synthetic_budget_limits(),
        memory_retrieval_limit=3,
    )
    result = orchestrator.run(runtime_input())
    assert result.budget.traffic_expert_calls == 1
    assert result.budget.abstract_tokens == 2
    assert result.budget.abstract_cost == 0.25


def test_duplicate_tool_registration_is_rejected() -> None:
    supervisor = MockSupervisorBackend([decision(AgentAction.ACCEPT_FINE)])
    with pytest.raises(ValueError, match="unique"):
        RuntimeOrchestrator(
            traffic_expert=MockTrafficExpertBackend([expert_result()]),
            unknown_scorer=runtime([expert_result()], supervisor)[2],
            supervisor=supervisor,
            tools=[PacketExpansionTool(), PacketExpansionTool()],
            budget_limits=synthetic_budget_limits(),
            memory_retrieval_limit=3,
        )


def test_invalid_supervisor_retry_consumes_calls_but_not_rounds() -> None:
    supervisor = MockSupervisorBackend(
        [object(), object()],
        estimate_metrics=CallMetrics(abstract_tokens=2),
    )
    orchestrator, _, _ = runtime([expert_result()], supervisor, max_invalid_retries=1)
    result = orchestrator.run(runtime_input())
    assert result.budget.supervisor_calls == 2
    assert result.budget.abstract_tokens == 4
    assert result.budget.rounds == 0


def test_tool_failures_with_different_requests_still_terminate() -> None:
    missing = expert_result(
        sufficiency=EvidenceSufficiency.INSUFFICIENT,
        gap_type=GapType.PACKET,
    )

    def fail(tool_request: object, current: object) -> ToolResult:
        return ToolResult(
            status=ToolStatus.FAILURE,
            request_signature=tool_request.signature,  # type: ignore[attr-defined]
            error="fixture failure",
        )

    tool = PacketExpansionTool(handler=fail)
    supervisor = MockSupervisorBackend(
        [
            decision(AgentAction.EXPAND_PACKETS, request(AgentAction.EXPAND_PACKETS, end=12)),
            decision(AgentAction.EXPAND_PACKETS, request(AgentAction.EXPAND_PACKETS, end=16)),
            decision(AgentAction.EXPAND_PACKETS, request(AgentAction.EXPAND_PACKETS, end=20)),
        ]
    )
    orchestrator, _, _ = runtime(
        [missing],
        supervisor,
        tools=[tool],
        max_invalid_retries=1,
    )
    result = orchestrator.run(runtime_input())
    assert result.final_decision.decision_type is FinalDecisionType.ABSTAIN
    assert result.budget.tool_calls == 2
    assert len(tool.requests) == 2


def test_duplicate_evidence_does_not_grow_state_or_trigger_reclassification() -> None:
    missing = expert_result(
        sufficiency=EvidenceSufficiency.INSUFFICIENT,
        gap_type=GapType.PACKET,
    )
    tool = PacketExpansionTool(default_evidence=(evidence(),))
    supervisor = MockSupervisorBackend(
        [decision(AgentAction.EXPAND_PACKETS, request(AgentAction.EXPAND_PACKETS, end=16))]
    )
    orchestrator, expert, unknown = runtime(
        [missing],
        supervisor,
        tools=[tool],
        max_invalid_retries=0,
    )
    result = orchestrator.run(runtime_input())
    assert FailureCode.NO_STATE_CHANGE in result.failures
    assert len(result.final_state.evidence) == 1  # type: ignore[union-attr]
    assert result.budget.rounds == 0
    assert len(expert.calls) == 1
    assert unknown.calls == 1


def test_conflicting_reuse_of_evidence_id_is_rejected() -> None:
    missing = expert_result(
        sufficiency=EvidenceSufficiency.INSUFFICIENT,
        gap_type=GapType.PACKET,
    )
    conflicting = evidence().model_copy(update={"content": "different safe evidence"})
    tool = PacketExpansionTool(default_evidence=(conflicting,))
    supervisor = MockSupervisorBackend(
        [decision(AgentAction.EXPAND_PACKETS, request(AgentAction.EXPAND_PACKETS, end=16))]
    )
    orchestrator, _, _ = runtime([missing], supervisor, tools=[tool])
    result = orchestrator.run(runtime_input())
    assert FailureCode.UNSAFE_EVIDENCE in result.failures
    assert len(result.final_state.evidence) == 1  # type: ignore[union-attr]


def test_expert_history_preserves_support_and_missing_evidence_semantics() -> None:
    first = expert_result(
        sufficiency=EvidenceSufficiency.INSUFFICIENT,
        gap_type=GapType.PACKET,
    ).model_copy(
        update={
            "supporting_evidence": (
                SupportingEvidence(evidence_id="initial", statement="initial packet summary"),
            )
        }
    )
    second = expert_result().model_copy(
        update={
            "supporting_evidence": (
                SupportingEvidence(evidence_id="packet", statement="expanded packet summary"),
            )
        }
    )
    supervisor = MockSupervisorBackend(
        [
            decision(AgentAction.EXPAND_PACKETS, request(AgentAction.EXPAND_PACKETS, end=16)),
            decision(AgentAction.ACCEPT_FINE),
        ]
    )
    orchestrator, _, _ = runtime([first, second], supervisor)
    result = orchestrator.run(runtime_input())
    history = result.final_state.traffic_expert_history  # type: ignore[union-attr]
    assert len(history) == 2
    assert history[0].missing_evidence[0].gap_type is GapType.PACKET
    assert history[0].supporting_evidence[0].evidence_id == "initial"
    assert history[1].missing_evidence == ()
    assert history[1].supporting_evidence[0].evidence_id == "packet"


def test_identical_runs_are_fully_deterministic() -> None:
    def execute() -> dict[str, object]:
        first = expert_result(
            sufficiency=EvidenceSufficiency.INSUFFICIENT,
            gap_type=GapType.PACKET,
        )
        supervisor = MockSupervisorBackend(
            [
                decision(
                    AgentAction.EXPAND_PACKETS,
                    request(AgentAction.EXPAND_PACKETS, end=16),
                ),
                decision(AgentAction.ACCEPT_FINE),
            ]
        )
        orchestrator, _, _ = runtime([first, expert_result()], supervisor)
        return orchestrator.run(runtime_input()).model_dump(mode="json")

    assert execute() == execute()


def test_unique_valid_actions_cannot_bypass_max_rounds() -> None:
    missing = expert_result(
        sufficiency=EvidenceSufficiency.INSUFFICIENT,
        gap_type=GapType.PACKET,
    )

    def unique_evidence(tool_request: object, current: object) -> ToolResult:
        end = tool_request.parameters["end"]  # type: ignore[attr-defined]
        return ToolResult(
            status=ToolStatus.SUCCESS,
            request_signature=tool_request.signature,  # type: ignore[attr-defined]
            evidence=(evidence(f"packet-{end}", gap_type=GapType.PACKET),),
        )

    requests = [
        decision(AgentAction.EXPAND_PACKETS, request(AgentAction.EXPAND_PACKETS, end=end))
        for end in (10, 12, 14, 16, 18)
    ]
    supervisor = MockSupervisorBackend(requests)
    tool = PacketExpansionTool(handler=unique_evidence)
    orchestrator, expert, unknown = runtime(
        [missing, missing, missing],
        supervisor,
        tools=[tool],
        budget=synthetic_budget_limits(max_rounds=2),
    )
    result = orchestrator.run(runtime_input())
    assert FailureCode.MAX_ROUNDS_REACHED in result.failures
    assert result.budget.rounds == 2
    assert len(expert.calls) == 3
    assert unknown.calls == 3
