from __future__ import annotations

from collections.abc import Callable
from typing import Generic, TypeVar

from flowsec.runtime.contracts import (
    CallMetrics,
    EvidenceItem,
    SupervisorDecision,
    SupervisorView,
    TrafficExpertResult,
)

from .contracts import (
    BackendAttemptRecord,
    BackendCallAudit,
    LLMBackendConfig,
    LLMBackendError,
    LLMFailureKind,
    LLMResponseError,
    LLMTransportError,
    LLMTransportRequest,
    ParseAudit,
    RawLLMResponse,
    RepairType,
    SecretRedactor,
    add_metrics,
    scale_metrics,
)
from .parsing import SupervisorResponseParser, TrafficExpertResponseParser
from .prompting import SupervisorPromptRenderer, TrafficExpertPromptRenderer
from .transport import LLMTransport


ResultT = TypeVar("ResultT", TrafficExpertResult, SupervisorDecision)


class _AdapterExecutor(Generic[ResultT]):
    def __init__(
        self,
        *,
        transport: LLMTransport,
        config: LLMBackendConfig,
        parser: object,
        parse: Callable[[RawLLMResponse], tuple[ResultT, ParseAudit]],
        secret_values: tuple[str, ...],
    ):
        self.transport = transport
        self.config = config
        self.parser = parser
        self._parse = parse
        self._redactor = SecretRedactor(secret_values)
        self.last_call_audit: BackendCallAudit | None = None

    def estimate(self, request: LLMTransportRequest) -> CallMetrics:
        self._ensure_no_secret_in_request(request)
        validated = self._safe_transport_estimate(request)
        return scale_metrics(validated, self.config.retry_policy.max_attempts)

    def call(self, request: LLMTransportRequest) -> ResultT:
        self._ensure_no_secret_in_request(request)
        per_attempt_estimate = self._safe_transport_estimate(request)
        cumulative = CallMetrics()
        attempts: list[BackendAttemptRecord] = []
        last_kind = LLMFailureKind.TRANSPORT_FAILURE
        last_message = "LLM backend call failed"
        retry_allowed = True

        for attempt in range(1, self.config.retry_policy.max_attempts + 1):
            response: RawLLMResponse | None = None
            audit = ParseAudit(parser_profile_id="unparsed")
            try:
                response = self.transport.send(request.model_copy(deep=True))
                if not isinstance(response, RawLLMResponse):
                    raise LLMTransportError(
                        LLMFailureKind.UNSUPPORTED_RESPONSE,
                        "transport returned a non-RawLLMResponse value",
                    )
                response = RawLLMResponse.model_validate(response.model_dump(mode="python"))
                self._validate_response_identity(response)
                attempt_metrics = response.usage.to_metrics()
                if not _metrics_within(attempt_metrics, per_attempt_estimate):
                    raise LLMTransportError(
                        LLMFailureKind.UNSUPPORTED_RESPONSE,
                        "response usage exceeded the transport preflight estimate",
                        retry_allowed=False,
                    )
                result, audit = self._parse(response.model_copy(deep=True))
                result = type(result).model_validate(result.model_dump(mode="python"))
                cumulative = add_metrics(cumulative, attempt_metrics)
                attempts.append(
                    BackendAttemptRecord(
                        attempt=attempt,
                        metrics=attempt_metrics,
                        repair_applied=audit.repair_applied,
                        repair_type=audit.repair_type,
                    )
                )
                result = result.model_copy(update={"metrics": cumulative}, deep=True)
                self.last_call_audit = BackendCallAudit(
                    attempts=tuple(attempts),
                    prompt=request.prompt,
                )
                return result
            except LLMResponseError as exc:
                last_kind = exc.kind
                last_message = self._redactor.text(str(exc))
                audit = ParseAudit(
                    parser_profile_id=getattr(self.parser, "profile_id", "unknown"),
                    repair_applied=exc.repair_applied,
                    repair_type=exc.repair_type,
                )
                attempt_metrics = _failure_metrics(response, per_attempt_estimate)
            except LLMTransportError as exc:
                last_kind = exc.kind
                last_message = exc.safe_message
                retry_allowed = exc.retry_allowed
                attempt_metrics = _failure_metrics(response, per_attempt_estimate)
            except Exception as exc:
                last_kind = LLMFailureKind.UNSUPPORTED_RESPONSE
                last_message = self._redactor.text(f"{type(exc).__name__}: {exc}")
                attempt_metrics = _failure_metrics(response, per_attempt_estimate)

            cumulative = add_metrics(cumulative, attempt_metrics)
            attempts.append(
                BackendAttemptRecord(
                    attempt=attempt,
                    failure=last_kind,
                    metrics=attempt_metrics,
                    repair_applied=audit.repair_applied,
                    repair_type=audit.repair_type,
                )
            )
            if (
                attempt >= self.config.retry_policy.max_attempts
                or last_kind not in self.config.retry_policy.retryable_failures
                or not retry_allowed
            ):
                break

        self.last_call_audit = BackendCallAudit(
            attempts=tuple(attempts),
            prompt=request.prompt,
        )
        raise LLMBackendError(
            last_kind,
            last_message,
            attempts=len(attempts),
        )

    def _validate_response_identity(self, response: RawLLMResponse) -> None:
        if response.provider != self.config.provider:
            raise LLMTransportError(
                LLMFailureKind.UNSUPPORTED_RESPONSE,
                "response provider does not match backend configuration",
                retry_allowed=False,
            )
        if response.model_id is not None and response.model_id != self.config.model_id:
            raise LLMTransportError(
                LLMFailureKind.UNSUPPORTED_RESPONSE,
                "response model does not match backend configuration",
                retry_allowed=False,
            )
        if (
            self.config.response_mode.value == "text"
            and (response.raw_text is None or response.structured_payload is not None)
        ):
            raise LLMTransportError(
                LLMFailureKind.UNSUPPORTED_RESPONSE,
                "response does not satisfy the configured text mode",
                retry_allowed=False,
            )
        if (
            self.config.response_mode.value == "structured"
            and response.structured_payload is None
        ):
            raise LLMTransportError(
                LLMFailureKind.UNSUPPORTED_RESPONSE,
                "response does not satisfy the configured structured mode",
                retry_allowed=False,
            )

    def _safe_transport_estimate(self, request: LLMTransportRequest) -> CallMetrics:
        try:
            estimate = self.transport.estimate(request.model_copy(deep=True))
            if not isinstance(estimate, CallMetrics):
                raise TypeError("LLM transport estimate must be CallMetrics")
            return CallMetrics.model_validate(estimate.model_dump(mode="python"))
        except LLMTransportError as exc:
            raise LLMTransportError(
                exc.kind,
                self._redactor.text(exc.safe_message),
                retry_allowed=False,
            ) from exc
        except Exception as exc:
            raise LLMTransportError(
                LLMFailureKind.TRANSPORT_FAILURE,
                self._redactor.text(f"transport estimate failed: {type(exc).__name__}: {exc}"),
                retry_allowed=False,
            ) from exc

    def _ensure_no_secret_in_request(self, request: LLMTransportRequest) -> None:
        serialized = request.model_dump_json()
        if self._redactor.contains(serialized):
            raise LLMTransportError(
                LLMFailureKind.SECRET_CONFIGURATION_FAILURE,
                "a runtime secret was found in the model request",
                retry_allowed=False,
            )


