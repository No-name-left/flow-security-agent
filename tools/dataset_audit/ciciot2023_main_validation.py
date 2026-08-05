#!/usr/bin/env python3
"""Limited, reproducible CICIoT2023 main-dataset feasibility probe.

The authoritative evidence for dataset construction and row counts is the
official UNB page and the Sensors paper.  Because the official download form
was unavailable during the audit, the empirical CPU probe intentionally uses
a small, explicitly secondary Hugging Face mirror.  It must not be described
as an official copy or used as the basis for a formal benchmark result.

No PCAP is downloaded and no GPU/LLM training is performed.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import sys
import time
import urllib.parse
import urllib.request
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd
from sklearn.base import clone
from sklearn.calibration import calibration_curve
from sklearn.ensemble import RandomForestClassifier
from sklearn.feature_selection import mutual_info_classif
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    balanced_accuracy_score,
    brier_score_loss,
    f1_score,
    log_loss,
    roc_auc_score,
)
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import LabelEncoder, StandardScaler
from sklearn.tree import DecisionTreeClassifier


SEED = 20260804
HF_DATASET = "lacg030175/CIC-IoT-2023-raw"
HF_CONFIG = "random_3way"
DATASET_SERVER = "https://datasets-server.huggingface.co/filter"
OFFICIAL_PAGE = "https://www.unb.ca/cic/datasets/iotdataset-2023.html"
OFFICIAL_PAPER = "https://doi.org/10.3390/s23135941"

FINE_COUNTS: dict[str, int] = {
    "DDoS-ICMP_Flood": 7_200_504,
    "DDoS-UDP_Flood": 5_412_287,
    "DDoS-TCP_Flood": 4_497_667,
    "DDoS-PSHACK_Flood": 4_094_755,
    "DDoS-SYN_Flood": 4_059_190,
    "DDoS-RSTFINFlood": 4_045_285,
    "DDoS-SynonymousIP_Flood": 3_598_138,
    "DoS-UDP_Flood": 3_318_595,
    "DoS-TCP_Flood": 2_671_445,
    "DoS-SYN_Flood": 2_028_834,
    "BenignTraffic": 1_098_195,
    "Mirai-greeth_flood": 991_866,
    "Mirai-udpplain": 890_576,
    "Mirai-greip_flood": 751_682,
    "DDoS-ICMP_Fragmentation": 452_489,
    "MITM-ArpSpoofing": 307_593,
    "DDoS-UDP_Fragmentation": 286_925,
    "DDoS-ACK_Fragmentation": 285_104,
    "DNS_Spoofing": 178_911,
    "Recon-HostDiscovery": 134_378,
    "Recon-OSScan": 98_259,
    "Recon-PortScan": 82_284,
    "DoS-HTTP_Flood": 71_864,
    "VulnerabilityScan": 37_382,
    "DDoS-HTTP_Flood": 28_790,
    "DDoS-SlowLoris": 23_426,
    "DictionaryBruteForce": 13_064,
    "BrowserHijacking": 5_859,
    "CommandInjection": 5_409,
    "SqlInjection": 5_245,
    "XSS": 3_846,
    "Backdoor_Malware": 3_218,
    "Recon-PingSweep": 2_262,
    "Uploading_Attack": 1_252,
}

COARSE_COUNTS = {
    "DDoS": 33_984_560,
    "DoS": 8_090_738,
    "Mirai": 2_634_124,
    "Benign": 1_098_195,
    "Spoofing": 486_504,
    "Recon": 354_565,
    "Web": 24_829,
    "BruteForce": 13_064,
}

WINDOW_FIELDS = [
    "Tot sum",
    "Min",
    "Max",
    "AVG",
    "Std",
    "Tot size",
    "IAT",
    "Number",
    "Magnitude",
    "Magnitue",
    "Radius",
    "Covariance",
    "Variance",
    "Weight",
]
PROTOCOL_FIELDS = [
    "Protocol Type",
    "HTTP",
    "HTTPS",
    "DNS",
    "Telnet",
    "SMTP",
    "SSH",
    "IRC",
    "TCP",
    "UDP",
    "DHCP",
    "ARP",
    "ICMP",
    "IGMP",
    "IPv",
    "LLC",
]

PRESETS = {
    "preset_a": {
        "dev_near": ["DoS-HTTP_Flood", "DDoS-SlowLoris"],
        "dev_far": ["SqlInjection", "CommandInjection"],
        "final_near": ["DDoS-HTTP_Flood", "Recon-PingSweep"],
        "final_far": ["Backdoor_Malware", "XSS"],
        "excluded_families": ["Web"],
    },
    "preset_b": {
        "dev_near": ["Mirai-greip_flood", "Recon-OSScan"],
        "dev_far": ["BrowserHijacking", "Uploading_Attack"],
        "final_near": ["DDoS-ACK_Fragmentation", "DoS-SYN_Flood"],
        "final_far": ["DNS_Spoofing", "MITM-ArpSpoofing"],
        "excluded_families": ["Spoofing", "Web"],
    },
    "preset_c": {
        "dev_near": ["DDoS-ICMP_Fragmentation", "Recon-PortScan"],
        "dev_far": ["Backdoor_Malware", "CommandInjection"],
        "final_near": ["DDoS-UDP_Fragmentation", "Recon-OSScan"],
        "final_far": ["DictionaryBruteForce", "Uploading_Attack"],
        "excluded_families": ["BruteForce", "Web"],
    },
}


def coarse_label(label: str) -> str:
    if label == "BenignTraffic":
        return "Benign"
    if label.startswith("DDoS-"):
        return "DDoS"
    if label.startswith("DoS-"):
        return "DoS"
    if label.startswith("Mirai-"):
        return "Mirai"
    if label.startswith("Recon-") or label == "VulnerabilityScan":
        return "Recon"
    if label in {"DNS_Spoofing", "MITM-ArpSpoofing"}:
        return "Spoofing"
    if label == "DictionaryBruteForce":
        return "BruteForce"
    return "Web"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(4 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=json_default) + "\n", encoding="utf-8")


def write_csv(path: Path, rows: list[dict[str, Any]], columns: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def json_default(value: Any) -> Any:
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return None if not np.isfinite(value) else float(value)
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, Path):
        return str(value)
    raise TypeError(type(value).__name__)


def fetch_rows(label: str, split: str, offset: int, cache_dir: Path) -> list[dict[str, Any]]:
    cache = cache_dir / f"{split}__{label}__{offset:05d}.json"
    if cache.exists():
        payload = json.loads(cache.read_text(encoding="utf-8"))
        return [item["row"] for item in payload.get("rows", [])]

    query = urllib.parse.urlencode(
        {
            "dataset": HF_DATASET,
            "config": HF_CONFIG,
            "split": split,
            "where": f'"Label"=\'{label}\'',
            "offset": offset,
            "length": 100,
        }
    )
    url = f"{DATASET_SERVER}?{query}"
    last_error: Exception | None = None
    for attempt in range(6):
        try:
            request = urllib.request.Request(url, headers={"User-Agent": "flow-security-agent-audit/1.0"})
            with urllib.request.urlopen(request, timeout=120) as response:
                payload = json.loads(response.read().decode("utf-8"))
            cache.parent.mkdir(parents=True, exist_ok=True)
            cache.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            return [item["row"] for item in payload.get("rows", [])]
        except Exception as exc:  # network/API transient errors
            last_error = exc
            time.sleep(min(3 * (attempt + 1), 15))
    raise RuntimeError(f"failed to fetch {split}/{label}/{offset}: {last_error}")


def acquire_probe_sample(cache_dir: Path, output_path: Path, workers: int) -> pd.DataFrame:
    if output_path.exists():
        return pd.read_parquet(output_path)

    requests: list[tuple[str, str, int]] = []
    for label in FINE_COUNTS:
        requests.extend((label, "train", offset) for offset in (0, 100))
        requests.append((label, "validation", 0))

    frames: list[pd.DataFrame] = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(fetch_rows, label, split, offset, cache_dir): (label, split, offset)
            for label, split, offset in requests
        }
        for future in as_completed(futures):
            label, split, offset = futures[future]
            rows = future.result()
            if not rows:
                continue
            frame = pd.DataFrame(rows)
            frame["_requested_label"] = label
            frame["_mirror_split"] = split
            frame["_mirror_offset"] = offset
            frames.append(frame)

    if not frames:
        raise RuntimeError("no mirror rows were acquired")
    data = pd.concat(frames, ignore_index=True)
    data["coarse_label"] = data["Label"].map(coarse_label)
    data["binary_label"] = np.where(data["Label"].eq("BenignTraffic"), "Benign", "Malicious")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    data.to_parquet(output_path, index=False)
    return data


def numeric_features(frame: pd.DataFrame) -> list[str]:
    blocked = {"Label", "attack_class", "label", "coarse_label", "binary_label"}
    blocked.update(col for col in frame.columns if col.startswith("_"))
    return [col for col in frame.columns if col not in blocked and pd.api.types.is_numeric_dtype(frame[col])]


def clean_matrix(frame: pd.DataFrame, features: list[str]) -> np.ndarray:
    values = frame[features].replace([np.inf, -np.inf], np.nan).copy()
    medians = values.median(numeric_only=True).fillna(0.0)
    return values.fillna(medians).to_numpy(dtype=np.float64)


def expected_calibration_error(y_true: np.ndarray, prob: np.ndarray, bins: int = 10) -> float:
    confidence = prob.max(axis=1)
    prediction = prob.argmax(axis=1)
    correctness = prediction == y_true
    edges = np.linspace(0.0, 1.0, bins + 1)
    value = 0.0
    for left, right in zip(edges[:-1], edges[1:]):
        mask = (confidence >= left) & (confidence < right if right < 1 else confidence <= right)
        if mask.any():
            value += mask.mean() * abs(correctness[mask].mean() - confidence[mask].mean())
    return float(value)


def multiclass_brier(y_true: np.ndarray, prob: np.ndarray) -> float:
    one_hot = np.eye(prob.shape[1], dtype=np.float64)[y_true]
    return float(np.mean(np.sum((prob - one_hot) ** 2, axis=1)))


def model_metrics(y_true: np.ndarray, prob: np.ndarray, elapsed_fit: float, elapsed_pred: float) -> dict[str, Any]:
    pred = prob.argmax(axis=1)
    confidence = prob.max(axis=1)
    error = pred != y_true
    risk_coverage = {}
    order = np.argsort(-confidence)
    for coverage in (0.5, 0.8, 0.9, 1.0):
        count = max(1, int(len(order) * coverage))
        risk_coverage[str(coverage)] = float(error[order[:count]].mean())
    return {
        "accuracy": float(accuracy_score(y_true, pred)),
        "balanced_accuracy": float(balanced_accuracy_score(y_true, pred)),
        "macro_f1": float(f1_score(y_true, pred, average="macro", zero_division=0)),
        "weighted_f1": float(f1_score(y_true, pred, average="weighted", zero_division=0)),
        "log_loss": float(log_loss(y_true, prob, labels=np.arange(prob.shape[1]))),
        "brier_multiclass": multiclass_brier(y_true, prob),
        "ece_10bin": expected_calibration_error(y_true, prob),
        "high_confidence_error_rate_at_0_9": float(np.mean(error & (confidence >= 0.9))),
        "mean_confidence": float(confidence.mean()),
        "risk_at_coverage": risk_coverage,
        "fit_seconds": elapsed_fit,
        "predict_seconds": elapsed_pred,
        "n_test": int(len(y_true)),
    }


def make_models() -> dict[str, Any]:
    from lightgbm import LGBMClassifier

    return {
        "lightgbm": LGBMClassifier(
            n_estimators=120,
            learning_rate=0.07,
            num_leaves=31,
            max_depth=-1,
            subsample=0.9,
            colsample_bytree=0.9,
            random_state=SEED,
            n_jobs=1,
            verbosity=-1,
        ),
        "random_forest": RandomForestClassifier(
            n_estimators=160,
            max_depth=16,
            min_samples_leaf=2,
            class_weight="balanced_subsample",
            random_state=SEED,
            n_jobs=1,
        ),
        "logistic_regression": make_pipeline(
            StandardScaler(),
            LogisticRegression(max_iter=600, class_weight="balanced", random_state=SEED),
        ),
    }


def run_task(
    train: pd.DataFrame,
    test: pd.DataFrame,
    features: list[str],
    label_column: str,
    models: dict[str, Any],
) -> dict[str, Any]:
    encoder = LabelEncoder().fit(pd.concat([train[label_column], test[label_column]], ignore_index=True))
    y_train = encoder.transform(train[label_column])
    y_test = encoder.transform(test[label_column])
    x_train = clean_matrix(train, features)
    x_test = clean_matrix(test, features)
    results: dict[str, Any] = {"classes": encoder.classes_.tolist(), "features": features, "models": {}}
    for name, model in models.items():
        estimator = clone(model)
        started = time.perf_counter()
        estimator.fit(x_train, y_train)
        fit_elapsed = time.perf_counter() - started
        started = time.perf_counter()
        prob = estimator.predict_proba(x_test)
        pred_elapsed = time.perf_counter() - started
        results["models"][name] = model_metrics(y_test, prob, fit_elapsed, pred_elapsed)
    return results


def run_ablation(
    train: pd.DataFrame,
    test: pd.DataFrame,
    all_features: list[str],
    model: Any,
) -> dict[str, Any]:
    candidates = {
        "full": all_features,
        "without_number": [col for col in all_features if col != "Number"],
        "without_available_window_fields": [col for col in all_features if col not in WINDOW_FIELDS],
        "only_available_window_fields": [col for col in all_features if col in WINDOW_FIELDS],
        "only_number": [col for col in all_features if col == "Number"],
        "without_protocol_behavior_fields": [col for col in all_features if col not in PROTOCOL_FIELDS],
    }
    results = {}
    for name, features in candidates.items():
        if not features:
            results[name] = {"status": "NOT_AVAILABLE"}
            continue
        task = run_task(train, test, features, "Label", {"lightgbm": model})
        results[name] = {"feature_count": len(features), **task["models"]["lightgbm"]}
    missing = sorted(set(WINDOW_FIELDS) - set(all_features))
    results["window_fields_absent_from_secondary_mirror"] = missing
    return results


def duplicate_audit(train: pd.DataFrame, test: pd.DataFrame, features: list[str]) -> dict[str, Any]:
    combined = pd.concat([train.assign(_partition="train"), test.assign(_partition="validation")], ignore_index=True)
    normalized = combined[features].replace([np.inf, -np.inf], np.nan).fillna(-9.87654321e99)
    hashes = pd.util.hash_pandas_object(normalized, index=False)
    combined = combined.assign(_feature_hash=hashes.to_numpy())
    train_hashes = set(combined.loc[combined["_partition"].eq("train"), "_feature_hash"])
    test_hashes = set(combined.loc[combined["_partition"].eq("validation"), "_feature_hash"])
    overlap = train_hashes & test_hashes
    conflicting = (
        combined.groupby("_feature_hash", sort=False)["Label"].nunique().gt(1).sum()
    )
    return {
        "train_unique_feature_vectors": len(train_hashes),
        "validation_unique_feature_vectors": len(test_hashes),
        "cross_partition_exact_feature_overlap": len(overlap),
        "cross_partition_overlap_fraction_of_validation_unique": float(len(overlap) / max(1, len(test_hashes))),
        "feature_vectors_with_multiple_labels": int(conflicting),
        "note": "Computed only on the capped secondary-mirror sample; it is not a full-dataset duplicate count.",
    }


def feature_shortcut_probe(train: pd.DataFrame, test: pd.DataFrame, features: list[str]) -> dict[str, Any]:
    encoder = LabelEncoder().fit(pd.concat([train["Label"], test["Label"]], ignore_index=True))
    y_train = encoder.transform(train["Label"])
    y_test = encoder.transform(test["Label"])
    x_train = clean_matrix(train, features)
    x_test = clean_matrix(test, features)
    mi = mutual_info_classif(x_train, y_train, discrete_features=False, random_state=SEED)
    rows = []
    for idx, feature in enumerate(features):
        tree = DecisionTreeClassifier(max_depth=3, min_samples_leaf=5, random_state=SEED)
        tree.fit(x_train[:, [idx]], y_train)
        pred = tree.predict(x_test[:, [idx]])
        rows.append(
            {
                "feature": feature,
                "mutual_information": float(mi[idx]),
                "depth3_tree_macro_f1": float(f1_score(y_test, pred, average="macro", zero_division=0)),
                "depth3_tree_accuracy": float(accuracy_score(y_test, pred)),
            }
        )
    rows.sort(key=lambda item: (item["depth3_tree_macro_f1"], item["mutual_information"]), reverse=True)
    number_table = None
    if "Number" in train.columns:
        temp = train.assign(window_bucket=np.where(train["Number"].lt(50), "short_or_10", "long_or_100"))
        number_table = pd.crosstab(temp["coarse_label"], temp["window_bucket"], normalize="index").round(6).to_dict()
    return {"single_feature_rank": rows, "number_by_coarse_label_fraction": number_table}


def label_shuffle_probe(train: pd.DataFrame, test: pd.DataFrame, features: list[str], model: Any) -> dict[str, Any]:
    encoder = LabelEncoder().fit(pd.concat([train["Label"], test["Label"]], ignore_index=True))
    y_train = encoder.transform(train["Label"])
    y_test = encoder.transform(test["Label"])
    rng = np.random.default_rng(SEED)
    shuffled = rng.permutation(y_train)
    estimator = clone(model)
    estimator.fit(clean_matrix(train, features), shuffled)
    pred = estimator.predict(clean_matrix(test, features))
    return {
        "macro_f1": float(f1_score(y_test, pred, average="macro", zero_division=0)),
        "accuracy": float(accuracy_score(y_test, pred)),
        "random_accuracy_reference": float(1.0 / len(encoder.classes_)),
        "classes": len(encoder.classes_),
    }


def saturation_probe(train: pd.DataFrame, test: pd.DataFrame, features: list[str], model: Any) -> list[dict[str, Any]]:
    rows = []
    for per_class in (25, 50, 100, 200):
        subset = (
            train.groupby("Label", group_keys=False, sort=True)
            .head(per_class)
            .reset_index(drop=True)
        )
        result = run_task(subset, test, features, "Label", {"lightgbm": model})["models"]["lightgbm"]
        rows.append({"train_rows_per_class": per_class, "train_rows": len(subset), **result})
    return rows


def fpr_at_tpr(y_unknown: np.ndarray, score: np.ndarray, target_tpr: float = 0.95) -> float:
    thresholds = np.unique(score)[::-1]
    positives = max(1, int(y_unknown.sum()))
    negatives = max(1, int((~y_unknown).sum()))
    for threshold in thresholds:
        selected = score >= threshold
        tpr = int((selected & y_unknown).sum()) / positives
        if tpr >= target_tpr:
            return float((selected & ~y_unknown).sum() / negatives)
    return 1.0


def open_set_probe(train: pd.DataFrame, test: pd.DataFrame, features: list[str], model: Any) -> dict[str, Any]:
    preset = PRESETS["preset_a"]
    held_out = set(preset["dev_near"] + preset["dev_far"] + preset["final_near"] + preset["final_far"])
    held_out.update(label for label in FINE_COUNTS if coarse_label(label) in preset["excluded_families"])
    planned_known = [label for label in FINE_COUNTS if label not in held_out]
    known_train = train[train["Label"].isin(planned_known)].copy()
    known = sorted(known_train["Label"].unique().tolist())
    known_test = test[test["Label"].isin(known)].copy()
    unknown_test = test[test["Label"].isin(preset["final_near"] + preset["final_far"])].copy()
    evaluation = pd.concat([known_test, unknown_test], ignore_index=True)
    encoder = LabelEncoder().fit(known)
    estimator = clone(model)
    estimator.fit(clean_matrix(known_train, features), encoder.transform(known_train["Label"]))
    prob = estimator.predict_proba(clean_matrix(evaluation, features))
    unknown_score = 1.0 - prob.max(axis=1)
    unknown_truth = ~evaluation["Label"].isin(known).to_numpy()
    known_prob = prob[: len(known_test)]
    known_pred = encoder.inverse_transform(known_prob.argmax(axis=1))
    return {
        "preset": "preset_a",
        "known_classes": known,
        "final_unknown": preset["final_near"] + preset["final_far"],
        "known_test_macro_f1": float(f1_score(known_test["Label"], known_pred, average="macro", zero_division=0)),
        "unknown_msp_auroc": float(roc_auc_score(unknown_truth, unknown_score)),
        "unknown_fpr_at_95_tpr": fpr_at_tpr(unknown_truth, unknown_score, 0.95),
        "mean_unknown_score_known": float(unknown_score[~unknown_truth].mean()),
        "mean_unknown_score_unknown": float(unknown_score[unknown_truth].mean()),
        "n_known_test": int((~unknown_truth).sum()),
        "n_unknown_test": int(unknown_truth.sum()),
        "warning": "Exploratory only: secondary mirror, capped rows, random row split, no capture isolation.",
    }


def build_distribution_rows() -> list[dict[str, Any]]:
    total = sum(FINE_COUNTS.values())
    rows = []
    for label, count in sorted(FINE_COUNTS.items(), key=lambda item: item[1], reverse=True):
        rows.append(
            {
                "fine_label": label,
                "coarse_label": coarse_label(label),
                "official_paper_rows": count,
                "fraction_of_total": count / total,
                "official_experiment_unit": "one attack experiment" if label != "BenignTraffic" else "16-hour benign collection",
                "independent_source_groups_confirmed": 1,
                "group_split_feasible": "no",
                "source": OFFICIAL_PAPER,
            }
        )
    return rows


def build_source_group_rows() -> list[dict[str, Any]]:
    return [
        {
            "fine_label": label,
            "coarse_label": coarse_label(label),
            "paper_experiment_description": "one experiment per attack" if label != "BenignTraffic" else "one 16-hour benign collection",
            "confirmed_independent_experiments": 1,
            "official_blended_csv_has_capture_id": "no",
            "spark_part_number_is_valid_source_group": "no",
            "formal_group_train_val_test_split": "not feasible from released blended CSV",
            "evidence": "Sensors 2023 section 3.3 and section 5; CSV combined and shuffled with PySpark",
        }
        for label in FINE_COUNTS
    ]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--skip-fetch", action="store_true")
    args = parser.parse_args()

    project = args.project_root.resolve()
    report = project / "reports" / "dataset_audit" / "2026-08-ciciot2023-main-validation"
    raw = project / "data" / "raw" / "ciciot2023_audit_probe"
    cache = raw / "datasets_server_cache"
    sample_path = raw / "hf_secondary_probe.parquet"
    report.mkdir(parents=True, exist_ok=True)

    sys.path.insert(0, str(project / ".test-tmp" / "ciciot_deps"))
    try:
        from lightgbm import LGBMClassifier  # noqa: F401
    except Exception as exc:
        raise RuntimeError("LightGBM is required in .test-tmp/ciciot_deps for this probe") from exc

    if args.skip_fetch and not sample_path.exists():
        raise FileNotFoundError(sample_path)
    data = pd.read_parquet(sample_path) if args.skip_fetch else acquire_probe_sample(cache, sample_path, args.workers)
    train = data[data["_mirror_split"].eq("train")].copy().sort_values(["Label", "_mirror_offset"]).reset_index(drop=True)
    test = data[data["_mirror_split"].eq("validation")].copy().sort_values(["Label", "_mirror_offset"]).reset_index(drop=True)
    features = numeric_features(data)
    models = make_models()

    baseline = {
        "binary": run_task(train, test, features, "binary_label", models),
        "coarse": run_task(train, test, features, "coarse_label", models),
        "fine": run_task(train, test, features, "Label", models),
    }
    lightgbm = models["lightgbm"]
    results = {
        "audit_seed": SEED,
        "probe_source": {
            "dataset": HF_DATASET,
            "config": HF_CONFIG,
            "status": "SECONDARY_MIRROR_EXPLORATORY_ONLY",
            "rows": len(data),
            "train_rows": len(train),
            "validation_rows": len(test),
            "sample_sha256": sha256(sample_path),
            "warning": "Not an official archive; subsampled/preprocessed and random-row split by mirror maintainer.",
        },
        "schema": {
            "columns": data.columns.tolist(),
            "numeric_features": features,
            "numeric_feature_count": len(features),
            "official_paper_feature_count": 47,
            "sample_unit_official": "fixed-size packet window, not a conventional bidirectional Flow row",
            "window_sizes": {"non_large_scale_and_benign": 10, "DDoS_DoS_Mirai": 100},
            "capture_id_present": False,
            "source_group_id_present": False,
        },
        "sample_class_counts": {
            "train": Counter(train["Label"]).most_common(),
            "validation": Counter(test["Label"]).most_common(),
        },
        "baseline": baseline,
        "fine_ablation": run_ablation(train, test, features, lightgbm),
        "shortcut_probe": feature_shortcut_probe(train, test, features),
        "label_shuffle": label_shuffle_probe(train, test, features, lightgbm),
        "duplicates": duplicate_audit(train, test, features),
        "saturation": saturation_probe(train, test, features, lightgbm),
        "open_set_probe": open_set_probe(train, test, features, lightgbm),
        "unknown_presets": PRESETS,
        "formal_split_feasibility": "NO",
        "formal_split_reason": "Official blended CSV is combined/shuffled and lacks capture or attack-run IDs; one attack experiment per fine label does not support within-class group separation.",
    }
    write_json(report / "cpu_probe_results.json", results)
    write_json(
        report / "probe_download_manifest.json",
        {
            "downloaded_at": "2026-08-04",
            "official_page": OFFICIAL_PAGE,
            "official_paper": OFFICIAL_PAPER,
            "official_download_status": "BLOCKED_BY_FORM_AND_REDIRECT_DURING_AUDIT",
            "secondary_probe_dataset": HF_DATASET,
            "secondary_probe_config": HF_CONFIG,
            "secondary_probe_rows": len(data),
            "secondary_probe_sha256": sha256(sample_path),
            "secondary_probe_role": "exploratory CPU/shortcut probe only; not formal evidence for benchmark performance",
            "pcap_downloaded": False,
        },
    )

    distribution_rows = build_distribution_rows()
    write_csv(
        report / "03_class_distribution.csv",
        distribution_rows,
        [
            "fine_label",
            "coarse_label",
            "official_paper_rows",
            "fraction_of_total",
            "official_experiment_unit",
            "independent_source_groups_confirmed",
            "group_split_feasible",
            "source",
        ],
    )
    group_rows = build_source_group_rows()
    write_csv(
        report / "04_source_group_matrix.csv",
        group_rows,
        [
            "fine_label",
            "coarse_label",
            "paper_experiment_description",
            "confirmed_independent_experiments",
            "official_blended_csv_has_capture_id",
            "spark_part_number_is_valid_source_group",
            "formal_group_train_val_test_split",
            "evidence",
        ],
    )
    print(json.dumps({"report": str(report), "rows": len(data), "features": len(features)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
