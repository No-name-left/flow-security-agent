# Agent Context

STATE_SCHEMA=AGENT_CONTEXT_V1
LAST_UPDATED=2026-08-18
UPDATED_BY_TASK=INSTRUCTION_HYGIENE_AND_STRONG_OSR_AUTHORIZATION_V1

This is the single short entry point every agent reads before substantive project
work. It carries only the current state and operating rules. Historical detail
lives in the sources listed under "Read on demand".

## Authority

Repository artifacts override conversational or persistent Agent memory.

SOURCE_OF_TRUTH_PRIORITY=

1. researcher-authorized frozen protocol / contract
2. formal report JSON
3. formal report MD
4. canonical artifact manifest / hash
5. this file
6. PROJECT_HANDOFF
7. vendor bootstrap (AGENTS.md)
8. conversational / persistent Agent memory

If a higher-priority source conflicts with a lower-priority one, use the
higher-priority one. If same-level authoritative artifacts conflict, output
`PROJECT_STATE_CONFLICT=NEEDS_REVIEW` and STOP.

## Stable operating rules

- Master split is immutable.
- FINAL_TEST is protected unless explicitly authorized.
- Evidence must obey strict past-only runtime availability.
- Teacher is not GT (not classification / utility / Unknown / recoverability /
  continual / RL-reward GT).
- No hidden rescue experiment after a preregistered gate result.
- Do not relabel PASS / YELLOW / FAIL after results.
- The V2 protocol's "neural novelty detector NOT AUTHORIZED" clause was
  task-scoped to RECOVERY_SIGNAL_CHARACTERIZATION_GATE_V2. It is not a
  permanent project-wide prohibition: any future novelty-scoring method
  (including the Strong Neural OSR baseline) still requires its own
  researcher-authorized, preregistered protocol (see DEC-0028).
- Large artifacts stay outside Git.
- Never force push.
- Use PROVISIONAL / NOT_RUN / NEEDS_REVIEW instead of guessing.
- NEXT_PROPOSED_ACTION is not authorization.
- Only CURRENT_AUTHORIZED_TASK or an explicit researcher prompt authorizes
  execution.

## Current research state

