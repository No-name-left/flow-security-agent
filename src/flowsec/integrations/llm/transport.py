from __future__ import annotations

import os
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
