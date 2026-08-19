# Strong Neural OSR Evidence Recoverability Gate V1 — Post-Run Validation

Date: 2026-08-18
Scope: independent validation of the completed frozen gate run. No
retraining, no protocol modification, no threshold/hyperparameter
tuning, no V2 experiment, no FINAL_TEST, no commit/push of results.

## 1. Protocol identity

- `docs/research_plan/strong_neural_osr_evidence_gate_v1_protocol.md`
  recomputed SHA256 = `0ebf5c8c3af20eedb07800f97db3627e16e35c895ed5420fc2fe3d2e8d18dc7c`
  — **matches** the authoritative value.
- Preregistration
  `reports/research_audit/strong_neural_osr_evidence_gate_v1_preregistration.json`
  (HEAD after `f23607a`) records the same protocol sha256 and
  `FROZEN_BEFORE_EVALUATION`; the three preregistration-consistency
  tests pass at HEAD (tool constants == preregistration; protocol hash
  == preregistration field).
- Run manifest (`run_manifest.json`) echoes the same sha256.
- Executed runner: `tools/run_strong_neural_osr_evidence_gate_v1.py`
  at commit `0fd06ca` (cells computed by the identical code after
  `3d4df57`, whose diff is restricted to the bool-cast fix).

### Frozen A1–A4 adequacy definitions (verbatim from the sha-pinned protocol §7)

Evaluated with the Basic-state encoder on VAL_GATE_EVAL. Adequacy PASS
iff ALL of:

- **A1 Known classification**: per-rotation Known Macro-F1 ≥ 0.90 AND
  pooled mean ≥ frozen RF Basic pooled mean − 0.01.
- **A2 Unknown discrimination**: pooled mean Unknown AUROC ≥ frozen RF
  Basic pooled mean − 0.02 AND no rotation more than 0.05 below that
  rotation's frozen RF Basic AUROC.
- **A3 Recall**: pooled mean Unknown Recall@5% Known FUR ≥ frozen RF
  Basic pooled mean − 0.03 AND no rotation more than 0.05 below that
  rotation's frozen RF Basic recall.
- **A4 Dedicated open-set value over same-encoder Deep MSP**: pooled
  paired bootstrap mean (Mahalanobis AUROC − Deep MSP AUROC) ≥ +0.010,
  positive in ≥ 2/3 rotations, pooled 95% CI lower bound > −0.02.

If adequacy FAILS: decision = GATE_INVALID_OSR_INADEQUATE. Evidence may
NOT be declared failed.

## 2. Pre-evaluation bugfix provenance

| Commit | Time | Nature | Pre-first-metric? | Verdict |
|---|---|---|---|---|
| `f23607a` | 18:23 | TRAIN split recorded counts corrected (np.isin recording bug); split RULE unchanged | Caught by the runner's own pre-training `TRAIN_SPLIT_MISMATCH` guard BEFORE any training | VALID — bookkeeping only |
| `3d4df57` | 18:29 | int8 parquet columns cast to bool (integer fancy-indexing bug); regression test added | Buggy intermediate runs never persisted any cell JSON (NaN/non-finite guards); all persisted cell artifacts have mtimes 18:30–18:34, strictly after this fix | VALID — implementation only |
| `0fd06ca` | 18:37 | Aggregate router-headroom now read from frozen eval parquet stored columns (read-only) instead of unpersisted arrays | First persisted `aggregate.json` is 18:38, after the fix; cell results unchanged | VALID — implementation only |

No commit after evaluation changed any scientific semantic; all three
carry BUGFIX_LOG entries consistent with the frozen execution lock.

## 3. Run completeness

- All 9 (seed × rotation) cells `COMPLETE` in `status.json`; per-cell
  JSON + rows/bc npz artifacts exist with post-fix timestamps.
- Frozen eval parquets: 56,000 rows/cell; TRAIN pool = 150,000 Known
  rows/cell (runtime cross-check passed; the fixed-run log portion has
  0 `TRAIN_SPLIT_MISMATCH`/`EXCEPTION` lines).
- Frozen Recoverable-Known identity: per-cell FURK denominators
  re-derived from the frozen `recoverable` column equal the recorded
  `furk_denom` in every cell (e.g., Credential 1396) — **identity
  preserved**.
- FINAL_TEST: appears only in the runner's safety docstring; no data
  path touches it.
- True-Unknown leakage: policy thresholds re-derived as the 95th
  percentile over `split_role==0 & ~is_unknown` rows of the saved
  scores match the recorded thresholds to 1e-9 in all 9 cells — Known-only
  calibration confirmed numerically; TRAIN FIT/EARLY_STOP populations
  are partition-0 Known rows only (runtime cross-check + code review).
- Router: `models.pkl` is never loaded by the runner; P6
  actions/preds come exclusively from the frozen stored columns — no
  router retraining. Evidence features come from the frozen Gate-1
  tables with the frozen transforms — no Evidence-contract change.

## 4. Independent re-derivation from saved frozen outputs

Re-derived from the frozen V1 eval parquet (labels, flags, stored P0
scores/preds, recoverable) + saved per-row npz (Mahalanobis D0/D1
scores, groups): frozen RF Basic Macro-F1 / AUROC / Recall@5%FUR, D0/D1
calibration thresholds, D0/D1 Known-vs-Unknown AUROC / AUPR /
Recall@5%FUR, FURK(D0), FURK(D1), recoverable denominators. **All 11
checks × 9 cells match the recorded cell JSON values within 1e-9.**

