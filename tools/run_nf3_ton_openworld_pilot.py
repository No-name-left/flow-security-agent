#!/usr/bin/env python3
"""Run the bounded NF3-ToN Evidence/open-world feasibility pilot.

The input is the deterministic Git-external NF3-ToN stratified sample created
by the preceding NF3 feasibility audit.  The tool never reads raw PCAP, calls
an API, or trains Qwen.  Raw addresses and absolute timestamps are used only
to build group IDs and strictly-past lookup features; they never enter a
classifier or utility selector.

This remains a diagnostic pilot.  The temporal/relation context is computed
from earlier rows in the bounded sample, rather than the full 27.5M-row
release, and must not be presented as a formal Dataset-v4 result.
"""

from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
from scipy.stats import spearmanr
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    average_precision_score,
    f1_score,
    mean_absolute_error,
    roc_auc_score,
)
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from tools.run_nf3_feasibility_pilot import (
    build_past_only_features,
    safe_matrix,
    table_to_numpy,
)


CORE_CLASS_ORDER = (
    "Backdoor",
    "Benign",
    "Credential",
    "DDoS",
    "DoS",
    "Recon_Scanning",
    "Web_Injection",
)
UNKNOWN_ROTATIONS = ("Credential", "Recon_Scanning", "Web_Injection")
UTILITY_SELECTOR_FEATURE_CONTRACT = (
    "SAFE_BASIC",
    "BASIC_CLASSIFIER_MAX_CONFIDENCE",
    "BASIC_CLASSIFIER_MARGIN",
    "BASIC_CLASSIFIER_ENTROPY",
)
FORBIDDEN_SELECTOR_INPUTS = (
    "GT",
    "LABEL",
    "FULL_EVIDENCE",
    "FUTURE_TRAFFIC",
    "ABSOLUTE_IDENTITY",
    "ABSOLUTE_TIMESTAMP",
)


def ton_broad_label(fine: str) -> str | None:
    """Map only the preregistered ToN-only candidate taxonomy."""

    return {
        "Benign": "Benign",
        "ddos": "DDoS",
        "dos": "DoS",
        "scanning": "Recon_Scanning",
        "password": "Credential",
        "xss": "Web_Injection",
        "injection": "Web_Injection",
        "Backdoor": "Backdoor",
    }.get(fine)


def group_id(
    start_ms: int,
    source_address: str,
    destination_address: str,
) -> str:
    """Return a private grouping key; callers persist only its digest."""

    endpoint_pair = "|".join(sorted((source_address, destination_address)))
    return f"{start_ms // 300_000}|{endpoint_pair}"


def group_digest(value: str) -> str:
    return hashlib.blake2b(value.encode("utf-8"), digest_size=16).hexdigest()


def stable_group_fold(value: str, folds: int, seed: int) -> int:
    if folds < 2:
        raise ValueError("folds must be at least 2")
    digest = hashlib.blake2b(
        f"{seed}|oof|{value}".encode("utf-8"), digest_size=8
    ).digest()
    return int.from_bytes(digest, "big") % folds


def stable_openworld_partition(value: str, seed: int) -> str:
    """Deterministically assign an entire group to 60/20/20 partitions."""

    digest = hashlib.blake2b(
        f"{seed}|openworld|{value}".encode("utf-8"), digest_size=8
    ).digest()
    bucket = int.from_bytes(digest, "big") % 10
    if bucket < 6:
        return "train"
    if bucket < 8:
        return "calibration"
    return "evaluation"


def iter_oof_masks(
    groups: np.ndarray,
    *,
    folds: int,
    seed: int,
) -> Iterable[tuple[int, np.ndarray, np.ndarray]]:
    """Yield disjoint group-level train/evaluation masks for each OOF fold."""

    fold_ids = np.array(
        [stable_group_fold(str(value), folds, seed) for value in groups], dtype=int
    )
    for fold in range(folds):
        evaluation = fold_ids == fold
        train = ~evaluation
        if set(groups[train].tolist()) & set(groups[evaluation].tolist()):
            raise ValueError(f"group leakage detected in OOF fold {fold}")
        yield fold, train, evaluation


