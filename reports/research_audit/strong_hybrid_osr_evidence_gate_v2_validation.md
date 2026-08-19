# Strong Hybrid OSR Evidence Recoverability Gate V2 — Post-Run Validation

Date: 2026-08-18
Scope: read-only finalization of the persisted validation audit
(`processed/dataset_v4_nf3_ton_v1/strong_hybrid_osr_evidence_gate_v2/validation_v2/`).
The V2 validation computation was already COMPLETE
(`VALIDATION_AUDIT_STATUS=COMPLETE`, process exited). This report only
verifies the persisted audit for internal completeness and records the
formal validation outputs. **No rerun, no retraining, no safeguard
replay, no new experiment, no FINAL_TEST, no commit, no push.**

Companion machine-readable artifact:
`reports/research_audit/strong_hybrid_osr_evidence_gate_v2_validation.json`
(primary). This MD is the explanatory context.

## 1. Protocol / preregistration identity

- Frozen protocol `docs/research_plan/strong_hybrid_osr_evidence_gate_v2_protocol.md`
  recomputed SHA256 = `50b1d7181d57bfa01008f2fb794d889ad34d302acaeb2050ae1db93cc79be5a7`
  — **matches** the authoritative value.
- Preregistration
  `reports/research_audit/strong_hybrid_osr_evidence_gate_v2_preregistration.json`
  (commit `22bf1f7`) records the **same** `protocol_sha256`.
- Run manifest (`run_manifest.json`) echoes the **same** sha256.
- Executed runner: commit `4e9005b` (the documented V2 runtime
  bugfix — aggregate-return fix — committed **before** the final
  aggregate; the audit re-derives all 9 cell outputs directly from the
  frozen stored rows/bc_rows/weights, so the fix cannot change any
  persisted scientific result).
- `PROTOCOL_HASH_MATCH=YES`, `PREREGISTRATION_MATCH=YES`.

## 2. Run completeness

- `run_state=COMPLETE`; **all 9 (rotation × seed) cells COMPLETE** in
  `status.json` (Credential/Recon_Scanning/Web_Injection ×
  20260817/20260818/20260819).
- 56,000 eval rows per cell; 8,000 True Unknown per rotation in every
  replayed population; determinism settings recorded (fixed
  PYTHONHASHSEED, seeded Generators, torch manual seeds,
  `cudnn.deterministic=True`, `benchmark=False`).
- `validation_stdout.log` ends with `VALIDATION_AUDIT_STATUS=COMPLETE`,
  contains zero errors; all persisted arrays (primary_replay + safeguards
  npz) load with the expected shapes and flags.
- FINAL_TEST unused; router not retrained; Evidence contract unchanged.

## 3. Hybrid OSR adequacy — H1–H4 (independent rederivation)

| Criterion | Rule (frozen) | Value | Result |
|---|---|---|---|
| H1 RF reproduction | 0 row mismatches; Known Macro-F1 ≈ frozen V1 result JSON (tol 1e-3) | p0 mismatch 0, p6 mismatch 0; frozen F1 0.9196/0.9391 reproduced exactly (max diff 0.0) | **PASS** |
| H2 Basic Unknown AUROC | pooled ≥ RF pooled − 0.02; every rotation ≥ RF − 0.05 | pooled neural 0.7666 vs RF 0.6359 (+0.131); rotations 0.738/0.751/0.812 vs floors 0.648/0.388/0.722 | **PASS** |
| H3 Recall / AUPR | pooled ≥ RF pooled − 0.03; every rotation ≥ RF − 0.05 (both metrics) | Recall pooled 0.1639 vs 0.1416 (+0.022); AUPR pooled 0.3593 vs 0.2855 (+0.074); rotations within floor 3/3 | **PASS** |
| H4 dedicated geometry value | pooled paired bootstrap (Maha − Deep MSP) ≥ +0.01; positive ≥ 2/3; CI lower > −0.02 | pooled +0.1242, 95% CI [+0.0883, +0.1542]; positive 3/3 (+0.081 / +0.194 / +0.115) | **PASS** |

