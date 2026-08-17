# Agent Context

STATE_SCHEMA=AGENT_CONTEXT_V1
LAST_UPDATED=2026-08-17
UPDATED_BY_TASK=OPEN_WORLD_V1_FAILURE_ATTRIBUTION_AND_FURK_AUDIT

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
CURRENT_AUTHORIZED_TASK=NONE_WAITING_RESEARCHER
  (Failure-attribution diagnostic for Open-World Gate V1 completed
   2026-08-17; waiting for researcher review of the failed gate,
   the attribution, and the mainline reassessment)
NEXT_PROPOSED_ACTION=REASSESS_RECOVERABILITY_CONDITIONED_OPEN_WORLD_MAINLINE
  (gate FAIL: novelty scoring under acquired Evidence must be addressed
   before any re-test of acquisition value for open-world routing;
   attribution: novelty interface must explicitly model recovery state
   rather than post-classification MSP alone — V2 protocol requires
   researcher authorization)
NEXT_ACTION_AUTHORIZED=false

CURRENT_FORBIDDEN_NEXT_STEPS=
  ANY_MODEL_B_OR_RL_WORK
  ANY_OPEN_WORLD_GATE_RE_RUN_OR_RESCUE
  ANY_NOVELTY_SCORING_CHANGE_WITHOUT_NEW_AUTHORIZED_PROTOCOL
  CONTINUAL
  ANY_RESCUE_EXPERIMENT_ON_GATE_1_OR_1B
  ANY_RESCUE_EXPERIMENT_ON_OPEN_WORLD_GATE_V1
