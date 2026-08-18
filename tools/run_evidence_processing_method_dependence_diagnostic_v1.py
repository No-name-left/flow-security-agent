#!/usr/bin/env python3
"""EVIDENCE PROCESSING / METHOD DEPENDENCE DIAGNOSTIC V1.

Prospective follow-up diagnostic to Strong Hybrid OSR Evidence Gate V2
(immutable: METHOD_DEPENDENT_REVIEW). Causal/mechanistic decomposition of
the Mahalanobis-FAIL / EDL-PASS specificity contradiction:

  1. generic Evidence-presence / Evidence-distribution bias
     (REAL / NULL-PRESENT / SHUFFLED controls on the frozen primary
     encoder, forward passes only);
  2. representation / Evidence-processing effects (Mahalanobis readout on
     the frozen EDL trunk representation — reverse cross-check);
  3. final novelty-readout effects (same-representation readout test:
     one fixed Dirichlet head trained on frozen h only).

NO detector search, NO performance tuning, NO Model B / RL / continual,
NO FINAL_TEST, NO V1/V2 modification. Preregistered protocol:
docs/research_plan/evidence_processing_method_dependence_diagnostic_v1_protocol.md
(sha256 frozen in the preregistration JSON).

Outputs (Git-external):
  processed/dataset_v4_nf3_ton_v1/evidence_processing_method_dependence_diagnostic_v1/
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np

TOOLS = Path(__file__).resolve().parent
REPO = TOOLS.parent
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import torch  # noqa: E402

import run_strong_hybrid_osr_evidence_gate_v2 as v2  # noqa: E402
from run_strong_neural_osr_evidence_gate_v1 import (  # noqa: E402
    ADAMW_LR,
    ADAMW_WEIGHT_DECAY,
    BATCH_SIZE,
    EARLY_STOP_PATIENCE,
    EDLHeadEncoder,
    EVIDENCE_STATES,
    LEGAL_STATES,
    MAX_EPOCHS,
    NUM_KNOWN,
    RNG_BASE,
    ROTATIONS,
    StrongOSREncoder,
    assemble_cell,
    cell_key,
    cell_rng,
    class_codes,
    edl_loss,
    encoder_forward,
    fit_osr_geometry,
    mahalanobis_min_distance,
    state_relation,
    state_temporal,
)

# ---------------------------------------------------------------------------
# Frozen protocol identity (tool constant; asserted equal to the
# preregistration at startup — the execution lock)
# ---------------------------------------------------------------------------
PROTOCOL_SHA256 = "91b8f7db1f0c754ae479f40690b10366835811df75072287942667af1a30e277"
CENTRAL_SEED = 20260817
RUN = Path("/root/autodl-tmp/processed/dataset_v4_nf3_ton_v1/"
           "evidence_processing_method_dependence_diagnostic_v1")
OWG = Path("/root/autodl-tmp/processed/dataset_v4_nf3_ton_v1/"
           "open_world_recoverability_gate_v1")
GATE1 = Path("/root/autodl-tmp/processed/dataset_v4_nf3_ton_v1/core_gate_v1")
V2RUN = Path("/root/autodl-tmp/processed/dataset_v4_nf3_ton_v1/"
             "strong_hybrid_osr_evidence_gate_v2")

SHUF_RNG_OFFSET = 400       # deterministic SHUFFLED permutations
SAME_REPR_RNG_OFFSET = 300  # same-representation EDL head training
EDL_RETRAIN_RNG_OFFSET = 200  # B_EDL safeguard retrain (frozen V2 recipe,
                              # identical to the validation replay)
BOOTSTRAP_REPS = 1000
BOOTSTRAP_RNG = 162000 + 500
RATIO_SUPPORT_MIN = 0.5
RATIO_CI_LOWER_MIN = 0.3
REAL_REPRO_TOL = 1e-6
SHUF_MARGINAL_TOL = 1e-9

# Identity values from the validated V2 audit (same_sample_comparison).
REAL_RK_GAIN_EXPECTED = {
    "Credential": 89.60648682287761,
    "Recon_Scanning": 31.31847660956691,
    "Web_Injection": 68.90515267403683,
}
REAL_TU_GAIN_EXPECTED = {
    "Credential": 135.73512605571747,
    "Recon_Scanning": 140.17709421348573,
    "Web_Injection": 98.95271797084808,
}


def set_determinism() -> dict[str, Any]:
    torch.backends.cudnn.deterministic = True
    torch.backends.cudnn.benchmark = False
    return {"PYTHONHASHSEED": os.environ.get("PYTHONHASHSEED", "unset"),
            "cudnn_benchmark": False,
            "cudnn_deterministic": True,
            "dataloader_workers": 0,
            "numpy_generators_only": True,
            "torch_cuda_manual_seed_all": True,
            "torch_manual_seed_per_cell": True}


# ---------------------------------------------------------------------------
# Condition feature construction
# ---------------------------------------------------------------------------

def null_features(cell) -> tuple[dict[str, np.ndarray], dict[str, np.ndarray]]:
    """NULL-PRESENT: availability masks as in the state (present); the
    T/R Evidence block values are replaced by the training-normalized
    neutral vector = all-zero in the frozen log1p transform space."""
    def zero_blocks(feats):
        out = {k: v.astype(np.float64).copy() for k, v in feats.items()}
        btr = out["BTR"]
        btr[:, 47:63] = 0.0   # T block
        btr[:, 63:81] = 0.0   # R block
        out["BT"] = np.column_stack([btr[:, :47], btr[:, 47:63]])
        out["BR"] = np.column_stack([btr[:, :47], btr[:, 63:81]])
        out["B"] = btr[:, :47]
        return out
    return zero_blocks(cell["features_train"]), zero_blocks(cell["features_ev"])


def shuffled_features(cell, rng: np.random.Generator) -> dict[str, np.ndarray]:
    """SHUFFLED (eval only): deterministic permutation of the T and R
    Evidence blocks among samples within the same rotation/seed/eval
    population and block type; RK and TU shuffled separately. Masks and
    availability identical to REAL. Offline mechanism control only."""
    feats = {k: v.astype(np.float64).copy()
             for k, v in cell["features_ev"].items()}
    btr = feats["BTR"]
    unk = cell["ev_is_unknown"]
    rec = cell["ev_recoverable"]
    rk_rows = np.flatnonzero(rec & (~unk))
    un_rows = np.flatnonzero(unk)
    for rows in (rk_rows, un_rows):
        for lo, hi in ((47, 63), (63, 81)):  # T block, R block
            perm = rng.permutation(len(rows))
            btr[rows, lo:hi] = btr[rows, lo:hi][perm]
    feats["BT"] = np.column_stack([btr[:, :47], btr[:, 47:63]])
    feats["BR"] = np.column_stack([btr[:, :47], btr[:, 63:81]])
    feats["B"] = btr[:, :47]
    return feats


# ---------------------------------------------------------------------------
# Forward passes with per-state geometry and scores
# ---------------------------------------------------------------------------

def state_embeddings(model, features, indices, states) -> dict[str, np.ndarray]:
    out = {}
    for s in states:
        emb, _ = encoder_forward(model, features, s, indices)
        out[s] = emb
    return out


def maha_scores_from(state_embs: dict[str, np.ndarray],
                     train_embs: dict[str, np.ndarray],
                     train_labels: np.ndarray, known: tuple[str, ...],
                     states) -> dict[str, np.ndarray]:
    scores = {}
    for s in states:
        geo = fit_osr_geometry(train_embs[s], train_labels, known)
        # float64 promotion: the persisted V2 audit scores are float64
        # (astype at save time); gains must subtract in float64 to match
        # the audit's same_sample values bit-for-bit (bugfix 2026-08-18).
        scores[s] = mahalanobis_min_distance(state_embs[s], geo).astype(
            np.float64)
    return scores


def gains_of(scores: dict[str, np.ndarray]) -> tuple[np.ndarray,
                                                     dict[str, np.ndarray]]:
    best = None
    per_type = {}
    for s in LEGAL_STATES:
        g = scores["B"] - scores[s]
        per_type[s] = g
        best = g if best is None else np.maximum(best, g)
    return best, per_type


# ---------------------------------------------------------------------------
# Same-representation readout B: fixed EDL head on FROZEN h. Mirrors
# train_encoder_v2 exactly (same make_tensors / early_states=zeros /
# best-state restore / epoch bookkeeping); the trunk is fully frozen AND
# kept in eval() mode so the frozen representation is not corrupted by
# dropout. Optimizer over trainable parameters only.
# ---------------------------------------------------------------------------

def train_edl_head_frozen_h(trunk: StrongOSREncoder, features,
                            labels_n, fit_mask, early_mask,
                            rng, seed, epoch_log_path: Path):
    edl = EDLHeadEncoder(trunk)
    for p in edl.trunk.parameters():
        p.requires_grad = False
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)
    device = "cuda" if torch.cuda.is_available() else "cpu"
    edl = edl.to(device)
    edl.trunk.eval()  # frozen representation: dropout OFF on the trunk
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
        edl.eval()
        total, count = 0.0, 0
        with torch.no_grad():
            for start in range(0, len(early_idx), BATCH_SIZE):
                chunk = early_idx[start:start + BATCH_SIZE]
                st = state_ids[start:start + BATCH_SIZE]
                b, t, r, mt, mr = make_tensors(chunk, st)
                y = torch.tensor(labels_n[chunk], device=device)
                loss = edl_loss(edl(b, t, r, mt, mr), y)
                total += float(loss) * len(chunk)
                count += len(chunk)
        edl.dirichlet_head.train()  # trunk stays eval
        return total / max(count, 1)

    optimizer = torch.optim.AdamW(
        [p for p in edl.parameters() if p.requires_grad],
        lr=ADAMW_LR, weight_decay=ADAMW_WEIGHT_DECAY)
    best_loss, best_state, stale = float("inf"), None, 0
    epochs_run = 0
    records = []
    early_states = np.zeros(len(early_idx), dtype=np.int64)
    loss_trajectory = []
    for epoch in range(MAX_EPOCHS):
        epochs_run = epoch + 1
        order = rng.permutation(len(train_idx))
        batch_states = rng.integers(0, len(EVIDENCE_STATES),
                                    size=len(train_idx))
        ce_sum = 0.0
        for start in range(0, len(order), BATCH_SIZE):
            pos = order[start:start + BATCH_SIZE]
            chunk = train_idx[pos]
            b, t, r, mt, mr = make_tensors(chunk, batch_states[pos])
            y = torch.tensor(labels_n[chunk], device=device)
            loss = edl_loss(edl(b, t, r, mt, mr), y)
            optimizer.zero_grad()
            loss.backward()
            optimizer.step()
            ce_sum += float(loss.detach()) * len(chunk)
        val_loss = early_loss(early_states)
        loss_trajectory.append(val_loss)
        is_best = val_loss < best_loss - 1e-6
        if is_best:
            best_loss, stale = val_loss, 0
            best_state = {k: v.detach().clone()
                          for k, v in edl.state_dict().items()}
        else:
            stale += 1
        records.append({"epoch": epoch + 1,
                        "train_ce": ce_sum / len(train_idx),
                        "early_stop_ce": val_loss,
                        "learning_rate": float(optimizer.param_groups[0]["lr"]),
                        "is_best": bool(is_best), "stale": stale})
        if stale >= EARLY_STOP_PATIENCE:
            break
    if best_state is not None:
        edl.load_state_dict(best_state)
    edl.eval()
    with open(epoch_log_path, "w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record) + "\n")
    return edl.cpu(), epochs_run, records, loss_trajectory


def edl_alpha_and_novelty(edl, features, indices, states
                          ) -> tuple[dict[str, np.ndarray],
                                     dict[str, np.ndarray]]:
    """alpha per state (S = alpha.sum = Dirichlet strength) and
    novelty(s) = 1 - max(alpha)/S (same semantics as the validated B_EDL
    safeguard)."""
    alpha_all, nov_all = {}, {}
    for s in states:
        alpha, _ = encoder_forward(edl, features, s, indices, use_edl=True)
        alpha = alpha.astype(np.float64)  # float64 (same convention as the
        S = alpha.sum(axis=-1)            # persisted float64 audit scores)
        nov_all[s] = 1.0 - alpha.max(axis=-1) / S
        alpha_all[s] = alpha
    return alpha_all, nov_all


# ---------------------------------------------------------------------------
# Bootstrap: rotation-stratified sample replicates, paired within
# condition/population. gains[cond][pop][rot] -> array of best-legal gains.
# Outputs: pooled means + CIs per (cond, pop); paired ratios ctrl/REAL per
# pop; paired gap CIs per cond (RK mean - TU mean); real_minus_control_gap
# paired differences with CIs.
# ---------------------------------------------------------------------------

def bootstrap_pooled(gains: dict[str, dict[str, dict[str, np.ndarray]]],
                     rng: np.random.Generator, reps: int = BOOTSTRAP_REPS
                     ) -> dict[str, Any]:
    conds = list(gains.keys())
    pops = list(gains[conds[0]].keys())
    rots = list(gains[conds[0]][pops[0]].keys())
    sizes = {rot: len(gains[conds[0]][pops[0]][rot]) for rot in rots}
    total = sum(sizes.values())
    weights = {rot: sizes[rot] / total for rot in rots}
    draws = {rot: rng.integers(0, sizes[rot], size=(reps, sizes[rot]))
             for rot in rots}
    rep_means = {cond: {pop: np.empty(reps) for pop in pops}
                 for cond in conds}
    for cond in conds:
        for pop in pops:
            for rep in range(reps):
                m = 0.0
                for rot in rots:
                    m += float(gains[cond][pop][rot][draws[rot][rep]].mean()
                               ) * weights[rot]
                rep_means[cond][pop][rep] = m
    out: dict[str, Any] = {}
    for pop in pops:
        for cond in conds:
            arr = rep_means[cond][pop]
            out[f"{cond}_{pop}"] = {"mean": float(arr.mean()),
                                    "ci95": [float(np.percentile(arr, 2.5)),
                                             float(np.percentile(arr, 97.5))]}
        for ctrl in ("NULL", "SHUFFLED"):
            if ctrl not in conds:
                continue
            ratio = rep_means[ctrl][pop] / rep_means["REAL"][pop]
            out[f"{ctrl}_to_REAL_{pop}"] = {
                "mean": float(ratio.mean()),
                "ci95": [float(np.percentile(ratio, 2.5)),
                         float(np.percentile(ratio, 97.5))]}
    gaps = {}
    for cond in conds:
        g = rep_means[cond]["RK"] - rep_means[cond]["TU"]
        gaps[cond] = g
        out[f"{cond}_gap"] = {"mean": float(g.mean()),
                              "ci95": [float(np.percentile(g, 2.5)),
                                       float(np.percentile(g, 97.5))]}
    out["real_minus_control_gap"] = {}
    for ctrl in ("NULL", "SHUFFLED"):
        if ctrl not in conds:
            continue
        d = gaps["REAL"] - gaps[ctrl]
        out["real_minus_control_gap"][ctrl] = {
            "mean": float(d.mean()),
            "ci95": [float(np.percentile(d, 2.5)),
                     float(np.percentile(d, 97.5))]}
    return out


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    RUN.mkdir(parents=True, exist_ok=True)
    det = set_determinism()
    start = time.time()
    out: dict[str, Any] = {}

    # --- Execution lock: protocol sha256 (tool == preregistration == file)
    protocol = REPO / "docs/research_plan" / \
        "evidence_processing_method_dependence_diagnostic_v1_protocol.md"
    recomputed = hashlib.sha256(protocol.read_bytes()).hexdigest()
    reg = json.loads((REPO / "reports/research_audit" /
                      "evidence_processing_method_dependence_diagnostic_v1_preregistration.json").read_text())
    out["protocol_sha256_recomputed"] = recomputed
    out["preregistration_sha256"] = reg["protocol_sha256"]
    out["protocol_hash_match"] = (recomputed == PROTOCOL_SHA256
                                  == reg["protocol_sha256"])
    if not out["protocol_hash_match"]:
        raise SystemExit("PROTOCOL_HASH_MISMATCH")

    # --- Load central-seed cells + frozen primary weights ---
    cells = {rot: assemble_cell(CENTRAL_SEED, rot, OWG, GATE1)
             for rot in ROTATIONS}
    primaries = {}
    for rot in ROTATIONS:
        model = StrongOSREncoder()
        model.load_state_dict(torch.load(
            V2RUN / "cells" / cell_key(CENTRAL_SEED, rot) / "model.pt",
            map_location="cpu"))
        model.eval()  # frozen-repr contract: identical to the validated
                      # primary_replay convention (dropout off)
        primaries[rot] = model

    per_rotation: dict[str, Any] = {}
    all_gains = {"REAL": {"RK": {}, "TU": {}},
                 "NULL": {"RK": {}, "TU": {}},
                 "SHUFFLED": {"RK": {}, "TU": {}}}
    for rot in ROTATIONS:
        cell = cells[rot]
        model = primaries[rot]
        fit_idx = np.flatnonzero(~cell["early"])
        labels_n = class_codes(cell, cell["train_labels"])
        rk_rows = np.flatnonzero(cell["ev_recoverable"] &
                                 (~cell["ev_is_unknown"]))
        un_rows = np.flatnonzero(cell["ev_is_unknown"])

        feats_tr_null, feats_ev_null = null_features(cell)
        shuf_rng = cell_rng(CENTRAL_SEED, rot, RNG_BASE + SHUF_RNG_OFFSET)
        feats_ev_shuf = shuffled_features(cell, shuf_rng)

        # SHUFFLED marginal-preservation check (T/R blocks, RK and TU
        # separately) and NULL-PRESENT zero-block check.
        btr_r = cell["features_ev"]["BTR"]
        btr_s = feats_ev_shuf["BTR"]
        shuf_marg_ok = True
        for rows in (rk_rows, un_rows):
            for lo, hi in ((47, 63), (63, 81)):
                shuf_marg_ok &= bool(np.allclose(
                    btr_r[rows, lo:hi].mean(axis=0),
                    btr_s[rows, lo:hi].mean(axis=0), atol=SHUF_MARGINAL_TOL))
                shuf_marg_ok &= bool(np.allclose(
                    btr_r[rows, lo:hi].std(axis=0),
                    btr_s[rows, lo:hi].std(axis=0), atol=SHUF_MARGINAL_TOL))
        if not shuf_marg_ok:
            raise SystemExit("SHUFFLED_MARGINAL_MISMATCH")
        if not bool((feats_ev_null["BTR"][:, 47:81] == 0.0).all()):
            raise SystemExit("NULL_PRESENT_BLOCK_CHECK_FAILED")

        # --- Condition controls on the frozen primary encoder ---
        cond_gains: dict[str, dict[str, Any]] = {}
        for cond, (ft, fe) in {
            "REAL": (cell["features_train"], cell["features_ev"]),
            "NULL": (feats_tr_null, feats_ev_null),
            "SHUFFLED": (cell["features_train"], feats_ev_shuf),
        }.items():
            train_embs = state_embeddings(model, ft, fit_idx, EVIDENCE_STATES)
            eval_embs = state_embeddings(model, fe,
                                         np.arange(len(fe["B"])),
                                         EVIDENCE_STATES)
            scores = maha_scores_from(eval_embs, train_embs,
                                      cell["train_labels"][fit_idx],
                                      cell["known"], EVIDENCE_STATES)
            best, per_type = gains_of(scores)
            cond_gains[cond] = {
                "rk": best[rk_rows], "un": best[un_rows],
                "per_type_rk": {s: per_type[s][rk_rows] for s in LEGAL_STATES},
                "per_type_un": {s: per_type[s][un_rows] for s in LEGAL_STATES},
                "scores_rk": {s: scores[s][rk_rows] for s in EVIDENCE_STATES},
                "scores_un": {s: scores[s][un_rows] for s in EVIDENCE_STATES},
            }
            all_gains[cond]["RK"][rot] = best[rk_rows]
            all_gains[cond]["TU"][rot] = best[un_rows]

        # REAL identity check vs the validated V2 audit (1e-6).
        for pop, expected, key in (("rk", REAL_RK_GAIN_EXPECTED, "RK"),
                                   ("un", REAL_TU_GAIN_EXPECTED, "TU")):
            got = float(cond_gains["REAL"][pop].mean())
            if abs(got - expected[rot]) > REAL_REPRO_TOL:
                raise SystemExit(f"REAL_REPRODUCTION_FAIL {rot} {key} "
                                 f"got={got} expected={expected[rot]}")
        print(f"[conditions {rot}] REAL/NULL/SHUFFLED gains computed "
              f"(REAL identity check passed)", flush=True)

        # --- Same-representation test: fixed EDL head on frozen h ---
        head_rng = cell_rng(CENTRAL_SEED, rot, RNG_BASE + SAME_REPR_RNG_OFFSET)
        epoch_log = RUN / "same_repr_edl_heads" / f"{rot}_epochs.jsonl"
        epoch_log.parent.mkdir(parents=True, exist_ok=True)
        edl, _, _, loss_traj = train_edl_head_frozen_h(
            primaries[rot], cell["features_train"], labels_n,
            fit_mask=~cell["early"], early_mask=cell["early"],
            rng=head_rng, seed=CENTRAL_SEED, epoch_log_path=epoch_log)
        alpha_ev, nov_ev = edl_alpha_and_novelty(
            edl, cell["features_ev"], np.arange(len(cell["features_ev"]["B"])),
            EVIDENCE_STATES)
        # Preregistered EDL sanity checks: alpha >= 1; loss decreases.
        alpha_ok = bool(np.concatenate(
            [alpha_ev[s] for s in EVIDENCE_STATES]).min() >= 1.0)
        loss_ok = bool(loss_traj[-1] < loss_traj[0])
        if not (alpha_ok and loss_ok):
            raise SystemExit("SAME_REPR_EDL_SANITY_FAILED")
        # Known-only calibration audit (per state, VAL_CALIB Known).
        ck = (cell["ev_split_role"] == 0) & (~cell["ev_is_unknown"])
        thr = {s: float(np.quantile(nov_ev[s][ck], 0.95))
               for s in EVIDENCE_STATES}
        best_e, _ = gains_of(nov_ev)
        same_repr = {
            "rk_gain": best_e[rk_rows], "un_gain": best_e[un_rows],
            "maha_gap": float(cond_gains["REAL"]["rk"].mean() -
                              cond_gains["REAL"]["un"].mean()),
            "edl_gap": float(best_e[rk_rows].mean() - best_e[un_rows].mean()),
            "edl_alpha_min": float(np.concatenate(
                [alpha_ev[s] for s in EVIDENCE_STATES]).min()),
            "loss_first": float(loss_traj[0]),
            "loss_last": float(loss_traj[-1]),
            "calib_thresholds": thr,
            "n_unknown_in_calib": int(((cell["ev_split_role"] == 0) &
                                       cell["ev_is_unknown"]).sum())}
        np.savez_compressed(
            RUN / "same_repr_edl_heads" / f"{rot}_scores.npz",
            **{f"s_{s}": nov_ev[s].astype(np.float64)
               for s in EVIDENCE_STATES},
            rk_gain=best_e[rk_rows].astype(np.float64),
            un_gain=best_e[un_rows].astype(np.float64),
            is_unknown=cell["ev_is_unknown"],
            recoverable=cell["ev_recoverable"],
            allow_pickle=False)
        print(f"[same-repr {rot}] maha_gap={same_repr['maha_gap']:.4f} "
              f"edl_gap={same_repr['edl_gap']:.4f}", flush=True)

        # --- Reverse cross-check: retrain B_EDL (exact frozen recipe,
        # identical to the validation replay), then Mahalanobis readout on
        # its frozen trunk representation h_EDL ---
        edl_full = EDLHeadEncoder(StrongOSREncoder())
        edl_rng = cell_rng(CENTRAL_SEED, rot, RNG_BASE + EDL_RETRAIN_RNG_OFFSET)
        epoch_log2 = RUN / "b_edl_retrain" / f"{rot}_epochs.jsonl"
        epoch_log2.parent.mkdir(parents=True, exist_ok=True)
        edl_full, _, _ = v2.train_encoder_v2(
            edl_full, cell["features_train"], labels_n,
            fit_mask=~cell["early"], early_mask=cell["early"], rng=edl_rng,
            seed=CENTRAL_SEED, use_edl=True, epoch_log_path=epoch_log2)
        trunk = edl_full.trunk
        trunk.eval()
        t_embs = state_embeddings(trunk, cell["features_train"], fit_idx,
                                  EVIDENCE_STATES)
        e_embs = state_embeddings(trunk, cell["features_ev"],
                                  np.arange(len(cell["features_ev"]["B"])),
                                  EVIDENCE_STATES)
        r_scores = maha_scores_from(e_embs, t_embs,
                                    cell["train_labels"][fit_idx],
                                    cell["known"], EVIDENCE_STATES)
        r_best, _ = gains_of(r_scores)
        reverse = {"rk_gain": r_best[rk_rows], "un_gain": r_best[un_rows],
                   "gap": float(r_best[rk_rows].mean() -
                                r_best[un_rows].mean())}
        print(f"[reverse {rot}] maha-on-EDL-trunk gap={reverse['gap']:.4f}",
              flush=True)

        # --- EDL mechanism diagnostics (retrained B_EDL chain, §7) ---
        alpha_b, nov_b_full = edl_alpha_and_novelty(
            edl_full, cell["features_ev"],
            np.arange(len(cell["features_ev"]["B"])), EVIDENCE_STATES)
        # Per-row best-legal state = argmax-legal of gain = nov(B) - nov(s).
        best_state_idx = np.zeros(len(nov_b_full["B"]), dtype=np.int64)
        best_gain = np.full(len(nov_b_full["B"]), -np.inf)
        for si, s in enumerate(LEGAL_STATES):
            g = nov_b_full["B"] - nov_b_full[s]
            take = g > best_gain
            best_gain[take] = g[take]
            best_state_idx[take] = si

        def mech(rows):
            n = len(rows)
            S_b = alpha_b["B"][rows].sum(axis=-1)
            u_b = NUM_KNOWN / S_b
            p_b = alpha_b["B"][rows].max(axis=-1) / S_b
            p2_b = np.partition(alpha_b["B"][rows], -2, axis=-1)[:, -2] / S_b
            arg_b = alpha_b["B"][rows].argmax(axis=-1)
            S_s = np.full(n, np.nan)
            u_s = np.full(n, np.nan)
            p_s = np.full(n, np.nan)
            p2_s = np.full(n, np.nan)
            arg_s = np.full(n, -1, dtype=np.int64)
            for si, s in enumerate(LEGAL_STATES):
                sel = best_state_idx[rows] == si
                if not sel.any():
                    continue
                a_s = alpha_b[s][rows[sel]]
                ssum = a_s.sum(axis=-1)
                S_s[sel] = ssum
                u_s[sel] = NUM_KNOWN / ssum
                p_s[sel] = a_s.max(axis=-1) / ssum
                p2_s[sel] = np.partition(a_s, -2, axis=-1)[:, -2] / ssum
                arg_s[sel] = a_s.argmax(axis=-1)
            return {"dS": float(np.nanmean(S_s - S_b)),
                    "du": float(np.nanmean(u_s - u_b)),
                    "dp_top": float(np.nanmean(p_s - p_b)),
                    "dp_2nd": float(np.nanmean(p2_s - p2_b)),
                    "S_b_mean": float(S_b.mean()),
                    "S_s_mean": float(np.nanmean(S_s)),
                    "u_b_mean": float(u_b.mean()),
                    "u_s_mean": float(np.nanmean(u_s)),
                    "p_top_b_mean": float(p_b.mean()),
                    "p_top_s_mean": float(np.nanmean(p_s)),
                    "p_2nd_b_mean": float(p2_b.mean()),
                    "p_2nd_s_mean": float(np.nanmean(p2_s)),
                    "stability": float((arg_s == arg_b).mean())}

        per_rotation[rot] = {
            "conditions": {cond: {
                "rk_gain_mean": float(cond_gains[cond]["rk"].mean()),
                "un_gain_mean": float(cond_gains[cond]["un"].mean()),
                "gap": float(cond_gains[cond]["rk"].mean() -
                             cond_gains[cond]["un"].mean()),
                "rk_frac_pos": float((cond_gains[cond]["rk"] > 0).mean()),
                "un_frac_pos": float((cond_gains[cond]["un"] > 0).mean()),
                "per_type_rk": {s: float(cond_gains[cond]["per_type_rk"][s].mean())
                                for s in LEGAL_STATES},
                "per_type_un": {s: float(cond_gains[cond]["per_type_un"][s].mean())
                                for s in LEGAL_STATES},
            } for cond in ("REAL", "NULL", "SHUFFLED")},
            "same_repr": same_repr,
            "reverse": reverse,
            "edl_mechanism": {"RK": mech(rk_rows), "TU": mech(un_rows)},
        }
        np.savez_compressed(
            RUN / f"condition_scores_{rot}.npz",
            **{f"real_{s}_rk": cond_gains["REAL"]["scores_rk"][s].astype(np.float64)
               for s in EVIDENCE_STATES},
            **{f"null_{s}_rk": cond_gains["NULL"]["scores_rk"][s].astype(np.float64)
               for s in EVIDENCE_STATES},
            **{f"shuf_{s}_rk": cond_gains["SHUFFLED"]["scores_rk"][s].astype(np.float64)
               for s in EVIDENCE_STATES},
            **{f"real_{s}_un": cond_gains["REAL"]["scores_un"][s].astype(np.float64)
               for s in EVIDENCE_STATES},
            **{f"null_{s}_un": cond_gains["NULL"]["scores_un"][s].astype(np.float64)
               for s in EVIDENCE_STATES},
            **{f"shuf_{s}_un": cond_gains["SHUFFLED"]["scores_un"][s].astype(np.float64)
               for s in EVIDENCE_STATES},
            allow_pickle=False)
        m = per_rotation[rot]["edl_mechanism"]
        print(f"[edl-mechanism {rot}] RK dS={m['RK']['dS']:.3f} "
              f"stab={m['RK']['stability']:.3f} | TU dS={m['TU']['dS']:.3f} "
              f"stab={m['TU']['stability']:.3f}", flush=True)

    # ------------------------------------------------------------------
    # Bootstrap (rotation-stratified, paired)
    # ------------------------------------------------------------------
    bs_rng = np.random.default_rng(BOOTSTRAP_RNG)
    boot = bootstrap_pooled(all_gains, bs_rng)
    out["bootstrap"] = boot
    out["per_rotation"] = per_rotation

    # Same-representation pooled gap CI (EDL head on frozen h) and reverse
    # cross-check pooled gap CI.
    sr_gains = {"REAL": {"RK": {}, "TU": {}}}
    rev_gains = {"REAL": {"RK": {}, "TU": {}}}
    for rot in ROTATIONS:
        sr_gains["REAL"]["RK"][rot] = per_rotation[rot]["same_repr"]["rk_gain"]
        sr_gains["REAL"]["TU"][rot] = per_rotation[rot]["same_repr"]["un_gain"]
        rev_gains["REAL"]["RK"][rot] = per_rotation[rot]["reverse"]["rk_gain"]
        rev_gains["REAL"]["TU"][rot] = per_rotation[rot]["reverse"]["un_gain"]
    sr_boot = bootstrap_pooled(sr_gains, np.random.default_rng(BOOTSTRAP_RNG + 1))
    rev_boot = bootstrap_pooled(rev_gains, np.random.default_rng(BOOTSTRAP_RNG + 2))
    out["same_repr_bootstrap"] = sr_boot
    out["reverse_bootstrap"] = rev_boot

    # ------------------------------------------------------------------
    # Interpretation rules (frozen §8; labels never stand alone)
    # ------------------------------------------------------------------
    sr_contradict = {rot: (per_rotation[rot]["same_repr"]["maha_gap"] < 0 and
                           per_rotation[rot]["same_repr"]["edl_gap"] > 0)
                     for rot in ROTATIONS}
    n_sr = int(sum(sr_contradict.values()))
    readout_dominant = bool(n_sr >= 2)

    prim_gap_ci = boot["REAL_gap"]["ci95"]
    rev_gap_ci = rev_boot["REAL_gap"]["ci95"]
    representation_dominant = bool(
        (not readout_dominant) and rev_gap_ci[0] > 0 and prim_gap_ci[1] < 0)

    presence_bias = bool(
        (boot["NULL_to_REAL_RK"]["mean"] >= RATIO_SUPPORT_MIN or
         boot["NULL_to_REAL_TU"]["mean"] >= RATIO_SUPPORT_MIN) and
        min(boot["NULL_to_REAL_RK"]["ci95"][0],
            boot["NULL_to_REAL_TU"]["ci95"][0]) >= RATIO_CI_LOWER_MIN)
    distribution_bias = bool(
        (boot["SHUFFLED_to_REAL_RK"]["mean"] >= RATIO_SUPPORT_MIN or
         boot["SHUFFLED_to_REAL_TU"]["mean"] >= RATIO_SUPPORT_MIN) and
        min(boot["SHUFFLED_to_REAL_RK"]["ci95"][0],
            boot["SHUFFLED_to_REAL_TU"]["ci95"][0]) >= RATIO_CI_LOWER_MIN)
    gd = boot["real_minus_control_gap"]
    content_signal = bool(gd["NULL"]["ci95"][0] > 0 and
                          gd["SHUFFLED"]["ci95"][0] > 0)

    rules_fired = []
    if readout_dominant:
        rules_fired.append("READOUT_DOMINANT")
    if representation_dominant:
        rules_fired.append("REPRESENTATION_OR_PROCESSING_DOMINANT")
    if presence_bias:
        rules_fired.append("GENERIC_EVIDENCE_PRESENCE_BIAS")
    if distribution_bias:
        rules_fired.append("GENERIC_EVIDENCE_DISTRIBUTION_BIAS")
    if content_signal:
        rules_fired.append("RECOVERY_SPECIFIC_CONTENT_SIGNAL")
    primary = rules_fired[0] if rules_fired else "MIXED_OR_UNRESOLVED"
    if len(rules_fired) > 1:
        primary += "_PRIMARY"
    out["interpretation"] = {
        "rules_fired": rules_fired,
        "primary": primary,
        "readout_dominant": readout_dominant,
        "representation_dominant": representation_dominant,
        "presence_bias": presence_bias,
        "distribution_bias": distribution_bias,
        "content_signal": content_signal,
        "same_repr_contradiction_by_rotation": sr_contradict,
        "n_rotations_contradiction": n_sr,
        "reverse_gap_by_rotation": {rot: per_rotation[rot]["reverse"]["gap"]
                                    for rot in ROTATIONS},
        "reverse_gap_pooled_ci": rev_gap_ci,
        "primary_gap_pooled_ci": prim_gap_ci,
        "v2_decision_not_reopened": True,
    }
    out["run_state"] = "COMPLETE"
    manifest = {
        "task": "EVIDENCE_PROCESSING_METHOD_DEPENDENCE_DIAGNOSTIC_V1",
        "protocol_sha256": PROTOCOL_SHA256,
        "central_seed": CENTRAL_SEED,
        "determinism": det,
        "rng_offsets": {"shuffled_permutation": SHUF_RNG_OFFSET,
                         "same_repr_edl_head": SAME_REPR_RNG_OFFSET,
                         "b_edl_retrain": EDL_RETRAIN_RNG_OFFSET,
                         "bootstrap": BOOTSTRAP_RNG,
                         "rng_base": RNG_BASE,
                         "bootstrap_rng_base": BOOTSTRAP_RNG},
    }
    (RUN / "run_manifest.json").write_text(
        json.dumps(manifest, indent=1, default=str), encoding="utf-8")
    (RUN / "aggregate.json").write_text(
        json.dumps(out, indent=1, default=str), encoding="utf-8")
    print(f"[diagnostic] DIAGNOSTIC_STATUS=COMPLETE primary={primary} "
          f"({time.time() - start:.0f}s)", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