Limitation (recorded honestly): the trained encoder weights were not
persisted, so Basic Known Macro-F1 and Deep-MSP AUROC of the strong OSR
cannot be recomputed from raw model outputs. They were validated by
internal consistency (per-cell `adequacy_cell.auroc_maha` == re-derived
D0 AUROC in every cell) and by reproducing the aggregate arithmetic on
the recorded cell values.

### Re-computed adequacy (frozen rules)

| Criterion | Value | Rule | Result |
|---|---|---|---|
| A1 per-rotation | Credential 0.8766 / Recon 0.9459 / Web 0.9120 | each ≥ 0.90 | **FAIL (Credential)** |
| A1 pooled | 0.9115 | ≥ frozen RF pooled 0.9340 − 0.01 = 0.9240 | **FAIL** |
| A2 pooled | 0.7615 | ≥ 0.6359 − 0.02 = 0.6159 | PASS |
| A2 per-rotation | within 0.05 of frozen RF in 3/3 | — | PASS |
| A3 pooled | 0.1574 | ≥ 0.1416 − 0.03 = 0.1116 | PASS |
| A3 per-rotation | within 0.05 in 3/3 | — | PASS |
| A4 pooled | +0.1238 | ≥ +0.010 | PASS |
| A4 rotations positive | 3/3 (+0.062 / +0.194 / +0.115) | ≥ 2/3 | PASS |

**OSR_ADEQUACY = FAIL** (A1 fails) → the recorded decision
`GATE_INVALID_OSR_INADEQUATE` is correct under the frozen decision
matrix. Per §7/§11, Evidence is **NOT declared failed**.

### Launch-NOTE A1 ambiguity resolution

The frozen, sha-pinned protocol is the only authority. It states:
**A1 pooled delta = −0.01** (Known Macro-F1 vs frozen RF Basic pooled);
the −0.02 figure belongs to **A2** (Unknown AUROC). The tool constant
(`A1_POOLED_MACRO_F1_RF_DELTA = -0.01`), the preregistration JSON
(`A1_known_macro_f1.pooled_minus_rf_basic_pooled: -0.01`), and the
launch NOTE all agree. The earlier "−0.02" discussion conflated A2's
rule. Moreover A1 fails under **either** reading (pooled 0.9115 <
0.9340−0.01 = 0.9240 and < 0.9340−0.02 = 0.9140; the per-rotation
0.90 floor fails on Credential regardless), so the ambiguity cannot
affect the decision.

## 5. Evidence-potential / specificity / deployable

Because OSR_ADEQUACY = FAIL, per the frozen protocol these metrics are
reported for completeness only and carry **no Evidence verdict**:

- B (potential): PASS (rate 0.953, standardized effect +0.766, CI
  [0.748, 0.788]; 3/3 rotations rate > 0.55; true-class distance
  improves 3/3).
- C (specificity): FAIL (Recon_Scanning gap −32.96; ratio bound
  violated).
- D (deployable): FAIL (FURK delta −0.0069 / +0.0106 / −0.0091; no
  rotation-worst violation but pooled/CI criteria unmet).
- Router headroom: material (frozen P6 recovery rate 0.395 / 0.927 /
  0.254).

None of these changes the gate outcome: adequacy gates first.

## 6. Diagnostic-only characterization of the A1 failure

(Descriptive; no tuning performed or proposed.)

- **Concentration**: the failure is concentrated in the **Credential
  rotation** — strong-OSR Known Macro-F1 0.8798 / 0.8639 / 0.8861
  across the three seeds (all < 0.90). Web_Injection 20260818
  (0.8888) is the only other sub-0.90 cell. Recon_Scanning is
  consistently strong (0.9445–0.9472).
- **Difficulty is not specific to the strong OSR**: the frozen RF
  Basic baseline itself scores only 0.9196 / 0.8887 / 0.9106 on
  Credential (its weakest rotation; sub-0.90 in one seed). The strong
  OSR lags the frozen RF baseline on Macro-F1 in **9/9 cells**
  (gaps 0.008–0.040), i.e., its Known classification head is
  consistently below the frozen tree probe.
- **Class-level context (frozen RF baseline, stored preds)**: in the
  Credential rotation the frozen RF's weak classes are Benign (0.73–
  0.79) and Recon_Scanning (0.73–0.87) — the known
  Benign/Recon_Scanning confusability pattern documented in V1. The
  strong OSR's own per-class F1 is **not re-derivable**: the encoder's
  per-row predictions were not persisted (limitation of the saved
  artifacts).
- **Training behavior**: 8/9 cells ran to the 20-epoch cap without
  early-stop trigger; 1/9 (Credential seed 20260817) stopped at epoch
  10 via patience. Reaching the cap in most cells is consistent with
  slow convergence within the frozen budget; the validation-loss
  trajectory was not saved, so a stronger underfitting claim is not
  supported.
- **Train vs early-stop vs eval gap**: not computable — train-side
  metrics were not persisted.
- **Representation/classification mismatch evidence**: A4 (+0.062 /
  +0.194 / +0.115 Mahalanobis-over-Deep-MSP Unknown AUROC) shows the
  embedding separates Known from Unknown better than its own softmax,
  while A1 shows the Known head underperforms the frozen RF. This is a
  classification-head/geometry mismatch pattern, descriptive only.

## 7. Verdict

- Run is complete, deterministic, restartable, and internally
  consistent; every re-derivable quantity matches the recorded outputs.
- The gate decision **GATE_INVALID_OSR_INADEQUATE** is the correct
  application of the frozen decision matrix (adequacy FAIL → INVALID).
- **Evidence scientific status: NOT JUDGED** — per the frozen
  protocol, the Evidence contract is neither supported nor failed by
  this run; the OSR was not adequate to judge it.
- Results remain uncommitted/unpushed, awaiting researcher review.
