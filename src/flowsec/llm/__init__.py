"""Reusable language-model runtime, cache and validation."""

from .cache import FileResultCache
from .fingerprint import GenerationParameters, RequestIdentity, build_request_identity
from .runtime import (
    CompletionResponse,
    LLMRequest,
    LLMRunner,
    OpenAIChatTransport,
    RunOutcome,
    select_shard,
)
from .structured_output import (
    JsonExtractionError,
    StructuredOutputValidationError,
    extract_json_value,
    validate_structured_output,
)

__all__ = [
    "CompletionResponse",
    "FileResultCache",
    "GenerationParameters",
    "JsonExtractionError",
    "LLMRequest",
    "LLMRunner",
    "OpenAIChatTransport",
    "RequestIdentity",
    "RunOutcome",
    "StructuredOutputValidationError",
    "build_request_identity",
    "extract_json_value",
    "select_shard",
    "validate_structured_output",
]
