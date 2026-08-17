# Recovery-Signal Characterization and Open-World Transfer Gate V2 — Frozen Protocol

Status: FROZEN_BEFORE_EVALUATION
Date: 2026-08-17
Schema: RECOVERY_SIGNAL_CHARACTERIZATION_V2_PROTOCOL_V1

This document is the preregistered, frozen protocol for
RECOVERY_SIGNAL_CHARACTERIZATION_AND_OPEN_WORLD_TRANSFER_GATE_V2.
It was committed BEFORE any V2 evaluation metric was computed.

Frozen historical context (unchanged, authoritative):

- CORE_HYPOTHESIS_GATE_1 = YELLOW
- CORE_HYPOTHESIS_GATE_1B = PASS
- OPEN_WORLD_RECOVERABILITY_GATE_V1 = FAIL
- OPEN_WORLD_V1_FAILURE_ATTRIBUTION = COMPLETE

V1 FAIL MUST NOT be changed or reinterpreted. The V1 diagnostic
established: FURK denominator correct; Evidence improves Known
classification; many Recoverable Known observations are class-recovered;
54.19% (pooled) of recovered Recoverable Known are still rejected
Unknown; post-Evidence MSP misalignment in 3/3 rotations;
policy-conditioned threshold subgroup shift in 3/3 rotations;
classification utility vs novelty-score utility weakly aligned;
True Unknown separation preserved; Credential/Web_Injection show
substantial router miss; V2 scientifically justified
(primary mechanism F2_POST_EVIDENCE_MSP_MISALIGNMENT).

---

## 0. Scientific interpretation rule

Failure of one implementation MUST NOT be interpreted as proof that
Evidence-conditioned open-world recognition is impossible, that the
recovery trajectory contains no information, or that no stronger method
could work. Allowed conclusions:

- SUPPORTED
- NOT_ESTABLISHED_UNDER_FROZEN_PROBES
- HIGH_RISK_UNDER_CURRENT_EVIDENCE_CONTRACT

"Impossible" is not an allowed conclusion. The purpose of the
preregistered two-capacity ladder (linear + nonlinear, matched) is to
reduce the alternative explanation "the relationship exists but the
chosen linear model is too weak."

## 1. Hypotheses

- H1_TRAJECTORY_SIGNAL: Evidence acquisition creates runtime-observable
  state transitions (PRE_STATE -> Evidence action -> POST_STATE) that
  contain information about whether the resulting Known prediction has
  become reliable.
- H2_INCREMENTAL_INFORMATION: Recovery-trajectory features contain
  predictive information beyond post-acquisition state alone.
- H3_OPEN_WORLD_TRANSFER: The incremental recovery information can
  reduce false-Unknown decisions among Recoverable Known observations
  without materially degrading True Unknown discrimination.
- H4_NONLINEARITY_ALTERNATIVE: Failure of a linear probe alone is
  insufficient evidence against H1/H2; therefore a fixed nonlinear probe
  is preregistered BEFORE evaluation.

## 2. Authorization boundary

AUTHORIZED: Phase A validation/checkpoint of V1 attribution (already
committed as 7604736); Phase B preregistration + implementation +
tests; Phase C execution of the frozen V2; reports; context update.

NOT AUTHORIZED: changing V1 results; changing Gate 1/1B; changing
B/BT/BR/BTR classifiers; changing the frozen P6 UTILITY_TYPED router;
retraining the router; changing Evidence definitions; changing Evidence
budget; changing Unknown rotations; detector shopping; Energy,
Mahalanobis, OpenMax, Dirichlet/evidential detectors; neural novelty
detector; pseudo-unknown detector search; Qwen / Model B; DeepSeek; RL;
continual learning; self-evolution buffer experiment; FINAL_TEST;
post-result threshold tuning; adding a third/fourth model family after
results.

## 3. Frozen inputs (V1 artifacts, unchanged)

Per (seed, rotation), with seeds 20260817/20260818/20260819 and
rotations Credential / Recon_Scanning / Web_Injection:

