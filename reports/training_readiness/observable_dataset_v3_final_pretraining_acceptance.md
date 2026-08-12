# Observable Dataset v3 Final Pre-Training Acceptance

Date: 2026-08-13

Scope: Task Definition v2 + Observable Dataset v3 + Evidence-v2 + Teacher-v2

Decision: `READY_FOR_FORMAL_SFT=true`

Execution: `FORMAL_SFT_STARTED=false`

## Final decision

The formal Near benchmark is frozen at six classes: Normal, DDoS_HTTP, DDoS_TCP, Password, SQL_injection and Vulnerability_scanner. MITM is excluded because the available ARP anomalies cannot be linked to the target session endpoints. Port_Scanning is excluded because the official capture presents changing source ports toward one destination port 80 rather than observable destination-port scanning. No class was retained to satisfy a numeric class-count target.

Backdoor remains a Long-Horizon Temporal Case Study. Uploading and Ransomware remain Observability-Limited/Abstain sources and never enter main classification CE or U_final. A separate bounded stress index contains 3,676 current-v3 exclusions with `classification_ce_eligible=false`; Uploading/Ransomware are declared but not falsely represented as part of the 17-capture Evidence-v2 scan.

## Dataset v3 freeze

The final protocol is `CONSTRAINED_CHRONOLOGICAL_BOUNDARY_V2_PER_SPLIT_ELIGIBILITY_FILTERED`: preserve the existing assignment and apply one eligibility contract independently to train, validation and test. No tshark Production rebuild, re-sessionization, canonical rewrite or random split was performed.

| Class | Original | Eligible | Removed generic | Removed unobservable | Removed wrong granularity | Train | Validation | Test | Basic sufficient | Needs packet/payload | Needs application | Needs temporal | Needs relation | Retain |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| Normal | 680,504 | 680,504 | 0 | 0 | 0 | 475,650 | 100,720 | 101,367 | 100% | 0% | 0% | 0% | 0% | yes |
| DDoS_HTTP | 12,145 | 10,383 | 1,762 | 0 | 0 | 3,633 | 156 | 842 | 0.0193% | 0% | 99.9807% | 99.9807% | 0% | yes |
| DDoS_TCP | 1,176,049 | 1,175,806 | 243 | 0 | 0 | 817,957 | 165,432 | 172,231 | 0% | 0% | 0% | 100% | 0% | yes |
| MITM | 227 | 0 | 0 | 0 | 227 | 0 | 0 | 0 | 0% | 0% | 0% | 0% | 0% | no |
| Password | 96,081 | 23,650 | 72,431 | 0 | 0 | 16,532 | 3,548 | 3,552 | 100% | 0% | 0% | 0% | 0% | yes |
| Port_Scanning | 10,908 | 0 | 10,908 | 0 | 0 | 0 | 0 | 0 | 0% | 0% | 0% | 0% | 0% | no |
| SQL_injection | 4,433 | 4,264 | 169 | 0 | 0 | 2,924 | 568 | 641 | 100% | 0% | 0% | 0% | 0% | yes |
| Vulnerability_scanner | 2,912 | 2,870 | 42 | 0 | 0 | 1,992 | 427 | 424 | 30.5923% | 9.2683% | 9.2683% | 60.1394% | 60.1394% | yes |

Formal totals are train 1,318,688, validation 270,851 and test 279,057. `GENERIC_MAIN_{TRAIN,VAL,TEST}=0`, `UNOBSERVABLE_MAIN_{TRAIN,VAL,TEST}=0`, and pairwise sample-identity overlap is zero. Exact and near model-view cross-split collisions are 761 and 348 groups; these are disclosed signature sensitivity, not backend identity leakage.

The default Known validation artifact is a deterministic six-class `EXACT_EVAL_CLEAN` view with 3,231 records: DDoS_HTTP 156, DDoS_TCP 127, Normal 1,000, Password 1,000, SQL_injection 568 and Vulnerability_scanner 380. Near-clean support is not a valid six-class default because DDoS_TCP has zero available near-clean validation records; it remains a sensitivity limitation.

## Evidence-v2

All 17 candidate captures were processed into versioned Git-external Evidence-only assets. Basic-v2 contains safe session summary, first-eight packet metadata, explicitly packet-indexed first-eight sanitized payload and cheap structured Application fields. Packet expansion is bounded to packets 9–16. Temporal-v2 exposes 10/60/180/300-second strictly-past behavior statistics. Relation-v2 requires same scope, strictly-past time and target endpoint/MAC linkage for ARP/DNS/relation facts; capture-wide ARP propagation is prohibited. Application-v2 uses structured protocol, request, response, auth and probe fields.

Packet alignment, strict-past behavior, model-safe projection and U_final guards pass. The Vulnerability_scanner PCAP has one verified corrupt trailing record after official frame 265,827; all Production locators end at 265,827, and the hash-bound parser exception accepts only that exact tail condition. No Production asset was changed.

## Teacher-v2 and formal SFT corpus

