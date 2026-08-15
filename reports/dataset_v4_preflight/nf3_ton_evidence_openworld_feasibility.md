# NF3-ToN Core + Evidence-Conditioned Open-World Feasibility Gate

> Audit date: 2026-08-15
> Scope: the immutable official NF3-ToN-IoT-v3 finished product and a bounded,
> deterministic ToN-only pilot. No raw PCAP, Qwen, Teacher/API, GPU, formal
> Dataset-v4 build, Model B, continual learning, or RL was run.
> Result: `CORE_RESEARCH_ROUTE_FEASIBLE=true_WITH_LIMITATIONS`.

## 1. Executive result

```text
NF3_TON_ARTIFACT_RECONCILIATION_STATUS=PASS
NF3_TON_OFFICIAL_FINAL_ARTIFACT=true
NF3_TON_RAW_REPROCESSING_REQUIRED=false
NF3_TON_SCHEMA_STATUS=PASS
NF3_TON_LABEL_STATUS=PASS_EXACT_MATCH_TO_PAPER_AND_UQ_CATALOGUE
NF3_TON_DOCUMENTATION_DISCREPANCY=NON_BLOCKING_53_VS_57_COUNT_ONLY

TON_ONLY_PILOT_N=24000
TON_ONLY_CORE_CLASS_CANDIDATES=[Backdoor,Benign,Credential,DDoS,DoS,Recon_Scanning,Web_Injection]

OOF_FOLDS=3
OOF_BASIC_MACRO_F1=0.9241027728324086
OOF_FULL_MACRO_F1=0.9542507313534688

PER_CLASS_RECOVERABILITY={
  Backdoor: 6/3000 (0.002000),
  Benign: 966/3000 (0.322000),
  Credential: 57/3000 (0.019000),
  DDoS: 122/3000 (0.040667),
  DoS: 324/3000 (0.108000),
  Recon_Scanning: 734/3000 (0.244667),
  Web_Injection: 670/6000 (0.111667)
}

RECOVERABLE_KNOWN_TOTAL=2879
RECOVERABLE_KNOWN_RATE=0.11995833333333333

UTILITY_PREDICTION_STATUS=CLEAR_SIGNAL
UTILITY_PREDICTION_AUROC=0.9559201214445113
UTILITY_PREDICTION_AUPR=0.6823986368255095

UNKNOWN_ROTATIONS=[Credential,Recon_Scanning,Web_Injection]
DIRECT_NOVELTY_UNKNOWN_AUROC=0.7583657442883499
EVIDENCE_CONDITIONED_UNKNOWN_AUROC=0.7683698955976005

DIRECT_FALSE_UNKNOWN_ON_RECOVERABLE_KNOWN=0.3062080536912752
EVIDENCE_CONDITIONED_FALSE_UNKNOWN_ON_RECOVERABLE_KNOWN=0.24161073825503357

EVIDENCE_ACQUISITION_RATE=0.1459902525476296

Q1_ARTIFACT_READY=true
Q2_RECOVERABLE_KNOWN_EXISTS=true
Q3_UTILITY_PREDICTABILITY=CLEAR_SIGNAL
Q4_EVIDENCE_CONDITIONED_OPEN_WORLD=GOOD_AGGREGATE_WITH_CLASS_CONDITIONAL_LIMITATIONS

CORE_RESEARCH_ROUTE_FEASIBLE=true_WITH_LIMITATIONS

CANONICAL_PLAN_REVISION_AUTHORIZED=false_PENDING_RESEARCHER_REVIEW
MODEL_B_DESIGN_AUTHORIZED=false_PENDING_PLAN_REVISION

NEXT_ACTION=RESEARCHER_REVIEW_THEN_REVISE_CANONICAL_PLANS_FREEZE_TON_CORE_ROLE_AND_DESIGN_MODEL_B
```

This Gate answers the four feasibility questions positively at pilot scale.
The official ToN finished product is independently usable without rebuilding
raw labels; recoverable Known samples exist; their utility is predictable from
Basic-visible state under nested cross-fitting; and aggregate Evidence recovery
reduces false Unknown while slightly improving Unknown discrimination.

