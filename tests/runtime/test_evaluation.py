from __future__ import annotations

from flowsec.runtime.backends import MockSupervisorBackend
from flowsec.runtime.contracts import AgentAction, EvidenceSufficiency, GapType
from flowsec.runtime.evaluation import summarize_runtime_results

from ._helpers import decision, expert_result, request, runtime, runtime_input


def test_evaluation_summarizes_decisions_calls_actions_and_resources() -> None:
    first = expert_result(sufficiency=EvidenceSufficiency.INSUFFICIENT, gap_type=GapType.PACKET)
    supervisor = MockSupervisorBackend(
        [
            decision(AgentAction.EXPAND_PACKETS, request(AgentAction.EXPAND_PACKETS, end=16)),
            decision(AgentAction.ACCEPT_FINE),
        ]
    )
    orchestrator, _, _ = runtime([first, expert_result()], supervisor)
    summary = summarize_runtime_results([orchestrator.run(runtime_input())])
    assert summary["sample_count"] == 1
    assert summary["fine_count"] == 1
    assert summary["tool_calls"] == 1
    assert summary["action_histogram"][AgentAction.EXPAND_PACKETS.value] >= 1


def test_evaluation_counts_unknown_abstain_failures_and_budget_events() -> None:
    reject_supervisor = MockSupervisorBackend([decision(AgentAction.REJECT_UNKNOWN)])
    reject_runtime, _, _ = runtime([expert_result(unknown_score=0.9)], reject_supervisor)
    unknown_result = reject_runtime.run(runtime_input(sample_id="unknown"))

    bad_supervisor = MockSupervisorBackend([object()])
    abstain_runtime, _, _ = runtime([expert_result()], bad_supervisor, max_invalid_retries=0)
    abstain_result = abstain_runtime.run(runtime_input(sample_id="abstain"))
    summary = summarize_runtime_results([unknown_result, abstain_result])
    assert summary["unknown_reject_count"] == 1
    assert summary["abstain_count"] == 1
    assert summary["supervisor_calls"] == 2