**HYBRID_OSR_ADEQUACY = PASS** (H1 AND H2 AND H3 AND H4), matching the
recorded aggregate.

## 4. Deployable Evidence gain (rederived)

- FURK re-derived per cell from frozen rows: pooled Basic 0.0593 →
  P6 0.0569; per-rotation delta Credential −0.0088 / Recon **+0.0106** /
  Web −0.0091 → D1 FAIL; paired CI upper **+0.0067 > 0** → D2 FAIL;
  AUROC/Recall/F1 protections all PASS (D3/D4/D5).
- Hybrid FURK levels are far below the V1 MSP system (V1 P0 FURK
  0.265/0.642/0.201) — the RF-known + Mahalanobis combination is a much
  stronger OSR — but the P6 Evidence gain is small and statistically
  unsupported.
- `DEPLOYABLE_EVIDENCE_GAIN=false`, unchanged from the recorded result.

## 5. Evidence recovery signal (rederived)

Offline best-legal oracle (GT-guided, never deployed): pooled
accept-correct 0.951 (0.950 / 0.937 / 0.966) vs Basic 0.000 (by
construction); paired bootstrap CI [0.9416, 0.9570].
`EVIDENCE_RECOVERY_SIGNAL=true` — legal Evidence can recover essentially
all frozen Recoverable Known in the hybrid system.

## 6. Primary Mahalanobis specificity — FAIL

Mahalanobis Known-ward gains: True Unknown's most-Known-ward legal state
moves it toward Known **more** than Recoverable Known's best-legal state
in all three rotations:

| Rotation | gap (RK gain − TU gain) |
|---|---|
| Credential | −41.65 |
| Recon_Scanning | −97.12 |
| Web_Injection | −28.28 |

Pooled gap −54.16, 95% CI [−61.61, −45.92] (entirely negative); median
pool −65.02; `ratio_ok` false in every rotation.
`PRIMARY_MAHALANOBIS_SPECIFICITY=FAIL` — the conservative True-Unknown
stress test fails under this geometry.

## 7. Conditional safeguards replay (central seed 20260817)

Per the preregistered false-negative protection, both safeguards were
replayed with the exact frozen recipe and per-sample persistence; the
replayed aggregate flags **reproduce the recorded flags exactly**
(`recorded_flags_reproduced=true`).

| Safeguard | Recovery | Specificity | Per-rotation gap | Verdict |
|---|---|---|---|---|
| A raw-normalized-concat | PASS | **FAIL** | −20.5 / −44.7 / −79.7 (ratio_ok false 3/3) | reproduces recorded flag |
| B Dirichlet/EDL | PASS | **PASS** | +0.155 / +0.212 / +0.229 (ratio_ok true 3/3) | reproduces recorded flag |

- `RAW_CONCAT_SPECIFICITY=FAIL` — the raw-concat geometry shares the
  primary failure.
- `EDL_SPECIFICITY=PASS` — the evidential belief interface meets its own
  specificity criteria in all three rotations (its own PASS criteria,
  preregistered).
- A materially contradictory strong positive exists → per the
  preregistered contradiction rule this routes to
  METHOD_DEPENDENT_REVIEW, **not** NO-GO.

## 8. EDL implementation / calibration / population validity

Verified in the frozen runner code against the preregistered B_EDL
recipe, plus the persisted epoch logs and scores:

- **EDL_IMPLEMENTATION_VALID=YES** — `EDLHeadEncoder`: identical trunk +
  Dirichlet head, `alpha = softplus(z)+1 ≥ 1` by construction; loss =
  Type-II ML + fixed KL `lambda = 0.1`; AdamW lr 3e-4 / weight decay
  1e-4; 20-epoch cap; patience 3 (epoch logs: B cells ran to the cap with
  best states at epochs 19–20, lr 3e-4); novelty score
  `1 − max(alpha/S)` (higher = more novel).