```text
PROJECT_STAGE=CORE_HYPOTHESIS_VALIDATION

CORE_DATASET=NF3-ToN-IoT
MASTER_SPLIT_STATUS=FROZEN
FINAL_TEST_STATUS=PROTECTED

TEACHER_CACHE_STATUS=FROZEN_COMPLETE_2000_VALID
SEMANTIC_REFERENCE_STATUS=FROZEN_COMPLETE_63_VALID
TEACHER_CACHE_MODEL=deepseek-v4-flash
CORE_HIGH_TOKEN_DEEPSEEK_DEPENDENCY_COMPLETE=true

TEACHER_ACTION_COVERAGE=STOP_AND_CLASSIFY 741 / ACQUIRE_TEMPORAL 1259
  / ACQUIRE_RELATION 0 / ENTER_NOVELTY_DETECTION 0
(TEACHER_SUPERVISOR_BASELINE=VALID; policy demonstration is
valid-with-action-support-limitation; imitation init is limited, not default)

CORE_HYPOTHESIS_GATE_1=YELLOW        (do not relabel PASS)
GATE_0=PASS
GATE_1_TEMPORAL_STATUS=MODEST_CONSISTENT_POSITIVE
GATE_1_RELATION_STATUS=OVERALL_NEGATIVE_CONDITIONAL_VALUE_UNRESOLVED
GATE_1_FULL_STATUS=NEGATIVE_AT_FROZEN_RF_PROBE
GATE_1_AGGREGATE_BOOTSTRAP_COMPLETENESS=COMPUTED_OPTIONAL_CHECK
  (2026-08-17, pooled paired group bootstrap from frozen predictions;
  consistent with Gate 1 = YELLOW; cannot change it)

CORE_HYPOTHESIS_GATE_1B=PASS        (2026-08-17; see gate v1b report)
GATE_1B_TEMPORAL_STATUS=PASS        (T1-T7: 7/7)
GATE_1B_RELATION_STATUS=CONDITIONALLY_USEFUL
EVIDENCE_DIVERSITY_STATUS=TEMPORAL_PLUS_RELATION_CONDITIONALLY_USEFUL
ADAPTIVE_EVIDENCE_ACQUISITION_STATUS=SUPPORTED_FOR_CLASSIFICATION
  (Gate 1B), NOT_SUPPORTED_FOR_MSP_NOVELTY_SCORING (Gate V1 2026-08-17)
OPEN_WORLD_RECOVERABILITY_GATE=FAIL (2026-08-17; see open-world gate report;
  OW1/OW2/OW7 fail, severe: FURK_UTILITY > FURK_DIRECT 9/9 cells,
  mean +0.235, CI [0.082, 0.290]; True Unknown AUROC/recall preserved;
  Known Macro-F1 +0.015; mechanism: post-acquisition MSP novelty scoring
  does not transfer classification recovery to novelty recovery)
V1_FAILURE_ATTRIBUTION=COMPLETE (2026-08-17; diagnostic only, V1 FAIL
  unchanged; FURK denominator audit PASS (identical across 6 policies per
  rotation, row identity verified); dominant mechanisms F1 2/3, F2 3/3
  (primary), F3 3/3, F4 2/3; True Unknown separation preserved 3/3;
  V2_JUSTIFICATION=YES — novelty interface must explicitly model recovery
  state rather than post-classification MSP alone; NO detector
  recommendation; RL relevance PLAUSIBLE (analysis only, R3=2179 of 9483)
UNKNOWN_CANDIDATE_PURIFICATION_GATE=NOT_RUN (B=FAIL -> STOP per B17)
SELF_EVOLUTION_PURIFICATION_FOUNDATION=NOT_ESTABLISHED
MODEL_B_STATUS=NOT_STARTED
RL_STATUS=NOT_STARTED
OPEN_WORLD_CAUSAL_GATE_STATUS=REASSESS_MAINLINE (FAIL)
CONTINUAL_STATUS=NOT_STARTED

STRONG_NEURAL_OSR_AUTHORIZATION=DEC-0028 (2026-08-18): preregistered
  pre-Model-B baseline authorized at protocol-drafting level only;
  protocol not yet drafted; evaluation requires a frozen
  protocol + preregistration commit BEFORE any evaluation metric
STRONG_NEURAL_OSR_STATUS=NOT_STARTED

RECOVERY_SIGNAL_CHARACTERIZATION_GATE_V2=COMPLETE (2026-08-17;
  preregistered commit 22c92c7, protocol sha256
  b1d01629215470ba425c52f76dc5547c8bf4cb8e810a1ebcad30a853be2a5b7b;
  frozen V1 results unchanged)
V2_LINEAR_SIGNAL=NOT_ESTABLISHED   (mean DeltaAUROC +0.0009, CI [-0.0031, +0.0041])
V2_NONLINEAR_SIGNAL=NOT_ESTABLISHED (mean DeltaAUROC +0.0002, CI [-0.0048, +0.0045])
V2_RECOVERY_TRAJECTORY_SIGNAL=WEAK (linear positive 2/3 rotations, +0.0058/+0.0031,
  but pooled CI lower <= 0 and mean < +0.01; nonlinear positive 1/3)
V2_OPEN_WORLD_TRAJECTORY_TRANSFER=NOT_ESTABLISHED
  (T1=False: Web_Injection FURK worsens +0.021 > 0.02; T2=True: RCJ
   reduction mean 0.154, CI [-0.235, -0.028]; T3=True; T4=True;
   T5=False: FURK_N_TRAJ-N_POST CI upper +0.037 > 0)
V2_END_TO_END_OPEN_WORLD_GAIN=NOT_ESTABLISHED (E1-E4 all False:
   FURK_N_TRAJ 0.500 > FURK_B0 0.292; Unknown AUROC -0.020 vs B0;
   Unknown Recall -0.130 vs B0)
V2_CASE=D -> C1_STATUS=RECOVERY_SIGNAL_INCONCLUSIVE
  NEXT_PROPOSED_ACTION=RESEARCHER_REASSESS_COST_BENEFIT_BEFORE_MODEL_B
V2_FURK_DENOMINATOR_IDENTITY=PASS (9483 pooled, uniform across all 6
  methods and all 9 cells; per-cell 1396/453/1053/1569/435/1200/1633/510/1234)
V2_POOLED_FURK= B0 0.2921 / B1 0.5273 / L_POST 0.5736 / L_TRAJ 0.5818
  / N_POST 0.5166 / N_TRAJ 0.5002
V2_ACCEPT_AUROC= L_POST 0.9191 / L_TRAJ 0.9211 / N_POST 0.9137 / N_TRAJ 0.9144
V2_HEADROOM= ROUTER_RECOVERY_HEADROOM 0.605/0.073/0.746,
  INTERFACE_HEADROOM_PROXY 0.376/0.683/0.526 (Credential/Recon/Web;
  analysis only, not a gate)
V2_SPEARMAN= T 0.134 [0.101,0.165] / R 0.203 [0.153,0.250] / TR 0.235 [0.209,0.259]
V2_HELP_IMPROVE= T 0.458 / R 0.571 / TR 0.446
V2_HELP_WORSEN= T 0.501 / R 0.380 / TR 0.509
V2_RL_SEQUENTIAL_DECISION_JUSTIFICATION=PLAUSIBLE (classification-utility
  vs open-world utility diverge: accept AUROC 0.91+ but FURK 0.50, RCJ 0.24)
V2_RL_REQUIRED=false
V2_RESULT_COMMITTED=true (2026-08-18 researcher-review checkpoint commit,
  local only)
V2_RESULT_PUSHED=false
```

