#!/usr/bin/env python3
"""STRONG_HYBRID_OSR_EVIDENCE_RECOVERABILITY_GATE_V2.

Preregistered prospective V2 (protocol:
docs/research_plan/strong_hybrid_osr_evidence_gate_v2_protocol.md).

Hybrid system: frozen RF family (stored P0/P6 outputs; frozen models
pickle read-only for offline state-s oracle) provides Known-class
prediction; the V1 neural typed-block representation + per-state
Mahalanobis geometry provides novelty. V1 remains immutable
(GATE_INVALID_OSR_INADEQUATE, EVIDENCE_SCIENTIFIC_STATUS=NOT_JUDGED).

Safety: FINAL_TEST forbidden; True Unknown never enters representation
training, normalization, early stopping, geometry fitting, calibration,
or model selection; router never retrained; RF never retrained/tuned;
no detector shopping; no post-result tuning; scientific change after
the first formal metric -> STOP.

Determinism: fixed PYTHONHASHSEED at launch, seeded Generators only,
torch manual seeds, cudnn.deterministic=True, cudnn.benchmark=False.

Modes:
  smoke — synthetic tiny data, pipeline integrity only.
  run   — executes the frozen gate cell by cell (deterministic,
          restartable, status-persistent).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import pickle
import random
import sys
import time
import traceback
from pathlib import Path
from typing import Any

import numpy as np
import pyarrow.parquet as pq

TOOLS = Path(__file__).resolve().parent
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import torch  # noqa: E402
import torch.nn as nn  # noqa: E402
from sklearn.metrics import (  # noqa: E402
    average_precision_score,
    f1_score,
    roc_auc_score,
)

from run_strong_neural_osr_evidence_gate_v1 import (  # noqa: E402
    ADAMW_LR,
    ADAMW_WEIGHT_DECAY,
    ACTION_MODEL,
    BATCH_SIZE,
    C3_RATIO_BOUND,
    EARLY_STOP_PATIENCE,
    EVIDENCE_STATES,
    FORMAL_SEEDS,
    LEGAL_STATES,
    MAX_EPOCHS,
    RNG_BASE,
    ROTATIONS,
    SUPCON_TEMPERATURE,
    SUPCON_WEIGHT,
    StrongOSREncoder,
    EDLHeadEncoder,
    assemble_cell,
    canonical_json,
    cell_key,
    cell_rng,
    class_codes,
    deep_msp,
    edl_loss,
    encoder_forward,
    find_nonfinite,
    fit_osr_geometry,
    furk_of,
    group_codes,
    known_classes_for,
    known_unknown_aupr,
    known_unknown_auroc,
    mahalanobis_min_distance,
    policy_states,
    recall_at_5fur,
    split_train_fit_early,
    state_relation,
    state_score_map,
    state_temporal,
    supervised_contrastive_loss,
    TRAIN_POOL_N,
    TRAIN_SPLIT_COUNTS,
    write_status,
    read_status,
)

DEFAULT_OWG_ROOT = (
    "/root/autodl-tmp/processed/dataset_v4_nf3_ton_v1/open_world_recoverability_gate_v1"
)
DEFAULT_GATE1_ROOT = (
    "/root/autodl-tmp/processed/dataset_v4_nf3_ton_v1/core_gate_v1"
)
DEFAULT_RUN_ROOT = (
    "/root/autodl-tmp/processed/dataset_v4_nf3_ton_v1/"
    "strong_hybrid_osr_evidence_gate_v2"
)

CALIB_KNOWN_FALSE_UNKNOWN_RATE = 0.05
BOOTSTRAP_REPS = 1000
BOOTSTRAP_RNG_OFFSET = 163000

# H1: RF reproduction tolerance vs frozen V1 result JSONs.
H1_TOL = 1e-3
# H2 (V1 A2): pooled AUROC >= RF pooled - 0.02; rotation floor -0.05.
H2_POOLED_DELTA = -0.02
H2_ROTATION_FLOOR = -0.05
# H3 (V1 A3 + AUPR): recall pooled -0.03 / rotation -0.05; AUPR same.
H3_POOLED_DELTA = -0.03
H3_ROTATION_FLOOR = -0.05
# H4 (V1 A4): pooled mean delta >= +0.010; positive >= 2/3; CI lower > -0.02.
H4_POOLED_MEAN_MIN = 0.010
H4_POSITIVE_ROTATIONS_MIN = 2
H4_CI_LOWER_MIN = -0.02

# Deployable (V1 D thresholds carried over + Known-F1 protection).
D1_POOLED_FURK_DELTA_MAX = -0.02
D1_IMPROVE_ROTATIONS_MIN = 2
D1_ROTATION_WORST = 0.02
D3_AUROC_POOLED_LOSS_MAX = 0.01
D3_AUROC_ROTATION_LOSS_MAX = 0.03
D4_RECALL_POOLED_LOSS_MAX = 0.03
D4_RECALL_ROTATION_LOSS_MAX = 0.05
D5_F1_POOLED_LOSS_MAX = 0.01
D5_F1_ROTATION_LOSS_MAX = 0.02

# Recovery / specificity (strengthened V1 philosophy).
R1_POOLED_RATE_MIN = 0.60
R2_ROTATION_RATE_MIN = 0.55
R2_ROTATIONS_MIN = 2

ROUTER_HEADROOM_RECOVERY_RATE_MAX = 0.85
ROUTER_HEADROOM_ROTATIONS_MIN = 2

ACTION_MODEL_INV = {v: k for k, v in ACTION_MODEL.items()}


def set_determinism() -> dict[str, Any]:
    settings = {
        "PYTHONHASHSEED": os.environ.get("PYTHONHASHSEED", "unset"),
        "numpy_generators_only": True,
        "torch_manual_seed_per_cell": True,
        "torch_cuda_manual_seed_all": True,
        "cudnn_deterministic": True,
        "cudnn_benchmark": False,
        "dataloader_workers": 0,
    }
    random.seed(0)
    torch.backends.cudnn.deterministic = True
    torch.backends.cudnn.benchmark = False
    return settings


# ---------------------------------------------------------------------------
# Neural training (V1-frozen semantics + per-epoch logging + persistence)
# ---------------------------------------------------------------------------

def train_encoder_v2(model: nn.Module, features: dict[str, np.ndarray],
                     labels_n: np.ndarray, fit_mask: np.ndarray,
                     early_mask: np.ndarray, rng: np.random.Generator,
                     seed: int, epoch_log_path: Path,
                     use_edl: bool = False
                     ) -> tuple[nn.Module, int, list[dict[str, Any]]]:
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)
    device = "cuda" if torch.cuda.is_available() else "cpu"
    model = model.to(device)
    train_idx = np.flatnonzero(fit_mask)
    early_idx = np.flatnonzero(early_mask)

    def make_tensors(idx: np.ndarray, state_ids: np.ndarray):
        basic = torch.tensor(features["B"][idx], dtype=torch.float32,
                             device=device)
        temporal = torch.tensor(state_temporal(features, "BTR", idx),
                                dtype=torch.float32, device=device)
        relation = torch.tensor(state_relation(features, "BTR", idx),
                                dtype=torch.float32, device=device)
        m_t = torch.tensor(
            [1.0 if "T" in EVIDENCE_STATES[int(s)] else 0.0
             for s in state_ids], dtype=torch.float32,
            device=device).unsqueeze(-1)
        m_r = torch.tensor(
            [1.0 if "R" in EVIDENCE_STATES[int(s)] else 0.0
             for s in state_ids], dtype=torch.float32,
            device=device).unsqueeze(-1)
        return basic, temporal, relation, m_t, m_r

    def early_loss(state_ids: np.ndarray) -> float:
        model.eval()
        total, count = 0.0, 0
        with torch.no_grad():
            for start in range(0, len(early_idx), BATCH_SIZE):
                chunk = early_idx[start:start + BATCH_SIZE]
                st = state_ids[start:start + BATCH_SIZE]
                b, t, r, mt, mr = make_tensors(chunk, st)
                y = torch.tensor(labels_n[chunk], device=device)
                if use_edl:
                    loss = edl_loss(model(b, t, r, mt, mr), y)
                else:
                    _, logits = model(b, t, r, mt, mr)
                    loss = nn.functional.cross_entropy(logits, y)
                total += float(loss) * len(chunk)
                count += len(chunk)
        model.train()
        return total / max(count, 1)

    optimizer = torch.optim.AdamW(
        model.parameters(), lr=ADAMW_LR, weight_decay=ADAMW_WEIGHT_DECAY)
    best_loss, best_state, stale = float("inf"), None, 0
    epochs_run = 0
    records = []
    early_states = np.zeros(len(early_idx), dtype=np.int64)
    for epoch in range(MAX_EPOCHS):
        epochs_run = epoch + 1
        order = rng.permutation(len(train_idx))
        batch_states = rng.integers(0, len(EVIDENCE_STATES),
                                    size=len(train_idx))
        ce_sum, sup_sum = 0.0, 0.0
        model.train()
        for start in range(0, len(order), BATCH_SIZE):
            pos = order[start:start + BATCH_SIZE]
            chunk = train_idx[pos]
            b, t, r, mt, mr = make_tensors(chunk, batch_states[pos])
            y = torch.tensor(labels_n[chunk], device=device)
            if use_edl:
                loss = edl_loss(model(b, t, r, mt, mr), y)
                ce = sup = loss
            else:
                emb, logits = model(b, t, r, mt, mr)
                ce = nn.functional.cross_entropy(logits, y)
                sup = supervised_contrastive_loss(emb, y)
                loss = ce + SUPCON_WEIGHT * sup
            optimizer.zero_grad()
            loss.backward()
            optimizer.step()
            ce_sum += float(ce.detach()) * len(chunk)
            sup_sum += float(sup.detach()) * len(chunk)
        val_loss = early_loss(early_states)
        is_best = val_loss < best_loss - 1e-6
        if is_best:
            best_loss, stale = val_loss, 0
            best_state = {k: v.detach().clone()
                          for k, v in model.state_dict().items()}
        else:
            stale += 1
        records.append({
            "epoch": epoch + 1,
            "train_ce": ce_sum / len(train_idx),
            "train_supcon": sup_sum / len(train_idx),
            "early_stop_ce": val_loss,
            "learning_rate": float(optimizer.param_groups[0]["lr"]),
            "is_best": bool(is_best),
            "stale": stale,
        })
        if stale >= EARLY_STOP_PATIENCE:
            break
    if best_state is not None:
        model.load_state_dict(best_state)
    model.eval()
    with open(epoch_log_path, "w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record) + "\n")
    return model.cpu(), epochs_run, records


# ---------------------------------------------------------------------------
# Frozen RF component (read-only)
# ---------------------------------------------------------------------------

def load_frozen_rf(seed: int, rotation: str, owg_root: Path) -> dict:
    with open(owg_root / "models" /
              f"owg_v1_seed_{seed}_rotation_{rotation}_models.pkl",
              "rb") as handle:
        return pickle.load(handle)["models"]


def rf_predict_state(models: dict, features_ev: dict, state: str,
                     indices: np.ndarray) -> np.ndarray:
    if state == "B":
        matrix = features_ev["B"]
    elif state == "BT":
        matrix = features_ev["BT"]
    elif state == "BR":
        matrix = features_ev["BR"]
    else:
        matrix = features_ev["BTR"]
    return np.array(models[state].predict(matrix[indices]), dtype=object)


def verify_rf_reproduction(seed: int, rotation: str, owg_root: Path,
                           cell: dict) -> dict[str, Any]:
    """Cross-verify frozen-model predictions against stored P0/P6 preds
    and frozen result JSON known_macro_f1 (H1 inputs)."""
    models = load_frozen_rf(seed, rotation, owg_root)
    n = len(cell["ev_labels"])
    pred_b = rf_predict_state(models, cell["features_ev"], "B",
                              np.arange(n))
    stored_p0 = cell["ev_pred_p0"]
    mism_p0 = int((pred_b != stored_p0).sum())
    # Per-state predictions under the stored P6 action.
    pred_p6_recomputed = np.empty(n, dtype=object)
    for state in EVIDENCE_STATES:
        mask = cell["ev_action_p6"] == ACTION_MODEL_INV[state]
        if mask.any():
            pred_p6_recomputed[mask] = rf_predict_state(
                models, cell["features_ev"], state, np.flatnonzero(mask))
    mism_p6 = int((pred_p6_recomputed != cell["ev_pred_p6"]).sum())
    frozen = json.loads(
        (owg_root / f"owg_v1_seed_{seed}_rotation_{rotation}_result.json"
         ).read_text(encoding="utf-8"))
    out = {"rf_p0_mismatch": mism_p0, "rf_p6_mismatch": mism_p6}
    for pol_key, field in (("P0_BASIC_DIRECT", "pred_p0"),
                           ("P6_UTILITY_TYPED", "pred_p6")):
        frozen_f1 = float(frozen["policies"][pol_key]["known_macro_f1"])
        ev = (cell["ev_split_role"] == 1) & (~cell["ev_is_unknown"])
        if field == "pred_p0":
            f1_now = float(f1_score(cell["ev_labels"][ev],
                                    stored_p0[ev], average="macro"))
        else:
            f1_now = float(f1_score(cell["ev_labels"][ev],
                                    cell["ev_pred_p6"][ev],
                                    average="macro"))
        out[f"{pol_key}_f1_frozen"] = frozen_f1
        out[f"{pol_key}_f1_now"] = f1_now
        out[f"{pol_key}_f1_abs_diff"] = abs(f1_now - frozen_f1)
    return out


# ---------------------------------------------------------------------------
# Cell execution
# ---------------------------------------------------------------------------

def run_cell(args, seed: int, rotation: str) -> dict[str, Any]:
    started = time.monotonic()
    cell = assemble_cell(seed, rotation, Path(args.owg_root),
                         Path(args.gate1_root))
    out: dict[str, Any] = {"seed": seed, "rotation": rotation,
                           "known": list(cell["known"])}
    rng = cell_rng(seed, rotation, RNG_BASE)

    # --- H1: frozen RF reproduction (before any formal hybrid metric) ---
    rf_check = verify_rf_reproduction(seed, rotation, Path(args.owg_root),
                                      cell)
    out["rf_reproduction"] = rf_check
    h1_ok = (rf_check["rf_p0_mismatch"] == 0 and
             rf_check["rf_p6_mismatch"] == 0 and
             rf_check["P0_BASIC_DIRECT_f1_abs_diff"] <= 1e-3 and
             rf_check["P6_UTILITY_TYPED_f1_abs_diff"] <= 1e-3)
    out["h1_ok"] = bool(h1_ok)
    print(f"[{seed} {rotation}] RF reproduction: p0_mismatch="
          f"{rf_check['rf_p0_mismatch']} p6_mismatch="
          f"{rf_check['rf_p6_mismatch']} f1_diffs="
          f"{rf_check['P0_BASIC_DIRECT_f1_abs_diff']:.6f}/"
          f"{rf_check['P6_UTILITY_TYPED_f1_abs_diff']:.6f} -> "
          f"H1={'OK' if h1_ok else 'FAIL'}", flush=True)
    if not h1_ok:
        out["status"] = "FAILED_H1"
        out["seconds"] = round(time.monotonic() - started, 1)
        return out

    # --- Train neural encoder (V1-frozen semantics, determinism on) ---
    labels_n = class_codes(cell, cell["train_labels"])
    model = StrongOSREncoder()
    cell_dir = Path(args.run_root) / "cells" / cell_key(seed, rotation)
    cell_dir.mkdir(parents=True, exist_ok=True)
    model, epochs_run, records = train_encoder_v2(
        model, cell["features_train"], labels_n, fit_mask=~cell["early"],
        early_mask=cell["early"], rng=rng, seed=seed,
        epoch_log_path=cell_dir / "epochs.jsonl")
    torch.save(model.state_dict(), cell_dir / "model.pt")
    out["train_epochs_run"] = epochs_run
    out["train_best_epoch"] = max((i + 1 for i, r in enumerate(records)
                                   if r["is_best"]), default=epochs_run)
    print(f"[{seed} {rotation}] trained epochs={epochs_run}", flush=True)

    # --- Embeddings and geometry per state ---
    fit_idx = np.flatnonzero(~cell["early"])
    fit_label_names = cell["train_labels"][fit_idx]
    geometries = {}
    for state in EVIDENCE_STATES:
        emb_fit, _ = encoder_forward(model, cell["features_train"], state,
                                     fit_idx)
        geometries[state] = fit_osr_geometry(emb_fit, fit_label_names,
                                             cell["known"])

    ev_n = len(cell["ev_labels"])
    ev_positions = np.arange(ev_n)
    scores_by_state: dict[str, np.ndarray] = {}
    proba_by_state: dict[str, np.ndarray] = {}
    emb_by_state: dict[str, np.ndarray] = {}
    for state in EVIDENCE_STATES:
        emb, proba = encoder_forward(model, cell["features_ev"], state,
                                     ev_positions)
        scores_by_state[state] = mahalanobis_min_distance(
            emb, geometries[state])
        proba_by_state[state] = proba
        emb_by_state[state] = emb
    np.savez_compressed(
        cell_dir / "embeddings.npz",
        **{f"emb_{s}": emb_by_state[s].astype(np.float32)
           for s in EVIDENCE_STATES}, allow_pickle=False)

    calib_known = (cell["ev_split_role"] == 0) & (~cell["ev_is_unknown"])
    ev_known = (cell["ev_split_role"] == 1) & (~cell["ev_is_unknown"])
    ev_unknown = (cell["ev_split_role"] == 1) & cell["ev_is_unknown"]

    # --- Hybrid policy assembly (RF class + neural novelty) ---
    rf_policy_pred = {}
    rf_policy_pred["D0_BASIC"] = cell["ev_pred_p0"]
    rf_policy_pred["D1_P6_SELECTIVE"] = cell["ev_pred_p6"]
    models = load_frozen_rf(seed, rotation, Path(args.owg_root))
    rf_policy_pred["D2_ALWAYS_FULL"] = rf_predict_state(
        models, cell["features_ev"], "BTR", ev_positions)
    d3_states = policy_states(cell, "D3_RANDOM_COST_MATCHED")
    d3_pred = np.empty(ev_n, dtype=object)
    for state in ("B", "BT"):
        mask = d3_states == state
        if mask.any():
            d3_pred[mask] = rf_predict_state(models, cell["features_ev"],
                                             state, np.flatnonzero(mask))
    rf_policy_pred["D3_RANDOM_COST_MATCHED"] = d3_pred

    policy_score: dict[str, np.ndarray] = {}
    for pol in ("D0_BASIC", "D1_P6_SELECTIVE", "D2_ALWAYS_FULL",
                "D3_RANDOM_COST_MATCHED"):
        policy_score[pol] = state_score_map(
            scores_by_state, policy_states(cell, pol))
    thresholds = {pol: float(np.quantile(
        policy_score[pol][calib_known],
        1.0 - CALIB_KNOWN_FALSE_UNKNOWN_RATE)) for pol in policy_score}
    rejected = {pol: policy_score[pol] >= thresholds[pol]
                for pol in policy_score}
    # Per-state thresholds for the offline recovery oracle (Known-only).
    state_thresholds = {s: float(np.quantile(
        scores_by_state[s][calib_known],
        1.0 - CALIB_KNOWN_FALSE_UNKNOWN_RATE)) for s in EVIDENCE_STATES}
    out["thresholds"] = thresholds
    out["state_thresholds"] = state_thresholds

    # --- Frozen RF Basic baseline (H2/H3 authority, stored P0) ---
    rf_known = cell["ev_score_p0"][ev_known]
    rf_unknown = cell["ev_score_p0"][ev_unknown]
    out["rf_basic"] = {
        "auroc": known_unknown_auroc(rf_known, rf_unknown),
        "aupr": known_unknown_aupr(rf_known, rf_unknown),
        "recall_at_5fur": recall_at_5fur(rf_known, rf_unknown),
        "macro_f1": float(f1_score(cell["ev_labels"][ev_known],
                                   cell["ev_pred_p0"][ev_known],
                                   average="macro")),
    }
    out["neural_basic"] = {
        "auroc": known_unknown_auroc(scores_by_state["B"][ev_known],
                                     scores_by_state["B"][ev_unknown]),
        "aupr": known_unknown_aupr(scores_by_state["B"][ev_known],
                                   scores_by_state["B"][ev_unknown]),
        "recall_at_5fur": recall_at_5fur(scores_by_state["B"][ev_known],
                                         scores_by_state["B"][ev_unknown]),
        "auroc_msp": known_unknown_auroc(deep_msp(proba_by_state["B"])[
            ev_known], deep_msp(proba_by_state["B"])[ev_unknown]),
    }

    # --- Hybrid deployable metrics ---
    dep = {}
    for pol in ("D0_BASIC", "D1_P6_SELECTIVE", "D2_ALWAYS_FULL",
                "D3_RANDOM_COST_MATCHED"):
        rej_kn = rejected[pol][ev_known]
        rec_kn = cell["ev_recoverable"][ev_known]
        furk, numer, denom = furk_of(rej_kn, rec_kn)
        accept_correct = (~rej_kn) & (rf_policy_pred[pol][ev_known] ==
                                      cell["ev_labels"][ev_known])
        dep[pol] = {
            "furk": furk, "furk_numer": numer, "furk_denom": denom,
            "recoverable_known_accept_correct_rate": float(
                (accept_correct & rec_kn).sum() /
                rec_kn.sum()) if rec_kn.sum() else float("nan"),
            "known_macro_f1": float(f1_score(
                cell["ev_labels"][ev_known],
                rf_policy_pred[pol][ev_known], average="macro")),
            "known_false_unknown_rate": float(rej_kn.mean()),
            "unknown_auroc": known_unknown_auroc(
                policy_score[pol][ev_known],
                policy_score[pol][ev_unknown]),
            "unknown_aupr": known_unknown_aupr(
                policy_score[pol][ev_known],
                policy_score[pol][ev_unknown]),
            "unknown_recall_at_5fur": recall_at_5fur(
                policy_score[pol][ev_known],
                policy_score[pol][ev_unknown]),
            "acquisition_rate": float((
                policy_states(cell, pol) != "B").mean()),
            "true_unknown_acquisition_rate": float((
                policy_states(cell, pol)[ev_unknown] != "B").mean())
            if ev_unknown.any() else float("nan"),
        }
    out["d"] = dep

    # --- Offline recovery oracle + specificity ---
    bc, row_data = hybrid_bc_rows(cell, models, scores_by_state,
                                  state_thresholds)
    if row_data is not None:
        np.savez_compressed(cell_dir / "bc_rows.npz", **row_data,
                            allow_pickle=False)
    out.update(bc)

    # --- Per-row persistence for bootstrap ---
    np.savez_compressed(
        cell_dir / "rows.npz",
        groups=group_codes(cell["ev_groups"]),
        is_unknown=cell["ev_is_unknown"],
        split_role=cell["ev_split_role"],
        recoverable=cell["ev_recoverable"],
        score_d0=policy_score["D0_BASIC"],
        score_d1=policy_score["D1_P6_SELECTIVE"],
        score_b_maha=scores_by_state["B"],
        score_b_msp=deep_msp(proba_by_state["B"]),
        pred_rf_d0=np.array([cell["known"].index(x) for x in
                             rf_policy_pred["D0_BASIC"]], dtype=np.int64),
        pred_rf_d1=np.array([cell["known"].index(x) for x in
                             rf_policy_pred["D1_P6_SELECTIVE"]],
                            dtype=np.int64),
        label_code=np.array([cell["known"].index(x) if x in cell["known"]
                             else -1 for x in cell["ev_labels"]],
                            dtype=np.int64),
        allow_pickle=False)
    out["status"] = "COMPLETE"
    out["seconds"] = round(time.monotonic() - started, 1)
    return out


# ---------------------------------------------------------------------------
# Hybrid recovery/specificity rows (primary and safeguards)
# ---------------------------------------------------------------------------

def hybrid_bc_rows(cell: dict, models: dict,
                   scores_by_state: dict[str, np.ndarray],
                   state_thresholds: dict[str, float]
                   ) -> tuple[dict[str, Any], dict[str, Any] | None]:
    rec_rows = np.flatnonzero(cell["ev_recoverable"] &
                              (~cell["ev_is_unknown"]))
    unk_rows = np.flatnonzero(cell["ev_is_unknown"])
    bc: dict[str, Any] = {}
    if not len(rec_rows):
        return bc, None
    rf_state_pred = {}
    for state in EVIDENCE_STATES:
        rf_state_pred[state] = rf_predict_state(models, cell["features_ev"],
                                                state, rec_rows)
    true_class = cell["ev_labels"][rec_rows]
    accepted = {s: scores_by_state[s][rec_rows] < state_thresholds[s]
                for s in EVIDENCE_STATES}
    recovered = {s: accepted[s] & (rf_state_pred[s] == true_class)
                 for s in EVIDENCE_STATES}
    best_legal = np.stack([recovered[s] for s in LEGAL_STATES]
                          ).max(axis=0)
    bc["recovery"] = {
        "basic_accept_correct_rate": float(recovered["B"].mean()),
        "best_legal_accept_correct_rate": float(best_legal.mean()),
        "rate_delta": float(best_legal.mean() - recovered["B"].mean()),
        "n_recoverable": int(len(rec_rows)),
    }
    rk_gain = np.stack([scores_by_state["B"][rec_rows] -
                        scores_by_state[s][rec_rows]
                        for s in LEGAL_STATES]).max(axis=0)
    row_data = {
        "rk_gain": rk_gain.astype(np.float64),
        "rk_groups": group_codes(cell["ev_groups"][rec_rows]),
        "rec_basic": recovered["B"].astype(bool),
        "rec_best": best_legal.astype(bool),
        "tu_gain": np.zeros(0, dtype=np.float64),
        "tu_groups": np.zeros(0, dtype=np.int64),
    }
    if len(unk_rows):
        tu_gain = np.stack([scores_by_state["B"][unk_rows] -
                            scores_by_state[s][unk_rows]
                            for s in LEGAL_STATES]).max(axis=0)
        bc["specificity"] = {
            "mean_rk_gain": float(rk_gain.mean()),
            "mean_tu_gain": float(tu_gain.mean()),
            "median_rk_gain": float(np.median(rk_gain)),
            "median_tu_gain": float(np.median(tu_gain)),
            "mean_gap": float(rk_gain.mean() - tu_gain.mean()),
            "median_gap": float(np.median(rk_gain) -
                                np.median(tu_gain)),
            "ratio_ok": bool(tu_gain.mean() <= C3_RATIO_BOUND *
                             rk_gain.mean()) if rk_gain.mean() > 0
            else False,
            "n_unknown": int(len(unk_rows)),
        }
        row_data["tu_gain"] = tu_gain.astype(np.float64)
        row_data["tu_groups"] = group_codes(cell["ev_groups"][unk_rows])
    return bc, row_data


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------

def _rot_means(cells, fn):
    out = {}
    for r in ROTATIONS:
        vals = [fn(c) for c in cells.values() if c["rotation"] == r]
        out[r] = float(np.nanmean(vals))
    return out


def _pooled(rot_vals):
    return float(np.mean(list(rot_vals.values())))


def _ci_pooled_cells(payloads, cell_metric, n_reps=BOOTSTRAP_REPS,
                     offset=BOOTSTRAP_RNG_OFFSET):
    rng = np.random.default_rng(offset)
    reps = []
    for _ in range(n_reps):
        vals = []
        for payload in payloads:
            uniq = np.unique(payload["groups"])
            sampled = rng.choice(uniq, size=len(uniq), replace=True)
            mask = np.isin(payload["groups"], sampled)
            vals.append(cell_metric(payload, mask))
        reps.append(float(np.mean(vals)))
    reps = np.array(reps)
    return (float(reps.mean()), float(np.percentile(reps, 2.5)),
            float(np.percentile(reps, 97.5)))


def aggregate_v2(cells: dict[str, dict[str, Any]], run_root: Path,
                 owg_root: Path) -> dict[str, Any]:
    rot = {r: [c for c in cells.values() if c["rotation"] == r]
           for r in ROTATIONS}

    # --- H1 ---
    h1_diffs = {c["seed"]: c["rf_reproduction"] for c in cells.values()}
    h1_ok = all(c.get("h1_ok") for c in cells.values())
    h1 = {"pass": bool(h1_ok),
          "max_f1_abs_diff": float(max(
              max(c["rf_reproduction"]["P0_BASIC_DIRECT_f1_abs_diff"],
                  c["rf_reproduction"]["P6_UTILITY_TYPED_f1_abs_diff"])
              for c in cells.values()))}

    # --- H2 ---
    nb = _rot_means(cells, lambda c: c["neural_basic"]["auroc"])
    rb = _rot_means(cells, lambda c: c["rf_basic"]["auroc"])
    h2 = (float(_pooled(nb)) >= float(_pooled(rb)) + H2_POOLED_DELTA) and \
        all(nb[r] >= rb[r] + H2_ROTATION_FLOOR for r in ROTATIONS)

    # --- H3 ---
    nb_rec = _rot_means(cells,
                        lambda c: c["neural_basic"]["recall_at_5fur"])
    rb_rec = _rot_means(cells, lambda c: c["rf_basic"]["recall_at_5fur"])
    nb_aupr = _rot_means(cells, lambda c: c["neural_basic"]["aupr"])
    rb_aupr = _rot_means(cells, lambda c: c["rf_basic"]["aupr"])
    h3 = (float(_pooled(nb_rec)) >= float(_pooled(rb_rec)) +
          H3_POOLED_DELTA and
          all(nb_rec[r] >= rb_rec[r] + H3_ROTATION_FLOOR for r in ROTATIONS)
          and float(_pooled(nb_aupr)) >= float(_pooled(rb_aupr)) +
          H3_POOLED_DELTA and
          all(nb_aupr[r] >= rb_aupr[r] + H3_ROTATION_FLOOR
              for r in ROTATIONS))

    # --- H4 ---
    delta_rot = {r: float(np.nanmean([
        c["neural_basic"]["auroc"] - c["neural_basic"]["auroc_msp"]
        for c in rot[r]])) for r in ROTATIONS}
    payloads = []
    for seed in FORMAL_SEEDS:
        for r in ROTATIONS:
            key = cell_key(seed, r)
            rows = np.load(run_root / "cells" / key / "rows.npz")
            payloads.append({
                "groups": rows["groups"],
                "is_unknown": rows["is_unknown"],
                "split_role": rows["split_role"],
                "maha": rows["score_b_maha"],
                "msp": rows["score_b_msp"],
            })

    def h4_cell_metric(p, mask):
        ev = (p["split_role"] == 1) & mask
        kn = ev & (~p["is_unknown"])
        un = ev & p["is_unknown"]
        a_maha = known_unknown_auroc(p["maha"][kn], p["maha"][un])
        a_msp = known_unknown_auroc(p["msp"][kn], p["msp"][un])
        return a_maha - a_msp

    h4_ci = _ci_pooled_cells(payloads, h4_cell_metric,
                             offset=BOOTSTRAP_RNG_OFFSET + 5)
    h4 = (float(np.mean(list(delta_rot.values()))) >= H4_POOLED_MEAN_MIN
          and sum(1 for r in ROTATIONS if delta_rot[r] > 0) >=
          H4_POSITIVE_ROTATIONS_MIN and h4_ci[1] > H4_CI_LOWER_MIN)

    adequacy = {"pass": bool(h1_ok and h2 and h3 and h4),
                "h1": h1, "h2": {"neural": nb, "rf": rb, "pass": bool(h2)},
                "h3": {"neural_recall": nb_rec, "rf_recall": rb_rec,
                       "neural_aupr": nb_aupr, "rf_aupr": rb_aupr,
                       "pass": bool(h3)},
                "h4": {"delta_rot": delta_rot, "ci": list(h4_ci),
                       "pass": bool(h4)}}

    # --- Deployable ---
    furk0 = _rot_means(cells, lambda c: c["d"]["D0_BASIC"]["furk"])
    furk1 = _rot_means(cells, lambda c: c["d"]["D1_P6_SELECTIVE"]["furk"])
    furk_delta = {r: furk1[r] - furk0[r] for r in ROTATIONS}
    d1_ok = (float(_pooled(furk_delta)) <= D1_POOLED_FURK_DELTA_MAX and
             sum(1 for r in ROTATIONS if furk_delta[r] < 0) >=
             D1_IMPROVE_ROTATIONS_MIN and
             all(furk_delta[r] <= D1_ROTATION_WORST for r in ROTATIONS))
    auroc0 = _rot_means(cells, lambda c: c["d"]["D0_BASIC"]["unknown_auroc"])
    auroc1 = _rot_means(cells, lambda c: c["d"][
        "D1_P6_SELECTIVE"]["unknown_auroc"])
    auroc_loss = {r: auroc0[r] - auroc1[r] for r in ROTATIONS}
    d3_ok = (float(_pooled(auroc_loss)) <= D3_AUROC_POOLED_LOSS_MAX and
             all(auroc_loss[r] <= D3_AUROC_ROTATION_LOSS_MAX
                 for r in ROTATIONS))
    rec0 = _rot_means(cells, lambda c: c["d"][
        "D0_BASIC"]["unknown_recall_at_5fur"])
    rec1 = _rot_means(cells, lambda c: c["d"][
        "D1_P6_SELECTIVE"]["unknown_recall_at_5fur"])
    recall_loss = {r: rec0[r] - rec1[r] for r in ROTATIONS}
    d4_ok = (float(_pooled(recall_loss)) <= D4_RECALL_POOLED_LOSS_MAX and
             all(recall_loss[r] <= D4_RECALL_ROTATION_LOSS_MAX
                 for r in ROTATIONS))
    f10 = _rot_means(cells, lambda c: c["d"]["D0_BASIC"]["known_macro_f1"])
    f11 = _rot_means(cells, lambda c: c["d"][
        "D1_P6_SELECTIVE"]["known_macro_f1"])
    f1_loss = {r: f10[r] - f11[r] for r in ROTATIONS}
    d5_ok = (float(_pooled(f1_loss)) <= D5_F1_POOLED_LOSS_MAX and
             all(f1_loss[r] <= D5_F1_ROTATION_LOSS_MAX for r in ROTATIONS))
    d2_ci = _furk_paired_ci_v2(run_root)
    d2_ok = d2_ci[2] < 0
    deployable = {"pass": bool(d1_ok and d2_ok and d3_ok and d4_ok and
                               d5_ok),
                  "d1": {"furk_delta": furk_delta, "pass": bool(d1_ok)},
                  "d2": {"furk_ci": list(d2_ci), "pass": bool(d2_ok)},
                  "d3": {"auroc_loss": auroc_loss, "pass": bool(d3_ok)},
                  "d4": {"recall_loss": recall_loss, "pass": bool(d4_ok)},
                  "d5": {"f1_loss": f1_loss, "pass": bool(d5_ok)}}

    # --- Recovery ---
    rec_rate_basic = _rot_means(cells, lambda c: c["recovery"][
        "basic_accept_correct_rate"])
    rec_rate_best = _rot_means(cells, lambda c: c["recovery"][
        "best_legal_accept_correct_rate"])
    r_payloads = []
    for seed in FORMAL_SEEDS:
        for r in ROTATIONS:
            key = cell_key(seed, r)
            rows = np.load(run_root / "cells" / key / "bc_rows.npz",
                           allow_pickle=False)
            r_payloads.append({"groups": rows["rk_groups"],
                               "rec_basic": rows["rec_basic"],
                               "rec_best": rows["rec_best"]})

    def r_cell_metric(p, mask):
        return float(p["rec_best"][mask].mean() -
                     p["rec_basic"][mask].mean())

    r_ci = _ci_pooled_cells(r_payloads, r_cell_metric,
                            offset=BOOTSTRAP_RNG_OFFSET + 9)
    r1_ok = float(_pooled(rec_rate_best)) >= R1_POOLED_RATE_MIN
    r2_ok = sum(1 for r in ROTATIONS if rec_rate_best[r] >
                R2_ROTATION_RATE_MIN) >= R2_ROTATIONS_MIN
    r_ci_ok = r_ci[1] > 0
    recovery = {"pass": bool(r1_ok and r2_ok and r_ci_ok),
                "basic_rate": rec_rate_basic,
                "best_legal_rate": rec_rate_best,
                "delta_ci": list(r_ci),
                "r1": bool(r1_ok), "r2": bool(r2_ok),
                "ci_ok": bool(r_ci_ok)}

    # --- Specificity ---
    gap_rot = _rot_means(cells,
                         lambda c: c["specificity"]["mean_gap"])
    median_gap_pool = float(np.nanmean([
        c["specificity"]["median_gap"] for c in cells.values()]))
    ratio_ok_all = all(c["specificity"]["ratio_ok"]
                       for c in cells.values())
    s_ci = _specificity_ci(run_root)
    specificity = {"pass": bool(float(_pooled(gap_rot)) > 0 and
                                median_gap_pool > 0 and ratio_ok_all and
                                sum(1 for r in ROTATIONS if gap_rot[r] > 0)
                                >= 2 and s_ci[1] > 0),
                   "gap_rot": gap_rot,
                   "median_gap_pool": median_gap_pool,
                   "ratio_ok_all": bool(ratio_ok_all),
                   "ci": list(s_ci)}

    # --- Router headroom (stored P6 predictions, frozen result JSONs) ---
    recovery_rot = {}
    for r in ROTATIONS:
        vals = []
        for c in rot[r]:
            frozen = json.loads(
                (owg_root / f"owg_v1_seed_{c['seed']}_rotation_{r}"
                           f"_result.json").read_text(encoding="utf-8"))
            vals.append(float(frozen["policies"]["P6_UTILITY_TYPED"][
                "evidence_recovery_rate"]))
        recovery_rot[r] = float(np.mean(vals))
    headroom = sum(1 for r in ROTATIONS
                   if recovery_rot[r] <= ROUTER_HEADROOM_RECOVERY_RATE_MAX
                   ) >= ROUTER_HEADROOM_ROTATIONS_MIN

    decision = _decide_v2(adequacy["pass"], recovery["pass"],
                          specificity["pass"], deployable["pass"],
                          headroom)
    return {"adequacy": adequacy, "recovery": recovery,
            "specificity": specificity, "deployable": deployable,
            "headroom": {"p6_recovery_rate": recovery_rot,
                         "material": bool(headroom)},
            "decision": decision}


def _specificity_ci(run_root: Path) -> tuple[float, float, float]:
    """Pooled paired group-atomic bootstrap CI of the RK-vs-TU gain gap;
    Recoverable-Known and True-Unknown groups resampled independently."""
    rng = np.random.default_rng(BOOTSTRAP_RNG_OFFSET + 13)
    payloads = []
    for seed in FORMAL_SEEDS:
        for r in ROTATIONS:
            key = cell_key(seed, r)
            rows = np.load(run_root / "cells" / key / "bc_rows.npz",
                           allow_pickle=False)
            payloads.append((rows["rk_groups"], rows["rk_gain"],
                             rows["tu_groups"], rows["tu_gain"]))
    reps = []
    for _ in range(BOOTSTRAP_REPS):
        vals = []
        for rk_grp, rk_gain, tu_grp, tu_gain in payloads:
            uniq_rk = np.unique(rk_grp)
            sample_rk = rng.choice(uniq_rk, size=len(uniq_rk),
                                   replace=True)
            mask_rk = np.isin(rk_grp, sample_rk)
            if len(tu_gain):
                uniq_tu = np.unique(tu_grp)
                sample_tu = rng.choice(uniq_tu, size=len(uniq_tu),
                                       replace=True)
                mask_tu = np.isin(tu_grp, sample_tu)
                vals.append(float(rk_gain[mask_rk].mean() -
                                  tu_gain[mask_tu].mean()))
            else:
                vals.append(float(rk_gain[mask_rk].mean()))
        reps.append(float(np.mean(vals)))
    reps = np.array(reps)
    return (float(reps.mean()), float(np.percentile(reps, 2.5)),
            float(np.percentile(reps, 97.5)))


def _furk_paired_ci_v2(run_root: Path) -> tuple[float, float, float]:
    rng = np.random.default_rng(BOOTSTRAP_RNG_OFFSET + 7)
    payloads = []
    for seed in FORMAL_SEEDS:
        for r in ROTATIONS:
            key = cell_key(seed, r)
            rows = np.load(run_root / "cells" / key / "rows.npz")
            payloads.append((rows["groups"], rows["is_unknown"],
                             rows["split_role"], rows["recoverable"],
                             rows["score_d0"], rows["score_d1"]))
    reps = []
    for _ in range(BOOTSTRAP_REPS):
        vals = []
        for groups, is_unk, role, rec, s0, s1 in payloads:
            uniq = np.unique(groups)
            sampled = rng.choice(uniq, size=len(uniq), replace=True)
            mask = np.isin(groups, sampled)
            ev = (role == 1) & mask
            cal = (role == 0) & (~is_unk)
            thr0 = float(np.quantile(s0[cal], 0.95))
            thr1 = float(np.quantile(s1[cal], 0.95))
            rec_ev = rec[ev]
            f0 = ((s0[ev] >= thr0) & rec_ev).sum() / max(rec_ev.sum(), 1)
            f1 = ((s1[ev] >= thr1) & rec_ev).sum() / max(rec_ev.sum(), 1)
            vals.append(float(f1 - f0))
        reps.append(float(np.mean(vals)))
    reps = np.array(reps)
    return (float(reps.mean()), float(np.percentile(reps, 2.5)),
            float(np.percentile(reps, 97.5)))


def _decide_v2(adequacy: bool, recovery: bool, specificity: bool,
               deployable: bool, headroom: bool) -> str:
    if not adequacy:
        return "GATE_INVALID_OSR_INADEQUATE"
    if recovery and specificity and deployable:
        return "GO"
    if recovery and specificity and not deployable and headroom:
        return "GO_SIGNAL_EXISTS_ROUTER_LIMITED"
    if recovery and specificity:
        return "METHOD_DEPENDENT_REVIEW"
    return "NO_GO_CURRENT_EVIDENCE_CONTRACT"


# ---------------------------------------------------------------------------
# Conditional NO-GO safeguards (protocol §8, central seed only)
# ---------------------------------------------------------------------------

def _safeguard_scores_mahal(model, cell, feats_train, feats_ev):
    """Per-state Mahalanobis scores for eval rows under a raw-concat or
    primary-feature model (geometry fitted on FIT Known embeddings)."""
    fit_idx = np.flatnonzero(~cell["early"])
    geometries = {}
    for state in EVIDENCE_STATES:
        emb_fit, _ = encoder_forward(model, feats_train, state, fit_idx)
        geometries[state] = fit_osr_geometry(
            emb_fit, cell["train_labels"][fit_idx], cell["known"])
    ev_n = len(cell["ev_labels"])
    scores = {}
    for state in EVIDENCE_STATES:
        emb, _ = encoder_forward(model, feats_ev, state, np.arange(ev_n))
        scores[state] = mahalanobis_min_distance(emb, geometries[state])
    return scores


def _safeguard_scores_edl(edl, cell):
    """Per-state EDL belief-based novelty scores (V1-frozen mapping)."""
    ev_n = len(cell["ev_labels"])
    scores = {}
    for state in EVIDENCE_STATES:
        alpha, _ = encoder_forward(edl, cell["features_ev"], state,
                                   np.arange(ev_n), use_edl=True)
        belief = alpha.max(axis=-1) / alpha.sum(axis=-1)
        scores[state] = 1.0 - belief
    return scores


def _safeguard_cell_agg(cell, models, scores_by_state) -> dict[str, Any]:
    calib_known = (cell["ev_split_role"] == 0) & (~cell["ev_is_unknown"])
    state_thresholds = {s: float(np.quantile(
        scores_by_state[s][calib_known],
        1.0 - CALIB_KNOWN_FALSE_UNKNOWN_RATE)) for s in EVIDENCE_STATES}
    bc, _ = hybrid_bc_rows(cell, models, scores_by_state, state_thresholds)
    bc["rotation"] = cell["rotation"]
    bc["seed"] = cell["seed"]
    return bc


def _bc_pass(bc_cells: dict[str, dict[str, Any]]) -> dict[str, bool]:
    rot = {r: [c for c in bc_cells.values() if c["rotation"] == r]
           for r in ROTATIONS}
    best = {r: float(np.nanmean([c["recovery"][
        "best_legal_accept_correct_rate"] for c in rot[r]]))
        for r in ROTATIONS}
    rec_pass = (float(np.mean(list(best.values()))) >= R1_POOLED_RATE_MIN
                and sum(1 for r in ROTATIONS if best[r] >
                        R2_ROTATION_RATE_MIN) >= R2_ROTATIONS_MIN)
    gaps = {r: float(np.nanmean([c["specificity"]["mean_gap"]
                                 for c in rot[r]
                                 if "specificity" in c]))
            for r in ROTATIONS}
    spec_pass = (float(np.mean(list(gaps.values()))) > 0 and
                 sum(1 for r in ROTATIONS if gaps[r] > 0) >= 2)
    return {"recovery_pass": bool(rec_pass),
            "specificity_pass": bool(spec_pass)}


def run_conditional_safeguards_v2(args, run_root: Path) -> dict[str, Any]:
    from run_strong_neural_osr_evidence_gate_v1 import _raw_concat_features
    out: dict[str, Any] = {"triggered": True, "A_RAW_CONCAT": {},
                           "B_EDL": {}, "contradiction": False}
    central = 20260817
    cells = {}
    for rotation in ROTATIONS:
        cells[rotation] = assemble_cell(central, rotation,
                                        Path(args.owg_root),
                                        Path(args.gate1_root))
    models_by_rot = {r: load_frozen_rf(central, r, Path(args.owg_root))
                     for r in ROTATIONS}

    # Safeguard A: raw normalized concat (V1 recipe).
    a_cells = {}
    for rotation in ROTATIONS:
        cell = cells[rotation]
        feats_raw = _raw_concat_features(cell)
        labels_n = class_codes(cell, cell["train_labels"])
        rng = cell_rng(central, rotation, RNG_BASE + 100)
        model = StrongOSREncoder()
        model, _, _ = train_encoder_v2(
            model, feats_raw, labels_n, fit_mask=~cell["early"],
            early_mask=cell["early"], rng=rng, seed=central,
            epoch_log_path=Path(args.run_root) / "cells" /
            f"safeguardA_{rotation}_epochs.jsonl")
        feats_ev = _raw_concat_eval(cell)
        scores = _safeguard_scores_mahal(model, cell, feats_raw, feats_ev)
        a_cells[rotation] = _safeguard_cell_agg(
            cell, models_by_rot[rotation], scores)
    a_pass = _bc_pass(a_cells)
    out["A_RAW_CONCAT"] = {"recovery_pass": a_pass["recovery_pass"],
                           "specificity_pass": a_pass["specificity_pass"]}

    # Safeguard B: fixed Dirichlet/evidential confirmation (V1-frozen).
    b_cells = {}
    for rotation in ROTATIONS:
        cell = cells[rotation]
        labels_n = class_codes(cell, cell["train_labels"])
        rng = cell_rng(central, rotation, RNG_BASE + 200)
        edl = EDLHeadEncoder(StrongOSREncoder())
        edl, _, _ = train_encoder_v2(
            edl, cell["features_train"], labels_n,
            fit_mask=~cell["early"], early_mask=cell["early"], rng=rng,
            seed=central, use_edl=True,
            epoch_log_path=Path(args.run_root) / "cells" /
            f"safeguardB_{rotation}_epochs.jsonl")
        scores = _safeguard_scores_edl(edl, cell)
        b_cells[rotation] = _safeguard_cell_agg(
            cell, models_by_rot[rotation], scores)
    b_pass = _bc_pass(b_cells)
    out["B_EDL"] = {"recovery_pass": b_pass["recovery_pass"],
                    "specificity_pass": b_pass["specificity_pass"],
                    "status": "RUN"}
    out["contradiction"] = bool(
        a_pass["recovery_pass"] or a_pass["specificity_pass"] or
        b_pass["recovery_pass"] or b_pass["specificity_pass"])
    return out


def _raw_concat_eval(cell: dict) -> dict[str, np.ndarray]:
    """Standardize eval raw concat with TRAIN Known statistics (V1
    recipe); dict keeps the shared 4-state shape."""
    fit = ~cell["early"]
    b = cell["features_ev"]["B"].astype(np.float64).copy()
    t = cell["features_ev"]["BTR"][:, 47:63].astype(np.float64).copy()
    r = cell["features_ev"]["BTR"][:, 63:81].astype(np.float64).copy()
    b_train = cell["features_train"]["B"].astype(np.float64)[fit]
    t_train = cell["features_train"]["BTR"][fit, 47:63].astype(np.float64)
    r_train = cell["features_train"]["BTR"][fit, 63:81].astype(np.float64)
    for block, trn in ((b, b_train), (t, t_train), (r, r_train)):
        block -= trn.mean(axis=0)
        block /= np.maximum(trn.std(axis=0), 1e-12)
    concat = np.column_stack([b, t, r])
    return {"B": concat[:, :47], "BT": concat, "BR": concat,
            "BTR": concat}


# ---------------------------------------------------------------------------
# Status persistence and cell loop
# ---------------------------------------------------------------------------

def run_formal(args) -> int:
    run_root = Path(args.run_root)
    run_root.mkdir(parents=True, exist_ok=True)
    (run_root / "cells").mkdir(exist_ok=True)
    (run_root / "logs").mkdir(exist_ok=True)
    determinism = set_determinism()
    manifest = {
        "task": "STRONG_HYBRID_OSR_EVIDENCE_RECOVERABILITY_GATE_V2",
        "protocol_sha256": args.protocol_sha256,
        "started_epoch": time.time(),
        "determinism": determinism,
        "args": vars(args),
    }
    (run_root / "run_manifest.json").write_text(
        canonical_json(manifest), encoding="utf-8")
    status = read_status(run_root)
    for seed in FORMAL_SEEDS:
        for rotation in ROTATIONS:
            key = cell_key(seed, rotation)
            if status["cells"].get(key) == "COMPLETE":
                print(f"[{key}] already COMPLETE, skipping", flush=True)
                continue
            status["cells"][key] = "RUNNING"
            write_status(run_root, status)
            log_path = run_root / "logs" / f"{key}.log"
            with open(log_path, "a", encoding="utf-8") as log:
                try:
                    cell_out = run_cell(args, seed, rotation)
                    hits = find_nonfinite(cell_out)
                    if hits:
                        raise ValueError(
                            f"non-finite metrics in cell output: {hits[:10]}")
                    (run_root / "cells" / key / f"{key}.json").write_text(
                        canonical_json(cell_out), encoding="utf-8")
                    status["cells"][key] = "COMPLETE"
                    print(f"[{key}] COMPLETE", flush=True)
                except Exception as exc:  # noqa: BLE001
                    status["cells"][key] = "FAILED"
                    write_status(run_root, status)
                    log.write(f"EXCEPTION: {exc!r}\n")
                    log.write(traceback.format_exc())
                    print(f"[{key}] FAILED: {exc!r}", flush=True)
                    continue
            write_status(run_root, status)

    if all(v == "COMPLETE" for v in status["cells"].values()):
        cell_outputs = {}
        for key in status["cells"]:
            cell_outputs[key] = json.loads(
                (run_root / "cells" / key / f"{key}.json").read_text(
                    encoding="utf-8"))
        aggregate = aggregate_v2(cell_outputs, run_root,
                                 Path(args.owg_root))
        if aggregate["decision"] == "NO_GO_CURRENT_EVIDENCE_CONTRACT" and \
                aggregate["adequacy"]["pass"]:
            safeguards = run_conditional_safeguards_v2(args, run_root)
            aggregate["safeguards"] = safeguards
            if safeguards.get("contradiction"):
                aggregate["decision"] = "METHOD_DEPENDENT_REVIEW"
        (run_root / "aggregate.json").write_text(
            canonical_json(aggregate), encoding="utf-8")
        print(f"[aggregate] DECISION={aggregate['decision']}", flush=True)
        status["run_state"] = "COMPLETE"
    else:
        status["run_state"] = "PARTIAL"
    write_status(run_root, status)
    return 0


# ---------------------------------------------------------------------------
# Smoke mode
# ---------------------------------------------------------------------------

def run_smoke(args) -> int:
    rng = np.random.default_rng(778002)
    n = 256
    known = known_classes_for("Credential")
    basic = rng.standard_normal((n, 47))
    history = np.abs(rng.standard_normal((n, 34)))
    from run_core_hypothesis_gate_v1 import (RELATION_FIELDS,
                                             TEMPORAL_FIELDS,
                                             build_feature_matrices)
    names = list(TEMPORAL_FIELDS) + list(RELATION_FIELDS)
    feats = build_feature_matrices(basic, history, names)
    labels_n = np.array([known.index(known[i % 6]) for i in range(n)],
                        dtype=np.int64)
    model = StrongOSREncoder()
    fit_mask = np.ones(n, dtype=bool)
    fit_mask[n // 2:] = False
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        model, epochs, records = train_encoder_v2(
            model, feats, labels_n, fit_mask, ~fit_mask,
            np.random.default_rng(1), 778002, Path(tmp) / "e.jsonl")
    emb, proba = encoder_forward(model, feats, "BTR", np.arange(16))
    assert emb.shape == (16, 128)
    label_names = np.array([known[i % 6] for i in range(16)],
                           dtype=object)
    geom = fit_osr_geometry(emb, label_names, known)
    scores = mahalanobis_min_distance(emb, geom)
    assert scores.shape == (16,)
    # Determinism check: same seed -> identical initialization.
    torch.manual_seed(3)
    m1 = StrongOSREncoder()
    s1 = {k: v.clone() for k, v in m1.state_dict().items()}
    torch.manual_seed(3)
    m2 = StrongOSREncoder()
    s2 = {k: v.clone() for k, v in m2.state_dict().items()}
    assert all(torch.equal(s1[k], s2[k]) for k in s1)
    print("[smoke] STRONG_HYBRID_OSR_V2_SMOKE_STATUS=PASS")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("smoke", "run"))
    parser.add_argument("--owg-root", default=DEFAULT_OWG_ROOT)
    parser.add_argument("--gate1-root", default=DEFAULT_GATE1_ROOT)
    parser.add_argument("--run-root", default=DEFAULT_RUN_ROOT)
    parser.add_argument("--protocol-sha256", default="",
                        help="frozen protocol sha256 (manifest echo)")
    args = parser.parse_args()
    if args.mode == "smoke":
        return run_smoke(args)
    return run_formal(args)


if __name__ == "__main__":
    raise SystemExit(main())
