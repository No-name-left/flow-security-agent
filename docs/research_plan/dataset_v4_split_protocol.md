# Dataset-v4 Split Protocol v1

> Status: `FROZEN / PASS`
>
> Decision: DEC-0026, 2026-08-16
>
> Scope: official NF3-ToN-IoT Dataset-v4 identity, taxonomy, grouped split,
> Evidence-history isolation, whole-class Unknown rotations, and the bounded
> Teacher-cache sampling population. The B1 observation/Evidence/action/I/O
> interfaces remain those in
> [dataset_v4_b1_runtime_contract.md](dataset_v4_b1_runtime_contract.md).

## 1. Source and taxonomy

The only core source is the official final processed `NF-ToN-IoT-v3.csv` with
SHA256 `53ec8f468a43ede9b1536fabc0390af2fa33ab4312b23ce4d864f186a4651f78`.
Raw PCAP reconstruction is neither required nor used.

`CANONICAL_TAXONOMY_V1` freezes seven targets:

```text
Backdoor, Benign, Credential, DDoS, DoS, Recon_Scanning, Web_Injection
```

The source map is `Backdoor→Backdoor`, `Benign→Benign`,
`password→Credential`, `ddos→DDoS`, `dos→DoS`,
`scanning→Recon_Scanning`, and `injection/xss→Web_Injection`. The 6,013
`mitm` and 3,971 `ransomware` rows retain source provenance and may contribute
label-free legal history, but they are not targets. In the manifest field
`unknown_canonical_label_n=9,984`, “unknown” means intentionally outside this
canonical target map, not a Model-B True-Unknown prediction. Current documents
refer to this quantity as `OUT_OF_CORE_FINE_LABEL_POOL_N=9,984`; the historical
manifest key is retained only for checksum compatibility.

## 2. Immutable row identity

`SOURCE_ROW_ID_CONTRACT_V1` is:

```text
SHA256(
  "NF3_TON_OBSERVATION_V1" NUL
  frozen_csv_sha256 NUL
  zero_based_source_row_index NUL
  canonical_row_digest
)
```

`canonical_row_digest` is SHA256 of the canonical JSON array of all 55 UTF-8
cell strings in official header order. The original source ordinal is bound to
the frozen artifact and never recomputed from a shuffled dataframe. All split,
OOF, Teacher-cache, Unknown-rotation and later Model-B artifacts must reuse this
identity.

## 3. Standard split

Protocol `GROUPED_TEMPORAL_HASH_70_15_15_V1` uses seed `20260816`.
The private activity group is BLAKE2b-128 over the protocol version, five-minute
UTC time block, and unordered raw endpoint pair. Raw endpoints and time remain
lookup-only. A stable hash assigns the whole group to TRAIN/VALIDATION/FINAL_TEST
with 70/15/15 buckets. Labels do not enter the group or assignment hash; they
are used only to audit per-class support.

| Class | TRAIN | VALIDATION | FINAL_TEST |
| --- | ---: | ---: | ---: |
| Backdoor | 140,424 | 29,880 | 33,080 |
| Benign | 12,370,697 | 2,228,630 | 2,192,887 |
| Credential | 1,115,241 | 187,479 | 292,057 |
| DDoS | 2,869,509 | 685,774 | 585,973 |
| DoS | 142,207 | 33,432 | 27,817 |
| Recon_Scanning | 1,011,613 | 174,421 | 172,943 |
| Web_Injection | 2,208,576 | 470,367 | 537,269 |
| **Total** | **19,858,267** | **3,809,983** | **3,842,026** |

Eligible group counts are 58,737 / 12,695 / 12,731. All seven classes occur in
all three partitions. There are zero source-row, exact-duplicate-group, or
activity-group cross-partition overlaps. The full target time ranges naturally
overlap because whole local temporal groups are deterministically assigned;
this is not a global chronological holdout and must not be described as one.