- `open_world_recoverability_gate_v1/owg_v1_seed_<s>_rotation_<r>_eval.parquet`
  — the full frozen VALIDATION table (56,000 rows) with columns:
  source_row_index, canonical_label, split_role (0=CALIB, 1=EVAL,
  frozen V1 CALIB/EVAL split), is_unknown, recoverable, residual_hard,
  activity_group_digest, temporal_block, and per-policy stored
  action/score/pred/rejected for P0/P1/P3/P4/P5/P6/P7.
- `owg_v1_seed_<s>_rotation_<r>_result.json` — frozen V1 result
  (thresholds, counts, metrics). Unchanged; only read for verification.
- `open_world_recoverability_gate_v1/models/owg_v1_seed_<s>_rotation_<r>_models.pkl`
  — frozen B/BT/BR/BTR classifiers and T/R/TR utility selectors.
- Gate-1 / Gate-1B roots for frozen feature tables and targets:
  `core_gate_v1/` (basic features, history features, targets).

Frozen constants (from run_open_world_recoverability_gate_v1.py):
FORMAL_SEEDS, ROTATIONS, CALIB_KNOWN_FALSE_UNKNOWN_RATE=0.05,
PRIMARY_COST_BUDGET_FRACTION=0.15, N_TEMPORAL_BLOCKS=20,
BOOTSTRAP_REPS=1000, BOOTSTRAP_RNG_OFFSET=161000.

## 4. Populations

Per (seed, rotation):

- VAL_GATE_EVAL: rows with split_role==1 in the frozen eval parquet
  (includes held-out outer Unknown rows, exposed ONLY for final
  evaluation metrics).
- VAL_CALIB Known: rows with split_role==0 and is_unknown==0.
- V2_PROBE_FIT, V2_PROBE_CALIB: a deterministic 60/40 split of
  VAL_CALIB Known (see Section 5).

Outer True Unknown must NEVER enter: probe fitting, feature-scaler
fitting, threshold calibration, hyperparameter selection, feature
design, or model selection.

## 5. V2_PROBE_FIT / V2_PROBE_CALIB split (frozen)

Split population: VAL_CALIB Known rows for the (seed, rotation).

Algorithm (deterministic, no RNG):

1. Groups = unique activity_group_digest values among split rows.
2. Each group's stratum = (canonical_label of the group's first row in
   frozen table order, temporal_block of that row).
3. Within each stratum, order groups by
   SHA256(seed_hex || rotation_utf8 || group_digest_bytes) ascending.
4. Assign groups in that order to the bin (FIT=0 / CALIB=1) with the
   smaller cumulative row count; ties go to FIT.
5. The resulting row ratio is approximately 60/40; exact ratio is
   determined by group atomicity (bounded by the largest group in each
   stratum).

Properties (verified by tests): group-disjoint (no group crosses
V2_PROBE_FIT / V2_PROBE_CALIB / VAL_GATE_EVAL), deterministic,
duplicate-safe (group-level, not row-level), class-stratified as
closely as practical at the (class, block) stratum level.

The per-cell group->role manifest is written to the large-artifact
directory and hashed (sha256) BEFORE any evaluation. If a frozen
artifact makes exact group isolation impossible, the tool must
STOP_NEEDS_REVIEW rather than weaken the split silently.

## 6. Frozen policy execution

On V2_PROBE_FIT, V2_PROBE_CALIB and VAL_GATE_EVAL rows, obtain:

- p_pre: Basic (B) Known-class probability vector (rotation-aligned),
- a: the frozen P6 UTILITY_TYPED action,
- p_post: probability vector of the classifier selected by a with
  mapping NONE->B, T->BT, R->BR, TR->BTR.

Prefer frozen persisted outputs (stored action/score/pred columns).
Probability vectors are not persisted by V1, so they are recomputed
deterministically from the frozen models with the same machinery the
V1 failure-attribution tool used, and the recomputation is
cross-verified against the stored columns (actions, scores, preds,
recoverable flag) before any metric is computed. No retraining.

## 7. Feature schemas (frozen)

Let i_pre=argmax(p_pre), i_post=argmax(p_post),
conf=max, margin=largest-second_largest,
entropy=H(p)/log(K) with K=len(rotation known classes) and the usual
0*log0=0 convention.

POST_ONLY (7 dims), in exact order:
1. conf_post
2. margin_post
3. entropy_post
4. ONEHOT_NONE
5. ONEHOT_T
6. ONEHOT_R
7. ONEHOT_TR