def openworld_masks(
    labels: np.ndarray,
    partitions: np.ndarray,
    *,
    holdout: str,
) -> dict[str, np.ndarray]:
    """Build masks that exclude the whole Unknown class from train/calibration."""

    known = labels != holdout
    unknown = labels == holdout
    evaluation = partitions == "evaluation"
    return {
        "known": known,
        "unknown": unknown,
        "train": known & (partitions == "train"),
        "calibration": known & (partitions == "calibration"),
        "evaluation": evaluation,
        "known_evaluation": known & evaluation,
        "unknown_evaluation": unknown & evaluation,
    }


def calibrate_known_confidence_threshold(
    known_confidence: np.ndarray,
    *,
    known_fpr: float,
) -> float:
    """Calibrate from Known-only scores; no Unknown input is accepted."""

    values = np.asarray(known_confidence, dtype=np.float64)
    if values.ndim != 1 or len(values) == 0:
        raise ValueError("known_confidence must be a non-empty vector")
    if not 0.0 < known_fpr < 1.0:
        raise ValueError("known_fpr must be between zero and one")
    return float(np.quantile(values, known_fpr, method="higher"))


def _aligned_probabilities(
    model: RandomForestClassifier,
    matrix: np.ndarray,
    classes: tuple[str, ...],
) -> np.ndarray:
    raw = model.predict_proba(matrix)
    output = np.zeros((len(matrix), len(classes)), dtype=np.float64)
    positions = {label: index for index, label in enumerate(classes)}
    for source_index, label in enumerate(model.classes_.tolist()):
        output[:, positions[str(label)]] = raw[:, source_index]
    return output


def _fit_classifier(
    matrix: np.ndarray,
    labels: np.ndarray,
    train: np.ndarray,
    *,
    seed: int,
    trees: int,
) -> RandomForestClassifier:
    model = RandomForestClassifier(
        n_estimators=trees,
        max_depth=20,
        min_samples_leaf=2,
        class_weight="balanced_subsample",
        # Single-threaded tree construction keeps the diagnostic exactly
        # reproducible across repeated runs; the bounded 24k-row pilot remains
        # inexpensive at this scale.
        n_jobs=1,
        random_state=seed,
    )
    model.fit(matrix[train], labels[train])
    return model


def _probability_diagnostics(
    probabilities: np.ndarray,
    labels: np.ndarray,
    classes: tuple[str, ...],
) -> dict[str, np.ndarray]:
    positions = {label: index for index, label in enumerate(classes)}
    true_positions = np.array([positions[str(label)] for label in labels], dtype=int)
    true_probability = probabilities[np.arange(len(labels)), true_positions]
    prediction_positions = probabilities.argmax(axis=1)
    prediction = np.array([classes[index] for index in prediction_positions], dtype=object)
    ordered = np.sort(probabilities, axis=1)
    max_confidence = ordered[:, -1]
    second = ordered[:, -2] if probabilities.shape[1] > 1 else np.zeros(len(labels))
    entropy = -np.sum(
        probabilities * np.log(np.clip(probabilities, 1e-12, 1.0)), axis=1
    )
    return {
        "true_probability": true_probability,
        "nll": -np.log(np.clip(true_probability, 1e-6, 1.0)),
        "prediction": prediction,
        "correct": prediction == labels,
        "max_confidence": max_confidence,
        "margin": max_confidence - second,
        "entropy": entropy,
    }


@dataclass
class CrossfitResult:
    basic_probabilities: np.ndarray
    full_probabilities: np.ndarray
    basic: dict[str, np.ndarray]
    full: dict[str, np.ndarray]
    uncertainty_threshold: np.ndarray
    folds: np.ndarray


