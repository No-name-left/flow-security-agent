from __future__ import annotations

import json

import pytest

from flowsec.integrations.llm.adapters import LLMTrafficExpertBackend
from flowsec.integrations.llm.contracts import (
    LLMBackendError,
    LLMFailureKind,
    RawLLMResponse,
    RawUsage,
    ResponseMode,
)
from flowsec.integrations.llm.prompting import (
    TrafficExpertPromptRenderer,
    fixture_traffic_expert_prompt,
)
from flowsec.integrations.llm.parsing import FixtureTrafficExpertResponseParserV0
from flowsec.integrations.llm.transport import (
    FakeFailure,
    FakeLLMTransport,
    FixtureProviderAProfile,
)
from flowsec.runtime.backends import DeterministicTestUnknownScorer, MockSupervisorBackend
from flowsec.runtime.contracts import CallMetrics, FailureCode
from flowsec.runtime.orchestrator import RuntimeOrchestrator
from tests.runtime._helpers import evidence, runtime_input, synthetic_budget_limits

from ._helpers import (
    config,
    envelope_a,
    envelope_b,
    expert_backend,
    expert_payload,
    fake_transport,
)


SECRET = "SUPER_SECRET_TEST_KEY_123"


def test_two_provider_envelopes_map_to_same_traffic_expert_contract() -> None:
    transport_a = fake_transport("provider_a", [envelope_a(expert_payload())])
    transport_b = fake_transport("provider_b", [envelope_b(expert_payload())])
    result_a = expert_backend(transport_a, provider="provider_a").evaluate((evidence(),))
    result_b = expert_backend(transport_b, provider="provider_b").evaluate((evidence(),))

    assert result_a.model_dump(exclude={"metrics"}) == result_b.model_dump(exclude={"metrics"})
    assert result_a.metrics == result_b.metrics


def test_retry_is_bounded_and_accumulates_conservative_failure_usage() -> None:
    transport = fake_transport(
        "provider_a",
        [
            FakeFailure(LLMFailureKind.TIMEOUT, "fixture timeout"),
            envelope_a(expert_payload()),
        ],
    )
    backend = expert_backend(
        transport,
        attempts=2,
        retryable=frozenset({LLMFailureKind.TIMEOUT}),
    )

    estimate = backend.estimate((evidence(),))
    result = backend.evaluate((evidence(),))

    assert estimate.abstract_tokens == 40
    assert result.metrics.abstract_tokens == 30
    assert result.metrics.abstract_cost == pytest.approx(1.1)
    assert result.metrics.abstract_latency == pytest.approx(2.2)
    assert len(transport.requests) == 2
    assert backend.last_call_audit is not None
    assert [item.failure for item in backend.last_call_audit.attempts] == [
        LLMFailureKind.TIMEOUT,
        None,
    ]


def test_non_retryable_failure_stops_after_one_attempt() -> None:
    transport = fake_transport(
        "provider_a",
        [
            FakeFailure(LLMFailureKind.RATE_LIMIT_LIKE_FAILURE, "rate-like"),
            envelope_a(expert_payload()),
        ],
    )
    backend = expert_backend(transport, attempts=3, retryable=frozenset())
    with pytest.raises(LLMBackendError) as captured:
        backend.evaluate((evidence(),))
    assert captured.value.kind is LLMFailureKind.RATE_LIMIT_LIKE_FAILURE
    assert captured.value.attempts == 1
    assert len(transport.requests) == 1


def test_runtime_budget_blocks_transport_before_any_send() -> None:
    transport = fake_transport("provider_a", [envelope_a(expert_payload())])
    backend = expert_backend(transport, attempts=2)
    runtime = RuntimeOrchestrator(
        traffic_expert=backend,
        unknown_scorer=DeterministicTestUnknownScorer(known_max=0.3, unknown_min=0.7),
        supervisor=MockSupervisorBackend([]),
        budget_limits=synthetic_budget_limits(max_abstract_tokens=39),
        memory_retrieval_limit=0,
    )

    result = runtime.run(runtime_input())
    assert result.failures == (FailureCode.BUDGET_EXHAUSTED,)
    assert transport.requests == []
    assert transport.estimate_requests


def test_successful_runtime_reconciles_reservation_downward() -> None:
    from tests.runtime._helpers import decision
    from flowsec.runtime.contracts import AgentAction

    transport = fake_transport("provider_a", [envelope_a(expert_payload())])
    runtime = RuntimeOrchestrator(
        traffic_expert=expert_backend(transport),
        unknown_scorer=DeterministicTestUnknownScorer(known_max=0.3, unknown_min=0.7),
        supervisor=MockSupervisorBackend([decision(AgentAction.ACCEPT_FINE)]),
        budget_limits=synthetic_budget_limits(),
        memory_retrieval_limit=0,
    )
    result = runtime.run(runtime_input())
    assert result.budget.abstract_tokens == 10
    assert result.budget.abstract_cost == pytest.approx(0.1)
    assert result.budget.abstract_latency == pytest.approx(0.2)


