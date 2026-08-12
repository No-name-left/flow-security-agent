#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import threading
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from flowsec.integrations.llm.transport import OpenAICompatibleChatTransport
from flowsec.training.blind_audit import (
    BLIND_AUDIT_VERSION,
    BLIND_CLASSIFIER_PROMPT_VERSION,
    audit_prompt_leakage,
    blind_request_digest,
    build_blind_classifier_request,
    load_frozen_records,
    pair_transition_stratum,
    select_pair_diagnostic_sample,
    validate_blind_output,
)
from flowsec.training.contracts import content_digest
from flowsec.training.teacher import (
    DEEPSEEK_BASE_URL_DEFAULT,
    DEEPSEEK_MODEL_DEFAULT,
    DEEPSEEK_SECRET_ENV,
)


CORPUS_SHA256 = "5b845cf9e5886e5e44fd46562135ba3eb5907de65fd8faf5d9b8777253149123"
MAX_DEEPSEEK_REQUESTS = 530


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


def _paths(args: argparse.Namespace) -> dict[str, Path]:
    near = args.artifact_root / "near_pretraining_v1"
    production = args.artifact_root / "edge_split_revision_v2"
    return {
        "corpus": near / "sft_corpus/final/near_sft_corpus_v2.jsonl",
        "snapshots": near / "sft_corpus/evidence_snapshot_universe_v1.jsonl",
        "preset": production / "manifests/edge_known_unknown_presets.json",
        "production_index": production / "sample_id_index/dataset=Edge-IIoTset/split=train",
    }


def _labels(path: Path) -> tuple[str, ...]:
    value = json.loads(path.read_text(encoding="utf-8"))
    labels = tuple(str(item) for item in value["Near"]["K_known"])
    if len(labels) != 11 or len(set(labels)) != 11:
        raise ValueError("Near preset must contain 11 unique K-known labels")
    return labels


def _backend_index(path: Path) -> dict[str, dict[str, str]]:
    import pyarrow.dataset as ds

    rows = ds.dataset(path, format="parquet").to_table(
        columns=["sample_id", "capture_ref_hash", "source_sha256"]
    ).to_pylist()
    return {
        str(row["sample_id"]): {
            "capture_ref_hash": str(row["capture_ref_hash"]),
            "source_sha256": str(row["source_sha256"]),
        }
        for row in rows
    }


def prepare(args: argparse.Namespace) -> int:
    paths = _paths(args)
    if _sha256(paths["corpus"]) != CORPUS_SHA256:
        raise ValueError("frozen corpus SHA256 changed")
    corpus, snapshots = load_frozen_records(paths["corpus"], paths["snapshots"])
    labels = _labels(paths["preset"])
    pairs = select_pair_diagnostic_sample(corpus)
    backend = _backend_index(paths["production_index"])
    universe: Counter[str] = Counter()
    by_sample: dict[str, list[Any]] = defaultdict(list)
    for record in corpus:
        by_sample[record.sample_id].append(record)
    for before in (item for item in corpus if item.state_role == "auxiliary"):
        after = next(item for item in by_sample[before.sample_id] if item.state_role == "primary")
        universe[pair_transition_stratum(before, after)] += 1

    leakage: Counter[str] = Counter()
    rows: list[dict[str, Any]] = []
    base_url = os.environ.get("DEEPSEEK_BASE_URL", DEEPSEEK_BASE_URL_DEFAULT)
    model_id = os.environ.get("DEEPSEEK_MODEL", DEEPSEEK_MODEL_DEFAULT)
    for pair in pairs:
        row = pair.model_dump(mode="json")
        meta = backend[pair.sample_id]
        for phase, state_id in (
            ("before", pair.before_evidence_state_id),
            ("after", pair.after_evidence_state_id),
        ):
            request = build_blind_classifier_request(
                snapshots[state_id].evidence,
                labels,
                provider="deepseek",
                base_url=base_url,
                model_id=model_id,
                timeout_seconds=90.0,
            )
            row[f"{phase}_input_digest"] = blind_request_digest(request)
            leakage.update(
                audit_prompt_leakage(
                    request,
                    sample_id=pair.sample_id,
                    dataset_identity="Edge-IIoTset",
                    capture_ref_hash=meta["capture_ref_hash"],
                    source_sha256=meta["source_sha256"],
                )
            )
        rows.append(row)
    status = "PASS" if leakage and all(value == 0 for value in leakage.values()) else "FAIL"
    manifest = {
        "status": status,
        "version": BLIND_AUDIT_VERSION,
        "base_corpus_sha256": CORPUS_SHA256,
        "formal_corpus_modified": False,
        "seed": 20260812,
        "pair_count": len(rows),
        "state_request_count": len(rows) * 2,
        "quota_adjustment": "99 pairs instead of 100 because primary used 332 requests; 198 remain under the hard 530 cap",
        "transition_universe": dict(sorted(universe.items())),
        "sample_distribution": dict(
            sorted(Counter(row["transition_stratum_backend_only"] for row in rows).items())
        ),
        "prompt_leakage_audit_count": len(rows) * 2,
        "prompt_leakage_counts": dict(sorted(leakage.items())),
        "candidate_labels": list(labels),
        "pairs": rows,
    }
    manifest["manifest_digest"] = content_digest(manifest)
    _atomic_json(args.output_root / "pairs/pair_sample_manifest.json", manifest)
    print(json.dumps({key: value for key, value in manifest.items() if key != "pairs"}, indent=2, sort_keys=True))
    return 0 if status == "PASS" else 2