- **EDL_KNOWN_ONLY_FIT=YES** — trained on the frozen TRAIN FIT/EARLY_STOP
  pools (partition-0 Known rows only), same Known-only training contract
  as the primary.
- **EDL_KNOWN_ONLY_CALIBRATION=YES** — per-state thresholds are the 95th
  percentile over `(split_role==0 & ~is_unknown)` rows only (explicit
  exclusion mask). Diagnostic: 4,426 / 3,404 / 4,078 True-Unknown rows
  are present inside the `split_role==0` partition (Credential / Recon /
  Web) but are **excluded by the mask**, consistent with the primary
  run's previously validated Known-only calibration convention.
- **EDL_SCORE_DIRECTION_VALID=YES** — gains `s_B − s_s` positive = moved
  toward Known; the EDL gap is positive 3/3 exactly as recorded.
- **EDL_POPULATION_MATCH=YES** — central seed 20260817, all three
  rotations, 56,000 eval rows incl. 8,000 True Unknown per rotation —
  the identical eval rows as the primary Mahalanobis interface.

## 9. Same-sample Mahalanobis-vs-EDL contradiction

On the **same central-seed rows** (per-sample, identical populations):

| Rotation | Mahalanobis gap | EDL gap | RK direction disagreement | UN direction disagreement |
|---|---|---|---|---|
| Credential | −46.13 | +0.155 | 8.1% | 8.9% |
| Recon_Scanning | −108.86 | +0.212 | 31.9% | 3.8% |
| Web_Injection | −30.05 | +0.229 | 8.6% | 44.7% |

- `MAHALANOBIS_VS_EDL_CONTRADICTION_REPRODUCED=YES`.
- `CONTRADICTION_BY_ROTATION=3/3` — the sign of the mean gap flips
  between interfaces in **all three rotations** (Mahalanobis negative
  3/3, EDL positive 3/3).
- `CONTRADICTION_BROAD_OR_CONCENTRATED=Broad at the aggregate level`
  (every rotation flips sign); per-sample direction disagreement is
  material but rotation/class-specific (up to 31.9% on Recon
  Recoverable-Known, up to 44.7% on Web True-Unknown), so the two
  interfaces also diverge per-sample on a material minority.

## 10. Final decision

- Recorded decision: **METHOD_DEPENDENT_REVIEW**.
- Decision-matrix application validated: adequacy PASS (H1–H4) +
  recovery PASS + deployable FAIL + primary Mahalanobis specificity FAIL
  → preregistered NO_GO path → safeguards triggered → A_RAW_CONCAT
  specificity FAIL + B_EDL specificity PASS (materially contradictory
  strong positive) → preregistered contradiction rule →
  METHOD_DEPENDENT_REVIEW.
- `FINAL_GATE_DECISION_VALIDATED=YES` — the recorded decision is the
  correct application of the frozen decision matrix. It is reported as
  recorded and **not reinterpreted into PASS or FAIL**.

## 11. Evidence scientific status

`EVIDENCE_SCIENTIFIC_STATUS=METHOD_DEPENDENT_PENDING_RESEARCHER_REVIEW`
(as recorded): the recovery signal is strong and the hybrid OSR is
adequate, but the specificity result depends on the novelty
representation (Mahalanobis geometry fails, EDL belief passes), and the
deployable P6 gain is small and statistically unsupported. The Evidence
verdict is not finalized.

## 12. Commit / next-action state

- `RESULT_COMMITTED=false`, `RESULT_PUSHED=false` (nothing committed or
  pushed by this task).
- `NEXT_PROPOSED_ACTION=RESEARCHER_REVIEW_OF_METHOD_DEPENDENCE`
  (proposal only; `NEXT_ACTION_AUTHORIZED=false` — not authorization).
