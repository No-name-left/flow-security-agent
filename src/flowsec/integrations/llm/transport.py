from __future__ import annotations

import json
import os
import threading
import time
from collections import deque
from typing import Any, Protocol

from pydantic import ValidationError

from flowsec.runtime.contracts import CallMetrics

from .contracts import (
    LLMBackendConfig,
    LLMFailureKind,
    LLMTransportError,
    LLMTransportRequest,
    RawLLMResponse,
    RawTransportFailure,
    RawUsage,
    ResponseMode,
    SecretProvider,
    SecretRedactor,
)


class LLMTransport(Protocol):
    """Provider-neutral, side-effect-free-estimate transport boundary."""

    def estimate(self, request: LLMTransportRequest) -> CallMetrics:
        ...

    def send(self, request: LLMTransportRequest) -> RawLLMResponse:
        ...


class ProviderEnvelopeProfile(Protocol):
    profile_id: str

    def normalize(
        self,
        envelope: dict[str, Any],
        request: LLMTransportRequest,
    ) -> RawLLMResponse:
        ...


class EnvironmentSecretProvider:
    """Runtime-only environment lookup; values are never retained by this object."""

    def resolve(self, reference: str) -> str:
        value = os.environ.get(reference)
        if not value:
            raise LLMTransportError(
                LLMFailureKind.SECRET_CONFIGURATION_FAILURE,
                f"secret reference is unavailable: {reference}",
            )
        return value


class InjectedSecretProvider:
    def __init__(self, secrets: dict[str, str]):
        self._secrets = dict(secrets)

    def resolve(self, reference: str) -> str:
        value = self._secrets.get(reference)
        if not value:
            raise LLMTransportError(
                LLMFailureKind.SECRET_CONFIGURATION_FAILURE,
                f"secret reference is unavailable: {reference}",
            )
        return value

    def __repr__(self) -> str:
        return f"InjectedSecretProvider(references={sorted(self._secrets)}, values=[REDACTED])"


def resolve_configured_secret(
    config: LLMBackendConfig,
    provider: SecretProvider | None,
) -> str | None:
    if config.secret_reference is None:
        return None
    if provider is None:
        raise LLMTransportError(
            LLMFailureKind.SECRET_CONFIGURATION_FAILURE,
            "a secret reference was configured without a secret provider",
        )
    return provider.resolve(config.secret_reference)