def crossfit_basic_full(
    basic_matrix: np.ndarray,
    full_matrix: np.ndarray,
    labels: np.ndarray,
    groups: np.ndarray,
    *,
    folds: int,
    seed: int,
    trees: int,
    classes: tuple[str, ...] | None = None,
) -> CrossfitResult:
    """Generate grouped OOF predictions; no model scores its own train rows."""

    classes = classes or tuple(sorted(set(labels.tolist())))
    fold_ids = np.array(
        [stable_group_fold(str(value), folds, seed) for value in groups], dtype=int
    )
    basic_probabilities = np.zeros((len(labels), len(classes)), dtype=np.float64)
    full_probabilities = np.zeros((len(labels), len(classes)), dtype=np.float64)
    thresholds = np.zeros(len(labels), dtype=np.float64)

    for fold, train, evaluation in iter_oof_masks(
        groups, folds=folds, seed=seed
    ):
        if not evaluation.any() or not train.any():
            raise ValueError(f"empty OOF partition for fold {fold}")
        if set(labels[train].tolist()) != set(classes):
            raise ValueError(f"fold {fold} training is missing a class")
        basic_model = _fit_classifier(
            basic_matrix, labels, train, seed=seed + fold * 17, trees=trees
        )
        full_model = _fit_classifier(
            full_matrix, labels, train, seed=seed + fold * 17 + 1, trees=trees
        )
        basic_probabilities[evaluation] = _aligned_probabilities(
            basic_model, basic_matrix[evaluation], classes
        )
        full_probabilities[evaluation] = _aligned_probabilities(
            full_model, full_matrix[evaluation], classes
        )
        train_confidence = _aligned_probabilities(
            basic_model, basic_matrix[train], classes
        ).max(axis=1)
        thresholds[evaluation] = calibrate_known_confidence_threshold(
            train_confidence, known_fpr=0.10
        )

    return CrossfitResult(
        basic_probabilities=basic_probabilities,
        full_probabilities=full_probabilities,
        basic=_probability_diagnostics(basic_probabilities, labels, classes),
        full=_probability_diagnostics(full_probabilities, labels, classes),
        uncertainty_threshold=thresholds,
        folds=fold_ids,
    )


def recovered_known_mask(result: CrossfitResult) -> np.ndarray:
    uncertain_or_wrong = (~result.basic["correct"]) | (
        result.basic["max_confidence"] < result.uncertainty_threshold
    )
    return uncertain_or_wrong & result.full["correct"]


def utility_selector_matrix(
    basic_matrix: np.ndarray,
    basic_probabilities: np.ndarray,
) -> np.ndarray:
    """Build the selector input from Basic-visible state only."""

    ordered = np.sort(basic_probabilities, axis=1)
    confidence = ordered[:, -1]
    second = ordered[:, -2] if basic_probabilities.shape[1] > 1 else np.zeros(len(confidence))
    entropy = -np.sum(
        basic_probabilities * np.log(np.clip(basic_probabilities, 1e-12, 1.0)),
        axis=1,
    )
    return np.column_stack([basic_matrix, confidence, confidence - second, entropy])


def _fit_utility_selector(
    matrix: np.ndarray,
    target: np.ndarray,
    *,
    seed: int,
) -> Any:
    if len(set(target.tolist())) < 2:
        return ConstantProbability(float(target.mean()))
    model = make_pipeline(
        StandardScaler(),
        LogisticRegression(
            class_weight="balanced",
            max_iter=1000,
            random_state=seed,
        ),
    )
    model.fit(matrix, target.astype(int))
    return model


@dataclass
class ConstantProbability:
    probability: float

    def predict_proba(self, matrix: np.ndarray) -> np.ndarray:
        positive = np.full(len(matrix), self.probability, dtype=np.float64)
        return np.column_stack([1.0 - positive, positive])


def nested_utility_predictions(
    basic_matrix: np.ndarray,
    full_matrix: np.ndarray,
    labels: np.ndarray,
    groups: np.ndarray,
    outer: CrossfitResult,
    *,
    folds: int,
    seed: int,
    trees: int,
    classes: tuple[str, ...],
) -> tuple[np.ndarray, dict[str, Any]]:
    """Predict utility with an outer meta split and inner OOF targets."""

    selector_score = np.zeros(len(labels), dtype=np.float64)
    outer_target = recovered_known_mask(outer)
    for fold in range(folds):
        evaluation = outer.folds == fold
        train = ~evaluation
        inner = crossfit_basic_full(
            basic_matrix[train],
            full_matrix[train],
            labels[train],
            groups[train],
            folds=folds,
            seed=seed + 10_000 + fold * 101,
            trees=trees,
            classes=classes,
        )
        inner_target = recovered_known_mask(inner)
        train_selector = utility_selector_matrix(
            basic_matrix[train], inner.basic_probabilities
        )
        evaluation_selector = utility_selector_matrix(
            basic_matrix[evaluation], outer.basic_probabilities[evaluation]
        )
        model = _fit_utility_selector(
            train_selector, inner_target, seed=seed + 20_000 + fold
        )
        selector_score[evaluation] = model.predict_proba(evaluation_selector)[:, 1]

    target = outer_target.astype(int)
    prediction = selector_score >= 0.5
    metrics = {
        "auroc": float(roc_auc_score(target, selector_score)),
        "aupr": float(average_precision_score(target, selector_score)),
        "f1_at_0_5": float(f1_score(target, prediction, zero_division=0)),
        "positive_rate": float(target.mean()),
        "threshold": 0.5,
        "selector": "standardized class-balanced logistic regression",
        "outer_folds": folds,
        "inner_folds": folds,
        "input_contract": list(UTILITY_SELECTOR_FEATURE_CONTRACT),
        "forbidden_inputs": list(FORBIDDEN_SELECTOR_INPUTS),
    }
    return selector_score, metrics


