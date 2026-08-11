# Near Final Pre-training Acceptance v2

Status: **PASS**
Audit date: 2026-08-12
Formal SFT run: **false**
RLAIF/GRPO run: **false**

## Decision

`CLASSIFICATION_SUFFICIENCY_DECOUPLED_V1` resolves the former blocker without weakening evidence semantics. `classification_ce_eligible` is a deterministic TRAIN/K-known/provenance decision; `evidence_sufficient` is an operational stopping/acquisition target. Every legal session contributes exactly one real primary classification state even when its visible Evidence is insufficient. Controlled lower-evidence auxiliaries keep Evidence LM supervision but mask classification CE. Immutable GT remains backend-only and is absent from model-visible input.

All final acceptance Gates pass. The frozen config and launcher are ready for a separately authorized explicit `--execute`, but this task did not run SFT, RL, Unknown, U_final, Agent evaluation or any formal benchmark.

## Frozen corpus and Teacher evidence

- Teacher Prompt: `TEACHER_PROMPT_V3`, digest `4840e5e61a40169986dae63402bb4375f88fa5cc9f9e5e5214a17a3c79ae9896`.
- Pilot: 250/250 valid, zero quarantine, 17 sufficient / 233 insufficient; 144 repaired records after reusing current digest-matched bulk cache.
- Bulk: 22,957/22,957 valid, zero quarantine, 11,107 first-pass and 11,850 repaired; 1,381 sufficient / 21,576 insufficient.
- Valid-record token accounting: 28,418,623 input + 4,081,790 output = 32,500,413; mean recorded latency 2.039 s; cache-miss cost upper bound from retained valid-token usage is USD 5.121508.
- Final acceptance rerun reused 22,957/22,957 valid cache records and made zero new API calls. Historical raw HTTP-attempt total, including discarded failed/reannotation attempts, was not persisted and is not reconstructed from the accepted cache.
- Sufficiency calibration is non-degenerate: 1,337/11,979 rich primary states are sufficient, all 5,978 controlled auxiliaries remain insufficient, and Application/Payload/Temporal/RAG stages show evidence-dependent transitions rather than a class quota.

## Supervision and corpus

- Final corpus: `NEAR_SFT_CORPUS_V2`, 22,957 records, 16,979 unique sessions; SHA256 `5b845cf9e5886e5e44fd46562135ba3eb5907de65fd8faf5d9b8777253149123`.
- Classification supervised: 16,979 records / 16,979 sessions / all 11 K-known classes; at most one per session.
- Classification masked: 5,978 controlled lower-evidence auxiliaries.
- Primary stage distribution: application 1,060; initial 5,000; knowledge 1,165; packet 1,615; payload 1,587; relation 3,280; temporal 3,272.
- Evidence records: Application 1,120; Sanitized Payload 1,697; Knowledge RAG 1,165.
- Gap distribution: ambiguous 1,045; application 6,447; none 1,381; packet 7,151; payload 3,318; relation 71; temporal 3,544.
- Duplicate rate, exact serialized-input duplicate groups, label collisions, invalid session weights, model-input backend identities, prohibited model-input keys, target class verdicts and U_final count are all zero.

## Evidence and serialization audits

Payload paired audit: 594/594 pairs have explainable marginal value; 168 change insufficient→sufficient and 484 cite newly visible Payload Observation. RAG paired audit: 380/380 pairs have explainable marginal value; 20 change insufficient→sufficient; Knowledge is never cited as current-session Observation. Safe queries contain no GT/dataset/K-U/U_final shortcut.

The final 100-record stratified manual review covers all 11 classes, primary/auxiliary, sufficient/insufficient, all eight stages, Application, Payload and RAG. Deterministic and manual acceptance are PASS. A non-blocking limitation remains: a small subset of `sufficient=true` cases are optimistic but defensible target-relative judgments; no class quota, majority forcing or GT-derived missing evidence was introduced.

Combined sequence tokens: P50 1,034; P90 1,439; P95 1,614; P99 1,842; max 2,902; overflow above 3,072 is zero.

## Exact acceptance fields

