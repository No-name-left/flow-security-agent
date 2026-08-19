# Strong Hybrid OSR Evidence Recoverability Gate V2 — Result

Date: 2026-08-18
Protocol: frozen V2 (sha256 50b1d7181d57bfa01008f2fb794d889ad34d302acaeb2050ae1db93cc79be5a7)
Preregistration commit: 22bf1f7 | Runner commit: 4e9005b

V1 remains immutable: GATE_INVALID_OSR_INADEQUATE,
EVIDENCE_SCIENTIFIC_STATUS=NOT_JUDGED.

## Run completeness

All 9 (rotation × seed) cells COMPLETE under the strengthened
determinism settings (fixed PYTHONHASHSEED, seeded Generators, torch
manual seeds, cudnn.deterministic=True, benchmark=False); weights,
embeddings, predictions, thresholds, per-cell metrics and training
curves persisted Git-externally under
`processed/dataset_v4_nf3_ton_v1/strong_hybrid_osr_evidence_gate_v2/`.

## Hybrid OSR adequacy — PASS (H1–H4)

- **H1 RF reproduction**: exact. Frozen-model predictions reproduce the
  stored P0/P6 outputs with 0 row mismatches in all 9 cells; Known
  Macro-F1 vs the frozen V1 result JSONs has max absolute difference
  **0.0** (tolerance 1e-3).
- **H2 Basic Unknown AUROC**: pooled 0.7665 vs frozen RF Basic 0.6359
  (−0.02 floor 0.6159); per rotation within the −0.05 floor. PASS.
- **H3 AUPR / Recall@5% Known FUR**: pooled recall 0.1639 vs RF 0.1416
  (−0.03 floor 0.1116); pooled AUPR 0.3593 vs RF 0.2855 (floor
  0.2555). PASS.
- **H4 dedicated geometry value**: Mahalanobis − Deep-MSP AUROC pooled
  +0.1242, 95% CI [0.0883, 0.1542], positive 3/3 rotations. PASS.

## Deployable Evidence gain — FAIL (partial)

| Metric (D0 → D1) | Credential | Recon | Web | Verdict |
|---|---|---|---|---|
| FURK | 0.0560 → 0.0472 | 0.0894 → 0.0999 | 0.0324 → 0.0234 | D1 FAIL (pooled −0.0024 > −0.02; Recon +0.011) |
| FURK paired bootstrap | CI [−0.0154, +0.0067] | | | D2 FAIL (upper > 0) |
| Unknown AUROC | −0.0072 | +0.0014 | +0.0035 | D3 PASS |
| Recall@5% FUR | −0.0433 | +0.0567 | −0.0284 | D4 PASS (pooled loss 0.0050) |
| Known Macro-F1 | +0.0224 | +0.0151 | +0.0085 | D5 PASS (improves) |
| Recoverable-Known accept-correct | 0 → 0.3946 | 0 → 0.8531 | 0 → 0.2542 | descriptive |

The hybrid FURK levels are dramatically lower than the V1 MSP-based
system (V1 P0 FURK 0.265/0.642/0.201) — the RF-known + Mahalanobis
novelty combination is a far stronger OSR — but the FURK improvement
from frozen-P6 Evidence acquisition is small and statistically
unsupported; the deployable gain criteria therefore fail while
classification, AUROC and recall protections all pass.

## Evidence recovery signal — PASS

Offline best-legal oracle (GT-guided, never deployed): pooled
accept-correct rate 0.950 (per rotation 0.950 / 0.937 / 0.966) vs
Basic 0.000 (by construction: recoverable rows are Basic-wrong);
paired bootstrap CI [0.9416, 0.9570]. Legal Evidence can recover
essentially all frozen Recoverable Known in the hybrid system when the
oracle is allowed to choose the state.

## Evidence specificity — FAIL (primary) / contradicted (safeguard)

Mahalanobis Known-ward gains: True Unknown's most Known-ward legal
state moves it toward Known regions MORE than Recoverable Known's
best-legal state in all three rotations (gap −41.6 / −97.1 / −28.3;
pooled CI [−61.6, −45.9]). The conservative True-Unknown stress test
fails: Evidence is not specific to recoverable Known under this
geometry.

Per the preregistered false-negative protection, the conditional
safeguards ran (central seed 20260817):

- A raw-normalized-concat: recovery PASS, specificity FAIL.
- B Dirichlet/evidential (EDL): recovery PASS, **specificity PASS**.

A materially contradictory strong positive → per the contradiction
rule the decision is METHOD_DEPENDENT_REVIEW rather than NO-GO.

## Final decision

**METHOD_DEPENDENT_REVIEW** (preregistered contradiction rule).
Evidence scientific status:
**METHOD_DEPENDENT_PENDING_RESEARCHER_REVIEW** — the recovery signal
is strong and the hybrid OSR is adequate, but the specificity result
depends on the novelty representation (Mahalanobis geometry fails,
EDL belief passes); the deployable P6 gain is small. Researcher review
is required; nothing is committed or pushed.