## Novelty positioning (literature audit 2026-08-17, revision 1)

```text
C1=RECOVERABILITY_CONDITIONED_OPEN_WORLD_TRAFFIC_RECOGNITION
C1_SCOPE=RUNTIME_OBSERVATION_ACQUISITION_BEFORE_NOVELTY
  (primary novelty is observation acquisition, NOT adaptive computation;
   mechanism = partial/basic observation -> adaptive acquisition of
   previously unobserved runtime-legal observation evidence ->
   reclassification before novelty handling)
C1_CORE_DISTINCTION=INSUFFICIENT_OBSERVATION_OF_KNOWN != TRUE_NOVELTY
C1_STATUS=PLAUSIBLY_NOVEL_PENDING_FULL_TRAFFIC_OSR_REVIEW
  (Known = Basic-sufficient + Evidence-recoverable + Residual-hard)
M1=RECOVERABILITY_AND_HARM_AWARE_TYPED_EVIDENCE_ROUTING
C2_CONDITIONAL=EVIDENCE_GATED_UNKNOWN_CANDIDATE_PURIFICATION_FOR_SELF_EVOLUTION
  (precise scope: remove Evidence-recoverable Known from the
   unknown-candidate stream BEFORE clustering / human verification /
   new-class adaptation; PLAUSIBLE_NOVELTY_PENDING_OPEN_WORLD_AND_CONTINUAL_VALIDATION)
SELF_EVOLUTION_STATUS=PLANNED_CORE_SYSTEM_LOOP_PENDING_PURIFICATION_AND_CONTINUAL_VALIDATION
SELF_EVOLUTION_NOVELTY_IS_NOT_CONTINUAL_LEARNING_ITSELF=true
POLICY_CONDITIONED_NOVELTY_CALIBRATION=REQUIRED_FOR_NEXT_GATE
NON_CHEATING_PRE_ACQUISITION_ROUTER=true
READ_ONLY_EVIDENCE_ACQUISITION_ASSUMPTION=true
UTILITY_VS_DIFFICULTY_ROUTING=REQUIRED (LOW_CONFIDENCE/HIGH_ENTROPY/UTILITY_SELECTOR)
RL_CORE_NOVELTY=false
FURK_STATUS=PROPOSED_RECOVERABILITY_CONDITIONED_FALSE_UNKNOWN_DIAGNOSTIC
EVIDENCE_SPECIALIZATION_STATUS=EMPIRICAL_ANALYSIS_NOT_STANDALONE_NOVELTY
FULL_LITERATURE_NOVELTY_AUDIT_STATUS=INCOMPLETE_ONE_ACCESS_LIMITED_PAPER
GENERIC_AFA_NOVELTY=false
TYPED_EVIDENCE_NOVELTY=false
UNCERTAINTY_BEFORE_REJECTION_NOVELTY=false
ADAPTIVE_COMPUTATION_BEFORE_REJECTION_NOVELTY=false
MULTI_VIEW_FUSION_NOVELTY=false
OPEN_WORLD_TRAFFIC_NOVELTY=false
NEW_CLASS_DISCOVERY_NOVELTY=false
CONTINUAL_TRAFFIC_NOVELTY=false
BUFFER_PURIFICATION_NOVELTY=false
```

