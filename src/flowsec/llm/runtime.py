from __future__ import annotations

import hashlib
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Protocol, TypeVar

from pydantic import BaseModel, ConfigDict, Field

from .cache import FileResultCache
from .fingerprint import GenerationParameters, RequestIdentity, build_request_identity
from .structured_output import validate_structured_output
from .trace import write_json, write_jsonl


SchemaT = TypeVar("SchemaT", bound=BaseModel)


class LLMRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    record_id: str = Field(min_length=1)
    input_data: Any
    prompt: str = Field(min_length=1)


class CompletionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str
    usage: dict[str, Any] = Field(default_factory=dict)
    response_id: str | None = None


class CompletionTransport(Protocol):
    def complete(
        self,
        *,
        prompt: str,
        model: str,
        generation: GenerationParameters,
    ) -> CompletionResponse:
        ...


class RecordSuccess(BaseModel):
    model_config = ConfigDict(extra="forbid")

    record_id: str
    identity: RequestIdentity
    output: dict[str, Any]
    cache_hit: bool
    attempts: int = Field(ge=0)
    latency_seconds: float = Field(ge=0)
    usage: dict[str, Any] = Field(default_factory=dict)
    response_id: str | None = None


class FailedRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    record_id: str
    identity: RequestIdentity
    attempts: int = Field(ge=1)
    latency_seconds: float = Field(ge=0)
    error_type: str
    error: str


class RunOutcome(BaseModel):
    model_config = ConfigDict(extra="forbid")

    successes: list[RecordSuccess]
    failures: list[FailedRecord]
    api_calls: int = Field(ge=0)

    @property
    def cache_hits(self) -> int:
        return sum(item.cache_hit for item in self.successes)


class OpenAIChatTransport:
    """Thread-local OpenAI-compatible chat transport."""

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        timeout_seconds: float,
        extra_body: dict[str, Any] | None = None,
    ):
        self.base_url = base_url
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds
        self.extra_body = extra_body
        self._local = threading.local()

    def _client(self) -> Any:
        client = getattr(self._local, "client", None)
        if client is None:
            from openai import OpenAI

            client = OpenAI(
                base_url=self.base_url,
                api_key=self.api_key,
                timeout=self.timeout_seconds,
            )
            self._local.client = client
        return client

    def complete(
        self,
        *,
        prompt: str,
        model: str,
        generation: GenerationParameters,
    ) -> CompletionResponse:
        request: dict[str, Any] = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
            **generation.request_kwargs(),
        }
        if self.extra_body:
            request["extra_body"] = self.extra_body
        response = self._client().chat.completions.create(**request)
        usage = getattr(response, "usage", None)
        if usage is None:
            usage_dict: dict[str, Any] = {}
        elif hasattr(usage, "model_dump"):
            usage_dict = usage.model_dump()
        elif isinstance(usage, dict):
            usage_dict = usage
        else:
            usage_dict = {
                key: getattr(usage, key)
                for key in ("prompt_tokens", "completion_tokens", "total_tokens")
                if getattr(usage, key, None) is not None
            }
        return CompletionResponse(
            text=response.choices[0].message.content or "",
            usage=usage_dict,
            response_id=getattr(response, "id", None),
        )


def select_shard(
    requests: list[LLMRequest],
    *,
    num_shards: int,
    shard_index: int,
) -> list[LLMRequest]:
    if num_shards < 1:
        raise ValueError("num_shards must be at least 1")
    if not 0 <= shard_index < num_shards:
        raise ValueError("shard_index must satisfy 0 <= shard_index < num_shards")
    if num_shards == 1:
        return list(requests)

    def bucket(record_id: str) -> int:
        digest = hashlib.sha256(record_id.encode("utf-8")).digest()
        return int.from_bytes(digest[:8], "big") % num_shards

    return [request for request in requests if bucket(request.record_id) == shard_index]