def _metrics_within(actual: CallMetrics, estimate: CallMetrics) -> bool:
    return (
        actual.abstract_tokens <= estimate.abstract_tokens
        and actual.abstract_cost <= estimate.abstract_cost
        and actual.abstract_latency <= estimate.abstract_latency
    )


def _failure_metrics(
    response: RawLLMResponse | None,
    conservative_estimate: CallMetrics,
) -> CallMetrics:
    if response is None:
        return conservative_estimate
    actual = response.usage.to_metrics()
    if actual == CallMetrics():
        return conservative_estimate
    if not _metrics_within(actual, conservative_estimate):
        return conservative_estimate
    return actual


class LLMTrafficExpertBackend:
    """Provider-neutral LLM adapter implementing the Runtime expert contract."""

    def __init__(
        self,
        *,
        transport: LLMTransport,
        config: LLMBackendConfig,
        renderer: TrafficExpertPromptRenderer,
        parser: TrafficExpertResponseParser,
        secret_values: tuple[str, ...] = (),
    ):
        if config.prompt_profile_id != renderer.identity.prompt_id:
            raise ValueError("Traffic Expert prompt profile does not match backend configuration")
        self.config = config
        self.renderer = renderer
        self.parser = parser
        self._executor = _AdapterExecutor[TrafficExpertResult](
            transport=transport,
            config=config,
            parser=parser,
            parse=parser.parse,
            secret_values=secret_values,
        )

    @property
    def last_call_audit(self) -> BackendCallAudit | None:
        return self._executor.last_call_audit

    def _request(self, evidence: tuple[EvidenceItem, ...]) -> LLMTransportRequest:
        safe_evidence = tuple(
            EvidenceItem.model_validate(item.model_dump(mode="python")) for item in evidence
        )
        if any(not item.model_safe for item in safe_evidence):
            raise LLMTransportError(
                LLMFailureKind.UNSUPPORTED_RESPONSE,
                "Traffic Expert evidence is not model-safe",
                retry_allowed=False,
            )
        return LLMTransportRequest(
            provider=self.config.provider,
            base_url=self.config.base_url,
            model_id=self.config.model_id,
            messages=self.renderer.render(safe_evidence),
            timeout_seconds=self.config.timeout_seconds,
            response_mode=self.config.response_mode,
            generation_options=self.config.generation_options,
            prompt=self.renderer.identity,
            request_metadata={"backend_role": "traffic_expert", **self.config.request_metadata},
        )

    def estimate(self, evidence: tuple[EvidenceItem, ...]) -> CallMetrics:
        return self._executor.estimate(self._request(evidence))

    def evaluate(self, evidence: tuple[EvidenceItem, ...]) -> TrafficExpertResult:
        result = self._executor.call(self._request(evidence))
        return TrafficExpertResult.model_validate(result.model_dump(mode="python"))