RECOVERY_TRAJECTORY (19 dims) = POST_ONLY followed by:
8. conf_pre
9. margin_pre
10. entropy_pre
11. delta_conf (conf_post - conf_pre)
12. delta_margin (margin_post - margin_pre)
13. delta_entropy (entropy_post - entropy_pre)
14. top1_changed (1[i_pre != i_post])
15. pre_prob_of_post_top1 (p_pre[i_post])
16. post_prob_of_pre_top1 (p_post[i_pre])
17. post_top1_support_gain (p_post[i_post] - p_pre[i_post])
18. pre_top1_support_change (p_post[i_pre] - p_pre[i_pre])
19. top1_transition_gap (p_post[i_post] - p_post[i_pre])

All features are runtime-observable. No GT label, no correctness flag,
no recoverability truth, no Unknown truth may enter inference features.

## 8. Supervised probe target

On V2_PROBE_FIT Known rows only:

ACCEPT_TARGET = 1 iff the frozen post-Evidence classifier's predicted
Known class (stored pred_P6_UTILITY_TYPED, cross-verified) equals the
true Known label; else 0.

GT is used to construct the fitting target on Known fitting data. GT is
NEVER an inference feature. No outer True Unknown sample enters fitting.

## 9. Capacity ladder (frozen, exactly two model families)

LEVEL 1 — LINEAR:
StandardScaler + LogisticRegression(penalty="l2", C=1.0,
solver="lbfgs", max_iter=2000, class_weight="balanced").
L_POST = linear POST_ONLY probe; L_TRAJ = linear RECOVERY_TRAJECTORY
probe. No tuning.

LEVEL 2 — NONLINEAR:
RandomForestClassifier(n_estimators=300, max_depth=10,
min_samples_leaf=20, max_features="sqrt",
class_weight="balanced_subsample", n_jobs=-1,
random_state=<rotation seed>).
N_POST = nonlinear POST_ONLY probe; N_TRAJ = nonlinear RECOVERY_TRAJECTORY
probe. No tuning.

No XGBoost/MLP/HGB or any other model family may be added after results.

## 10. Scores

Learned probes: P_ACCEPT = predicted probability of ACCEPT_TARGET=1;
S_ACCEPT = 1 - P_ACCEPT (higher = riskier / more Unknown-like).
MSP baselines: S_MSP = 1 - max(p).

## 11. Open-world methods (frozen)

- B0_BASIC_MSP: Basic observation, Basic MSP novelty score.
- B1_UTILITY_POST_MSP: frozen P6 acquisition + post-Evidence MSP.
- L_POST: frozen P6 + L_POST probe (S_ACCEPT).
- L_TRAJ: frozen P6 + L_TRAJ probe.
- N_POST: frozen P6 + N_POST probe.
- N_TRAJ: frozen P6 + N_TRAJ probe.

No detector may be added after results.

## 12. Known-only calibration (frozen)

For every method independently, run the full frozen policy on
V2_PROBE_CALIB Known rows and calibrate its score to
KNOWN_FALSE_UNKNOWN_RATE=5% using the frozen V1 semantics:
threshold = np.quantile(known_calib_scores, 1.0 - 0.05);
rejected = score >= threshold. Exact threshold per (rotation, seed,
method) is recorded. These are NEW V2 matched thresholds; they MUST NOT
overwrite V1 thresholds.

## 13. Signal-characterization metrics (Section 16 of task)

On VAL_GATE_EVAL Known rows (ACCEPT_TARGET defined there by labels),
for L_POST, L_TRAJ, N_POST, N_TRAJ report AUROC, AUPRC, balanced
accuracy at the calibration-derived operating point, Brier score, and
log loss of P_ACCEPT vs ACCEPT_TARGET. Primary comparison:
AUROC_TRAJ - AUROC_POST per capacity level. CIs via the pooled
group-atomic paired bootstrap (Section 17 below). No threshold tuning
using VAL_GATE_EVAL.

## 14. Signal status (frozen rules)

For each capacity level (LINEAR, NONLINEAR):

SIGNAL=SUPPORTED iff (rotation value = mean over seeds):
- mean over rotations of DeltaAUROC >= +0.01,
- DeltaAUROC positive in >=2/3 rotations,
- pooled paired-bootstrap 95% CI lower bound > 0.

