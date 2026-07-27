from __future__ import annotations

import os
from pathlib import Path
from typing import Mapping

import yaml
from pydantic import BaseModel, ConfigDict, Field, PositiveFloat, PositiveInt


class RuntimeProfile(BaseModel):
    """Non-secret endpoint configuration stored in YAML."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    base_url: str
    base_url_env: str | None = None
    model: str
    model_env: str | None = None
    api_key_env: str
    local_api_key_default: str | None = None
    request_timeout_seconds: PositiveFloat = 180
    max_context_tokens: PositiveInt = 8192
    max_output_tokens: PositiveInt = 512
    enable_thinking: bool = False
    max_workers: PositiveInt = 1
    max_retries: int = Field(default=2, ge=0)
    retry_delay_seconds: float = Field(default=2, ge=0)

    def resolve(self, environ: Mapping[str, str] | None = None) -> "ResolvedRuntime":
        values = os.environ if environ is None else environ
        base_url = (values.get(self.base_url_env) or self.base_url) if self.base_url_env else self.base_url
        model = (values.get(self.model_env) or self.model) if self.model_env else self.model
        api_key = values.get(self.api_key_env) or self.local_api_key_default
        if not api_key:
            raise ValueError(f"missing API key environment variable: {self.api_key_env}")
        return ResolvedRuntime(
            base_url=base_url,
            model=model,
            api_key=api_key,
            request_timeout_seconds=self.request_timeout_seconds,
            max_context_tokens=self.max_context_tokens,
            max_output_tokens=self.max_output_tokens,
            enable_thinking=self.enable_thinking,
            max_workers=self.max_workers,
            max_retries=self.max_retries,
            retry_delay_seconds=self.retry_delay_seconds,
        )


class ResolvedRuntime(BaseModel):
    """Runtime values after environment overrides have been applied."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    base_url: str
    model: str
    api_key: str = Field(repr=False)
    request_timeout_seconds: PositiveFloat
    max_context_tokens: PositiveInt
    max_output_tokens: PositiveInt
    enable_thinking: bool
    max_workers: PositiveInt
    max_retries: int = Field(ge=0)
    retry_delay_seconds: float = Field(ge=0)

    def public_identity(self) -> dict[str, object]:
        """Return cache/log identity without exposing the credential."""

        return {
            "base_url": self.base_url,
            "model": self.model,
            "request_timeout_seconds": self.request_timeout_seconds,
            "max_context_tokens": self.max_context_tokens,
            "max_output_tokens": self.max_output_tokens,
            "enable_thinking": self.enable_thinking,
        }


def load_runtime_profile(
    path: Path,
    profile_name: str,
    environ: Mapping[str, str] | None = None,
) -> ResolvedRuntime:
    document = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    profiles = document.get("profiles")
    if not isinstance(profiles, dict) or profile_name not in profiles:
        available = ", ".join(sorted(profiles)) if isinstance(profiles, dict) else "none"
        raise ValueError(f"unknown runtime profile {profile_name!r}; available: {available}")
    profile = RuntimeProfile.model_validate(profiles[profile_name])
    return profile.resolve(environ)