class LLMSupervisorBackend:
    """Provider-neutral LLM adapter that can propose, but cannot execute, actions."""

    def __init__(
        self,
        *,
        transport: LLMTransport,
        config: LLMBackendConfig,
        renderer: SupervisorPromptRenderer,
        parser: SupervisorResponseParser,
        secret_values: tuple[str, ...] = (),
    ):
        if config.prompt_profile_id != renderer.identity.prompt_id:
            raise ValueError("Supervisor prompt profile does not match backend configuration")
        self.config = config
        self.renderer = renderer
        self.parser = parser
        self._executor = _AdapterExecutor[SupervisorDecision](
            transport=transport,
            config=config,
            parser=parser,
            parse=parser.parse,
            secret_values=secret_values,
        )

    @property
    def last_call_audit(self) -> BackendCallAudit | None:
        return self._executor.last_call_audit

    def _request(self, state: SupervisorView) -> LLMTransportRequest:
        safe_state = SupervisorView.model_validate(state.model_dump(mode="python"))
        if any(not item.model_safe for item in safe_state.evidence):
            raise LLMTransportError(
                LLMFailureKind.UNSUPPORTED_RESPONSE,
                "Supervisor evidence is not model-safe",
                retry_allowed=False,
            )
        return LLMTransportRequest(
            provider=self.config.provider,
            base_url=self.config.base_url,
            model_id=self.config.model_id,
            messages=self.renderer.render(safe_state),
            timeout_seconds=self.config.timeout_seconds,
            response_mode=self.config.response_mode,
            generation_options=self.config.generation_options,
            prompt=self.renderer.identity,
            request_metadata={"backend_role": "supervisor", **self.config.request_metadata},
        )

    def estimate(self, state: SupervisorView) -> CallMetrics:
        return self._executor.estimate(self._request(state))

    def decide(self, state: SupervisorView) -> SupervisorDecision:
        result = self._executor.call(self._request(state))
        return SupervisorDecision.model_validate(result.model_dump(mode="python"))
