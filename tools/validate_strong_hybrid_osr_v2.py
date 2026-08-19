#!/usr/bin/env python3
"""POST-RUN VALIDATION for Strong Hybrid OSR Evidence Gate V2.

Independent validation: identity, primary rederivation (H1-H4, deployable
metrics, bootstrap CIs, recovery/specificity), a diagnostic REPLAY of the
frozen conditional safeguards with per-sample persistence, the EDL audit,
and the Mahalanobis-vs-EDL same-sample comparison. No retraining for
selection, no tuning, no new detectors. Primary per-state scores are
recomputed from the PERSISTED primary weights (forward passes only).
Safeguard models are re-trained with the exact frozen recipe and
verified to reproduce the recorded aggregate flags.

Outputs (Git-external):
  processed/dataset_v4_nf3_ton_v1/strong_hybrid_osr_evidence_gate_v2/
    validation_v2/validation_audit.json
"""

from __future__ import annotations

import hashlib
import json
import pickle
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np
import pyarrow.parquet as pq

TOOLS = Path(__file__).resolve().parent
REPO = TOOLS.parent
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import torch  # noqa: E402
from sklearn.metrics import (  # noqa: E402
    average_precision_score,
    f1_score,
    roc_auc_score,
)

import run_strong_hybrid_osr_evidence_gate_v2 as v2  # noqa: E402
from run_strong_neural_osr_evidence_gate_v1 import (  # noqa: E402
    EVIDENCE_STATES,
    LEGAL_STATES,
    ROTATIONS,
    StrongOSREncoder,
    EDLHeadEncoder,
    assemble_cell,
    cell_rng,
    class_codes,
    encoder_forward,
    fit_osr_geometry,
    mahalanobis_min_distance,
    RNG_BASE,
)

OWG = Path("/root/autodl-tmp/processed/dataset_v4_nf3_ton_v1/"
           "open_world_recoverability_gate_v1")
GATE1 = Path("/root/autodl-tmp/processed/dataset_v4_nf3_ton_v1/core_gate_v1")
RUN = Path("/root/autodl-tmp/processed/dataset_v4_nf3_ton_v1/"
           "strong_hybrid_osr_evidence_gate_v2")
VALDIR = RUN / "validation_v2"
SEEDS = v2.FORMAL_SEEDS
CENTRAL = 20260817


def load_cell(seed, rot):
    key = v2.cell_key(seed, rot)
    return json.loads((RUN / "cells" / key / f"{key}.json").read_text())


def known_unknown_auroc(known, unknown):
    if len(known) < 2 or len(unknown) < 2:
        return float("nan")
    y = np.concatenate([np.zeros(len(known)), np.ones(len(unknown))])
    return float(roc_auc_score(y, np.concatenate([known, unknown])))


def known_unknown_aupr(known, unknown):
    if len(known) < 2 or len(unknown) < 2:
        return float("nan")
    y = np.concatenate([np.zeros(len(known)), np.ones(len(unknown))])
    return float(average_precision_score(y, np.concatenate([known, unknown])))


def recall_at_5fur(known, unknown):
    thr = float(np.quantile(known, 0.95))
    return float((unknown >= thr).mean())