def _valid_cache(
    path: Path,
    *,
    digest: str,
    labels: tuple[str, ...],
    evidence: tuple[Any, ...],
) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    value = json.loads(path.read_text(encoding="utf-8"))
    if value.get("status") != "PASS" or value.get("input_digest") != digest:
        return None
    validate_blind_output(value["output"], candidate_labels=labels, evidence=evidence)
    return value


def run(args: argparse.Namespace) -> int:
    key = os.environ.get(DEEPSEEK_SECRET_ENV)
    if not key:
        raise RuntimeError("DEEPSEEK_PROVIDER_BLOCKED=NO_API_KEY")
    manifest_path = args.output_root / "pairs/pair_sample_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("status") != "PASS":
        raise RuntimeError("pair prompt leakage gate is not PASS")
    paths = _paths(args)
    if _sha256(paths["corpus"]) != CORPUS_SHA256:
        raise ValueError("frozen corpus SHA256 changed")
    _corpus, snapshots = load_frozen_records(paths["corpus"], paths["snapshots"])
    labels = tuple(str(item) for item in manifest["candidate_labels"])
    primary_summary = json.loads(
        (args.output_root / "deepseek/summary.json").read_text(encoding="utf-8")
    )
    primary_requests = int(primary_summary["new_requests"])
    request_budget = MAX_DEEPSEEK_REQUESTS - primary_requests
    if request_budget < 0 or manifest["state_request_count"] > request_budget:
        raise RuntimeError("DeepSeek request budget is insufficient for fixed pair sample")
    transport = OpenAICompatibleChatTransport(
        api_key=key,
        max_input_tokens=16384,
        max_output_tokens=320,
        max_latency_seconds=args.timeout,
        trust_env=False,
    )
    base_url = os.environ.get("DEEPSEEK_BASE_URL", DEEPSEEK_BASE_URL_DEFAULT)
    model_id = os.environ.get("DEEPSEEK_MODEL", DEEPSEEK_MODEL_DEFAULT)
    records_root = args.output_root / "pairs/deepseek/records"
    primary_root = args.output_root / "deepseek/records"
    work: list[dict[str, Any]] = []
    results: dict[str, dict[str, Any]] = {}
    reused_primary = 0
    for pair in manifest["pairs"]:
        for phase, state_key, digest_key in (
            ("before", "before_evidence_state_id", "before_input_digest"),
            ("after", "after_evidence_state_id", "after_input_digest"),
        ):
            state_id = str(pair[state_key])
            digest = str(pair[digest_key])
            evidence = snapshots[state_id].evidence
            pair_cache = _valid_cache(
                records_root / f"{state_id}.json",
                digest=digest,
                labels=labels,
                evidence=evidence,
            )
            primary_cache = _valid_cache(
                primary_root / f"{state_id}.json",
                digest=digest,
                labels=labels,
                evidence=evidence,
            )
            cached = pair_cache or primary_cache
            if cached is not None:
                results[state_id] = cached
                reused_primary += int(pair_cache is None and primary_cache is not None)
            else:
                work.append({"state_id": state_id, "digest": digest, "phase": phase})
    if len(work) > request_budget:
        raise RuntimeError("uncached pair work exceeds remaining DeepSeek request budget")

    lock = threading.Lock()
    new_requests = 0
    def execute(item: dict[str, Any]) -> dict[str, Any]:
        nonlocal new_requests
        state_id = item["state_id"]
        snapshot = snapshots[state_id]
        request = build_blind_classifier_request(
            snapshot.evidence,
            labels,
            provider="deepseek",
            base_url=base_url,
            model_id=model_id,
            timeout_seconds=args.timeout,
        )
        if blind_request_digest(request) != item["digest"]:
            raise ValueError("pair DeepSeek request differs from leak-audited request")
        with lock:
            if new_requests >= request_budget:
                raise RuntimeError("DeepSeek hard request budget exhausted")
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
                "provider": "deepseek",
                "model_id": response.model_id or model_id,
                "evidence_state_id": state_id,
                "input_digest": item["digest"],
                "prompt_version": BLIND_CLASSIFIER_PROMPT_VERSION,
                "output": output.model_dump(mode="json"),
                "request_id": response.request_id,
                "usage": response.usage.model_dump(mode="json"),
                "attempts": 1,
                "timestamp_utc": datetime.now(UTC).isoformat(),
            }
        except Exception as exc:
            record = {
                "status": "QUARANTINE",
                "provider": "deepseek",
                "model_id": model_id,
                "evidence_state_id": state_id,
                "input_digest": item["digest"],
                "safe_failure_type": type(exc).__name__,
                "attempts": 1,
                "timestamp_utc": datetime.now(UTC).isoformat(),
            }
        _atomic_json(records_root / f"{state_id}.json", record)
        return record

    with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
        futures = {pool.submit(execute, item): item for item in work}
        for completed, future in enumerate(as_completed(futures), start=1):
            record = future.result()
            results[str(record["evidence_state_id"])] = record
            if completed % 25 == 0 or completed == len(work):
                print(f"PAIR_DEEPSEEK_PROGRESS={completed}/{len(work)}", flush=True)

    scored: list[dict[str, Any]] = []
    for pair in manifest["pairs"]:
        label = str(pair["fine_label_backend_only"])
        before = results[str(pair["before_evidence_state_id"])]
        after = results[str(pair["after_evidence_state_id"])]
        before_output = before.get("output") or {}
        after_output = after.get("output") or {}
        scored.append({
            **pair,
            "status": "PASS" if before["status"] == after["status"] == "PASS" else "QUARANTINE",
            "before_output": before_output,
            "after_output": after_output,
            "before_correct": before_output.get("top1") == label,
            "after_correct": after_output.get("top1") == label,
        })
    summary = _pair_summary(scored)
    summary.update({
        "primary_deepseek_requests": primary_requests,
        "pair_new_requests": new_requests,
        "total_deepseek_requests": primary_requests + new_requests,
        "primary_cache_reused": reused_primary,
        "hard_request_cap": MAX_DEEPSEEK_REQUESTS,
        "formal_corpus_modified": False,
    })
    if summary["total_deepseek_requests"] > MAX_DEEPSEEK_REQUESTS:
        raise RuntimeError("DeepSeek hard request cap violated")
    _atomic_json(args.output_root / "pairs/deepseek/scored_results.json", {"rows": scored})
    _atomic_json(args.output_root / "pairs/deepseek/summary.json", summary)
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if summary["status"] == "PASS" else 4


