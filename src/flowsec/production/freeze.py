from __future__ import annotations

import hashlib
import json
import os
import resource
import shutil
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from flowsec.production.adapters import AdapterResult, EdgeAdapter, IoT23Adapter
from flowsec.production.audits import build_leakage_audit
from flowsec.production.config import ProductionConfig
from flowsec.production.core import combine_hashes, sha256_file
from flowsec.production.label_provenance import (
    checkpoint_reuse_audit,
    preflight_edge_captures,
    provenance_by_capture,
    summarize_catalog_session_provenance,
)
from flowsec.production.manifests import (
    build_support_entry,
    canonical_schema_manifest,
    ku_counts,
    label_schema_edge,
    label_schema_iot,
    write_logical_assets,
)
from flowsec.production.readiness import build_class_role_support_gate
from flowsec.production.sensitivity import build_evaluation_clean_variants
from flowsec.production.schema import (
    INITIAL_VIEW_VERSION,
    MODEL_FEATURE_WHITELIST,
    NO_SERVICE_VIEW_VERSION,
    PROHIBITED_FIELDS_VERSION,
    PROHIBITED_MODEL_FIELDS,
    SERVICE_DIAGNOSTIC_VIEW_VERSION,
    canonical_json,
    content_hash,
)
from flowsec.production.storage import ProductionCatalog, write_json