def primary_rederivation(out: dict):
    """Rederive H1-H4, deployable metrics, CIs, recovery/specificity from
    persisted rows/bc_rows + frozen parquets."""
    cells = {}
    for seed in SEEDS:
        for rot in ROTATIONS:
            cells[v2.cell_key(seed, rot)] = load_cell(seed, rot)

    # H1: re-verify one cell's RF reproduction independently.
    key = "20260817_Credential"
    cell = assemble_cell(20260817, "Credential", OWG, GATE1)
    with open(OWG / "models" /
              "owg_v1_seed_20260817_rotation_Credential_models.pkl",
              "rb") as handle:
        models = pickle.load(handle)["models"]
    n = len(cell["ev_labels"])
    pred_b = v2.rf_predict_state(models, cell["features_ev"], "B",
                                 np.arange(n))
    mism_p0 = int((pred_b != cell["ev_pred_p0"]).sum())
    pred_p6 = np.empty(n, dtype=object)
    for state in EVIDENCE_STATES:
        inv = {"B": "NONE", "BT": "T", "BR": "R", "BTR": "TR"}[state]
        mask = cell["ev_action_p6"] == inv
        if mask.any():
            pred_p6[mask] = v2.rf_predict_state(models, cell["features_ev"],
                                                state, np.flatnonzero(mask))
    mism_p6 = int((pred_p6 != cell["ev_pred_p6"]).sum())
    frozen = json.loads((OWG / "owg_v1_seed_20260817_rotation_Credential"
                         f"_result.json").read_text())
    out["h1_independent"] = {"p0_mismatch": mism_p0, "p6_mismatch": mism_p6,
                             "frozen_p0_f1": frozen["policies"][
                                 "P0_BASIC_DIRECT"]["known_macro_f1"],
                             "frozen_p6_f1": frozen["policies"][
                                 "P6_UTILITY_TYPED"]["known_macro_f1"]}

    # H2/H3/H4 from cell JSONs.
    def rot_mean(fn):
        return {r: float(np.nanmean([fn(cells[v2.cell_key(s, r)])
                                     for s in SEEDS])) for r in ROTATIONS}
    nb = rot_mean(lambda c: c["neural_basic"]["auroc"])
    rb = rot_mean(lambda c: c["rf_basic"]["auroc"])
    nb_rec = rot_mean(lambda c: c["neural_basic"]["recall_at_5fur"])
    rb_rec = rot_mean(lambda c: c["rf_basic"]["recall_at_5fur"])
    nb_aupr = rot_mean(lambda c: c["neural_basic"]["aupr"])
    rb_aupr = rot_mean(lambda c: c["rf_basic"]["aupr"])
    delta = rot_mean(lambda c: c["neural_basic"]["auroc"] -
                     c["neural_basic"]["auroc_msp"])
    pooled = lambda d: float(np.mean(list(d.values())))  # noqa: E731
    out["h2"] = {"pass": pooled(nb) >= pooled(rb) + v2.H2_POOLED_DELTA and
                 all(nb[r] >= rb[r] + v2.H2_ROTATION_FLOOR for r in ROTATIONS),
                 "neural": nb, "rf": rb}
    out["h3"] = {"pass": (pooled(nb_rec) >= pooled(rb_rec) +
                          v2.H3_POOLED_DELTA and
                          all(nb_rec[r] >= rb_rec[r] + v2.H3_ROTATION_FLOOR
                              for r in ROTATIONS) and
                          pooled(nb_aupr) >= pooled(rb_aupr) +
                          v2.H3_POOLED_DELTA and
                          all(nb_aupr[r] >= rb_aupr[r] + v2.H3_ROTATION_FLOOR
                              for r in ROTATIONS)),
                 "neural_recall": nb_rec, "rf_recall": rb_rec,
                 "neural_aupr": nb_aupr, "rf_aupr": rb_aupr}
    out["h4"] = {"pass": pooled(delta) >= v2.H4_POOLED_MEAN_MIN and
                 sum(1 for r in ROTATIONS if delta[r] > 0) >=
                 v2.H4_POSITIVE_ROTATIONS_MIN,
                 "delta_rot": delta}

    # Deployable per-cell rederivation from persisted rows + frozen tables.
    per_cell = {}
    for seed in SEEDS:
        for rot in ROTATIONS:
            key = v2.cell_key(seed, rot)
            table = pq.read_table(
                OWG / f"owg_v1_seed_{seed}_rotation_{rot}_eval.parquet")
            labels = np.array(table["canonical_label"].to_pylist(),
                              dtype=object)
            unk = table["is_unknown"].to_numpy(
                zero_copy_only=False).astype(bool)
            role = table["split_role"].to_numpy(zero_copy_only=False)
            rec = table["recoverable"].to_numpy(
                zero_copy_only=False).astype(bool)
            rows = np.load(RUN / "cells" / key / "rows.npz")
            ek = (role == 1) & (~unk)
            eu = (role == 1) & unk
            ck = (role == 0) & (~unk)
            known = v2.known_classes_for(rot)
            f1_d0 = float(f1_score(labels[ek],
                                   np.array([known[i] for i in
                                             rows["pred_rf_d0"][ek]]),
                                   average="macro"))
            f1_d1 = float(f1_score(labels[ek],
                                   np.array([known[i] for i in
                                             rows["pred_rf_d1"][ek]]),
                                   average="macro"))
            thr0 = float(np.quantile(rows["score_d0"][ck], 0.95))
            thr1 = float(np.quantile(rows["score_d1"][ck], 0.95))
            rec_ek = rec[ek]
            f0 = float(((rows["score_d0"][ek] >= thr0) &
                        rec_ek).sum() / max(rec_ek.sum(), 1))
            f1_ = float(((rows["score_d1"][ek] >= thr1) &
                         rec_ek).sum() / max(rec_ek.sum(), 1))
            per_cell[key] = {
                "furk0": f0, "furk1": f1_, "f1_0": f1_d0, "f1_1": f1_d1,
                "auroc0": known_unknown_auroc(rows["score_d0"][ek],
                                              rows["score_d0"][eu]),
                "auroc1": known_unknown_auroc(rows["score_d1"][ek],
                                              rows["score_d1"][eu]),
                "aupr0": known_unknown_aupr(rows["score_d0"][ek],
                                            rows["score_d0"][eu]),
                "aupr1": known_unknown_aupr(rows["score_d1"][ek],
                                            rows["score_d1"][eu]),
                "recall0": recall_at_5fur(rows["score_d0"][ek],
                                          rows["score_d0"][eu]),
                "recall1": recall_at_5fur(rows["score_d1"][ek],
                                          rows["score_d1"][eu]),
            }
    out["deployable_rederived"] = per_cell
    out["furk_ci"] = list(v2._furk_paired_ci_v2(RUN))

    # Recovery/specificity rederivation from bc_rows + own bootstrap.
    bc_summary = {}
    for seed in SEEDS:
        for rot in ROTATIONS:
            key = v2.cell_key(seed, rot)
            bc = np.load(RUN / "cells" / key / "bc_rows.npz",
                         allow_pickle=False)
            bc_summary[key] = {"basic": float(bc["rec_basic"].mean()),
                               "best": float(bc["rec_best"].mean()),
                               "rk_gain_mean": float(bc["rk_gain"].mean()),
                               "tu_gain_mean": float(
                                   bc["tu_gain"].mean())
                               if len(bc["tu_gain"]) else 0.0}
    out["recovery_rederived"] = bc_summary
    out["specificity_ci_rederived"] = list(v2._specificity_ci(RUN))
    return cells


