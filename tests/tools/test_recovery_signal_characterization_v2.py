"""Synthetic-only tests for the frozen V2 recovery-signal gate tool.

Phase B constraint: NO real evaluation metrics. Everything here runs on
tiny synthetic fixtures. Covers:
  - feature schemas (exact column order, formulas, no-GT-in-features)
  - V2_PROBE_FIT/CALIB split (determinism, group atomicity, isolation)
  - capacity ladder (matched configs, determinism, fit-on-FIT-only)
  - calibration (V1 quantile semantics, tie semantics)
  - signal / transfer / end-to-end / interpretation rules
  - weighted group bootstrap (pairing, consistency with point estimates)
  - preregistration manifest (tool constants == frozen preregistration JSON)
"""

import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

TOOLS = Path(__file__).resolve().parents[2] / "tools"
REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(TOOLS))

import run_recovery_signal_characterization_v2 as v2  # noqa: E402

K = 6  # frozen Known class count


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def proba_pair():
    rng = np.random.default_rng(7)
    n = 24
    pre = rng.dirichlet(np.ones(K), size=n)
    post = np.abs(pre + rng.normal(0, 0.25, size=(n, K)))
    post /= post.sum(axis=1, keepdims=True)
    actions = np.array(["NONE", "T", "R", "TR"] * (n // 4), dtype=object)
    return pre, post, actions


@pytest.fixture
def split_input():
    rng = np.random.default_rng(42)
    digests = [hashlib.sha256(f"g{i}".encode()).digest() for i in range(20)]
    sizes = [3, 1, 5, 2, 4, 1, 7, 2, 3, 1, 2, 4, 1, 3, 2, 5, 1, 2, 4, 3]
    groups, labels, blocks = [], [], []
    for i, s in enumerate(sizes):
        lab, blk = f"C{i % 3}", i % 2
        for _ in range(s):
            groups.append(digests[i])
            labels.append(lab)
            blocks.append(blk)
    return (np.array(groups, dtype=object), np.array(labels, dtype=object),
            np.array(blocks, dtype=np.int64))


def fake_cell(rotation, seed, rng, n_groups=40, n_rows=120, n_eval=26):
    """Synthetic cell + matching parquet table for bootstrap tests."""
    digests = [hashlib.sha256(f"{seed}-{rotation}-g{i}".encode()).digest()
               for i in range(n_groups)]
    groups = np.repeat(digests, 3)[:n_rows]
    n = len(groups)
    role = rng.integers(0, 2, size=n)
    role[: n // 2] = 0  # keep both split roles present
    is_unknown = rng.random(n) < 0.2
    recoverable = rng.random(n) < 0.3
    labels = np.array([f"L{i % 3}" for i in range(n)], dtype=object)
    # 2/3 of rows recover (pred6 == label) so ACCEPT_TARGET has both classes
    pred6 = np.array([labels[i] if i % 3 else f"L{(i + 1) % 3}"
                      for i in range(n)], dtype=object)
    pred0 = np.array([f"L{(i + 2) % 3}" for i in range(n)], dtype=object)
    sc0 = rng.random(n)
    sc1 = rng.random(n)
    ev = np.flatnonzero(role == 1)
    n_eval = len(ev)
    # per-cell caches used by the bootstrap
    s1 = 1.0 - rng.random(n)
    s2 = np.clip(s1 + rng.normal(0, 0.05, size=n), 0, 1)
    cache = {
        "B0_BASIC_MSP": sc0, "B1_UTILITY_POST_MSP": sc1,
        "L_POST": s1, "L_TRAJ": s2, "N_POST": s1, "N_TRAJ": s2,
    }
    paccept = {p: 1.0 - cache[p] for p in v2.PROBES}
    util_cache = {f: {"signed": rng.integers(-1, 2, size=n),
                      "novelty_util": rng.normal(0, 0.1, size=n)}
                  for f in v2.FAMILIES}
    thresholds = {m: float(np.quantile(cache[m][role == 0], 0.5))
                  for m in v2.METHODS}
    cell = {
        "seed": int(seed), "rotation": rotation,
        "n_eval": n_eval,
        "n_calib_known": int((role == 0).sum()),
        "n_fit": 0, "n_calib_fit": 0,
        "n_eval_known": int(((role == 1) & (is_unknown == 0)).sum()),
        "n_eval_unknown": int(((role == 1) & is_unknown).sum()),
        "n_recoverable_known_eval": 0,
        "thresholds": thresholds,
        "_scores_cache": cache, "_paccept_cache": paccept,
        "_util_cache": util_cache,
    }
    table = pa.table({
        "split_role": role.astype(np.int8),
        "is_unknown": is_unknown.astype(np.int8),
        "recoverable": recoverable.astype(np.int8),
        "activity_group_digest": pa.array(groups, type=pa.binary()),
        "canonical_label": labels,
        "pred_P6_UTILITY_TYPED": pred6,
        "pred_P0_BASIC_DIRECT": pred0,
    })
    return cell, table


# ---------------------------------------------------------------------------
# Feature schemas
# ---------------------------------------------------------------------------

def test_post_only_schema(proba_pair):
    pre, post, actions = proba_pair
    m = v2.post_only_matrix(post, actions)
    assert m.shape == (len(post), 7)
    # exact column order
    names = v2.POST_ONLY_FEATURES
    assert names == ("conf_post", "margin_post", "entropy_post",
                     "ONEHOT_NONE", "ONEHOT_T", "ONEHOT_R", "ONEHOT_TR")
    conf = post.max(axis=1)
    margin = np.sort(post, axis=1)[:, ::-1][:, 0] - np.sort(post, axis=1)[
        :, ::-1][:, 1]
    np.testing.assert_allclose(m[:, 0], conf, atol=1e-12)
    np.testing.assert_allclose(m[:, 1], margin, atol=1e-12)
    np.testing.assert_allclose(m[:, 2], v2.entropy_norm(post), atol=1e-12)
    onehot = m[:, 3:]
    assert np.allclose(onehot.sum(axis=1), 1.0)
    for i, act in enumerate(actions):
        col = {"NONE": 0, "T": 1, "R": 2, "TR": 3}[act]
        assert onehot[i, col] == 1.0
        assert (onehot[i] != 1.0).sum() == 3


def test_trajectory_schema(proba_pair):
    pre, post, actions = proba_pair
    m = v2.trajectory_matrix(pre, post, actions)
    assert m.shape == (len(post), 19)
    assert len(v2.TRAJECTORY_FEATURES) == 19
    assert v2.TRAJECTORY_FEATURES[:7] == v2.POST_ONLY_FEATURES
    # first 7 columns are identical to the post-only matrix
    np.testing.assert_allclose(m[:, :7], v2.post_only_matrix(post, actions),
                               atol=1e-12)
    # formulas
    conf_pre = pre.max(axis=1)
    s_pre = np.sort(pre, axis=1)[:, ::-1]
    margin_pre = s_pre[:, 0] - s_pre[:, 1]
    ent_pre = v2.entropy_norm(pre)
    np.testing.assert_allclose(m[:, 7], conf_pre, atol=1e-12)
    np.testing.assert_allclose(m[:, 8], margin_pre, atol=1e-12)
    np.testing.assert_allclose(m[:, 9], ent_pre, atol=1e-12)
    conf_post = post.max(axis=1)
    np.testing.assert_allclose(m[:, 10], conf_post - conf_pre, atol=1e-12)
    i_pre = np.argmax(pre, axis=1)
    i_post = np.argmax(post, axis=1)
    np.testing.assert_allclose(m[:, 13], (i_pre != i_post).astype(float),
                               atol=1e-12)
    rows = np.arange(len(pre))
    np.testing.assert_allclose(m[:, 14], pre[rows, i_post], atol=1e-12)
    np.testing.assert_allclose(m[:, 15], post[rows, i_pre], atol=1e-12)
    np.testing.assert_allclose(m[:, 16], post[rows, i_post] - pre[rows, i_post],
                               atol=1e-12)
    np.testing.assert_allclose(m[:, 17], post[rows, i_pre] - pre[rows, i_pre],
                               atol=1e-12)
    np.testing.assert_allclose(m[:, 18], post[rows, i_post] - post[rows, i_pre],
                               atol=1e-12)


def test_features_never_contain_labels(proba_pair):
    """API-level leakage check: feature builders take only probas + actions
    (runtime-observable), never labels, predictions, or correctness."""
    import inspect
    for fn in (v2.post_only_matrix, v2.trajectory_matrix,
               v2.entropy_norm, v2.onehot_action):
        params = list(inspect.signature(fn).parameters)
        for banned in ("label", "target", "y", "accept", "truth",
                       "recoverable", "unknown"):
            assert not any(banned in p for p in params), (fn, params)


def test_accept_target():
    pred = np.array(["A", "B", "C", "A"], dtype=object)
    label = np.array(["A", "A", "C", "D"], dtype=object)
    np.testing.assert_array_equal(v2.accept_target(pred, label),
                                  [1, 0, 1, 0])


# ---------------------------------------------------------------------------
# V2_PROBE_FIT / V2_PROBE_CALIB split
# ---------------------------------------------------------------------------

def test_split_deterministic_and_atomic(split_input):
    groups, labels, blocks = split_input
    r1 = v2.build_probe_split(20260817, "Credential", groups, labels, blocks)
    r2 = v2.build_probe_split(20260817, "Credential", groups, labels, blocks)
    assert np.array_equal(r1, r2)
    seen = {}
    for d, r in zip(groups, r1):
        if d in seen:
            assert seen[d] == r, "group crosses FIT/CALIB"
        seen[d] = r


def test_split_covers_input_exactly(split_input):
    groups, labels, blocks = split_input
    r = v2.build_probe_split(20260817, "Credential", groups, labels, blocks)
    assert set(np.unique(r)) <= {0, 1}
    assert len(r) == len(groups)


def test_split_seed_and_rotation_sensitive(split_input):
    groups, labels, blocks = split_input
    r1 = v2.build_probe_split(20260817, "Credential", groups, labels, blocks)
    r2 = v2.build_probe_split(20260818, "Credential", groups, labels, blocks)
    r3 = v2.build_probe_split(20260817, "Web_Injection", groups, labels,
                              blocks)
    assert not np.array_equal(r1, r2)
    assert not np.array_equal(r1, r3)


def test_split_roughly_60_40(split_input):
    groups, labels, blocks = split_input
    r = v2.build_probe_split(20260817, "Credential", groups, labels, blocks)
    frac = (r == 0).mean()
    assert 0.4 <= frac <= 0.8  # group-atomicity allows drift from 0.60


def test_split_stratum_uses_primary_row(split_input):
    """Same (class, block) stratum layout exercises the ordering code path;
    assignment must not depend on row order within a group."""
    groups, labels, blocks = split_input
    r1 = v2.build_probe_split(20260817, "Credential", groups, labels, blocks)
    perm = np.random.default_rng(3).permutation(len(groups))
    r2 = v2.build_probe_split(20260817, "Credential", groups[perm],
                              labels[perm], blocks[perm])
    # group roles must agree after unpermuting
    role1 = {bytes(d): int(r) for d, r in zip(groups, r1)}
    role2 = {bytes(d): int(r) for d, r in zip(groups[perm], r2)}
    assert role1 == role2


# ---------------------------------------------------------------------------
# Capacity ladder
# ---------------------------------------------------------------------------

def test_capacity_ladder_matched_configs(proba_pair):
    pre, post, actions = proba_pair
    post_f = v2.post_only_matrix(post, actions)
    traj_f = v2.trajectory_matrix(pre, post, actions)
    feats = {"L_POST": post_f, "L_TRAJ": traj_f,
             "N_POST": post_f, "N_TRAJ": traj_f}
    # ACCEPT_TARGET on a synthetic Known FIT population
    pred = np.array(["A"] * len(post), dtype=object)
    labels = np.array(["A", "B"] * (len(post) // 2), dtype=object)
    y_fit = v2.accept_target(pred, labels)
    fit_mask = np.zeros(len(post), dtype=bool)
    fit_mask[:16] = True
    p1 = v2.fit_probes(feats, y_fit[fit_mask], fit_mask, 20260817)
    p2 = v2.fit_probes(feats, y_fit[fit_mask], fit_mask, 20260817)
    assert set(p1) == set(v2.PROBES)
    # determinism
    for probe in v2.PROBES:
        np.testing.assert_allclose(p1[probe], p2[probe], atol=1e-12)
    # probability mass
    for probe in v2.PROBES:
        assert np.all((p1[probe] >= 0) & (p1[probe] <= 1))


def test_capacity_ladder_fit_mask_isolation(proba_pair):
    """Probes must not depend on non-FIT rows: fitting on a subset equals
    fitting on the full population restricted to the same FIT rows."""
    pre, post, actions = proba_pair
    post_f = v2.post_only_matrix(post, actions)
    traj_f = v2.trajectory_matrix(pre, post, actions)
    feats = {"L_POST": post_f, "L_TRAJ": traj_f,
             "N_POST": post_f, "N_TRAJ": traj_f}
    pred = np.array(["A"] * len(post), dtype=object)
    labels = np.array(["A", "B"] * (len(post) // 2), dtype=object)
    y_fit = v2.accept_target(pred, labels)
    fit_mask = np.zeros(len(post), dtype=bool)
    fit_mask[:16] = True
    p_full = v2.fit_probes(feats, y_fit[fit_mask], fit_mask, 20260817)
    # restrict every input to the FIT rows
    sub = {k: feats[k][fit_mask] for k in feats}
    p_sub = v2.fit_probes(sub, y_fit[fit_mask],
                          np.ones(16, dtype=bool), 20260817)
    for probe in v2.PROBES:
        np.testing.assert_allclose(p_full[probe][fit_mask], p_sub[probe],
                                   atol=1e-9)


def test_linear_vs_rf_configs_match_preregistration():
    """Manifest check: the tool's capacity ladder equals the frozen
    preregistration JSON (no detector shopping)."""
    reg = json.loads((REPO / "reports" / "research_audit" /
                      "recovery_signal_characterization_v2_preregistration.json"
                      ).read_text())
    ladder = reg["capacity_ladder"]
    assert v2.LINEAR_CONFIG == dict(sorted(ladder["LEVEL1_LINEAR"]["config"].items()))
    rf_conf = dict(ladder["LEVEL2_NONLINEAR"]["config"])
    rf_conf.pop("random_state")  # <rotation seed> placeholder in JSON
    assert v2.RF_CONFIG == rf_conf
    assert set(v2.METHODS) == set(reg["methods"])
    assert list(v2.POST_ONLY_FEATURES) == reg["feature_schemas"]["POST_ONLY"]
    assert list(v2.TRAJECTORY_FEATURES) == reg["feature_schemas"][
        "RECOVERY_TRAJECTORY"]
    assert v2.CALIB_KNOWN_FALSE_UNKNOWN_RATE == 0.05


# ---------------------------------------------------------------------------
# Calibration (frozen V1 semantics)
# ---------------------------------------------------------------------------

def test_calibration_quantile_and_tie_semantics():
    rng = np.random.default_rng(11)
    scores = rng.random(200)
    thr = v2.calibrate_threshold(scores)
    assert thr == pytest.approx(np.quantile(scores, 0.95))
    # V1 tie semantics: rejected = score >= threshold
    assert (scores >= thr).sum() == pytest.approx(10, abs=1)
    assert (scores > thr).sum() <= 10


def test_calibration_empty_returns_inf():
    assert v2.calibrate_threshold(np.array([])) == float("inf")


# ---------------------------------------------------------------------------
# Signal / transfer / end-to-end / interpretation rules
# ---------------------------------------------------------------------------

def _metric_row(furk, rcj=0.50, ua=0.90, urec=0.80, kfur=0.05, rbr=0.20):
    return {"FURK": furk,
            "FURK_NUMERATOR": int(furk * 100), "FURK_DENOMINATOR": 100,
            "A1": int((1.0 - furk) * 80), "A2": int(furk * 20),
            "RECOVERY_CONDITIONAL_REJECTION_RATE": rcj,
            "RECOVERED_BUT_REJECTED_RATE": rbr,
            "UNKNOWN_AUROC": ua, "UNKNOWN_AUPR": ua - 0.05,
            "UNKNOWN_RECALL_AT_CALIBRATED_FUR": urec,
            "KNOWN_FALSE_UNKNOWN_RATE": kfur}


def _fabricated_cells(delta, ci_lower, headroom=0.1, rcj_delta=0.10,
                      auroc_loss=0.0, recall_loss=0.0, furk_gain=0.05):
    """Cells with controllable per-rotation mean deltas."""
    cells = []
    for rotation in v2.ROTATIONS:
        for seed in v2.SEEDS:
            c = {
                "rotation": rotation, "seed": int(seed),
                "signal": {
                    "L_POST": {"AUROC": 0.60}, "L_TRAJ": {"AUROC": 0.60 + delta},
                    "N_POST": {"AUROC": 0.60},
                    "N_TRAJ": {"AUROC": 0.60 + delta}},
                "metrics": {
                    "B0_BASIC_MSP": _metric_row(0.60 - furk_gain),
                    "B1_UTILITY_POST_MSP": _metric_row(0.55),
                    "L_POST": _metric_row(0.55), "L_TRAJ": _metric_row(0.51),
                    "N_POST": _metric_row(0.50),
                    "N_TRAJ": _metric_row(0.50 - 0.04,
                                          rcj=0.50 - rcj_delta,
                                          ua=0.90 - auroc_loss,
                                          urec=0.80 - recall_loss)},
                "utility_correlation": {
                    f: {"SPEARMAN_CLASSIFICATION_UTILITY_VS_NOVELTY_UTILITY":
                        0.1, "CLASSIFICATION_HELP_N": 100,
                        "HELP_NOVELTY_IMPROVE_RATE": 0.2,
                        "HELP_NOVELTY_WORSEN_RATE": 0.1,
                        "HELP_MEAN_NOVELTY_UTILITY": 0.05}
                    for f in v2.FAMILIES},
                "P6_RECOVERY_RATE": 0.6 - headroom,
                "ROUTER_RECOVERY_HEADROOM": headroom,
                "INTERFACE_HEADROOM_PROXY": 0.2,
            }
            cells.append(c)
    boot = {
        "FURK_N_TRAJ_MINUS_N_POST": {"ci95": [ci_lower, ci_lower + 0.01]},
        "FURK_L_TRAJ_MINUS_L_POST": {"ci95": [ci_lower, ci_lower + 0.01]},
        "FURK_N_TRAJ_MINUS_B1": {"ci95": [ci_lower, ci_lower + 0.01]},
        "FURK_L_TRAJ_MINUS_B1": {"ci95": [ci_lower, ci_lower + 0.01]},
        "FURK_N_TRAJ_MINUS_B0": {"ci95": [ci_lower, ci_lower + 0.01]},
        "RBR_N_TRAJ_MINUS_N_POST": {"ci95": [ci_lower, ci_lower + 0.01]},
        "RBR_N_TRAJ_MINUS_B1": {"ci95": [ci_lower, ci_lower + 0.01]},
        "RCJ_N_TRAJ_MINUS_N_POST": {"ci95": [ci_lower, ci_lower + 0.01]},
        "RCJ_N_TRAJ_MINUS_B1": {"ci95": [ci_lower, ci_lower + 0.01]},
        "UNKNOWN_AUROC_N_TRAJ_MINUS_N_POST": {"ci95": [0, 0.01]},
        "UNKNOWN_AUROC_N_TRAJ_MINUS_B0": {"ci95": [0, 0.01]},
        "UNKNOWN_RECALL_N_TRAJ_MINUS_N_POST": {"ci95": [0, 0.01]},
        "UNKNOWN_RECALL_N_TRAJ_MINUS_B0": {"ci95": [0, 0.01]},
        "LINEAR_DELTA_AUROC": {"ci95": [ci_lower, ci_lower + 0.01]},
        "NONLINEAR_DELTA_AUROC": {"ci95": [ci_lower, ci_lower + 0.01]},
        "SPEARMAN_T": {"mean": 0.0, "ci95": [-0.01, 0.01]},
        "SPEARMAN_R": {"mean": 0.0, "ci95": [-0.01, 0.01]},
        "SPEARMAN_TR": {"mean": 0.0, "ci95": [-0.01, 0.01]},
        "HELP_IMPROVE_T": {"mean": 0.1, "ci95": [0.0, 0.2]},
        "HELP_IMPROVE_R": {"mean": 0.1, "ci95": [0.0, 0.2]},
        "HELP_IMPROVE_TR": {"mean": 0.1, "ci95": [0.0, 0.2]},
        "HELP_WORSEN_T": {"mean": 0.1, "ci95": [0.0, 0.2]},
        "HELP_WORSEN_R": {"mean": 0.1, "ci95": [0.0, 0.2]},
        "HELP_WORSEN_TR": {"mean": 0.1, "ci95": [0.0, 0.2]},
    }
    return cells, boot


def test_signal_status_supported():
    cells, boot = _fabricated_cells(delta=0.03, ci_lower=0.005)
    status = v2.level_signal_status(cells, "nonlinear", 0.005)
    assert status == "SUPPORTED"


def test_signal_status_not_established_when_ci_crosses_zero():
    cells, boot = _fabricated_cells(delta=0.03, ci_lower=-0.001)
    status = v2.level_signal_status(cells, "nonlinear", -0.001)
    assert status == "NOT_ESTABLISHED"


def test_signal_status_not_established_when_too_small():
    cells, boot = _fabricated_cells(delta=0.005, ci_lower=0.001)
    status = v2.level_signal_status(cells, "nonlinear", 0.001)
    assert status == "NOT_ESTABLISHED"


def test_signal_status_rotation_requirement():
    """2 of 3 rotations positive is the required minimum (cells 0..2 are
    Credential's three seeds; zero their trajectory delta)."""
    cells, boot = _fabricated_cells(delta=0.03, ci_lower=0.005)
    for i in (0, 1, 2):
        cells[i]["signal"]["N_TRAJ"]["AUROC"] = 0.59  # Credential: delta<0
    deltas = v2.delta_auroc_by_rotation(cells, "nonlinear")
    assert sum(1 for v in deltas.values() if v > 0) == 2
    # mean = (0.03 + 0.03 - 0.01) / 3 = 0.0167 >= 0.01; CI lower > 0
    status = v2.level_signal_status(cells, "nonlinear", 0.005)
    assert status == "SUPPORTED"


def test_recovery_trajectory_signal_strong():
    cells, boot = _fabricated_cells(delta=0.03, ci_lower=0.005)
    lin = v2.level_signal_status(cells, "linear", 0.005)
    nonlin = v2.level_signal_status(cells, "nonlinear", 0.005)
    deltas = v2.delta_auroc_by_rotation(cells, "linear")
    assert v2.recovery_trajectory_signal(lin, nonlin, deltas) == "STRONG"


def test_transfer_pass_all_criteria():
    cells, boot = _fabricated_cells(delta=0.03, ci_lower=-0.02)
    t = v2.transfer_status(cells, boot)
    assert t["T1"] and t["T2"] and t["T3"] and t["T4"] and t["T5"]
    assert t["PASS"]


def test_transfer_fails_when_t1_violated():
    cells, boot = _fabricated_cells(delta=0.03, ci_lower=-0.01)
    for c in cells:
        c["metrics"]["N_TRAJ"]["FURK"] = c["metrics"]["N_POST"]["FURK"]
    t = v2.transfer_status(cells, boot)
    assert not t["T1"] and not t["PASS"]


def test_transfer_fails_when_ci_crosses_zero():
    cells, boot = _fabricated_cells(delta=0.03, ci_lower=0.002)
    t = v2.transfer_status(cells, boot)
    assert not t["T5"] and not t["PASS"]


def test_end_to_end_pass():
    cells, boot = _fabricated_cells(delta=0.03, ci_lower=-0.02)
    e = v2.end_to_end_status(cells, boot)
    assert e["E1"] and e["E2"] and e["E3"] and e["E4"]
    assert e["PASS"]


def test_interpretation_matrix():
    cells, boot = _fabricated_cells(delta=0.03, ci_lower=-0.02)
    sig = v2.recovery_trajectory_signal("SUPPORTED", "SUPPORTED", {})
    t = v2.transfer_status(cells, boot)
    e = v2.end_to_end_status(cells, boot)
    case = v2.interpret_case(sig, t, e, cells)
    assert case["CASE"] == "A"

    cells_d, boot_d = _fabricated_cells(delta=0.005, ci_lower=-0.01)
    sig_d = v2.recovery_trajectory_signal("NOT_ESTABLISHED",
                                          "NOT_ESTABLISHED", {})
    case_d = v2.interpret_case(sig_d, t, e, cells_d)
    assert case_d["CASE"] in ("E_HEADROOM", "E_NO_HEADROOM")

    # headroom large in >=2 rotations -> E_HEADROOM
    cells_h, boot_h = _fabricated_cells(delta=0.005, ci_lower=-0.01,
                                        headroom=0.5)
    case_h = v2.interpret_case(sig_d, t, e, cells_h)
    assert case_h["CASE"] == "E_HEADROOM"


# ---------------------------------------------------------------------------
# Weighted group bootstrap
# ---------------------------------------------------------------------------

def test_bootstrap_runs_and_is_paired(tmp_path):
    rng = np.random.default_rng(5)
    cells, tables = [], []
    for rotation in v2.ROTATIONS:
        for seed in v2.SEEDS:
            cell, table = fake_cell(rotation, seed, rng)
            cells.append(cell)
            tables.append(table)
    v1_root = tmp_path / "frozen"
    v1_root.mkdir()
    for cell, table in zip(cells, tables):
        pq.write_table(table, v1_root / (
            f"owg_v1_seed_{cell['seed']}_rotation_"
            f"{cell['rotation']}_eval.parquet"))
    boot = v2.run_bootstrap(cells, v1_root)
    assert boot["reps"] == 1000
    assert boot["paired"] is True
    for key in ("FURK_N_TRAJ_MINUS_N_POST", "FURK_N_TRAJ_MINUS_B0",
                "NONLINEAR_DELTA_AUROC", "SPEARMAN_T", "HELP_IMPROVE_R"):
        assert key in boot
        assert len(boot[key]["ci95"]) == 2
        assert np.isfinite(boot[key]["mean"]) or key.startswith("SPEARMAN")


def test_bootstrap_mean_consistency(tmp_path):
    """The mean of the per-replicate FURK difference (expectation of the
    ratio) must closely track the direct point difference (ratio of
    expectations); exact equality is not expected for bootstrap means."""
    rng = np.random.default_rng(9)
    cells, tables = [], []
    for rotation in v2.ROTATIONS:
        for seed in v2.SEEDS:
            cell, table = fake_cell(rotation, seed, rng)
            cells.append(cell)
            tables.append(table)
    v1_root = tmp_path / "frozen"
    v1_root.mkdir()
    for cell, table in zip(cells, tables):
        pq.write_table(table, v1_root / (
            f"owg_v1_seed_{cell['seed']}_rotation_"
            f"{cell['rotation']}_eval.parquet"))
    boot = v2.run_bootstrap(cells, v1_root)
    # direct point difference from the same frozen scores/thresholds
    num = den = 0.0
    for cell, table in zip(cells, tables):
        ev = np.flatnonzero(table["split_role"].to_numpy() == 1)
        known = table["is_unknown"].to_numpy() == 0
        rec = table["recoverable"].to_numpy().astype(bool)
        ev_rec_kn = ev[rec[ev] & known[ev]]
        sc_post = cell["_scores_cache"]["N_POST"][ev_rec_kn]
        sc_traj = cell["_scores_cache"]["N_TRAJ"][ev_rec_kn]
        thr = cell["thresholds"]
        num += ((sc_traj >= thr["N_TRAJ"]).sum()
                - (sc_post >= thr["N_POST"]).sum())
        den += len(ev_rec_kn)
    direct = num / den
    assert abs(boot["FURK_N_TRAJ_MINUS_N_POST"]["mean"] - direct) < 0.02
    assert np.isfinite(boot["FURK_N_TRAJ_MINUS_N_POST"]["mean"])


def test_bootstrap_spearman_matches_scipy_unweighted(tmp_path):
    """With the cell's util caches, the unweighted pooled Spearman over EVAL
    rows must match scipy on the same pooled arrays (sanity of the weighted
    implementation at w == 1)."""
    from scipy.stats import spearmanr
    rng = np.random.default_rng(13)
    cells, tables = [], []
    pooled_signed, pooled_nu = [], []
    for rotation in v2.ROTATIONS:
        for seed in v2.SEEDS:
            cell, table = fake_cell(rotation, seed, rng)
            cells.append(cell)
            tables.append(table)
            ev = np.flatnonzero(table["split_role"].to_numpy() == 1)
            pooled_signed.append(cell["_util_cache"]["T"]["signed"][ev])
            pooled_nu.append(cell["_util_cache"]["T"]["novelty_util"][ev])
    v1_root = tmp_path / "frozen"
    v1_root.mkdir()
    for cell, table in zip(cells, tables):
        pq.write_table(table, v1_root / (
            f"owg_v1_seed_{cell['seed']}_rotation_"
            f"{cell['rotation']}_eval.parquet"))
    sx = np.concatenate(pooled_signed).astype(np.float64)
    sy = np.concatenate(pooled_nu)
    direct = spearmanr(sx, sy).statistic
    boot = v2.run_bootstrap(cells, v1_root)
    # weighted rank at w=1 equals plain ranks (verified in the pure check);
    # the bootstrap mean over group draws tracks the pooled point estimate
    # (group-correlation bias permits small drift), and the CI contains it
    assert abs(boot["SPEARMAN_T"]["mean"] - direct) < 0.10
    lo, hi = boot["SPEARMAN_T"]["ci95"]
    assert lo <= direct <= hi


# ---------------------------------------------------------------------------
# Report assembly smoke (structure only)
# ---------------------------------------------------------------------------

def test_assemble_report_structure():
    cells, boot = _fabricated_cells(delta=0.03, ci_lower=-0.01)
    report = v2.assemble_report(cells, boot, "deadbeef", "abc1234")
    assert report["v2_protocol_sha256"] == "deadbeef"
    assert report["signal"]["RECOVERY_TRAJECTORY_SIGNAL"] in (
        "STRONG", "WEAK", "NOT_ESTABLISHED")
    assert report["frozen"]["V1_RESULT"] == "FAIL"
    assert report["frozen"]["V1_RESULT_CHANGED"] is False
    assert report["interpretation"]["CASE"]
    for m in v2.METHODS:
        assert m in report["pooled"]
    assert report["rl"]["RL_REQUIRED"] is False
    assert report["safety"]["FINAL_TEST_MODELING_CONTAMINATION"] is False
    assert report["safety"]["ROUTER_RETRAINED"] is False
    for r in v2.ROTATIONS:
        assert r in report["per_rotation"]
    assert "methods" in report
