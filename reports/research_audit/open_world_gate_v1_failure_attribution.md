# Open-World Gate V1 Failure Attribution and FURK Audit — Report

> Status: **COMPLETE** (diagnostic-only; V1 result unchanged: FAIL)
>
> Date: 2026-08-17
>
> Task: `OPEN_WORLD_V1_FAILURE_ATTRIBUTION_AND_FURK_AUDIT`
>
> Primary result JSON: `reports/research_audit/open_world_gate_v1_failure_attribution.json`
> (copied verbatim from the diagnostic tool output, untracked, do not commit)
>
> Diagnostic tool: `tools/run_open_world_gate_v1_failure_attribution.py`
> (module docstring is the pre-registration; implemented before any result)
>
> Tests: `tests/tools/test_open_world_gate_v1_failure_attribution.py`
>
> Frozen artifacts: `processed/dataset_v4_nf3_ton_v1/open_world_recoverability_gate_v1/`
> (Git-external, unchanged; `owg_v1_failure_attribution.json` written there)
>
> This report is a NEW diagnostic report. It does NOT rewrite the frozen
> historical reports (`open_world_recoverability_gate_v1.{md,json}`,
> `core_hypothesis_gate_v1b.{md,json}`, `core_hypothesis_gate_v1.{md,json}`).

## 0. Scope and safety

This task is diagnostic-only. It did NOT change the V1 result, retrain any
classifier or utility selector, change the acquisition budget, change the
novelty score, change any novelty threshold, evaluate any alternative
novelty detector, run Open-World V2, run Phase C purification, start
Qwen / Model B / RL / continual learning, or use FINAL_TEST. No rescue
experiment was run. The V1 FAIL checkpoint commit `4fc7591` exists
(local, push blocked: no GitHub credentials); ALL diagnostic outputs
(tool, tests, report md/json, context updates) remain UNCOMMITTED and
UNPUSHED for researcher review (Section 19 of the task contract).

```text
OPEN_WORLD_GATE_V1_RESULT=FAIL            (frozen report, unchanged)
V1_RESULT_CHANGED=false
FINAL_TEST_MODELING_CONTAMINATION=false
OPEN_WORLD_GATE_V2_STARTED=false
PHASE_C_EXECUTED=false
MODEL_B_TRAINING_STARTED=false
QWEN_API_CALLS=0
DEEPSEEK_API_CALLS=0
RL_TRAINING_STARTED=false
CONTINUAL_TRAINING_STARTED=false
```

## 1. Question

Given the frozen Open-World Recoverability Gate V1 FAIL (FURK utility
+0.235 vs direct, 9/9 cells), WHERE does the recoverable-Known
false-Unknown failure come from — and is a prospective V2 justified by a
specific, data-supported mechanism?

**Answer: the FURK denominator is sound (PASS); the failure is a
post-Evidence MSP novelty interface problem, not a routing, calibration,
or implementation problem alone.** Four mechanisms are dominant in
>=2/3 rotations (F1 classification-utility target mismatch 2/3,
F2 post-Evidence MSP misalignment 3/3, F3 policy-conditioned calibration
subgroup shift 3/3, F4 router selection failure 2/3); the primary
mechanism is F2 (3/3). V2_JUSTIFICATION=YES with the prospective
requirement: **the novelty interface must explicitly model recovery
state rather than post-classification MSP alone**.

## 2. Frozen context (unchanged, summarized)

- Gate V1 FAIL (2026-08-17, commit 4fc7591): typed utility acquisition
  worsens recoverable-Known false-Unknown (FURK P6 − P0 = +0.235 mean,
  9/9 cells worse, paired bootstrap CI [0.082, 0.290]); True Unknown
  recognition preserved; Known classification improves.
- Rotations: Credential / Recon_Scanning / Web_Injection (whole-class
  held out, = TRUE_UNKNOWN). Seeds 20260817/18/19. VAL_CALIB/VAL_GATE_EVAL
  group-atomic temporal-block-aware 50/50 split, frozen manifest + sha256.
