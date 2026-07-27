from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from flowsec.llm import (
    CompletionResponse,
    FileResultCache,
    GenerationParameters,
    LLMRequest,
    LLMRunner,
    select_shard,
)


class ExampleOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    record_id: str
    label: Literal["benign", "malicious"]
    confidence: float = Field(ge=0, le=1)


class FakeTransport:
    def __init__(self) -> None:
        self.calls: list[str] = []
        self._lock = threading.Lock()

    def complete(
        self,
        *,
        prompt: str,
        model: str,
        generation: GenerationParameters,
    ) -> CompletionResponse:
        with self._lock:
            self.calls.append(prompt)
        if prompt.startswith("fail:"):
            raise RuntimeError("synthetic provider failure")
        record_id = prompt.split(":", 1)[1].split("|", 1)[0]
        return CompletionResponse(
            text=(
                "validated output follows\n"
                + json.dumps(
                    {"record_id": record_id, "label": "benign", "confidence": 0.75}
                )
            ),
            usage={"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
            response_id=f"response-{record_id}",
        )


def make_runner(
    tmp_path: Path,
    transport: FakeTransport,
    *,
    model: str = "local-reviewer",
    runtime_identity: dict[str, object] | None = None,
    trace: bool = False,
    workers: int = 1,
) -> LLMRunner:
    return LLMRunner(
        transport=transport,
        model=model,
        generation=GenerationParameters(temperature=0, max_tokens=64),
        schema_version="example-v1",
        cache=FileResultCache(tmp_path / "cache"),
        runtime_identity=runtime_identity,
        max_workers=workers,
        max_retries=0,
        retry_delay_seconds=0,
        trace_dir=tmp_path / "trace" if trace else None,
    )


def test_resume_skips_only_compatible_cache(tmp_path: Path) -> None:
    transport = FakeTransport()
    runner = make_runner(tmp_path, transport)
    request = LLMRequest(record_id="flow-1", input_data={"bytes": 10}, prompt="ok:flow-1")

    first = runner.run([request], ExampleOutput)
    second = runner.run([request], ExampleOutput)

    assert first.api_calls == 1
    assert second.api_calls == 0
    assert second.successes[0].cache_hit
    assert transport.calls == ["ok:flow-1"]


def test_input_prompt_and_model_changes_invalidate_cache(tmp_path: Path) -> None:
    transport = FakeTransport()
    base = make_runner(tmp_path, transport)
    base.run(
        [LLMRequest(record_id="flow-1", input_data={"bytes": 10}, prompt="ok:flow-1")],
        ExampleOutput,
    )
    base.run(
        [LLMRequest(record_id="flow-1", input_data={"bytes": 11}, prompt="ok:flow-1")],
        ExampleOutput,
    )
    base.run(
        [LLMRequest(record_id="flow-1", input_data={"bytes": 11}, prompt="ok:flow-1|v2")],
        ExampleOutput,
    )
    other_model = make_runner(tmp_path, transport, model="other-reviewer")
    other_model.run(
        [LLMRequest(record_id="flow-1", input_data={"bytes": 11}, prompt="ok:flow-1")],
        ExampleOutput,
    )
    other_runtime = make_runner(
        tmp_path,
        transport,
        runtime_identity={"enable_thinking": True},
    )
    other_runtime.run(
        [LLMRequest(record_id="flow-1", input_data={"bytes": 11}, prompt="ok:flow-1")],
        ExampleOutput,
    )
    assert len(transport.calls) == 5


def test_failed_record_does_not_drop_success_and_traces_usage(tmp_path: Path) -> None:
    transport = FakeTransport()
    runner = make_runner(tmp_path, transport, trace=True, workers=2)
    outcome = runner.run(
        [
            LLMRequest(record_id="flow-ok", input_data={"x": 1}, prompt="ok:flow-ok"),
            LLMRequest(record_id="flow-fail", input_data={"x": 2}, prompt="fail:flow-fail"),
        ],
        ExampleOutput,
    )

    assert [item.record_id for item in outcome.successes] == ["flow-ok"]
    assert [item.record_id for item in outcome.failures] == ["flow-fail"]
    success = outcome.successes[0]
    assert success.usage["total_tokens"] == 15
    assert success.latency_seconds >= 0
    assert outcome.failures[0].latency_seconds >= 0
    assert outcome.api_calls == 2
    assert (tmp_path / "trace" / "validated_results.jsonl").exists()
    assert (tmp_path / "trace" / "failed_records.jsonl").exists()
    summary = json.loads((tmp_path / "trace" / "run_summary.json").read_text(encoding="utf-8"))
    assert summary["usage"]["total_tokens"] == 15
    assert summary["failures"] == 1


def test_concurrency_and_shards_have_no_duplicates_or_loss(tmp_path: Path) -> None:
    requests = [
        LLMRequest(record_id=f"flow-{index}", input_data={"index": index}, prompt=f"ok:flow-{index}")
        for index in range(24)
    ]
    shard_ids = []
    for shard_index in range(4):
        shard = select_shard(requests, num_shards=4, shard_index=shard_index)
        shard_ids.extend(item.record_id for item in shard)
    assert sorted(shard_ids) == sorted(item.record_id for item in requests)
    assert len(shard_ids) == len(set(shard_ids))

    transport = FakeTransport()
    outcome = make_runner(tmp_path, transport, workers=4).run(requests, ExampleOutput)
    assert not outcome.failures
    assert [item.record_id for item in outcome.successes] == [item.record_id for item in requests]
    assert len(transport.calls) == len(requests)