Full-text review (2026-08-17, completed externally by the researcher
workflow; the local Agent did NOT access those PDFs):
`RONETC_FULL_TEXT_REVIEW=COMPLETE_EXTERNAL_RESEARCHER_WORKFLOW`
`ROECI_FULL_TEXT_REVIEW=COMPLETE_EXTERNAL_RESEARCHER_WORKFLOW`
`GCLC_FULL_TEXT_REVIEW=COMPLETE_EXTERNAL_RESEARCHER_WORKFLOW`
`ACO_ICML_2024_FULL_METHOD_REVIEW=PENDING` (MEDIUM_HIGH, does NOT block
empirical gates; must be reviewed before final first/novelty claims)
`ACCESS_LIMITED_CRITICAL_PAPERS=1`

Prior-art boundary (RoNeTC/RoeCi/GCLC full-text): uncertainty before
rejection, adaptive computation before rejection, multi-view dynamic
fusion, open-world traffic recognition, new-class discovery/clustering/
human-confirmation/incremental-update, open-world continual evolution —
all PRIOR_ART_EXISTS. RoeCi adds capacity/compute to the SAME observation;
OURS acquires previously unobserved observation evidence + reclassifies
before novelty.

Full prior-art register, claim-safety table:
`reports/research_audit/related_work_novelty_reassessment_v1.{md,json}` and
addendum `docs/research_plan/literature_novelty_reassessment_v1.md`
(non-frozen; does not alter DEC-0025/0027 frozen contracts).

## Current authorization

```text
CURRENT_AUTHORIZED_TASK=STRONG_NEURAL_OSR_PROTOCOL_DRAFT_AND_REVIEW
  (DEC-0028, 2026-08-18: draft the preregistered Strong Neural OSR
   Evidence Gate protocol and submit it for researcher review. No
   evaluation may run until the frozen protocol + preregistration are
   committed before any evaluation metric. This supersedes the V2
   waiting state: V2 CASE D = RECOVERY_SIGNAL_INCONCLUSIVE, and the
   researcher decided the next methodological step is a dedicated
   open-set representation baseline, not Model B.)
NEXT_PROPOSED_ACTION=DRAFT_STRONG_NEURAL_OSR_EVIDENCE_GATE_PROTOCOL
NEXT_ACTION_AUTHORIZED=true   (protocol drafting/review only)

CURRENT_FORBIDDEN_NEXT_STEPS=
  ANY_MODEL_B_OR_RL_WORK
  ANY_QWEN_TRAINING
  ANY_CONTINUAL_OR_PURIFICATION_WORK
  ANY_STRONG_NEURAL_OSR_EVALUATION_BEFORE_PREREGISTRATION
  ANY_OPEN_WORLD_GATE_RE_RUN_OR_RESCUE
  ANY_V2_RE_RUN_OR_V2_RESCUE_OR_PROBE_SHOPPING
  ANY_NOVELTY_SCORING_CHANGE_WITHOUT_NEW_AUTHORIZED_PROTOCOL
  ANY_RESCUE_EXPERIMENT_ON_GATE_1_OR_1B
  ANY_RESCUE_EXPERIMENT_ON_OPEN_WORLD_GATE_V1
  FINAL_TEST_UNSEALING
```

## Evidence Processing / Method Dependence Diagnostic V1 (2026-08-18)

