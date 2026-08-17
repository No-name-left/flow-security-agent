# Literature and Novelty Reassessment — V1 (Addendum)

> Status: `DRAFT_ADDENDUM` — **non-frozen, supersedes nothing**
>
> Date: 2026-08-17
>
> REVISION=1 (2026-08-17): full-text sync (RoNeTC / RoeCi / GCLC reviewed
> externally by researcher workflow); primary novelty scope narrowed to
> runtime observation acquisition; utility-vs-difficulty routing baselines
> required; self-evolution framing added.
>
> Relation to frozen contracts: this addendum does **not** modify
> [experiment_protocol_v1.md](experiment_protocol_v1.md) (DEC-0027 frozen,
> `FROZEN DESIGN / NOT RUN`) or
> [model_b_evidence_openworld_design.md](model_b_evidence_openworld_design.md)
> (DEC-0025 design source). Those remain the frozen historical contracts and
> are still fully reproducible as written. This document records, for the
> next gate-design task only, the literature constraints and prospective
> design requirements identified by the Related Work Novelty Reassessment
> audit. It is a literature reassessment, not a material protocol deviation;
> no new DEC row has been added to the Decision Log. If the researcher
> accepts these revisions, they become binding only through a new
> researcher-authorized frozen protocol (e.g., the Open-World Gate protocol).
>
> Full register, access-statuses, and claim-safety table:
> [reports/research_audit/related_work_novelty_reassessment_v1.md](../../reports/research_audit/related_work_novelty_reassessment_v1.md)
> (JSON: [related_work_novelty_reassessment_v1.json](../../reports/research_audit/related_work_novelty_reassessment_v1.json))
>
> Provenance: RoNeTC / RoeCi / GCLC full-text review was completed outside
> this repository by the researcher workflow
> (`FULL_TEXT_REVIEW_COMPLETED_EXTERNALLY_BY_RESEARCHER_WORKFLOW`); the
> local Agent does not claim independent PDF access.

## 1. Positioning (binding for any future draft)

```text
PRIMARY_NOVELTY_CANDIDATE=RECOVERABILITY_CONDITIONED_OPEN_WORLD_TRAFFIC_RECOGNITION
  PRIMARY_NOVELTY_SCOPE=RUNTIME_OBSERVATION_ACQUISITION_BEFORE_NOVELTY
    (the primary novelty is specifically observation acquisition,
     NOT adaptive computation)
  core=INSUFFICIENT_OBSERVATION_OF_KNOWN != TRUE_NOVELTY
  decomposition=Known = Basic-sufficient + Evidence-recoverable + Residual-hard
  mechanism=partial/basic observation -> adaptive acquisition of previously
    unobserved, runtime-legal observation evidence -> reclassification
    before novelty handling
  status=PLAUSIBLY_NOVEL_PENDING_FULL_TRAFFIC_OSR_REVIEW

SUPPORTING_METHOD=RECOVERABILITY_AND_HARM_AWARE_TYPED_EVIDENCE_ROUTING
  status=SUPPORTED_BY_GATE_1B (diagnostic form frozen); Model B form PROPOSED_NOT_FROZEN
  not_claimed=instance-wise acquisition, typed acquisition,
    expected utility routing, AFA (all PRIOR_ART_EXISTS)

CONTINUAL_NOVELTY_CANDIDATE=EVIDENCE_GATED_UNKNOWN_CANDIDATE_PURIFICATION_FOR_SELF_EVOLUTION
  precise_scope=remove Evidence-recoverable Known from the unknown-candidate
    stream BEFORE clustering, human verification, and new-class adaptation
  status=PLAUSIBLE_NOVELTY_PENDING_OPEN_WORLD_AND_CONTINUAL_VALIDATION

SELF_EVOLUTION_STATUS=PLANNED_CORE_SYSTEM_LOOP_PENDING_PURIFICATION_AND_CONTINUAL_VALIDATION
  SELF_EVOLUTION_NOVELTY_IS_NOT_CONTINUAL_LEARNING_ITSELF=true
```

Generic AFA, typed/temporal acquisition, cost-aware two-stage routing,
instance-specific acquisition, acquire-before-abstain, uncertainty-based
rejection, adaptive computation before rejection, dynamic multi-view fusion
(RoNeTC), open-world traffic classification (RoNeTC / RoeCi / GCLC),
new-class discovery/clustering/human-confirmation/incremental-update (GCLC),
open-world continual traffic learning, and buffer purification are all
`PRIOR_ART_EXISTS` — none of them may appear as a novelty claim.

## 2. Novelty-threshold calibration requirement (must be designed into the next gate)

`POLICY_CONDITIONED_NOVELTY_CALIBRATION=REQUIRED_FOR_NEXT_GATE`

- Freeze the acquisition policy before calibrating any novelty threshold.
- Calibration and test observations must traverse the **same frozen**
  acquisition pipeline (acquisition decision → post-acquisition
  representation → score).
- Never reuse a Basic-only threshold after acquisition.
- If the policy/budget is selected using calibration data, require a
  separate held-out calibration protocol or a pre-specified correction.
- This principle is prior art (Xu et al. arXiv:2606.16667) — it is a
  required design element, not a claim.

## 3. Next-gate (Open-World) design requirements (prospective, not run)

