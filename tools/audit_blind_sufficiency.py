#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import threading
import time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from flowsec.training.blind_audit import (
    BLIND_AUDIT_VERSION,
    BLIND_CLASSIFIER_PROMPT_VERSION,
    BLIND_PROMPT_DIGEST,
    audit_prompt_leakage,
    blind_request_digest,
    build_blind_classifier_request,
    classification_summary,
    load_frozen_records,
    rendered_blind_request,
    select_pair_diagnostic_sample,
    select_primary_diagnostic_sample,
    stratified_classification_summary,
    validate_blind_output,
    wilson_interval,
)
from flowsec.integrations.llm.transport import OpenAICompatibleChatTransport
from flowsec.training.contracts import content_digest
from flowsec.training.teacher import (
    DEEPSEEK_BASE_URL_DEFAULT,
    DEEPSEEK_MODEL_DEFAULT,
    DEEPSEEK_SECRET_ENV,
)


CORPUS_SHA256 = "5b845cf9e5886e5e44fd46562135ba3eb5907de65fd8faf5d9b8777253149123"
QWEN_MODEL = "Qwen/Qwen3.5-9B"
QWEN_BASE_URL = "http://127.0.0.1:8000/v1"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while block := handle.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def _atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False), encoding="utf-8"
    )
    os.replace(temporary, path)


def _artifact_paths(artifact_root: Path) -> dict[str, Path]:
    near = artifact_root / "near_pretraining_v1"
    production = artifact_root / "edge_split_revision_v2"
    return {
        "corpus": near / "sft_corpus/final/near_sft_corpus_v2.jsonl",
        "snapshots": near / "sft_corpus/evidence_snapshot_universe_v1.jsonl",
        "app": near / "application/captures",
        "payload": near / "sanitized_payload/captures",
        "rag_manifest": near / "rag/manifest.json",
        "preset": production / "manifests/edge_known_unknown_presets.json",
        "production_index": production / "sample_id_index/dataset=Edge-IIoTset/split=train",
    }


def _sidecar_ids(path: Path) -> set[str]:
    import pyarrow.parquet as pq

    values: set[str] = set()
    for shard in sorted(path.glob("*.parquet")):
        for value in pq.read_table(shard, columns=["sample_id"]).column("sample_id").to_pylist():
            if value:
                values.add(str(value))
    return values


def _backend_index(path: Path) -> dict[str, dict[str, str]]:
    import pyarrow.dataset as ds

    table = ds.dataset(path, format="parquet").to_table(
        columns=["sample_id", "capture_ref_hash", "source_sha256"]
    )
    return {
        str(row["sample_id"]): {
            "capture_ref_hash": str(row["capture_ref_hash"]),
            "source_sha256": str(row["source_sha256"]),
        }
        for row in table.to_pylist()
    }


def _candidate_labels(path: Path) -> tuple[str, ...]:
    value = json.loads(path.read_text(encoding="utf-8"))
    labels = tuple(str(item) for item in value["Near"]["K_known"])
    if len(labels) != 11 or len(set(labels)) != 11:
        raise ValueError("Near preset must contain exactly 11 unique K-known labels")
    return labels