class OpenAICompatibleChatTransport:
    # Real OpenAI-compatible transport for audited local/provider deployments.

    def __init__(
        self,
        *,
        api_key: str = "EMPTY",
        max_input_tokens: int,
        max_output_tokens: int,
        max_latency_seconds: float,
        trust_env: bool = True,
    ):
        if max_input_tokens < 1 or max_output_tokens < 1 or max_latency_seconds <= 0:
            raise ValueError("transport estimates must be positive")
        self._api_key = api_key
        self.max_input_tokens = max_input_tokens
        self.max_output_tokens = max_output_tokens
        self.max_latency_seconds = float(max_latency_seconds)
        self.trust_env = bool(trust_env)
        self._local = threading.local()
        self._redactor = SecretRedactor(() if api_key == "EMPTY" else (api_key,))
        self.last_response_metadata: dict[str, Any] = {}

    def _client(self, request: LLMTransportRequest) -> Any:
        key = (request.base_url, request.timeout_seconds)
        clients = getattr(self._local, "clients", None)
        if clients is None:
            clients = {}
            self._local.clients = clients
        if key not in clients:
            import httpx
            from openai import OpenAI

            clients[key] = OpenAI(
                base_url=request.base_url,
                api_key=self._api_key,
                timeout=request.timeout_seconds,
                http_client=httpx.Client(
                    timeout=request.timeout_seconds,
                    trust_env=self.trust_env,
                ),
            )
        return clients[key]

    def estimate(self, request: LLMTransportRequest) -> CallMetrics:
        requested = request.generation_options.get("max_tokens", self.max_output_tokens)
        if isinstance(requested, bool) or not isinstance(requested, int) or requested < 1:
            raise LLMTransportError(
                LLMFailureKind.UNSUPPORTED_RESPONSE,
                "max_tokens must be a positive integer",
                retry_allowed=False,
            )
        if requested > self.max_output_tokens:
            raise LLMTransportError(
                LLMFailureKind.UNSUPPORTED_RESPONSE,
                "requested output exceeds the configured transport estimate",
                retry_allowed=False,
            )
        return CallMetrics(
            abstract_tokens=self.max_input_tokens + requested,
            abstract_latency=self.max_latency_seconds,
        )

    @staticmethod
    def _failure_kind(exc: Exception) -> LLMFailureKind:
        name = type(exc).__name__.casefold()
        status = getattr(exc, "status_code", None)
        if isinstance(exc, TimeoutError) or "timeout" in name:
            return LLMFailureKind.TIMEOUT
        if status == 429 or "ratelimit" in name or "rate_limit" in name:
            return LLMFailureKind.RATE_LIMIT_LIKE_FAILURE
        return LLMFailureKind.TRANSPORT_FAILURE

    def send(self, request: LLMTransportRequest) -> RawLLMResponse:
        self.estimate(request)
        from .prompting import render_messages_as_tagged_text

        call: dict[str, Any] = {
            "model": request.model_id,
            "messages": list(render_messages_as_tagged_text(request.messages)),
            "stream": False,
            **request.generation_options,
        }
        started = time.perf_counter()
        try:
            response = self._client(request).chat.completions.create(**call)
        except Exception as exc:
            raise LLMTransportError(
                self._failure_kind(exc),
                self._redactor.text(f"{type(exc).__name__}: {exc}"),
            ) from exc
        latency = time.perf_counter() - started
        try:
            choice = response.choices[0]
            message = choice.message
            content = message.content
            if content is not None and not isinstance(content, str):
                raise TypeError("OpenAI-compatible response content is not text")
            reasoning = getattr(message, "reasoning_content", None)
            usage = getattr(response, "usage", None)
            input_tokens = getattr(usage, "prompt_tokens", None) if usage is not None else None
            output_tokens = getattr(usage, "completion_tokens", None) if usage is not None else None
            total_tokens = getattr(usage, "total_tokens", None) if usage is not None else None
            structured = None
            raw_text = content
            if request.response_mode is ResponseMode.STRUCTURED:
                if not content:
                    raise ValueError("structured response content is empty")
                structured = json.loads(content)
                if not isinstance(structured, dict):
                    raise TypeError("structured response is not a JSON object")
                raw_text = None
            metadata = {
                "reasoning_content_present": bool(reasoning),
                "created": getattr(response, "created", None),
                "system_fingerprint": getattr(response, "system_fingerprint", None),
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "total_tokens": total_tokens,
                "latency_seconds": float(latency),
                "output_tokens_per_second": (
                    float(output_tokens) / latency
                    if isinstance(output_tokens, int) and latency > 0.0
                    else None
                ),
            }
            self.last_response_metadata = dict(metadata)
            return RawLLMResponse(
                raw_text=raw_text,
                structured_payload=structured,
                usage=RawUsage(
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    total_tokens=total_tokens,
                    abstract_latency=float(latency),
                ),
                finish_status=getattr(choice, "finish_reason", None),
                provider=request.provider,
                model_id=getattr(response, "model", None) or request.model_id,
                request_id=getattr(response, "id", None),
                provider_metadata=metadata,
            )
        except (IndexError, KeyError, TypeError, ValueError, ValidationError) as exc:
            raise LLMTransportError(
                LLMFailureKind.UNSUPPORTED_RESPONSE,
                self._redactor.text(
                    f"unsupported OpenAI-compatible response: {type(exc).__name__}"
                ),
                retry_allowed=False,
            ) from exc

    def __repr__(self) -> str:
        return (
            "OpenAICompatibleChatTransport("
            f"max_input_tokens={self.max_input_tokens}, "
            f"max_output_tokens={self.max_output_tokens}, secrets=[REDACTED])"
        )


class FixtureProviderAProfile:
    """Synthetic envelope A; not a permanent mapping for any real provider."""

    profile_id = "SYNTHETIC_PROVIDER_A_ENVELOPE_V0"

    def normalize(
        self,
        envelope: dict[str, Any],
        request: LLMTransportRequest,
    ) -> RawLLMResponse:
        try:
            if "text" not in envelope and "structured" not in envelope:
                raise ValueError("provider A envelope has no response payload")
            usage = RawUsage.model_validate(envelope.get("usage", {}))
            return RawLLMResponse(
                raw_text=envelope.get("text"),
                structured_payload=envelope.get("structured"),
                usage=usage,
                finish_status=envelope.get("finish_status"),
                provider=request.provider,
                model_id=request.model_id,
                request_id=envelope.get("id"),
                provider_metadata=envelope.get("metadata", {}),
            )
        except (ValidationError, TypeError, ValueError) as exc:
            raise LLMTransportError(
                LLMFailureKind.UNSUPPORTED_RESPONSE,
                f"synthetic provider A envelope is unsupported: {type(exc).__name__}",
            ) from exc