The 40-state Teacher smoke passed. Resumable bulk produced 20,807/20,807 valid cached annotations with zero quarantine. Raw caches are retained byte-for-byte. The formal trajectory policy requires terminal sufficiency and stops after the first sufficient state: 161 terminal-inconsistent candidate sessions are quarantined from SFT supervision and 6,116 post-sufficient counterfactual states are omitted. No Teacher target is semantically rewritten.

The formal corpus contains 14,350 states from 11,958 sessions: 11,958 Basic-v2 primary records and 2,392 controlled richer auxiliary records. Every session has exactly one classification-CE primary and at most three total states. Session weights sum to one and are consumed by the harness Evidence-LM weighted-sum; auxiliary states do not multiply session contribution. Formal transitions contain 1,839 false→true, 121 false→false with reduced gap cardinality, 432 other false→false progress states, and zero true→false. Every retained terminal state is sufficient.

Single-gap rate is 12.8014% of all formal states; multi-gap rate is 3.8676%. The remaining states are sufficient. A 120-record class/stage/sufficiency/gap stratified review contains 49 SUPPORTED and 71 PARTIALLY_SUPPORTED records, with zero WEAK_OR_UNRESOLVABLE. Full local-tokenizer-only audit has maximum combined length 4,794 under the frozen 8,192 limit and zero overflow. No Qwen model inference or training was run.

Formal corpus SHA256: `d93789de29b746d923660bb2e4ccad501412e75303ddf95f7087c85f6c67d6ca`.

## Hard Gates and limitations

- Task Definition v2, Dataset v3, Basic/Packet/Temporal/Relation/Application v2: PASS.
- Teacher-v2 schema, grounding, trajectory and manual review: PASS after explicit trajectory quarantine; raw repair rate 30.4369% and provider cost remains `UNKNOWN`, both disclosed limitations.
- session-weight harness, one-primary CE, active six-class map and tokenizer length: PASS.
- U_final isolation: PASS; only the prior sealed isolation manifest was read and U_final content was not opened.
- Plan consistency: PASS.
- Formal SFT preflight and full regression: PASS.
- Production online Runtime wiring of every v2 evidence family is still an Agent-stage implementation task; it does not change the frozen offline pretraining input.
- Edge remains predominantly single-capture per attack class; claims remain limited to this acquisition setting.

Plan files updated are `research_plan_detailed.md`, `research_plan_and_timeline.md`, `research_plan_brief.md`, `task_definition_v2.md`, `near_mainline_training_protocol_v1.md`, the Agent architecture and `PROJECT_HANDOFF.md`. The repository has no `research_workflow_overview.md`; no duplicate was created. Active-text search found no remaining current `READY_FOR_FORMAL_SFT=false`, Dataset-v3-in-progress, Backdoor/Uploading/Ransomware-main, old single-gap or old payload-alignment claims. Historical 11-class/Teacher V3/DEC-0021 statements remain only where explicitly marked historical, superseded or as immutable Decision Log evidence.

```text
PLAN_CONSISTENCY_STATUS=PASS
PLAN_FILES_UPDATED=[research_plan_detailed.md,research_plan_and_timeline.md,research_plan_brief.md,task_definition_v2.md,near_mainline_training_protocol_v1.md,agent_architecture_provisional.md,PROJECT_HANDOFF.md,README.md]
PLAN_CONFLICTS_REMAINING=[]
```

## Acceptance block

```text
TASK_DEFINITION_V2_STATUS=PASS
FINAL_MAIN_CLASSES=Normal,DDoS_HTTP,DDoS_TCP,Password,SQL_injection,Vulnerability_scanner
FINAL_MAIN_CLASS_COUNT=6
BACKDOOR_ROLE=LONG_HORIZON_CASE_STUDY
UPLOADING_ROLE=OBSERVABILITY_LIMITED
RANSOMWARE_ROLE=OBSERVABILITY_LIMITED
DATASET_V3_STATUS=PASS
TOTAL_TRAIN=1318688
TOTAL_VAL=270851
TOTAL_TEST=279057
GENERIC_MAIN_TRAIN=0
GENERIC_MAIN_VAL=0
GENERIC_MAIN_TEST=0
UNOBSERVABLE_MAIN_TRAIN=0
UNOBSERVABLE_MAIN_VAL=0
UNOBSERVABLE_MAIN_TEST=0
BASIC_V2_STATUS=PASS
PACKET_ALIGNMENT_STATUS=PASS
TEMPORAL_V2_STATUS=PASS
RELATION_V2_STATUS=PASS
APPLICATION_V2_STATUS=PASS
TEACHER_V2_STATUS=PASS_WITH_EXPLICIT_TRAJECTORY_QUARANTINE
SINGLE_GAP_RATE=0.12801393728222996
MULTI_GAP_RATE=0.03867595818815331
SESSION_WEIGHT_HARNESS_STATUS=PASS
U_FINAL_ISOLATION=PASS
PLAN_CONSISTENCY_STATUS=PASS
SFT_CORPUS_SHA256=d93789de29b746d923660bb2e4ccad501412e75303ddf95f7087c85f6c67d6ca
READY_FOR_FORMAL_SFT=true
FORMAL_SFT_STARTED=false
```