- Policies P0..P7 as frozen; this diagnostic uses only frozen stored
  per-cell eval parquets (per-policy action/score/pred/rejected columns),
  frozen models + selectors (recomputed VALIDATION predictions purely for
  cross-verification), and frozen per-cell result JSONs. P2 is stored only
  as mean-over-100-reps furk (no per-row decisions, by design).
- RECOVERABLE_KNOWN = Basic wrong ∧ (BT∨BR∨BTR correct);
  RESIDUAL_HARD = Basic wrong ∧ all wrong (label-based, offline).

## 3. Cross-verification of the diagnostic against frozen artifacts

All 11 checks PASS in all 9 cells (CELL_STATUS=PASS 9/9):
EVAL_TABLE_SHA256_MATCH, SOURCE_ROW_ORDER_MATCH, BASIC_PRED_MATCH,
BASIC_MSP_MATCH, RECOVERABLE_FLAG_MATCH, RESIDUAL_HARD_FLAG_MATCH,
DIGEST_COLUMN_MATCH, BLOCK_COLUMN_MATCH, TYPED_ACTIONS_MATCH
(recomputed frozen typed policy with budget 0.15·N per population),
TYPED_SCORES_MATCH (allclose 1e-12), TYPED_REJECTED_SELF_CONSISTENT,
TYPED_REJECTED_MATCH (recomputed flips confined to |score−thr| ≤ 1e-12 —
ulp-level float nondeterminism from parallel predict_proba thread order;
the stored threshold comparison is the frozen authority),
FURK_DENOMINATOR_MATCH_RESULT_JSON, FURK_NUMERATOR_P0_MATCH.

## 4. FURK denominator audit (Section 2 of the contract) — PASS

For every rotation × policy (P0,P2,P3,P4,P5,P6), the denominator is the
same single stored per-row Recoverable-Known mask:

| rotation | denominator (per seed 17/18/19) | identical across 6 policies | row identity |
|---|---|---|---|
| Credential | 1396 / 1569 / 1633 (pooled 4598) | yes | PASS |
| Recon_Scanning | 453 / 435 / 510 (pooled 1398) | yes | PASS |
| Web_Injection | 1053 / 1200 / 1234 (pooled 3487) | yes | PASS |

Row identity is verified not merely by counts: the stored `recoverable`
column equals the frozen-model-recomputed Recoverable-Known flag per row
(RECOVERABLE_FLAG_MATCH), and the stored activity-group digest and
temporal-block columns are row-aligned to the frozen targets view
(DIGEST_COLUMN_MATCH, BLOCK_COLUMN_MATCH). The P0 denominator matches the
frozen per-cell result JSON in 9/9 cells
(FURK_DENOMINATOR_MATCH_RESULT_JSON).

**FURK_DENOMINATOR_AUDIT = PASS.** No REPORTING_BUG, no
METRIC_IMPLEMENTATION_BUG, no TARGET_ALIGNMENT_BUG. The failure is real
on the frozen denominator.

## 5. FURK numerator recomputation (Section 3) — EXACT agreement

Raw numerators recomputed directly from the stored per-row decisions
(P0) and stored per-row rejected flags under each policy:

| rotation | denom | numerator P0 | numerator P6 | FURK P0 | FURK P6 |
|---|---|---|---|---|---|
| Credential | 4598 | 1220 | 2295 | 0.2653 | 0.4991 |
| Recon_Scanning | 1398 | 895 | 1034 | 0.6402 | 0.7396 |
| Web_Injection | 3487 | 702 | 2043 | 0.2013 | 0.5859 |

Per-cell `matches_frozen_cell_furk` = True for every deterministic policy
in every cell (9/9 cells; P2 excluded by design: stored mean only). The
rotation-level rates above are denominator-weighted pooled rates and
differ at the third decimal from the frozen report's rotation rows, which
are means of per-cell rates (frozen vs pooled: Credential P0 0.2651 vs
0.2653, Credential P6 0.4999 vs 0.4991, Recon P0 0.6418 vs 0.6402, Recon
P6 0.7398 vs 0.7396, Web P0 0.2009 vs 0.2013, Web P6 0.5745 vs 0.5859).
Both aggregations are over the identical per-cell numerators and
denominators, which match the frozen artifacts exactly; the aggregation
method (mean-of-cell-rates vs pooled) is the only difference.