def _pair_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    valid = [row for row in rows if row["status"] == "PASS"]
    changes: Counter[str] = Counter()
    confidence: Counter[str] = Counter()
    by_stratum: dict[str, Counter[str]] = defaultdict(Counter)
    for row in valid:
        before = bool(row["before_correct"])
        after = bool(row["after_correct"])
        key = ("correct" if before else "wrong") + "_to_" + ("correct" if after else "wrong")
        changes[key] += 1
        by_stratum[str(row["transition_stratum_backend_only"])][key] += 1
        confidence[
            f"{row['before_output'].get('confidence')}_to_{row['after_output'].get('confidence')}"
        ] += 1
    return {
        "status": "PASS" if len(valid) == len(rows) else "PASS_WITH_QUARANTINE",
        "pair_count": len(rows),
        "valid_pair_count": len(valid),
        "quarantine_pair_count": len(rows) - len(valid),
        "classification_changes": dict(sorted(changes.items())),
        "before_already_correct_and_stable_count": changes["correct_to_correct"],
        "before_already_correct_and_stable_rate": changes["correct_to_correct"] / len(valid) if valid else None,
        "before_wrong_after_correct_count": changes["wrong_to_correct"],
        "before_wrong_after_correct_rate": changes["wrong_to_correct"] / len(valid) if valid else None,
        "confidence_transitions": dict(sorted(confidence.items())),
        "by_transition_stratum": {
            key: dict(sorted(value.items())) for key, value in sorted(by_stratum.items())
        },
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--artifact-root", type=Path, default=Path("/root/autodl-tmp/processed")
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=Path("/root/autodl-tmp/experiments/blind_sufficiency_calibration_v1"),
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("prepare").set_defaults(function=prepare)
    runner = subparsers.add_parser("run")
    runner.add_argument("--concurrency", type=int, default=12)
    runner.add_argument("--timeout", type=float, default=90.0)
    runner.set_defaults(function=run)
    return parser


def main() -> int:
    args = _parser().parse_args()
    if getattr(args, "concurrency", 1) < 1 or getattr(args, "concurrency", 1) > 16:
        raise ValueError("concurrency must be in [1, 16]")
    return int(args.function(args))


if __name__ == "__main__":
    raise SystemExit(main())