The result is not an unconditional architecture freeze. `Recon_Scanning`
remains difficult as a held-out Unknown, and the `Web_Injection` rotation
improves Unknown AUROC/recall while worsening its recoverable-Known false-
Unknown rate. These class-conditional errors must shape the next protocol.

## 2. TASK A — official artifact reconciliation

### 2.1 Authority and processing contract

The authoritative publication is [Luay et al., *Temporal Analysis of NetFlow
Datasets for Network Intrusion Detection Systems*](https://arxiv.org/abs/2503.04404).
The authoritative release directory is the [University of Queensland NIDS
dataset catalogue](https://staff.itee.uq.edu.au/marius/NIDS_datasets/), and the
ToN dataset has [UQ DOI 10.48610/44D7C5E](https://doi.org/10.48610/44D7C5E).

The paper describes the release lineage as:

```text
PCAP
-> nProbe with original PCAP timestamps preserved
-> precise timestamp + bidirectional 5-tuple GT matching
-> binary Label + multiclass Attack
-> final NF3-ToN-IoT-v3 CSV
```

This Gate verified the final artifact; it did not recreate that process or
revisit the raw ToN `-28800s` issue. UQ describes each released row as one
labelled network flow. Within this task, that official flow row is the
observation unit.

### 2.2 Immutable artifact identity

| Field | Value |
| --- | --- |
| `ARTIFACT_SOURCE_URL` | `https://rdm.uq.edu.au/files/343e2e8c-6e6e-4a0c-813d-a46acea1b7f4` |
| `LOCAL_PATH` | `/root/autodl-tmp/dataset_v4_nf3_gate/downloads/nf3_ton.zip` |
| `ARCHIVE_NAME` | `02934b58528a226b_NFV3DATA-A11964_A11964.zip` |
| `ARCHIVE_SIZE` | `417,476,635` bytes |
| `ARCHIVE_SHA256` | `b3b6256e970a8986d87716edea4bfd436d68f04058bf5c26cf67e6d839c83698` |
| `EMBEDDED_HASH_STATUS` | `PASS` — BagIt CSV SHA-1 matched |
| `ZIP_CRC_STATUS` | `PASS` |
| `CSV_MEMBER` | `.../data/NF-ToN-IoT-v3.csv` |
| `CSV_SIZE` | `5,302,886,266` bytes |
| `CSV_SHA256` | `53ec8f468a43ede9b1536fabc0390af2fa33ab4312b23ce4d864f186a4651f78` |
| Embedded CSV SHA-1 | `24854ca3072ab7c2ade9ebfb202345a666a94cfe` |
| `ROW_COUNT` | `27,520,260` |
| `COLUMN_COUNT` | `55` |

No archive or CSV was added to Git.

### 2.3 Actual schema

```text
ACTUAL_CSV_COLUMN_COUNT=55
ACTUAL_PREDICTOR_COLUMNS=53
MODEL_VISIBLE_SAFE_BASIC_COLUMNS=47
IDENTITY_OR_LOOKUP_COLUMNS=[IPV4_SRC_ADDR,IPV4_DST_ADDR]
TIMESTAMP_COLUMNS=[FLOW_START_MILLISECONDS,FLOW_END_MILLISECONDS]
LABEL_COLUMNS=[Label,Attack]
```

The 53 official predictor columns consist of:

- two absolute timestamps used for ordering/grouping, never direct model input;
- two raw IP addresses used for private history/relation lookup and grouping;
- two ports, retained by the release but excluded from the primary Safe Basic
  pilot (the prior audit separately showed ports were not required);
- 47 model-visible candidates covering protocol/L7 code, directional
  bytes/packets, TCP flags, duration, TTL, packet-length bins, retransmission,
  throughput, windows, ICMP, DNS, FTP and directional IAT statistics.

The ordered release columns match the bundled 53-feature dictionary exactly.
There are no unknown, missing, or same-name/different-semantics columns.
One paper paragraph says 57 features, whereas its feature table, UQ record,
bundled dictionary, and CSV all say/contain 53. For this immutable artifact:

```text
DOCUMENTATION_COUNT_DISCREPANCY=NON_BLOCKING
```

### 2.4 ToN labels

| Official label | CSV count | Percentage | Paper/UQ match |
| --- | ---: | ---: | --- |
| Benign | 16,792,214 | 61.017643% | exact |
| DoS | 203,456 | 0.739295% | exact |
| DDoS | 4,141,256 | 15.048026% | exact |
| Scanning | 1,358,977 | 4.938097% | exact |
| XSS | 2,834,435 | 10.299448% | exact |
| Password | 1,594,777 | 5.794920% | exact |
| Injection | 381,777 | 1.387258% | exact |
| Backdoor | 203,384 | 0.739034% | exact |
| Ransomware | 3,971 | 0.014429% | exact |
| MITM | 6,013 | 0.021849% | exact |

All 27,520,260 rows have both labels, and `Label=0` is exactly equivalent to
`Attack=Benign`; conflicts are zero.

```text
NF3_TON_LABEL_COUNTS_MATCH_PAPER=true
NF3_TON_UNKNOWN_LABELS=[]
NF3_TON_LABEL_CONFLICTS=0
NF3_TON_ARTIFACT_USABLE=true
```

The unresolved UNSW and BoT metadata discrepancies from the preceding Gate do
not affect this ToN-only verdict.

## 3. TASK B — ToN-only candidate taxonomy

The pilot preserved source fine labels and applied this non-frozen candidate
mapping:

| Candidate class | ToN fine labels | Pilot N |
| --- | --- | ---: |
| Benign | Benign | 3,000 |
| DDoS | ddos | 3,000 |
| DoS | dos | 3,000 |
| Recon_Scanning | scanning | 3,000 |
| Credential | password | 3,000 |
| Web_Injection | xss + injection | 6,000 |
| Backdoor | Backdoor | 3,000 |

`mitm` and `ransomware` remain preserved source labels but were excluded from
the 24,000-row candidate-core pilot. `Backdoor` was not renamed to Persistence.
This table is a Gate proposal, not a frozen Dataset-v4 taxonomy.

## 4. TASK C — OOF Basic versus Full

### 4.1 Evidence and split contract

`SAFE_BASIC` contains the 47 non-identity, non-time, no-port release features.
`SAFE_FULL` adds the preceding pilot's deterministic, sample-local 10/60/300s
strictly-past Temporal/Relation statistics. Equal-start-time rows are excluded
from one another's context. Raw IP and absolute time are lookup/grouping inputs
only; source identity, future traffic and GT never enter either classifier.

Three folds were used because nested meta cross-fitting and three whole-class
rotations already require 36 bounded RF fits. Assignment is deterministic by:

```text
5-minute UTC block + unordered endpoint pair -> BLAKE2b fold
```

There are 6,766 groups, zero cross-fold group overlap, 24,000 unique source row
identities and no self-scored row. The RF has 80 trees, depth 20,
`balanced_subsample`, fixed seed `20260815`, one CPU worker and no tuning.

Important limitation: past context is computed from the deterministic 30,000-
row ToN stratified sample, not from all 27.5M release rows. These numbers are
feasibility diagnostics, not paper metrics or final utility labels.

### 4.2 Aggregate OOF results

| Metric | Safe Basic | Safe Full |
| --- | ---: | ---: |
| Accuracy | 0.927417 | 0.957083 |
| Macro-F1 | 0.924103 | 0.954251 |

```text
DELTA_NLL_MEAN=0.078036
DELTA_NLL_MEDIAN=0.001073
POSITIVE_DELTA_NLL_RATE=0.629917
RECOVERABLE_KNOWN=2879/24000 (0.119958)
```

`RECOVERABLE_KNOWN` means Basic was wrong or below a fold-training-derived
uncertainty threshold, while Full was correct. The threshold never uses the
row being scored.

### 4.3 Per-class recoverability

| Class | N | Basic correct | Full correct | Basic uncertain | Recovered N/rate | mean delta NLL | median delta NLL | positive delta |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Backdoor | 3,000 | 0.997667 | 0.997667 | 0.004000 | 6 / 0.002000 | 0.004093 | 0.000000 | 0.427667 |
| Benign | 3,000 | 0.753333 | 0.790000 | 0.290000 | 966 / 0.322000 | 0.140097 | 0.009835 | 0.656333 |
| Credential | 3,000 | 0.992667 | 0.991667 | 0.021000 | 57 / 0.019000 | -0.011627 | 0.000000 | 0.492333 |
| DDoS | 3,000 | 0.973333 | 0.981333 | 0.054667 | 122 / 0.040667 | 0.019605 | 0.003762 | 0.764333 |
| DoS | 3,000 | 0.964667 | 0.993000 | 0.109667 | 324 / 0.108000 | 0.082401 | 0.000471 | 0.705667 |
| Recon_Scanning | 3,000 | 0.879000 | 0.918000 | 0.254667 | 734 / 0.244667 | 0.141887 | 0.105167 | 0.814000 |
| Web_Injection | 6,000 | 0.929333 | 0.992500 | 0.077667 | 670 / 0.111667 | 0.123917 | 0.002680 | 0.589500 |

The desired within-class mixture exists most clearly for Benign,
Recon_Scanning, DoS and Web_Injection. Backdoor is almost always Basic-
sufficient. Credential is also Basic-sufficient and has slightly negative mean
delta NLL, so it is a Known/Unknown candidate but not a strong acquisition
class in this pilot. No core candidate is labelled Observability-Limited from
this experiment.

## 5. TASK D — utility predictability

The binary target is the OOF `RECOVERABLE_KNOWN` state above. Continuous utility
is `NLL_basic - NLL_full`. A class-balanced logistic regression sees only:

```text
Safe Basic features
+ Basic classifier max confidence
+ Basic margin
+ Basic entropy
```

It cannot access GT, Full Evidence, future traffic, absolute identity or
absolute timestamp. Each of the three outer meta folds creates training utility
targets through a separate three-fold inner OOF; the selector is then evaluated
on the untouched outer fold.

| Metric | Result |
| --- | ---: |
| AUROC | 0.955920 |
| AUPR | 0.682399 |
| F1 at fixed 0.5 | 0.666095 |
| Spearman with continuous delta NLL | 0.505598 |
| Positive prevalence | 0.119958 |

```text
UTILITY_PREDICTION_STATUS=CLEAR_SIGNAL
```

This is evidence that acquisition value is predictable from Basic-visible
state. It does not determine the final selector model, threshold, Evidence
family, or cost coefficient. `COST=1` was conceptually uniform; no cost tuning
was performed.

## 6. TASK E — Evidence-conditioned open world

### 6.1 Protocol

The preregistered rotations were run in this order:

1. Credential;
2. Recon_Scanning;
3. Web_Injection.

Each class is wholly absent from its classifier training and Known calibration.
It is also masked from the history lookup used to build Known train/calibration
Full features; held-out evaluation rows may use their own deployment-legal
strictly-past traffic context.
Groups use a deterministic 60/20/20 train/calibration/evaluation assignment,
with zero cross-partition group overlap. Only the evaluation partition of the
held-out class is exposed to final metrics.

Direct novelty uses Basic MSP. Evidence-conditioned novelty acquires Full when
Basic confidence is below a fixed 10th-percentile Known-calibration threshold,
then scores novelty from the resulting stage. Unknown thresholds are calibrated
only on Known validation and conservatively enforce at most a 5% Known FPR;
ties never expand the budget. No Unknown label tunes a model or threshold.

### 6.2 Aggregate comparison

| Policy | Unknown AUROC | Unknown AUPR | Unknown recall at fixed Known FPR | false Unknown on recoverable Known | acquisition rate |
| --- | ---: | ---: | ---: | ---: | ---: |
| Direct novelty | 0.758366 | 0.431084 | 0.310805 | 0.306208 | 0 |
| Always acquire when uncertain | 0.768370 | 0.442585 | 0.321472 | 0.241611 | 0.145990 |
| Simple utility selector | 0.768358 | 0.442700 | 0.321472 | 0.243289 | 0.145621 |

Always-acquire reduces pooled false Unknown on recoverable Known by 0.064597
absolute, or 21.10% relative, while improving—not degrading—mean Unknown AUROC,
AUPR and recall. With one Basic→Full transition, acquisition rate equals the
average number of extra Evidence steps.

The simple selector almost exactly reproduces always-acquire at similar cost.
That is compatible with the strong utility AUROC, but it does not yet establish
a cost advantage. No RL or complex OOD algorithm is justified here.

### 6.3 Rotation detail

| Held-out class | Unknown eval N | Direct→Evidence AUROC | Direct→Evidence Unknown recall | Direct→Evidence FURK |
| --- | ---: | ---: | ---: | ---: |
| Credential | 566 | 0.820826 → 0.828867 | 0.284452 → 0.219081 | 0.328512 → 0.190083 |
| Recon_Scanning | 487 | 0.554788 → 0.568251 | 0.055441 → 0.078029 | 0.407609 → 0.328804 |
| Web_Injection | 1,043 | 0.899484 → 0.907992 | 0.592522 → 0.667306 | 0.164706 → 0.220588 |

The aggregate route passes, but the errors are heterogeneous:

- Credential substantially lowers recoverable-Known false Unknown and raises
  AUROC, but its fixed-FPR Unknown recall falls after acquisition.
- Recon_Scanning remains close to chance as an Unknown despite lower FURK.
- Web_Injection gains true-Unknown detection but sends more recoverable Known
  rows to Unknown under the stage-specific conservative threshold.

Therefore the next design must report class-conditional routing and cannot
claim that one acquisition rule uniformly helps every held-out class.

## 7. Architecture feasibility verdict

| Question | Verdict | Evidence |
| --- | --- | --- |
| Q1 artifact ready | `true` | official ToN labels/schema/hashes reconcile; raw rebuilding unnecessary |
| Q2 recoverable Known exists | `true` | 2,879/24,000 OOF samples; class-conditional concentration |
| Q3 utility predictable | `CLEAR_SIGNAL` | nested AUROC 0.955920, AUPR 0.682399 |
| Q4 Evidence-conditioned open world | `GOOD_AGGREGATE_WITH_CLASS_CONDITIONAL_LIMITATIONS` | pooled FURK down; Unknown metrics up; Web/Recon limitations disclosed |

```text
CORE_RESEARCH_ROUTE_FEASIBLE=true_WITH_LIMITATIONS
```

This authorizes a researcher decision about the next architecture revision; it
does not itself freeze ToN as Dataset-v4 Core or authorize Model B execution.
Per the task boundary, canonical plans remain unchanged until review.

## 8. Reproducibility and boundaries

Reproduce the bounded diagnostic with:

```bash
/root/autodl-tmp/conda/flow-data/bin/python \
  -m tools.run_nf3_ton_openworld_pilot \
  --pilot /root/autodl-tmp/dataset_v4_nf3_gate/artifacts/pilot_ton.parquet \
  --output /root/autodl-tmp/dataset_v4_nf3_gate/artifacts/ton_openworld_results.json \
  --trace-output /root/autodl-tmp/dataset_v4_nf3_gate/artifacts/ton_openworld_oof_trace.parquet \
  --folds 3 --trees 80 --seed 20260815
```

The full per-sample OOF trace and raw pilot summary stay Git-external. The
tracked JSON report contains their paths and SHA256 values. No PCAP, dataset
archive, large table, checkpoint, model, or cache is tracked.

Stopped after TASK A/C/D/E as required. No taxonomy freeze, canonical-plan
rewrite, Model B, Unknown clustering, continual adaptation, Qwen, Teacher, API,
RL, CICIoT2023, or other-source work followed this Gate.