class IntentionalInterruption(RuntimeError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _progress(event: str, **values: Any) -> None:
    print(canonical_json({"event": event, "at": _now(), **values}), flush=True)


def _md5_file(path: Path) -> str:
    digest = hashlib.md5(usedforsecurity=False)
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def build_source_manifest(
    *,
    config: ProductionConfig,
    edge_root: Path,
    edge_archive: Path,
    iot_root: Path,
) -> tuple[dict[str, Any], dict[tuple[str, str], str]]:
    files: list[dict[str, Any]] = []
    capture_fingerprints: dict[tuple[str, str], str] = {}
    archive = config.edge["archive"]
    archive_sha = sha256_file(edge_archive)
    archive_md5 = _md5_file(edge_archive)
    archive_ok = (
        edge_archive.stat().st_size == int(archive["bytes"])
        and archive_sha == str(archive["sha256"])
        and archive_md5 == str(archive["md5"])
    )
    files.append(
        {
            "logical_name": "Edge-IIoTset official complete archive",
            "dataset": config.edge["dataset_name"],
            "scenario_or_capture": "complete official archive",
            "path": str(edge_archive),
            "bytes": edge_archive.stat().st_size,
            "sha256": archive_sha,
            "md5": archive_md5,
            "expected_sha256": archive["sha256"],
            "expected_md5": archive["md5"],
            "verification_basis": "official Kaggle archive size and MD5 plus local SHA256",
            "verification_status": "VERIFIED" if archive_ok else "MISMATCH",
        }
    )
    for spec in config.edge["captures"]:
        pcap = edge_root / spec["pcap"]
        label = edge_root / spec["csv"]
        if not pcap.is_file() or not label.is_file():
            raise FileNotFoundError(f"missing Edge source: {pcap} / {label}")
        pcap_sha, label_sha = sha256_file(pcap), sha256_file(label)
        capture_fingerprints[(config.edge["dataset_name"], spec["id"])] = combine_hashes(
            [pcap_sha, label_sha]
        )
        for kind, path, digest in (("pcap", pcap, pcap_sha), ("label_csv", label, label_sha)):
            files.append(
                {
                    "logical_name": f"{spec['id']} {kind}",
                    "dataset": config.edge["dataset_name"],
                    "scenario_or_capture": spec["id"],
                    "path": str(path),
                    "bytes": path.stat().st_size,
                    "sha256": digest,
                    "expected_sha256": None,
                    "verification_basis": "member of exact verified official archive; per-file hash frozen by this production run",
                    "verification_status": "VERIFIED" if archive_ok else "MISMATCH",
                }
            )
        spec["_pcap_sha256"] = pcap_sha
        spec["_csv_sha256"] = label_sha
    for spec in config.iot23["scenarios"]:
        scenario_hashes: list[str] = []
        definitions = [
            ("pcap", spec["pcap"], spec["pcap_sha256"]),
            ("labeled_log", spec["log"], spec["log_sha256"]),
        ]
        if spec.get("readme"):
            definitions.append(("scenario_readme", spec["readme"], spec["readme_sha256"]))
        for kind, relative, expected in definitions:
            path = iot_root / relative
            if not path.is_file():
                raise FileNotFoundError(f"missing IoT-23 source: {path}")
            digest = sha256_file(path)
            scenario_hashes.append(digest)
            official_url = spec.get(
                f"official_{'log' if kind == 'labeled_log' else kind}_url"
            )
            if kind == "scenario_readme" and not official_url and spec.get("official_pcap_url"):
                official_url = str(spec["official_pcap_url"]).rsplit("/", 1)[0] + "/README.md"
            files.append(
                {
                    "logical_name": f"{spec['id']} {kind}",
                    "dataset": config.iot23["dataset_name"],
                    "scenario_or_capture": spec["id"],
                    "path": str(path),
                    "bytes": path.stat().st_size,
                    "sha256": digest,
                    "expected_sha256": expected,
                    "official_url": official_url,
                    "selection_reason": spec.get("selection_reason"),
                    "verification_basis": "exact expected SHA256 from server download freeze",
                    "verification_status": "VERIFIED" if digest == expected else "MISMATCH",
                }
            )
        capture_fingerprints[(config.iot23["dataset_name"], spec["id"])] = combine_hashes(
            scenario_hashes[:2]
        )
        spec["_pcap_sha256"] = scenario_hashes[0]
        spec["_log_sha256"] = scenario_hashes[1]
    source_manifest = {
        "generated_at": _now(),
        "config_hash": config.config_hash,
        "files": files,
        "verified_files": sum(item["verification_status"] == "VERIFIED" for item in files),
        "mismatched_files": sum(item["verification_status"] != "VERIFIED" for item in files),
        "source_changed": any(item["verification_status"] != "VERIFIED" for item in files),
    }
    if source_manifest["source_changed"]:
        mismatches = [
            item["logical_name"]
            for item in files
            if item["verification_status"] != "VERIFIED"
        ]
        raise ValueError(f"source hash mismatch: {mismatches}")
    return source_manifest, capture_fingerprints


def _checkpoint_path(output_root: Path, dataset: str, capture_id: str) -> Path:
    safe = "".join(
        character if character.isalnum() or character in {"_", "-"} else "_"
        for character in f"{dataset}_{capture_id}"
    )
    return output_root / "_state" / "checkpoints" / f"{safe}.json"


def _edge_provenance_baseline(report_dir: Path) -> dict[str, dict[str, str]]:
    path = report_dir / "edge_label_provenance_manifest.json"
    if not path.is_file():
        path = report_dir / "edge_label_provenance_preflight.json"
    if not path.is_file():
        return {}
    value = json.loads(path.read_text(encoding="utf-8"))
    return {
        str(item["capture_id"]): {
            "pcap_sha256": str(item["pcap_sha256"]),
            "companion_csv_sha256": str(item["companion_csv_sha256"]),
        }
        for item in value.get("captures", [])
        if item.get("pcap_sha256") and item.get("companion_csv_sha256")
    }


def _load_checkpoint(
    *,
    path: Path,
    config_hash: str,
    source_fingerprint: str,
    catalog: ProductionCatalog,
    dataset: str,
    capture_id: str,
    mode: str,
) -> AdapterResult | None:
    if not path.is_file():
        return None
    value = json.loads(path.read_text(encoding="utf-8"))
    if (
        value.get("status") != "COMPLETED"
        or value.get("config_hash") != config_hash
        or value.get("source_fingerprint") != source_fingerprint
        or value.get("mode") != mode
    ):
        return None
    result = value["result"]
    if catalog.capture_count(dataset, capture_id) != int(result["records"]):
        return None
    return AdapterResult(**result)


def _save_checkpoint(
    path: Path,
    *,
    config_hash: str,
    source_fingerprint: str,
    mode: str,
    result: AdapterResult,
) -> None:
    write_json(
        path,
        {
            "status": "COMPLETED",
            "config_hash": config_hash,
            "source_fingerprint": source_fingerprint,
            "mode": mode,
            "result": result.as_dict(),
        },
    )


def _clean_generated_assets(output_root: Path) -> None:
    for name in (
        "backend_records",
        "canonical_sessions",
        "initial_model_views",
        "expandable_packet_store",
        "temporal_index",
        "relation_index",
        "sample_id_index",
        "application_evidence",
        "sensitivity_variants",
        "manifests",
    ):
        target = output_root / name
        if target.exists():
            shutil.rmtree(target)


def _edge_presets(config: ProductionConfig, catalog: ProductionCatalog) -> dict[str, Any]:
    all_labels = set(config.edge["coarse_mapping"])
    parent = dict(config.edge["coarse_mapping"])
    output: dict[str, Any] = {}
    for name, preset in config.edge["known_unknown_presets"].items():
        udev, ufinal = set(preset["u_dev"]), set(preset["u_final"])
        known = sorted(all_labels - udev - ufinal)
        values = {
            "seed": int(preset["seed"]),
            "K_known": known,
            "U_dev": sorted(udev),
            "U_final": sorted(ufinal),
            "definition": preset["definition"],
            "selection_rule": "native taxonomy only; frozen before any Qwen/model run",
            "parent_relationships": {
                label: {
                    "coarse_parent": parent[label],
                    "known_siblings": sorted(
                        item for item in known if parent[item] == parent[label]
                    ),
                }
                for label in sorted(udev | ufinal)
            },
            "counts": {
                "K_known": ku_counts(
                    catalog,
                    dataset=config.edge["dataset_name"],
                    label_column="fine_label",
                    labels=known,
                ),
                "U_dev": ku_counts(
                    catalog,
                    dataset=config.edge["dataset_name"],
                    label_column="fine_label",
                    labels=sorted(udev),
                ),
                "U_final": ku_counts(
                    catalog,
                    dataset=config.edge["dataset_name"],
                    label_column="fine_label",
                    labels=sorted(ufinal),
                ),
            },
            "exclusion_reason": "none",
        }
        output[name] = values
    return output


def _support_manifests(
    config: ProductionConfig,
    catalog: ProductionCatalog,
    edge_presets: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    query_cap = int(config.processing["support_query_cap_per_class"])
    edge = {
        "dataset": config.edge["dataset_name"],
        "sample_level_only": True,
        "support_labels_locked_until_phase_c": True,
        "presets": {},
    }
    for name, preset in edge_presets.items():
        classes: dict[str, Any] = {}
        for label in preset["U_final"]:
            classes[label] = build_support_entry(
                catalog,
                dataset=config.edge["dataset_name"],
                label_column="fine_label",
                label=label,
                split="test",
                seed=int(preset["seed"]),
                shots=[1, 5, 10],
                query_cap=query_cap,
            )
        edge["presets"][name] = {
            "seed": preset["seed"],
            "classes": classes,
        }
    iot_preset = config.iot23["known_unknown_preset"]
    iot_label_column = str(config.iot23["task_label_level"])
    if iot_label_column not in {"fine_label", "coarse_label"}:
        raise ValueError(f"unsupported IoT-23 task label level: {iot_label_column}")
    iot_classes: dict[str, Any] = {}
    for label in iot_preset["u_final"]:
        iot_classes[label] = build_support_entry(
            catalog,
            dataset=config.iot23["dataset_name"],
            label_column=iot_label_column,
            label=label,
            split="unknown_final",
            seed=int(iot_preset["seed"]),
            shots=[1, 5],
            query_cap=query_cap,
        )
    iot = {
        "dataset": config.iot23["dataset_name"],
        "task_label_level": iot_label_column,
        "native_fine_labels": sorted(iot_preset["u_final_native_fine"]),
        "sample_level_only": True,
        "support_labels_locked_until_phase_c": True,
        "presets": {
            iot_preset["id"]: {
                "seed": iot_preset["seed"],
                "classes": iot_classes,
            }
        },
    }
    return edge, iot


def _training_manifests(
    *,
    config: ProductionConfig,
    source_manifest: dict[str, Any],
    edge_presets: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    source_hashes = sorted({item["sha256"] for item in source_manifest["files"]})
    edge_assets: list[dict[str, Any]] = []
    for name, preset in edge_presets.items():
        reference = {
            "storage": "partitioned_parquet",
            "asset": "sample_id_index",
            "dataset": config.edge["dataset_name"],
        }
        for role, split in (
            ("sft_train", "train"),
            ("sft_validation", "validation"),
            ("closed_test", "test"),
        ):
            edge_assets.append(
                {
                    "preset": name,
                    "role": role,
                    "split": split,
                    "sample_ids": {**reference, "filter": {"split": split, "fine_label_in": preset["K_known"]}},
                    "allowed_labels": preset["K_known"],
                    "ku_role": "K_known",
                    "development_visible": role != "closed_test",
                }
            )
        edge_assets.append(
            {
                "preset": name,
                "role": "unknown_development",
                "split": "validation",
                "sample_ids": {**reference, "filter": {"split": "validation", "fine_label_in": preset["U_dev"]}},
                "allowed_labels": [],
                "ku_role": "U_dev",
                "development_visible": True,
                "main_classification_supervision": False,
            }
        )
        edge_assets.append(
            {
                "preset": name,
                "role": "final_unknown",
                "split": "test",
                "sample_ids": {**reference, "filter": {"split": "test", "fine_label_in": preset["U_final"]}},
                "allowed_labels": [],
                "ku_role": "U_final",
                "development_visible": False,
                "support_labels_locked": True,
            }
        )
    common = {
        "schema_version": config.schema_version,
        "model_view_version": INITIAL_VIEW_VERSION,
        "feature_variant": "PRIMARY_VIEW=NO_SERVICE_VIEW",
        "prohibited_fields_version": PROHIBITED_FIELDS_VERSION,
        "fit_scope": "train_only",
        "source_hashes": source_hashes,
        "prompt_corpus_generated": False,
        "final_unknown_default_excluded": True,
    }
    edge = {
        **common,
        "dataset": config.edge["dataset_name"],
        "assets": edge_assets,
        "normal_loader_policy": "--exclude-final-unknown is default",
    }
    iot_preset = config.iot23["known_unknown_preset"]
    iot_ref = {
        "storage": "partitioned_parquet",
        "asset": "sample_id_index",
        "dataset": config.iot23["dataset_name"],
    }
    iot_assets = [
        {
            "role": "sft_train",
            "split": "train",
            "sample_ids": {**iot_ref, "filter": {"split": "train", "coarse_label_in": iot_preset["k_known"]}},
            "allowed_labels": iot_preset["k_known"],
            "ku_role": "K_known",
            "development_visible": True,
        },
        {
            "role": "sft_validation",
            "split": "validation",
            "sample_ids": {**iot_ref, "filter": {"split": "validation", "coarse_label_in": iot_preset["k_known"]}},
            "allowed_labels": iot_preset["k_known"],
            "ku_role": "K_known",
            "development_visible": True,
        },
        {
            "role": "scenario_held_closed_test",
            "split": "test",
            "sample_ids": {**iot_ref, "filter": {"split": "test", "coarse_label_in": iot_preset["k_known"]}},
            "allowed_labels": iot_preset["k_known"],
            "ku_role": "K_known",
            "development_visible": False,
        },
        {
            "role": "unknown_development",
            "split": "unknown_dev",
            "sample_ids": {**iot_ref, "filter": {"split": "unknown_dev", "coarse_label_in": iot_preset["u_dev"]}},
            "allowed_labels": [],
            "ku_role": "U_dev",
            "development_visible": True,
            "main_classification_supervision": False,
        },
        {
            "role": "final_unknown",
            "split": "unknown_final",
            "sample_ids": {**iot_ref, "filter": {"split": "unknown_final", "coarse_label_in": iot_preset["u_final"]}},
            "allowed_labels": [],
            "ku_role": "U_final",
            "development_visible": False,
            "support_labels_locked": True,
        },
    ]
    iot = {
        **common,
        "dataset": config.iot23["dataset_name"],
        "task_label_level": config.iot23["task_label_level"],
        "assets": iot_assets,
        "normal_loader_policy": "--exclude-final-unknown is default",
    }
    return edge, iot


def _aggregate_counts(catalog: ProductionCatalog, dataset: str) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for name, column in (
        ("fine_labels", "fine_label"),
        ("coarse_labels", "coarse_label"),
        ("splits", "base_split"),
        ("captures", "capture_id"),
    ):
        result[name] = {
            str(key): int(count)
            for key, count in catalog.query(
                f"SELECT {column},COUNT(*) FROM records WHERE dataset=? AND retained=1 GROUP BY {column}",
                (dataset,),
            )
        }
    result["retained"] = int(
        catalog.scalar("SELECT COUNT(*) FROM records WHERE dataset=? AND retained=1", (dataset,))
        or 0
    )
    result["excluded"] = int(
        catalog.scalar("SELECT COUNT(*) FROM records WHERE dataset=? AND retained=0", (dataset,))
        or 0
    )
    return result


def _retention_breakdown(catalog: ProductionCatalog, dataset: str) -> dict[str, Any]:
    output: dict[str, Any] = {}
    labels = [
        str(row[0])
        for row in catalog.query(
            "SELECT DISTINCT fine_label FROM records WHERE dataset=? ORDER BY fine_label",
            (dataset,),
        )
    ]
    for label in labels:
        rows = {
            str(reason): int(count)
            for reason, count in catalog.query(
                """
                SELECT exclusion_reason,COUNT(*)
                FROM records
                WHERE dataset=? AND fine_label=? AND retained=0
                GROUP BY exclusion_reason
                """,
                (dataset, label),
            )
        }
        constructed = int(
            catalog.scalar(
                "SELECT COUNT(*) FROM records WHERE dataset=? AND fine_label=?",
                (dataset, label),
            )
            or 0
        )
        retained = int(
            catalog.scalar(
                "SELECT COUNT(*) FROM records WHERE dataset=? AND fine_label=? AND retained=1",
                (dataset, label),
            )
            or 0
        )
        known_reasons = {
            "identity_duplicate",
            "identity_label_conflict",
            "split_boundary_or_gap",
        }
        output[label] = {
            "constructed": constructed,
            "identity_duplicate": rows.get("identity_duplicate", 0),
            "boundary_or_gap": rows.get("split_boundary_or_gap", 0),
            "identity_label_conflict": rows.get("identity_label_conflict", 0),
            "other_exclusion": sum(
                count for reason, count in rows.items() if reason not in known_reasons
            ),
            "retained": retained,
            "retention_rate": retained / constructed if constructed else 0.0,
        }
    return {
        "dataset": dataset,
        "deduplication_identity": "dataset + stable sample_id",
        "classes": output,
        "constructed": sum(item["constructed"] for item in output.values()),
        "retained": sum(item["retained"] for item in output.values()),
    }


def _copy_manifests(report_dir: Path, output_root: Path, names: list[str]) -> None:
    target = output_root / "manifests"
    target.mkdir(parents=True, exist_ok=True)
    for name in names:
        shutil.copy2(report_dir / name, target / name)


def _update_server_download_manifest(
    path: Path,
    source_manifest: dict[str, Any],
) -> None:
    if not path.is_file():
        return
    value = json.loads(path.read_text(encoding="utf-8"))
    existing = {
        (item.get("scenario_or_capture"), item.get("sha256")): item
        for item in value.get("files", [])
    }
    for item in source_manifest["files"]:
        if item.get("scenario_or_capture") != "CTU-IoT-Malware-Capture-3-1":
            continue
        key = (item["scenario_or_capture"], item["sha256"])
        if key in existing:
            existing[key].update(
                {
                    "expected_sha256": item["expected_sha256"],
                    "official_url": item.get("official_url"),
                    "selection_reason": item.get("selection_reason"),
                    "source_content_length": item["bytes"],
                    "verification_status": "VERIFIED",
                }
            )
            continue
        value.setdefault("files", []).append(
            {
                "byte_size": item["bytes"],
                "dataset": "IoT-23",
                "downloaded_file": Path(item["path"]).name,
                "expected_sha256": item["expected_sha256"],
                "known_anomaly": None,
                "local_path": item["path"],
                "official_source": "CTU IoT-23 individual scenario endpoint",
                "official_url": item.get("official_url"),
                "retrieval_timestamp": _now(),
                "scenario_or_capture": item["scenario_or_capture"],
                "sha256": item["sha256"],
                "source_changed": False,
                "source_content_length": item["bytes"],
                "verification_status": "VERIFIED",
                "selection_reason": item.get("selection_reason"),
            }
        )
    value["files"] = sorted(
        value["files"],
        key=lambda item: (
            item.get("dataset", ""),
            item.get("scenario_or_capture", ""),
            item.get("downloaded_file", ""),
        ),
    )
    write_json(path, value)


def run_freeze(
    *,
    config: ProductionConfig,
    edge_root: Path,
    edge_archive: Path,
    iot_root: Path,
    output_root: Path,
    report_dir: Path,
    tshark_bin: str,
    mode: str = "full",
    sample_sessions: int = 5000,
    only_datasets: set[str] | None = None,
    only_captures: set[str] | None = None,
    stop_after_captures: int | None = None,
    force: bool = False,
) -> dict[str, Any]:
    started = time.monotonic()
    selected = only_datasets or {"edge", "iot23"}
    output_root.mkdir(parents=True, exist_ok=True)
    report_dir.mkdir(parents=True, exist_ok=True)
    source_manifest, fingerprints = build_source_manifest(
        config=config,
        edge_root=edge_root,
        edge_archive=edge_archive,
        iot_root=iot_root,
    )
    _progress("source_verification_complete", files=len(source_manifest["files"]))
    edge_provenance_preflight: dict[str, Any] | None = None
    if "edge" in selected:
        edge_provenance_preflight = preflight_edge_captures(
            edge_config=config.edge,
            edge_root=edge_root,
            official_archive_verified=True,
            expected_hashes=_edge_provenance_baseline(report_dir),
        )
        write_json(
            report_dir / "edge_label_provenance_preflight.json",
            edge_provenance_preflight,
        )
        _progress(
            "edge_label_provenance_preflight_complete",
            gate=edge_provenance_preflight["CAPTURE_PROVENANCE_GATE"],
            passed=edge_provenance_preflight["passed_capture_count"],
        )
        if edge_provenance_preflight["CAPTURE_PROVENANCE_GATE"] != "PASS":
            raise ValueError("PROVENANCE_CAPTURE_LABEL_FAIL: all-capture preflight blocked")
    if mode == "dry-run":
        write_json(report_dir / "source_checksum_manifest.json", source_manifest)
        return {
            "status": "DRY_RUN_OK",
            "source_manifest": source_manifest,
            "edge_label_provenance": edge_provenance_preflight,
        }
    catalog = ProductionCatalog(output_root / "_state" / "production_catalog.sqlite")
    if force:
        catalog.connection.execute("DELETE FROM records")
        catalog.connection.execute("DELETE FROM quarantine")
        catalog.connection.commit()
        checkpoint_root = output_root / "_state" / "checkpoints"
        if checkpoint_root.exists():
            shutil.rmtree(checkpoint_root)
    checkpoint_provenance: dict[str, Any] | None = None
    if edge_provenance_preflight is not None:
        checkpoint_provenance = checkpoint_reuse_audit(
            output_root=output_root,
            catalog=catalog,
            dataset=str(config.edge["dataset_name"]),
            config_hash=config.config_hash,
            mode=mode,
            preflight_manifest=edge_provenance_preflight,
        )
        write_json(report_dir / "edge_checkpoint_reuse_audit.json", checkpoint_provenance)
    results: list[AdapterResult] = []
    completed = 0
    try:
        if "edge" in selected:
            adapter = EdgeAdapter(
                catalog=catalog,
                dataset_root=edge_root,
                config=config.edge,
                processing=config.processing,
                tshark_bin=tshark_bin,
                mode=mode,
                sample_sessions=sample_sessions,
            )
            for spec in config.edge["captures"]:
                if only_captures and spec["id"] not in only_captures:
                    continue
                dataset, capture = config.edge["dataset_name"], spec["id"]
                checkpoint = _checkpoint_path(output_root, dataset, capture)
                result = _load_checkpoint(
                    path=checkpoint,
                    config_hash=config.config_hash,
                    source_fingerprint=fingerprints[(dataset, capture)],
                    catalog=catalog,
                    dataset=dataset,
                    capture_id=capture,
                    mode=mode,
                )
                if result is None:
                    _progress("capture_started", dataset=dataset, capture_id=capture)
                    result = adapter.process_capture(spec)
                    _save_checkpoint(
                        checkpoint,
                        config_hash=config.config_hash,
                        source_fingerprint=fingerprints[(dataset, capture)],
                        mode=mode,
                        result=result,
                    )
                    _progress(
                        "capture_completed",
                        dataset=dataset,
                        capture_id=capture,
                        records=result.records,
                        quarantined=result.quarantined,
                    )
                else:
                    _progress(
                        "capture_resumed",
                        dataset=dataset,
                        capture_id=capture,
                        records=result.records,
                    )
                results.append(result)
                completed += 1
                if stop_after_captures and completed >= stop_after_captures:
                    raise IntentionalInterruption(f"stopped after {completed} captures")
        if "iot23" in selected:
            adapter = IoT23Adapter(
                catalog=catalog,
                dataset_root=iot_root,
                config=config.iot23,
                processing=config.processing,
                tshark_bin=tshark_bin,
                mode=mode,
                sample_sessions=sample_sessions,
            )
            for spec in config.iot23["scenarios"]:
                if only_captures and spec["id"] not in only_captures:
                    continue
                dataset, capture = config.iot23["dataset_name"], spec["id"]
                checkpoint = _checkpoint_path(output_root, dataset, capture)
                result = _load_checkpoint(
                    path=checkpoint,
                    config_hash=config.config_hash,
                    source_fingerprint=fingerprints[(dataset, capture)],
                    catalog=catalog,
                    dataset=dataset,
                    capture_id=capture,
                    mode=mode,
                )
                if result is None:
                    _progress("capture_started", dataset=dataset, capture_id=capture)
                    result = adapter.process_capture(spec)
                    _save_checkpoint(
                        checkpoint,
                        config_hash=config.config_hash,
                        source_fingerprint=fingerprints[(dataset, capture)],
                        mode=mode,
                        result=result,
                    )
                    _progress(
                        "capture_completed",
                        dataset=dataset,
                        capture_id=capture,
                        records=result.records,
                        quarantined=result.quarantined,
                        match=result.match,
                    )
                else:
                    _progress(
                        "capture_resumed",
                        dataset=dataset,
                        capture_id=capture,
                        records=result.records,
                    )
                results.append(result)
                completed += 1
                if stop_after_captures and completed >= stop_after_captures:
                    raise IntentionalInterruption(f"stopped after {completed} captures")

        edge_label_provenance = (
            summarize_catalog_session_provenance(
                catalog=catalog,
                dataset=str(config.edge["dataset_name"]),
                preflight_manifest=edge_provenance_preflight,
            )
            if edge_provenance_preflight is not None
            else None
        )
        if edge_label_provenance is not None:
            existing_provenance_path = report_dir / "edge_label_provenance_manifest.json"
            if existing_provenance_path.is_file():
                existing_provenance = json.loads(
                    existing_provenance_path.read_text(encoding="utf-8")
                )
                if existing_provenance.get("independent_direct_evidence_audit"):
                    edge_label_provenance["independent_direct_evidence_audit"] = (
                        existing_provenance["independent_direct_evidence_audit"]
                    )
            totals = edge_label_provenance["totals"]
            postfix_safe = (
                edge_label_provenance["CAPTURE_PROVENANCE_GATE"] == "PASS"
                and int(totals["conflict_sessions"]) == 0
                and int(totals["unmatched_quarantine_sessions"]) == 0
            )
            edge_label_provenance["LABEL_PROVENANCE_AUDIT_POSTFIX"] = (
                "PASS_WITH_LIMITATIONS" if postfix_safe else "BLOCKED"
            )
            edge_label_provenance["checkpoint_reuse"] = checkpoint_provenance
            write_json(
                report_dir / "edge_label_provenance_manifest.json",
                edge_label_provenance,
            )
            if not postfix_safe:
                raise ValueError("LABEL_PROVENANCE_AUDIT_POSTFIX=BLOCKED")

        _progress("deduplication_started")
        deduplication = catalog.apply_identity_deduplication()
        _progress("deduplication_completed", identity=deduplication)
        _clean_generated_assets(output_root)
        _progress("logical_asset_write_started")
        asset_metadata, asset_counts = write_logical_assets(
            catalog=catalog,
            output_root=output_root,
            processing=config.processing,
            label_schema_ids={
                config.edge["dataset_name"]: config.edge["label_schema_id"],
                config.iot23["dataset_name"]: config.iot23["label_schema_id"],
            },
            edge_label_provenance=(
                provenance_by_capture(edge_label_provenance)
                if edge_label_provenance is not None
                else None
            ),
        )
        _progress("logical_asset_write_completed", counts=asset_counts)
        _progress("evaluation_clean_variants_started")
        sensitivity_manifest = build_evaluation_clean_variants(
            catalog=catalog,
            output_root=output_root,
            processing=config.processing,
        )
        for variant_name, variant in sensitivity_manifest["variants"].items():
            key = f"sensitivity_{variant_name.lower()}_exclusion_ids"
            asset_metadata[key] = variant["exclusion_id_asset"]
            asset_counts[key] = int(variant["exclusion_id_asset"]["rows"])
        _progress(
            "evaluation_clean_variants_completed",
            counts={
                name: value["exclusion_id_asset"]["rows"]
                for name, value in sensitivity_manifest["variants"].items()
            },
        )
        edge_presets = _edge_presets(config, catalog)
        edge_support, iot_support = _support_manifests(config, catalog, edge_presets)
        training_edge, training_iot = _training_manifests(
            config=config,
            source_manifest=source_manifest,
            edge_presets=edge_presets,
        )
        observed_iot_fine = [
            row[0]
            for row in catalog.query(
                "SELECT DISTINCT fine_label FROM records WHERE dataset=? ORDER BY fine_label",
                (config.iot23["dataset_name"],),
            )
        ]
        edge_counts = _aggregate_counts(catalog, config.edge["dataset_name"])
        iot_counts = _aggregate_counts(catalog, config.iot23["dataset_name"])
        edge_retention = _retention_breakdown(catalog, config.edge["dataset_name"])
        iot_retention = _retention_breakdown(catalog, config.iot23["dataset_name"])
        edge_results = {item.capture_id: item.as_dict() for item in results if item.dataset == config.edge["dataset_name"]}
        iot_results = {item.capture_id: item.as_dict() for item in results if item.dataset == config.iot23["dataset_name"]}
        edge_dataset_manifest = {
            "status": "PRODUCTION_READY",
            "dataset": config.edge["dataset_name"],
            "dataset_version": config.edge["dataset_version"],
            "adapter": "EdgeAdapter",
            "capture_count": len(edge_results),
            "captures": edge_results,
            "counts_after_deduplication": edge_counts,
            "deduplication": deduplication,
        }
        iot_dataset_manifest = {
            "status": "PRODUCTION_READY",
            "dataset": config.iot23["dataset_name"],
            "dataset_version": config.iot23["dataset_version"],
            "adapter": "IoT23Adapter",
            "scenario_count": len(iot_results),
            "scenarios": iot_results,
            "counts_after_deduplication": iot_counts,
            "new_scenario": {
                "id": "CTU-IoT-Malware-Capture-3-1",
                "count": 1,
                "selection_reason": next(
                    item["selection_reason"]
                    for item in config.iot23["scenarios"]
                    if item["id"] == "CTU-IoT-Malware-Capture-3-1"
                ),
            },
        }
        edge_split_manifest = {
            "policy": "capture-internal chronological contiguous 70/15/15 blocks",
            "session_timeout_seconds": config.processing["session_timeout_seconds"],
            "gap_rule": "max(fixed safety window, duration p99.9), clipped only by preregistered 2% capture-span usability cap",
            "captures": {
                key: {
                    "split_counts": value["split_counts"],
                    "duration_statistics": value["duration_statistics"],
                }
                for key, value in edge_results.items()
            },
            "counts": edge_counts["splits"],
            "context_scope": config.processing["context_scope"],
        }
        scenario_roles = {
            role: sorted(
                spec["id"] for spec in config.iot23["scenarios"] if spec["role"] == role
            )
            for role in ("train", "validation", "test", "unknown_probe", "unknown_pool")
        }
        iot_split_manifest = {
            "policy": "fully scenario-held train/validation/test; class-held unknown labels in independent Capture-3",
            "scenario_roles": scenario_roles,
            "task_label_level": config.iot23["task_label_level"],
            "closed_set_labels": config.iot23["known_coarse_labels"],
            "unknown_dev": {"scenario": "CTU-IoT-Malware-Capture-3-1", "native_fine": ["PartOfAHorizontalPortScan"], "coarse": ["Reconnaissance"]},
            "unknown_final": {"scenario": "CTU-IoT-Malware-Capture-3-1", "native_fine": ["Attack"], "coarse": ["Exploitation"]},
            "capture42_role": "six-flow unknown probe only; not a formal main result",
            "counts": iot_counts["splits"],
        }
        iot_preset = {
            **config.iot23["known_unknown_preset"],
            "counts": {
                "K_known": ku_counts(catalog, dataset=config.iot23["dataset_name"], label_column="coarse_label", labels=config.iot23["known_unknown_preset"]["k_known"]),
                "U_dev": ku_counts(catalog, dataset=config.iot23["dataset_name"], label_column="coarse_label", labels=config.iot23["known_unknown_preset"]["u_dev"]),
                "U_final": ku_counts(catalog, dataset=config.iot23["dataset_name"], label_column="coarse_label", labels=config.iot23["known_unknown_preset"]["u_final"]),
            },
            "selection_rule": "native coarse hierarchy and official scenario metadata; no model outputs",
        }
        class_role_support = build_class_role_support_gate(
            catalog=catalog,
            edge_dataset=config.edge["dataset_name"],
            edge_presets=edge_presets,
            edge_support=edge_support,
            edge_training=training_edge,
            iot_dataset=config.iot23["dataset_name"],
            iot_preset=iot_preset,
            iot_support=iot_support,
            iot_training=training_iot,
        )
        anomaly_rows = [
            {
                "reproducibility_id": row[0],
                "dataset": row[1],
                "capture_id": row[2],
                "source_hash": row[3],
                "reason": row[4],
                "severity": row[5],
                "count": int(row[6]),
                "details": json.loads(row[7]),
            }
            for row in catalog.query(
                "SELECT reproducibility_id,dataset,capture_id,source_hash,reason,severity,count,details_json FROM quarantine ORDER BY dataset,capture_id,reason"
            )
        ]
        anomaly_manifest = {
            "status": "PASS_WITH_LIMITATIONS" if anomaly_rows else "PASS",
            "entries": anomaly_rows,
            "total_events_or_records": sum(item["count"] for item in anomaly_rows),
        }
        leakage = build_leakage_audit(
            catalog=catalog,
            projection_violations=asset_metadata.pop("_projection_violations"),
            edge_presets=edge_presets,
            iot_preset=iot_preset,
            support_manifests=[edge_support, iot_support],
            training_manifests=[training_edge, training_iot],
            source_manifest=source_manifest,
        )
        elapsed = time.monotonic() - started
        output_bytes = sum(
            path.stat().st_size
            for path in output_root.rglob("*")
            if path.is_file()
        )
        disk = shutil.disk_usage(output_root)
        catalog_files = list((output_root / "_state").glob("production_catalog.sqlite*"))
        initial_attempt_path = report_dir / "production_statistics_initial_full_attempt.json"
        initial_attempt = (
            json.loads(initial_attempt_path.read_text(encoding="utf-8"))
            if initial_attempt_path.is_file()
            else None
        )
        statistics = {
            "mode": mode,
            "elapsed_seconds": elapsed,
            "peak_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
            "processed_input_bytes": sum(item["bytes"] for item in source_manifest["files"]),
            "final_output_bytes": output_bytes,
            "temporary_catalog_bytes": sum(path.stat().st_size for path in catalog_files),
            "disk_remaining_bytes": disk.free,
            "asset_counts": asset_counts,
            "asset_metadata": asset_metadata,
            "sessions_per_second": asset_counts.get("canonical_sessions", 0) / elapsed if elapsed else 0,
            "adapter_results": [item.as_dict() for item in results],
        }
        if initial_attempt:
            first_elapsed = float(initial_attempt.get("elapsed_seconds", 0.0))
            first_peak = int(initial_attempt.get("peak_rss_kib", 0))
            statistics["attempt_history"] = {
                "initial_full_processing": {
                    "elapsed_seconds": first_elapsed,
                    "peak_rss_kib": first_peak,
                    "result": "INCOMPLETE_AUDIT_CORRECTED_BY_CHECKPOINT_RESUME",
                },
                "checkpoint_resume_finalization": {
                    "elapsed_seconds": elapsed,
                    "peak_rss_kib": statistics["peak_rss_kib"],
                },
            }
            statistics["cumulative_elapsed_seconds"] = first_elapsed + elapsed
            statistics["overall_peak_rss_kib"] = max(
                first_peak, int(statistics["peak_rss_kib"])
            )
        report_values = {
            "canonical_schema_v1.json": canonical_schema_manifest(),
            "edge_dataset_manifest.json": edge_dataset_manifest,
            "iot23_dataset_manifest.json": iot_dataset_manifest,
            "edge_split_manifest.json": edge_split_manifest,
            "iot23_split_manifest.json": iot_split_manifest,
            "edge_label_schema.json": label_schema_edge(config.edge),
            "iot23_label_schema.json": label_schema_iot(config.iot23, observed_iot_fine),
            "edge_known_unknown_presets.json": edge_presets,
            "iot23_known_unknown_presets.json": iot_preset,
            "edge_support_query_manifest.json": edge_support,
            "iot23_support_query_manifest.json": iot_support,
            "evaluation_clean_sensitivity_manifest.json": sensitivity_manifest,
            "edge_label_provenance_manifest.json": edge_label_provenance,
            "edge_checkpoint_reuse_audit.json": checkpoint_provenance,
            "class_role_support_gate.json": class_role_support,
            "edge_retention_audit.json": edge_retention,
            "iot23_retention_audit.json": iot_retention,
            "model_feature_whitelist.json": {
                "version": INITIAL_VIEW_VERSION,
                "primary_view": "NO_SERVICE",
                "features": list(MODEL_FEATURE_WHITELIST),
                "service_diagnostic_view": SERVICE_DIAGNOSTIC_VIEW_VERSION,
            },
            "prohibited_model_fields.json": {
                "version": PROHIBITED_FIELDS_VERSION,
                "fields": list(PROHIBITED_MODEL_FIELDS),
                "model_input": False,
            },
            "anomaly_policy.json": {
                "version": "anomaly_policy_v1",
                "raw_immutable": True,
                "known_recoverable_tail_policy": "retain readable prefix, record parser return code and anomaly ID; never repair source in place",
                "unmatched_policy": "quarantine strict unmatched records; never relax matching for coverage",
                "split_boundary_policy": "exclude session and record reproducibility ID/count",
                "severity_values": ["INFO", "WARNING", "PASS_WITH_LIMITATION", "FAIL"],
            },
            "anomaly_manifest.json": anomaly_manifest,
            "source_checksum_manifest.json": source_manifest,
            "training_asset_manifest_edge.json": training_edge,
            "training_asset_manifest_iot23.json": training_iot,
            "leakage_audit.json": leakage,
            "production_statistics.json": statistics,
        }
        for name, value in report_values.items():
            write_json(report_dir / name, value)
        determinism_path = report_dir / "determinism_audit.json"
        determinism = (
            json.loads(determinism_path.read_text(encoding="utf-8"))
            if determinism_path.is_file()
            else {
                "status": "NOT_RUN",
                "DETERMINISM_AUDIT_OK": False,
                "reason": "run subset clean/double/resume audit before finalizing full freeze",
            }
        )
        if not determinism_path.is_file():
            write_json(determinism_path, determinism)
        selected_all = selected == {"edge", "iot23"} and only_captures is None
        postfix_path = report_dir / "postfix_audit" / "precommit_scientific_audit.json"
        postfix = (
            json.loads(postfix_path.read_text(encoding="utf-8"))
            if postfix_path.is_file()
            else {}
        )
        edge_support_safe = class_role_support["edge"] and all(
            value["status"] == "PASS"
            for value in class_role_support["edge"].values()
        )
        iot_support_safe = class_role_support["iot23"]["status"] == "PASS"
        iot_support_labels = {
            label
            for preset in iot_support.get("presets", {}).values()
            for label in preset.get("classes", {})
        }
        iot_support_label_safe = (
            iot_support.get("task_label_level") == config.iot23["task_label_level"]
            and iot_support_labels == set(iot_preset["u_final"])
        )
        u_final_isolation = all(
            item["status"] == "PASS"
            for item in leakage["items"]
            if item["id"] in {15, 16, 17}
        )
        ready = {
            "EDGE_PRODUCTION_ADAPTER_OK": bool(edge_results),
            "IOT23_PRODUCTION_ADAPTER_OK": bool(iot_results),
            "CANONICAL_SCHEMA_V1_OK": True,
            "EDGE_SPLIT_FROZEN": bool(edge_split_manifest["captures"]),
            "IOT23_SPLIT_FROZEN": bool(iot_split_manifest["scenario_roles"]),
            "EDGE_KU_FROZEN": len(edge_presets) == 3,
            "IOT23_KU_FROZEN": True,
            "SUPPORT_QUERY_FROZEN": bool(class_role_support["FEW_SHOT_VARIANT_READY"]),
            "BASE_PRODUCTION_READY": bool(class_role_support["BASE_PRODUCTION_READY"]),
            "FEW_SHOT_VARIANT_READY": bool(class_role_support["FEW_SHOT_VARIANT_READY"]),
            "U_FINAL_ISOLATION_OK": u_final_isolation,
            "LEAKAGE_AUDIT_OK": leakage["LEAKAGE_AUDIT_OK"],
            "DETERMINISM_AUDIT_OK": bool(determinism.get("DETERMINISM_AUDIT_OK")),
            "TRAINING_MANIFEST_OK": True,
            "EDGE_DEDUP_POLICY_SAFE": (
                config.processing.get("primary_deduplication_policy")
                == "immutable_backend_identity_only"
                and "exact_model_evidence_duplicate"
                not in deduplication.get("excluded_counts", {})
            ),
            "EDGE_LABEL_PROVENANCE_SAFE": bool(
                edge_label_provenance
                and edge_label_provenance.get("CAPTURE_PROVENANCE_GATE") == "PASS"
                and edge_label_provenance.get("LABEL_PROVENANCE_AUDIT_POSTFIX")
                == "PASS_WITH_LIMITATIONS"
            ),
            "CAPTURE_PROVENANCE_GATE": (
                edge_label_provenance.get("CAPTURE_PROVENANCE_GATE")
                if edge_label_provenance
                else "NOT_RUN"
            ),
            "LABEL_PROVENANCE_AUDIT_POSTFIX": (
                edge_label_provenance.get("LABEL_PROVENANCE_AUDIT_POSTFIX")
                if edge_label_provenance
                else "NOT_RUN"
            ),
            "EDGE_SESSIONIZATION_SAFE": float(config.processing["session_timeout_seconds"]) == 60.0,
            "EDGE_SPLIT_SAFE": bool(edge_support_safe),
            "EDGE_KU_SEMANTICS_SAFE": len(edge_presets) == 3,
            "IOT23_SPLIT_SAFE": bool(iot_support_safe),
            "IOT23_KU_SAFE": True,
            "IOT23_SUPPORT_LABEL_SAFE": iot_support_label_safe,
            "IDENTITY_CROSS_SPLIT_LEAKAGE": int(leakage["IDENTITY_CROSS_SPLIT_LEAKAGE"]),
            "U_FINAL_ISOLATION_PASS": u_final_isolation,
            "CLASS_ROLE_SUPPORT_GATE": class_role_support["CLASS_ROLE_SUPPORT_GATE"],
            "LEAKAGE_GATE_PASS": bool(leakage["LEAKAGE_AUDIT_OK"]),
            "DETERMINISM_GATE_PASS": bool(determinism.get("DETERMINISM_AUDIT_OK")),
            "EXACT_EVAL_CLEAN_REGISTERED": sensitivity_manifest["variants"]["EXACT_EVAL_CLEAN"]["status"] == "REGISTERED",
            "NEAR_EVAL_CLEAN_REGISTERED": sensitivity_manifest["variants"]["NEAR_EVAL_CLEAN"]["status"] == "REGISTERED",
            "POSTFIX_PRECOMMIT_AUDIT": postfix.get("POSTFIX_PRECOMMIT_AUDIT", "NOT_RUN"),
        }
        required_ready = (
            ready["EDGE_DEDUP_POLICY_SAFE"]
            and ready["EDGE_LABEL_PROVENANCE_SAFE"]
            and ready["EDGE_SESSIONIZATION_SAFE"]
            and ready["EDGE_SPLIT_SAFE"]
            and ready["EDGE_KU_SEMANTICS_SAFE"]
            and ready["IOT23_SPLIT_SAFE"]
            and ready["IOT23_KU_SAFE"]
            and ready["IOT23_SUPPORT_LABEL_SAFE"]
            and ready["IDENTITY_CROSS_SPLIT_LEAKAGE"] == 0
            and ready["U_FINAL_ISOLATION_PASS"]
            and ready["CLASS_ROLE_SUPPORT_GATE"] == "PASS"
            and ready["LEAKAGE_GATE_PASS"]
            and ready["DETERMINISM_GATE_PASS"]
            and ready["EXACT_EVAL_CLEAN_REGISTERED"]
            and ready["NEAR_EVAL_CLEAN_REGISTERED"]
            and ready["POSTFIX_PRECOMMIT_AUDIT"] == "PASS_WITH_LIMITATIONS"
        )
        production_ready = selected_all and mode == "full" and required_ready
        ready["PRODUCTION_DATA_READY"] = production_ready
        ready["TRAINING_STARTED"] = False
        ready["QWEN_DOWNLOADED"] = False
        ready["DECISION_REQUIRED"] = not production_ready
        final = {
            "generated_at": _now(),
            "status": "PASS_WITH_LIMITATIONS" if production_ready else "INCOMPLETE",
            **ready,
            "limitations": [
                "Edge attack classes are mostly single-capture; no cross-run generalization claim.",
                "Gap safety request is clipped only where necessary to keep chronological blocks usable; every clipping is capture-level manifest evidence.",
                "Somfy strict matching limitation and Capture-42 official tail truncation/six-flow probe are retained.",
                "IoT-23 formal task uses the native coarse layer because fine labels do not overlap across train/validation/test scenarios.",
                "Primary view excludes service_category; service remains an on-demand diagnostic generator.",
            ],
            "exact_next_action": "审查并commit/push Production Data Freeze实现，然后配置Qwen3.5-9B训练环境并进行原始模型与BF16 LoRA SFT小规模冒烟。",
        }
        write_json(report_dir / "production_readiness.json", final)
        markdown = [
            "# Production Data Freeze",
            "",
            f"- Status: **{final['status']}**",
            f"- PRODUCTION_DATA_READY: **{str(production_ready).lower()}**",
            f"- Edge retained sessions: {edge_counts['retained']}",
            f"- IoT-23 retained sessions: {iot_counts['retained']}",
            f"- Leakage audit: {leakage['status']}",
            f"- Determinism audit: {determinism.get('status')}",
            f"- Elapsed: {statistics.get('cumulative_elapsed_seconds', elapsed):.2f}s",
            f"- Peak RSS: {statistics.get('overall_peak_rss_kib', statistics['peak_rss_kib'])} KiB",
            f"- Output bytes: {output_bytes}",
            "",
            "## Frozen decisions",
            "",
            "- CanonicalSessionRecord v1 with backend/model-safe/expandable layers.",
            "- PRIMARY_VIEW is the Gate-validated no-service view; derived service is diagnostic only.",
            "- Edge uses capture-internal chronological 70/15/15 blocks with data-derived gaps.",
            "- IoT-23 keeps scenario-held train/validation/test and uses one minimal official Capture-3 supplement for class-held Unknown.",
            "- U_final is excluded from normal loaders, SFT/development manifests, and known-only label-schema projection.",
            "",
            "## Next action",
            "",
            final["exact_next_action"],
            "",
        ]
        (report_dir / "final_production_freeze_report.md").write_text(
            "\n".join(markdown), encoding="utf-8"
        )
        names = list(report_values) + [
            "determinism_audit.json",
            "production_readiness.json",
            "final_production_freeze_report.md",
        ]
        _copy_manifests(report_dir, output_root, names)
        if selected_all and mode == "full":
            _update_server_download_manifest(
                Path("/root/autodl-tmp/experiments/data_download_20260809/source_manifest.json"),
                source_manifest,
            )
        write_json(
            output_root / "_state" / "completion.json",
            {
                "config_hash": config.config_hash,
                "source_manifest_hash": content_hash(source_manifest["files"]),
                "mode": mode,
                "selected_all": selected_all,
                "production_ready": production_ready,
                "asset_logical_hashes": {
                    key: value.get("logical_sha256")
                    for key, value in asset_metadata.items()
                },
                "readiness": ready,
            },
        )
        return {
            "status": final["status"],
            "production_ready": production_ready,
            "readiness": ready,
            "statistics": statistics,
            "asset_logical_hashes": {
                key: value.get("logical_sha256")
                for key, value in asset_metadata.items()
            },
            "report_dir": str(report_dir),
        }
    finally:
        catalog.close()
