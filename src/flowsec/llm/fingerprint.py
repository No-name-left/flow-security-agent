from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class GenerationParameters(BaseModel):
    """Generation values that can affect a structured model response."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    temperature: float = Field(default=0.0, ge=0)
    top_p: float = Field(default=0.8, gt=0, le=1)
    max_tokens: int = Field(default=512, gt=0)
    seed: int | None = None

    def request_kwargs(self) -> dict[str, Any]:
        return self.model_dump(exclude_none=True)


class RequestIdentity(BaseModel):
    """Complete compatibility identity required for cache reuse."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    record_id: str = Field(min_length=1)
    input_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    prompt_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    model: str = Field(min_length=1)
    generation_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    runtime_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    schema_version: str = Field(min_length=1)

    @property
    def digest(self) -> str:
        return sha256_json(self.model_dump(mode="json"))


def _json_default(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if isinstance(value, Path):
        return value.as_posix()
    if isinstance(value, set):
        return sorted(value)
    if isinstance(value, bytes):
        return value.hex()
    raise TypeError(f"not JSON serializable: {type(value).__name__}")


def canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=_json_default,
    )


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def sha256_json(value: Any) -> str:
    return sha256_text(canonical_json(value))


def build_request_identity(
    *,
    record_id: str,
    input_data: Any,
    prompt: str,
    model: str,
    generation: GenerationParameters,
    runtime_identity: Any,
    schema_version: str,
) -> RequestIdentity:
    return RequestIdentity(
        record_id=record_id,
        input_fingerprint=sha256_json(input_data),
        prompt_fingerprint=sha256_text(prompt),
        model=model,
        generation_fingerprint=sha256_json(generation),
        runtime_fingerprint=sha256_json(runtime_identity),
        schema_version=schema_version,
    )
