# Agent Context

STATE_SCHEMA=AGENT_CONTEXT_V1
LAST_UPDATED=2026-08-17
UPDATED_BY_TASK=RELATED_WORK_NOVELTY_REASSESSMENT_AND_PLAN_SYNC_V1

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
ADAPTIVE_EVIDENCE_ACQUISITION_STATUS=SUPPORTED_FOR_NEXT_OPEN_WORLD_GATE
MODEL_B_STATUS=NOT_STARTED
RL_STATUS=NOT_STARTED
OPEN_WORLD_CAUSAL_GATE_STATUS=NOT_STARTED
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
CURRENT_AUTHORIZED_TASK=LITERATURE_NOVELTY_AND_PLAN_SYNCHRONIZATION_ONLY
  (completed; awaiting researcher review)
NEXT_PROPOSED_ACTION=OPEN_WORLD_CAUSAL_GATE_BEFORE_MODEL_B
NEXT_ACTION_AUTHORIZED=false

CURRENT_FORBIDDEN_NEXT_STEPS=
  ANY_MODEL_B_OR_RL_WORK
  OPEN_WORLD_CAUSAL_GATE
  CONTINUAL
  ANY_RESCUE_EXPERIMENT_ON_GATE_1_OR_1B
```

Gate 1B completed 2026-08-17: conditional Evidence utility is separable from
pre-acquisition Basic state (Temporal primary PASS 7/7; Relation conditional
value supported with strong UNIQUE_R diversity). Per the frozen protocol,
the next proposed action is the Open-World causal gate BEFORE any Model B
work — still NOT authorized.

## Latest formal result

```text
LATEST_FORMAL_REPORT_JSON=reports/research_audit/core_hypothesis_gate_v1b.json
LATEST_FORMAL_REPORT_MD=reports/research_audit/core_hypothesis_gate_v1b.md
PREVIOUS_REPORT_JSON=reports/research_audit/core_hypothesis_gate_v1.json
PREVIOUS_REPORT_MD=reports/research_audit/core_hypothesis_gate_v1.md
```

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
GIT_CHECKPOINT=0cb49e31 (Phase A checkpoint: Gate 1 yellow + agent context)
WORKING_TREE_STATE=Gate 1B complete + novelty audit; results intentionally uncommitted
GATE_1_CHECKPOINT_STATUS=COMMITTED_0cb49e31 (push blocked: no GitHub creds)
GATE_1B_COMMIT_CREATED=false
GATE_1B_PUSHED=false
NOVELTY_AUDIT_COMMIT_CREATED=false
NOVELTY_AUDIT_PUSHED=false
```

(untracked: Gate 1B tool + test + gate v1b report md/json + novelty audit
report md/json + literature addendum; modified: this file, PROJECT_HANDOFF)