def test_failed_runtime_keeps_full_backend_reservation() -> None:
    transport = fake_transport(
        "provider_a",
        [
            FakeFailure(LLMFailureKind.TIMEOUT, "one"),
            FakeFailure(LLMFailureKind.TIMEOUT, "two"),
        ],
    )
    runtime = RuntimeOrchestrator(
        traffic_expert=expert_backend(
            transport,
            attempts=2,
            retryable=frozenset({LLMFailureKind.TIMEOUT}),
        ),
        unknown_scorer=DeterministicTestUnknownScorer(known_max=0.3, unknown_min=0.7),
        supervisor=MockSupervisorBackend([]),
        budget_limits=synthetic_budget_limits(),
        memory_retrieval_limit=0,
    )
    result = runtime.run(runtime_input())
    assert result.budget.abstract_tokens == 40
    assert FailureCode.TRAFFIC_EXPERT_OUTPUT_FAILURE in result.failures
    assert len(transport.requests) == 2


def test_secret_is_absent_from_exception_repr_audit_and_runtime_trace() -> None:
    transport = FakeLLMTransport(
        profile=FixtureProviderAProfile(),
        events=[RuntimeError(f"authorization failed for {SECRET}")],
        estimate_metrics=CallMetrics(abstract_tokens=20, abstract_cost=1.0),
        secret_values=(SECRET,),
    )
    backend = expert_backend(transport, secret_values=(SECRET,))
    with pytest.raises(LLMBackendError) as captured:
        backend.evaluate((evidence(),))
    serialized = json.dumps(
        {
            "exception": repr(captured.value),
            "transport": repr(transport),
            "audit": backend.last_call_audit.model_dump(mode="json")
            if backend.last_call_audit
            else {},
        },
        sort_keys=True,
    )
    assert SECRET not in serialized
    assert "[REDACTED]" in repr(captured.value)


def test_secret_is_absent_from_runtime_result_and_trace() -> None:
    transport = FakeLLMTransport(
        profile=FixtureProviderAProfile(),
        events=[RuntimeError(f"timeout using {SECRET}")],
        estimate_metrics=CallMetrics(abstract_tokens=20),
        secret_values=(SECRET,),
    )
    runtime = RuntimeOrchestrator(
        traffic_expert=expert_backend(transport, secret_values=(SECRET,)),
        unknown_scorer=DeterministicTestUnknownScorer(known_max=0.3, unknown_min=0.7),
        supervisor=MockSupervisorBackend([]),
        budget_limits=synthetic_budget_limits(),
        memory_retrieval_limit=0,
    )
    result = runtime.run(runtime_input())
    assert SECRET not in result.model_dump_json()
    assert SECRET not in repr(result)


def test_provider_metadata_is_backend_only_and_never_reaches_result() -> None:
    transport = fake_transport(
        "provider_a",
        [envelope_a(expert_payload(), metadata={"authorization": SECRET, "ground_truth": "x"})],
    )
    result = expert_backend(transport).evaluate((evidence(),))
    assert SECRET not in result.model_dump_json()
    assert "ground_truth" not in result.model_dump_json()


class MutatingTransport:
    def __init__(self):
        self.seen = None

    def estimate(self, request):
        return CallMetrics(abstract_tokens=20)

    def send(self, request):
        request.generation_options["mutated_by_transport"] = True
        self.seen = request
        return RawLLMResponse(
            structured_payload=expert_payload(),
            usage=RawUsage(total_tokens=10),
            provider=request.provider,
            model_id=request.model_id,
        )


def test_transport_cannot_mutate_caller_configuration_or_future_requests() -> None:
    transport = MutatingTransport()
    backend = LLMTrafficExpertBackend(
        transport=transport,
        config=config("expert"),
        renderer=TrafficExpertPromptRenderer(fixture_traffic_expert_prompt()),
        parser=FixtureTrafficExpertResponseParserV0(),
    )
    backend.evaluate((evidence(),))
    assert "mutated_by_transport" not in backend.config.generation_options
    backend.estimate((evidence(),))
    assert "mutated_by_transport" not in backend.config.generation_options


class FailingEstimateTransport:
    def estimate(self, request):
        raise RuntimeError(f"estimate exposed {SECRET}")

    def send(self, request):
        raise AssertionError("send must not run after estimate failure")