## 6. Recovered-but-rejected (Section 4)

A = selected-Evidence class correct; A1 = recovered ∧ accepted;
A2 = recovered ∧ rejected. Rates over the recoverable-Known EVAL
population:

| rotation | A | A1 | A2 | RECOVERED_BUT_REJECTED_RATE (A2/denom) | RECOVERY_CONDITIONAL_REJECTION_RATE (A2/(A1+A2)) | RECOVERED_AND_ACCEPTED_RATE (A1/denom) |
|---|---|---|---|---|---|---|
| Credential | 1837 | 1114 | 723 | 0.1572 | 0.3936 | 0.2423 |
| Recon_Scanning | 1297 | 345 | 952 | 0.6810 | 0.7340 | 0.2468 |
| Web_Injection | 887 | 383 | 504 | 0.1445 | 0.5682 | 0.1098 |
| pooled | 4021 | 1842 | 2179 | 0.2298 | 0.5419 | 0.1943 |

~39%–73% of CLASSIFICATION-recovered rows are still rejected as Unknown
by the utility policy — evidence acquisition recovers the class but the
novelty decision still rejects. This is the core F2 signature.

## 7. Four-stage transitions P0 → P6 (Section 5), recoverable targets

Stage 3 (Basic direct novelty) → Stage 4 (post-Evidence novelty):

| rotation | Known→Known | Unknown→Known | Known→Unknown | Unknown→Unknown | B-wrong→post-correct→Unknown |
|---|---|---|---|---|---|
| Credential | 1679 | 624 | 1699 | 596 | 723 |
| Recon_Scanning | 85 | 279 | 418 | 616 | 952 |
| Web_Injection | 1093 | 351 | 1692 | 351 | 504 |

Attention transitions: (a) **Direct Known → Utility Unknown** (1699 /
418 / 1692) — recoverable rows already Known under P0 flipped to Unknown
under P6; (b) **Basic-wrong → post-Evidence-correct → final Unknown**
(723 / 952 / 504) — rows the Evidence models correctly classify are
nevertheless rejected as Unknown. Both are novel-signal failures of the
post-acquisition MSP score, not of classification.

## 8. MSP score shift by subgroup (Section 6)

Mean per-row shift POST − PRE (P6 scores minus P0 scores):

| subgroup | Credential | Recon_Scanning | Web_Injection |
|---|---|---|---|
| A Basic-sufficient Known | −0.0075 | −0.0005 | −0.0101 |
| B Recoverable Known (all) | +0.0049 | −0.0128 | +0.0025 |
| B1 Recoverable, class recovered | −0.0595 | −0.0267 | −0.0369 |
| B2 Recoverable, class NOT recovered | +0.0196 | n/a (≈0) | n/a |
| C Residual-hard Known | −0.0125 | +0.0394 | −0.0157 |
| D True Unknown | −0.0126 | −0.0026 | −0.0079 |

Answer to the Section 6 question: Evidence DOES recover the class
(B1 shifts −0.027 to −0.060 toward Known) but NOT enough to cross the
threshold — recovered rows' post-Evidence MSP remains high (B1 median
shift only −0.005 on seed 20260817/Credential; B P95 stays 0.459 vs
0.313 threshold). The recovered subgroup's novelty score is not made
Known-like under MSP.

## 9. Threshold migration (Section 7) — no new thresholds created

Frozen policy-conditioned thresholds (mean over seeds; threshold =
95th percentile of Known post-acquisition scores on VAL_CALIB):

| rotation | thr P0 (direct) | thr P6 (utility) | Δ (P6−P0) |
|---|---|---|---|
| Credential | 0.3407 | 0.3113 | −0.0294 |
| Recon_Scanning | 0.2556 | 0.1704 | −0.0853 |
| Web_Injection | 0.3395 | 0.2983 | −0.0412 |

