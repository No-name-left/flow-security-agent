from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, TypeVar

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from .fingerprint import RequestIdentity, sha256_text


SchemaT = TypeVar("SchemaT", bound=BaseModel)


class CachedResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    identity: RequestIdentity
    output: dict[str, Any]
    usage: dict[str, Any] = Field(default_factory=dict)
    latency_seconds: float = Field(ge=0)
    attempts: int = Field(ge=1)
    response_id: str | None = None
    created_at: str


class FileResultCache:
    """Validated per-record JSON cache with atomic replacement."""

    def __init__(self, root: Path):
        self.root = Path(root)

    def path_for(self, identity: RequestIdentity) -> Path:
        record_hash = sha256_text(identity.record_id)[:16]
        return self.root / record_hash / f"{identity.digest}.json"

    def load(self, identity: RequestIdentity, schema: type[SchemaT]) -> tuple[SchemaT, CachedResult] | None:
        path = self.path_for(identity)
        if not path.exists():
            return None
        try:
            cached = CachedResult.model_validate_json(path.read_text(encoding="utf-8"))
            if cached.identity != identity:
                return None
            validated = schema.model_validate(cached.output)
        except (OSError, ValueError, ValidationError):
            return None
        return validated, cached

    def save(
        self,
        *,
        identity: RequestIdentity,
        output: BaseModel,
        usage: dict[str, Any],
        latency_seconds: float,
        attempts: int,
        response_id: str | None,
    ) -> CachedResult:
        cached = CachedResult(
            identity=identity,
            output=output.model_dump(mode="json"),
            usage=usage,
            latency_seconds=latency_seconds,
            attempts=attempts,
            response_id=response_id,
            created_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        )
        path = self.path_for(identity)
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
        temporary.write_text(cached.model_dump_json(indent=2) + "\n", encoding="utf-8")
        os.replace(temporary, path)
        return cached