def test_transport_estimate_exception_is_redacted_and_blocks_send() -> None:
    backend = LLMTrafficExpertBackend(
        transport=FailingEstimateTransport(),
        config=config("expert"),
        renderer=TrafficExpertPromptRenderer(fixture_traffic_expert_prompt()),
        parser=FixtureTrafficExpertResponseParserV0(),
        secret_values=(SECRET,),
    )
    with pytest.raises(Exception) as captured:
        backend.estimate((evidence(),))
    assert SECRET not in repr(captured.value)
    assert getattr(captured.value, "kind") is LLMFailureKind.TRANSPORT_FAILURE


def test_malformed_response_is_retried_only_when_explicitly_configured() -> None:
    transport = fake_transport(
        "provider_a",
        [envelope_a("{broken"), envelope_a(expert_payload())],
    )
    backend = expert_backend(
        transport,
        attempts=2,
        retryable=frozenset({LLMFailureKind.MALFORMED_RESPONSE}),
    )
    result = backend.evaluate((evidence(),))
    assert result.fine_candidates[0].label == "fixture.attack"
    assert len(transport.requests) == 2
    assert result.metrics.abstract_tokens == 20


def test_response_usage_above_estimate_forces_stop_without_retry() -> None:
    oversized = envelope_a(
        expert_payload(),
        usage={"input_tokens": 10, "output_tokens": 20, "total_tokens": 30},
    )
    transport = fake_transport(
        "provider_a",
        [oversized, envelope_a(expert_payload())],
        tokens=20,
    )
    backend = expert_backend(
        transport,
        attempts=2,
        retryable=frozenset({LLMFailureKind.UNSUPPORTED_RESPONSE}),
    )
    with pytest.raises(LLMBackendError) as captured:
        backend.evaluate((evidence(),))
    assert captured.value.kind is LLMFailureKind.UNSUPPORTED_RESPONSE
    assert len(transport.requests) == 1


@pytest.mark.parametrize(
    ("mode", "event"),
    [
        (ResponseMode.STRUCTURED, envelope_a(expert_payload())),
        (
            ResponseMode.TEXT,
            {
                "id": "fixture",
                "structured": expert_payload(),
                "usage": {"total_tokens": 10},
                "finish_status": "stop",
            },
        ),
    ],
)
def test_response_mode_mismatch_is_explicit(mode: ResponseMode, event: dict[str, object]) -> None:
    transport = fake_transport("provider_a", [event])
    configured = config("expert").model_copy(update={"response_mode": mode})
    backend = LLMTrafficExpertBackend(
        transport=transport,
        config=configured,
        renderer=TrafficExpertPromptRenderer(fixture_traffic_expert_prompt()),
        parser=FixtureTrafficExpertResponseParserV0(),
    )
    with pytest.raises(LLMBackendError) as captured:
        backend.evaluate((evidence(),))
    assert captured.value.kind is LLMFailureKind.UNSUPPORTED_RESPONSE


def test_bypassed_unsafe_evidence_is_revalidated_before_transport() -> None:
    transport = fake_transport("provider_a", [envelope_a(expert_payload())])
    backend = expert_backend(transport)
    unsafe = evidence().model_copy()
    object.__setattr__(unsafe, "metadata", {"ground_truth": "fixture.attack"})
    with pytest.raises(Exception):
        backend.evaluate((unsafe,))
    assert transport.requests == []


class TamperedParser:
    profile_id = "SYNTHETIC_TAMPERED_PARSER"

    def parse(self, response):
        from flowsec.integrations.llm.contracts import ParseAudit
        from flowsec.runtime.contracts import EvidenceSufficiency, TrafficExpertResult

        result = TrafficExpertResult.model_construct(
            fine_candidates=(),
            coarse_candidates=(),
            short_analysis="raw identity 192.0.2.10",
            supporting_evidence=(),
            missing_evidence=(),
            evidence_sufficiency=EvidenceSufficiency.INSUFFICIENT,
            model_signals={},
            metrics=CallMetrics(),
        )
        return result, ParseAudit(parser_profile_id=self.profile_id)


def test_adapter_revalidates_a_tampered_parser_object() -> None:
    transport = fake_transport("provider_a", [envelope_a(expert_payload())])
    backend = LLMTrafficExpertBackend(
        transport=transport,
        config=config("expert"),
        renderer=TrafficExpertPromptRenderer(fixture_traffic_expert_prompt()),
        parser=TamperedParser(),  # type: ignore[arg-type]
    )
    with pytest.raises(LLMBackendError) as captured:
        backend.evaluate((evidence(),))
    assert captured.value.kind is LLMFailureKind.UNSUPPORTED_RESPONSE
