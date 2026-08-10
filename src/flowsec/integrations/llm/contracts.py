from __future__ import annotations

import json
import re
from enum import StrEnum
from typing import Any, Protocol
from urllib.parse import parse_qsl, urlsplit

from pydantic import ConfigDict, Field, field_validator, model_validator

from flowsec.runtime.contracts import (
    CallMetrics,
    EvidenceTrust,
    FrozenRuntimeModel,
    validate_model_visible_value,
)


class LLMFailureKind(StrEnum):
    TRANSPORT_FAILURE = "transport_failure"
    TIMEOUT = "timeout"
    RATE_LIMIT_LIKE_FAILURE = "rate_limit_like_failure"
    EMPTY_RESPONSE = "empty_response"
    MALFORMED_RESPONSE = "malformed_response"
    SCHEMA_VALIDATION_FAILURE = "schema_validation_failure"
    UNSUPPORTED_RESPONSE = "unsupported_response"
    TRUNCATED_RESPONSE = "truncated_response"
    SECRET_CONFIGURATION_FAILURE = "secret_configuration_failure"


class ResponseMode(StrEnum):
    TEXT = "text"
    STRUCTURED = "structured"
    AUTO = "auto"


class MessageRole(StrEnum):
    SYSTEM = "system"
    USER = "user"


class ContentKind(StrEnum):
    INSTRUCTION = "instruction"
    DATA = "data"


class RepairType(StrEnum):
    NONE = "none"
    STRIP_MARKDOWN_FENCE = "strip_markdown_fence"
    EXTRACT_UNIQUE_JSON_OBJECT = "extract_unique_json_object"


_SENSITIVE_KEY = re.compile(
    r"(?:api[_-]?key|authorization|bearer|password|passwd|secret|access[_-]?token|private[_-]?key)",
    flags=re.IGNORECASE,
)
_BEARER_VALUE = re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]+")
_COMMON_KEY_VALUE = re.compile(
    r"(?i)\b(api[_-]?key|password|secret|access[_-]?token)\s*[:=]\s*[^\s,;]+"
)