```text
FINAL_PRETRAINING_ACCEPTANCE_STATUS=PASS
SUPERVISION_CONTRACT_VERSION=CLASSIFICATION_SUFFICIENCY_DECOUPLED_V1
CLASSIFICATION_SUFFICIENCY_DECOUPLING=PASS
PRIMARY_STATE_COUNT=16979
PRIMARY_UNIQUE_SESSIONS=16979
PRIMARY_CLASS_DISTRIBUTION=Backdoor:659,DDoS_HTTP:2048,DDoS_TCP:2048,MITM:105,Normal:2048,Password:2048,Port_Scanning:1530,Ransomware:491,SQL_injection:2048,Uploading:2048,Vulnerability_scanner:1906
AUXILIARY_STATE_COUNT=5978
DEEPSEEK_PROVIDER_READY=true
TEACHER_PROMPT_VERSION=TEACHER_PROMPT_V3
TEACHER_PILOT_PASS=true
TEACHER_SCHEMA_VALID_RATE=1.0
TEACHER_GROUNDING_PASS=PASS
TEACHER_SUFFICIENCY_DISTRIBUTION=sufficient:1381,insufficient:21576
TEACHER_BULK_COMPLETE=true
TEACHER_BULK_VALID_COUNT=22957
TEACHER_BULK_QUARANTINE=0
TEACHER_CACHE_REUSED=22957/22957_final_zero_network_validation
TEACHER_NEW_API_CALLS=0_final_zero_network_validation;historical_raw_attempt_total_not_persisted
FINAL_SFT_CORPUS_READY=true
FINAL_SFT_RECORD_COUNT=22957
FINAL_UNIQUE_SESSIONS=16979
CLASSIFICATION_SUPERVISED_RECORDS=16979
CLASSIFICATION_MASKED_RECORDS=5978
CLASSIFICATION_SUPERVISED_CLASS_COVERAGE=11/11
EVIDENCE_SUFFICIENT_RECORDS=1381
EVIDENCE_INSUFFICIENT_RECORDS=21576
GAP_TYPE_DISTRIBUTION=ambiguous:1045,application:6447,none:1381,packet:7151,payload:3318,relation:71,temporal:3544
APPLICATION_RECORDS=1120
PAYLOAD_RECORDS=1697
RAG_RECORDS=1165
PAYLOAD_GAP_PAIR_AUDIT=PASS
RAG_GAP_PAIR_AUDIT=PASS
FINAL_SEQUENCE_TOKEN_P50=1034
FINAL_SEQUENCE_TOKEN_P90=1439
FINAL_SEQUENCE_TOKEN_P95=1614
FINAL_SEQUENCE_TOKEN_P99=1842
FINAL_SEQUENCE_TOKEN_MAX=2902
SEQUENCE_OVERFLOW_COUNT=0
PROMPT_FINAL_AUDIT=PASS
SERIALIZATION_FINAL_AUDIT=PASS
PAYLOAD_FINAL_AUDIT=PASS_WITH_LIMITATIONS
RAG_FINAL_AUDIT=PASS
DEEPSEEK_ROLE_ISOLATION_AUDIT=PASS
TRAINING_HARNESS_FINAL_AUDIT=PASS
FORMAL_SFT_CONFIG_READY=true
FORMAL_SFT_LAUNCHER_READY=true
CHECKPOINT_RESUME_READY=true
RL_COMPATIBILITY_PRECHECK=PASS
U_FINAL_ISOLATION_GATE=PASS
FULL_PYTEST=283_passed_3_skipped_optional_torch_in_flow_data
CI_PORTABILITY_TEST=280_passed_6_expected_skips_without_external_assets
QWEN_TARGETED_TESTS=20_passed
SFT_RUN=false
RL_RUN=false
READY_TO_START_FORMAL_NEAR_SFT=true
NEXT_ACTION=START_FORMAL_NEAR_MULTI_TASK_SFT
```

## Remaining limitations

- Edge attack classes retain documented single-capture/run generalization limits; this corpus is not a paper result.
- Application/Payload are naturally unavailable for some sessions; absence stays explicit. No explicit file-upload marker appeared in the sampled Payload signal audit.
- Teacher repair rate is 51.6%, so the final corpus depends materially on deterministic repair/validation; all accepted targets nevertheless pass the current digest-bound validator and quarantine is zero.
- Cost accounting covers retained valid-record usage; discarded historical failed/reannotation attempts were not fully persisted.
- Application/Payload/RAG are ready as pretraining assets, not yet formal online Runtime tools.

No formal training, RL, Unknown, U_final or Agent benchmark ran during this acceptance.