def replay_safeguards(out: dict, cells: dict):
    """Re-run the frozen safeguard computations with per-sample
    persistence; verify the recorded flags reproduce."""
    from run_strong_neural_osr_evidence_gate_v1 import _raw_concat_features
    val_dir = VALDIR / "safeguards"
    val_dir.mkdir(parents=True, exist_ok=True)
    results = {"A_RAW_CONCAT": {}, "B_EDL": {}}
    models_by_rot = {}
    central_cells = {}
    for rot in ROTATIONS:
        central_cells[rot] = assemble_cell(CENTRAL, rot, OWG, GATE1)
        with open(OWG / "models" /
                  f"owg_v1_seed_{CENTRAL}_rotation_{rot}_models.pkl",
                  "rb") as handle:
            models_by_rot[rot] = pickle.load(handle)["models"]

    def run_one(kind, rot):
        cell = central_cells[rot]
        labels_n = class_codes(cell, cell["train_labels"])
        rng = cell_rng(CENTRAL, rot,
                       RNG_BASE + (100 if kind == "A" else 200))
        if kind == "A":
            feats_train = _raw_concat_features(cell)
            feats_eval = v2._raw_concat_eval(cell)
            model = StrongOSREncoder()
            model, _, _ = v2.train_encoder_v2(
                model, feats_train, labels_n, fit_mask=~cell["early"],
                early_mask=cell["early"], rng=rng, seed=CENTRAL,
                epoch_log_path=val_dir / f"A_{rot}_epochs.jsonl")
            fit_idx = np.flatnonzero(~cell["early"])
            geometries = {}
            for state in EVIDENCE_STATES:
                emb_fit, _ = encoder_forward(model, feats_train, state,
                                             fit_idx)
                geometries[state] = fit_osr_geometry(
                    emb_fit, cell["train_labels"][fit_idx], cell["known"])
            scores = {}
            for state in EVIDENCE_STATES:
                emb, _ = encoder_forward(model, feats_eval, state,
                                         np.arange(len(cell["ev_labels"])))
                scores[state] = mahalanobis_min_distance(
                    emb, geometries[state])
        else:
            edl = EDLHeadEncoder(StrongOSREncoder())
            edl, _, _ = v2.train_encoder_v2(
                edl, cell["features_train"], labels_n,
                fit_mask=~cell["early"], early_mask=cell["early"], rng=rng,
                seed=CENTRAL, use_edl=True,
                epoch_log_path=val_dir / f"B_{rot}_epochs.jsonl")
            scores = {}
            for state in EVIDENCE_STATES:
                alpha, _ = encoder_forward(
                    edl, cell["features_ev"], state,
                    np.arange(len(cell["ev_labels"])), use_edl=True)
                belief = alpha.max(axis=-1) / alpha.sum(axis=-1)
                scores[state] = 1.0 - belief
        # Persist per-sample per-state scores + flags.
        np.savez_compressed(
            val_dir / f"{kind}_{rot}_scores.npz",
            **{f"s_{s}": scores[s].astype(np.float64)
               for s in EVIDENCE_STATES},
            is_unknown=cell["ev_is_unknown"],
            split_role=cell["ev_split_role"],
            recoverable=cell["ev_recoverable"],
            groups=v2.group_codes(cell["ev_groups"]),
            allow_pickle=False)
        # Known-only per-state thresholds (leakage audit target).
        ck = (cell["ev_split_role"] == 0) & (~cell["ev_is_unknown"])
        thresholds = {s: float(np.quantile(scores[s][ck], 0.95))
                      for s in EVIDENCE_STATES}
        agg = v2._safeguard_cell_agg(cell, models_by_rot[rot], scores)
        agg["thresholds"] = thresholds
        agg["n_unknown_in_calib"] = int(
            ((cell["ev_split_role"] == 0) & cell["ev_is_unknown"]).sum())
        return scores, agg

    for rot in ROTATIONS:
        scores_a, agg_a = run_one("A", rot)
        results["A_RAW_CONCAT"][rot] = agg_a
        scores_b, agg_b = run_one("B", rot)
        results["B_EDL"][rot] = agg_b
        a_rec = agg_a["recovery"]["best_legal_accept_correct_rate"]
        b_rec = agg_b["recovery"]["best_legal_accept_correct_rate"]
        print(f"[replay {rot}] A rec={a_rec:.3f} B rec={b_rec:.3f}",
              flush=True)
    a_pass = v2._bc_pass(results["A_RAW_CONCAT"])
    b_pass = v2._bc_pass(results["B_EDL"])
    out["safeguard_replay"] = {
        "A": {"recovery_pass": a_pass["recovery_pass"],
              "specificity_pass": a_pass["specificity_pass"],
              "per_rotation": {r: results["A_RAW_CONCAT"][r]["specificity"]
                               for r in ROTATIONS}},
        "B": {"recovery_pass": b_pass["recovery_pass"],
              "specificity_pass": b_pass["specificity_pass"],
              "per_rotation": {r: results["B_EDL"][r]["specificity"]
                               for r in ROTATIONS}},
        "recorded_flags_reproduced": bool(
            a_pass["recovery_pass"] is True and
            a_pass["specificity_pass"] is False and
            b_pass["recovery_pass"] is True and
            b_pass["specificity_pass"] is True),
    }
    return results


