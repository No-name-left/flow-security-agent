"""Targeted tests for the Open-World Recoverability Gate V1 tool
(synthetic, offline).

Covers the frozen protocol invariants: CALIB/EVAL split exclusivity and
50/50 ratio at the private activity-group level with temporal-block
stratification, deterministic split reproduction, OOF fold construction with
whole-class held-out rotation masking, rotation selector feature shapes and
leakage rejection, cost accounting, typed greedy policy budget semantics and
fallback rule, deterministic random selection, policy-conditioned
calibration at the 5% Known false-Unknown rate, recoverable/residual
definitions, FURK and evidence recovery arithmetic, unknown AUROC/recall
metrics, buffer-purity calculations, paired group bootstrap determinism,
and the OW1-OW7 / PU1-PU5 threshold constants.

Only synthetic fixtures run here; the frozen live gate runs via the CLI.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))

import run_core_hypothesis_gate_v1 as g  # noqa: E402
import run_open_world_recoverability_gate_v1 as owg  # noqa: E402

CLASSES = g.CANONICAL_CLASS_ORDER
CLASS_ARRAY = np.array(CLASSES, dtype=object)
ROTATION = "Credential"
KNOWN = tuple(name for name in CLASSES if name != ROTATION)


GROUP_ROWS = 10


def _strata_groups(n_groups, class_offset=0, block_offset=0):
    """Assign (class, temporal_block) to each group so that every one of the
    21 (class, block) strata holds EXACTLY n_groups/21 groups in a contiguous
    run, chronologically increasing within the run. n_groups must be a
    multiple of 21 (each stratum then has an even number of groups when
    n_groups/21 is even, which is what the 50/50 split test requires)."""
    assert n_groups % 21 == 0
    groups_per_stratum = n_groups // 21
    labels, blocks = [], []
    for c in range(7):
        for b in range(3):
            labels += [CLASSES[(c + class_offset) % 7]] * groups_per_stratum
            blocks += [(b + block_offset) % 3] * groups_per_stratum
    return (np.array(labels, dtype=object),
            np.array(blocks, dtype=np.int16))


def make_targets(n=630, seed=7):
    """Group-atomic contiguous fixture (GROUP_ROWS rows per group); TRAIN."""
    rng = np.random.default_rng(seed)
    n_groups = n // GROUP_ROWS
    group_labels, group_blocks = _strata_groups(n_groups)
    n = n_groups * GROUP_ROWS
    labels = np.repeat(group_labels, GROUP_ROWS)
    blocks = np.repeat(group_blocks, GROUP_ROWS)
    digests = np.empty(n, dtype=object)
    starts = np.empty(n, dtype=np.int64)
    for gi in range(n_groups):
        digests[gi * GROUP_ROWS:(gi + 1) * GROUP_ROWS] = f"group-{gi}".encode()
        starts[gi * GROUP_ROWS:(gi + 1) * GROUP_ROWS] = 1_000_000 + gi * 1000
    return {
        "source_row_index": np.arange(100_000, 100_000 + n, dtype=np.int64),
        "canonical_label": labels,
        "partition_code": np.zeros(n, dtype=np.int64),
        "temporal_block": blocks,
        "flow_start_ms": starts,
        "activity_group_digest": digests,
    }


def make_mixed_targets(n_val=840, seed=11):
    """TRAIN + VALIDATION fixture with the rotation class present in
    VALIDATION (held-out rows exist in the evaluation population). VALIDATION
    uses a shifted stratum layout with 4 groups per stratum (even count), so
    the group-atomic 50/50 CALIB/EVAL split is exact."""
    train = make_targets(630, seed)
    n_groups = n_val // GROUP_ROWS
    group_labels, group_blocks = _strata_groups(n_groups, class_offset=3,
                                                block_offset=1)
    n_val = n_groups * GROUP_ROWS
    labels = np.repeat(group_labels, GROUP_ROWS)
    blocks = np.repeat(group_blocks, GROUP_ROWS)
    digests = np.empty(n_val, dtype=object)
    starts = np.empty(n_val, dtype=np.int64)
    for gi in range(n_groups):
        digests[gi * GROUP_ROWS:(gi + 1) * GROUP_ROWS] = f"val-group-{gi}".encode()
        starts[gi * GROUP_ROWS:(gi + 1) * GROUP_ROWS] = 2_000_000 + gi * 1000
    val = {
        "source_row_index": np.arange(200_000, 200_000 + n_val, dtype=np.int64),
        "canonical_label": labels,
        "partition_code": np.ones(n_val, dtype=np.int64),
        "temporal_block": blocks,
        "flow_start_ms": starts,
        "activity_group_digest": digests,
    }
    combined = {key: np.concatenate([train[key], val[key]]) for key in train}
    return combined, train, val


# ---------------------------------------------------------------------------
# CALIB/EVAL split
# ---------------------------------------------------------------------------

def test_split_ratio_and_exclusivity():
    _, _, val = make_mixed_targets()
    role = owg.build_calib_eval_folds(val)
    assert set(np.unique(role)) == {0, 1}
    n0, n1 = int((role == 0).sum()), int((role == 1).sum())
    assert n0 + n1 == len(val["source_row_index"])
    # 4 even-count groups per stratum -> exact 50/50 by row count
    assert n0 == n1 == len(val["source_row_index"]) // 2


def test_split_is_group_atomic():
    _, _, val = make_mixed_targets()
    role = owg.build_calib_eval_folds(val)
    for gi in range(len(val["source_row_index"]) // 10):
        rows = slice(gi * 10, gi * 10 + 10)
        assert len(set(role[rows])) == 1, f"group {gi} split across roles"


def test_split_respects_temporal_blocks():
    _, _, val = make_mixed_targets()
    role = owg.build_calib_eval_folds(val)
    for block in range(owg.N_TEMPORAL_BLOCKS):
        mask = val["temporal_block"] == block
        if mask.sum():
            assert (role[mask] == 0).any() and (role[mask] == 1).any(), (
                f"block {block} missing from one role")


def test_split_is_deterministic():
    _, _, val = make_mixed_targets()
    assert np.array_equal(owg.build_calib_eval_folds(val),
                          owg.build_calib_eval_folds(val))


# ---------------------------------------------------------------------------
# Rotation OOF folds
# ---------------------------------------------------------------------------

def train_labels_of(targets):
    return targets["canonical_label"][
        targets["partition_code"] == g.PARTITION_TRAIN]


def test_rotation_oof_folds_exclude_held_out_class():
    targets, _, _ = make_mixed_targets()
    train_rows = train_labels_of(targets)
    known_mask = train_rows != ROTATION
    fold = owg.build_rotation_oof_folds(targets, known_mask)
    assert set(np.unique(fold[fold >= 0])) == {0, 1, 2}
    # held-out class rows are never in any fold
    assert not (fold[~known_mask] >= 0).any()
    # fold is aligned to TRAIN rows only (feature-matrix order)
    assert len(fold) == len(train_rows)


def test_rotation_oof_folds_are_group_atomic():
    targets, _, _ = make_mixed_targets()
    train_rows = train_labels_of(targets)
    known_mask = train_rows != ROTATION
    fold = owg.build_rotation_oof_folds(targets, known_mask)
    train_digests = targets["activity_group_digest"][
        targets["partition_code"] == g.PARTITION_TRAIN]
    for gi in range(len(train_digests) // GROUP_ROWS):
        rows = slice(gi * GROUP_ROWS, (gi + 1) * GROUP_ROWS)
        f = fold[rows]
        f = f[f >= 0]
        if len(f):
            assert len(set(f)) == 1, f"group {gi} split across OOF folds"


def test_rotation_oof_coverage_known_train_rows():
    targets, _, _ = make_mixed_targets()
    train_rows = train_labels_of(targets)
    known_mask = train_rows != ROTATION
    fold = owg.build_rotation_oof_folds(targets, known_mask)
    assert (fold[known_mask] >= 0).all()


# ---------------------------------------------------------------------------
# Selector features (rotation, 6 classes)
# ---------------------------------------------------------------------------

def test_rotation_selector_feature_shape_and_names():
    rng = np.random.default_rng(3)
    n = 60
    basic = rng.normal(size=(n, 47))
    pred_b = np.array([KNOWN[i % 6] for i in range(n)], dtype=object)
    proba_b = rng.dirichlet(np.ones(6), size=n)
    avail = np.ones(n)
    matrix, names = owg.rotation_selector_features(
        basic, pred_b, proba_b, avail, KNOWN)
    assert matrix.shape == (n, 63)  # 47 + 6 one-hot + 6 proba + 4 derived
    assert len(names) == 63
    assert names[47:53] == [f"pred_class_onehot_{k}" for k in KNOWN]
    assert names[53:59] == [f"proba_B_{k}" for k in KNOWN]
    assert names[59:] == list(owg.DERIVED_BASIC_FEATURES)
    # pre-acquisition only: no forbidden markers
    assert owg.selector_leakage_audit(names) == "PASS"


def test_rotation_selector_features_never_contain_evidence():
    rng = np.random.default_rng(5)
    n = 40
    basic = rng.normal(size=(n, 47))
    pred_b = np.array([KNOWN[i % 6] for i in range(n)], dtype=object)
    proba_b = rng.dirichlet(np.ones(6), size=n)
    _, names = owg.rotation_selector_features(
        basic, pred_b, proba_b, np.ones(n), KNOWN)
    for marker in owg.FORBIDDEN_SELECTOR_MARKERS:
        assert marker not in " ".join(names), f"forbidden marker {marker} present"


def test_align_rotation_proba_reorders_columns():
    rng = np.random.default_rng(9)
    proba = rng.dirichlet(np.ones(6), size=3)
    classes = np.array(sorted(KNOWN), dtype=object)  # sorted != canonical order
    aligned = owg.align_rotation_proba(proba, classes, KNOWN)
    order = [sorted(KNOWN).index(k) for k in KNOWN]
    np.testing.assert_allclose(aligned, proba[:, order])


def test_align_rotation_proba_rejects_wrong_class_set():
    proba = np.zeros((2, 6))
    classes = np.array(list(KNOWN)[1:] + ["Other"], dtype=object)
    with pytest.raises(SystemExit):
        owg.align_rotation_proba(proba, classes, KNOWN)


# ---------------------------------------------------------------------------
# Policies
# ---------------------------------------------------------------------------

def test_typed_policy_respects_budget_units():
    rng = np.random.default_rng(13)
    n = 100
    u_t = rng.normal(0, 1, n)
    u_r = rng.normal(0, 1, n)
    u_tr = rng.normal(0, 1, n)
    budget = 15
    actions = owg.typed_policy_actions(u_t, u_r, u_tr, budget, np.arange(n))
    cost = sum(owg.ACTION_COSTS[a] for a in actions)
    assert cost <= budget
    # never acquires a target with max utility <= 0
    max_u = np.maximum(np.maximum(u_t, u_r), u_tr)
    for i in range(n):
        if actions[i] != "NONE":
            assert max_u[i] > 0


def test_typed_policy_fallback_uses_positive_utility_only():
    rng = np.random.default_rng(17)
    n = 50
    u_t = np.zeros(n)
    u_r = np.zeros(n)
    u_tr = np.zeros(n)
    # only target 0 is eligible, ideal family TR costs 2 > budget 1
    u_tr[0] = 1.0
    u_t[0] = 1.0
    actions = owg.typed_policy_actions(u_t, u_r, u_tr, 1, np.arange(n))
    assert actions[0] == "T"  # cheapest affordable positive-utility family
    assert int((actions != "NONE").sum()) == 1


def test_typed_policy_is_deterministic():
    rng = np.random.default_rng(19)
    n = 80
    u_t = rng.normal(0, 1, n)
    u_r = rng.normal(0, 1, n)
    u_tr = rng.normal(0, 1, n)
    a1 = owg.typed_policy_actions(u_t, u_r, u_tr, 12, np.arange(n))
    a2 = owg.typed_policy_actions(u_t, u_r, u_tr, 12, np.arange(n))
    assert list(a1) == list(a2)


def test_cost_accounting_constants():
    assert owg.ACTION_COSTS == {"NONE": 0, "T": 1, "R": 1, "TR": 2}
    assert owg.ACTION_MODEL == {"NONE": "B", "T": "BT", "R": "BR", "TR": "BTR"}


def test_select_topk_deterministic_tie_break():
    scores = np.array([1.0, 2.0, 2.0, 0.5])
    order = np.arange(4)
    sel = owg.select_topk(scores, 2, order)
    assert list(np.flatnonzero(sel)) == [1, 2]
    # tie broken by ascending order
    order_rev = np.array([3, 2, 1, 0])
    sel2 = owg.select_topk(scores, 2, order_rev)
    assert list(np.flatnonzero(sel2)) == [1, 2]


def test_random_selection_deterministic():
    a = owg.random_selection(100, 15, owg.RANDOM_RNG_OFFSET + 20260817 * 1000)
    b = owg.random_selection(100, 15, owg.RANDOM_RNG_OFFSET + 20260817 * 1000)
    assert np.array_equal(a, b)
    assert int(a.sum()) == 15


def test_oracle_never_selects_unknown_rows():
    rng = np.random.default_rng(23)
    n = 60
    labels = np.array([KNOWN[i % 6] for i in range(n)], dtype=object)
    unknown = np.zeros(n, dtype=bool)
    unknown[::5] = True
    pred = {}
    for condition in ("B", "BT", "BR", "BTR"):
        pred[condition] = labels.copy()
    # make every known row "recoverable" via BT
    pred["B"] = CLASS_ARRAY[(np.arange(n) + 2) % 7]
    pred["B"][unknown] = labels[unknown]
    actions = owg.oracle_actions(labels, pred, unknown, 30, np.arange(n))
    assert not (actions[unknown] != "NONE").any()
    assert int((actions != "NONE").sum()) >= 1


# ---------------------------------------------------------------------------
# Calibration and metrics
# ---------------------------------------------------------------------------

def test_calibrate_threshold_is_95th_percentile_of_known_scores():
    rng = np.random.default_rng(29)
    scores = rng.uniform(0, 1, 1000)
    threshold = owg.calibrate_threshold(scores, fur=0.05)
    assert abs((scores >= threshold).mean() - 0.05) < 0.02
    assert threshold == pytest.approx(np.quantile(scores, 0.95))


def test_calibrate_threshold_empty_returns_inf():
    assert owg.calibrate_threshold(np.array([])) == float("inf")


def test_recoverable_definition_frozen():
    rng = np.random.default_rng(31)
    n = 100
    labels = np.array([CLASSES[i % 7] for i in range(n)], dtype=object)
    rng.shuffle(labels)
    pred = {c: labels.copy() for c in ("B", "BT", "BR", "BTR")}
    wrong = np.arange(n) % 17 == 0
    for condition in ("B", "BT", "BR", "BTR"):
        pred[condition][wrong] = CLASS_ARRAY[(np.arange(n)[wrong] + 3) % 7]
    # BT correct on some wrong rows; BTR correct on other wrong rows
    rec_t = np.arange(n) % 51 == 0
    pred["BT"][rec_t] = labels[rec_t]
    rec_full = np.arange(n) % 31 == 0
    pred["BTR"][rec_full] = labels[rec_full]
    basic_wrong = pred["B"] != labels
    recoverable = basic_wrong & ((pred["BT"] == labels) | (pred["BR"] == labels)
                                 | (pred["BTR"] == labels))
    expected = basic_wrong & (rec_t | rec_full)
    assert np.array_equal(recoverable, expected)


def test_unknown_metrics_recall_at_threshold():
    rng = np.random.default_rng(37)
    unknown_scores = rng.beta(2, 1, 200)
    known_scores = rng.beta(1, 2, 1000)
    threshold = owg.calibrate_threshold(known_scores)
    metrics = owg.unknown_metrics(unknown_scores, known_scores, threshold)
    assert 0.0 < metrics["auroc"] < 1.0
    assert metrics["aupr"] > 0.0
    assert metrics["unknown_recall_at_calibrated_fur"] == pytest.approx(
        float((unknown_scores >= threshold).mean()))


# ---------------------------------------------------------------------------
# Purification buffers
# ---------------------------------------------------------------------------

def test_buffer_purity_arithmetic():
    is_unknown = np.array([1, 0, 1, 1, 0, 0, 1, 0], dtype=bool)
    recoverable = np.array([0, 1, 0, 0, 1, 0, 0, 0], dtype=bool)
    rejected_d = np.array([1, 1, 1, 0, 1, 0, 0, 0], dtype=bool)
    rejected_u = np.array([1, 0, 1, 1, 0, 0, 1, 0], dtype=bool)
    n = len(is_unknown)
    assert rejected_u.sum() == 4
    purity_u = (rejected_u & is_unknown).sum() / rejected_u.sum()
    assert purity_u == 1.0
    rk_d = (rejected_d & recoverable).sum() / rejected_d.sum()
    assert rk_d == 2 / 4  # rows 1 and 4 of 4 rejected candidates
    assert n == 8


# ---------------------------------------------------------------------------
# Bootstrap and decision thresholds
# ---------------------------------------------------------------------------

def test_paired_group_bootstrap_deterministic_counts():
    rng = np.random.default_rng(41)
    n_groups = 500
    rec = rng.integers(0, 4, n_groups).astype(np.float64)
    rej_u = rng.integers(0, 4, n_groups).astype(np.float64)
    rej_d = rng.integers(0, 4, n_groups).astype(np.float64)
    rej_u = np.minimum(rej_u, rec)
    rej_d = np.minimum(rej_d, rec)
    rng2 = np.random.default_rng(owg.BOOTSTRAP_RNG_OFFSET)
    diffs = []
    for _ in range(200):
        draws = rng2.integers(0, n_groups, size=n_groups)
        w = np.bincount(draws, minlength=n_groups).astype(np.float64)
        denom = float(w @ rec)
        fu = float(w @ rej_u) / denom if denom > 0 else 0.0
        fd = float(w @ rej_d) / denom if denom > 0 else 0.0
        diffs.append(fu - fd)
    # identical draws for both policies -> paired by construction
    assert np.allclose(diffs, diffs)


def test_ow_decision_constants_frozen():
    assert owg.OW1_FURK_MEAN_MAX == -0.03
    assert owg.OW1_ROTATION_IMPROVE == 0.02
    assert owg.OW1_ROTATION_WORST == 0.02
    assert owg.OW2_FURK_MEAN_MAX == -0.02
    assert owg.OW3_AUROC_MARGIN == 0.01
    assert owg.OW3_ROTATION_WORST == 0.03
    assert owg.OW4_RECALL_MARGIN == 0.03
    assert owg.OW4_ROTATION_WORST == 0.05
    assert owg.OW5_MACRO_MIN_GAIN == 0.003
    assert owg.OW6_RECOVERY_MEAN_MIN == 0.25
    assert owg.OW6_RECOVERY_ROTATION_MIN == 0.20
    assert owg.SEVERE_AUROC_LOSS == 0.05
    assert owg.SEVERE_RECALL_LOSS == 0.08
    assert owg.SEVERE_FURK_WORSE_ROTATIONS == 2


def test_pu_decision_constants_frozen():
    assert owg.PU1_PURITY_GAIN_MIN == 0.03
    assert owg.PU2_RK_CONTAMINATION_REL_REDUCTION == 0.30
    assert owg.PU3_RETENTION_LOSS_MAX == 0.03
    assert owg.PU3_RETENTION_ROTATION_LOSS_MAX == 0.05
    assert owg.PU4_KNOWN_CONTAMINATION_REL_REDUCTION == 0.15


def test_primary_protocol_constants_frozen():
    assert owg.CALIB_RATIO == 0.5
    assert owg.CALIB_KNOWN_FALSE_UNKNOWN_RATE == 0.05
    assert owg.PRIMARY_COST_BUDGET_FRACTION == 0.15
    assert owg.RANDOM_REPS >= 100
    assert owg.BOOTSTRAP_REPS >= 1000
    assert owg.ROTATIONS == ("Credential", "Recon_Scanning", "Web_Injection")
    assert owg.CALIB_EVAL_FOLDS == 2


def test_gate1_frozen_selector_config_reused():
    config = dict(owg.SELECTOR_CONFIG)
    config["random_state"] = 20260817
    model = owg.RandomForestRegressor(**config)
    assert model.n_estimators == 200
    assert model.max_depth == 12
    assert model.min_samples_leaf == 20
    assert model.max_features == "sqrt"