```text
INDEPENDENT_NOVELTY_DETECTOR=true
  (Unknown truth may not train the utility selector; whole-class held-out
  rotations are evaluation-only)

NON_CHEATING_PRE_ACQUISITION_ROUTER=true
  (no actual T/R Evidence, no GT, no future correctness, no True Unknown
  status, no actual future utility)

READ_ONLY_EVIDENCE_ACQUISITION_ASSUMPTION=true
  (same-split, strictly past-only, runtime-legally available, must not
  causally modify target traffic)

EVIDENCE_SUBSET_ANALYSIS=NONE / T / R / TR
  (unique / shared / TR-only recovery, redundancy, synergy;
  do not assume greedy T->R is optimal)

MANDATORY_METRICS=TRUE_UNKNOWN_ACQUISITION_RATE,
  TRUE_UNKNOWN_POST_ACQUISITION_SCORE_SHIFT, UNKNOWN_AUROC, UNKNOWN_AUPR,
  UNKNOWN_RECALL_AT_FIXED_KNOWN_FPR, KNOWN_MACRO_F1, FURK,
  EVIDENCE_RECOVERY_RATE, ACQUISITION_RATE_COST
  (guard: Known recovery must not pull True Unknown toward Known)

REQUIRED_BASELINES=BASIC_DIRECT_NOVELTY, ALWAYS_FULL_EVIDENCE,
  RANDOM_COST_MATCHED_ACQUISITION, LOW_CONFIDENCE_COST_MATCHED,
  HIGH_ENTROPY_COST_MATCHED, SUPERVISED_UTILITY_ACQUISITION,
  ORACLE_ANALYSIS_ONLY
  (oracle uses actual future outcomes: analysis-only, never described as
  deployable; RoNeTC-style multi-view fusion as Related Work comparator)

UTILITY_VS_DIFFICULTY_ROUTING=REQUIRED
  utility routing MUST be compared against generic difficulty routing:
  LOW_CONFIDENCE / HIGH_ENTROPY / UTILITY_SELECTOR
  (RoeCi establishes uncertainty/sample-complexity adaptive escalation
  as prior art; if Utility does not beat generic uncertainty routing,
  do not claim utility-specific routing value)

FURK_DECOMPOSITION=RECOVERABLE_KNOWN_FALSE_UNKNOWN + RESIDUAL_KNOWN_FALSE_UNKNOWN
```

## 4. Continual design requirement (prospective, not run)

Three matched systems with the same continual learner and matched
replay/adaptation/training budget/label budget/update schedule:

```text
A. DIRECT_UNKNOWN_BUFFER
B. EVIDENCE_GATED_UNKNOWN_BUFFER
C. ORACLE_CLEAN_UNKNOWN_BUFFER
```

Metrics: BUFFER_PURITY, RECOVERABLE_KNOWN_CONTAMINATION,
TRUE_UNKNOWN_RETENTION, LABEL_QUERY_EFFICIENCY, NEW_CLASS_F1, OLD_CLASS_F1,
ALL_CLASS_F1, FORGETTING_BWT, ADAPTATION_COUNT.

Self-evolution is retained as a system-level mainline; self-evolution
novelty is NOT continual learning itself. Before full continual training,
first test whether the Evidence Gate actually purifies the Unknown
candidate stream (Unknown-Candidate Purification Gate — buffer-purity
analysis only, no continual model training). This future matched
experiment will finally validate the teacher-required self-evolution loop.

## 5. Access-limited papers

```text
RONETC_FULL_TEXT_REVIEW=COMPLETE_EXTERNAL_RESEARCHER_WORKFLOW
ROECI_FULL_TEXT_REVIEW=COMPLETE_EXTERNAL_RESEARCHER_WORKFLOW
GCLC_FULL_TEXT_REVIEW=COMPLETE_EXTERNAL_RESEARCHER_WORKFLOW
ACO_ICML_2024_FULL_METHOD_REVIEW=PENDING   (MEDIUM_HIGH)
ACCESS_LIMITED_CRITICAL_PAPERS=1
```

ACO does NOT block the next empirical gate (its main threat is generic
non-greedy AFA novelty, already excluded from our claim). It MUST still be
reviewed before final first/novelty claims. Do not invent method details
for any access-limited paper.

## 6. Open items carried into the next gate design

```text
RL_IS_NOT_CORE_NOVELTY=true; RL remains optional and non-core, retained
  only if it improves the quality-cost/open-world frontier over the
  supervised utility selector + simple heuristics.
MODEL_B_CONTINUOUS_UTILITY=PROPOSED_NOT_FROZEN
  (expected post-acquisition task-loss improvement - lambda * cost;
  no Unknown-dependent target until a leakage-safe formulation exists;
  Gate 1B HELP/NEUTRAL/HARM +1/0/-1 remains frozen as-is;
  Teacher remains NOT_UTILITY_GT)
EVIDENCE_SPECIALIZATION_AUDIT=SECONDARY_ANALYSIS_ONLY
  (true-known-class x Evidence family x HELP/HARM/UNIQUE_HELP/NET_UTILITY)
EVIDENCE_AVAILABILITY_MISSINGNESS_STRESS_TEST=PLANNED (per JMLR 26(60))
```