The Git-external row manifest is
`/root/autodl-tmp/processed/dataset_v4_nf3_ton_v1/rows/dataset_v4_row_manifest_v1.parquet`,
SHA256 `faa5220beae65f06591e7ea399c59092985135b81860fcd2388f20cadaa7c095`.
The tracked rebuild contract and exact counts are in
`configs/dataset_v4/dataset_v4_split_manifest_v1.json`.

## 4. Validity, duplicates and history

The full scan covers 27,520,260 source rows. Invalid critical rows are zero.
There are 1,816,137 duplicate copies beyond the first member across 480,040
exact duplicate groups; because identical rows share the same temporal/endpoint
group, cross-split duplicate groups are zero.

These copies are not identity leakage, but may affect optimization and metric
weighting. [experiment_protocol_v1.md](experiment_protocol_v1.md) therefore
requires duplicate-aware derived TRAIN/evaluation views without changing this
master split.

`EVIDENCE_HISTORY_SCOPE_V1` is
`WITHIN_SPLIT_STRICT_END_BEFORE_TARGET_START_V1`. Temporal/Relation lookup may
read only critical-valid contributors in the target's partition whose flow end
is strictly less than target start and lies in a fixed 10/60/300-second window.
Equal-time, overlapping, future, and cross-split rows are forbidden. Target GT,
attack interval and canonical eligibility never choose neighbors.

## 5. Whole-class Unknown rotations

Three development/final rotations are frozen:

- `Credential` held out as a whole class;
- `Recon_Scanning` held out as a whole class;
- `Web_Injection` held out as a whole class.

In each rotation the class is absent from Known classifier fit and Known
threshold tuning. TRAIN+VALIDATION supplies development/meta observations;
FINAL_TEST is sealed evaluation and never tunes a threshold. Exact per-rotation
counts and Known maps are in
`configs/dataset_v4/unknown_rotation_manifest_v1.json`.

## 6. Reference states and Teacher-cache pools

The bounded reference materializer is a sampling diagnostic, not Model B. It
uses group-disjoint three-fold TRAIN OOF predictions and TRAIN-fit VALIDATION
predictions from Random Forests. Basic+strict Temporal/Relation recovery creates
only backend sampling provenance. FINAL_TEST contributes zero reference rows.

`teacher_cache_v1` uses the already frozen sampling seed `20260815` and contains
exactly 2,000 unique rows: 750 Basic-sufficient Known, 850 recoverable Known,
and 400 whole-class True-Unknown rotation rows; their development/evaluation
subquotas are 450/300, 510/340 and 240/160. TRAIN-side development groups are
reserved from Known classifier fit; VALIDATION-side policy-evaluation groups
are reserved from Known threshold fit. No private group crosses the two roles.

The Teacher request projection contains only the opaque sample handle, Basic
card with explicit missing indicators, Known prediction summary, Evidence mask,
and available Temporal/Relation actions. GT, recovery outcome, Unknown role,
split/group, raw identity, future/full Evidence and utility targets remain in a
separate Git-external offline manifest. FINAL_TEST contamination, source overlap,
private-group role overlap and request leakage are all zero. No response or API
call is part of this protocol.

The 63-entry semantic-admissibility request manifest covers seven mechanism
keys × three B1 Evidence families × three pattern roles. It is class/family
review only and cannot become operational utility ground truth.

## 7. Rebuild and authority

Run the local zero-network generator with:

```bash
/root/autodl-tmp/conda/flow-data/bin/python \
  tools/finalize_dataset_v4_split.py \
  --repo-root /root/autodl-tmp/workspace/flow-security-agent \
  --archive /root/autodl-tmp/dataset_v4_nf3_gate/downloads/nf3_ton.zip \
  --pilot /root/autodl-tmp/dataset_v4_nf3_gate/artifacts/nf3_stratified_pilot.parquet \
  --output-root /root/autodl-tmp/processed/dataset_v4_nf3_ton_v1
```

Tracked manifests and the final audit report are authoritative summaries;
large row/reference/request assets remain Git-external. This PASS authorizes
the previously preregistered low-cost Model-B design gates, but does not start
or authorize a formal Model-B training run. Generating DeepSeek responses still
requires a separate explicit researcher action.