class FixtureProviderBProfile:
    """Synthetic envelope B; proves mapping independence from envelope A."""

    profile_id = "SYNTHETIC_PROVIDER_B_ENVELOPE_V0"

    def normalize(
        self,
        envelope: dict[str, Any],
        request: LLMTransportRequest,
    ) -> RawLLMResponse:
        try:
            output = envelope["output"]
            if not isinstance(output, dict) or not ({"content", "structured"} & set(output)):
                raise ValueError("provider B output is unsupported")
            metering = envelope.get("metering", {})
            usage = RawUsage(
                input_tokens=metering.get("prompt"),
                output_tokens=metering.get("completion"),
                total_tokens=metering.get("total"),
                abstract_cost=metering.get("abstract_cost", 0.0),
                abstract_latency=metering.get("abstract_latency", 0.0),
            )
            return RawLLMResponse(
                raw_text=output.get("content"),
                structured_payload=output.get("structured"),
                usage=usage,
                finish_status=envelope.get("status"),
                provider=request.provider,
                model_id=request.model_id,
                request_id=envelope.get("request_id"),
                provider_metadata=envelope.get("backend", {}),
            )
        except (KeyError, ValidationError, TypeError, ValueError) as exc:
            raise LLMTransportError(
                LLMFailureKind.UNSUPPORTED_RESPONSE,
                f"synthetic provider B envelope is unsupported: {type(exc).__name__}",
            ) from exc


class FakeFailure:
    def __init__(self, kind: LLMFailureKind, message: str):
        self.kind = kind
        self.message = message

    def __repr__(self) -> str:
        return f"FakeFailure(kind={self.kind.value!r}, message=[REDACTED])"


FakeTransportEvent = dict[str, Any] | RawLLMResponse | FakeFailure | Exception


class FakeLLMTransport:
    """Deterministic provider-independent transport for integration and attack tests."""

    def __init__(
        self,
        *,
        profile: ProviderEnvelopeProfile,
        events: list[FakeTransportEvent],
        estimate_metrics: CallMetrics,
        secret_values: tuple[str, ...] = (),
    ):
        self.profile = profile
        self._events = deque(events)
        self.estimate_metrics = estimate_metrics
        self._redactor = SecretRedactor(secret_values)
        self.estimate_requests: list[LLMTransportRequest] = []
        self.requests: list[LLMTransportRequest] = []
        self.attempt_metrics: list[CallMetrics] = []
        self.operation_log: list[str] = []

    def estimate(self, request: LLMTransportRequest) -> CallMetrics:
        self.operation_log.append("estimate")
        self.estimate_requests.append(request.model_copy(deep=True))
        return self.estimate_metrics.model_copy(deep=True)

    def send(self, request: LLMTransportRequest) -> RawLLMResponse:
        self.operation_log.append("send")
        self.requests.append(request.model_copy(deep=True))
        if not self._events:
            raise LLMTransportError(
                LLMFailureKind.TRANSPORT_FAILURE,
                "no fake transport event remains",
            )
        event = self._events.popleft()
        if isinstance(event, FakeFailure):
            raise LLMTransportError(
                event.kind,
                self._redactor.text(event.message),
            )
        if isinstance(event, Exception):
            raise LLMTransportError(
                LLMFailureKind.TRANSPORT_FAILURE,
                self._redactor.text(str(event)),
            ) from event
        if isinstance(event, RawLLMResponse):
            response = RawLLMResponse.model_validate(event.model_dump(mode="python"))
        else:
            response = self.profile.normalize(event, request.model_copy(deep=True))
        self.attempt_metrics.append(response.usage.to_metrics())
        return response

    @property
    def remaining_events(self) -> int:
        return len(self._events)

    def __repr__(self) -> str:
        return (
            f"FakeLLMTransport(profile={self.profile.profile_id!r}, "
            f"remaining_events={len(self._events)}, secrets=[REDACTED])"
        )


def failed_raw_response(
    *,
    provider: str,
    kind: LLMFailureKind,
    safe_message: str,
    usage: RawUsage | None = None,
) -> RawLLMResponse:
    return RawLLMResponse(
        provider=provider,
        usage=usage or RawUsage(),
        failure=RawTransportFailure(kind=kind, safe_message=safe_message),
    )