def _per_class_recoverability(
    labels: np.ndarray,
    result: CrossfitResult,
) -> dict[str, Any]:
    recovered = recovered_known_mask(result)
    delta_nll = result.basic["nll"] - result.full["nll"]
    output: dict[str, Any] = {}
    for label in sorted(set(labels.tolist())):
        mask = labels == label
        output[label] = {
            "n": int(mask.sum()),
            "basic_correct_rate": float(result.basic["correct"][mask].mean()),
            "full_correct_rate": float(result.full["correct"][mask].mean()),
            "basic_uncertain_rate": float(
                (result.basic["max_confidence"][mask] < result.uncertainty_threshold[mask]).mean()
            ),
            "recovered_known_n": int(recovered[mask].sum()),
            "recovered_known_rate": float(recovered[mask].mean()),
            "delta_nll_mean": float(delta_nll[mask].mean()),
            "delta_nll_median": float(np.median(delta_nll[mask])),
            "positive_delta_nll_rate": float((delta_nll[mask] > 0).mean()),
        }
    return output


def _known_macro_f1(
    truth: np.ndarray,
    prediction: np.ndarray,
    known_classes: tuple[str, ...],
) -> float:
    return float(
        f1_score(
            truth,
            prediction,
            labels=list(known_classes),
            average="macro",
            zero_division=0,
        )
    )


def _unknown_metrics(
    unknown_truth: np.ndarray,
    novelty_score: np.ndarray,
    known_validation_score: np.ndarray,
    *,
    known_fpr: float,
) -> dict[str, Any]:
    # Tree probabilities are discrete and often tied.  A strict comparison at
    # the conservative upper quantile prevents a tie block from silently
    # exceeding the preregistered Known-FPR budget.
    score_threshold = float(
        np.quantile(known_validation_score, 1.0 - known_fpr, method="higher")
    )
    prediction = novelty_score > score_threshold
    known = ~unknown_truth
    unknown = unknown_truth
    return {
        "auroc": float(roc_auc_score(unknown_truth.astype(int), novelty_score)),
        "aupr": float(average_precision_score(unknown_truth.astype(int), novelty_score)),
        "unknown_recall_at_fixed_known_fpr": float(prediction[unknown].mean()),
        "known_fpr_target": known_fpr,
        "known_fpr_observed": float(prediction[known].mean()),
        "score_threshold_from_known_validation_only": score_threshold,
        "threshold_operator": ">",
        "prediction": prediction,
    }


def _rotation_utility_selector(
    basic_matrix: np.ndarray,
    full_matrix: np.ndarray,
    labels: np.ndarray,
    groups: np.ndarray,
    known_train: np.ndarray,
    *,
    folds: int,
    seed: int,
    trees: int,
    classes: tuple[str, ...],
) -> Any:
    crossfit = crossfit_basic_full(
        basic_matrix[known_train],
        full_matrix[known_train],
        labels[known_train],
        groups[known_train],
        folds=folds,
        seed=seed,
        trees=trees,
        classes=classes,
    )
    target = recovered_known_mask(crossfit)
    matrix = utility_selector_matrix(
        basic_matrix[known_train], crossfit.basic_probabilities
    )
    return _fit_utility_selector(matrix, target, seed=seed + 999)