class LLMRunner:
    """Concurrent structured inference with validated per-record resume."""

    def __init__(
        self,
        *,
        transport: CompletionTransport,
        model: str,
        generation: GenerationParameters,
        schema_version: str,
        cache: FileResultCache,
        runtime_identity: Any | None = None,
        max_workers: int = 1,
        max_retries: int = 2,
        retry_delay_seconds: float = 2,
        trace_dir: Path | None = None,
    ):
        if max_workers < 1:
            raise ValueError("max_workers must be at least 1")
        if max_retries < 0:
            raise ValueError("max_retries cannot be negative")
        if retry_delay_seconds < 0:
            raise ValueError("retry_delay_seconds cannot be negative")
        self.transport = transport
        self.model = model
        self.generation = generation
        self.schema_version = schema_version
        self.cache = cache
        self.runtime_identity = runtime_identity or {}
        self.max_workers = max_workers
        self.max_retries = max_retries
        self.retry_delay_seconds = retry_delay_seconds
        self.trace_dir = Path(trace_dir) if trace_dir is not None else None

    def _identity(self, request: LLMRequest) -> RequestIdentity:
        return build_request_identity(
            record_id=request.record_id,
            input_data=request.input_data,
            prompt=request.prompt,
            model=self.model,
            generation=self.generation,
            runtime_identity=self.runtime_identity,
            schema_version=self.schema_version,
        )

    def _run_one(
        self,
        request: LLMRequest,
        output_schema: type[SchemaT],
    ) -> RecordSuccess | FailedRecord:
        identity = self._identity(request)
        cached = self.cache.load(identity, output_schema)
        if cached is not None:
            output, entry = cached
            return RecordSuccess(
                record_id=request.record_id,
                identity=identity,
                output=output.model_dump(mode="json"),
                cache_hit=True,
                attempts=0,
                latency_seconds=entry.latency_seconds,
                usage=entry.usage,
                response_id=entry.response_id,
            )

        total_started = time.perf_counter()
        attempts = self.max_retries + 1
        error: Exception | None = None
        for attempt in range(1, attempts + 1):
            try:
                response = self.transport.complete(
                    prompt=request.prompt,
                    model=self.model,
                    generation=self.generation,
                )
                output = validate_structured_output(response.text, output_schema)
                output_record_id = getattr(output, "record_id", request.record_id)
                if output_record_id != request.record_id:
                    raise ValueError(
                        f"record_id mismatch: expected {request.record_id!r}, "
                        f"received {output_record_id!r}"
                    )
                latency = time.perf_counter() - total_started
                self.cache.save(
                    identity=identity,
                    output=output,
                    usage=response.usage,
                    latency_seconds=latency,
                    attempts=attempt,
                    response_id=response.response_id,
                )
                return RecordSuccess(
                    record_id=request.record_id,
                    identity=identity,
                    output=output.model_dump(mode="json"),
                    cache_hit=False,
                    attempts=attempt,
                    latency_seconds=latency,
                    usage=response.usage,
                    response_id=response.response_id,
                )
            except Exception as exc:  # Providers and validators expose different exception types.
                error = exc
                if attempt < attempts and self.retry_delay_seconds:
                    time.sleep(self.retry_delay_seconds)

        assert error is not None
        return FailedRecord(
            record_id=request.record_id,
            identity=identity,
            attempts=attempts,
            latency_seconds=time.perf_counter() - total_started,
            error_type=type(error).__name__,
            error=str(error)[:1000],
        )

    def run(
        self,
        requests: list[LLMRequest],
        output_schema: type[SchemaT],
    ) -> RunOutcome:
        ids = [request.record_id for request in requests]
        if len(ids) != len(set(ids)):
            raise ValueError("record_id values must be unique within one run")
        order = {record_id: index for index, record_id in enumerate(ids)}
        records: list[RecordSuccess | FailedRecord] = []

        if self.max_workers == 1:
            records = [self._run_one(request, output_schema) for request in requests]
        else:
            with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                futures = {
                    executor.submit(self._run_one, request, output_schema): request.record_id
                    for request in requests
                }
                for future in as_completed(futures):
                    records.append(future.result())

        records.sort(key=lambda item: order[item.record_id])
        successes = [item for item in records if isinstance(item, RecordSuccess)]
        failures = [item for item in records if isinstance(item, FailedRecord)]
        api_calls = sum(item.attempts for item in successes if not item.cache_hit) + sum(
            item.attempts for item in failures
        )
        outcome = RunOutcome(successes=successes, failures=failures, api_calls=api_calls)
        if self.trace_dir is not None:
            self._write_traces(outcome)
        return outcome

    def _write_traces(self, outcome: RunOutcome) -> None:
        assert self.trace_dir is not None
        write_jsonl(
            self.trace_dir / "validated_results.jsonl",
            (item.model_dump(mode="json") for item in outcome.successes),
        )
        write_jsonl(
            self.trace_dir / "failed_records.jsonl",
            (item.model_dump(mode="json") for item in outcome.failures),
        )
        write_json(
            self.trace_dir / "run_summary.json",
            {
                "model": self.model,
                "schema_version": self.schema_version,
                "records": len(outcome.successes) + len(outcome.failures),
                "successes": len(outcome.successes),
                "failures": len(outcome.failures),
                "cache_hits": outcome.cache_hits,
                "api_calls": outcome.api_calls,
                "usage": _sum_usage(item.usage for item in outcome.successes),
                "success_latency_seconds": sum(
                    item.latency_seconds for item in outcome.successes
                ),
                "failure_latency_seconds": sum(
                    item.latency_seconds for item in outcome.failures
                ),
                "latency_seconds": sum(
                    item.latency_seconds for item in [*outcome.successes, *outcome.failures]
                ),
            },
        )


def _sum_usage(rows: Any) -> dict[str, int]:
    totals = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    for usage in rows:
        for key in totals:
            value = usage.get(key)
            if isinstance(value, int) and not isinstance(value, bool):
                totals[key] += value
    return totals