def primary_maha_scores(out: dict):
    """Per-state primary Mahalanobis scores for the central-seed cells,
    recomputed from PERSISTED weights (forward passes only)."""
    val_dir = VALDIR / "primary_replay"
    val_dir.mkdir(parents=True, exist_ok=True)
    for rot in ROTATIONS:
        key = v2.cell_key(CENTRAL, rot)
        cell = assemble_cell(CENTRAL, rot, OWG, GATE1)
        model = StrongOSREncoder()
        model.load_state_dict(torch.load(RUN / "cells" / key / "model.pt",
                                         map_location="cpu"))
        model.eval()
        fit_idx = np.flatnonzero(~cell["early"])
        geometries = {}
        for state in EVIDENCE_STATES:
            emb_fit, _ = encoder_forward(model, cell["features_train"],
                                         state, fit_idx)
            geometries[state] = fit_osr_geometry(
                emb_fit, cell["train_labels"][fit_idx], cell["known"])
        scores = {}
        for state in EVIDENCE_STATES:
            emb, _ = encoder_forward(model, cell["features_ev"], state,
                                     np.arange(len(cell["ev_labels"])))
            scores[state] = mahalanobis_min_distance(emb, geometries[state])
        np.savez_compressed(
            val_dir / f"{rot}_maha.npz",
            **{f"s_{s}": scores[s].astype(np.float64)
               for s in EVIDENCE_STATES},
            is_unknown=cell["ev_is_unknown"],
            split_role=cell["ev_split_role"],
            recoverable=cell["ev_recoverable"],
            groups=v2.group_codes(cell["ev_groups"]),
            labels=np.array([cell["known"].index(x) if x in cell["known"]
                             else -1 for x in cell["ev_labels"]],
                            dtype=np.int64),
            allow_pickle=False)
        print(f"[primary-replay {rot}] per-state maha persisted",
              flush=True)