The utility threshold DROPS in 7/9 cells (0.000 in 2 cells). The
calibration-population evidence (new, direct, not asserted):
VAL_CALIB Known POST P95 vs PRE P95 shifts −0.029 / −0.085 / −0.041
pooled while VAL_CALIB Recoverable POST P95 shifts +0.011 / +0.052 /
−0.004. I.e., the easy-Known calibration mass becomes MORE confident
under acquisition (threshold mass moves down), while the Recoverable
subgroup's scores stay high — the fixed 5%-Known-FUR calibration then
rejects recoverable rows at a higher rate. This is F3 with direct
calibration-side evidence (per-cell in the JSON under
`calibration_population_shifts`). No new threshold was created; the
values above are frozen.

## 10. Classification utility vs novelty utility (Section 8)

NOVELTY_SCORE_UTILITY_E = MSP_BASIC − MSP_BASIC_PLUS_E vs the frozen
Gate-1B SIGNED_CLASSIFICATION_UTILITY (Spearman, EVAL Known population):

| rotation | Spearman T | Spearman R | Spearman TR | HELP rows: novelty improve / unchanged / worsen |
|---|---|---|---|---|
| Credential | 0.163 | 0.237 | 0.251 | 0.446 / 0.038 / 0.516 |
| Recon_Scanning | 0.082 | 0.097 | 0.134 | 0.531 / 0.041 / 0.428 |
| Web_Injection | 0.144 | 0.234 | 0.289 | 0.406 / 0.047 / 0.547 |

Correlation is weak (0.08–0.29). On classification-HELP rows, novelty
utility IMPROVES only 41–53% of the time and WORSENS 43–55% — for a
substantial share of the rows the supervised utility labels as HELPFUL,
the acquired Evidence makes the MSP novelty score WORSE (further from
Known). The utility target (class recovery) does not align with the
novelty objective (open-world decision). This is F1 with raw rates.
Nothing here is trained on novelty utility.

## 11. Router vs novelty failure, P6 recoverable targets (Section 9)

| category | Credential | Recon_Scanning | Web_Injection |
|---|---|---|---|
| R1 ROUTER_MISS (selected fails, another legal Evidence state correct) | 2761 (0.600) | 101 (0.072) | 2600 (0.746) |
| — R1_NONE (budget-forced no acquisition) | 1710 (0.372) | 37 (0.026) | 1178 (0.338) |
| — R1_ACQUIRED_WRONG_FAMILY | 1051 (0.229) | 64 (0.046) | 1422 (0.408) |
| R2 POST_EVIDENCE_CLASSIFICATION_FAILURE | 0 | 0 | 0 |
| R3 RECOVERED_BUT_REJECTED | 723 (0.157) | 952 (0.681) | 504 (0.145) |
| R4 THRESHOLD_SHIFT_CONTRIBUTION (counterfactual-only) | 861 (0.187) | 160 (0.114) | 971 (0.278) |
| R3 ∩ R4 | 68 | 157 | 53 |
| R4 without R3 | 793 | 3 | 918 |

R2 = 0 definitionally (recoverable ⇒ some family correct; selected-wrong
⇒ R1). R3 ∩ R4 is small: 83–90% of recovered-but-rejected rows have
post-Evidence MSP scores ABOVE even the frozen DIRECT threshold — i.e.,
rejection is driven by the scores themselves, not (mainly) by the
threshold drop. R4 is counterfactual-only and is NEVER presented as an
alternative method; the direct threshold is not a candidate solution.

## 12. Selection overlap (Section 10)

On the SAME fixed Recoverable-Known population (frozen P3/P4 vs P6
actions; per-cell, seed 20260817/Credential shown):

- **P3 LOW_CONFIDENCE vs P6**: BOTH 938, ONLY_HEURISTIC 201,
  ONLY_UTILITY 40, NEITHER 217. ONLY_UTILITY rows: recovery rate 1.00,
  final rejection 0.275 — utility does better than the heuristic on its
  exclusive rows, but the pool is tiny (40). ONLY_HEURISTIC rows: 0.00
  recovery, 0.896 rejection.