```text
EVIDENCE_PROCESSING_METHOD_DEPENDENCE_DIAGNOSTIC_V1=COMPLETE
PREREGISTRATION_COMMIT_SHA=fd3f4b7   (protocol+preregistration+tool, local only)
TOOL_BUGFIX_COMMIT_SHA=30bff93       (3 logged implementation fixes, semantics unchanged)
PROTOCOL_HASH_MATCH=YES              (91b8f7db… = preregistration = tool)
IDENTITY_CHECKS=PASS                 (REAL reproduces V2 audit within 1e-6 3/3;
                                      EDL alpha>=1, loss decreases; SHUFFLED marginals preserved;
                                      NULL blocks zeroed)
SAME_REPRESENTATION_CONTRADICTION=3/3
  (same frozen h: Mahalanobis gap -46.13/-108.86/-30.05 vs EDL-head gap
   +0.076/+0.072/+0.148 -> the V2 contradiction survives with representation
   AND Evidence processing held fixed)
PRIMARY_INTERPRETATION=READOUT_DOMINANT
  (secondary GENERIC_EVIDENCE_DISTRIBUTION_BIAS: SHUFFLED_TO_REAL
   RK 0.893 CI[0.877,0.910], TU 1.015 CI[1.009,1.022])
REVERSE_CROSSCHECK=COMPLETED
  (Mahalanobis on EDL-trained frozen trunk: gap negative 3/3,
   pooled -58.86 CI[-64.76,-53.32] -> sign follows the READOUT)
NULL_PRESENT_REPRODUCES_REAL_MOVEMENT=FALSE (ratios -0.556/-0.138)
CONTENT_SPECIFIC_SEPARATION=PARTIAL (REAL vs SHUFFLED +9.86 CI>0; REAL vs NULL fails)
EDL_GENERALLY_STRONGER_ALONE=FALSE
  (fixed-representation contradiction reproduced -> the preregistered
   consequence rule is NOT triggered; recovery-aware novelty hypothesis
   neither confirmed nor weakened at the representation level)
V2_DECISION_NOT_REOPENED=YES         (METHOD_DEPENDENT_REVIEW unchanged)
RESULT_COMMITTED=false               (report pair untracked)
RESULT_PUSHED=false
NEXT_PROPOSED_ACTION=RESEARCHER_REVIEW_OF_CAUSAL_DECOMPOSITION
NEXT_ACTION_AUTHORIZED=false         (proposal only, not authorization)
Artifacts: processed/dataset_v4_nf3_ton_v1/evidence_processing_method_dependence_diagnostic_v1/
  (aggregate.json, run_manifest.json, per-rotation npz, same-repr + B_EDL epoch logs)
Reports: reports/research_audit/evidence_processing_method_dependence_diagnostic_v1.{json,md}
```

Gate outcome summaries (conclusions unchanged; full metrics in the formal
report pairs under `reports/research_audit/`):

- Open-World Recoverability Gate V1 (2026-08-17) = FAIL: typed utility
  acquisition materially WORSENS recoverable-Known false-Unknown (FURK
  +0.235 vs direct, 9/9 cells) while True Unknown recognition is
  preserved; the novelty scoring under acquired Evidence, not the
  routing, is the bottleneck. Phase C (purification) NOT run
  (FAIL -> STOP). Gate 1 / Gate 1B conclusions unchanged.
- V1 failure attribution (2026-08-17, diagnostic only, V1 result
  unchanged): FURK denominator audit PASS; dominant mechanism F2
  post-Evidence MSP misalignment (3/3, PRIMARY); True Unknown separation
  preserved 3/3; V2_JUSTIFICATION=YES — the novelty interface must
  explicitly model recovery state (conceptual correction, no detector
  recommended). Diagnostic outputs UNCOMMITTED/UNPUSHED.

## Latest formal result

```text
LATEST_FORMAL_REPORT_JSON=reports/research_audit/recovery_signal_characterization_gate_v2.json
LATEST_FORMAL_REPORT_MD=reports/research_audit/recovery_signal_characterization_gate_v2.md
PREVIOUS_REPORT_JSON=reports/research_audit/open_world_gate_v1_failure_attribution.json
PREVIOUS_REPORT_MD=reports/research_audit/open_world_gate_v1_failure_attribution.md
```

One-line interpretations (all unchanged from the frozen reports; full
metrics and narratives live in the JSON/MD pairs named above):

- Gate 1 = YELLOW: Temporal modest consistent positive (3/3 seeds);
  Relation always-on harmful at the frozen RF probe; combined negative.
  The prior 24k pilot's strong recoverability did not reproduce at the
  same strength.
- Gate 1B = PASS: pre-acquisition Basic state predicts HELP vs HARM;
  conditional selector-driven acquisition positive 9/9; random
  acquisition harmful.
- Open-World V1 = FAIL: post-acquisition MSP novelty scoring is the
  bottleneck (F2 primary); True Unknown separation preserved; Phase C
  NOT run (B17 STOP).
- V1 attribution = COMPLETE (diagnostic only): FURK denominator PASS;
  V2 justification = the novelty interface must explicitly model
  recovery state (conceptual; no detector recommended).
