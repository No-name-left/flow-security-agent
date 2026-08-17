"""Targeted tests for the core-hypothesis Gate 0/1 tool (synthetic, offline).

Covers the frozen Gate invariants: duplicate representative determinism,
no duplicate-group repetition in the target view, evidence history not
deduplicated, strict past-only evidence, no cross-split history leakage,
FINAL_TEST exclusion from modeling arrays, forbidden-feature rejection,
identical target ids across B/BT/BR/BTR, recoverability/harm arithmetic,
seed reproducibility, and bootstrap pairing.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest
from sklearn.metrics import f1_score

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))

import run_core_hypothesis_gate_v1 as g  # noqa: E402


# ---------------------------------------------------------------------------
# Synthetic fixtures
# ---------------------------------------------------------------------------

def make_arrays(n=60):
    rng = np.random.default_rng(7)
    digests = np.array([f"digest-{i // 4}".encode() for i in range(n)], dtype=object)
    labels = np.array(
        [g.CANONICAL_CLASS_ORDER[i % 7] for i in range(n)], dtype=object)
    # force a label conflict inside one duplicate group to test conflict detection
    digests[4] = b"digest-0"
    labels[4] = "Benign"  # digest-0 members otherwise share label by construction
    arrays = {
        "source_row_index": np.arange(n, dtype=np.int64),
        "canonical_row_digest": digests,
        "canonical_label": labels,
        "flow_start_ms": (rng.integers(100_000, 200_000, n)).astype(np.int64),
        "flow_end_ms": None,
        "src_code": (rng.integers(1, 9, n)).astype(np.int64),
        "dst_code": (rng.integers(10, 18, n)).astype(np.int64),
        "src_port": rng.integers(1000, 9999, n).astype(np.int64),
        "dst_port": rng.integers(1000, 9999, n).astype(np.int64),
        "in_bytes": rng.integers(0, 1000, n).astype(np.int64),
        "out_bytes": rng.integers(0, 1000, n).astype(np.int64),
        "in_pkts": rng.integers(0, 20, n).astype(np.int64),
        "out_pkts": rng.integers(0, 20, n).astype(np.int64),
        "activity_group_digest": np.array(
            [f"group-{i % 9}".encode() for i in range(n)], dtype=object),
        "partition_code": np.array([i % 3 for i in range(n)], dtype=np.int64),
        "critical_valid": np.ones(n, dtype=bool),
        "target_eligible": np.ones(n, dtype=bool),
    }
    starts = arrays["flow_start_ms"].copy()
    arrays["flow_end_ms"] = starts + rng.integers(1, 500, n).astype(np.int64)
    return arrays


def test_verify_duplicate_semantics_counts_and_conflicts():
    rng = np.random.default_rng(0)
    digests = np.array([f"d-{i // 5}".encode() for i in range(40)], dtype=object)
    labels = np.array(["Benign"] * 40, dtype=object)
    groups, copies, conflicts = g.verify_duplicate_semantics(digests, labels)
    assert groups == 8
    assert copies == 32
    assert conflicts == 0
    labels[9] = "DDoS"  # conflict inside d-1
    _, _, conflicts = g.verify_duplicate_semantics(digests, labels)
    assert conflicts == 1


def test_duplicate_representative_rule_deterministic():
    arrays = make_arrays(48)
    arrays["partition_code"] = np.zeros(48, dtype=np.int64)
    # group members: earliest start wins; ties broken by min source_row_index
    reps, _ = g.duplicate_representatives(arrays, 0)
    seen = set()
    for position in reps:
        digest = arrays["canonical_row_digest"][position]
        assert digest not in seen
        seen.add(digest)
    # digest-0 members are rows 0..4 (4 forced to digest-0): representative must
    # be the one with earliest flow_start_ms among them
    group_positions = np.flatnonzero(
        np.array([d == b"digest-0" for d in arrays["canonical_row_digest"]]))
    best = min(group_positions, key=lambda p: (
        arrays["flow_start_ms"][p], arrays["source_row_index"][p]))
    assert best in reps
    # deterministic: same result twice
    reps2, _ = g.duplicate_representatives(arrays, 0)
    assert np.array_equal(reps, reps2)


def test_sample_pool_caps_blocks_and_seed_reproducibility():
    arrays = make_arrays(4000)
    arrays["partition_code"] = np.zeros(4000, dtype=np.int64)
    arrays["target_eligible"] = np.ones(4000, dtype=bool)
    pool, _ = g.duplicate_representatives(arrays, 0)
    assert len(pool) == len(np.unique(arrays["canonical_row_digest"][pool]))
    rng1 = np.random.default_rng(20260817)
    rng2 = np.random.default_rng(20260817)
    chosen1, blocks1 = g.sample_pool(
        rng=rng1, pool_positions=pool, arrays=arrays, cap=800, minimum=500,
        blocks=50, name="test")
    chosen2, blocks2 = g.sample_pool(
        rng=rng2, pool_positions=pool, arrays=arrays, cap=800, minimum=500,
        blocks=50, name="test")
    assert len(chosen1) == 800
    assert len(np.unique(chosen1)) == 800
    assert np.array_equal(chosen1, chosen2)
    assert np.array_equal(blocks1, blocks2)
    assert blocks1.min() >= 0 and blocks1.max() < 50
    # no duplicate group appears twice in the drawn targets
    digests = arrays["canonical_row_digest"][chosen1]
    assert len(np.unique(digests)) == len(digests)
    # minimum violation blocks sampling
    with pytest.raises(SystemExit):
        g.sample_pool(rng=np.random.default_rng(1), pool_positions=pool[:500],
                      arrays=arrays, cap=1500, minimum=1000, blocks=50, name="small")


def test_strict_history_past_only_and_cross_split_isolation():
    # one target (row 10) in partition 0, source 5, destination 11, port 2000
    n = 20
    arrays = make_arrays(n)
    for key in arrays:
        pass
    arrays["partition_code"] = np.zeros(n, dtype=np.int64)
    arrays["src_code"] = np.full(n, 5, dtype=np.int64)
    arrays["dst_code"] = np.full(n, 11, dtype=np.int64)
    arrays["dst_port"] = np.full(n, 2000, dtype=np.int64)
    arrays["critical_valid"] = np.ones(n, dtype=bool)
    starts = np.array([100_000, 110_000, 120_000, 130_000, 140_000,
                       150_000, 160_000, 170_000, 180_000, 190_000,
                       200_000] + [250_000] * (n - 11), dtype=np.int64)
    arrays["flow_start_ms"] = starts
    arrays["flow_end_ms"] = starts + 100
    target = np.array([10])  # start 200_000
    # row 9 (start 190_000, end 190_100 < 200_000) inside 10s window;
    # rows 0..8 outside 10s; row 10 itself and later rows must never contribute.
    history, names = g.strict_history_features(arrays, target)
    assert list(names) == list(g.HISTORY_FIELDS)
    assert history.shape == (1, 34)
    count_index = names.index("source_flow_count_10s")
    assert history[0, count_index] == 1  # only row 9 in the 10s window
    count_60 = names.index("source_flow_count_60s")
    # 60s window covers ends in [140_000, 200_000): rows 4..9
    assert history[0, count_60] == 6
    gap_index = names.index("same_source_last_seen_gap_ms")
    assert history[0, gap_index] == 200_000 - 190_100
    # cross-split isolation: same setup but contributors in partition 1
    arrays["partition_code"][:10] = 1
    history2, _ = g.strict_history_features(arrays, target)
    assert history2[0, count_index] == 0  # partition-1 rows cannot contribute
    assert history2[0, gap_index] == -1.0  # no legal prior flow at all


def test_strict_history_excludes_equal_start_and_future():
    n = 8
    arrays = make_arrays(n)
    arrays["partition_code"] = np.zeros(n, dtype=np.int64)
    arrays["src_code"] = np.full(n, 3, dtype=np.int64)
    arrays["dst_code"] = np.full(n, 9, dtype=np.int64)
    arrays["dst_port"] = np.full(n, 5000, dtype=np.int64)
    arrays["critical_valid"] = np.ones(n, dtype=bool)
    arrays["flow_start_ms"] = np.array([100_000, 150_000, 150_000, 150_000,
                                        150_000, 150_000, 300_000, 400_000],
                                       dtype=np.int64)
    arrays["flow_end_ms"] = np.array([100_050, 150_050, 149_000, 150_000,
                                      151_000, 150_050, 300_050, 400_050],
                                     dtype=np.int64)
    target = np.array([5])  # start 150_000
    history, names = g.strict_history_features(arrays, target)
    count_index = names.index("source_flow_count_60s")
    # rows 0 (end 100_050) and 2 (end 149_000) end strictly before 150_000;
    # end == start (row 3) and future rows (1, 4, 6, 7) are excluded
    assert history[0, count_index] == 2


def test_forbidden_features_not_in_feature_names():
    for name in (list(g.MODEL_VISIBLE_FIELDS) + list(g.TEMPORAL_FIELDS)
                 + list(g.RELATION_FIELDS)):
        lowered = name.casefold()
        for marker in g.FORBIDDEN_FEATURE_MARKERS:
            assert marker not in lowered, (name, marker)
    assert "canonical_label" not in g.MODEL_VISIBLE_FIELDS
    assert "source_row_index" not in g.MODEL_VISIBLE_FIELDS


def test_build_feature_matrices_same_targets_and_shapes():
    targets = np.array([3, 7, 9])
    basic_values = {int(i): np.full(47, float(i)) for i in targets}
    history_values = {}
    for i in targets:
        row = np.arange(34, dtype=np.float64) + i
        row[list(g.HISTORY_FIELDS).index("same_source_last_seen_gap_ms")] = -1.0
        history_values[int(i)] = row
    basic = np.stack([basic_values[int(i)] for i in targets])
    history = np.stack([history_values[int(i)] for i in targets])
    matrices = g.build_feature_matrices(basic, history, list(g.HISTORY_FIELDS))
    assert matrices["B"].shape == (3, 47)
    assert matrices["BT"].shape == (3, 47 + 16)
    assert matrices["BR"].shape == (3, 47 + 18)
    assert matrices["BTR"].shape == (3, 47 + 34)
    # same target ids everywhere: first rows are the transform of target 3
    assert np.allclose(matrices["B"][0], matrices["BT"][0, :47])
    assert np.allclose(matrices["B"][0], matrices["BTR"][0, :47])
    names = list(g.HISTORY_FIELDS)
    temporal_index = [names.index(name) for name in g.TEMPORAL_FIELDS]
    relation_index = [names.index(name) for name in g.RELATION_FIELDS]
    # BT history block equals BTR's temporal columns; BR equals BTR's relation columns
    assert np.allclose(matrices["BT"][0, 47:],
                       matrices["BTR"][0, [47 + i for i in temporal_index]])
    assert np.allclose(matrices["BR"][0, 47:],
                       matrices["BTR"][0, [47 + i for i in relation_index]])
    # history transform log1p(clip(>=0)): -1 gap becomes log1p(0)=0;
    # positive raw values (target 3 -> raw 3) become log1p(3)
    gap = list(g.HISTORY_FIELDS).index("same_source_last_seen_gap_ms")
    assert matrices["BTR"][0, 47 + gap] == 0.0
    assert matrices["BTR"][0, 47] == np.log1p(3.0)


def test_recoverability_and_harm_arithmetic():
    labels = np.array(["Benign", "DDoS", "DDoS", "Benign", "DDoS", "DDoS"], dtype=object)
    pred_b = np.array(["Benign", "DDoS", "Benign", "DDoS", "DDoS", "Benign"], dtype=object)
    pred_c = np.array(["Benign", "DDoS", "DDoS", "Benign", "DDoS", "DDoS"], dtype=object)
    out = g.recoverability(pred_b, pred_c, labels)
    # rows 2, 3, 5: Basic wrong and condition correct -> recovered
    # no row has Basic correct and condition wrong -> harm 0
    assert out["recoverable_known_n"] == 3
    assert out["recoverable_known_rate"] == pytest.approx(3 / 6)
    assert out["recoverable_among_basic_errors"] == pytest.approx(1.0)
    assert out["harm_n"] == 0
    assert out["harm_rate"] == pytest.approx(0.0)
    assert out["net_recovery_rate"] == pytest.approx(3 / 6)
    assert out["per_class"]["DDoS"]["recoverable_known_rate"] == pytest.approx(2 / 4)
    assert out["per_class"]["Benign"]["recoverable_known_rate"] == pytest.approx(1 / 2)


def test_macro_f1_from_confusion_matches_sklearn():
    rng = np.random.default_rng(11)
    labels = np.array([g.CANONICAL_CLASS_ORDER[i] for i in rng.integers(0, 7, 2000)],
                      dtype=object)
    predicted = np.array([g.CANONICAL_CLASS_ORDER[i] for i in rng.integers(0, 7, 2000)],
                         dtype=object)
    confusion = np.zeros((7, 7), dtype=np.int64)
    code = {name: i for i, name in enumerate(g.CANONICAL_CLASS_ORDER)}
    for label, pred in zip(labels, predicted, strict=True):
        confusion[code[label], code[pred]] += 1
    ours = g._macro_f1_from_confusion(confusion)
    sklearn = f1_score(labels, predicted, average="macro")
    assert ours == pytest.approx(sklearn, abs=1e-12)


def test_paired_group_bootstrap_pairing_and_reproducibility():
    rng = np.random.default_rng(3)
    n = 600
    groups = np.array([f"g-{i % 40}".encode() for i in range(n)], dtype=object)
    labels = np.array([g.CANONICAL_CLASS_ORDER[i % 7] for i in range(n)], dtype=object)
    predictions = {}
    for condition in g.CONDITIONS:
        predictions[condition] = np.array(
            [g.CANONICAL_CLASS_ORDER[i % 7] for i in rng.integers(0, 7, n)], dtype=object)
    families = g.paired_group_bootstrap(
        labels=labels, groups=groups, predictions=predictions,
        n_reps=50, rng_seed=20260817 + g.BOOTSTRAP_RNG_OFFSET)
    assert set(families) == {"T", "R", "TR"}
    for family in ("T", "R", "TR"):
        info = families[family]
        assert 0.0 <= info["recoverable_rate_mean"] <= 1.0
        assert info["delta_macro_f1_ci95"][0] <= info["delta_macro_f1_mean"] \
            <= info["delta_macro_f1_ci95"][1]
        assert info["net_recovery_mean"] == pytest.approx(
            info["recoverable_rate_mean"] - info["harm_rate_mean"])
    # deterministic under the same rng seed
    families2 = g.paired_group_bootstrap(
        labels=labels, groups=groups, predictions=predictions,
        n_reps=50, rng_seed=20260817 + g.BOOTSTRAP_RNG_OFFSET)
    assert families["T"]["delta_macro_f1_mean"] == families2["T"]["delta_macro_f1_mean"]


def test_build_candidates_decision_states():
    def make_result(delta, rec, harm, attack_classes):
        return {"result": {
            "deltas": {f: delta for f in ("T", "R", "TR")},
            "recoverability": {f: {
                "recoverable_known_rate": rec,
                "harm_rate": harm,
                "net_recovery_rate": rec - harm,
                "per_class": {name: {"recoverable_known_rate":
                                     (rec if name in attack_classes else 0.0)}
                              for name in g.CANONICAL_CLASS_ORDER},
            } for f in ("T", "R", "TR")},
        }, "bootstrap": {"families": {f: {
            "delta_macro_f1_mean": delta,
            "delta_macro_f1_ci95": [delta - 0.0001, delta + 0.0001],
        } for f in ("T", "R", "TR")}}}

    # strong positive everywhere -> PASS
    strong = [make_result(0.02, 0.10, 0.005, ["DDoS", "DoS", "Credential"])] * 3
    candidates, decision, family = g.build_candidates(strong)
    assert decision == "PASS" and family in ("T", "R", "TR")
    # everything negative -> FAIL
    weak = [make_result(-0.001, 0.005, 0.001, [])] * 3
    _, decision, family = g.build_candidates(weak)
    assert decision == "FAIL" and family == "NONE"
    # marginal positive delta -> YELLOW
    marginal = [make_result(0.003, 0.01, 0.0005, [])] * 3
    _, decision, _ = g.build_candidates(marginal)
    assert decision == "YELLOW"
    # recoverability present but not all criteria -> YELLOW (weak signal)
    partial = [make_result(0.02, 0.06, 0.001, ["DDoS"])] * 3
    _, decision, _ = g.build_candidates(partial)
    assert decision == "YELLOW"


def test_estimator_config_frozen():
    assert g.ESTIMATOR_FAMILY == "RandomForestClassifier"
    assert g.ESTIMATOR_CONFIG["n_estimators"] == 80
    assert g.ESTIMATOR_CONFIG["max_depth"] == 20
    assert g.ESTIMATOR_CONFIG["class_weight"] == "balanced_subsample"
    model = g.fit_estimator(20260817)
    assert model.random_state == 20260817


def test_safe_basic_transform():
    matrix = np.array([[0.0, -5.0, 10.0, np.nan, np.inf]])
    out = g.safe_basic(matrix)
    assert out[0, 0] == 0.0
    assert out[0, 1] == pytest.approx(-np.log1p(5.0))
    assert out[0, 2] == pytest.approx(np.log1p(10.0))
    assert out[0, 3] == 0.0
    assert out[0, 4] == pytest.approx(np.log1p(1e15))