- **P4 HIGH_ENTROPY vs P6**: BOTH 389, ONLY_HEURISTIC 220,
  ONLY_UTILITY 589, NEITHER 198. ONLY_UTILITY rows: recovery 0.382,
  rejection 0.635; ONLY_HEURISTIC rows: 0.00 recovery, 0.818 rejection.

The two heuristics overlap the utility selection very differently
(P3 shares most of P6's selection; P4 is largely disjoint). In every
subset, NEITHER rows are never acquired and never rejected (rejection
0.000) — the failure is entirely among selected rows.

## 13. Action-conditional P6 (Section 11)

| rotation | action | n | recovery rate | recovered-but-rejected rate | mean post MSP | FURK contribution |
|---|---|---|---|---|---|---|
| Credential | NONE | 1710 | 0.00 | 0.000 | — | 0.234 |
| Credential | T | 1005 | 0.45 | 0.144 | — | 0.107 |
| Credential | R | 457 | 0.98 | 0.041 | — | 0.019 |
| Credential | TR | 1426 | 0.66 | 0.238 | — | 0.140 |
| Recon_Scanning | NONE | 37 | 0.00 | 0.000 | — | 0.013 |
| Recon_Scanning | T | 337 | 0.97 | 0.159 | — | 0.166 |
| Recon_Scanning | R | 446 | 0.96 | 0.211 | — | 0.226 |
| Recon_Scanning | TR | 578 | 0.94 | 0.374 | — | 0.335 |
| Web_Injection | NONE | 1178 | 0.00 | 0.000 | — | 0.259 |
| Web_Injection | T | 1850 | 0.25 | 0.070 | — | 0.276 |
| Web_Injection | R | 299 | 0.99 | 0.043 | — | 0.013 |
| Web_Injection | TR | 160 | 0.79 | 0.394 | — | 0.037 |

R recovers 96–99% of its acquired rows and contributes little FURK — but
gets few acquisitions (457/446/299). T/TR dominate the budget, and their
recovered-but-rejected share is high (Credential TR 0.238, Recon TR
0.374, Web TR 0.394). The failure is NOT concentrated in a single family
(F5 not supported), but T/TR rows carry most of it. (Mean post-Evidence
MSP per action is in the JSON.)

## 14. True Unknown check (Section 12)

| rotation | AUROC Δ (P6−P0) | mean score shift | separation |
|---|---|---|---|
| Credential | +0.0143 | −0.0126 | PRESERVED |
| Recon_Scanning | +0.0017 | −0.0026 | PRESERVED |
| Web_Injection | +0.0135 | −0.0079 | PRESERVED |

**TRUE_UNKNOWN_SEPARATION_PRESERVED = true in 3/3 rotations** (ΔAUROC ≥
−0.01 margin, consistent with the frozen OW3 result). True Unknown
recognition is not the failure locus.

## 15. Failure attribution F0–F7 (Section 13)

Rule application on raw counts (frozen scores/thresholds; no tuning):

| mechanism | rotations supported | evidence |
|---|---|---|
| F0 implementation/denominator error | 0 | denominator audit PASS, 9/9 cross-verification PASS |
| F1 classification-utility target mismatch | 2/3 (Credential, Web) | HELP-novelty improve rate 0.45 / 0.53 / 0.41 < 0.5 in 2/3 |
| F2 post-Evidence MSP misalignment | 3/3 | RBR > 0.1 ∧ RCJ > 0.2 in 3/3 (0.157/0.681/0.145; 0.394/0.734/0.568) |
| F3 policy-conditioned calibration subgroup shift | 3/3 | |Δthreshold| > 0.01 in 3/3 (−0.029/−0.085/−0.041); calibration-side P95 evidence |
| F4 router selection failure | 2/3 (Credential, Web) | R1 share 0.60 / 0.07 / 0.75 > 0.3 in 2/3 |
| F5 evidence-action-specific failure | 0 | no single action carries >60% of rejected rows |
| F6 True-Unknown separation failure | 0 | preserved 3/3 |
| F7 no clear dominant | 0 | — |

**DOMINANT_MECHANISMS = [F1, F2, F3, F4]; PRIMARY = F2
(POST_EVIDENCE_MSP_MISALIGNMENT, 3/3).**

## 16. V2 justification (Section 14)

All five conditions hold: (1) denominator audit PASS; (2) clear mechanism
in ≥2/3 rotations; (3) the mechanism names a specific conceptual
correction; (4) definable without held-out True Unknown GT; (5) no
detector shopping (no Energy/Mahalanobis/OpenMax/neural binary detector
or any concrete replacement was evaluated or recommended).

**V2_JUSTIFICATION = YES.**
**PROSPECTIVE_V2_DESIGN_REQUIREMENT = "novelty interface must explicitly
model recovery state rather than post-classification MSP alone"**
(primary mechanism F2). The requirement is a conceptual correction, not a
replacement detector.

## 17. RL relevance (Section 15) — analysis only, no RL run

Pooled over all rotations: R3 (recovered-but-rejected) = 2179,
R4 (threshold-shift contribution, counterfactual) = 1992 of 9483
recoverable targets (R3/denom = 0.23 > 0.15). The acquisition/stopping
decision carries a downstream open-world consequence (Known vs Unknown)
that the supervised classification-utility label does not encode.
**RL_SEQUENTIAL_DECISION_JUSTIFICATION = PLAUSIBLE.** This is analysis
only: no RL was run, and RL is NOT claimed to be required. RL is not used
as a rescue mechanism for this gate.

## 18. Status update (Section 16)

```text
C1_STATUS=V1_MECHANISM_FAILED_V2_PROSPECTIVE_JUSTIFIED
M1_STATUS=CLASSIFICATION_CONDITIONAL_UTILITY_SUPPORTED_ONLY
C2_STATUS=PAUSED_NOT_SUPPORTED_BY_V1
SELF_EVOLUTION_STATUS=PLANNED_BUT_NOT_AUTHORIZED_PENDING_OPEN_WORLD_FOUNDATION
```

## 19. Safety ledger

```text
FINAL_TEST_MODELING_CONTAMINATION=false  (frozen VALIDATION-derived tables only;
                                          verified structurally: 0 FINAL_TEST rows)
OPEN_WORLD_GATE_V2_STARTED=false
PHASE_C_EXECUTED=false
MODEL_B_TRAINING_STARTED=false
QWEN_API_CALLS=0
DEEPSEEK_API_CALLS=0
RL_TRAINING_STARTED=false
CONTINUAL_TRAINING_STARTED=false
NO_THRESHOLD_CREATED=true             (only frozen thresholds read)
BASIC_THRESHOLD_NOT_PRESENTED_AS_METHOD=true  (R4 counterfactual-only)
NO_FROZEN_REPORT_REWRITTEN=true
DIAGNOSTIC_COMMIT_CREATED=false
DIAGNOSTIC_PUSHED=false
```

## 20. Consequences for the mainline

1. The V1 FAIL stands on a verified denominator: no implementation,
   reporting, or target-alignment bug. The failure is in the
   evidence-to-novelty-score path.
2. Classification recovery and novelty recovery are DIFFERENT objectives:
   the frozen utility selector (Gate-1B labels, class-recovery-based)
   provably recovers classes (Macro-F1 +0.015, recovery 0.525) but the
   post-acquisition MSP novelty score does not follow (RBR 0.23 pooled,
   RCJ 0.54 pooled, R3=2179).
3. The router matters at the margin (F4, 2/3) but is not the bottleneck:
   R1 is 0.07 in Recon_Scanning (3/3 F2 evidence) and even budget-forced
   NONE rows (R1_NONE) are a smaller share than R3.
4. The calibration threshold drop (F3, 3/3, direct CALIB evidence) is a
   real but secondary contributor: R3∩R4 is only 68/157/53 rows.
5. The proposed V2 direction is a conceptual novelty-interface change —
   explicitly modeling recovery state — NOT a new detector and NOT a
   threshold re-tune, and it is definable without held-out True Unknown
   GT. Any V2 protocol requires researcher authorization.