def _evaluate_policy(
    *,
    name: str,
    labels: np.ndarray,
    evaluation: np.ndarray,
    known_evaluation: np.ndarray,
    unknown_evaluation: np.ndarray,
    known_calibration: np.ndarray,
    known_classes: tuple[str, ...],
    basic_probabilities: np.ndarray,
    full_probabilities: np.ndarray,
    acquire_calibration: np.ndarray,
    acquire_evaluation: np.ndarray,
    recoverable_known: np.ndarray,
    known_fpr: float,
) -> dict[str, Any]:
    selected_calibration = np.where(
        acquire_calibration[:, None],
        full_probabilities[known_calibration],
        basic_probabilities[known_calibration],
    )
    selected_evaluation = np.where(
        acquire_evaluation[:, None],
        full_probabilities[evaluation],
        basic_probabilities[evaluation],
    )
    calibration_score = 1.0 - selected_calibration.max(axis=1)
    evaluation_score = 1.0 - selected_evaluation.max(axis=1)
    unknown_metrics = _unknown_metrics(
        unknown_evaluation[evaluation],
        evaluation_score,
        calibration_score,
        known_fpr=known_fpr,
    )
    reject = unknown_metrics.pop("prediction")
    class_prediction = np.array(
        [known_classes[index] for index in selected_evaluation.argmax(axis=1)],
        dtype=object,
    )
    class_prediction[reject] = "__UNKNOWN__"
    known_eval_local = known_evaluation[evaluation]
    recoverable_local = recoverable_known[evaluation]
    false_unknown_n = int((reject & recoverable_local).sum())
    recoverable_n = int(recoverable_local.sum())
    return {
        "policy": name,
        **unknown_metrics,
        "known_macro_f1": _known_macro_f1(
            labels[evaluation][known_eval_local],
            class_prediction[known_eval_local],
            known_classes,
        ),
        "recoverable_known_n": recoverable_n,
        "false_unknown_on_recoverable_known_n": false_unknown_n,
        "false_unknown_on_recoverable_known_rate": (
            float(false_unknown_n / recoverable_n) if recoverable_n else None
        ),
        "recoverable_known_final_accuracy": (
            float(
                (
                    class_prediction[recoverable_local]
                    == labels[evaluation][recoverable_local]
                ).mean()
            )
            if recoverable_n
            else None
        ),
        "evidence_acquisition_n": int(acquire_evaluation.sum()),
        "evidence_acquisition_rate": float(acquire_evaluation.mean()),
        "average_extra_evidence_steps": float(acquire_evaluation.mean()),
    }