- V2 = CASE D (RECOVERY_SIGNAL_INCONCLUSIVE): weak trajectory signal;
  transfer/e2e NOT_ESTABLISHED; headroom diagnostics analysis-only;
  frozen V1 results unchanged; results UNCOMMITTED/UNPUSHED by design.

## Read on demand

For detailed project history:

```text
docs/PROJECT_HANDOFF.md
```

For exact Gate 1 numbers:

```text
reports/research_audit/core_hypothesis_gate_v1.json   (primary)
reports/research_audit/core_hypothesis_gate_v1.md     (explanatory context)
```

For exact Gate 1B numbers (tracked):

```text
reports/research_audit/core_hypothesis_gate_v1b.json  (primary)
reports/research_audit/core_hypothesis_gate_v1b.md    (explanatory context)
```

For exact Open-World Recoverability Gate V1 numbers (tracked):

```text
reports/research_audit/open_world_recoverability_gate_v1.json (primary)
reports/research_audit/open_world_recoverability_gate_v1.md   (explanatory context)
```

For the V1 failure attribution and FURK audit (tracked):

```text
reports/research_audit/open_world_gate_v1_failure_attribution.json (primary)
reports/research_audit/open_world_gate_v1_failure_attribution.md   (explanatory context)
```

For the Recovery-Signal Characterization Gate V2 (result md/json committed
in the 2026-08-18 researcher-review checkpoint, local only, not pushed):

```text
reports/research_audit/recovery_signal_characterization_gate_v2.json (primary)
reports/research_audit/recovery_signal_characterization_gate_v2.md   (explanatory context)
reports/research_audit/recovery_signal_characterization_v2_preregistration.json (preregistration, tracked)
docs/research_plan/recovery_signal_characterization_v2_protocol.md               (frozen protocol)
processed/dataset_v4_nf3_ton_v1/recovery_signal_characterization_gate_v2/        (cells/features/probes)
```

For novelty positioning and claim-safety (tracked):

```text
reports/research_audit/related_work_novelty_reassessment_v1.json (primary)
reports/research_audit/related_work_novelty_reassessment_v1.md   (register)
docs/research_plan/literature_novelty_reassessment_v1.md         (addendum)
```

For task-specific frozen constraints: read only the protocol explicitly
required by the current task. Do not preload unrelated reports or plans.

## State maintenance

After a MATERIAL project-state change:

1. create/update the task formal report;
2. update this file;
3. update PROJECT_HANDOFF only if high-level project interpretation changed;
4. preserve historical formal reports unchanged;
5. do not duplicate full metrics into this file.

Material changes include: formal Gate completion; PASS/YELLOW/FAIL; model
training start/completion; dataset/split status change; authorized frozen
protocol change; canonical artifact/hash change; component deprecation;
CURRENT_AUTHORIZED_TASK change; NEXT_PROPOSED_ACTION change; blocker status
change.

## Git/repository state

```text
GIT_CHECKPOINT=2026-08-18 hygiene + V2 result checkpoint commit (local
  only; pushed: no, blocked: no GitHub creds; run `git rev-parse HEAD` —
  never trust this)
WORKING_TREE_STATE=clean after the 2026-08-18 checkpoint commit (V2 gate
  results, instruction hygiene, DEC-0028, and the documented V2 runtime
  bugfix all committed; push remains blocked: no GitHub creds)
GATE_1_CHECKPOINT_STATUS=COMMITTED (0cb49e3; push blocked: no GitHub creds)
GATE_1B_COMMIT_CREATED=true (917303a, local only)
GATE_1B_PUSHED=false
NOVELTY_AUDIT_COMMIT_CREATED=true (917303a, local only)
NOVELTY_AUDIT_PUSHED=false
OPEN_WORLD_GATE_COMMIT_CREATED=true (4fc7591, local only)
OPEN_WORLD_GATE_PUSHED=false
FAILURE_ATTRIBUTION_COMMIT_CREATED=true (7604736, local only)
FAILURE_ATTRIBUTION_PUSHED=false
V2_PREREGISTRATION_COMMIT_CREATED=true (22c92c7, local only)
V2_PREREGISTRATION_PUSHED=false
V2_RESULT_COMMITTED=true (2026-08-18 checkpoint, local only)
V2_RESULT_PUSHED=false
```
