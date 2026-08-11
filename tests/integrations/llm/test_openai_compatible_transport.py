from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from flowsec.integrations.llm.adapters import LLMTrafficExpertBackend
from flowsec.integrations.llm.contracts import (
    LLMBackendConfig,
    LLMFailureKind,
    LLMTransportError,
    ResponseMode,
    RetryPolicy,
)
from flowsec.integrations.llm.parsing import RawSmokeTrafficExpertResponseParserV0
from flowsec.integrations.llm.prompting import (
    TrafficExpertPromptRenderer,
    raw_smoke_traffic_expert_prompt,
)
from flowsec.integrations.llm.transport import OpenAICompatibleChatTransport
from tests.runtime._helpers import evidence


MODEL_ID = "Qwen/Qwen3.5-9B"


def _payload() -> dict:
    return {
        "fine_candidates": [{"label": "candidate", "score": None}],
        "coarse_candidates": [{"label": "candidate_parent", "score": None}],
        "short_analysis": "short transport smoke",
        "supporting_evidence": [
            {"evidence_id": evidence().evidence_id, "statement": "packet sequence is available"}
        ],
        "missing_evidence": [],
        "evidence_sufficiency": "sufficient",
        "model_signals": {},
    }


class RecordingCompletions:
    def __init__(self, *, reasoning_content: str | None = None):
        self.calls: list[dict] = []
        self.reasoning_content = reasoning_content

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(
            id="local-request-1",
            model=MODEL_ID,
            created=1,
            system_fingerprint=None,
            choices=[
                SimpleNamespace(
                    finish_reason="stop",
                    message=SimpleNamespace(
                        content=json.dumps(_payload()),
                        reasoning_content=self.reasoning_content,
                    ),
                )
            ],
            usage=SimpleNamespace(
                prompt_tokens=120,
                completion_tokens=80,
                total_tokens=200,
            ),
        )


class FakeClient:
    def __init__(self, completions):
        self.chat = SimpleNamespace(completions=completions)


def _config() -> LLMBackendConfig:
    profile = raw_smoke_traffic_expert_prompt()
    return LLMBackendConfig(
        provider="local_vllm",
        base_url="http://127.0.0.1:8000/v1",
        model_id=MODEL_ID,
        timeout_seconds=30.0,
        retry_policy=RetryPolicy(max_attempts=1, retryable_failures=frozenset()),
        response_mode=ResponseMode.TEXT,
        generation_options={
            "temperature": 0.0,
            "seed": 7,
            "max_tokens": 256,
            "response_format": {"type": "json_object"},
            "extra_body": {"chat_template_kwargs": {"enable_thinking": False}},
        },
        prompt_profile_id=profile.prompt_id,
    )


def test_real_transport_runs_through_traffic_expert_boundary(monkeypatch) -> None:
    completions = RecordingCompletions()
    transport = OpenAICompatibleChatTransport(
        api_key="EMPTY",
        max_input_tokens=4096,
        max_output_tokens=256,
        max_latency_seconds=30.0,
    )
    monkeypatch.setattr(transport, "_client", lambda request: FakeClient(completions))
    backend = LLMTrafficExpertBackend(
        transport=transport,
        config=_config(),
        renderer=TrafficExpertPromptRenderer(raw_smoke_traffic_expert_prompt()),
        parser=RawSmokeTrafficExpertResponseParserV0(),
    )

    estimate = backend.estimate((evidence(),))
    result = backend.evaluate((evidence(),))

    assert estimate.abstract_tokens == 4352
    assert result.fine_candidates[0].label == "candidate"
    assert result.metrics.abstract_tokens == 200
    call = completions.calls[0]
    assert call["model"] == MODEL_ID
    assert call["stream"] is False
    assert call["extra_body"]["chat_template_kwargs"]["enable_thinking"] is False
    assert [message["role"] for message in call["messages"]] == ["system", "user"]
    assert "<DATA" in call["messages"][1]["content"]
    assert transport.last_response_metadata["reasoning_content_present"] is False
    assert transport.last_response_metadata["input_tokens"] == 120
    assert transport.last_response_metadata["output_tokens"] == 80
    assert transport.last_response_metadata["total_tokens"] == 200
    assert transport.last_response_metadata["latency_seconds"] >= 0.0
    assert transport.last_response_metadata["output_tokens_per_second"] is not None


def test_real_transport_maps_timeout_and_redacts_secret(monkeypatch) -> None:
    class FailingCompletions:
        def create(self, **kwargs):
            raise TimeoutError("timeout with LOCAL_SECRET_VALUE")

    transport = OpenAICompatibleChatTransport(
        api_key="LOCAL_SECRET_VALUE",
        max_input_tokens=4096,
        max_output_tokens=256,
        max_latency_seconds=30.0,
    )
    monkeypatch.setattr(
        transport, "_client", lambda request: FakeClient(FailingCompletions())
    )
    backend = LLMTrafficExpertBackend(
        transport=transport,
        config=_config(),
        renderer=TrafficExpertPromptRenderer(raw_smoke_traffic_expert_prompt()),
        parser=RawSmokeTrafficExpertResponseParserV0(),
        secret_values=("LOCAL_SECRET_VALUE",),
    )

    with pytest.raises(Exception) as captured:
        backend.evaluate((evidence(),))
    assert "LOCAL_SECRET_VALUE" not in repr(captured.value)
    assert "[REDACTED]" in repr(transport)
    assert getattr(captured.value, "kind", None) is LLMFailureKind.TIMEOUT


def test_real_transport_rejects_unbounded_output_request() -> None:
    transport = OpenAICompatibleChatTransport(
        max_input_tokens=4096,
        max_output_tokens=128,
        max_latency_seconds=30.0,
    )
    backend = LLMTrafficExpertBackend(
        transport=transport,
        config=_config().model_copy(
            update={"generation_options": {"max_tokens": 256}}
        ),
        renderer=TrafficExpertPromptRenderer(raw_smoke_traffic_expert_prompt()),
        parser=RawSmokeTrafficExpertResponseParserV0(),
    )
    with pytest.raises(LLMTransportError):
        backend.estimate((evidence(),))