def openworld_rotation(
    basic_matrix: np.ndarray,
    full_matrix: np.ndarray,
    labels: np.ndarray,
    groups: np.ndarray,
    partitions: np.ndarray,
    *,
    holdout: str,
    folds: int,
    seed: int,
    trees: int,
) -> dict[str, Any]:
    known_classes = tuple(label for label in CORE_CLASS_ORDER if label != holdout)
    masks = openworld_masks(labels, partitions, holdout=holdout)
    known = masks["known"]
    unknown = masks["unknown"]
    train = masks["train"]
    calibration = masks["calibration"]
    evaluation = masks["evaluation"]
    known_evaluation = masks["known_evaluation"]
    unknown_evaluation = masks["unknown_evaluation"]
    if set(labels[train].tolist()) != set(known_classes):
        raise ValueError(f"{holdout} rotation training is missing a Known class")

    basic_model = _fit_classifier(
        basic_matrix, labels, train, seed=seed, trees=trees
    )
    full_model = _fit_classifier(
        full_matrix, labels, train, seed=seed + 1, trees=trees
    )
    basic_probabilities = _aligned_probabilities(
        basic_model, basic_matrix, known_classes
    )
    full_probabilities = _aligned_probabilities(
        full_model, full_matrix, known_classes
    )
    basic_diagnostics = _probability_diagnostics(
        basic_probabilities[known], labels[known], known_classes
    )
    full_diagnostics = _probability_diagnostics(
        full_probabilities[known], labels[known], known_classes
    )
    known_indices = np.flatnonzero(known)
    basic_correct = np.zeros(len(labels), dtype=bool)
    full_correct = np.zeros(len(labels), dtype=bool)
    basic_correct[known_indices] = basic_diagnostics["correct"]
    full_correct[known_indices] = full_diagnostics["correct"]

    acquisition_threshold = calibrate_known_confidence_threshold(
        basic_probabilities[calibration].max(axis=1), known_fpr=0.10
    )
    uncertain = basic_probabilities.max(axis=1) < acquisition_threshold
    recoverable_known = known & (uncertain | ~basic_correct) & full_correct

    no_acquisition_calibration = np.zeros(int(calibration.sum()), dtype=bool)
    no_acquisition_evaluation = np.zeros(int(evaluation.sum()), dtype=bool)
    direct = _evaluate_policy(
        name="DIRECT_NOVELTY",
        labels=labels,
        evaluation=evaluation,
        known_evaluation=known_evaluation,
        unknown_evaluation=unknown_evaluation,
        known_calibration=calibration,
        known_classes=known_classes,
        basic_probabilities=basic_probabilities,
        full_probabilities=full_probabilities,
        acquire_calibration=no_acquisition_calibration,
        acquire_evaluation=no_acquisition_evaluation,
        recoverable_known=recoverable_known,
        known_fpr=0.05,
    )
    always = _evaluate_policy(
        name="ALWAYS_ACQUIRE_WHEN_UNCERTAIN",
        labels=labels,
        evaluation=evaluation,
        known_evaluation=known_evaluation,
        unknown_evaluation=unknown_evaluation,
        known_calibration=calibration,
        known_classes=known_classes,
        basic_probabilities=basic_probabilities,
        full_probabilities=full_probabilities,
        acquire_calibration=uncertain[calibration],
        acquire_evaluation=uncertain[evaluation],
        recoverable_known=recoverable_known,
        known_fpr=0.05,
    )

    selector = _rotation_utility_selector(
        basic_matrix,
        full_matrix,
        labels,
        groups,
        train,
        folds=folds,
        seed=seed + 50_000,
        trees=trees,
        classes=known_classes,
    )
    selector_score = selector.predict_proba(
        utility_selector_matrix(basic_matrix, basic_probabilities)
    )[:, 1]
    selector_acquire = uncertain & (selector_score >= 0.5)
    utility = _evaluate_policy(
        name="SIMPLE_UTILITY_SELECTOR",
        labels=labels,
        evaluation=evaluation,
        known_evaluation=known_evaluation,
        unknown_evaluation=unknown_evaluation,
        known_calibration=calibration,
        known_classes=known_classes,
        basic_probabilities=basic_probabilities,
        full_probabilities=full_probabilities,
        acquire_calibration=selector_acquire[calibration],
        acquire_evaluation=selector_acquire[evaluation],
        recoverable_known=recoverable_known,
        known_fpr=0.05,
    )

    return {
        "held_out_unknown_class": holdout,
        "known_classes": list(known_classes),
        "unknown_absent_from_classifier_train": bool(
            holdout not in set(labels[train].tolist())
        ),
        "unknown_absent_from_threshold_calibration": bool(
            holdout not in set(labels[calibration].tolist())
        ),
        "train_n": int(train.sum()),
        "known_calibration_n": int(calibration.sum()),
        "known_evaluation_n": int(known_evaluation.sum()),
        "unknown_evaluation_n": int(unknown_evaluation.sum()),
        "cross_partition_group_overlap": len(
            set(groups[train].tolist())
            & set(groups[calibration | evaluation].tolist())
        ),
        "acquisition_threshold_known_calibration_only": acquisition_threshold,
        "direct": direct,
        "always_acquire_when_uncertain": always,
        "simple_utility_selector": utility,
    }


def _pooled_policy_summary(
    rotations: Iterable[dict[str, Any]],
    key: str,
) -> dict[str, Any]:
    items = [rotation[key] for rotation in rotations]
    recoverable = sum(int(item["recoverable_known_n"]) for item in items)
    false_unknown = sum(
        int(item["false_unknown_on_recoverable_known_n"]) for item in items
    )
    weighted_evaluation = sum(
        int(rotation["known_evaluation_n"] + rotation["unknown_evaluation_n"])
        for rotation in rotations
    )
    acquired = sum(int(item["evidence_acquisition_n"]) for item in items)
    return {
        "mean_unknown_auroc": float(np.mean([item["auroc"] for item in items])),
        "mean_unknown_aupr": float(np.mean([item["aupr"] for item in items])),
        "mean_unknown_recall_at_fixed_known_fpr": float(
            np.mean([item["unknown_recall_at_fixed_known_fpr"] for item in items])
        ),
        "recoverable_known_total": recoverable,
        "false_unknown_on_recoverable_known_n": false_unknown,
        "false_unknown_on_recoverable_known_rate": (
            float(false_unknown / recoverable) if recoverable else None
        ),
        "evidence_acquisition_rate": (
            float(acquired / weighted_evaluation) if weighted_evaluation else 0.0
        ),
    }


