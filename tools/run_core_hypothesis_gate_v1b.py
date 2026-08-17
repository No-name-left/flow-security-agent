#!/usr/bin/env python3
"""CORE HYPOTHESIS FORMAL GATE V1B — Conditional Evidence Utility Separability.

Prospective post-Gate-1 follow-up (Gate 1 = YELLOW, unchanged by this task).

Research question: can runtime-visible BASIC state alone, available BEFORE any
Evidence acquisition, identify which observations are likely to benefit from
TEMPORAL / RELATION Evidence and which are likely to be harmed?

This is a KILL GATE. A FAIL is a valid outcome. No selector hyperparameter
search, no selector-family comparison, no budget changes, no HELP/HARM
redefinition, no added/deleted seeds, no rescue experiment, no Qwen, no
DeepSeek, no RL, no open-world gate, no continual learning.

Frozen decisions (pre-registered before any formal result):
  - Input: frozen Gate 1 validation predictions and TRAIN target set per formal
    seed (20260817/20260818/20260819), artifacts under core_gate_v1/.
    No Gate 1 model is retrained for utility truth; the frozen predictions are
    authoritative. A deterministic reproduction of the frozen BASIC estimator
    (identical config, data and random_state) is used ONLY as a runtime-visible
    probability provider for selector input features; its hard predictions are
    verified to equal the frozen pred_B exactly (abort otherwise).
  - Utility labels: HELP_E (B wrong, B+E correct), HARM_E (B correct, B+E
    wrong), SIGNED_UTILITY_E = +1/-1/0, frozen definitions; denominator for
    every prevalence/net-recovery rate = ALL corresponding validation targets.
  - OOF cross-fitting: 3 folds on the TRAIN target set (175,000/seed), folds
    constructed at the private activity-group level (never split) within
    (class, temporal_block) strata, groups ordered by time and chunked
    contiguously (largest remainder). Each fold trains the frozen Gate 1
    estimator variants B/BT/BR/BTR on the other 2 folds and predicts the
    held-out fold (hard + probability). Coverage must be 100%.
  - Selector: exactly one learned family — RandomForestRegressor
    (n_estimators=200, max_depth=12, min_samples_leaf=20, max_features="sqrt",
    n_jobs=-1, random_state=formal seed), one per family (T, R, TR), trained on
    TRAIN OOF SIGNED_UTILITY labels only. Input = pre-acquisition BASIC state
    only (47 frozen Basic fields + Basic predicted class one-hot + Basic
    probability vector + max-probability + top1-top2 margin + entropy +
    evidence availability mask). No Temporal/Relation/Full features, no GT, no
    HELP/HARM labels, no group/row identity, no FINAL_TEST information.
  - Acquisition budgets: 5 / 10 / 15 / 20 %; PRIMARY = 15 %.
  - Baselines: S0 random (>=100 deterministic reps, mean + CI), S1 low Basic
    confidence, S2 high Basic entropy, S3 learned selector, S4 oracle (true
    signed utility; analysis upper bound only, not evidence of learnability).
  - Selective acquisition simulation: final = B+E prediction for selected
    targets, B otherwise. NET_RECOVERY = (#HELP selected - #HARM selected) /
    #all validation targets.
  - T1-T7 temporal gate, Relation diversity sub-gate, TR secondary analysis:
    thresholds frozen below (see build_temporal_decision).
  - Optional Gate 1 aggregate paired group bootstrap (delta T/R/TR Macro-F1,
    pooled across seeds) computed from frozen predictions only; it cannot
    change CORE_HYPOTHESIS_GATE_1=YELLOW.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import pickle
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
from sklearn.metrics import (
    average_precision_score,
    balanced_accuracy_score,
    f1_score,
    roc_auc_score,
)

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from run_core_hypothesis_gate_v1 import (  # noqa: E402
    BOOTSTRAP_REPS,
    CANONICAL_CLASS_ORDER,
    CONDITIONS,
    DEFAULT_ARTIFACT_ROOT,
    ESTIMATOR_CONFIG,
    EVIDENCE_DELTAS,
    FORMAL_SEEDS,
    HISTORY_FIELDS,
    MODEL_VISIBLE_FIELDS,
    N_TEMPORAL_BLOCKS,
    PARTITION_TRAIN,
    PARTITION_VALIDATION,
    RELATION_FIELDS,
    TEMPORAL_FIELDS,
    build_feature_matrices,
    fit_estimator,
    safe_basic,
)

DEFAULT_GATE1B_ROOT = (
    "/root/autodl-tmp/processed/dataset_v4_nf3_ton_v1/core_gate_v1b"
)

OOF_FOLDS = 3
BUDGETS = (0.05, 0.10, 0.15, 0.20)
PRIMARY_BUDGET = 0.15
RANDOM_REPS = 500
RANDOM_RNG_OFFSET = 41000
T7_RNG_OFFSET = 81000
SELECTOR_RNG_OFFSET = 91000
PROBA_EPS = 1e-12
VAL_PER_SEED = 56_000

FAMILIES = ("T", "R", "TR")
FAMILY_CONDITION = {"T": "BT", "R": "BR", "TR": "BTR"}

SELECTOR_FAMILY = "RandomForestRegressor"
SELECTOR_CONFIG = {
    "n_estimators": 200,
    "max_depth": 12,
    "min_samples_leaf": 20,
    "max_features": "sqrt",
    "n_jobs": -1,
    "random_state": "formal seed",
}
SELECTOR_PROVENANCE = (
    "exactly one learned selector family (RandomForestRegressor), frozen before "
    "any Gate 1B result; config n_estimators=200, max_depth=12, "
    "min_samples_leaf=20, max_features='sqrt', n_jobs=-1, random_state=formal "
    "seed; no hyperparameter search, no family comparison."
)

# Selector input: pre-acquisition BASIC state only.
DERIVED_BASIC_FEATURES = (
    "basic_max_prob", "basic_margin", "basic_entropy", "evidence_availability_mask",
)

FORBIDDEN_SELECTOR_MARKERS = (
    "canonical_label", "digest", "row_id", "partition", "fold", "rotation",
    "source_row", "source_dataset", "source_file", "flow_start", "flow_end",
    "src_code", "dst_code", "group", "attack", "help", "harm", "utility",
    "recover", "temporal_", "relation_", "same_source_last_seen",
)

T1_AUROC = 0.70
T2_AUPR_PREVALENCE_MULTIPLE = 2.0
T3_TOP15_CAPTURE = 0.30
T5_MIN_GAIN = 0.002
T6_MIN_DELTA_MACRO = 0.002
YELLOW_MIN_PASS = 5
YELLOW_MIN_AUROC = 0.65
SEVERE_AUROC = 0.65
SEVERE_TOP15_CAPTURE = 0.25
SEVERE_GAIN = 0.001

RELATION_DIVERSITY_MEAN_RATE = 0.005
RELATION_DIVERSITY_SEED_RATE = 0.004
RELATION_DIVERSITY_SEED_FRACTION = 2.0 / 3.0

R1_AUROC = 0.70
R2_TOP15_CAPTURE = 0.30

HARD_HELP_EPS = 1e-6


# ---------------------------------------------------------------------------
# Deterministic helpers
# ---------------------------------------------------------------------------

def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
                      allow_nan=False)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def entropy_of(proba: np.ndarray) -> np.ndarray:
    """Shannon entropy per row over the frozen class order (0-contributions)."""
    clipped = np.clip(proba, PROBA_EPS, 1.0)
    return -np.sum(clipped * np.log(clipped), axis=1)


def align_proba_to_class_order(proba: np.ndarray, classes: np.ndarray) -> np.ndarray:
    """Reorder predict_proba columns into CANONICAL_CLASS_ORDER."""
    classes = list(classes)
    if classes == list(CANONICAL_CLASS_ORDER):
        return proba
    order = [classes.index(name) for name in CANONICAL_CLASS_ORDER]
    return proba[:, order]


def one_hot_class(predicted: np.ndarray) -> np.ndarray:
    codes = np.array([CANONICAL_CLASS_ORDER.index(name) for name in predicted],
                     dtype=np.int64)
    out = np.zeros((len(predicted), len(CANONICAL_CLASS_ORDER)), dtype=np.float64)
    out[np.arange(len(predicted)), codes] = 1.0
    return out


# ---------------------------------------------------------------------------
# Data loading (frozen Gate 1 artifacts)
# ---------------------------------------------------------------------------

def load_targets(artifact_root: Path, seed: int) -> dict[str, np.ndarray]:
    table = pq.read_table(artifact_root / f"gate_seed_{seed}_targets.parquet")
    return {
        "source_row_index": table["source_row_index"].to_numpy(zero_copy_only=False),
        "canonical_label": np.array(table["canonical_label"].to_pylist(), dtype=object),
        "partition_code": table["partition_code"].to_numpy(),
        "temporal_block": table["temporal_block"].to_numpy(),
        "flow_start_ms": table["flow_start_ms"].to_numpy(),
        "activity_group_digest": np.array(
            [bytes(value) for value in table["activity_group_digest"].to_pylist()],
            dtype=object,
        ),
    }


def load_validation_predictions(artifact_root: Path, seed: int) -> dict[str, np.ndarray]:
    table = pq.read_table(
        artifact_root / f"gate_seed_{seed}_validation_predictions.parquet")
    out = {
        "source_row_index": table["source_row_index"].to_numpy(zero_copy_only=False),
        "canonical_label": np.array(table["canonical_label"].to_pylist(), dtype=object),
        "temporal_block": table["temporal_block"].to_numpy(),
        "activity_group_digest": np.array(
            [bytes(value) for value in table["activity_group_digest"].to_pylist()],
            dtype=object,
        ),
    }
    for condition in CONDITIONS:
        out[f"pred_{condition}"] = np.array(
            table[f"pred_{condition}"].to_pylist(), dtype=object)
    if len(out["canonical_label"]) != VAL_PER_SEED:
        raise SystemExit(f"GATE_1B_STATUS=UNEXPECTED_VALIDATION_N "
                         f"seed={seed} n={len(out['canonical_label'])}")
    return out


def load_basic_features(artifact_root: Path) -> tuple[np.ndarray, np.ndarray]:
    table = pq.read_table(artifact_root / "core_gate_basic_features_v1.parquet")
    rows = table["source_row_index"].to_numpy(zero_copy_only=False)
    positions = {int(value): index for index, value in enumerate(rows)}
    arrays = {
        name: np.asarray(table[name].to_pylist(), dtype=np.float64)
        for name in MODEL_VISIBLE_FIELDS
    }
    return rows, arrays


def basic_matrix_for(rows: np.ndarray, arrays: dict[str, np.ndarray],
                     positions: dict[int, int]) -> np.ndarray:
    local = np.array([positions[int(row)] for row in rows], dtype=np.int64)
    return np.column_stack([arrays[name][local] for name in MODEL_VISIBLE_FIELDS])


def load_history_features(artifact_root: Path, seed: int,
                          rows: np.ndarray) -> tuple[np.ndarray, list[str]]:
    table = pq.read_table(artifact_root / f"gate_seed_{seed}_history.parquet")
    names = [name for name in table.column_names if name != "source_row_index"]
    stored_rows = table["source_row_index"].to_numpy(zero_copy_only=False)
    row_index = {int(value): index for index, value in enumerate(stored_rows)}
    position = np.array([row_index[int(row)] for row in rows], dtype=np.int64)
    values = np.column_stack(
        [table[name].to_numpy(zero_copy_only=False) for name in names])
    return values[position].astype(np.float64), names


# ---------------------------------------------------------------------------
# Utility definitions (frozen)
# ---------------------------------------------------------------------------

def utility_labels(pred_b: np.ndarray, pred_be: np.ndarray, labels: np.ndarray,
                   ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """HELP, HARM, SIGNED_UTILITY for one Evidence family (frozen)."""
    basic_wrong = pred_b != labels
    cond_correct = pred_be == labels
    cond_wrong = pred_be != labels
    basic_correct = pred_b == labels
    help_flag = basic_wrong & cond_correct
    harm_flag = basic_correct & cond_wrong
    signed = np.where(help_flag, 1, np.where(harm_flag, -1, 0)).astype(np.int64)
    return help_flag, harm_flag, signed


def diversity_flags(pred_b, pred_bt, pred_br, pred_btr, labels):
    """Evidence diversity / unique recovery flags (frozen, probe-relative)."""
    basic_wrong = pred_b != labels
    bt_correct = pred_bt == labels
    br_correct = pred_br == labels
    btr_correct = pred_btr == labels
    unique_t = basic_wrong & bt_correct & (pred_br != labels)
    unique_r = basic_wrong & br_correct & (pred_bt != labels)
    shared_tr = basic_wrong & bt_correct & br_correct
    full_only = basic_wrong & (pred_bt != labels) & (pred_br != labels) & btr_correct
    return unique_t, unique_r, shared_tr, full_only


def per_class_counts(flag: np.ndarray, labels: np.ndarray,
                     total: int) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for class_name in CANONICAL_CLASS_ORDER:
        mask = labels == class_name
        out[class_name] = {
            "n": int(mask.sum()),
            "count": int(flag[mask].sum()),
            "rate": float(flag[mask].sum() / max(int(total), 1)),
        }
    return out


# ---------------------------------------------------------------------------
# OOF cross-fitting (TRAIN only, group- and temporal-block-aware)
# ---------------------------------------------------------------------------

def build_oof_folds(targets: dict[str, np.ndarray]) -> np.ndarray:
    """3-fold assignment, atomic at the private activity-group level.

    Each private activity group is assigned exactly ONE fold. A group's fold is
    determined by its PRIMARY (class, temporal_block) stratum — the stratum of
    the group's earliest target row — where groups are ordered chronologically
    (minimum flow_start_ms) and chunked contiguously into 3 bins
    (largest-remainder by target count). All rows of the group carry that fold,
    so duplicate groups and protected temporal units can never leak across OOF
    train/held-out roles, and fold membership is temporally contiguous within
    every stratum.
    """
    train_mask = targets["partition_code"] == PARTITION_TRAIN
    rows_all = np.flatnonzero(train_mask)
    groups = targets["activity_group_digest"][rows_all]
    unique_groups, inverse = np.unique(groups, return_inverse=True)
    starts = targets["flow_start_ms"][rows_all]
    labels = targets["canonical_label"][rows_all]
    blocks = targets["temporal_block"][rows_all]

    # primary stratum per group: the stratum of the group's earliest row.
    # Sort rows by (flow_start_ms, source_row_index) — interleaved group rows
    # and ties (all rows of one flow share flow_start_ms) both stay correct
    # because np.unique keeps the FIRST occurrence per group in this order.
    order = np.lexsort((rows_all, starts))
    _, first_idx = np.unique(groups[order], return_index=True)
    primary_positions = order[first_idx]
    # align primary metadata to group ids (0..n_groups-1)
    gid_index = {bytes(value): index for index, value in enumerate(unique_groups)}
    primary_gidx = np.array(
        [gid_index[bytes(value)] for value in groups[primary_positions]],
        dtype=np.int64)
    reorder = np.argsort(primary_gidx, kind="stable")
    primary_class = labels[primary_positions][reorder]
    primary_block = blocks[primary_positions][reorder]
    primary_start = starts[primary_positions][reorder]
    group_counts = np.bincount(inverse)

    group_fold = np.full(len(unique_groups), -1, dtype=np.int8)
    for class_name in CANONICAL_CLASS_ORDER:
        for block in range(N_TEMPORAL_BLOCKS):
            gids = np.flatnonzero((primary_class == class_name)
                                  & (primary_block == block))
            if not len(gids):
                continue
            pstarts = primary_start[gids]
            counts = group_counts[gids]
            order_g = np.argsort(pstarts, kind="stable")
            total = int(counts.sum())
            # largest-remainder fold sizes: boundaries are ROW-count cutoffs.
            # Each group ends up in the fold whose cumulative row-count range
            # it terminates in (searchsorted, side="left"); groups are never
            # split, remain chronologically contiguous within the stratum, and
            # boundaries are applied to cumulative COUNTS, not to group indices
            # (a stratum with fewer groups than rows must not overrun).
            boundaries = np.floor(
                total * np.arange(1, OOF_FOLDS) / OOF_FOLDS).astype(np.int64)
            cum = np.cumsum(counts[order_g])
            group_fold[gids[order_g]] = np.searchsorted(
                boundaries, cum, side="left").astype(np.int8)
    if (group_fold < 0).any():
        raise SystemExit("GATE_1B_STATUS=OOF_FOLD_ASSIGNMENT_INCOMPLETE")
    fold = group_fold[inverse]
    return fold


def run_oof(args) -> int:
    artifact_root = Path(args.artifact_root)
    gate1_root = Path(args.gate1_root)
    artifact_root.mkdir(parents=True, exist_ok=True)
    for seed in (args.seed,) if args.seed else FORMAL_SEEDS:
        started = time.monotonic()
        print(f"[oof seed {seed}] loading frozen TRAIN targets", flush=True)
        targets = load_targets(gate1_root, seed)
        train_mask = targets["partition_code"] == PARTITION_TRAIN
        rows = targets["source_row_index"][train_mask]
        labels = targets["canonical_label"][train_mask]
        if len(rows) != 175_000:
            raise SystemExit(f"GATE_1B_STATUS=UNEXPECTED_TRAIN_N seed={seed} "
                             f"n={len(rows)}")

        basic_rows, basic_arrays = load_basic_features(gate1_root)
        basic_positions = {int(value): index for index, value in enumerate(basic_rows)}
        basic = basic_matrix_for(rows, basic_arrays, basic_positions)
        history, history_names = load_history_features(gate1_root, seed, rows)
        matrices = build_feature_matrices(basic, history, history_names)

        fold = build_oof_folds(targets)
        print(f"[oof seed {seed}] folds: "
              f"{[int((fold == f).sum()) for f in range(OOF_FOLDS)]}",
              flush=True)

        oof_pred: dict[str, np.ndarray] = {}
        oof_proba: dict[str, np.ndarray] = {}
        for condition in CONDITIONS:
            pred = np.empty(len(rows), dtype=object)
            proba = np.zeros((len(rows), len(CANONICAL_CLASS_ORDER)), dtype=np.float64)
            for fold_id in range(OOF_FOLDS):
                held = fold == fold_id  # fold is already TRAIN-only
                train_here = ~held
                model = fit_estimator(seed)
                model.fit(matrices[condition][train_here], labels[train_here])
                pred[held] = model.predict(matrices[condition][held])
                proba[held] = align_proba_to_class_order(
                    model.predict_proba(matrices[condition][held]), model.classes_)
            oof_pred[condition] = pred
            oof_proba[condition] = proba
            print(f"[oof seed {seed}] {condition} OOF complete", flush=True)

        records = {
            "source_row_index": pa.array(rows, pa.int64()),
            "canonical_label": pa.array(labels, pa.string()),
            "fold_id": pa.array(fold, pa.int8()),
        }
        for condition in CONDITIONS:
            records[f"pred_{condition}"] = pa.array(oof_pred[condition], pa.string())
        for condition in CONDITIONS:
            for index, class_name in enumerate(CANONICAL_CLASS_ORDER):
                records[f"proba_{condition}_{class_name}"] = pa.array(
                    oof_proba[condition][:, index], pa.float64())
        out = artifact_root / f"gate_v1b_seed_{seed}_oof.parquet"
        pq.write_table(pa.table(records), out, compression="zstd")
        print(f"[oof seed {seed}] wrote {out} rows={len(rows)} in "
              f"{time.monotonic() - started:.0f}s", flush=True)
    print("[oof] UTILITY_OOF_COVERAGE=100%")
    return 0


# ---------------------------------------------------------------------------
# Selector features (pre-acquisition BASIC state only) and leakage audit
# ---------------------------------------------------------------------------

def build_selector_features(
    basic: np.ndarray,
    pred_b: np.ndarray,
    proba_b: np.ndarray,
    availability: np.ndarray,
) -> tuple[np.ndarray, list[str]]:
    """Pre-acquisition runtime-visible state only."""
    basic_t = safe_basic(basic)
    columns = [basic_t, one_hot_class(pred_b), proba_b]
    max_prob = proba_b.max(axis=1)
    sorted_proba = np.sort(proba_b, axis=1)
    margin = sorted_proba[:, -1] - sorted_proba[:, -2]
    ent = entropy_of(proba_b)
    columns.extend([max_prob[:, None], margin[:, None], ent[:, None]])
    columns.append(availability.astype(np.float64)[:, None])
    matrix = np.column_stack(columns)
    names = (list(MODEL_VISIBLE_FIELDS)
             + [f"pred_class_onehot_{name}" for name in CANONICAL_CLASS_ORDER]
             + [f"proba_B_{name}" for name in CANONICAL_CLASS_ORDER]
             + list(DERIVED_BASIC_FEATURES))
    if len(names) != matrix.shape[1]:
        raise SystemExit("GATE_1B_STATUS=SELECTOR_FEATURE_NAME_MISMATCH")
    return matrix, names


def selector_leakage_audit(names: list[str]) -> str:
    lower = " ".join(names).lower()
    violations = [marker for marker in FORBIDDEN_SELECTOR_MARKERS if marker in lower]
    if violations:
        return f"FAIL:{','.join(violations)}"
    history_intersection = set(names) & set(HISTORY_FIELDS)
    if history_intersection:
        return f"FAIL:history_fields={sorted(history_intersection)}"
    return "PASS"


def run_selector(args) -> int:
    artifact_root = Path(args.artifact_root)
    gate1_root = Path(args.gate1_root)
    (artifact_root / "models").mkdir(parents=True, exist_ok=True)
    for seed in (args.seed,) if args.seed else FORMAL_SEEDS:
        started = time.monotonic()
        print(f"[selector seed {seed}] loading OOF labels", flush=True)
        oof_table = pq.read_table(artifact_root / f"gate_v1b_seed_{seed}_oof.parquet")
        rows = oof_table["source_row_index"].to_numpy(zero_copy_only=False)
        labels = np.array(oof_table["canonical_label"].to_pylist(), dtype=object)
        oof_pred = {c: np.array(oof_table[f"pred_{c}"].to_pylist(), dtype=object)
                    for c in CONDITIONS}

        basic_rows, basic_arrays = load_basic_features(gate1_root)
        basic_positions = {int(value): index for index, value in enumerate(basic_rows)}
        basic = basic_matrix_for(rows, basic_arrays, basic_positions)
        proba_b = np.column_stack([
            oof_table[f"proba_B_{name}"].to_numpy() for name in CANONICAL_CLASS_ORDER
        ])
        availability = np.ones(len(rows))
        features, names = build_selector_features(basic, oof_pred["B"], proba_b,
                                                  availability)
        audit = selector_leakage_audit(names)
        print(f"[selector seed {seed}] UTILITY_SELECTOR_LEAKAGE_AUDIT={audit}",
              flush=True)
        if audit != "PASS":
            raise SystemExit(f"GATE_1B_STATUS=SELECTOR_LEAKAGE_AUDIT_FAIL "
                             f"audit={audit}")

        models: dict[str, Any] = {}
        for family in FAMILIES:
            condition = FAMILY_CONDITION[family]
            _, _, signed = utility_labels(oof_pred["B"], oof_pred[condition], labels)
            config = dict(SELECTOR_CONFIG)
            config["random_state"] = seed
            model = RandomForestRegressor(**config)
            model.fit(features, signed)
            models[family] = model
            print(f"[selector seed {seed}] Selector_{family} fitted "
                  f"(labels: {int((signed == 1).sum())} help, "
                  f"{int((signed == -1).sum())} harm)", flush=True)

        model_path = artifact_root / "models" / f"selector_seed_{seed}.pkl"
        with open(model_path, "wb") as handle:
            pickle.dump(models, handle, protocol=5)
        (artifact_root / f"selector_features_seed_{seed}.json").write_text(
            json.dumps({"feature_names": names, "leakage_audit": audit}, indent=2),
            encoding="utf-8")
        print(f"[selector seed {seed}] saved models in "
              f"{time.monotonic() - started:.0f}s", flush=True)
    return 0


# ---------------------------------------------------------------------------
# Evaluation on frozen VALIDATION targets
# ---------------------------------------------------------------------------

def reproduce_frozen_basic_proba(gate1_root: Path, seed: int,
                                 ) -> tuple[np.ndarray, np.ndarray]:
    """Deterministic reproduction of the frozen BASIC estimator (same config,
    data, random_state) to serve as the runtime-visible probability provider.
    Hard predictions are verified to equal frozen pred_B exactly."""
    targets = load_targets(gate1_root, seed)
    train_mask = targets["partition_code"] == PARTITION_TRAIN
    basic_rows, basic_arrays = load_basic_features(gate1_root)
    basic_positions = {int(value): index for index, value in enumerate(basic_rows)}
    basic = basic_matrix_for(targets["source_row_index"], basic_arrays,
                             basic_positions)
    X_b = safe_basic(basic)
    model = fit_estimator(seed)
    model.fit(X_b[train_mask], targets["canonical_label"][train_mask])
    proba = align_proba_to_class_order(
        model.predict_proba(X_b[~train_mask]), model.classes_)
    pred = model.predict(X_b[~train_mask])
    frozen = load_validation_predictions(gate1_root, seed)["pred_B"]
    if not np.array_equal(pred, frozen):
        raise SystemExit(
            "GATE_1B_STATUS=BLOCKED_BASIC_REPRODUCTION_MISMATCH "
            f"seed={seed} (frozen pred_B not exactly reproduced)")
    return proba, pred


def select_topk(scores: np.ndarray, k: int, order: np.ndarray) -> np.ndarray:
    """Deterministic top-k: score descending, tie-break ascending row order."""
    ranked = np.lexsort((order, -scores))
    selected = np.zeros(len(scores), dtype=bool)
    selected[ranked[:k]] = True
    return selected


def random_selection(n: int, k: int, rng_seed: int) -> np.ndarray:
    rng = np.random.default_rng(rng_seed)
    selected = np.zeros(n, dtype=bool)
    selected[rng.choice(n, size=k, replace=False)] = True
    return selected


def random_baseline_stats(
    pred_b: np.ndarray, pred_be: np.ndarray, labels: np.ndarray,
    k: int, reps: int, seed: int,
) -> tuple[np.ndarray, np.ndarray]:
    """Deterministic random acquisition baseline: `reps` seeded draws, returning
    per-rep NET_RECOVERY and Macro-F1 arrays (vectorized)."""
    n = len(labels)
    label_codes = np.array([CANONICAL_CLASS_ORDER.index(name) for name in labels],
                           dtype=np.int64)
    pred_b_codes = np.array([CANONICAL_CLASS_ORDER.index(name) for name in pred_b],
                            dtype=np.int64)
    pred_be_codes = np.array([CANONICAL_CLASS_ORDER.index(name) for name in pred_be],
                             dtype=np.int64)
    help_flag = (pred_b != labels) & (pred_be == labels)
    harm_flag = (pred_b == labels) & (pred_be != labels)
    nets = np.empty(reps, dtype=np.float64)
    macros = np.empty(reps, dtype=np.float64)
    for rep in range(reps):
        rng = np.random.default_rng(RANDOM_RNG_OFFSET + seed * 1000 + rep)
        selected = np.zeros(n, dtype=bool)
        selected[rng.choice(n, size=k, replace=False)] = True
        nets[rep] = float(((selected & help_flag).sum() - (selected & harm_flag).sum())
                          / n)
        final_codes = np.where(selected, pred_be_codes, pred_b_codes)
        confusion = np.bincount(label_codes * 7 + final_codes, minlength=49)
        confusion = confusion.reshape(7, 7).astype(np.float64)
        per_class = np.zeros(7, dtype=np.float64)
        for index in range(7):
            precision = confusion[index, index] / max(confusion[:, index].sum(), 1e-12)
            recall = confusion[index, index] / max(confusion[index, :].sum(), 1e-12)
            per_class[index] = 2 * precision * recall / max(precision + recall, 1e-12)
        macros[rep] = float(per_class.mean())
    return nets, macros


def selective_metrics(
    pred_b: np.ndarray, pred_be: np.ndarray, labels: np.ndarray,
    selected: np.ndarray, total: int,
) -> dict[str, Any]:
    final = np.where(selected, pred_be, pred_b)
    help_flag, harm_flag, _ = utility_labels(pred_b, pred_be, labels)
    selected_help = int((selected & help_flag).sum())
    selected_harm = int((selected & harm_flag).sum())
    selected_n = int(selected.sum())
    help_total = int(help_flag.sum())
    harm_total = int(harm_flag.sum())
    return {
        "macro_f1": float(f1_score(labels, final, average="macro")),
        "micro_f1": float(f1_score(labels, final, average="micro")),
        "balanced_accuracy": float(balanced_accuracy_score(labels, final)),
        "selected_n": selected_n,
        "help_captured": selected_help,
        "help_precision_among_acquired": float(selected_help / selected_n)
        if selected_n else 0.0,
        "help_capture": float(selected_help / help_total) if help_total else 0.0,
        "harm_captured": selected_harm,
        "harm_rate_among_acquired": float(selected_harm / selected_n)
        if selected_n else 0.0,
        "net_recovery": float((selected_help - selected_harm) / max(total, 1)),
    }


def run_evaluate(args) -> int:
    artifact_root = Path(args.artifact_root)
    gate1_root = Path(args.gate1_root)
    for seed in (args.seed,) if args.seed else FORMAL_SEEDS:
        started = time.monotonic()
        print(f"[evaluate seed {seed}] loading frozen validation predictions",
              flush=True)
        val = load_validation_predictions(gate1_root, seed)
        labels = val["canonical_label"]
        pred = {c: val[f"pred_{c}"] for c in CONDITIONS}
        total = len(labels)

        proba_b, reproduced_pred_b = reproduce_frozen_basic_proba(gate1_root, seed)
        if not np.array_equal(reproduced_pred_b, pred["B"]):
            raise SystemExit("GATE_1B_STATUS=BLOCKED_BASIC_REPRODUCTION_MISMATCH "
                             f"seed={seed}")
        basic_rows, basic_arrays = load_basic_features(gate1_root)
        basic_positions = {int(value): index for index, value in enumerate(basic_rows)}
        basic = basic_matrix_for(val["source_row_index"], basic_arrays, basic_positions)
        availability = np.ones(total)
        features, names = build_selector_features(basic, pred["B"], proba_b,
                                                  availability)
        audit = selector_leakage_audit(names)
        if audit != "PASS":
            raise SystemExit(f"GATE_1B_STATUS=SELECTOR_LEAKAGE_AUDIT_FAIL "
                             f"audit={audit}")

        with open(artifact_root / "models" / f"selector_seed_{seed}.pkl", "rb") as handle:
            models = pickle.load(handle)

        diversity = diversity_flags(pred["B"], pred["BT"], pred["BR"], pred["BTR"],
                                    labels)
        result: dict[str, Any] = {
            "schema_version": "CORE_HYPOTHESIS_GATE_V1B_SEED_RESULT_V1",
            "seed": seed,
            "validation_n": total,
            "selector_family": SELECTOR_FAMILY,
            "selector_config": dict(SELECTOR_CONFIG),
            "selector_feature_names": names,
            "selector_leakage_audit": audit,
            "basic_proba_provider": (
                "REPRODUCED_FROZEN_BASIC_ESTIMATOR_DETERMINISTIC_"
                "VERIFIED_EXACT_PRED_MATCH"),
            "budgets": list(BUDGETS),
            "primary_budget": PRIMARY_BUDGET,
            "diversity": {},
            "families": {},
        }

        diversity_keys = (
            ("UNIQUE_T_HELP", diversity[0]), ("UNIQUE_R_HELP", diversity[1]),
            ("SHARED_TR_HELP", diversity[2]), ("FULL_ONLY_HELP", diversity[3]),
        )
        for report_key, flag in diversity_keys:
            result["diversity"][report_key] = {
                "count": int(flag.sum()),
                "rate": float(flag.sum() / total),
                "per_class": per_class_counts(flag, labels, total),
            }

        for family in FAMILIES:
            condition = FAMILY_CONDITION[family]
            help_flag, harm_flag, signed = utility_labels(
                pred["B"], pred[condition], labels)
            score = models[family].predict(features)
            help_prevalence = float(help_flag.mean())
            harm_prevalence = float(harm_flag.mean())
            auroc = float(roc_auc_score(help_flag.astype(np.int64), score))
            aupr = float(average_precision_score(help_flag.astype(np.int64), score))
            k15 = int(round(PRIMARY_BUDGET * total))

            budgets: dict[str, Any] = {}
            for q in BUDGETS:
                k = int(round(q * total))
                row_order = val["source_row_index"]
                sel_sel = select_topk(score, k, row_order)
                sel_conf = select_topk(-proba_b.max(axis=1), k, row_order)
                sel_ent = select_topk(entropy_of(proba_b), k, row_order)
                sel_oracle = select_topk(signed.astype(np.float64), k, row_order)
                random_nets, random_macros = random_baseline_stats(
                    pred["B"], pred[condition], labels, k, RANDOM_REPS, seed)
                budgets[str(q)] = {
                    "k": k,
                    "selector": selective_metrics(pred["B"], pred[condition],
                                                  labels, sel_sel, total),
                    "confidence": selective_metrics(pred["B"], pred[condition],
                                                    labels, sel_conf, total),
                    "entropy": selective_metrics(pred["B"], pred[condition],
                                                 labels, sel_ent, total),
                    "oracle": selective_metrics(pred["B"], pred[condition],
                                                labels, sel_oracle, total),
                    "random_mean": {
                        "net_recovery": float(random_nets.mean()),
                        "net_recovery_ci95": [
                            float(np.percentile(random_nets, 2.5)),
                            float(np.percentile(random_nets, 97.5))],
                        "macro_f1": float(random_macros.mean()),
                        "macro_f1_ci95": [
                            float(np.percentile(random_macros, 2.5)),
                            float(np.percentile(random_macros, 97.5))],
                    },
                }

            s15 = budgets["0.15"]["selector"]
            r15 = budgets["0.15"]["random_mean"]
            families_result = {
                "condition": condition,
                "help_prevalence": help_prevalence,
                "harm_prevalence": harm_prevalence,
                "global_net_utility_prevalence": float(help_flag.mean() - harm_flag.mean()),
                "help_auroc": auroc,
                "help_aupr": aupr,
                "budgets": budgets,
                "top15": {
                    "help_capture": s15["help_capture"],
                    "help_precision_among_acquired": s15["help_precision_among_acquired"],
                    "harm_captured": s15["harm_captured"],
                    "net_recovery": s15["net_recovery"],
                },
                "net_recovery_gain_vs_random_15": float(
                    s15["net_recovery"] - r15["net_recovery"]),
                "selector15_macro_f1": s15["macro_f1"],
                "basic_macro_f1": float(
                    f1_score(labels, pred["B"], average="macro")),
                "delta_selective15_macro_f1": float(
                    s15["macro_f1"] - f1_score(labels, pred["B"], average="macro")),
                "help_prevalence_ratio_aupr": float(
                    aupr / help_prevalence) if help_prevalence else None,
            }
            result["families"][family] = families_result
            print(f"[evaluate seed {seed}] {family}: HELP prev={help_prevalence:.5f} "
                  f"AUROC={auroc:.4f} AUPR={aupr:.4f} "
                  f"top15_capture={s15['help_capture']:.4f} "
                  f"sel15_net={s15['net_recovery']:+.5f} "
                  f"rand15_net={r15['net_recovery']:+.5f} "
                  f"gain={families_result['net_recovery_gain_vs_random_15']:+.5f} "
                  f"macro={s15['macro_f1']:.5f} "
                  f"basic={families_result['basic_macro_f1']:.5f}",
                  flush=True)

        score_table = pa.table({
            "source_row_index": pa.array(val["source_row_index"], pa.int64()),
            "canonical_label": pa.array(labels, pa.string()),
            "activity_group_digest": pa.array(val["activity_group_digest"], pa.binary(16)),
            "temporal_block": pa.array(val["temporal_block"], pa.int16()),
        })
        for family in FAMILIES:
            condition = FAMILY_CONDITION[family]
            help_flag, harm_flag, signed = utility_labels(
                pred["B"], pred[condition], labels)
            score = models[family].predict(features)
            k15 = int(round(PRIMARY_BUDGET * total))
            row_order = val["source_row_index"]
            sel_sel = select_topk(score, k15, row_order)
            rng = np.random.default_rng(T7_RNG_OFFSET + seed)
            rand15 = np.zeros(total, dtype=bool)
            rand15[rng.choice(total, size=k15, replace=False)] = True
            score_table = score_table.append_column(
                f"help_{family}", pa.array(help_flag, pa.bool_())
            ).append_column(f"harm_{family}", pa.array(harm_flag, pa.bool_())
            ).append_column(f"signed_{family}", pa.array(signed, pa.int8())
            ).append_column(f"score_{family}", pa.array(score, pa.float64())
            ).append_column(f"selector15_{family}", pa.array(sel_sel, pa.bool_())
            ).append_column(f"random15_{family}", pa.array(rand15, pa.bool_()))
        out = artifact_root / f"gate_v1b_seed_{seed}_validation_scores.parquet"
        pq.write_table(score_table, out, compression="zstd")

        out_json = artifact_root / f"gate_v1b_seed_{seed}_evaluation.json"
        out_json.write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(f"[evaluate seed {seed}] wrote {out_json.name} in "
              f"{time.monotonic() - started:.0f}s", flush=True)
    return 0


# ---------------------------------------------------------------------------
# Paired group bootstrap (T7 + Gate 1 aggregate CI)
# ---------------------------------------------------------------------------

def paired_selector_vs_random_bootstrap(
    groups: np.ndarray, help_flag: np.ndarray, harm_flag: np.ndarray,
    selector_selected: np.ndarray, random_selected: np.ndarray,
    total: int, n_reps: int, rng_seed: int,
) -> dict[str, float]:
    """Paired private-activity-group bootstrap of the Selector15 vs Random15
    NET_RECOVERY difference (same group multiset for both arms)."""
    _, group_index = np.unique(groups, return_inverse=True)
    n_groups = len(np.unique(groups))
    n_sel_help = np.bincount(group_index, weights=selector_selected & help_flag,
                             minlength=n_groups)
    n_sel_harm = np.bincount(group_index, weights=selector_selected & harm_flag,
                             minlength=n_groups)
    n_rand_help = np.bincount(group_index, weights=random_selected & help_flag,
                              minlength=n_groups)
    n_rand_harm = np.bincount(group_index, weights=random_selected & harm_flag,
                              minlength=n_groups)
    rng = np.random.default_rng(rng_seed)
    draws = rng.integers(0, n_groups, size=(n_reps, n_groups))
    counts = np.apply_along_axis(np.bincount, 1, draws, minlength=n_groups)
    diffs = np.empty(n_reps, dtype=np.float64)
    for rep in range(n_reps):
        weight = counts[rep].astype(np.float64)
        sel_net = (np.dot(weight, n_sel_help) - np.dot(weight, n_sel_harm)) / total
        rand_net = (np.dot(weight, n_rand_help) - np.dot(weight, n_rand_harm)) / total
        diffs[rep] = sel_net - rand_net
    return {
        "mean": float(diffs.mean()),
        "ci95": [float(np.percentile(diffs, 2.5)), float(np.percentile(diffs, 97.5))],
        "reps": n_reps,
        "unit": "private activity group",
        "paired": True,
    }


def aggregate_gate1_bootstrap(pred_tables: list[dict[str, np.ndarray]],
                              n_reps: int, rng_seed: int) -> dict[str, Any]:
    """Optional Gate 1 statistical completeness: aggregate paired group
    bootstrap of delta Macro-F1 (B+E vs B) pooled across all 3 formal seeds,
    from frozen predictions only. Cannot change Gate 1 = YELLOW."""
    from run_core_hypothesis_gate_v1 import _macro_f1_from_confusion

    labels = np.concatenate([t["canonical_label"] for t in pred_tables])
    groups = np.concatenate([t["activity_group_digest"] for t in pred_tables])
    preds = {c: np.concatenate([t[f"pred_{c}"] for t in pred_tables])
             for c in CONDITIONS}
    _, group_index = np.unique(groups, return_inverse=True)
    n_groups = len(np.unique(groups))
    class_index = {name: index for index, name in enumerate(CANONICAL_CLASS_ORDER)}
    label_codes = np.array([class_index[name] for name in labels], dtype=np.int64)
    pred_codes = {c: np.array([class_index[name] for name in preds[c]],
                              dtype=np.int64) for c in CONDITIONS}

    confusion_by_group = np.zeros((len(CONDITIONS), n_groups, 7, 7), dtype=np.int64)
    for condition_index, condition in enumerate(CONDITIONS):
        np.add.at(confusion_by_group[condition_index],
                  (group_index, label_codes, pred_codes[condition]), 1)
    rng = np.random.default_rng(rng_seed)
    draws = rng.integers(0, n_groups, size=(n_reps, n_groups))
    counts = np.apply_along_axis(np.bincount, 1, draws, minlength=n_groups)
    families: dict[str, Any] = {}
    for condition, family in EVIDENCE_DELTAS.items():
        deltas = np.empty(n_reps, dtype=np.float64)
        for rep in range(n_reps):
            weight = counts[rep].astype(np.int64)
            confusion_b = np.einsum("g,gij->ij", weight, confusion_by_group[0])
            confusion_c = np.einsum("g,gij->ij", weight, confusion_by_group[
                CONDITIONS.index(condition)])
            deltas[rep] = (_macro_f1_from_confusion(confusion_c)
                           - _macro_f1_from_confusion(confusion_b))
        families[family] = {
            "delta_macro_f1_mean": float(deltas.mean()),
            "delta_macro_f1_ci95": [float(np.percentile(deltas, 2.5)),
                                    float(np.percentile(deltas, 97.5))],
        }
    return {"families": families, "reps": n_reps, "unit": "private activity group",
            "pooled_seeds": [int(s) for s in FORMAL_SEEDS], "paired": True}


def run_bootstrap(args) -> int:
    artifact_root = Path(args.artifact_root)
    gate1_root = Path(args.gate1_root)
    seeds = (args.seed,) if args.seed else FORMAL_SEEDS
    for seed in seeds:
        val = load_validation_predictions(gate1_root, seed)
        groups = val["activity_group_digest"]
        total = len(val["canonical_label"])
        score_table = pq.read_table(
            artifact_root / f"gate_v1b_seed_{seed}_validation_scores.parquet")
        bootstrap: dict[str, Any] = {}
        for family in FAMILIES:
            help_flag = score_table[f"help_{family}"].to_numpy()
            harm_flag = score_table[f"harm_{family}"].to_numpy()
            sel = score_table[f"selector15_{family}"].to_numpy()
            rnd = score_table[f"random15_{family}"].to_numpy()
            bootstrap[family] = paired_selector_vs_random_bootstrap(
                groups, help_flag, harm_flag, sel, rnd, total,
                BOOTSTRAP_REPS, T7_RNG_OFFSET + seed * 10 + family_index(family))
            print(f"[bootstrap seed {seed}] {family}: "
                  f"sel-vs-rand15 CI95 {bootstrap[family]['ci95']}", flush=True)
        (artifact_root / f"gate_v1b_seed_{seed}_bootstrap.json").write_text(
            json.dumps({"schema_version": "CORE_HYPOTHESIS_GATE_V1B_BOOTSTRAP_V1",
                        "seed": seed, **bootstrap}, indent=2), encoding="utf-8")
    return 0


def family_index(family: str) -> int:
    return {"T": 0, "R": 1, "TR": 2}[family]


# ---------------------------------------------------------------------------
# Decision
# ---------------------------------------------------------------------------

def mean(values: list[float]) -> float:
    return float(np.mean(values))


def build_temporal_decision(per_seed: dict[int, dict[str, Any]],
                            aggregate_bootstrap: dict[str, Any]) -> dict[str, Any]:
    """Frozen T1-T7 gate on the TEMPORAL primary family."""
    t = [per_seed[seed]["evaluation"]["families"]["T"] for seed in FORMAL_SEEDS]
    auroc_seeds = [info["help_auroc"] for info in t]
    aupr_seeds = [info["help_aupr"] for info in t]
    prev_seeds = [info["help_prevalence"] for info in t]
    capture_seeds = [info["top15"]["help_capture"] for info in t]
    sel15_seeds = [info["budgets"]["0.15"]["selector"]["net_recovery"] for info in t]
    rand15_seeds = [info["budgets"]["0.15"]["random_mean"]["net_recovery"] for info in t]
    gain_seeds = [info["net_recovery_gain_vs_random_15"] for info in t]
    sel15_macro = [info["budgets"]["0.15"]["selector"]["macro_f1"] for info in t]
    basic_macro = [info["basic_macro_f1"] for info in t]
    delta_macro = [info["delta_selective15_macro_f1"] for info in t]

    t1 = mean(auroc_seeds) >= T1_AUROC
    t2 = mean(aupr_seeds) >= T2_AUPR_PREVALENCE_MULTIPLE * mean(prev_seeds)
    t3 = all(capture >= T3_TOP15_CAPTURE for capture in capture_seeds)
    t4 = all(sel > rand for sel, rand in zip(sel15_seeds, rand15_seeds, strict=True))
    t5 = mean(gain_seeds) >= T5_MIN_GAIN
    t6 = all(sm > bm for sm, bm in zip(sel15_macro, basic_macro, strict=True)) \
        and mean(delta_macro) >= T6_MIN_DELTA_MACRO
    t7 = aggregate_bootstrap["T"]["ci95"][0] > 0

    passed = [t1, t2, t3, t4, t5, t6, t7]
    n_pass = sum(passed)
    severe = (mean(auroc_seeds) < SEVERE_AUROC
              and mean(capture_seeds) < SEVERE_TOP15_CAPTURE
              and mean(gain_seeds) < SEVERE_GAIN)
    if all(passed):
        status = "PASS"
    elif (n_pass >= YELLOW_MIN_PASS and t4
          and mean(gain_seeds) > 0 and mean(auroc_seeds) >= YELLOW_MIN_AUROC
          and not severe):
        status = "YELLOW"
    else:
        status = "FAIL_SEVERE" if severe else "FAIL"
    return {
        "status": status,
        "severe_failure": bool(severe),
        "n_pass": n_pass,
        "criteria": {
            "T1_mean_help_auroc": {"value": mean(auroc_seeds),
                                   "threshold": T1_AUROC, "pass": t1},
            "T2_mean_help_aupr": {"value": mean(aupr_seeds),
                                  "threshold": 2.0 * mean(prev_seeds), "pass": t2},
            "T3_top15_help_capture_3of3": {"values": capture_seeds,
                                           "threshold": T3_TOP15_CAPTURE, "pass": t3},
            "T4_sel15_gt_rand15_3of3": {
                "selector_values": sel15_seeds, "random_values": rand15_seeds,
                "pass": t4},
            "T5_mean_gain_vs_random": {"value": mean(gain_seeds),
                                       "threshold": T5_MIN_GAIN, "pass": t5},
            "T6_sel15_macro_gt_basic_3of3": {
                "selector_macro": sel15_macro, "basic_macro": basic_macro,
                "mean_delta": mean(delta_macro), "threshold": T6_MIN_DELTA_MACRO,
                "pass": t6},
            "T7_aggregate_ci_lower": {"value": aggregate_bootstrap["T"][
                "ci95"][0], "pass": t7},
        },
    }


def build_relation_decision(per_seed: dict[int, dict[str, Any]],
                            aggregate_bootstrap: dict[str, Any]) -> dict[str, Any]:
    r = [per_seed[seed]["evaluation"]["families"]["R"] for seed in FORMAL_SEEDS]
    unique_r_rates = [per_seed[seed]["evaluation"]["diversity"]["UNIQUE_R_HELP"]["rate"]
                      for seed in FORMAL_SEEDS]
    diversity_pass = (mean(unique_r_rates) >= RELATION_DIVERSITY_MEAN_RATE
                      and sum(rate >= RELATION_DIVERSITY_SEED_RATE
                              for rate in unique_r_rates) >= 2)
    r1 = mean([info["help_auroc"] for info in r]) >= R1_AUROC
    r2 = mean([info["top15"]["help_capture"] for info in r]) >= R2_TOP15_CAPTURE
    r3 = sum(info["budgets"]["0.15"]["selector"]["net_recovery"] > 0
             for info in r) >= 2
    r4 = sum(info["budgets"]["0.15"]["selector"]["net_recovery"]
             > info["budgets"]["0.15"]["random_mean"]["net_recovery"]
             for info in r) >= 2
    r5 = aggregate_bootstrap["R"]["mean"] > 0
    return {
        "diversity_signal": bool(diversity_pass),
        "unique_r_help_rate_by_seed": unique_r_rates,
        "criteria": {
            "R1_mean_help_auroc": {"value": mean([info["help_auroc"] for info in r]),
                                   "threshold": R1_AUROC, "pass": r1},
            "R2_mean_top15_capture": {"value": mean([info["top15"]["help_capture"]
                                                     for info in r]),
                                      "threshold": R2_TOP15_CAPTURE, "pass": r2},
            "R3_sel15_net_gt_0_2of3": {"pass": r3},
            "R4_sel15_gt_rand15_2of3": {"pass": r4},
            "R5_central_estimate_gt_0": {"pass": r5},
        },
        "conditional_value": bool(diversity_pass and r1 and r2 and r3 and r4 and r5),
    }


def build_tr_decision(per_seed: dict[int, dict[str, Any]]) -> dict[str, Any]:
    tr = [per_seed[seed]["evaluation"]["families"]["TR"] for seed in FORMAL_SEEDS]
    gain = mean([info["net_recovery_gain_vs_random_15"] for info in tr])
    return {
        "mean_help_auroc": mean([info["help_auroc"] for info in tr]),
        "mean_top15_capture": mean([info["top15"]["help_capture"] for info in tr]),
        "mean_gain_vs_random_15": gain,
        "secondary_only": True,
    }


def run_report(args) -> int:
    artifact_root = Path(args.artifact_root)
    gate1_root = Path(args.gate1_root)
    per_seed: dict[int, dict[str, Any]] = {}
    for seed in FORMAL_SEEDS:
        evaluation = json.loads(
            (artifact_root / f"gate_v1b_seed_{seed}_evaluation.json").read_text())
        bootstrap = json.loads(
            (artifact_root / f"gate_v1b_seed_{seed}_bootstrap.json").read_text())
        per_seed[int(seed)] = {"evaluation": evaluation, "bootstrap": bootstrap}

    # paired Selector-vs-Random15 aggregate bootstrap (pooled across seeds)
    pred_tables = [load_validation_predictions(gate1_root, seed)
                   for seed in FORMAL_SEEDS]
    score_tables = [pq.read_table(
        artifact_root / f"gate_v1b_seed_{seed}_validation_scores.parquet")
        for seed in FORMAL_SEEDS]
    groups = np.concatenate([t["activity_group_digest"] for t in pred_tables])
    total_pooled = int(np.sum([len(t["canonical_label"]) for t in pred_tables]))
    aggregate_selector_random: dict[str, Any] = {}
    for family in FAMILIES:
        help_flag = np.concatenate([t[f"help_{family}"].to_numpy()
                                    for t in score_tables])
        harm_flag = np.concatenate([t[f"harm_{family}"].to_numpy()
                                    for t in score_tables])
        sel = np.concatenate([t[f"selector15_{family}"].to_numpy()
                              for t in score_tables])
        rnd = np.concatenate([t[f"random15_{family}"].to_numpy()
                              for t in score_tables])
        aggregate_selector_random[family] = paired_selector_vs_random_bootstrap(
            groups, help_flag, harm_flag, sel, rnd, total_pooled,
            BOOTSTRAP_REPS, T7_RNG_OFFSET + 999)

    # optional Gate 1 aggregate paired group bootstrap (frozen predictions only)
    gate1_aggregate = aggregate_gate1_bootstrap(pred_tables, BOOTSTRAP_REPS,
                                                7_000)

    temporal = build_temporal_decision(per_seed, aggregate_selector_random)
    relation = build_relation_decision(per_seed, aggregate_selector_random)
    tr_info = build_tr_decision(per_seed)

    if temporal["status"] == "PASS":
        gate1b = "PASS"
        adaptive = "SUPPORTED_FOR_NEXT_OPEN_WORLD_GATE"
    elif temporal["status"] == "YELLOW":
        gate1b = "YELLOW"
        adaptive = "NOT_YET_AUTHORIZED_FOR_MODEL_B"
    else:
        gate1b = "FAIL"
        adaptive = "STOP_BEFORE_MODEL_B_RL_CONTINUAL"

    report = {
        "schema_version": "CORE_HYPOTHESIS_GATE_V1B_REPORT_V1",
        "status": f"COMPLETE_{gate1b}",
        "date": args.date,
        "repository": "flow-security-agent",
        "branch": args.branch,
        "head": args.head,
        "gate1_status": "YELLOW",
        "gate1_status_changed": False,
        "gate1b_prospective_followup": True,
        "gate1_thresholds_unchanged": True,
        "rescue_experiments": False,
        "formal_seeds": list(FORMAL_SEEDS),
        "oof_folds": OOF_FOLDS,
        "utility_oof_coverage": "100%",
        "validation_per_seed": VAL_PER_SEED,
        "selector_family": SELECTOR_FAMILY,
        "selector_config": dict(SELECTOR_CONFIG),
        "selector_provenance": SELECTOR_PROVENANCE,
        "selector_feature_names": per_seed[FORMAL_SEEDS[0]]["evaluation"][
            "selector_feature_names"],
        "selector_leakage_audit": per_seed[FORMAL_SEEDS[0]]["evaluation"][
            "selector_leakage_audit"],
        "basic_proba_provider": per_seed[FORMAL_SEEDS[0]]["evaluation"][
            "basic_proba_provider"],
        "budgets": list(BUDGETS),
        "primary_budget": PRIMARY_BUDGET,
        "random_reps": RANDOM_REPS,
        "bootstrap_reps": BOOTSTRAP_REPS,
        "per_seed": {str(seed): per_seed[seed]["evaluation"] for seed in FORMAL_SEEDS},
        "selector_vs_random15_aggregate_bootstrap": aggregate_selector_random,
        "gate1_aggregate_bootstrap": gate1_aggregate,
        "gate1_aggregate_bootstrap_completeness": "COMPUTED_OPTIONAL_CHECK",
        "temporal_decision": temporal,
        "relation_decision": relation,
        "tr_secondary": tr_info,
        "evidence_diversity_status": (
            "TEMPORAL_PLUS_RELATION_CONDITIONALLY_USEFUL"
            if relation["conditional_value"]
            else "TEMPORAL_ONLY_CORE_RELATION_NEGATIVE_ABLATION"),
        "decision": gate1b,
        "adaptive_evidence_acquisition_status": adaptive,
        "teacher_utility_alignment_status": "NOT_RUN_OUT_OF_SCOPE",
        "final_test_modeling_contamination": False,
        "deepseek_api_calls": 0,
        "qwen_api_calls": 0,
        "model_b_training_started": False,
        "rl_training_started": False,
        "continual_training_started": False,
    }
    out = artifact_root / "core_hypothesis_gate_v1b.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"[report] CORE_HYPOTHESIS_GATE_1B={gate1b} "
          f"TEMPORAL={temporal['status']} "
          f"RELATION={relation['conditional_value']}")
    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", required=True,
                        choices=["oof", "selector", "evaluate", "bootstrap",
                                 "report"])
    parser.add_argument("--artifact-root", default=DEFAULT_GATE1B_ROOT)
    parser.add_argument("--gate1-root", default=DEFAULT_ARTIFACT_ROOT)
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--branch", default="main")
    parser.add_argument("--head", default="")
    parser.add_argument("--date", default="2026-08-17")
    args = parser.parse_args()
    if args.mode == "oof":
        return run_oof(args)
    if args.mode == "selector":
        return run_selector(args)
    if args.mode == "evaluate":
        return run_evaluate(args)
    if args.mode == "bootstrap":
        return run_bootstrap(args)
    return run_report(args)


if __name__ == "__main__":
    raise SystemExit(main())