def _validate_json_value(value: Any, *, location: str) -> None:
    try:
        json.dumps(value, sort_keys=True, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{location} must contain finite JSON data") from exc


def _reject_secret_fields(value: Any, *, location: str) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            if _SENSITIVE_KEY.search(str(key)):
                raise ValueError(f"secret-like field is not allowed in {location}: {key}")
            _reject_secret_fields(item, location=f"{location}.{key}")
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            _reject_secret_fields(item, location=f"{location}[{index}]")


def _validate_endpoint(value: str) -> str:
    parsed = urlsplit(value)
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("base_url must not embed credentials")
    if any(_SENSITIVE_KEY.search(key) for key, _ in parse_qsl(parsed.query)):
        raise ValueError("base_url must not embed secret-like query parameters")
    if _COMMON_KEY_VALUE.search(value):
        raise ValueError("base_url must not embed secret-like values")
    return value


def redact_text(text: str, secret_values: tuple[str, ...] = ()) -> str:
    """Return log-safe text without retaining injected secret values."""

    redacted = text
    for secret in sorted((item for item in secret_values if item), key=len, reverse=True):
        redacted = redacted.replace(secret, "[REDACTED]")
    redacted = _BEARER_VALUE.sub("Bearer [REDACTED]", redacted)
    redacted = _COMMON_KEY_VALUE.sub(lambda match: f"{match.group(1)}=[REDACTED]", redacted)
    return redacted


def redact_mapping(value: Any, secret_values: tuple[str, ...] = ()) -> Any:
    if isinstance(value, dict):
        return {
            str(key): (
                "[REDACTED]"
                if _SENSITIVE_KEY.search(str(key))
                else redact_mapping(item, secret_values)
            )
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [redact_mapping(item, secret_values) for item in value]
    if isinstance(value, str):
        return redact_text(value, secret_values)
    return value


class SecretRedactor:
    """Runtime-only redaction helper whose representation never exposes values."""

    def __init__(self, values: tuple[str, ...] = ()):
        self._values = tuple(item for item in values if item)

    def text(self, value: str) -> str:
        return redact_text(value, self._values)

    def mapping(self, value: Any) -> Any:
        return redact_mapping(value, self._values)

    def contains(self, value: str) -> bool:
        return any(secret in value for secret in self._values)

    def __repr__(self) -> str:
        return f"SecretRedactor(values={len(self._values)} redacted)"


class SecretProvider(Protocol):
    def resolve(self, reference: str) -> str:
        """Resolve a secret at runtime without persisting it in configuration."""


class RetryPolicy(FrozenRuntimeModel):
    """Caller-supplied retry policy; no value here is a production default."""

    max_attempts: int = Field(ge=1)
    retryable_failures: frozenset[LLMFailureKind]


class LLMBackendConfig(FrozenRuntimeModel):
    provider: str = Field(min_length=1)
    base_url: str = Field(min_length=1)
    model_id: str = Field(min_length=1)
    timeout_seconds: float = Field(gt=0, allow_inf_nan=False)
    retry_policy: RetryPolicy
    response_mode: ResponseMode
    generation_options: dict[str, Any]
    prompt_profile_id: str = Field(min_length=1)
    secret_reference: str | None = Field(default=None, repr=False)
    request_metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("base_url")
    @classmethod
    def validate_base_url(cls, value: str) -> str:
        return _validate_endpoint(value)

    @field_validator("generation_options", "request_metadata")
    @classmethod
    def validate_options(cls, value: dict[str, Any]) -> dict[str, Any]:
        _validate_json_value(value, location="LLM backend configuration")
        _reject_secret_fields(value, location="LLM backend configuration")
        validate_model_visible_value(value, location="LLM backend configuration")
        return value


class PromptIdentity(FrozenRuntimeModel):
    prompt_id: str = Field(min_length=1)
    prompt_version: str = Field(min_length=1)
    prompt_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    renderer_version: str = Field(min_length=1)


class MessageContent(FrozenRuntimeModel):
    kind: ContentKind
    content: str = Field(min_length=1, repr=False)
    trust: EvidenceTrust | None = None
    label: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_boundary(self) -> "MessageContent":
        validate_model_visible_value(self.content, location=f"llm_message.{self.label}")
        if self.trust is EvidenceTrust.UNTRUSTED_EVIDENCE and self.kind is not ContentKind.DATA:
            raise ValueError("untrusted evidence must remain a data content block")
        if self.kind is ContentKind.INSTRUCTION and self.trust is not None:
            raise ValueError("instruction blocks cannot carry evidence trust")
        return self


class LLMMessage(FrozenRuntimeModel):
    role: MessageRole
    content: tuple[MessageContent, ...]

    @model_validator(mode="after")
    def validate_role(self) -> "LLMMessage":
        if not self.content:
            raise ValueError("LLM messages cannot be empty")
        if self.role is MessageRole.SYSTEM and any(
            item.kind is not ContentKind.INSTRUCTION for item in self.content
        ):
            raise ValueError("system messages may contain instructions only")
        return self


class LLMTransportRequest(FrozenRuntimeModel):
    provider: str = Field(min_length=1)
    base_url: str = Field(min_length=1)
    model_id: str = Field(min_length=1)
    messages: tuple[LLMMessage, ...] = Field(repr=False)
    timeout_seconds: float = Field(gt=0, allow_inf_nan=False)
    response_mode: ResponseMode
    generation_options: dict[str, Any]
    prompt: PromptIdentity
    request_metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("base_url")
    @classmethod
    def validate_base_url(cls, value: str) -> str:
        return _validate_endpoint(value)

    @model_validator(mode="after")
    def validate_request(self) -> "LLMTransportRequest":
        if not self.messages or self.messages[0].role is not MessageRole.SYSTEM:
            raise ValueError("the first LLM message must be a system instruction")
        _validate_json_value(self.generation_options, location="generation options")
        _validate_json_value(self.request_metadata, location="request metadata")
        _reject_secret_fields(self.generation_options, location="generation options")
        _reject_secret_fields(self.request_metadata, location="request metadata")
        validate_model_visible_value(self.generation_options, location="generation options")
        validate_model_visible_value(self.request_metadata, location="request metadata")
        return self

    def redacted_projection(self, redactor: SecretRedactor | None = None) -> dict[str, Any]:
        helper = redactor or SecretRedactor()
        return helper.mapping(
            self.model_dump(mode="json", exclude={"messages"})
        )


class RawUsage(FrozenRuntimeModel):
    input_tokens: int | None = Field(default=None, ge=0, strict=True)
    output_tokens: int | None = Field(default=None, ge=0, strict=True)
    total_tokens: int | None = Field(default=None, ge=0, strict=True)
    abstract_cost: float = Field(default=0.0, ge=0, allow_inf_nan=False, strict=True)
    abstract_latency: float = Field(default=0.0, ge=0, allow_inf_nan=False, strict=True)

    @model_validator(mode="after")
    def validate_total(self) -> "RawUsage":
        if (
            self.total_tokens is not None
            and self.input_tokens is not None
            and self.output_tokens is not None
            and self.total_tokens < self.input_tokens + self.output_tokens
        ):
            raise ValueError("total_tokens cannot be smaller than input plus output")
        return self

    def to_metrics(self) -> CallMetrics:
        tokens = self.total_tokens
        if tokens is None:
            tokens = (self.input_tokens or 0) + (self.output_tokens or 0)
        return CallMetrics(
            abstract_tokens=tokens,
            abstract_cost=self.abstract_cost,
            abstract_latency=self.abstract_latency,
        )


class RawTransportFailure(FrozenRuntimeModel):
    kind: LLMFailureKind
    safe_message: str = Field(min_length=1, repr=False)
    retry_after_hint: float | None = Field(default=None, ge=0, allow_inf_nan=False)


class RawLLMResponse(FrozenRuntimeModel):
    """Untrusted provider-neutral response. Never a Runtime evidence contract."""

    raw_text: str | None = Field(default=None, repr=False)
    structured_payload: dict[str, Any] | None = Field(default=None, repr=False)
    usage: RawUsage = Field(default_factory=RawUsage)
    finish_status: str | None = None
    provider: str = Field(min_length=1)
    model_id: str | None = None
    request_id: str | None = None
    provider_metadata: dict[str, Any] = Field(default_factory=dict, repr=False)
    failure: RawTransportFailure | None = Field(default=None, repr=False)


class ParseAudit(FrozenRuntimeModel):
    parser_profile_id: str = Field(min_length=1)
    repair_applied: bool = False
    repair_type: RepairType = RepairType.NONE


class BackendAttemptRecord(FrozenRuntimeModel):
    attempt: int = Field(ge=1)
    failure: LLMFailureKind | None = None
    metrics: CallMetrics
    repair_applied: bool = False
    repair_type: RepairType = RepairType.NONE


class BackendCallAudit(FrozenRuntimeModel):
    attempts: tuple[BackendAttemptRecord, ...]
    prompt: PromptIdentity

    @property
    def total_metrics(self) -> CallMetrics:
        return CallMetrics(
            abstract_tokens=sum(item.metrics.abstract_tokens for item in self.attempts),
            abstract_cost=sum(item.metrics.abstract_cost for item in self.attempts),
            abstract_latency=sum(item.metrics.abstract_latency for item in self.attempts),
        )


class LLMTransportError(RuntimeError):
    def __init__(
        self,
        kind: LLMFailureKind,
        message: str,
        *,
        secret_values: tuple[str, ...] = (),
        retry_allowed: bool = True,
    ):
        self.kind = kind
        self.retry_allowed = retry_allowed
        self.safe_message = redact_text(message, secret_values)
        super().__init__(self.safe_message)


class LLMResponseError(ValueError):
    def __init__(
        self,
        kind: LLMFailureKind,
        message: str,
        *,
        repair_applied: bool = False,
        repair_type: RepairType = RepairType.NONE,
    ):
        self.kind = kind
        self.repair_applied = repair_applied
        self.repair_type = repair_type
        super().__init__(message)


class LLMBackendError(RuntimeError):
    def __init__(
        self,
        kind: LLMFailureKind,
        message: str,
        *,
        attempts: int,
        secret_values: tuple[str, ...] = (),
    ):
        self.kind = kind
        self.attempts = attempts
        self.safe_message = redact_text(message, secret_values)
        super().__init__(f"{kind.value} after {attempts} attempt(s): {self.safe_message}")


def add_metrics(left: CallMetrics, right: CallMetrics) -> CallMetrics:
    return CallMetrics(
        abstract_tokens=left.abstract_tokens + right.abstract_tokens,
        abstract_cost=left.abstract_cost + right.abstract_cost,
        abstract_latency=left.abstract_latency + right.abstract_latency,
    )


def scale_metrics(metrics: CallMetrics, multiplier: int) -> CallMetrics:
    return CallMetrics(
        abstract_tokens=metrics.abstract_tokens * multiplier,
        abstract_cost=metrics.abstract_cost * multiplier,
        abstract_latency=metrics.abstract_latency * multiplier,
    )
