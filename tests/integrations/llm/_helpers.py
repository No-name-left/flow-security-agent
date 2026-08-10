from __future__ import annotations

import json
from typing import Any

from flowsec.integrations.llm.adapters import LLMSupervisorBackend, LLMTrafficExpertBackend
from flowsec.integrations.llm.contracts import (
    LLMBackendConfig,
    LLMFailureKind,
    ResponseMode,
    RetryPolicy,
)
from flowsec.integrations.llm.parsing import (
    FixtureSupervisorResponseParserV0,
    FixtureTrafficExpertResponseParserV0,
)
from flowsec.integrations.llm.prompting import (
    SupervisorPromptRenderer,
    ToolSpecification,
    TrafficExpertPromptRenderer,
    fixture_supervisor_prompt,
    fixture_traffic_expert_prompt,
)
from flowsec.integrations.llm.transport import (
    FakeLLMTransport,
    FixtureProviderAProfile,
    FixtureProviderBProfile,
)
from flowsec.runtime.contracts import AgentAction, CallMetrics


def expert_payload(
    *,
    fine_label: str = "fixture.attack",
    sufficiency: str = "sufficient",
    gap: str | None = None,
    unknown_signal: float = 0.1,
) -> dict[str, Any]:
    missing: list[dict[str, Any]] = []
    if gap is not None:
        missing.append(
            {
                "description": f"need {gap}",
                "gap_type": gap,
                "domain": "knowledge" if gap == "knowledge" else "observational",
                "valuable": True,
            }
        )
    return {
        "fine_candidates": [{"label": fine_label, "score": 0.8}],
        "coarse_candidates": [{"label": "malicious", "score": 0.9}],
        "short_analysis": "fixture analysis",
        "supporting_evidence": [
            {"evidence_id": "initial", "statement": "fixture support"}
        ],
        "missing_evidence": missing,
        "evidence_sufficiency": sufficiency,
        "model_signals": {"synthetic_open_set_signal": unknown_signal},
    }


def supervisor_payload(
    action: str,
    *,
    parameters: dict[str, Any] | None = None,
    reason: str = "fixture decision",
) -> dict[str, Any]:
    return {
        "action": action,
        "request_parameters": parameters,
        "short_reason": reason,
        "priority": 1,
        "expected_value": 0.5,
    }


def envelope_a(
    payload: dict[str, Any] | str,
    *,
    usage: dict[str, Any] | None = None,
    finish_status: str = "stop",
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    value = payload if isinstance(payload, str) else json.dumps(payload, sort_keys=True)
    return {
        "id": "fixture-a",
        "text": value,
        "usage": usage
        or {
            "input_tokens": 4,
            "output_tokens": 6,
            "total_tokens": 10,
            "abstract_cost": 0.1,
            "abstract_latency": 0.2,
        },
        "finish_status": finish_status,
        "metadata": metadata or {},
    }


def envelope_b(
    payload: dict[str, Any],
    *,
    structured: bool = True,
) -> dict[str, Any]:
    output = {"structured": payload} if structured else {"content": json.dumps(payload)}
    return {
        "request_id": "fixture-b",
        "output": output,
        "metering": {
            "prompt": 4,
            "completion": 6,
            "total": 10,
            "abstract_cost": 0.1,
            "abstract_latency": 0.2,
        },
        "status": "completed",
        "backend": {"fixture": "b"},
    }


def config(
    role: str,
    *,
    provider: str = "provider_a",
    attempts: int = 1,
    retryable: frozenset[LLMFailureKind] | None = None,
) -> LLMBackendConfig:
    prompt_id = (
        fixture_traffic_expert_prompt().prompt_id
        if role == "expert"
        else fixture_supervisor_prompt().prompt_id
    )
    return LLMBackendConfig(
        provider=provider,
        base_url=f"fixture://{provider}",
        model_id=f"SYNTHETIC_{role.upper()}_MODEL",
        timeout_seconds=1.0,
        retry_policy=RetryPolicy(
            max_attempts=attempts,
            retryable_failures=retryable or frozenset(),
        ),
        response_mode=ResponseMode.AUTO,
        generation_options={"fixture_temperature": 0.0},
        prompt_profile_id=prompt_id,
        request_metadata={"fixture": True},
    )


def profile(provider: str):
    return FixtureProviderAProfile() if provider == "provider_a" else FixtureProviderBProfile()


def fake_transport(provider: str, events: list[object], *, tokens: int = 20) -> FakeLLMTransport:
    return FakeLLMTransport(
        profile=profile(provider),
        events=events,  # type: ignore[arg-type]
        estimate_metrics=CallMetrics(
            abstract_tokens=tokens,
            abstract_cost=1.0,
            abstract_latency=2.0,
        ),
    )


def expert_backend(
    transport: FakeLLMTransport,
    *,
    provider: str = "provider_a",
    attempts: int = 1,
    retryable: frozenset[LLMFailureKind] | None = None,
    secret_values: tuple[str, ...] = (),
) -> LLMTrafficExpertBackend:
    return LLMTrafficExpertBackend(
        transport=transport,
        config=config(
            "expert",
            provider=provider,
            attempts=attempts,
            retryable=retryable,
        ),
        renderer=TrafficExpertPromptRenderer(fixture_traffic_expert_prompt()),
        parser=FixtureTrafficExpertResponseParserV0(),
        secret_values=secret_values,
    )

def supervisor_backend(
    transport: FakeLLMTransport,
    *,
    provider: str = "provider_a",
    attempts: int = 1,
    retryable: frozenset[LLMFailureKind] | None = None,
    secret_values: tuple[str, ...] = (),
) -> LLMSupervisorBackend:
    actions = (
        AgentAction.EXPAND_PACKETS,
        AgentAction.EXPAND_TEMPORAL_CONTEXT,
        AgentAction.EXPAND_GRAPH_CONTEXT,
        AgentAction.REQUEST_APPLICATION_EVIDENCE,
        AgentAction.RETRIEVE_KNOWLEDGE,
        AgentAction.ACCEPT_FINE,
        AgentAction.BACKOFF_COARSE,
        AgentAction.REJECT_UNKNOWN,
        AgentAction.ABSTAIN,
    )
    return LLMSupervisorBackend(
        transport=transport,
        config=config(
            "supervisor",
            provider=provider,
            attempts=attempts,
            retryable=retryable,
        ),
        renderer=SupervisorPromptRenderer(
            fixture_supervisor_prompt(),
            ToolSpecification(
                allowed_actions=actions,
                parameter_contracts={"expand_temporal_context": {"past_only": True}},
            ),
        ),
        parser=FixtureSupervisorResponseParserV0(),
        secret_values=secret_values,
    )