Else SIGNAL=NOT_ESTABLISHED.

RECOVERY_TRAJECTORY_SIGNAL:
- STRONG if NONLINEAR_SIGNAL=SUPPORTED and (LINEAR_SIGNAL=SUPPORTED or
  linear DeltaAUROC positive in >=2/3 rotations).
- WEAK if at least one capacity shows consistently positive point
  estimates but the preregistered CI/size criteria are not fully met.
- NOT_ESTABLISHED if neither capacity shows stable incremental
  trajectory value.

NOT_ESTABLISHED is never interpreted as mathematical absence of signal.

## 15. Open-world evaluation metrics (VAL_GATE_EVAL)

Per method: FURK (raw numerator / fixed Recoverable-Known denominator);
RECOVERED_BUT_REJECTED_RATE (A2/denom); RECOVERY_CONDITIONAL_REJECTION
_RATE (A2/(A1+A2)); Known total false-Unknown rate; Known Macro-F1
before novelty rejection (method's own classification stage);
accepted-Known classification accuracy; Unknown AUROC; Unknown AUPR;
Unknown Recall @ 5% Known false-Unknown calibration point; OSCR (only if
already cleanly supported by the V1 metrics module — the V1 gate's
unknown_metrics module provides auroc/aupr/recall; OSCR is reported if
the frozen module exposes it, otherwise omitted with a note); True
Unknown acquisition rate; Evidence cost. Per seed, per rotation, pooled.

Recovered (classification-level) = method's classification-stage
prediction equals the true label (B0: pred_P0; B1/L*/N*: pred_P6).
A1 = recovered and accepted; A2 = recovered and rejected.

## 16. FURK identity audit

The frozen V1 Recoverable-Known definition is reused exactly. Within a
(rotation, seed), the exact Recoverable-Known EVAL row set must be
identical across B0, B1, L_POST, L_TRAJ, N_POST, N_TRAJ. Any mismatch
=> STOP_NEEDS_REVIEW.

## 17. Paired bootstrap protocol (frozen)

Pooled over 3 rotations x 3 seeds (9 cells). Units = private activity
groups (temporal-block-aware by construction: each row's
activity_group_digest and temporal_block columns are frozen and the
group is the atomic unit; per-group stratum composition is fixed).
Replicates = 1000 (BOOTSTRAP_REPS), RNG = np.random.default_rng(
BOOTSTRAP_RNG_OFFSET) — identical convention to the frozen V1 gate.
Per replicate: draw n_total_groups group ids with replacement and
recompute the pooled statistic from the drawn groups' rows; methods are
paired by construction (same draws for all methods).

Required comparisons:
- M1 vs B1 FURK (N_TRAJ vs B1 and L_TRAJ vs B1),
- M1 vs B2 FURK (N_TRAJ vs N_POST and L_TRAJ vs L_POST),
- N_TRAJ vs B0 FURK,
- 95% CIs (percentiles 2.5/97.5) for: FURK differences,
  Recovered-but-Rejected reduction, Unknown AUROC difference,
  Unknown Recall difference, signal DeltaAUROC.

## 18. Open-world trajectory transfer criteria (frozen)

T1: mean FURK_N_TRAJ - FURK_N_POST <= -0.03, improves in >=2/3
rotations, no rotation worsens by >0.02.
T2: mean absolute reduction in RECOVERY_CONDITIONAL_REJECTION_RATE
(N_TRAJ vs N_POST) >= 0.08, improves in >=2/3 rotations.
T3: mean AUROC_N_TRAJ >= AUROC_N_POST - 0.01, no rotation loses >0.03.
T4: mean Unknown Recall_N_TRAJ >= Unknown Recall_N_POST - 0.03, no
rotation loses >0.05.
T5: paired-bootstrap 95% CI upper bound of FURK_N_TRAJ - FURK_N_POST
< 0.

OPEN_WORLD_TRAJECTORY_TRANSFER = PASS iff T1-T5 all PASS, else
NOT_ESTABLISHED.

## 19. End-to-end criteria (frozen; secondary)

Compare strongest preregistered trajectory method N_TRAJ vs B0_BASIC_MSP:
E1: mean FURK_N_TRAJ <= mean FURK_B0 - 0.02 and improves in >=2/3
rotations.
E2: paired-bootstrap 95% CI upper bound of FURK_N_TRAJ - FURK_B0 < 0.
E3: True Unknown AUROC mean loss <= 0.01, no rotation loss > 0.03.
E4: True Unknown Recall mean loss <= 0.03, no rotation loss > 0.05.
END_TO_END_OPEN_WORLD_GAIN = PASS iff E1-E4 PASS, else NOT_ESTABLISHED.

## 20. Component headroom diagnostics (analysis only; not deployable)

26A ROUTER_RECOVERY_HEADROOM per rotation =
1 - P6_RECOVERY_RATE, where P6_RECOVERY_RATE = A/denom among
Recoverable-Known EVAL with the frozen P6 classification stage
(ORACLE_LEGAL_ACTION_RECOVERY_RATE = 1.0 by definition when at least
one of T/R/TR is correct — i.e., the recoverable definition itself).
Quantifies classification recovery unavailable because the frozen
router failed to select a rescuing legal action. The oracle is NEVER
presented as a method.

26B INTERFACE_HEADROOM_PROXY per rotation =
RECOVERY_CONDITIONAL_REJECTION_RATE (B1 = P6 with V2-matched threshold).
Not an attainable oracle score; quantifies downstream loss among rows
already recovered at classification level.

## 21. Failure interpretation matrix (frozen)

CASE A (SIGNAL=STRONG, TRANSFER=PASS, E2E=PASS):
C1_STATUS=RECOVERY_AWARE_OPEN_WORLD_MECHANISM_SUPPORTED;
NEXT_PROPOSED_ACTION=UNKNOWN_CANDIDATE_PURIFICATION_GATE_V2 (not run).

CASE B (SIGNAL=STRONG, TRANSFER=PASS, E2E=NOT_ESTABLISHED):
C1_STATUS=RECOVERY_SIGNAL_AND_INTERFACE_SUPPORTED_UPSTREAM_LIMITED;
NEXT_PROPOSED_ACTION=OPEN_WORLD_ROUTER_OBJECTIVE_GATE_V1 (not run).

CASE C (SIGNAL=STRONG, TRANSFER=NOT_ESTABLISHED):
C1_STATUS=RECOVERY_SIGNAL_SUPPORTED_OPEN_WORLD_MECHANISM_UNRESOLVED;
NEXT_PROPOSED_ACTION=RESEARCHER_REVIEW_FORMAL_MODEL_B_NOVELTY_DESIGN
(not started).

CASE D (SIGNAL=WEAK):
C1_STATUS=RECOVERY_SIGNAL_INCONCLUSIVE;
NEXT_PROPOSED_ACTION=RESEARCHER_REASSESS_COST_BENEFIT_BEFORE_MODEL_B.

CASE E (SIGNAL=NOT_ESTABLISHED): inspect headroom diagnostics. If
ROUTER_RECOVERY_HEADROOM large in >=2 rotations OR
INTERFACE_HEADROOM_PROXY large in >=2 rotations:
C1_STATUS=RECOVERY_TRAJECTORY_NOT_ESTABLISHED_CURRENT_REPRESENTATION_INCONCLUSIVE;
NEXT_PROPOSED_ACTION=RESEARCHER_REASSESS_MAINLINE_BEFORE_ANY_EXPENSIVE_MODEL.
Else:
C1_STATUS=RECOVERABILITY_MAINLINE_HIGH_RISK_UNDER_CURRENT_EVIDENCE_CONTRACT;
NEXT_PROPOSED_ACTION=RESEARCHER_REASSESS_PAPER_MAINLINE.
No automatic V3; no impossibility claims.

## 22. Descriptive statistics on prior observations (frozen, Section 32)

Using frozen V1 outputs only, report group/temporal-block bootstrap 95%
CIs for: Spearman rho between SIGNED_CLASSIFICATION_UTILITY
(g1b.utility_labels) and NOVELTY_SCORE_UTILITY (msp_pre - msp_post per
family T/R/TR over EVAL Known rows — identical construction to the V1
failure-attribution report), and HELP P(novelty score improves) /
P(worsens) rates. Descriptive only; does not alter V2 training or Gate
decisions. Allowed wording: "weak alignment under the evaluated
setting". No claim of universal independence.

## 23. RL status

RL is not run. RL_SEQUENTIAL_DECISION_JUSTIFICATION stays PLAUSIBLE
only if results continue to show myopic classification utility != final
open-world utility (the V1 diagnostic's RBR/RCJ/R3 evidence); otherwise
preserve the prior status. RL_REQUIRED=false always.

## 24. Relation to prior traffic work (document only; no implementation)

RoNeTC: uncertainty-aware open-set traffic recognition and multi-view
dynamic fusion of already observed evidence are prior art; lesson —
classification probability and open-set uncertainty should not
automatically be treated as identical objects.
RoeCi: adaptive extra computation on the same observation is prior art;
uncertainty formulation materially affects open-set behavior; lesson —
post-classification confidence alone may be insufficient.
GCLC: open-world detection/clustering/class evolution are prior art;
representation-space novelty and known-holdout calibration are useful
future references; GCLC does not model runtime Evidence-induced Known
recovery trajectory before novelty admission.
Candidate scope: RUNTIME_OBSERVATION_ACQUISITION + RECOVERY-STATE
MODELING + OPEN-WORLD DECISION. No broad "first" claims.

## 25. What V2 must not claim

No claims that classification-vs-novelty mismatch, confidence-based OSR
failure, learned uncertainty, selective prediction, or trajectory
modeling in general are new. Contribution remains narrower:
RECOVERY_AWARE_EVIDENCE_CONDITIONED_OPEN_WORLD_RECOGNITION — using
runtime Observation-Evidence-induced recovery state to distinguish
recovered Known from residual novelty.

## 26. Execution lock

Run exactly the preregistered implementation. After the first real V2
evaluation metric is observed, no scientific code/protocol changes are
permitted. A pure runtime bugfix is permitted only if scientific
semantics are unchanged, the bug is documented, the old/new diff is
recorded, and the protocol hash meaning remains unchanged. If scientific
behavior must change: STOP_NEEDS_REVIEW.

## 27. Output artifacts

- reports/research_audit/recovery_signal_characterization_gate_v2.md
- reports/research_audit/recovery_signal_characterization_gate_v2.json
- Large artifacts (NOT committed):
  /root/autodl-tmp/processed/dataset_v4_nf3_ton_v1/recovery_signal_characterization_gate_v2/
  (per-cell split manifests, probe models, feature matrices, bootstrap
  outputs).

## 28. Git policy

Authorized commits: (1) V1 failure-attribution checkpoint (done,
7604736); (2) V2 preregistration/code checkpoint before evaluation.
After V2 evaluation: DO NOT COMMIT result reports/context changes; DO
NOT PUSH. Leave results uncommitted for researcher review.

## 29. Safety ledger (must remain)

FINAL_TEST_MODELING_CONTAMINATION=false;
TRUE_UNKNOWN_USED_FOR_PROBE_TRAINING=false;
TRUE_UNKNOWN_USED_FOR_THRESHOLD_CALIBRATION=false;
ROUTER_RETRAINED=false; EVIDENCE_CONTRACT_CHANGED=false;
DETECTOR_SHOPPING=false; POST_RESULT_THRESHOLD_TUNING=false;
QWEN_API_CALLS=0; DEEPSEEK_API_CALLS=0; MODEL_B_TRAINING_STARTED=false;
RL_TRAINING_STARTED=false; CONTINUAL_TRAINING_STARTED=false;
UNKNOWN_CANDIDATE_PURIFICATION_STARTED=false.

## 30. Validation (pre-Phase-C and final)

Tests cover: outer True Unknown exclusion from probe fit, scaler fit,
threshold calibration; V2_PROBE_FIT/V2_PROBE_CALIB group isolation;
VAL_GATE_EVAL isolation; FINAL_TEST exclusion; exact frozen P6 action
reproduction; exact B/BT/BR/BTR action mapping; trajectory feature
formulas; no GT/correctness in runtime features; ACCEPT_TARGET only
during probe fit; matched model configuration (L_POST vs L_TRAJ,
N_POST vs N_TRAJ); independent score calibration; FURK denominator
identity; recovered-but-rejected definition; bootstrap pairing;
deterministic seeds. Full runs: compileall, targeted pytest, full
pytest, JSON parse, git diff --check, secret scan.
