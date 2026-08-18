#!/usr/bin/env python3
"""RECOVERY_SIGNAL_CHARACTERIZATION_AND_OPEN_WORLD_TRANSFER_GATE_V2.

Preregistered, mechanism-driven V2 gate (protocol:
docs/research_plan/recovery_signal_characterization_v2_protocol.md).

Central questions:
  Q1 SIGNAL EXISTENCE  — does the Evidence-induced pre/post recovery
                         trajectory contain predictive information
                         beyond post-acquisition state alone?
  Q2 EXPLOITABILITY    — extractable by a matched linear AND a matched
                         nonlinear probe (capacity ladder)?
  Q3 OPEN-WORLD TRANSFER — fewer false-Unknown decisions among
                         Recoverable Known without damaging True
                         Unknown discrimination?
  Q4 HEADROOM          — if end-to-end gain is insufficient, is the
                         bottleneck consistent with remaining
                         router/interface headroom?

Methods (frozen):
  B0_BASIC_MSP            Basic observation + Basic MSP
  B1_UTILITY_POST_MSP     frozen P6 + post-Evidence MSP
  L_POST / L_TRAJ         frozen P6 + linear POST_ONLY / TRAJECTORY probe
  N_POST / N_TRAJ         frozen P6 + nonlinear (RF) POST_ONLY / TRAJECTORY

Everything not explicitly frozen here comes from the frozen V1 artifacts
(open_world_recoverability_gate_v1): the B/BT/BR/BTR classifiers, the
P6 UTILITY_TYPED actions, VAL_CALIB/VAL_GATE_EVAL split, Recoverable
definition, calibration semantics (5% Known FUR quantile), and the
group-atomic paired bootstrap convention.

Modes:
  smoke — synthetic tiny cells, pipeline integrity only, prints no real
          evaluation metrics.
  run   — executes the frozen gate on the frozen artifacts (Phase C).

Safety:
  - outer True Unknown never enters probe fit / scaler fit / threshold
    calibration / feature design / model selection;
  - FINAL_TEST never enters;
  - no retraining of classifiers or the router;
  - no detector shopping: exactly the two preregistered model families.
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
import pyarrow.parquet as pq
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    average_precision_score,
    balanced_accuracy_score,
    brier_score_loss,
    f1_score,
    log_loss,
    roc_auc_score,
)
from sklearn.preprocessing import StandardScaler

import run_open_world_recoverability_gate_v1 as owg  # noqa: E402
import run_core_hypothesis_gate_v1 as g  # noqa: E402
import run_core_hypothesis_gate_v1b as g1b  # noqa: E402

# ---------------------------------------------------------------------------
# Frozen constants (mirrors of the V1 gate; nothing new is invented here)
# ---------------------------------------------------------------------------

SEEDS = owg.FORMAL_SEEDS
ROTATIONS = owg.ROTATIONS
CALIB_KNOWN_FALSE_UNKNOWN_RATE = owg.CALIB_KNOWN_FALSE_UNKNOWN_RATE  # 0.05
BOOTSTRAP_REPS = owg.BOOTSTRAP_REPS  # 1000
BOOTSTRAP_RNG_OFFSET = owg.BOOTSTRAP_RNG_OFFSET  # 161000
PRIMARY_COST_BUDGET_FRACTION = owg.PRIMARY_COST_BUDGET_FRACTION  # 0.15
ACTION_MODEL = owg.ACTION_MODEL  # NONE->B, T->BT, R->BR, TR->BTR
ACTION_COSTS = owg.ACTION_COSTS  # NONE=0, T=1, R=1, TR=2
FAMILIES = g1b.FAMILIES  # ("T", "R", "TR")
CONDITIONS = g.CONDITIONS  # ("B", "BT", "BR", "BTR")

METHODS = ("B0_BASIC_MSP", "B1_UTILITY_POST_MSP", "L_POST", "L_TRAJ",
           "N_POST", "N_TRAJ")
PROBES = ("L_POST", "L_TRAJ", "N_POST", "N_TRAJ")
ACQUIRING_METHODS = ("B1_UTILITY_POST_MSP", "L_POST", "L_TRAJ", "N_POST",
                     "N_TRAJ")

# V2_PROBE_FIT share of VAL_CALIB Known (frozen approximate 60/40).
SPLIT_FIT_RATIO = 0.60

# Signal status thresholds (Section 17 of the task / Section 14 of protocol).
SIGNAL_MIN_DELTA_AUROC = 0.01
SIGNAL_MIN_ROTATIONS_POSITIVE = 2

# Transfer criteria (Section 18 of the protocol).
T1_FURK_DIFF_MAX = -0.03
T1_MIN_ROTATIONS = 2
T1_MAX_ROTATION_WORSE = 0.02
T2_RCJ_REDUCTION_MIN = 0.08
T2_MIN_ROTATIONS = 2
T3_AUROC_LOSS_MAX = 0.01
T3_MAX_ROTATION_LOSS = 0.03
T4_RECALL_LOSS_MAX = 0.03
T4_MAX_ROTATION_LOSS = 0.05

# End-to-end criteria (Section 19 of the protocol).
E1_FURK_GAIN_MIN = 0.02
E1_MIN_ROTATIONS = 2
E1_MAX_ROTATION_WORSE = 0.02
E3_AUROC_LOSS_MAX = 0.01
E3_MAX_ROTATION_LOSS = 0.03
E4_RECALL_LOSS_MAX = 0.03
E4_MAX_ROTATION_LOSS = 0.05

# Headroom "large" thresholds for CASE E interpretation (>=2 rotations).
HEADROOM_LARGE_ROUTER = 0.30
HEADROOM_LARGE_INTERFACE = 0.30
HEADROOM_MIN_ROTATIONS = 2

# Frozen capacity-ladder configurations.
LINEAR_CONFIG = {
    "penalty": "l2", "C": 1.0, "solver": "lbfgs", "max_iter": 2000,
    "class_weight": "balanced",
}
RF_CONFIG = {
    "n_estimators": 300, "max_depth": 10, "min_samples_leaf": 20,
    "max_features": "sqrt", "class_weight": "balanced_subsample",
    "n_jobs": -1,
}

POST_ONLY_FEATURES = (
    "conf_post", "margin_post", "entropy_post",
    "ONEHOT_NONE", "ONEHOT_T", "ONEHOT_R", "ONEHOT_TR",
)
TRAJECTORY_FEATURES = POST_ONLY_FEATURES + (
    "conf_pre", "margin_pre", "entropy_pre",
    "delta_conf", "delta_margin", "delta_entropy",
    "top1_changed", "pre_prob_of_post_top1", "post_prob_of_pre_top1",
    "post_top1_support_gain", "pre_top1_support_change",
    "top1_transition_gap",
)

OUT_SCHEMA = "RECOVERY_SIGNAL_CHARACTERIZATION_GATE_V2_REPORT_V1"
BOOTSTRAP_SCHEMA = "RECOVERY_SIGNAL_CHARACTERIZATION_V2_BOOTSTRAP_V1"
SPLIT_MANIFEST_SCHEMA = "RECOVERY_SIGNAL_CHARACTERIZATION_V2_SPLIT_MANIFEST_V1"


def entropy_norm(p: np.ndarray) -> np.ndarray:
    """H(p)/log(K) with 0*log(0)=0. p: (n, K) row-stochastic."""
    p = np.asarray(p, dtype=np.float64)
    eps = np.finfo(np.float64).tiny
    safe = np.clip(p, eps, 1.0)
    ent = -(p * np.log(safe)).sum(axis=1)
    return ent / np.log(p.shape[1])


def onehot_action(action: str) -> np.ndarray:
    return np.array([action == "NONE", action == "T", action == "R",
                     action == "TR"], dtype=np.float64)


def conf_margin(pre: np.ndarray, post: np.ndarray
                ) -> tuple[np.ndarray, np.ndarray]:
    """(conf, margin) per row for pre and post vectors."""
    p = np.sort(pre, axis=1)[:, ::-1]
    q = np.sort(post, axis=1)[:, ::-1]
    conf_pre, conf_post = p[:, 0], q[:, 0]
    margin_pre = p[:, 0] - p[:, 1]
    margin_post = q[:, 0] - q[:, 1]
    return (conf_pre, conf_post, margin_pre, margin_post)


def post_only_matrix(post: np.ndarray, actions: np.ndarray) -> np.ndarray:
    """POST_ONLY feature matrix (n, 7), column order POST_ONLY_FEATURES."""
    conf, _, margin, _ = conf_margin(post, post)
    out = np.column_stack([
        conf, margin, entropy_norm(post),
        (actions == "NONE").astype(np.float64),
        (actions == "T").astype(np.float64),
        (actions == "R").astype(np.float64),
        (actions == "TR").astype(np.float64),
    ])
    return out


def trajectory_matrix(pre: np.ndarray, post: np.ndarray,
                      actions: np.ndarray) -> np.ndarray:
    """RECOVERY_TRAJECTORY feature matrix (n, 19), order TRAJECTORY_FEATURES."""
    n = len(actions)
    conf_pre, conf_post, margin_pre, margin_post = conf_margin(pre, post)
    ent_pre = entropy_norm(pre)
    ent_post = entropy_norm(post)
    i_pre = np.argmax(pre, axis=1)
    i_post = np.argmax(post, axis=1)
    rows = np.arange(n)
    pre_prob_of_post_top1 = pre[rows, i_post]
    post_prob_of_pre_top1 = post[rows, i_pre]
    post_top1_support_gain = post[rows, i_post] - pre[rows, i_post]
    pre_top1_support_change = post[rows, i_pre] - pre[rows, i_pre]
    top1_transition_gap = post[rows, i_post] - post[rows, i_pre]
    base = post_only_matrix(post, actions)
    extra = np.column_stack([
        conf_pre, margin_pre, ent_pre,
        conf_post - conf_pre,
        margin_post - margin_pre,
        ent_post - ent_pre,
        (i_pre != i_post).astype(np.float64),
        pre_prob_of_post_top1,
        post_prob_of_pre_top1,
        post_top1_support_gain,
        pre_top1_support_change,
        top1_transition_gap,
    ])
    return np.column_stack([base, extra])


def accept_target(pred_post: np.ndarray, labels: np.ndarray) -> np.ndarray:
    """ACCEPT_TARGET = 1 iff post-Evidence predicted Known class equals the
    true Known label (frozen P6 preds)."""
    return (pred_post == labels).astype(np.int64)


# ---------------------------------------------------------------------------
# V2_PROBE_FIT / V2_PROBE_CALIB split (frozen; deterministic, no RNG)
# ---------------------------------------------------------------------------

def build_probe_split(seed: int, rotation: str, group_digests: np.ndarray,
                      labels: np.ndarray, blocks: np.ndarray
                      ) -> np.ndarray:
    """Assign each row's group to FIT(0) / CALIB(1).

    Population = the caller-supplied rows (VAL_CALIB Known). Groups are
    atomic; stratum = (label, block) of the group's FIRST row in the
    supplied (frozen table) order; within a stratum groups are ordered by
    SHA256(seed_hex || rotation_utf8 || group_digest_bytes) ascending and
    each group is placed in the bin with the smaller cumulative row count
    (ties -> FIT). Deterministic; no RNG; duplicate-safe (group-level).
    """
    groups = np.asarray([bytes(v) for v in group_digests], dtype=object)
    unique, inverse = np.unique(groups, return_inverse=True)
    n_groups = len(unique)
    # primary row of each group (first occurrence in frozen table order)
    _, first_idx = np.unique(inverse, return_index=True)
    primary_gidx = inverse[first_idx]
    primary_class = np.asarray(labels[first_idx], dtype=object)
    primary_block = blocks[first_idx]
    group_counts = np.bincount(inverse, minlength=n_groups)

    role = np.full(n_groups, -1, dtype=np.int8)
    # iterate over unique (class, block) strata
    for cls in sorted(set(str(x) for x in primary_class)):
        for blk in sorted(set(int(x) for x in primary_block)):
            sel = np.flatnonzero(
                (np.array([str(x) for x in primary_class]) == cls)
                & (primary_block == blk))
            if len(sel) == 0:
                continue
            seed_hex = f"{int(seed):08x}".encode("utf-8")
            rot = str(rotation).encode("utf-8")
            order = sorted(
                sel,
                key=lambda gi: hashlib.sha256(
                    seed_hex + rot + bytes(unique[gi])).digest())
            c_fit, c_cal = 0, 0
            for gi in order:
                if c_fit <= c_cal:
                    role[gi] = 0
                    c_fit += int(group_counts[gi])
                else:
                    role[gi] = 1
                    c_cal += int(group_counts[gi])
    if (role == -1).any():
        raise RuntimeError("probe split left groups unassigned")
    return role[inverse]


# ---------------------------------------------------------------------------
# Weighted (group-bootstrap) rank statistics
# ---------------------------------------------------------------------------

def weighted_rank(values: np.ndarray, w: np.ndarray) -> np.ndarray:
    """Average ranks (1..sum(w)) in the weighted multiplicity sequence.
    Ties share the average weighted rank, matching sklearn's AUROC
    convention. Vectorized; deterministic."""
    values = np.asarray(values, dtype=np.float64)
    w = np.asarray(w, dtype=np.float64)
    order = np.argsort(values, kind="stable")
    v = values[order]
    wv = w[order]
    swc = np.cumsum(wv)
    uniq, first, counts = np.unique(v, return_index=True, return_counts=True)
    last = first + counts
    before = swc[first] - wv[first]
    group_sum = swc[last - 1] - before
    avg = before + (group_sum + 1.0) / 2.0
    gid = np.searchsorted(uniq, v, side="left")
    ranks_sorted = avg[gid]
    ranks = np.empty(len(values), dtype=np.float64)
    ranks[order] = ranks_sorted
    return ranks


def weighted_auroc(scores: np.ndarray, y: np.ndarray, w: np.ndarray) -> float:
    pos = y == 1
    n_pos = float(w[pos].sum())
    n_neg = float(w[~pos].sum())
    if n_pos == 0 or n_neg == 0:
        return float("nan")
    ranks = weighted_rank(scores, w)
    u = float((w[pos] * ranks[pos]).sum() - n_pos * (n_pos + 1.0) / 2.0)
    return u / (n_pos * n_neg)


def weighted_pearson(x: np.ndarray, y: np.ndarray, w: np.ndarray) -> float:
    x = np.asarray(x, dtype=np.float64)
    y = np.asarray(y, dtype=np.float64)
    w = np.asarray(w, dtype=np.float64)
    sw = float(w.sum())
    if sw <= 0:
        return float("nan")
    sx, sy = float((w * x).sum()), float((w * y).sum())
    sxx, syy, sxy = (float((w * x * x).sum()), float((w * y * y).sum()),
                     float((w * x * y).sum()))
    den = np.sqrt((sxx - sx * sx / sw) * (syy - sy * sy / sw))
    if den <= 0:
        return float("nan")
    return (sxy - sx * sy / sw) / den


def weighted_spearman(x: np.ndarray, y: np.ndarray, w: np.ndarray) -> float:
    if len(x) < 2:
        return float("nan")
    rx = weighted_rank(x, w)
    ry = weighted_rank(y, w)
    return weighted_pearson(rx, ry, w)


def weighted_recall(scores: np.ndarray, threshold: float,
                    unknown: np.ndarray, w: np.ndarray) -> float:
    den = float(w[unknown].sum())
    if den <= 0:
        return float("nan")
    return float(w[(scores >= threshold) & unknown].sum()) / den


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------

def calibrate_threshold(scores_known: np.ndarray) -> float:
    return owg.calibrate_threshold(
        scores_known, fur=CALIB_KNOWN_FALSE_UNKNOWN_RATE)


def signal_metrics(p_accept: np.ndarray, accept: np.ndarray,
                   threshold: float) -> dict[str, Any]:
    """ACCEPT_TARGET prediction quality on Known rows. threshold is the
    method's V2_PROBE_CALIB-derived S_ACCEPT threshold (operating point:
    predict accept iff P_ACCEPT >= 1 - threshold)."""
    y = accept.astype(np.int64)
    p = np.clip(p_accept, 1e-15, 1.0 - 1e-15)
    pred = (p_accept >= 1.0 - threshold).astype(np.int64)
    return {
        "AUROC": float(roc_auc_score(y, p)),
        "AUPRC": float(average_precision_score(y, p)),
        "BALANCED_ACCURACY_AT_OPERATING_POINT": float(
            balanced_accuracy_score(y, pred)),
        "BRIER": float(brier_score_loss(y, p)),
        "LOG_LOSS": float(log_loss(y, p)),
    }


def unknown_metrics(unknown_score: np.ndarray, known_score: np.ndarray,
                    threshold: float) -> dict[str, float]:
    return owg.unknown_metrics(unknown_score, known_score, threshold)


def recovered_split(recoverable_kn: np.ndarray, recovered: np.ndarray,
                    rejected: np.ndarray) -> dict[str, int]:
    """A = recovered; A1 = recovered & accepted; A2 = recovered & rejected."""
    a = int((recoverable_kn & recovered).sum())
    a1 = int((recoverable_kn & recovered & ~rejected).sum())
    a2 = int((recoverable_kn & recovered & rejected).sum())
    return {"A": a, "A1_RECOVERED_AND_ACCEPTED": a1,
            "A2_RECOVERED_BUT_REJECTED": a2}


def recoverable_flag(pred_b: np.ndarray, pred_bt: np.ndarray,
                     pred_br: np.ndarray, pred_btr: np.ndarray,
                     labels: np.ndarray) -> np.ndarray:
    """Frozen RECOVERABLE_KNOWN definition (V1 gate line 712: basic_wrong &
    (bt_correct | br_correct | btr_correct); label-based, offline only)."""
    basic_wrong = pred_b != labels
    return basic_wrong & (pred_bt == labels) | basic_wrong & (
        pred_br == labels) | basic_wrong & (pred_btr == labels)


def residual_hard_flag(pred_b: np.ndarray, pred_bt: np.ndarray,
                       pred_br: np.ndarray, pred_btr: np.ndarray,
                       labels: np.ndarray) -> np.ndarray:
    basic_wrong = pred_b != labels
    return basic_wrong & (pred_bt != labels) & (pred_br != labels) & (
        pred_btr != labels)


# ---------------------------------------------------------------------------
# Frozen-artifact loading (identical semantics to the V1 failure-attribution
# tool; recomputation is deterministic and cross-verified before metrics)
# ---------------------------------------------------------------------------

def load_cell_table(artifact_root: Path, seed: int, rotation: str
                    ) -> dict[str, np.ndarray]:
    table = pq.read_table(artifact_root / (
        f"owg_v1_seed_{seed}_rotation_{rotation}_eval.parquet"))
    arrays: dict[str, np.ndarray] = {
        "source_row_index": table["source_row_index"].to_numpy(
            zero_copy_only=False),
        "canonical_label": np.array(table["canonical_label"].to_pylist(),
                                    dtype=object),
        "split_role": table["split_role"].to_numpy(zero_copy_only=False),
        "is_unknown": table["is_unknown"].to_numpy(zero_copy_only=False),
        "recoverable": table["recoverable"].to_numpy(
            zero_copy_only=False).astype(bool),
        "residual_hard": table["residual_hard"].to_numpy(
            zero_copy_only=False).astype(bool),
        "activity_group_digest": np.array(
            [bytes(v) for v in table["activity_group_digest"].to_pylist()],
            dtype=object),
        "temporal_block": table["temporal_block"].to_numpy(
            zero_copy_only=False),
    }
    for name in ("P0_BASIC_DIRECT", "P6_UTILITY_TYPED"):
        arrays[f"action_{name}"] = np.array(table[f"action_{name}"].to_pylist(),
                                            dtype=object)
        arrays[f"score_{name}"] = table[f"score_{name}"].to_numpy(
            zero_copy_only=False)
        arrays[f"pred_{name}"] = np.array(table[f"pred_{name}"].to_pylist(),
                                          dtype=object)
    return arrays


def rebuild_val_predictions(gate1_root: Path, artifact_root: Path,
                            seed: int, rotation: str) -> dict[str, Any]:
    """Recompute frozen-model probas/preds on VALIDATION rows in frozen
    table order (B/BT/BR/BTR). Used ONLY for the probability vectors and
    cross-verification. No training."""
    targets = owg.load_targets(gate1_root, seed)
    val_mask = targets["partition_code"] == owg.PARTITION_VALIDATION
    val_rows = targets["source_row_index"][val_mask]
    val_labels = targets["canonical_label"][val_mask]
    known = owg.known_classes_for(rotation)
    basic_rows, basic_arrays = owg.load_basic_features(gate1_root)
    basic_positions = {int(v): i for i, v in enumerate(basic_rows)}
    basic_val = owg.basic_matrix_for(val_rows, basic_arrays, basic_positions)
    history_val, history_names = owg.load_history_features(
        gate1_root, seed, val_rows)
    matrices_val = owg.build_feature_matrices(basic_val, history_val,
                                              history_names)
    with open(artifact_root / "models" / (
            f"owg_v1_seed_{seed}_rotation_{rotation}_models.pkl"), "rb") as f:
        payload = pickle.load(f)
    models: dict[str, Any] = payload["models"]
    proba: dict[str, np.ndarray] = {}
    pred: dict[str, np.ndarray] = {}
    for condition in CONDITIONS:
        clf = models[condition]
        proba[condition] = owg.align_rotation_proba(
            clf.predict_proba(matrices_val[condition]), clf.classes_, known)
        pred[condition] = clf.predict(matrices_val[condition])
    return {"val_rows": val_rows, "val_labels": val_labels, "known": known,
            "pred": pred, "proba": proba}


def cross_verify(arrays: dict[str, np.ndarray], rebuilt: dict[str, Any],
                 result: dict[str, Any], artifact_root: Path, seed: int,
                 rotation: str) -> dict[str, Any]:
    checks: dict[str, Any] = {}
    eval_table_path = artifact_root / (
        f"owg_v1_seed_{seed}_rotation_{rotation}_eval.parquet")
    checks["EVAL_TABLE_SHA256_MATCH"] = bool(
        owg.sha256_file(eval_table_path) == result["eval_table_sha256"])
    checks["SOURCE_ROW_ORDER_MATCH"] = bool(
        np.array_equal(arrays["source_row_index"], rebuilt["val_rows"]))
    checks["BASIC_PRED_MATCH"] = bool(
        np.array_equal(arrays["pred_P0_BASIC_DIRECT"],
                       rebuilt["pred"]["B"]))
    msp_b = 1.0 - rebuilt["proba"]["B"].max(axis=1)
    checks["BASIC_MSP_MATCH"] = bool(
        np.allclose(arrays["score_P0_BASIC_DIRECT"], msp_b, atol=1e-12))
    actions = arrays["action_P6_UTILITY_TYPED"]
    p_post = np.empty((len(actions), len(rebuilt["known"])),
                      dtype=np.float64)
    for act, cond in ACTION_MODEL.items():
        mask = actions == act
        p_post[mask] = rebuilt["proba"][cond][mask]
    msp_post = 1.0 - p_post.max(axis=1)
    checks["UTILITY_MSP_MATCH"] = bool(
        np.allclose(arrays["score_P6_UTILITY_TYPED"], msp_post, atol=1e-12))
    checks["UTILITY_PRED_MATCH"] = bool(
        np.array_equal(arrays["pred_P6_UTILITY_TYPED"],
                       np.array([rebuilt["pred"][ACTION_MODEL[a]][i]
                                 for i, a in enumerate(actions)],
                                dtype=object)))
    rec = recoverable_flag(rebuilt["pred"]["B"], rebuilt["pred"]["BT"],
                           rebuilt["pred"]["BR"], rebuilt["pred"]["BTR"],
                           rebuilt["val_labels"])
    res = residual_hard_flag(rebuilt["pred"]["B"], rebuilt["pred"]["BT"],
                             rebuilt["pred"]["BR"], rebuilt["pred"]["BTR"],
                             rebuilt["val_labels"])
    checks["RECOVERABLE_FLAG_MATCH"] = bool(
        np.array_equal(arrays["recoverable"], rec))
    checks["RESIDUAL_HARD_FLAG_MATCH"] = bool(
        np.array_equal(arrays["residual_hard"], res))
    return checks


def p_post_matrix(actions: np.ndarray, proba: dict[str, np.ndarray],
                  n_classes: int) -> np.ndarray:
    out = np.empty((len(actions), n_classes), dtype=np.float64)
    for act, cond in ACTION_MODEL.items():
        mask = actions == act
        out[mask] = proba[cond][mask]
    return out


# ---------------------------------------------------------------------------
# Probe capacity ladder (frozen; pure; tested with synthetic fixtures)
# ---------------------------------------------------------------------------

def fit_probes(features: dict[str, np.ndarray], y_fit: np.ndarray,
               fit_mask: np.ndarray, seed: int) -> dict[str, np.ndarray]:
    """Fit the frozen capacity ladder on V2_PROBE_FIT rows only.

    L_POST/L_TRAJ: StandardScaler + LogisticRegression (frozen LINEAR_CONFIG).
    N_POST/N_TRAJ: RandomForestClassifier (frozen RF_CONFIG, random_state =
    the rotation seed). Returns P_ACCEPT = P(class 1) for ALL rows.
    No tuning; no Unknown rows (y_fit comes from ACCEPT_TARGET on Known fit
    rows only, via the caller); GT never enters inference features."""
    proba_fit: dict[str, np.ndarray] = {}
    for probe in PROBES:
        feats = features[probe]
        if probe in ("L_POST", "L_TRAJ"):
            scaler = StandardScaler().fit(feats[fit_mask])
            model = LogisticRegression(**LINEAR_CONFIG)
            model.fit(scaler.transform(feats[fit_mask]), y_fit)
            proba_fit[probe] = model.predict_proba(
                scaler.transform(feats))[:, 1]
        else:
            model = RandomForestClassifier(
                random_state=int(seed), **RF_CONFIG)
            model.fit(feats[fit_mask], y_fit)
            proba_fit[probe] = model.predict_proba(feats)[:, 1]
    return proba_fit


# ---------------------------------------------------------------------------
# Cell execution (Phase C; also reusable by smoke mode)
# ---------------------------------------------------------------------------

def run_cell(seed: int, rotation: str, v1_root: Path, gate1_root: Path,
             out_root: Path, smoke: bool = False) -> dict[str, Any]:
    artifact_root = v1_root
    arrays = load_cell_table(artifact_root, seed, rotation)
    rebuilt = rebuild_val_predictions(gate1_root, artifact_root, seed,
                                      rotation)
    result = json.loads((artifact_root / (
        f"owg_v1_seed_{seed}_rotation_{rotation}_result.json")).read_text(
            encoding="utf-8"))
    checks = cross_verify(arrays, rebuilt, result, artifact_root, seed,
                          rotation)
    if not all(v is True for v in checks.values()):
        raise RuntimeError(
            f"CROSS_VERIFICATION_FAILED seed={seed} rotation={rotation}: "
            f"{[k for k, v in checks.items() if v is not True]}")

    n_classes = len(rebuilt["known"])
    actions = arrays["action_P6_UTILITY_TYPED"]
    p_pre = rebuilt["proba"]["B"]
    p_post = p_post_matrix(actions, rebuilt["proba"], n_classes)

    known_flag = arrays["is_unknown"] == 0
    eval_mask = arrays["split_role"] == 1
    calib_mask = arrays["split_role"] == 0
    calib_kn = calib_mask & known_flag

    # ---- V2 split on VAL_CALIB Known (frozen, deterministic) ----
    split_roles = np.full(len(actions), -1, dtype=np.int8)
    split_roles[calib_kn] = build_probe_split(
        seed, rotation, arrays["activity_group_digest"][calib_kn],
        arrays["canonical_label"][calib_kn],
        arrays["temporal_block"][calib_kn])
    fit_mask = calib_kn & (split_roles == 0)
    calib_fit_kn = calib_kn & (split_roles == 1)
    if not fit_mask.any() or not calib_fit_kn.any():
        raise RuntimeError(f"EMPTY_SPLIT seed={seed} rotation={rotation}")

    # ---- probe training on V2_PROBE_FIT Known rows only ----
    post_f = post_only_matrix(p_post, actions)
    traj_f = trajectory_matrix(p_pre, p_post, actions)
    labels = arrays["canonical_label"]
    y_fit = accept_target(arrays["pred_P6_UTILITY_TYPED"][fit_mask],
                          labels[fit_mask])
    # frozen schema mapping (capacity ladder, no alternatives)
    probe_feats = {"L_POST": post_f, "L_TRAJ": traj_f,
                   "N_POST": post_f, "N_TRAJ": traj_f}
    proba_fit = fit_probes(probe_feats, y_fit, fit_mask, int(seed))

    # ---- scores per method (all rows) ----
    scores: dict[str, np.ndarray] = {}
    scores["B0_BASIC_MSP"] = arrays["score_P0_BASIC_DIRECT"].astype(
        np.float64)
    scores["B1_UTILITY_POST_MSP"] = arrays["score_P6_UTILITY_TYPED"].astype(
        np.float64)
    for probe in PROBES:
        scores[probe] = 1.0 - proba_fit[probe]

    # ---- thresholds on V2_PROBE_CALIB Known (5% Known FUR) ----
    thresholds: dict[str, float] = {}
    for method in METHODS:
        thresholds[method] = calibrate_threshold(
            scores[method][calib_fit_kn])

    # ---- EVAL metrics ----
    ev_kn = eval_mask & known_flag
    ev_rec_kn = ev_kn & arrays["recoverable"]
    labels_ev = labels[ev_kn]
    unknown_ev = eval_mask & (arrays["is_unknown"] == 1)
    preds_ev = {
        "B0_BASIC_MSP": arrays["pred_P0_BASIC_DIRECT"][ev_kn],
        "B1_UTILITY_POST_MSP": arrays["pred_P6_UTILITY_TYPED"][ev_kn],
    }
    for probe in PROBES:
        preds_ev[probe] = arrays["pred_P6_UTILITY_TYPED"][ev_kn]

    metrics: dict[str, Any] = {}
    furk_denominator = int(ev_rec_kn.sum())
    for method in METHODS:
        thr = thresholds[method]
        rej = scores[method] >= thr
        rej_ev = rej[ev_kn]
        recovered = preds_ev[method] == labels_ev
        # ev_rec_kn is a full-table boolean mask; index it to the EVAL-Known
        # positions (same length as recovered / rej_ev).
        split = recovered_split(ev_rec_kn[ev_kn], recovered, rej_ev)
        denom = furk_denominator
        a1a2 = split["A1_RECOVERED_AND_ACCEPTED"] + split[
            "A2_RECOVERED_BUT_REJECTED"]
        unk_scores = scores[method][unknown_ev]
        kn_scores = scores[method][ev_kn]
        um = unknown_metrics(unk_scores, kn_scores, thr)
        acquired = actions[ev_kn] != "NONE"
        metrics[method] = {
            "FURK_NUMERATOR": int((rej_ev & ev_rec_kn[ev_kn]).sum()),
            "FURK_DENOMINATOR": denom,
            "FURK": float((rej_ev & ev_rec_kn[ev_kn]).sum()) / denom,
            "RECOVERED_BUT_REJECTED_RATE": (
                split["A2_RECOVERED_BUT_REJECTED"] / denom),
            "RECOVERY_CONDITIONAL_REJECTION_RATE": (
                split["A2_RECOVERED_BUT_REJECTED"] / a1a2) if a1a2 else 0.0,
            "RECOVERED_AND_ACCEPTED_RATE": (
                split["A1_RECOVERED_AND_ACCEPTED"] / denom),
            "A": split["A"], "A1": split["A1_RECOVERED_AND_ACCEPTED"],
            "A2": split["A2_RECOVERED_BUT_REJECTED"],
            "KNOWN_FALSE_UNKNOWN_RATE": float(rej_ev.mean()),
            "KNOWN_MACRO_F1_PRE_NOVELTY": float(
                f1_score(labels_ev, preds_ev[method], average="macro")),
            "ACCEPTED_KNOWN_ACCURACY": float(
                accuracy_score(labels_ev[~rej_ev],
                               preds_ev[method][~rej_ev]))
                if (~rej_ev).any() else float("nan"),
            "UNKNOWN_AUROC": um["auroc"],
            "UNKNOWN_AUPR": um["aupr"],
            "UNKNOWN_RECALL_AT_CALIBRATED_FUR": um[
                "unknown_recall_at_calibrated_fur"],
            "TRUE_UNKNOWN_ACQUISITION_RATE": float(
                (actions[unknown_ev] != "NONE").mean())
                if unknown_ev.sum() else 0.0,
            "EVIDENCE_COST_TOTAL_UNITS": float(
                np.array([ACTION_COSTS[a] for a in actions[eval_mask]]).sum()),
            "EVIDENCE_MEAN_COST": float(
                np.array([ACTION_COSTS[a] for a in actions[eval_mask]]).mean()),
            "THRESHOLD": thr,
        }

    # ---- signal characterization on EVAL Known (accept-target) ----
    accept_ev = accept_target(arrays["pred_P6_UTILITY_TYPED"][ev_kn],
                              labels_ev)
    signal: dict[str, Any] = {}
    for probe in PROBES:
        signal[probe] = signal_metrics(proba_fit[probe][ev_kn], accept_ev,
                                       thresholds[probe])
        signal[probe]["ACCEPT_POSITIVE_RATE"] = float(accept_ev.mean())
    signal["N_EVAL_KNOWN"] = int(ev_kn.sum())

    # ---- classification-utility vs novelty-utility (Section 32 data) ----
    # Raw per-row arrays are kept in underscore caches for the pooled
    # bootstrap; they never enter the report body.
    util: dict[str, Any] = {}
    util_cache: dict[str, dict[str, np.ndarray]] = {}
    for family in FAMILIES:
        condition = ACTION_MODEL[family]
        _, _, signed = g1b.utility_labels(rebuilt["pred"]["B"],
                                          rebuilt["pred"][condition],
                                          rebuilt["val_labels"])
        msp_e = 1.0 - rebuilt["proba"][condition].max(axis=1)
        novelty_util = msp_b_of(rebuilt) - msp_e
        pop = eval_mask & known_flag
        rho = weighted_spearman(signed[pop].astype(np.float64),
                                novelty_util[pop],
                                np.ones(int(pop.sum())))
        help_mask = pop & (signed == 1)
        nu = novelty_util[help_mask]
        util[family] = {
            "SPEARMAN_CLASSIFICATION_UTILITY_VS_NOVELTY_UTILITY": rho,
            "CLASSIFICATION_HELP_N": int(help_mask.sum()),
            "HELP_NOVELTY_IMPROVE_RATE": float(
                (nu > 0.01).mean()) if len(nu) else None,
            "HELP_NOVELTY_WORSEN_RATE": float(
                (nu < -0.01).mean()) if len(nu) else None,
            "HELP_MEAN_NOVELTY_UTILITY": float(nu.mean()) if len(nu) else None,
        }
        util_cache[family] = {"signed": signed, "novelty_util": novelty_util}

    # ---- headroom diagnostics (analysis only) ----
    recovered_ev = preds_ev["B1_UTILITY_POST_MSP"] == labels_ev
    p6_recovery_rate = float(recovered_ev[ev_rec_kn[ev_kn]].mean())
    router_headroom = 1.0 - p6_recovery_rate
    rcj_b1 = metrics["B1_UTILITY_POST_MSP"][
        "RECOVERY_CONDITIONAL_REJECTION_RATE"]

    cell_out = {
        "seed": int(seed), "rotation": rotation,
        "n_eval": int(eval_mask.sum()), "n_calib_known": int(calib_kn.sum()),
        "n_fit": int(fit_mask.sum()), "n_calib_fit": int(calib_fit_kn.sum()),
        "n_eval_known": int(ev_kn.sum()),
        "n_eval_unknown": int(unknown_ev.sum()),
        "n_recoverable_known_eval": furk_denominator,
        "cross_verification": checks,
        "thresholds": thresholds,
        "metrics": metrics,
        "signal": signal,
        "utility_correlation": util,
        "P6_RECOVERY_RATE": float(p6_recovery_rate),
        "ROUTER_RECOVERY_HEADROOM": float(router_headroom),
        "INTERFACE_HEADROOM_PROXY": float(rcj_b1),
        "FURK_DENOMINATOR_IDENTITY": {
            m: int(metrics[m]["FURK_DENOMINATOR"]) for m in METHODS},
        "_scores_cache": {m: scores[m] for m in METHODS},
        "_paccept_cache": proba_fit,
        "_util_cache": util_cache,
    }
    if not smoke:
        (out_root / "cells").mkdir(parents=True, exist_ok=True)
        # split manifest (group -> role) + hashes, frozen before evaluation
        ck_digests = arrays["activity_group_digest"][calib_kn]
        ck_roles = split_roles[calib_kn]
        _, first = np.unique(ck_digests, return_index=True)
        manifest = {
            "schema_version": SPLIT_MANIFEST_SCHEMA,
            "seed": int(seed), "rotation": rotation,
            "split_rule": "SHA256(seed||rotation||group_digest), stratum=(class,block) of primary row, smaller-bin assignment, ties->FIT",
            "groups": [
                {"digest": bytes(ck_digests[i]).hex(),
                 "role": int(ck_roles[i]),
                 "rows": int((ck_digests == ck_digests[i]).sum())}
                for i in first],
            "n_groups": int(len(first)),
            "n_fit": int(fit_mask.sum()),
            "n_calib_fit": int(calib_fit_kn.sum()),
        }
        manifest_text = json.dumps(manifest, sort_keys=True).encode("utf-8")
        manifest_sha = hashlib.sha256(manifest_text).hexdigest()
        cell_out["split_manifest_sha256"] = manifest_sha
        (out_root / "cells" / (
            f"v2_split_manifest_seed_{seed}_rotation_{rotation}.json")
         ).write_text(manifest_text.decode("utf-8"))
        np.savez_compressed(
            out_root / "cells" / (
                f"v2_features_seed_{seed}_rotation_{rotation}.npz"),
            post_only=post_f, trajectory=traj_f,
            split_roles=split_roles,
            action=actions.astype(np.str_),
            label=np.array(labels, dtype=np.str_),
            is_unknown=arrays["is_unknown"],
            split_role=arrays["split_role"],
            recoverable=arrays["recoverable"],
            residual_hard=arrays["residual_hard"],
            activity_group_digest=np.array(
                [bytes(v).hex() for v in arrays["activity_group_digest"]],
                dtype=np.str_),
            temporal_block=arrays["temporal_block"])
        with open(out_root / "cells" / (
                f"v2_probes_seed_{seed}_rotation_{rotation}.pkl"), "wb") as f:
            pickle.dump({"schema": "V2_PROBES_V1",
                         "seed": int(seed), "rotation": rotation,
                         "probabilities": proba_fit,
                         "thresholds": thresholds,
                         "post_only_features": list(POST_ONLY_FEATURES),
                         "trajectory_features": list(TRAJECTORY_FEATURES)},
                        f)
    return cell_out


def msp_b_of(rebuilt: dict[str, Any]) -> np.ndarray:
    return 1.0 - rebuilt["proba"]["B"].max(axis=1)


# ---------------------------------------------------------------------------
# Aggregation (per rotation: mean over seeds; pooled: sums over cells)
# ---------------------------------------------------------------------------

def rotation_mean(cells: list[dict[str, Any]], rotation: str,
                  key: str, sub: str | None = None,
                  method: str | None = None) -> float:
    vals = []
    for c in cells:
        if c["rotation"] != rotation:
            continue
        v = c
        if sub:
            v = c[sub]
        if method is not None:
            v = v[method]
        vals.append(v[key])
    return float(np.mean([float(x) for x in vals]))


def pooled_furk(cells: list[dict[str, Any]], method: str) -> dict[str, float]:
    num = sum(c["metrics"][method]["FURK_NUMERATOR"] for c in cells)
    den = sum(c["metrics"][method]["FURK_DENOMINATOR"] for c in cells)
    return {"NUMERATOR": int(num), "DENOMINATOR": int(den),
            "RATE": float(num) / den}


def pooled_a1a2(cells: list[dict[str, Any]], method: str
                ) -> dict[str, float]:
    a1 = sum(c["metrics"][method]["A1"] for c in cells)
    a2 = sum(c["metrics"][method]["A2"] for c in cells)
    den = sum(c["metrics"][method]["FURK_DENOMINATOR"] for c in cells)
    rcj = float(a2) / (a1 + a2) if (a1 + a2) else 0.0
    return {"A1": int(a1), "A2": int(a2), "DENOMINATOR": int(den),
            "RECOVERED_BUT_REJECTED_RATE": float(a2) / den,
            "RECOVERY_CONDITIONAL_REJECTION_RATE": rcj}


def pooled_metric(cells: list[dict[str, Any]], section: str, key: str,
                  method: str | None = None) -> float:
    if method is None:
        vals = [c[section][key] for c in cells]
    else:
        vals = [c[section][method][key] for c in cells]
    return float(np.mean([float(v) for v in vals]))


# ---------------------------------------------------------------------------
# Signal / transfer / end-to-end status (frozen rules)
# ---------------------------------------------------------------------------

def delta_auroc_by_rotation(cells: list[dict[str, Any]],
                            capacity: str) -> dict[str, float]:
    """Per-rotation mean-over-seeds of TRAJ accept-AUROC - POST accept-AUROC
    for the given capacity (linear -> L, nonlinear -> N)."""
    post = {"linear": "L_POST", "nonlinear": "N_POST"}[capacity]
    traj = {"linear": "L_TRAJ", "nonlinear": "N_TRAJ"}[capacity]
    out: dict[str, float] = {}
    for rotation in ROTATIONS:
        deltas = [c["signal"][traj]["AUROC"] - c["signal"][post]["AUROC"]
                  for c in cells if c["rotation"] == rotation]
        out[rotation] = float(np.mean(deltas))
    return out


def level_signal_status(cells: list[dict[str, Any]], capacity: str,
                        delta_ci_lower: float | None) -> str:
    deltas = delta_auroc_by_rotation(cells, capacity)
    mean_delta = float(np.mean(list(deltas.values())))
    n_pos = sum(1 for v in deltas.values() if v > 0)
    supported = (mean_delta >= SIGNAL_MIN_DELTA_AUROC
                 and n_pos >= SIGNAL_MIN_ROTATIONS_POSITIVE
                 and delta_ci_lower is not None and delta_ci_lower > 0)
    return "SUPPORTED" if supported else "NOT_ESTABLISHED"


def recovery_trajectory_signal(linear_status: str, nonlinear_status: str,
                               linear_deltas: dict[str, float]) -> str:
    nonlinear_ok = nonlinear_status == "SUPPORTED"
    linear_ok = linear_status == "SUPPORTED"
    linear_pos = sum(1 for v in linear_deltas.values() if v > 0) >= 2
    if nonlinear_ok and (linear_ok or linear_pos):
        return "STRONG"
    if (nonlinear_ok or linear_ok) or (
            sum(1 for v in linear_deltas.values() if v > 0) >= 2):
        return "WEAK"
    return "NOT_ESTABLISHED"


def rotation_means(cells: list[dict[str, Any]], section: str, key: str,
                   method: str) -> dict[str, float]:
    return {r: rotation_mean(cells, r, key, section, method)
            for r in ROTATIONS}


def transfer_status(cells: list[dict[str, Any]],
                    boot: dict[str, Any]) -> dict[str, Any]:
    furk_post = rotation_means(cells, "metrics", "FURK", "N_POST")
    furk_traj = rotation_means(cells, "metrics", "FURK", "N_TRAJ")
    d_furk = {r: furk_traj[r] - furk_post[r] for r in ROTATIONS}
    mean_d = float(np.mean(list(d_furk.values())))
    n_improve = sum(1 for v in d_furk.values() if v < 0)
    no_worse = all(v <= T1_MAX_ROTATION_WORSE for v in d_furk.values())
    t1 = (mean_d <= T1_FURK_DIFF_MAX and n_improve >= T1_MIN_ROTATIONS
          and no_worse)

    rcj_post = rotation_means(cells, "metrics",
                              "RECOVERY_CONDITIONAL_REJECTION_RATE", "N_POST")
    rcj_traj = rotation_means(cells, "metrics",
                              "RECOVERY_CONDITIONAL_REJECTION_RATE", "N_TRAJ")
    d_rcj = {r: rcj_post[r] - rcj_traj[r] for r in ROTATIONS}
    mean_red = float(np.mean(list(d_rcj.values())))
    t2 = (mean_red >= T2_RCJ_REDUCTION_MIN
          and sum(1 for v in d_rcj.values() if v > 0) >= T2_MIN_ROTATIONS)

    auroc_post = rotation_means(cells, "metrics", "UNKNOWN_AUROC", "N_POST")
    auroc_traj = rotation_means(cells, "metrics", "UNKNOWN_AUROC", "N_TRAJ")
    loss = {r: auroc_post[r] - auroc_traj[r] for r in ROTATIONS}
    t3 = (float(np.mean(list(loss.values()))) <= T3_AUROC_LOSS_MAX
          and all(v <= T3_MAX_ROTATION_LOSS for v in loss.values()))

    rec_post = rotation_means(cells, "metrics",
                              "UNKNOWN_RECALL_AT_CALIBRATED_FUR", "N_POST")
    rec_traj = rotation_means(cells, "metrics",
                              "UNKNOWN_RECALL_AT_CALIBRATED_FUR", "N_TRAJ")
    rloss = {r: rec_post[r] - rec_traj[r] for r in ROTATIONS}
    t4 = (float(np.mean(list(rloss.values()))) <= T4_RECALL_LOSS_MAX
          and all(v <= T4_MAX_ROTATION_LOSS for v in rloss.values()))

    ci = boot["FURK_N_TRAJ_MINUS_N_POST"]["ci95"]
    t5 = bool(ci[1] < 0)

    return {"T1": bool(t1), "T2": bool(t2), "T3": bool(t3), "T4": bool(t4),
            "T5": bool(t5),
            "FURK_DIFF_BY_ROTATION": d_furk, "FURK_DIFF_MEAN": mean_d,
            "RCJ_REDUCTION_BY_ROTATION": d_rcj,
            "RCJ_REDUCTION_MEAN": mean_red,
            "AUROC_LOSS_BY_ROTATION": loss,
            "RECALL_LOSS_BY_ROTATION": rloss,
            "PASS": bool(t1 and t2 and t3 and t4 and t5)}


def end_to_end_status(cells: list[dict[str, Any]],
                      boot: dict[str, Any]) -> dict[str, Any]:
    furk_b0 = rotation_means(cells, "metrics", "FURK", "B0_BASIC_MSP")
    furk_ntraj = rotation_means(cells, "metrics", "FURK", "N_TRAJ")
    d_furk = {r: furk_b0[r] - furk_ntraj[r] for r in ROTATIONS}
    mean_gain = float(np.mean(list(d_furk.values())))
    e1 = (mean_gain >= E1_FURK_GAIN_MIN
          and sum(1 for v in d_furk.values() if v >= E1_FURK_GAIN_MIN)
          >= E1_MIN_ROTATIONS
          and all(v >= -E1_MAX_ROTATION_WORSE for v in d_furk.values()))

    ci = boot["FURK_N_TRAJ_MINUS_B0"]["ci95"]
    e2 = bool(ci[1] < 0)

    auroc_b0 = rotation_means(cells, "metrics", "UNKNOWN_AUROC", "B0_BASIC_MSP")
    auroc_ntraj = rotation_means(cells, "metrics", "UNKNOWN_AUROC", "N_TRAJ")
    loss = {r: auroc_b0[r] - auroc_ntraj[r] for r in ROTATIONS}
    e3 = (float(np.mean(list(loss.values()))) <= E3_AUROC_LOSS_MAX
          and all(v <= E3_MAX_ROTATION_LOSS for v in loss.values()))

    rec_b0 = rotation_means(cells, "metrics",
                            "UNKNOWN_RECALL_AT_CALIBRATED_FUR", "B0_BASIC_MSP")
    rec_ntraj = rotation_means(cells, "metrics",
                               "UNKNOWN_RECALL_AT_CALIBRATED_FUR", "N_TRAJ")
    rloss = {r: rec_b0[r] - rec_ntraj[r] for r in ROTATIONS}
    e4 = (float(np.mean(list(rloss.values()))) <= E4_RECALL_LOSS_MAX
          and all(v <= E4_MAX_ROTATION_LOSS for v in rloss.values()))

    return {"E1": bool(e1), "E2": bool(e2), "E3": bool(e3), "E4": bool(e4),
            "FURK_GAIN_BY_ROTATION": d_furk, "FURK_GAIN_MEAN": mean_gain,
            "AUROC_LOSS_BY_ROTATION": loss,
            "RECALL_LOSS_BY_ROTATION": rloss,
            "PASS": bool(e1 and e2 and e3 and e4)}


def interpret_case(signal: str, transfer: dict[str, Any],
                   e2e: dict[str, Any], cells: list[dict[str, Any]]
                   ) -> dict[str, str]:
    t_pass = transfer["PASS"]
    e_pass = e2e["PASS"]
    if signal == "STRONG" and t_pass and e_pass:
        return {"CASE": "A",
                "C1_STATUS": "RECOVERY_AWARE_OPEN_WORLD_MECHANISM_SUPPORTED",
                "NEXT_PROPOSED_ACTION": "UNKNOWN_CANDIDATE_PURIFICATION_GATE_V2"}
    if signal == "STRONG" and t_pass and not e_pass:
        return {"CASE": "B",
                "C1_STATUS":
                    "RECOVERY_SIGNAL_AND_INTERFACE_SUPPORTED_UPSTREAM_LIMITED",
                "NEXT_PROPOSED_ACTION": "OPEN_WORLD_ROUTER_OBJECTIVE_GATE_V1"}
    if signal == "STRONG" and not t_pass:
        return {"CASE": "C",
                "C1_STATUS":
                    "RECOVERY_SIGNAL_SUPPORTED_OPEN_WORLD_MECHANISM_UNRESOLVED",
                "NEXT_PROPOSED_ACTION":
                    "RESEARCHER_REVIEW_FORMAL_MODEL_B_NOVELTY_DESIGN"}
    if signal == "WEAK":
        return {"CASE": "D", "C1_STATUS": "RECOVERY_SIGNAL_INCONCLUSIVE",
                "NEXT_PROPOSED_ACTION":
                    "RESEARCHER_REASSESS_COST_BENEFIT_BEFORE_MODEL_B"}
    # NOT_ESTABLISHED: inspect headroom diagnostics
    router_large = sum(1 for r in ROTATIONS
                       if rotation_mean(cells, r, "ROUTER_RECOVERY_HEADROOM")
                       >= HEADROOM_LARGE_ROUTER) >= HEADROOM_MIN_ROTATIONS
    interface_large = sum(
        1 for r in ROTATIONS
        if rotation_mean(cells, r, "INTERFACE_HEADROOM_PROXY")
        >= HEADROOM_LARGE_INTERFACE) >= HEADROOM_MIN_ROTATIONS
    if router_large or interface_large:
        return {"CASE": "E_HEADROOM",
                "C1_STATUS":
                    "RECOVERY_TRAJECTORY_NOT_ESTABLISHED_CURRENT_REPRESENTATION_INCONCLUSIVE",
                "NEXT_PROPOSED_ACTION":
                    "RESEARCHER_REASSESS_MAINLINE_BEFORE_ANY_EXPENSIVE_MODEL"}
    return {"CASE": "E_NO_HEADROOM",
            "C1_STATUS":
                "RECOVERABILITY_MAINLINE_HIGH_RISK_UNDER_CURRENT_EVIDENCE_CONTRACT",
            "NEXT_PROPOSED_ACTION": "RESEARCHER_REASSESS_PAPER_MAINLINE"}


# ---------------------------------------------------------------------------
# Pooled group-atomic paired bootstrap (frozen convention: 1000 reps,
# unit = private activity group pooled over 3 rotations x 3 seeds, same
# draws for all methods -> paired by construction; temporal-block aware
# because each group's rows and block membership are frozen).
# ---------------------------------------------------------------------------

def run_bootstrap(cells: list[dict[str, Any]], v1_root: Path) -> dict[str, Any]:
    # Per-cell pooled structures over EVAL rows
    all_scores: dict[str, np.ndarray] = {m: [] for m in METHODS}
    all_unknown: list[np.ndarray] = []
    all_group_pool: list[np.ndarray] = []  # group id (within pooled pool)
    all_cell_group_ids: list[np.ndarray] = []  # per row: group in pooled pool
    pooled_group_owner: list[int] = []  # pooled group -> cell idx
    all_accept: list[np.ndarray] = []  # accept target on EVAL known
    all_paccept: dict[str, list[np.ndarray]] = {p: [] for p in PROBES}
    # Section 32 structures on EVAL Known
    all_signed: dict[str, list[np.ndarray]] = {f: [] for f in FAMILIES}
    all_novelty_util: dict[str, list[np.ndarray]] = {f: [] for f in FAMILIES}
    # per-group linear counts
    g_denom: list[np.ndarray] = []  # recoverable-known EVAL per group
    g_furk_num: dict[str, list[np.ndarray]] = {m: [] for m in METHODS}
    g_a1: dict[str, list[np.ndarray]] = {m: [] for m in METHODS}
    g_a2: dict[str, list[np.ndarray]] = {m: [] for m in METHODS}
    g_help_n: dict[str, list[np.ndarray]] = {f: [] for f in FAMILIES}
    g_help_imp: dict[str, list[np.ndarray]] = {f: [] for f in FAMILIES}
    g_help_wor: dict[str, list[np.ndarray]] = {f: [] for f in FAMILIES}

    cell_id = 0
    for c in cells:
        seed, rotation = int(c["seed"]), c["rotation"]
        table = pq.read_table(v1_root / (
            f"owg_v1_seed_{seed}_rotation_{rotation}_eval.parquet"))
        groups = np.array([bytes(v) for v in
                           table["activity_group_digest"].to_pylist()],
                          dtype=object)
        eval_mask = table["split_role"].to_numpy().astype(bool)
        known = table["is_unknown"].to_numpy().astype(bool) == 0
        recoverable = table["recoverable"].to_numpy().astype(bool)
        is_unknown = table["is_unknown"].to_numpy().astype(bool)
        n_rows = len(groups)
        group_local, ginv = np.unique(groups, return_inverse=True)
        n_gl = len(group_local)
        offset = len(pooled_group_owner)
        pooled_group_owner.extend([cell_id] * n_gl)
        grp_pooled = ginv + offset
        # EVAL row indices
        ev = np.flatnonzero(eval_mask)
        ev_kn = ev[known[ev]]
        ev_rec_kn = ev[recoverable[ev] & known[ev]]
        # thresholds from the cell
        thr = c["thresholds"]
        for m in METHODS:
            all_scores[m].append(c["_scores_cache"][m][ev])
        all_unknown.append(is_unknown[ev])
        all_group_pool.append(grp_pooled[ev])
        labels_ev = np.array(table["canonical_label"].to_pylist(),
                             dtype=object)
        pred6 = np.array(table["pred_P6_UTILITY_TYPED"].to_pylist(),
                         dtype=object)
        pred0 = np.array(table["pred_P0_BASIC_DIRECT"].to_pylist(),
                         dtype=object)
        y_accept = (pred6[ev_kn] == labels_ev[ev_kn])
        all_accept.append(y_accept)
        # per-group linear counts on recoverable-known EVAL
        g_rec = ginv[ev_rec_kn]
        g_denom.append(np.bincount(g_rec, minlength=n_gl).astype(np.float64))
        for m in METHODS:
            sc = c["_scores_cache"][m]
            rej = sc[ev_rec_kn] >= thr[m]
            g_furk_num[m].append(np.bincount(
                g_rec, weights=rej.astype(np.float64), minlength=n_gl))
            rec_at = (pred6 if m != "B0_BASIC_MSP" else pred0)[ev_rec_kn]
            recovered_at = rec_at == labels_ev[ev_rec_kn]
            g_a1[m].append(np.bincount(
                g_rec, weights=(recovered_at & ~rej).astype(np.float64),
                minlength=n_gl))
            g_a2[m].append(np.bincount(
                g_rec, weights=(recovered_at & rej).astype(np.float64),
                minlength=n_gl))
        # signal / Section-32 populations are EVAL-Known rows only (aligned
        # with accept_ev and w_kn below)
        for probe in PROBES:
            all_paccept[probe].append(c["_paccept_cache"][probe][ev_kn])
        for family in FAMILIES:
            signed = c["_util_cache"][family]["signed"][ev_kn]
            nu = c["_util_cache"][family]["novelty_util"][ev_kn]
            all_signed[family].append(signed)
            all_novelty_util[family].append(nu)
            g = ginv[ev_kn]
            h = (signed == 1)
            imp = nu > 0.01
            wor = nu < -0.01
            g_help_n[family].append(np.bincount(
                g, weights=h.astype(np.float64), minlength=n_gl))
            g_help_imp[family].append(np.bincount(
                g, weights=(h & imp).astype(np.float64), minlength=n_gl))
            g_help_wor[family].append(np.bincount(
                g, weights=(h & wor).astype(np.float64), minlength=n_gl))
        cell_id += 1

    # Concatenate over cells
    n_groups_total = len(pooled_group_owner)
    group_pool = np.concatenate(all_group_pool)  # pooled group id per EVAL row
    unknown_ev = np.concatenate(all_unknown)
    known_ev = ~unknown_ev
    accept_ev = np.concatenate(all_accept)
    scores: dict[str, np.ndarray] = {m: np.concatenate(all_scores[m])
                                     for m in METHODS}
    paccept: dict[str, np.ndarray] = {p: np.concatenate(all_paccept[p])
                                      for p in PROBES}
    signed_pool: dict[str, np.ndarray] = {f: np.concatenate(all_signed[f])
                                          for f in FAMILIES}
    nu_pool: dict[str, np.ndarray] = {f: np.concatenate(all_novelty_util[f])
                                      for f in FAMILIES}
    denom_g = np.concatenate(g_denom)
    furk_g = {m: np.concatenate(g_furk_num[m]) for m in METHODS}
    a1_g = {m: np.concatenate(g_a1[m]) for m in METHODS}
    a2_g = {m: np.concatenate(g_a2[m]) for m in METHODS}
    help_n_g = {f: np.concatenate(g_help_n[f]) for f in FAMILIES}
    help_imp_g = {f: np.concatenate(g_help_imp[f]) for f in FAMILIES}
    help_wor_g = {f: np.concatenate(g_help_wor[f]) for f in FAMILIES}

    # thresholds per row (per cell) for recall computation
    thr_by_row: dict[str, np.ndarray] = {}
    # rebuild per-cell thresholds aligned to EVAL rows
    thr_concat: dict[str, list[np.ndarray]] = {m: [] for m in METHODS}
    for c in cells:
        thr = c["thresholds"]
        for m in METHODS:
            thr_concat[m].append(np.full(int(c["n_eval"]), thr[m]))
    thr_by_row = {m: np.concatenate(thr_concat[m]) for m in METHODS}

    rng = np.random.default_rng(BOOTSTRAP_RNG_OFFSET)
    rep = {
        "FURK_N_TRAJ_MINUS_N_POST": np.empty(BOOTSTRAP_REPS),
        "FURK_L_TRAJ_MINUS_L_POST": np.empty(BOOTSTRAP_REPS),
        "FURK_N_TRAJ_MINUS_B1": np.empty(BOOTSTRAP_REPS),
        "FURK_L_TRAJ_MINUS_B1": np.empty(BOOTSTRAP_REPS),
        "FURK_N_TRAJ_MINUS_B0": np.empty(BOOTSTRAP_REPS),
        "RBR_N_TRAJ_MINUS_N_POST": np.empty(BOOTSTRAP_REPS),
        "RBR_N_TRAJ_MINUS_B1": np.empty(BOOTSTRAP_REPS),
        "RCJ_N_TRAJ_MINUS_N_POST": np.empty(BOOTSTRAP_REPS),
        "RCJ_N_TRAJ_MINUS_B1": np.empty(BOOTSTRAP_REPS),
        "UNKNOWN_AUROC_N_TRAJ_MINUS_N_POST": np.empty(BOOTSTRAP_REPS),
        "UNKNOWN_AUROC_N_TRAJ_MINUS_B0": np.empty(BOOTSTRAP_REPS),
        "UNKNOWN_RECALL_N_TRAJ_MINUS_N_POST": np.empty(BOOTSTRAP_REPS),
        "UNKNOWN_RECALL_N_TRAJ_MINUS_B0": np.empty(BOOTSTRAP_REPS),
        "LINEAR_DELTA_AUROC": np.empty(BOOTSTRAP_REPS),
        "NONLINEAR_DELTA_AUROC": np.empty(BOOTSTRAP_REPS),
        "SPEARMAN_T": np.empty(BOOTSTRAP_REPS),
        "SPEARMAN_R": np.empty(BOOTSTRAP_REPS),
        "SPEARMAN_TR": np.empty(BOOTSTRAP_REPS),
        "HELP_IMPROVE_T": np.empty(BOOTSTRAP_REPS),
        "HELP_IMPROVE_R": np.empty(BOOTSTRAP_REPS),
        "HELP_IMPROVE_TR": np.empty(BOOTSTRAP_REPS),
        "HELP_WORSEN_T": np.empty(BOOTSTRAP_REPS),
        "HELP_WORSEN_R": np.empty(BOOTSTRAP_REPS),
        "HELP_WORSEN_TR": np.empty(BOOTSTRAP_REPS),
    }
    for rep_i in range(BOOTSTRAP_REPS):
        draws = rng.integers(0, n_groups_total, size=n_groups_total)
        wg = np.bincount(draws, minlength=n_groups_total).astype(np.float64)
        # linear group-level metrics
        def pooled_rate(num: np.ndarray) -> float:
            d = float(wg @ denom_g)
            return float(wg @ num) / d if d > 0 else 0.0

        furk = {m: pooled_rate(furk_g[m]) for m in METHODS}

        def pooled_rcj(a1_gv: np.ndarray, a2_gv: np.ndarray) -> float:
            a1 = float(wg @ a1_gv)
            a2 = float(wg @ a2_gv)
            return a2 / (a1 + a2) if (a1 + a2) > 0 else 0.0

        def pooled_rbr(a2_gv: np.ndarray) -> float:
            d = float(wg @ denom_g)
            return float(wg @ a2_gv) / d if d > 0 else 0.0

        rbr = {m: pooled_rbr(a2_g[m]) for m in METHODS}
        rcj = {m: pooled_rcj(a1_g[m], a2_g[m]) for m in METHODS}
        rep["FURK_N_TRAJ_MINUS_N_POST"][rep_i] = (
            furk["N_TRAJ"] - furk["N_POST"])
        rep["FURK_L_TRAJ_MINUS_L_POST"][rep_i] = (
            furk["L_TRAJ"] - furk["L_POST"])
        rep["FURK_N_TRAJ_MINUS_B1"][rep_i] = furk["N_TRAJ"] - furk["B1_UTILITY_POST_MSP"]
        rep["FURK_L_TRAJ_MINUS_B1"][rep_i] = furk["L_TRAJ"] - furk["B1_UTILITY_POST_MSP"]
        rep["FURK_N_TRAJ_MINUS_B0"][rep_i] = furk["N_TRAJ"] - furk["B0_BASIC_MSP"]
        rep["RBR_N_TRAJ_MINUS_N_POST"][rep_i] = rbr["N_TRAJ"] - rbr["N_POST"]
        rep["RBR_N_TRAJ_MINUS_B1"][rep_i] = (
            rbr["N_TRAJ"] - rbr["B1_UTILITY_POST_MSP"])
        rep["RCJ_N_TRAJ_MINUS_N_POST"][rep_i] = rcj["N_TRAJ"] - rcj["N_POST"]
        rep["RCJ_N_TRAJ_MINUS_B1"][rep_i] = (
            rcj["N_TRAJ"] - rcj["B1_UTILITY_POST_MSP"])

        # row-level weighted metrics on EVAL rows
        w_row = wg[group_pool]
        w_kn = w_row[known_ev]
        ua = {}
        for m in METHODS:
            ua[m] = weighted_auroc(scores[m], unknown_ev.astype(np.int64),
                                   w_row)
        rep["UNKNOWN_AUROC_N_TRAJ_MINUS_N_POST"][rep_i] = (
            ua["N_TRAJ"] - ua["N_POST"])
        rep["UNKNOWN_AUROC_N_TRAJ_MINUS_B0"][rep_i] = (
            ua["N_TRAJ"] - ua["B0_BASIC_MSP"])
        rec_n = weighted_recall(scores["N_TRAJ"], thr_by_row["N_TRAJ"],
                                unknown_ev, w_row)
        rec_p = weighted_recall(scores["N_POST"], thr_by_row["N_POST"],
                                unknown_ev, w_row)
        rec_b0 = weighted_recall(scores["B0_BASIC_MSP"],
                                 thr_by_row["B0_BASIC_MSP"], unknown_ev, w_row)
        rep["UNKNOWN_RECALL_N_TRAJ_MINUS_N_POST"][rep_i] = rec_n - rec_p
        rep["UNKNOWN_RECALL_N_TRAJ_MINUS_B0"][rep_i] = rec_n - rec_b0

        # signal AUROC on EVAL known
        for cap, post, traj in (("LINEAR", "L_POST", "L_TRAJ"),
                                ("NONLINEAR", "N_POST", "N_TRAJ")):
            a_post = weighted_auroc(paccept[post], accept_ev, w_kn)
            a_traj = weighted_auroc(paccept[traj], accept_ev, w_kn)
            rep[f"{cap}_DELTA_AUROC"][rep_i] = a_traj - a_post

        # Section 32: Spearman + HELP rates (EVAL known rows)
        for f in FAMILIES:
            sx = signed_pool[f]
            sy = nu_pool[f]
            s = weighted_spearman(sx, sy, w_kn)
            rep[f"SPEARMAN_{f}"][rep_i] = s
            hn = float(wg @ help_n_g[f])
            imp = float(wg @ help_imp_g[f]) / hn if hn > 0 else float("nan")
            wor = float(wg @ help_wor_g[f]) / hn if hn > 0 else float("nan")
            rep[f"HELP_IMPROVE_{f}"][rep_i] = imp
            rep[f"HELP_WORSEN_{f}"][rep_i] = wor

    def ci95(values: np.ndarray) -> list[float]:
        return [float(np.nanpercentile(values, 2.5)),
                float(np.nanpercentile(values, 97.5))]

    out = {"schema_version": BOOTSTRAP_SCHEMA, "reps": BOOTSTRAP_REPS,
           "unit": "private activity group, pooled over 3 rotations x 3 seeds",
           "paired": True}
    for key, values in rep.items():
        out[key] = {"mean": float(np.nanmean(values)),
                    "ci95": ci95(values)}
    return out


# ---------------------------------------------------------------------------
# Report assembly
# ---------------------------------------------------------------------------

def assemble_report(cells: list[dict[str, Any]], boot: dict[str, Any],
                    v2_protocol_sha256: str, git_head: str
                    ) -> dict[str, Any]:
    linear_deltas = delta_auroc_by_rotation(cells, "linear")
    nonlinear_deltas = delta_auroc_by_rotation(cells, "nonlinear")
    linear_status = level_signal_status(
        cells, "linear", boot["LINEAR_DELTA_AUROC"]["ci95"][0])
    nonlinear_status = level_signal_status(
        cells, "nonlinear", boot["NONLINEAR_DELTA_AUROC"]["ci95"][0])
    signal = recovery_trajectory_signal(linear_status, nonlinear_status,
                                        linear_deltas)
    transfer = transfer_status(cells, boot)
    e2e = end_to_end_status(cells, boot)
    case = interpret_case(signal, transfer, e2e, cells)

    per_rotation: dict[str, Any] = {}
    for r in ROTATIONS:
        per_rotation[r] = {
            "FURK": {m: rotation_mean(cells, r, "FURK", "metrics", m)
                     for m in METHODS},
            "RECOVERY_CONDITIONAL_REJECTION_RATE": {
                m: rotation_mean(cells, r,
                                 "RECOVERY_CONDITIONAL_REJECTION_RATE",
                                 "metrics", m) for m in METHODS},
            "RECOVERED_BUT_REJECTED_RATE": {
                m: rotation_mean(cells, r, "RECOVERED_BUT_REJECTED_RATE",
                                 "metrics", m) for m in METHODS},
            "UNKNOWN_AUROC": {m: rotation_mean(cells, r, "UNKNOWN_AUROC",
                                               "metrics", m)
                              for m in METHODS},
            "UNKNOWN_AUPR": {m: rotation_mean(cells, r, "UNKNOWN_AUPR",
                                              "metrics", m)
                             for m in METHODS},
            "UNKNOWN_RECALL_AT_CALIBRATED_FUR": {
                m: rotation_mean(cells, r,
                                 "UNKNOWN_RECALL_AT_CALIBRATED_FUR",
                                 "metrics", m) for m in METHODS},
            "KNOWN_FALSE_UNKNOWN_RATE": {
                m: rotation_mean(cells, r, "KNOWN_FALSE_UNKNOWN_RATE",
                                 "metrics", m) for m in METHODS},
            "SIGNAL_ACCEPT_AUROC": {
                p: rotation_mean(cells, r, "AUROC", "signal", p)
                for p in PROBES},
            "LINEAR_DELTA_AUROC": linear_deltas[r],
            "NONLINEAR_DELTA_AUROC": nonlinear_deltas[r],
            "P6_RECOVERY_RATE": rotation_mean(cells, r,
                                              "P6_RECOVERY_RATE"),
            "ROUTER_RECOVERY_HEADROOM": rotation_mean(
                cells, r, "ROUTER_RECOVERY_HEADROOM"),
            "INTERFACE_HEADROOM_PROXY": rotation_mean(
                cells, r, "INTERFACE_HEADROOM_PROXY"),
        }
        for fam in FAMILIES:
            per_rotation[r][f"SPEARMAN_{fam}"] = mean_of_util(
                cells, r, fam,
                "SPEARMAN_CLASSIFICATION_UTILITY_VS_NOVELTY_UTILITY")

    pooled: dict[str, Any] = {}
    for m in METHODS:
        pooled[m] = {**pooled_furk(cells, m),
                     **{k: v for k, v in pooled_a1a2(cells, m).items()}}
    # pooled unknown metrics: recompute from per-cell rows is done in
    # bootstrap; report pooled AUROC as mean of per-cell AUROC (no single
    # pooled row set is retained here).
    pooled["UNKNOWN_AUROC_MEAN_OF_CELLS"] = {
        m: pooled_metric(cells, "metrics", "UNKNOWN_AUROC", m) for m in METHODS}
    pooled["UNKNOWN_AUPR_MEAN_OF_CELLS"] = {
        m: pooled_metric(cells, "metrics", "UNKNOWN_AUPR", m) for m in METHODS}
    pooled["UNKNOWN_RECALL_MEAN_OF_CELLS"] = {
        m: pooled_metric(cells, "metrics",
                         "UNKNOWN_RECALL_AT_CALIBRATED_FUR", m) for m in METHODS}
    pooled["SIGNAL_ACCEPT_AUROC_MEAN_OF_CELLS"] = {
        p: pooled_metric(cells, "signal", "AUROC", p) for p in PROBES}

    return {
        "schema_version": OUT_SCHEMA,
        "date": "2026-08-17",
        "branch": "main",
        "head": git_head,
        "task": "RECOVERY_SIGNAL_CHARACTERIZATION_AND_OPEN_WORLD_TRANSFER_GATE_V2",
        "v2_protocol_status": "FROZEN_BEFORE_EVALUATION",
        "v2_protocol_sha256": v2_protocol_sha256,
        "seeds": list(SEEDS),
        "rotations": list(ROTATIONS),
        "frozen": {
            "V1_RESULT": "FAIL",
            "V1_RESULT_CHANGED": False,
            "GATE_1": "YELLOW", "GATE_1B": "PASS",
            "V1_FAILURE_ATTRIBUTION": "COMPLETE",
        },
        "signal": {
            "LINEAR_STATUS": linear_status,
            "NONLINEAR_STATUS": nonlinear_status,
            "RECOVERY_TRAJECTORY_SIGNAL": signal,
            "LINEAR_DELTA_AUROC_BY_ROTATION": linear_deltas,
            "NONLINEAR_DELTA_AUROC_BY_ROTATION": nonlinear_deltas,
        },
        "transfer": transfer,
        "end_to_end": e2e,
        "interpretation": case,
        "per_rotation": per_rotation,
        "pooled": pooled,
        "bootstrap": boot,
        "safety": {
            "FINAL_TEST_MODELING_CONTAMINATION": False,
            "TRUE_UNKNOWN_USED_FOR_PROBE_TRAINING": False,
            "TRUE_UNKNOWN_USED_FOR_THRESHOLD_CALIBRATION": False,
            "ROUTER_RETRAINED": False,
            "EVIDENCE_CONTRACT_CHANGED": False,
            "DETECTOR_SHOPPING": False,
            "POST_RESULT_THRESHOLD_TUNING": False,
            "QWEN_API_CALLS": 0, "DEEPSEEK_API_CALLS": 0,
            "MODEL_B_TRAINING_STARTED": False, "RL_TRAINING_STARTED": False,
            "CONTINUAL_TRAINING_STARTED": False,
            "UNKNOWN_CANDIDATE_PURIFICATION_STARTED": False,
        },
        "rl": {"RL_REQUIRED": False,
               "RL_SEQUENTIAL_DECISION_JUSTIFICATION": "PLAUSIBLE"},
        "methods": list(METHODS),
    }


def mean_of_util(cells: list[dict[str, Any]], rotation: str, family: str,
                 key: str) -> float:
    vals = [c["utility_correlation"][family][key] for c in cells
            if c["rotation"] == rotation]
    vals = [float(v) for v in vals if v is not None]
    return float(np.mean(vals)) if vals else float("nan")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="RECOVERY_SIGNAL_CHARACTERIZATION_AND_OPEN_WORLD_"
                    "TRANSFER_GATE_V2 (frozen)")
    parser.add_argument("--mode", choices=["smoke", "run"], required=True)
    parser.add_argument("--artifact-root", type=Path, required=True,
                        help="open_world_recoverability_gate_v1 root")
    parser.add_argument("--gate1-root", type=Path, required=True,
                        help="core_gate_v1 root")
    parser.add_argument("--out-root", type=Path, required=True,
                        help="V2 large-artifact root (not committed)")
    parser.add_argument("--report-root", type=Path, required=True,
                        help="reports/research_audit root")
    parser.add_argument("--protocol-sha256", type=str, default="",
                        help="frozen protocol sha256 (report echo)")
    args = parser.parse_args(argv)

    started = time.monotonic()
    cells: list[dict[str, Any]] = []
    for seed in SEEDS:
        for rotation in ROTATIONS:
            print(f"[v2 cell] seed={seed} rotation={rotation} ...")
            cell = run_cell(int(seed), rotation, args.artifact_root,
                            args.gate1_root, args.out_root,
                            smoke=(args.mode == "smoke"))
            cells.append(cell)
    boot = run_bootstrap(cells, args.artifact_root)

    if args.mode == "smoke":
        # integrity-only: print counts, never evaluation metrics
        for c in cells:
            print(f"[smoke] seed={c['seed']} rotation={c['rotation']} "
                  f"n_fit={c['n_fit']} n_calib_fit={c['n_calib_fit']} "
                  f"n_eval={c['n_eval']} split_ok="
                  f"{c['cross_verification'].get('UTILITY_MSP_MATCH')}")
        print("[smoke] bootstrap reps:", boot["reps"])
        return 0

    git_head = "unknown"
    try:
        import subprocess
        git_head = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"], capture_output=True,
            text=True, check=True).stdout.strip()
    except Exception:
        pass

    report = assemble_report(cells, boot, args.protocol_sha256, git_head)
    report_root = args.report_root
    report_root.mkdir(parents=True, exist_ok=True)
    (report_root / "recovery_signal_characterization_gate_v2.json").write_text(
        json.dumps(report, indent=1, allow_nan=True))
    (report_root / "recovery_signal_characterization_gate_v2.md").write_text(
        render_markdown(report))
    print(f"[v2] report written ({time.monotonic()-started:.1f}s)")
    return 0


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Recovery-Signal Characterization and Open-World Transfer Gate V2 — Report",
        "",
        f"Date: {report['date']}  |  Head: {report['head']}",
        f"Protocol: {report['v2_protocol_status']} (sha256 "
        f"{report['v2_protocol_sha256']})",
        "",
        "Frozen context: Gate 1 YELLOW, Gate 1B PASS, Open-World V1 FAIL "
        "(unchanged), V1 failure attribution COMPLETE.",
        "",
        "## Signal characterization",
        f"- LINEAR_SIGNAL = {report['signal']['LINEAR_STATUS']}",
        f"- NONLINEAR_SIGNAL = {report['signal']['NONLINEAR_STATUS']}",
        f"- RECOVERY_TRAJECTORY_SIGNAL = "
        f"{report['signal']['RECOVERY_TRAJECTORY_SIGNAL']}",
        "",
        "| rotation | linear ΔAUROC | nonlinear ΔAUROC |",
        "|---|---|---|",
    ]
    for r in report["rotations"]:
        s = report["signal"]
        lines.append(f"| {r} | {s['LINEAR_DELTA_AUROC_BY_ROTATION'][r]:+.4f} "
                     f"| {s['NONLINEAR_DELTA_AUROC_BY_ROTATION'][r]:+.4f} |")
    lines += [
        "",
        "## Open-world trajectory transfer",
        f"T1={report['transfer']['T1']} T2={report['transfer']['T2']} "
        f"T3={report['transfer']['T3']} T4={report['transfer']['T4']} "
        f"T5={report['transfer']['T5']} -> "
        f"OPEN_WORLD_TRAJECTORY_TRANSFER = "
        f"{'PASS' if report['transfer']['PASS'] else 'NOT_ESTABLISHED'}",
        "",
        "## End-to-end",
        f"E1={report['end_to_end']['E1']} E2={report['end_to_end']['E2']} "
        f"E3={report['end_to_end']['E3']} E4={report['end_to_end']['E4']} -> "
        f"END_TO_END_OPEN_WORLD_GAIN = "
        f"{'PASS' if report['end_to_end']['PASS'] else 'NOT_ESTABLISHED'}",
        "",
        "## Interpretation",
        f"CASE {report['interpretation']['CASE']}",
        f"C1_STATUS = {report['interpretation']['C1_STATUS']}",
        f"NEXT_PROPOSED_ACTION = {report['interpretation']['NEXT_PROPOSED_ACTION']}",
        "",
        "## Pooled FURK (weighted)",
        "",
        "| method | numerator | denominator | rate |",
        "|---|---|---|---|",
    ]
    for m in report["methods"]:
        p = report["pooled"][m]
        lines.append(f"| {m} | {p['NUMERATOR']} | {p['DENOMINATOR']} | "
                     f"{p['RATE']:.4f} |")
    lines += [
        "",
        "## Safety ledger",
        "",
        "All entries false / zero (see JSON report for the full ledger).",
        "",
        f"V2_RESULT_COMMITTED=false | V2_RESULT_PUSHED=false | "
        f"CURRENT_AUTHORIZED_TASK=NONE_WAITING_RESEARCHER | "
        f"NEXT_ACTION_AUTHORIZED=false",
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    sys.exit(main())