def prepare(args: argparse.Namespace) -> int:
    paths = _artifact_paths(args.artifact_root)
    if _sha256(paths["corpus"]) != CORPUS_SHA256:
        raise ValueError("frozen corpus SHA256 changed")
    corpus, snapshots = load_frozen_records(paths["corpus"], paths["snapshots"])
    labels = _candidate_labels(paths["preset"])
    rag = json.loads(paths["rag_manifest"].read_text(encoding="utf-8"))
    selected = select_primary_diagnostic_sample(
        corpus,
        snapshots,
        candidate_labels=labels,
        application_ids=_sidecar_ids(paths["app"]),
        payload_ids=_sidecar_ids(paths["payload"]),
        knowledge_available=rag.get("status") == "PASS",
    )
    backend = _backend_index(paths["production_index"])
    leakage = Counter()
    request_digests: dict[str, str] = {}
    for sample in selected:
        request = build_blind_classifier_request(
            snapshots[sample.evidence_state_id].evidence,
            labels,
            provider="deepseek",
            base_url=os.environ.get("DEEPSEEK_BASE_URL", DEEPSEEK_BASE_URL_DEFAULT),
            model_id=os.environ.get("DEEPSEEK_MODEL", DEEPSEEK_MODEL_DEFAULT),
            timeout_seconds=90.0,
        )
        request_digests[sample.evidence_state_id] = blind_request_digest(request)
        meta = backend[sample.sample_id]
        leakage.update(
            audit_prompt_leakage(
                request,
                sample_id=sample.sample_id,
                dataset_identity="Edge-IIoTset",
                capture_ref_hash=meta["capture_ref_hash"],
                source_sha256=meta["source_sha256"],
            )
        )
    checks = {key: leakage[key] == 0 for key in sorted(leakage)}
    status = "PASS" if checks and all(checks.values()) else "FAIL"
    rows = [
        {
            **sample.model_dump(mode="json"),
            "input_digest": request_digests[sample.evidence_state_id],
        }
        for sample in selected
    ]
    manifest = {
        "status": status,
        "version": BLIND_AUDIT_VERSION,
        "prompt_version": BLIND_CLASSIFIER_PROMPT_VERSION,
        "prompt_digest": BLIND_PROMPT_DIGEST,
        "base_corpus_sha256": CORPUS_SHA256,
        "formal_corpus_modified": False,
        "seed": 20260812,
        "candidate_labels": list(labels),
        "primary_sample_count": len(rows),
        "class_distribution": dict(sorted(Counter(row["fine_label_backend_only"] for row in rows).items())),
        "stage_distribution": dict(sorted(Counter(row["stage_type"] for row in rows).items())),
        "teacher_sufficiency_distribution": dict(
            sorted(Counter("sufficient" if row["teacher_sufficient_backend_only"] else "insufficient" for row in rows).items())
        ),
        "no_next_action_count": sum(row["no_gap_matched_next_action_backend_only"] for row in rows),
        "prompt_leakage_audit_count": len(rows),
        "prompt_leakage_counts": dict(sorted(leakage.items())),
        "prompt_leakage_checks": checks,
        "samples": rows,
    }
    manifest["manifest_digest"] = content_digest(manifest)
    _atomic_json(args.output_root / "primary_sample_manifest.json", manifest)
    print(json.dumps({key: value for key, value in manifest.items() if key != "samples"}, indent=2, sort_keys=True))
    print(f"PROMPT_LEAKAGE_GATE={status}")
    return 0 if status == "PASS" else 2


