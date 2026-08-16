# Dataset-v4 Final Split Report

> Status: `PASS`
>
> Scope: deterministic NF3-ToN Dataset-v4 split, whole-class Unknown rotations,
> low-cost tree reference states, and offline Teacher/semantic request manifests.
> No DeepSeek, Qwen, Model B training, SFT, continual learning, RL, download, or
> raw-PCAP processing was performed.

## 1. Frozen result

```text
DATASET_V4_FINAL_SPLIT_STATUS=PASS
DATASET_V4_CORE=NF3-ToN-IoT
SOURCE_ARTIFACT_SHA256=53ec8f468a43ede9b1536fabc0390af2fa33ab4312b23ce4d864f186a4651f78
CANONICAL_TAXONOMY_V1=Backdoor,Benign,Credential,DDoS,DoS,Recon_Scanning,Web_Injection
SOURCE_ROW_ID_CONTRACT=SOURCE_ROW_ID_CONTRACT_V1
SPLIT_PROTOCOL=GROUPED_TEMPORAL_HASH_70_15_15_V1
SPLIT_SEED=20260816
SPLIT_MANIFEST_SHA256=faa5220beae65f06591e7ea399c59092985135b81860fcd2388f20cadaa7c095
EVIDENCE_HISTORY_SCOPE=WITHIN_SPLIT_STRICT_END_BEFORE_TARGET_START_V1
```

The formal target remains one official complete bidirectional flow row. Source
identity binds the frozen artifact, original zero-based row ordinal, and
canonical row digest; dataframe order cannot change it.

## 2. Standard split

| Canonical class | TRAIN | VALIDATION | FINAL_TEST |
| --- | ---: | ---: | ---: |
| Backdoor | 140,424 | 29,880 | 33,080 |
| Benign | 12,370,697 | 2,228,630 | 2,192,887 |
| Credential | 1,115,241 | 187,479 | 292,057 |
| DDoS | 2,869,509 | 685,774 | 585,973 |
| DoS | 142,207 | 33,432 | 27,817 |
| Recon_Scanning | 1,011,613 | 174,421 | 172,943 |
| Web_Injection | 2,208,576 | 470,367 | 537,269 |

Totals: TRAIN `19,858,267`, VALIDATION
`3,809,983`, FINAL_TEST
`3,842,026`. Assignment is a stable 70/15/15
hash of a five-minute temporal block plus unordered endpoint pair. Label is used
only to audit support, never in the group key or runtime Evidence.

The Git-external row manifest is `/root/autodl-tmp/processed/dataset_v4_nf3_ton_v1/rows/dataset_v4_row_manifest_v1.parquet`
(`2,084,881,501` bytes; SHA256
`faa5220beae65f06591e7ea399c59092985135b81860fcd2388f20cadaa7c095`). Its rules, counts and rebuild command are
tracked in `configs/dataset_v4/dataset_v4_split_manifest_v1.json`.

## 3. Identity, duplicate and validity audit

```text
EXACT_DUPLICATE_N=1816137
INVALID_CRITICAL_ROW_N=0
UNKNOWN_CANONICAL_LABEL_N=9984
DUPLICATE_GROUP_CROSS_SPLIT_N=0
ACTIVITY_GROUP_CROSS_SPLIT_N=0
```

`mitm` and `ransomware` remain in source provenance and label-free history
eligibility but are not Dataset-v4 targets. This avoids using GT to filter
runtime neighbors while preserving the frozen seven-class taxonomy.

## 4. Evidence history isolation

Temporal and Relation contributors must be in the target's same standard split,
must satisfy `contributor.FLOW_END_MILLISECONDS <
target.FLOW_START_MILLISECONDS`, and must fall within the fixed 10/60/300-second
window. Equal-time, overlapping, future and cross-split rows are excluded. Raw
IP/port/time values remain lookup-only and GT never selects a neighbor.

## 5. Whole-class Unknown rotations

| Rotation | Unknown class | Development/meta observations | Sealed FINAL_TEST observations | Status |
| --- | --- | ---: | ---: | --- |
| UNKNOWN_ROTATION_V1_R1 | Credential | 1,302,720 | 292,057 | PASS |
| UNKNOWN_ROTATION_V1_R2 | Recon_Scanning | 1,186,034 | 172,943 | PASS |
| UNKNOWN_ROTATION_V1_R3 | Web_Injection | 2,678,943 | 537,269 | PASS |

For each rotation the Unknown class is absent from Known classifier training and
Known threshold-tuning data. FINAL_TEST Unknown labels never tune a threshold.

## 6. Reference state and Teacher cache

The bounded reference pipeline uses Random Forests only. TRAIN states use
group-disjoint OOF predictions; VALIDATION states use models fit only on TRAIN;
whole-class Unknown states are predicted by a classifier that never saw the
held-out class. Strict full-release, within-split past-only history is used.
This materialization is not Model B training or a formal model comparison.

```text
REFERENCE_BASIC_SUFFICIENT_KNOWN_N=56295
REFERENCE_RECOVERABLE_KNOWN_N=24028
TEACHER_CACHE_V1_N=2000
TEACHER_CACHE_FINAL_TEST_CONTAMINATION=0
TEACHER_PAYLOAD_LEAKAGE_N=0
TEACHER_RESPONSES_GENERATED=0
DEEPSEEK_CALLS=0
```

The 1,200 policy-demo-development rows may support optional demonstration or
imitation. The 800 policy-meta-evaluation rows are evaluation-only. No sample
touches FINAL_TEST, and Teacher request payloads contain no GT, recoverability,
true-Unknown flag, future Evidence, split, raw endpoint/time, or utility target.
Capacity-limited class/confidence cells are recorded in the tracked allocation
audit and redistributed deterministically without duplicating rows.

## 7. Semantic reference

The tracked request manifest contains 63 requests: seven class/mechanism keys ×
three B1 Evidence families × three pattern roles. It is ready for a separately
authorized review call, contains no responses, and can never become operational
utility GT.

## 8. Acceptance

```text
DATASET_V4_FORMALIZATION_STATUS=PASS
TEACHER_CACHE_V1_SAMPLE_MANIFEST_READY=true
TEACHER_CACHE_V1_READY_TO_GENERATE=true
SEMANTIC_REFERENCE_REQUEST_MANIFEST_READY=true
SEMANTIC_REFERENCE_V1_READY_TO_GENERATE=true
MODEL_B_LOW_COST_GATES_AUTHORIZED=true
NEXT_ACTION=GENERATE_PREPRICE_DEEPSEEK_CACHE_AND_SEMANTIC_REFERENCE
```

The next action still requires explicit researcher authorization. This report
does not itself authorize API calls or Model B execution.