```

Open-World Recoverability Gate V1 (2026-08-17) = FAIL: typed utility
acquisition materially WORSENS recoverable-Known false-Unknown (FURK +0.235
vs direct, 9/9 cells, CI [0.082, 0.290]) while True Unknown recognition is
preserved and Known classification improves (Macro-F1 +0.015, recovery rate
0.525). Mechanism: post-acquisition MSP novelty scores stay high on
recoverable rows even with oracle routing — the novelty scoring, not the
routing, is the bottleneck. Phase C (purification) NOT run (FAIL -> STOP).
Gate 1 / Gate 1B conclusions unchanged. Reassessment of the
recoverability-conditioned open-world mainline is the next proposed action —
still NOT authorized.

V1 failure attribution (2026-08-17, diagnostic only, V1 result unchanged):
FURK denominator audit PASS — denominator identical across all 6 policies
within each rotation, per-row identity verified (stored recoverable column
== frozen-model-recomputed flag; digest/block row alignment); raw
numerators match the frozen report exactly. Dominant mechanisms
(>=2/3 rotations, raw counts, no tuning): F1 classification-utility target
mismatch (2/3), F2 post-Evidence MSP misalignment (3/3, PRIMARY),
F3 policy-conditioned calibration subgroup shift (3/3; CALIB Known POST
P95 drops -0.029/-0.085/-0.041 while CALIB Recoverable P95 rises),
F4 router selection failure (2/3). R3 recovered-but-rejected = 2179 pooled
(23.0% of recoverable); recovery-conditional rejection 0.54 pooled.
True Unknown separation preserved 3/3. V2_JUSTIFICATION=YES:
PROSPECTIVE_V2_DESIGN_REQUIREMENT="novelty interface must explicitly model
recovery state rather than post-classification MSP alone" (conceptual
correction, definable without True Unknown GT, NO detector recommended).
RL_SEQUENTIAL_DECISION_JUSTIFICATION=PLAUSIBLE (analysis only, no RL run).
All diagnostic outputs remain UNCOMMITTED/UNPUSHED for researcher review.

## Latest formal result

```text
LATEST_FORMAL_REPORT_JSON=reports/research_audit/open_world_gate_v1_failure_attribution.json
LATEST_FORMAL_REPORT_MD=reports/research_audit/open_world_gate_v1_failure_attribution.md
PREVIOUS_REPORT_JSON=reports/research_audit/open_world_recoverability_gate_v1.json
PREVIOUS_REPORT_MD=reports/research_audit/open_world_recoverability_gate_v1.md
```

Open-World Gate V1 failure attribution (2026-08-17, COMPLETE): FURK
denominator audit PASS; numerators exactly match the frozen report
(Credential 1220/2295 of 4598, Recon 895/1034 of 1398, Web 702/2043 of
3487; rates 0.2653→0.4991 / 0.6402→0.7396 / 0.2013→0.5859). Dominant
mechanisms F1 2/3, F2 3/3 (primary), F3 3/3, F4 2/3; F0=F5=F6=0.
RBR/RCJ pooled 0.2298/0.5419 (A2=2179); R3=2179, R4=1992 (R3∩R4=278);
HELP-novelty improve 0.446/0.531/0.406, worsen 0.516/0.428/0.547;
Spearman 0.08–0.29. Thresholds P6−P0: −0.029/−0.085/−0.041; CALIB Known
POST P95 shift −0.029/−0.085/−0.041 with CALIB Recoverable +0.011/+0.052/
−0.004. True Unknown AUROC delta +0.014/+0.002/+0.014, separation
PRESERVED 3/3. V2_JUSTIFICATION=YES (all 5 conditions; requirement:
"novelty interface must explicitly model recovery state rather than
post-classification MSP alone"; primary F2). RL=PLAUSIBLE (analysis only).
No threshold created; Basic threshold never presented as an alternative;
no detector recommended; no frozen report rewritten; safety counters all
false/0; diagnostic outputs UNCOMMITTED/UNPUSHED.

Open-World Recoverability Gate V1 (2026-08-17, FAIL): typed utility Evidence
acquisition makes recoverable-Known false-Unknown rejection materially worse
(FURK +0.235 mean vs direct; 9/9 cells worse; pooled paired group/temporal
bootstrap CI [0.082, 0.290]) while True Unknown recognition is preserved
(AUROC +0.0098, recall +0.013) and Known classification improves (Macro-F1
+0.015, Evidence Recovery Rate 0.525). Mechanism: post-acquisition MSP
novelty scores stay high on recoverable rows even under oracle-perfect
routing (P7: 0.140 -> 0.143 residual Known FUR) — the novelty scoring under
acquired Evidence, not the routing, is the bottleneck. Phase C
(Unknown-Candidate Purification) NOT run (B17 FAIL -> STOP). B14:
utility does NOT beat generic difficulty routing on FURK -> no
utility-specific routing value claim. All artifacts Git-external under
`processed/dataset_v4_nf3_ton_v1/open_world_recoverability_gate_v1/`;
reports untracked (not committed by design).

Gate 1 interpretation (only what is needed here):

- Temporal is modest but consistently positive (3/3 seeds; mean ΔMacro-F1
  ≈ +0.0065, mean recoverable ≈ 0.0276, mean net recovery ≈ +0.0066;
  meaningful attack-class recovery: DoS, Web_Injection).
- Relation is harmful when always-on under the frozen RF probe (mean
  recoverable ≈ 0.0455, but harm > recovery); non-zero recovery means
  conditional value remains unresolved — now resolved by Gate 1B:
  conditional (selector-driven) acquisition is strongly positive.
- Temporal + Relation combined is negative at the frozen RF probe.
- Gate 1 remains YELLOW because the preregistered strong-existence criteria
  were not all met. The prior 24k pilot's strong recoverability did not
  reproduce at the same strength.
- Model B / RL / continual are not yet authorized.

Gate 1B (2026-08-17, PASS): pre-acquisition Basic state alone predicts
HELP vs HARM well (Temporal: mean HELP AUROC 0.92, top15 capture 0.90,
selector15 net +0.021 vs random +0.001, gain +0.020, T7 aggregate CI lower
> 0; Relation: conditional value supported, UNIQUE_R rate ≈ 0.019;
random Relation acquisition is harmful — random net negative 9/9 cells —
while selector net is positive 9/9). All Gate 1B artifacts are Git-external
under `processed/dataset_v4_nf3_ton_v1/core_gate_v1b/`; report files are
untracked (not committed by design).

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

For exact Gate 1B numbers (untracked, do not commit):

```text
reports/research_audit/core_hypothesis_gate_v1b.json  (primary)
reports/research_audit/core_hypothesis_gate_v1b.md    (explanatory context)
```

For exact Open-World Recoverability Gate V1 numbers (untracked, do not
commit):

```text
reports/research_audit/open_world_recoverability_gate_v1.json (primary)
reports/research_audit/open_world_recoverability_gate_v1.md   (explanatory context)
```

For the V1 failure attribution and FURK audit (untracked, do not commit):

```text
reports/research_audit/open_world_gate_v1_failure_attribution.json (primary)
reports/research_audit/open_world_gate_v1_failure_attribution.md   (explanatory context)
```

For novelty positioning and claim-safety (untracked, do not commit):

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
GIT_CHECKPOINT=4fc7591 (Open-World Recoverability Gate V1 FAIL checkpoint;
  pushed: no, blocked: no GitHub creds)
WORKING_TREE_STATE=V1 failure attribution complete (diagnostic only);
  diagnostic outputs intentionally uncommitted for researcher review
GATE_1_CHECKPOINT_STATUS=COMMITTED (push blocked: no GitHub creds)
GATE_1B_COMMIT_CREATED=false
GATE_1B_PUSHED=false
NOVELTY_AUDIT_COMMIT_CREATED=false
NOVELTY_AUDIT_PUSHED=false
OPEN_WORLD_GATE_COMMIT_CREATED=true (4fc7591, local only)
OPEN_WORLD_GATE_PUSHED=false
FAILURE_ATTRIBUTION_COMMIT_CREATED=false
FAILURE_ATTRIBUTION_PUSHED=false
```

(untracked: failure-attribution tool + test + attribution report md/json +
open-world gate tool + test + gate v1 report md/json + gate 1B tool + test
+ gate v1b report md/json + novelty audit report md/json + literature
addendum; modified: this file, PROJECT_HANDOFF)