def run(args: argparse.Namespace) -> tuple[dict[str, Any], pa.Table]:
    data = table_to_numpy(args.pilot)
    mapped = np.array([ton_broad_label(str(value)) for value in data["Attack"]], dtype=object)
    eligible = np.array([value is not None for value in mapped], dtype=bool)
    labels = mapped[eligible].astype(object)
    if set(labels.tolist()) != set(CORE_CLASS_ORDER):
        raise ValueError("ToN pilot does not contain the preregistered candidate classes")

    groups = np.array(
        [
            group_id(int(start), str(source), str(destination))
            for start, source, destination in zip(
                data["FLOW_START_MILLISECONDS"][eligible],
                data["IPV4_SRC_ADDR"][eligible],
                data["IPV4_DST_ADDR"][eligible],
                strict=True,
            )
        ],
        dtype=object,
    )
    group_digests = np.array([group_digest(value) for value in groups], dtype=object)
    basic_all, basic_names = safe_matrix(data, include_ports=False)
    past_only_all = build_past_only_features(data)
    basic = basic_all[eligible]
    full = np.column_stack(
        [basic, np.log1p(np.clip(past_only_all[eligible], a_min=0.0, a_max=None))]
    )

    oof = crossfit_basic_full(
        basic,
        full,
        labels,
        groups,
        folds=args.folds,
        seed=args.seed,
        trees=args.trees,
        classes=CORE_CLASS_ORDER,
    )
    recovered = recovered_known_mask(oof)
    delta_nll = oof.basic["nll"] - oof.full["nll"]
    selector_score, utility_metrics = nested_utility_predictions(
        basic,
        full,
        labels,
        groups,
        oof,
        folds=args.folds,
        seed=args.seed,
        trees=args.trees,
        classes=CORE_CLASS_ORDER,
    )
    rho = spearmanr(selector_score, delta_nll).statistic
    utility_metrics["continuous_delta_nll_spearman"] = (
        float(rho) if not math.isnan(float(rho)) else None
    )
    utility_metrics["continuous_delta_nll_mae_from_selector_score"] = float(
        mean_absolute_error(delta_nll, selector_score)
    )

    partitions = np.array(
        [stable_openworld_partition(value, args.seed) for value in groups], dtype=object
    )
    rotations: list[dict[str, Any]] = []
    for index, holdout in enumerate(UNKNOWN_ROTATIONS):
        # A whole-class holdout must not influence Known training even as an
        # unlabeled history row. Known rows therefore use context built with
        # that class masked from history. Held-out evaluation rows retain the
        # deployment-legal all-traffic strictly-past context.
        history_eligible = np.array(
            [value != holdout for value in mapped], dtype=bool
        )
        known_history = build_past_only_features(
            data, history_eligible=history_eligible
        )[eligible]
        rotation_full = np.column_stack(
            [basic, np.log1p(np.clip(known_history, a_min=0.0, a_max=None))]
        )
        rotation_full[labels == holdout] = full[labels == holdout]
        rotations.append(openworld_rotation(
            basic,
            rotation_full,
            labels,
            groups,
            partitions,
            holdout=holdout,
            folds=args.folds,
            seed=args.seed + index * 1_000,
            trees=args.trees,
        ))

    basic_prediction = oof.basic["prediction"]
    full_prediction = oof.full["prediction"]
    per_class = _per_class_recoverability(labels, oof)
    result = {
        "schema_version": "NF3_TON_EVIDENCE_OPENWORLD_PILOT_V1",
        "status": "DIAGNOSTIC_ONLY",
        "seed": args.seed,
        "model": {
            "known_classifier": "RandomForestClassifier",
            "trees": args.trees,
            "max_depth": 20,
            "class_weight": "balanced_subsample",
            "n_jobs": 1,
            "hyperparameter_search": False,
            "gpu_used": False,
        },
        "population": {
            "input_pilot_n": len(mapped),
            "candidate_core_n": int(eligible.sum()),
            "candidate_class_counts": dict(sorted(Counter(labels.tolist()).items())),
            "excluded_fine_counts": dict(
                sorted(Counter(data["Attack"][~eligible].tolist()).items())
            ),
        },
        "evidence_contract": {
            "safe_basic_feature_names": basic_names,
            "safe_basic_feature_count": len(basic_names),
            "safe_basic_contains_ports": False,
            "safe_full": "SAFE_BASIC + sample-local strictly-past Temporal/Relation",
            "absolute_timestamp_model_visible": False,
            "raw_ip_model_visible": False,
            "source_identity_model_visible": False,
            "future_traffic_used": False,
            "equal_timestamp_context_excluded": True,
            "limitations": [
                "past context is drawn from the bounded stratified sample, not the full release",
                "this is not a formal Dataset-v4 split or paper metric",
            ],
        },
        "oof": {
            "folds": args.folds,
            "group": "5-minute UTC block + unordered endpoint pair",
            "group_count": len(set(groups.tolist())),
            "cross_fold_group_overlap": 0,
            "no_self_training": True,
            "basic_accuracy": float(accuracy_score(labels, basic_prediction)),
            "basic_macro_f1": float(
                f1_score(
                    labels,
                    basic_prediction,
                    labels=list(CORE_CLASS_ORDER),
                    average="macro",
                    zero_division=0,
                )
            ),
            "full_accuracy": float(accuracy_score(labels, full_prediction)),
            "full_macro_f1": float(
                f1_score(
                    labels,
                    full_prediction,
                    labels=list(CORE_CLASS_ORDER),
                    average="macro",
                    zero_division=0,
                )
            ),
            "recoverable_known_total": int(recovered.sum()),
            "recoverable_known_rate": float(recovered.mean()),
            "delta_nll_mean": float(delta_nll.mean()),
            "delta_nll_median": float(np.median(delta_nll)),
            "positive_delta_nll_rate": float((delta_nll > 0).mean()),
            "per_class_recoverability": per_class,
        },
        "utility_predictability": utility_metrics,
        "openworld": {
            "partition": "deterministic group-level 60/20/20 train/calibration/evaluation",
            "unknown_threshold": "Known calibration only, fixed 5% Known FPR target",
            "acquisition_threshold": "Known calibration only, fixed 10% uncertainty quantile",
            "heldout_unknown_excluded_from_known_history_lookup": True,
            "unknown_rotations": rotations,
            "pooled": {
                "direct": _pooled_policy_summary(rotations, "direct"),
                "always_acquire_when_uncertain": _pooled_policy_summary(
                    rotations, "always_acquire_when_uncertain"
                ),
                "simple_utility_selector": _pooled_policy_summary(
                    rotations, "simple_utility_selector"
                ),
            },
        },
    }

    trace = pa.table(
        {
            "source_row_index": np.asarray(data["source_row_index"])[eligible],
            "source_fine_label": np.asarray(data["Attack"])[eligible],
            "candidate_broad_label": labels,
            "private_group_digest": group_digests,
            "oof_fold": oof.folds,
            "basic_true_probability": oof.basic["true_probability"],
            "full_true_probability": oof.full["true_probability"],
            "nll_basic": oof.basic["nll"],
            "nll_full": oof.full["nll"],
            "delta_nll": delta_nll,
            "basic_correct": oof.basic["correct"],
            "full_correct": oof.full["correct"],
            "basic_uncertainty_threshold": oof.uncertainty_threshold,
            "basic_uncertain": oof.basic["max_confidence"] < oof.uncertainty_threshold,
            "recovered_known": recovered,
            "utility_selector_score": selector_score,
        }
    )
    return result, trace


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pilot", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--trace-output", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=20260815)
    parser.add_argument("--folds", type=int, default=3)
    parser.add_argument("--trees", type=int, default=80)
    args = parser.parse_args()
    result, trace = run(args)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.trace_output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    pq.write_table(trace, args.trace_output, compression="zstd")
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