def compare_interfaces(out: dict):
    """Same-sample Mahalanobis vs EDL comparison on central-seed cells."""
    comp = {}
    for rot in ROTATIONS:
        maha = np.load(VALDIR / "primary_replay" / f"{rot}_maha.npz")
        edl = np.load(VALDIR / "safeguards" / f"B_{rot}_scores.npz")
        rec = maha["recoverable"]
        unk = maha["is_unknown"]
        role = maha["split_role"]
        rk_rows = np.flatnonzero(rec & (~unk))
        unk_rows = np.flatnonzero(unk)
        # Known-ward gain per family: score_B - score_s (positive = moved
        # toward Known; both interfaces use novelty scores, higher = more
        # novel, so the same formula applies).
        def gains(store, rows):
            return {s: store["s_B"][rows] - store[f"s_{s}"][rows]
                    for s in LEGAL_STATES}
        m_rk = gains(maha, rk_rows)
        e_rk = gains(edl, rk_rows)
        m_un = gains(maha, unk_rows)
        e_un = gains(edl, unk_rows)
        # Best-legal / most-Known-ward per sample.
        m_rk_best = np.stack([m_rk[s] for s in LEGAL_STATES]).max(axis=0)
        e_rk_best = np.stack([e_rk[s] for s in LEGAL_STATES]).max(axis=0)
        m_un_best = np.stack([m_un[s] for s in LEGAL_STATES]).max(axis=0)
        e_un_best = np.stack([e_un[s] for s in LEGAL_STATES]).max(axis=0)
        # Direction disagreement: sign of gain for the best-legal state.
        rk_disagree = float(((m_rk_best > 0) != (e_rk_best > 0)).mean())
        un_disagree = float(((m_un_best > 0) != (e_un_best > 0)).mean())
        comp[rot] = {
            "rk_n": int(len(rk_rows)), "un_n": int(len(unk_rows)),
            "maha_rk_gain_mean": float(m_rk_best.mean()),
            "edl_rk_gain_mean": float(e_rk_best.mean()),
            "maha_un_gain_mean": float(m_un_best.mean()),
            "edl_un_gain_mean": float(e_un_best.mean()),
            "maha_gap": float(m_rk_best.mean() - m_un_best.mean()),
            "edl_gap": float(e_rk_best.mean() - e_un_best.mean()),
            "rk_direction_disagreement_frac": rk_disagree,
            "un_direction_disagreement_frac": un_disagree,
            "maha_un_best_gt_zero_frac": float((m_un_best > 0).mean()),
            "edl_un_best_gt_zero_frac": float((e_un_best > 0).mean()),
            "maha_rk_best_gt_zero_frac": float((m_rk_best > 0).mean()),
            "edl_rk_best_gt_zero_frac": float((e_rk_best > 0).mean()),
        }
        # Per-family means (both interfaces, RK and TU).
        for s in LEGAL_STATES:
            comp[rot][f"maha_rk_{s}"] = float(m_rk[s].mean())
            comp[rot][f"edl_rk_{s}"] = float(e_rk[s].mean())
            comp[rot][f"maha_un_{s}"] = float(m_un[s].mean())
            comp[rot][f"edl_un_{s}"] = float(e_un[s].mean())
    out["same_sample_comparison"] = comp
    return comp


def main() -> int:
    VALDIR.mkdir(parents=True, exist_ok=True)
    out: dict[str, Any] = {}
    # Identity.
    protocol = REPO / "docs/research_plan/strong_hybrid_osr_evidence_gate_v2_protocol.md"
    out["protocol_sha256_recomputed"] = hashlib.sha256(
        protocol.read_bytes()).hexdigest()
    reg = json.loads((REPO / "reports/research_audit/"
                      "strong_hybrid_osr_evidence_gate_v2_preregistration.json"
                      ).read_text())
    out["preregistration_sha256"] = reg["protocol_sha256"]
    manifest = json.loads((RUN / "run_manifest.json").read_text())
    out["run_manifest_sha256"] = manifest["protocol_sha256"]
    status = json.loads((RUN / "status.json").read_text())
    out["run_state"] = status["run_state"]
    out["all_9_complete"] = all(
        v == "COMPLETE" for v in status["cells"].values())
    aggregate = json.loads((RUN / "aggregate.json").read_text())
    out["recorded_decision"] = aggregate["decision"]

    cells = primary_rederivation(out)
    out["furk_ci_done"] = True
    replay_safeguards(out, cells)
    primary_maha_scores(out)
    compare_interfaces(out)
    (VALDIR / "validation_audit.json").write_text(
        json.dumps(out, indent=1, default=str), encoding="utf-8")
    print("[validation] VALIDATION_AUDIT_STATUS=COMPLETE", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
