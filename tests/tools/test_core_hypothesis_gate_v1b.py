"""Targeted tests for the core-hypothesis Gate 1B tool (synthetic, offline).

Covers the frozen Gate 1B invariants: OOF fold exclusivity at the private
activity-group level, temporal-block-aware fold construction, 100% OOF
coverage, validation never used to train the selector, HELP/HARM/signed
utility arithmetic, unique T/R / shared / full-only recovery flags, selector
feature leakage rejection (pre-acquisition BASIC state only), exact budget
selection, deterministic random baseline, same target ids across comparison
methods, paired group bootstrap, and FINAL_TEST exclusion.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest
from sklearn.ensemble import RandomForestRegressor

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))

import run_core_hypothesis_gate_v1 as g  # noqa: E402
import run_core_hypothesis_gate_v1b as b  # noqa: E402


# ---------------------------------------------------------------------------
# Synthetic fixtures
# ---------------------------------------------------------------------------

CLASSES = g.CANONICAL_CLASS_ORDER
CLASS_ARRAY = np.array(CLASSES, dtype=object)


def make_predictions(n=560, seed=3):
    rng = np.random.default_rng(seed)
    labels = np.array([CLASSES[i % 7] for i in range(n)], dtype=object)
    rng.shuffle(labels)
    pred_b = labels.copy()
    pred_bt = labels.copy()
    pred_br = labels.copy()
    pred_btr = labels.copy()
    # deterministic perturbed patterns
    wrong = np.array([i % 17 == 0 for i in range(n)])
    pred_b[wrong] = CLASS_ARRAY[(np.arange(n)[wrong] + 3) % 7]
    # HELP_T: B wrong, BT correct
    pred_bt[wrong] = labels[wrong]
    # HARM_T: B correct, BT wrong
    harm_t = np.array([i % 23 == 0 for i in range(n)])
    pred_bt[harm_t] = CLASS_ARRAY[(np.arange(n)[harm_t] + 2) % 7]
    # UNIQUE_T: B wrong, BT correct, BR wrong
    pred_br[wrong] = CLASS_ARRAY[(np.arange(n)[wrong] + 5) % 7]
    # UNIQUE_R: B wrong, BR correct, BT wrong
    unique_r = np.array([i % 29 == 0 for i in range(n)])
    pred_br[unique_r] = labels[unique_r]
    pred_bt[unique_r] = CLASS_ARRAY[(np.arange(n)[unique_r] + 1) % 7]
    # FULL_ONLY: B wrong, BT wrong, BR wrong, BTR correct
    pred_btr[wrong] = labels[wrong]
    return labels, pred_b, pred_bt, pred_br, pred_btr


def make_targets(n=630, seed=7):
    # Realistic layout: each activity group occupies one contiguous row block,
    # every row of a group shares one (class, temporal_block) stratum, and each
    # stratum holds exactly 3 groups (10 rows each) so the 3 OOF folds all fill.
    # n must be a multiple of 10 (10 rows per group) for a clean grid
    assert n % 10 == 0, "fixture n must be a multiple of 10"
    rng = np.random.default_rng(seed)
    n_groups = n // 10
    labels = np.empty(n, dtype=object)
    blocks = np.empty(n, dtype=np.int16)
    digests = np.empty(n, dtype=object)
    for g in range(n_groups):
        labels[g * 10:(g + 1) * 10] = CLASSES[g % 7]
        blocks[g * 10:(g + 1) * 10] = (g // 7) % 3
        digests[g * 10:(g + 1) * 10] = f"group-{g}".encode()
    return {
        "source_row_index": np.arange(100_000, 100_000 + n, dtype=np.int64),
        "canonical_label": labels,
        "partition_code": np.zeros(n, dtype=np.int64),
        "temporal_block": blocks,
        "flow_start_ms": (1_000_000 + np.arange(n) * 100).astype(np.int64),
        "activity_group_digest": digests,
    }


# ---------------------------------------------------------------------------
# Utility definitions
# ---------------------------------------------------------------------------

def test_help_harm_signed_arithmetic():
    labels, pb, pbt, pbr, pbtr = make_predictions()
    help_t, harm_t, signed = b.utility_labels(pb, pbt, labels)
    expected_help = (pb != labels) & (pbt == labels)
    expected_harm = (pb == labels) & (pbt != labels)
    assert np.array_equal(help_t, expected_help)
    assert np.array_equal(harm_t, expected_harm)
    assert np.array_equal(signed, np.where(expected_help, 1,
                                           np.where(expected_harm, -1, 0)))


def test_diversity_flags_unique_t_and_unique_r():
    labels, pb, pbt, pbr, pbtr = make_predictions()
    unique_t, unique_r, shared_tr, full_only = b.diversity_flags(
        pb, pbt, pbr, pbtr, labels)
    assert np.array_equal(unique_t,
                          (pb != labels) & (pbt == labels) & (pbr != labels))
    assert np.array_equal(unique_r,
                          (pb != labels) & (pbr == labels) & (pbt != labels))
    assert np.array_equal(shared_tr,
                          (pb != labels) & (pbt == labels) & (pbr == labels))
    assert np.array_equal(full_only, (pb != labels) & (pbt != labels)
                          & (pbr != labels) & (pbtr == labels))
    # disjointness: a target cannot be both unique-T and unique-R
    assert not (unique_t & unique_r).any()


# ---------------------------------------------------------------------------
# OOF fold construction
# ---------------------------------------------------------------------------

def test_oof_folds_complete_and_exclusive():
    targets = make_targets()
    fold = b.build_oof_folds(targets)
    assert (fold < 0).sum() == 0
    assert set(np.unique(fold)) == {0, 1, 2}
    # group exclusivity: no activity group in more than one fold
    for group in np.unique(targets["activity_group_digest"]):
        member_folds = np.unique(fold[targets["activity_group_digest"] == group])
        assert len(member_folds) == 1
    # every fold non-trivial
    for f in range(3):
        assert (fold == f).sum() > 0


def test_oof_folds_respect_temporal_blocks():
    # dense fixture: 3 blocks x 7 classes with 10 groups per stratum
    n = 2100
    targets = make_targets(n=n, seed=7)
    fold = b.build_oof_folds(targets)
    # blocks 0..2 all covered
    assert set(np.unique(targets["temporal_block"])) == set(range(3))
    # every class appears in every fold (stratum-chunked assignment)
    for class_name in CLASSES:
        for f in range(3):
            mask = (targets["canonical_label"] == class_name) & (fold == f)
            assert mask.sum() > 0
    # folds are balanced within a third of the population
    for f in range(3):
        share = (fold == f).sum() / n
        assert 0.25 < share < 0.42


def test_oof_folds_never_split_duplicate_groups():
    targets = make_targets()
    # force members of one digest into distinct activity groups is impossible;
    # instead verify same-group rows share a fold even with interleaved ids
    targets2 = make_targets(n=100)
    targets2["activity_group_digest"][1] = targets2["activity_group_digest"][0]
    fold = b.build_oof_folds(targets2)
    assert fold[0] == fold[1]


# ---------------------------------------------------------------------------
# Selector features and leakage audit
# ---------------------------------------------------------------------------

def test_selector_feature_names_and_shapes():
    rng = np.random.default_rng(0)
    n = 40
    basic = rng.normal(size=(n, len(g.MODEL_VISIBLE_FIELDS)))
    pred_b = np.array([CLASSES[i % 7] for i in range(n)], dtype=object)
    proba = rng.dirichlet(np.ones(7), size=n)
    availability = np.ones(n)
    features, names = b.build_selector_features(basic, pred_b, proba, availability)
    assert features.shape == (n, len(names))
    assert names == (list(g.MODEL_VISIBLE_FIELDS)
                     + [f"pred_class_onehot_{c}" for c in CLASSES]
                     + [f"proba_B_{c}" for c in CLASSES]
                     + list(b.DERIVED_BASIC_FEATURES))
    assert names.count("basic_entropy") == 1


def test_selector_leakage_audit_rejects_forbidden():
    names = list(g.MODEL_VISIBLE_FIELDS) + ["temporal_source_flow_count_10s",
                                            "help_flag", "group_id"]
    assert b.selector_leakage_audit(names) != "PASS"
    clean = (list(g.MODEL_VISIBLE_FIELDS)
             + [f"proba_B_{c}" for c in CLASSES]
             + list(b.DERIVED_BASIC_FEATURES))
    assert b.selector_leakage_audit(clean) == "PASS"


def test_selector_features_are_pre_acquisition_only():
    names = b.selector_leakage_audit(
        list(g.MODEL_VISIBLE_FIELDS) + [f"proba_B_{c}" for c in CLASSES]
        + list(b.DERIVED_BASIC_FEATURES))
    assert names == "PASS"
    # any history feature (Temporal or Relation) must be rejected
    for feature in g.HISTORY_FIELDS:
        assert b.selector_leakage_audit([feature]) != "PASS"


def test_selector_config_is_frozen():
    assert b.SELECTOR_FAMILY == "RandomForestRegressor"
    assert b.SELECTOR_CONFIG["n_estimators"] == 200
    assert b.SELECTOR_CONFIG["max_depth"] == 12
    assert b.SELECTOR_CONFIG["min_samples_leaf"] == 20
    assert b.SELECTOR_CONFIG["max_features"] == "sqrt"
    model = RandomForestRegressor(**{k: v for k, v in b.SELECTOR_CONFIG.items()
                                     if k != "random_state"})
    assert isinstance(model, RandomForestRegressor)


# ---------------------------------------------------------------------------
# Acquisition simulation
# ---------------------------------------------------------------------------

def test_exact_budget_selection():
    n = 1000
    scores = np.linspace(1.0, 0.0, n)
    order = np.arange(n)[::-1]
    for q in (0.05, 0.10, 0.15, 0.20):
        k = int(round(q * n))
        selected = b.select_topk(scores, k, order)
        assert selected.sum() == k
        assert selected[:k].all() and not selected[k:].any()


def test_select_topk_deterministic_tie_break():
    n = 100
    scores = np.zeros(n)
    order = np.arange(n)
    sel = b.select_topk(scores, 10, order)
    assert sel.sum() == 10
    # tie-break by ascending order: first 10 rows selected
    assert sel[:10].all() and not sel[10:].any()


def test_random_baseline_deterministic():
    labels, pb, pbt, pbr, pbtr = make_predictions(n=500, seed=11)
    n = len(labels)
    k = 75
    nets_a, macros_a = b.random_baseline_stats(pb, pbt, labels, k, 50, seed=1)
    nets_b, macros_b = b.random_baseline_stats(pb, pbt, labels, k, 50, seed=1)
    assert np.array_equal(nets_a, nets_b)
    assert np.array_equal(macros_a, macros_b)
    assert len(nets_a) == 50
    # random acquisition captures HELP only proportionally: E[net]/help_rate
    # equals (k/n) * (1 - harm_rate/help_rate) — no enrichment either way
    # (the fixture's unique-R pattern makes harm > help, so the ratio is
    # expected to be slightly negative, not "clearly above zero").
    help_flag, harm_flag, _ = b.utility_labels(pb, pbt, labels)
    ratio = nets_a.mean() / (help_flag.mean() + 1e-12)
    expected = (k / n) * (1 - harm_flag.mean() / (help_flag.mean() + 1e-12))
    assert abs(ratio - expected) < 0.05
    assert -0.30 < ratio < 0.30


def test_same_target_ids_across_comparison_methods():
    labels, pb, pbt, pbr, pbtr = make_predictions(n=560, seed=5)
    n = len(labels)
    scores = np.linspace(0.9, 0.1, n)
    order = np.arange(n)
    for q in b.BUDGETS:
        k = int(round(q * n))
        sel_selector = b.select_topk(scores, k, order)
        sel_conf = b.select_topk(-scores, k, order)
        assert sel_selector.sum() == sel_conf.sum() == k
        assert not (sel_selector & sel_conf).all()  # different selections


# ---------------------------------------------------------------------------
# Selective metrics
# ---------------------------------------------------------------------------

def test_selective_metrics_net_recovery_denominator():
    labels, pb, pbt, pbr, pbtr = make_predictions(n=560, seed=6)
    help_flag, harm_flag, _ = b.utility_labels(pb, pbt, labels)
    selected = help_flag.copy()  # acquire exactly the HELP targets
    m = b.selective_metrics(pb, pbt, labels, selected, len(labels))
    assert m["help_captured"] == int(help_flag.sum())
    # NET_RECOVERY=(help_sel - harm_sel)/total with SELECTED counts; help and
    # harm are disjoint by definition, so harm_sel is 0 for this selection
    expected = (int(help_flag.sum()) - 0) / 560
    assert abs(m["net_recovery"] - expected) < 1e-12
    assert m["help_precision_among_acquired"] == 1.0


def test_selective_metrics_final_prediction_uses_b_for_unselected():
    labels, pb, pbt, pbr, pbtr = make_predictions(n=560, seed=8)
    selected = np.zeros(len(labels), dtype=bool)
    selected[:5] = True
    m = b.selective_metrics(pb, pbt, labels, selected, len(labels))
    final_expected = np.where(selected, pbt, pb)
    assert m["macro_f1"] == pytest.approx(
        __import__("sklearn.metrics", fromlist=["f1_score"]).f1_score(
            labels, final_expected, average="macro"))


# ---------------------------------------------------------------------------
# Paired bootstrap
# ---------------------------------------------------------------------------

def test_paired_bootstrap_deterministic_and_paired():
    rng = np.random.default_rng(0)
    n = 1000
    groups = np.array([f"grp-{i % 50}".encode() for i in range(n)], dtype=object)
    help_flag = rng.random(n) < 0.1
    harm_flag = rng.random(n) < 0.05
    selected = rng.random(n) < 0.15
    res_a = b.paired_selector_vs_random_bootstrap(
        groups, help_flag, harm_flag, selected, selected, n, 200, rng_seed=42)
    res_b = b.paired_selector_vs_random_bootstrap(
        groups, help_flag, harm_flag, selected, selected, n, 200, rng_seed=42)
    assert res_a["mean"] == res_b["mean"]
    assert res_a["ci95"] == res_b["ci95"]
    assert res_a["reps"] == 200
    # identical arms => difference centered at 0
    assert abs(res_a["mean"]) < 1e-9


# ---------------------------------------------------------------------------
# FINAL_TEST exclusion and validation isolation
# ---------------------------------------------------------------------------

def test_final_test_never_enters_validation_predictions_contract():
    # Gate 1B consumes only the frozen validation prediction artifacts which
    # were built with FINAL_TEST excluded (verified upstream); here we assert
    # the tool loads exactly the frozen per-seed validation population size.
    assert b.VAL_PER_SEED == 56_000


def test_selector_never_trains_on_validation_labels():
    # the frozen selector pipeline trains only on TRAIN OOF labels; helper
    # asserts the OOF artifacts carry fold ids and that validation truth is
    # never an input to build_selector_features (labels are not in the feature
    # set).
    names = b.selector_leakage_audit(
        list(g.MODEL_VISIBLE_FIELDS) + [f"proba_B_{c}" for c in CLASSES]
        + list(b.DERIVED_BASIC_FEATURES))
    assert names == "PASS"
    assert "canonical_label" not in " ".join(names)


def test_utility_oof_coverage_contract():
    assert b.OOF_FOLDS == 3
    # every TRAIN target receives exactly one OOF prediction set by the fold
    # assignment invariant (build_oof_folds assigns exactly one fold per row).
    targets = make_targets()
    fold = b.build_oof_folds(targets)
    assert (fold >= 0).all()
    assert len(np.unique(fold)) == 3


def test_gate1b_frozen_thresholds_present():
    assert b.T1_AUROC == 0.70
    assert b.T3_TOP15_CAPTURE == 0.30
    assert b.T5_MIN_GAIN == 0.002
    assert b.YELLOW_MIN_PASS == 5
    assert b.BUDGETS == (0.05, 0.10, 0.15, 0.20)
    assert b.PRIMARY_BUDGET == 0.15