def _load_primary_context(
    args: argparse.Namespace,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    manifest_path = args.output_root / "primary_sample_manifest.json"
    if not manifest_path.is_file():
        raise RuntimeError("run prepare before provider execution")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("status") != "PASS":
        raise RuntimeError("PROMPT_LEAKAGE_GATE is not PASS")
    paths = _artifact_paths(args.artifact_root)
    if _sha256(paths["corpus"]) != CORPUS_SHA256:
        raise ValueError("frozen corpus SHA256 changed")
    corpus, snapshots = load_frozen_records(paths["corpus"], paths["snapshots"])
    records = {item.evidence_state_id: item for item in corpus}
    expected_ids = {str(row["evidence_state_id"]) for row in manifest["samples"]}
    if expected_ids - snapshots.keys() or expected_ids - records.keys():
        raise ValueError("diagnostic sample no longer matches frozen assets")
    return manifest, snapshots, records


def _provider_settings(args: argparse.Namespace) -> dict[str, Any]:
    if args.provider == "deepseek":
        key = os.environ.get(DEEPSEEK_SECRET_ENV)
        if not key:
            return {"status": "BLOCKED", "reason": "NO_API_KEY"}
        return {
            "status": "READY",
            "api_key": key,
            "base_url": os.environ.get("DEEPSEEK_BASE_URL", DEEPSEEK_BASE_URL_DEFAULT),
            "model_id": os.environ.get("DEEPSEEK_MODEL", DEEPSEEK_MODEL_DEFAULT),
            "local_qwen": False,
        }
    return {
        "status": "READY",
        "api_key": "EMPTY",
        "base_url": args.qwen_base_url,
        "model_id": args.qwen_model,
        "local_qwen": True,
    }


def _cached_result(
    path: Path,
    *,
    input_digest: str,
    candidate_labels: tuple[str, ...],
    evidence: tuple[Any, ...],
) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    value = json.loads(path.read_text(encoding="utf-8"))
    if value.get("status") != "PASS" or value.get("input_digest") != input_digest:
        return None
    validate_blind_output(
        value["output"], candidate_labels=candidate_labels, evidence=evidence
    )
    return value

def run_provider(args: argparse.Namespace) -> int:
    manifest, snapshots, _records = _load_primary_context(args)
    settings = _provider_settings(args)
    provider_root = args.output_root / args.provider
    if settings["status"] != "READY":
        blocked = {
            "status": "BLOCKED",
            "provider": args.provider,
            "reason": settings["reason"],
            "new_requests": 0,
            "formal_corpus_modified": False,
        }
        _atomic_json(provider_root / "summary.json", blocked)
        print(f"{args.provider.upper()}_PROVIDER_BLOCKED={settings['reason']}")
        return 3

    labels = tuple(str(item) for item in manifest["candidate_labels"])
    transport = OpenAICompatibleChatTransport(
        api_key=str(settings["api_key"]),
        max_input_tokens=16384,
        max_output_tokens=320,
        max_latency_seconds=args.timeout,
        trust_env=not bool(settings["local_qwen"]),
    )
    records_root = provider_root / "records"
    progress_lock = threading.Lock()
    completed = 0
    new_requests = 0

    def execute_one(sample_row: dict[str, Any]) -> dict[str, Any]:
        nonlocal completed, new_requests
        state_id = str(sample_row["evidence_state_id"])
        snapshot = snapshots[state_id]
        request = build_blind_classifier_request(
            snapshot.evidence,
            labels,
            provider=args.provider,
            base_url=str(settings["base_url"]),
            model_id=str(settings["model_id"]),
            timeout_seconds=args.timeout,
            local_qwen=bool(settings["local_qwen"]),
        )
        input_digest = blind_request_digest(request)
        expected_digest = str(sample_row["input_digest"])
        if args.provider == "deepseek" and input_digest != expected_digest:
            raise ValueError("executed DeepSeek request differs from leak-audited request")
        record_path = records_root / f"{state_id}.json"
        cached = _cached_result(
            record_path,
            input_digest=input_digest,
            candidate_labels=labels,
            evidence=snapshot.evidence,
        )
        if cached is not None:
            with progress_lock:
                completed += 1
            return cached

        last_failure = "Unknown"
        for attempt in range(1, args.max_attempts + 1):
            with progress_lock:
                new_requests += 1
            try:
                response = transport.send(request)
                output = validate_blind_output(
                    response.structured_payload or {},
                    candidate_labels=labels,
                    evidence=snapshot.evidence,
                )
                record = {
                    "status": "PASS",
                    "provider": args.provider,
                    "model_id": response.model_id or settings["model_id"],
                    "evidence_state_id": state_id,
                    "input_digest": input_digest,
                    "prompt_version": BLIND_CLASSIFIER_PROMPT_VERSION,
                    "output": output.model_dump(mode="json"),
                    "output_digest": content_digest(output.model_dump(mode="json")),
                    "request_id": response.request_id,
                    "usage": response.usage.model_dump(mode="json"),
                    "attempts": attempt,
                    "timestamp_utc": datetime.now(UTC).isoformat(),
                }
                _atomic_json(record_path, record)
                with progress_lock:
                    completed += 1
                    if completed % 25 == 0 or completed == len(manifest["samples"]):
                        print(
                            f"{args.provider.upper()}_PROGRESS={completed}/{len(manifest['samples'])}",
                            file=sys.stderr,
                            flush=True,
                        )
                return record
            except Exception as exc:
                last_failure = type(exc).__name__
                if attempt < args.max_attempts:
                    time.sleep(min(2**attempt, 4))
        failed = {
            "status": "QUARANTINE",
            "provider": args.provider,
            "model_id": settings["model_id"],
            "evidence_state_id": state_id,
            "input_digest": input_digest,
            "attempts": args.max_attempts,
            "safe_failure_type": last_failure,
            "timestamp_utc": datetime.now(UTC).isoformat(),
        }
        _atomic_json(record_path, failed)
        with progress_lock:
            completed += 1
        return failed

    with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
        futures = [pool.submit(execute_one, row) for row in manifest["samples"]]
        provider_records = [future.result() for future in as_completed(futures)]
    by_state = {str(item["evidence_state_id"]): item for item in provider_records}
    scored: list[dict[str, Any]] = []
    for sample in manifest["samples"]:
        result = by_state[str(sample["evidence_state_id"])]
        output = result.get("output") or {}
        label = str(sample["fine_label_backend_only"])
        scored.append(
            {
                **sample,
                "status": result["status"],
                "output": output,
                "top1_correct": output.get("top1") == label,
                "top2_contains_gt": label in {output.get("top1"), output.get("top2")},
                "confidence": output.get("confidence"),
                "attempts": result.get("attempts"),
            }
        )
    summary = _summarize_provider(args.provider, scored, new_requests)
    _atomic_json(provider_root / "scored_results.json", {"rows": scored})
    _atomic_json(provider_root / "summary.json", summary)
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if summary["status"] == "PASS" else 4


def _summarize_provider(
    provider: str, rows: list[dict[str, Any]], new_requests: int
) -> dict[str, Any]:
    pass_count = sum(row["status"] == "PASS" for row in rows)
    teacher_cell = Counter(
        (
            "teacher_sufficient" if row["teacher_sufficient_backend_only"] else "teacher_insufficient",
            "classifier_correct" if row["top1_correct"] else "classifier_incorrect",
        )
        for row in rows
        if row["status"] == "PASS"
    )
    return {
        "status": "PASS" if pass_count == len(rows) else "PASS_WITH_QUARANTINE",
        "provider": provider,
        "requested": len(rows),
        "valid_count": pass_count,
        "quarantine_count": len(rows) - pass_count,
        "new_requests": new_requests,
        "all": classification_summary(rows),
        "by_teacher_sufficiency": stratified_classification_summary(
            rows, "teacher_sufficient_backend_only"
        ),
        "by_no_next_action": stratified_classification_summary(
            rows, "no_gap_matched_next_action_backend_only"
        ),
        "by_class": stratified_classification_summary(rows, "fine_label_backend_only"),
        "by_stage": stratified_classification_summary(rows, "stage_type"),
        "teacher_sufficient_rate_by_stage": {
            stage: sum(bool(row["teacher_sufficient_backend_only"]) for row in values)
            / len(values)
            for stage, values in sorted(
                (
                    stage,
                    [
                        row
                        for row in rows
                        if row["status"] == "PASS" and row["stage_type"] == stage
                    ],
                )
                for stage in {row["stage_type"] for row in rows}
            )
            if values
        },
        "four_cell": {" / ".join(key): value for key, value in sorted(teacher_cell.items())},
        "high_confidence_teacher_insufficient_correct": sum(
            row["status"] == "PASS"
            and not row["teacher_sufficient_backend_only"]
            and row["top1_correct"]
            and row["confidence"] == "high"
            for row in rows
            and bool(row["output"].get("supporting_evidence_ids"))
        ),
        "formal_corpus_modified": False,
    }

def inspect_results(args: argparse.Namespace) -> int:
    summaries: dict[str, Any] = {}
    scored: dict[str, list[dict[str, Any]]] = {}
    for provider in ("deepseek", "qwen"):
        summary_path = args.output_root / provider / "summary.json"
        scored_path = args.output_root / provider / "scored_results.json"
        if summary_path.is_file():
            summaries[provider] = json.loads(summary_path.read_text(encoding="utf-8"))
        if scored_path.is_file():
            scored[provider] = json.loads(scored_path.read_text(encoding="utf-8"))["rows"]
    comparison: dict[str, Any] = {
        "status": "BLOCKED" if set(scored) != {"deepseek", "qwen"} else "PASS",
        "providers_available": sorted(scored),
        "provider_summaries": summaries,
        "formal_corpus_modified": False,
    }
    if set(scored) == {"deepseek", "qwen"}:
        deepseek = {row["evidence_state_id"]: row for row in scored["deepseek"]}
        qwen = {row["evidence_state_id"]: row for row in scored["qwen"]}
        common = sorted(deepseek.keys() & qwen.keys())
        valid = [
            state_id
            for state_id in common
            if deepseek[state_id]["status"] == qwen[state_id]["status"] == "PASS"
        ]
        top1_agree = sum(
            deepseek[state_id]["output"]["top1"] == qwen[state_id]["output"]["top1"]
            for state_id in valid
        )
        cells = Counter(
            (
                "both_correct"
                if deepseek[state_id]["top1_correct"] and qwen[state_id]["top1_correct"]
                else "deepseek_only_correct"
                if deepseek[state_id]["top1_correct"]
                else "qwen_only_correct"
                if qwen[state_id]["top1_correct"]
                else "both_wrong"
            )
            for state_id in valid
        )
        teacher_insufficient = [
            state_id
            for state_id in valid
            if not deepseek[state_id]["teacher_sufficient_backend_only"]
        ]
        strong = [
            state_id
            for state_id in teacher_insufficient
            if deepseek[state_id]["top1_correct"]
            and qwen[state_id]["top1_correct"]
        ]
        comparison["cross_model"] = {
            "n": len(valid),
            "top1_agreement_count": top1_agree,
            "top1_agreement_rate": top1_agree / len(valid) if valid else None,
            "correctness_cells": dict(sorted(cells.items())),
            "both_correct_rate": cells["both_correct"] / len(valid) if valid else None,
            "teacher_insufficient_common_valid_count": len(teacher_insufficient),
            "strong_teacher_contradiction_count": len(strong),
            "strong_teacher_contradiction_rate": (
                len(strong) / len(teacher_insufficient)
                if teacher_insufficient
                else None
            ),
            "strong_teacher_contradiction_state_ids_backend_only": strong,
        }
    comparison["comparison_digest"] = content_digest(comparison)
    _atomic_json(args.output_root / "cross_model_summary.json", comparison)
    print(json.dumps(comparison, indent=2, sort_keys=True))
    return 0 if comparison["status"] == "PASS" else 5


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--artifact-root",
        type=Path,
        default=Path("/root/autodl-tmp/processed"),
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=Path("/root/autodl-tmp/experiments/blind_sufficiency_calibration_v1"),
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("prepare").set_defaults(function=prepare)
    run = subparsers.add_parser("run-provider")
    run.add_argument("--provider", choices=("deepseek", "qwen"), required=True)
    run.add_argument("--concurrency", type=int, default=12)
    run.add_argument("--max-attempts", type=int, default=2)
    run.add_argument("--timeout", type=float, default=90.0)
    run.add_argument("--qwen-base-url", default=QWEN_BASE_URL)
    run.add_argument("--qwen-model", default=QWEN_MODEL)
    run.set_defaults(function=run_provider)
    subparsers.add_parser("inspect").set_defaults(function=inspect_results)
    return parser


def main() -> int:
    args = _parser().parse_args()
    if getattr(args, "concurrency", 1) < 1 or getattr(args, "concurrency", 1) > 16:
        raise ValueError("concurrency must be in [1, 16]")
    if getattr(args, "max_attempts", 1) not in (1, 2):
        raise ValueError("max_attempts must be 1 or 2")
    return int(args.function(args))


if __name__ == "__main__":
    raise SystemExit(main())
