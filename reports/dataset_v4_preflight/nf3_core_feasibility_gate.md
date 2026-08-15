# NF3 Dataset-v4 Core Feasibility Gate

> Audit date: 2026-08-15
> Scope: official NF3 v3 finished products only; no PCAP, Qwen, SFT, Teacher,
> Unknown detector, continual learning, or RL was run.
> Result: `BLOCKED_PENDING_OFFICIAL_METADATA_RECONCILIATION`

## 1. Executive decision

```text
NF3_CORE_FEASIBILITY_STATUS=BLOCKED_PENDING_OFFICIAL_METADATA_RECONCILIATION
NF3_SOURCE_INTEGRITY=NEEDS_REVIEW
NF3_SCHEMA_STATUS=PASS_RELEASE_SELF_CONSISTENT_WITH_PAPER_COUNT_DISCREPANCY
NF3_LABEL_STATUS=NEEDS_REVIEW_UNSW_FINE_COUNT_MISMATCH

PILOT_TOTAL_N=106918

SHORTCUT_PROBE_RESULT=MACRO_F1_0.967608_HIGH_ENVIRONMENT_SHORTCUT
SAFE_BASIC_RESULT=WITHOUT_PORT_MACRO_F1_0.926084
SAFE_FULL_RESULT=SAMPLE_LOCAL_PAST_ONLY_MACRO_F1_0.975511

BASIC_SUFFICIENT_CANDIDATES=[Benign,Bot_C2,DDoS,DoS,Web_Injection]
EVIDENCE_RECOVERABLE_CANDIDATES=[Credential,Recon_Scanning]
OBSERVABILITY_LIMITED_CANDIDATES=[]

CANDIDATE_CORE_CLASSES=[Benign,Bot_C2,Credential,DDoS,DoS,Recon_Scanning,Web_Injection]
CANDIDATE_UNKNOWN_CLASSES=[Credential,Recon_Scanning,Web_Injection]

CROSS_SOURCE_GENERALIZATION_STATUS=WEAK_AND_DOMAIN_DEPENDENT
TEMPORAL_EVIDENCE_FEASIBLE=true_WITH_EXPLICIT_TIMESTAMP_SORT
RELATION_EVIDENCE_FEASIBLE=true_AS_BOUNDED_PAST_FLOW_STATISTICS

RAW_PCAP_REQUIRED_FOR_CORE=false
NF3_SUITABLE_AS_DATASET_V4_CORE=false
CICIoT2023_REQUIRED_FOR_CORE=false
FULL_NF3_DOWNLOAD_REQUIRED_NEXT=false
MODEL_B_PILOT_AUTHORIZED=false
RESEARCHER_REVIEW_REQUIRED=true
NEXT_ACTION=RECONCILE_OFFICIAL_UNSW_LABEL_COUNTS_AND_53_VS_57_FEATURE_METADATA
```

This is not a finding that the downloaded files are corrupt. All four UQ BagIt
payloads match their embedded official SHA-1 manifests, ZIP CRC checks pass,
all binary/multiclass labels are non-null, and `Label=0` is row-wise equivalent
to `Attack=Benign` with zero mismatches. The blocker is a reproducible conflict
between the official CSV and the paper/UQ catalogue text. Under the task's
source-integrity rule, that conflict requires researcher/author review before
NF3 can become the Dataset-v4 Core or authorize Model B.

The bounded pilot nevertheless gives useful conditional evidence: safe flow
features retain strong signal, sample-local past-only features improve the
pooled grouped evaluation, and the task is not dependent on ports. However,
held-out-source performance collapses. NF3 is therefore promising as a
class-filtered multi-source core, but it is not yet a validated cross-domain
benchmark.

## 2. Official source and release integrity

The authoritative publication is [Luay et al., *Temporal Analysis of NetFlow
Datasets for Network Intrusion Detection Systems*](https://arxiv.org/abs/2503.04404),
arXiv v2, 9 March 2025. The official UQ catalogue is [ML-Based NIDS
Datasets](https://staff.itee.uq.edu.au/marius/NIDS_datasets/). UQ identifies
v3 as 43 prior features plus 10 temporal features, or 53 flow features. The
four authoritative dataset records are:

| Dataset | UQ DOI | UQ RDM UUID | Current internal CSV |
| --- | --- | --- | --- |
| NF-UNSW-NB15-v3 | [10.48610/6E0EDA1](https://doi.org/10.48610/6E0EDA1) | `abd2f5d8-e268-4ff0-84fb-f2f7b3ca3e8f` | `NF-UNSW-NB15-v3.csv` |
| NF-ToN-IoT-v3 | [10.48610/44D7C5E](https://doi.org/10.48610/44D7C5E) | `343e2e8c-6e6e-4a0c-813d-a46acea1b7f4` | `NF-ToN-IoT-v3.csv` |
| NF-BoT-IoT-v3 | [10.48610/73C4EBC](https://doi.org/10.48610/73C4EBC) | `db0187cc-1f78-4215-8e34-303364498866` | `NF-BoT-IoT-v3.csv` |
| NF-CSE-CIC-IDS2018-v3 | [10.48610/ECE9B83](https://doi.org/10.48610/ECE9B83) | `4ac221b1-6bd6-42b1-bdf7-03f4fc7efb22` | `NF-CICIDS2018-v3.csv` |

The paper states that raw PCAP was converted by nProbe with
`--dont-reforge-time`, then labelled by timestamp plus source/destination IP,
source/destination port, and protocol. It says the added columns are one binary
and one multiclass label, and that timestamps retain the original PCAP time.
The finished release therefore has an official flow-level label contract; this
gate did not reconstruct or independently validate the raw-PCAP join.

### Remote manifest before download

UQ RDM exposes one open BagIt ZIP per dataset. Range requests work, but the main
CSV is one deflate member, so true whole-file class counts cannot be obtained
from a small random byte range. The inventory was completed before download:

| Remote BagIt ZIP | Compressed bytes | Main CSV uncompressed bytes |
| --- | ---: | ---: |
| `f7546561558c07c5_NFV3DATA-A11964_A11964.zip` | 110,825,147 | 577,360,958 |
| `02934b58528a226b_NFV3DATA-A11964_A11964.zip` | 417,476,635 | 5,302,886,266 |
| `d509c9db7490cf92_NFV3DATA-A11964_A11964.zip` | 72,956,946 | 3,817,527,532 |
| `f78acbaa2afe1595_NFV3DATA-A11964_A11964.zip` | 780,113,687 | 4,222,783,755 |
| **Total** | **1,381,372,415** | **13,920,558,511** |

The exact sum of all uncompressed BagIt members is 13,920,575,596 bytes.
Because 1.381 GB compressed is bounded and is required to verify true row/class
counts and obtain a stratified pilot, all four finished-product ZIPs were
downloaded to `/root/autodl-tmp/dataset_v4_nf3_gate/downloads`. No PCAP or
uncompressed full CSV was materialized.

### Hash and package verification

UQ publishes payload SHA-1 values inside each BagIt archive, not an external
archive checksum. `local ZIP SHA-256` below is an audit fingerprint, not an
official checksum.

| Dataset | Local ZIP SHA-256 | Official main-CSV SHA-1 | Verified |
| --- | --- | --- | --- |
| UNSW | `6d51554df43e324ba8d68fc31a02a83d860ba0a3a93d63320a4a6fc314c9cdfd` | `2cba4879ead17c51e3268a01c06af41186cd90e4` | yes |
| ToN | `b3b6256e970a8986d87716edea4bfd436d68f04058bf5c26cf67e6d839c83698` | `24854ca3072ab7c2ade9ebfb202345a666a94cfe` | yes |
| BoT | `cd0d3eab5b2da73a377561492aafae078432e69c7932b6302a9fbd7f51429eca` | `357cc7ffe46ef57ba8193a58d7a66eff5cf44db8` | yes |
| CSE | `7399bdef73d29875ab388a53e2ae7e592d1952c4ef07ae6de195ba133823d97f` | `ddcad6d826b73a128a447a0189137efd6c8f70c9` | yes |

All ZIP CRC checks passed. The shared `NetFlow_v3_Features.csv` also matches its
BagIt SHA-1 `d028597391217f78df3db31c1dbd96805203196f`.

### Publication/release conflicts

1. The actual UNSW CSV has `Backdoor=4,659`, `Analysis=1,226`, and
   `Shellcode=2,381`. The paper and current UQ catalogue say respectively
   `1,226`, `2,381`, and `4,659`. Total malicious rows still match 127,693.
2. The UQ catalogue summary says UNSW has 127,639 malicious rows, while its own
   class table, the paper, and the CSV sum to 127,693.
3. The UQ catalogue says BoT total rows are 16,993,808 and `Theft=1,651`; the
   CSV and paper binary table have 16,933,808 total rows and the CSV/paper class
   table have `Theft=1,615`.
4. The paper conversion paragraph says nProbe extracts 57 flow features, while
   its feature table, current UQ catalogue, schema file, and every CSV contain
   exactly 53 features plus `Label` and `Attack` (55 columns total).
5. The paper's multiclass table prints incorrect total cells for UNSW and BoT;
   its binary table and the actual CSV totals are internally consistent.

These look like metadata/table defects or an undocumented label-name version,
but this audit cannot choose which authority to silently correct. Hence
`NF3_SOURCE_INTEGRITY=NEEDS_REVIEW`.

## 3. Actual schema

All four current CSVs have the same ordered 55-column header. The 53 feature
columns exactly match the 53 rows in the packaged schema file; the final two
columns are `Label` (binary) and `Attack` (multiclass).

```text
FLOW_START_MILLISECONDS, FLOW_END_MILLISECONDS,
IPV4_SRC_ADDR, L4_SRC_PORT, IPV4_DST_ADDR, L4_DST_PORT,
PROTOCOL, L7_PROTO, IN_BYTES, IN_PKTS, OUT_BYTES, OUT_PKTS,
TCP_FLAGS, CLIENT_TCP_FLAGS, SERVER_TCP_FLAGS,
FLOW_DURATION_MILLISECONDS, DURATION_IN, DURATION_OUT,
MIN_TTL, MAX_TTL, LONGEST_FLOW_PKT, SHORTEST_FLOW_PKT,
MIN_IP_PKT_LEN, MAX_IP_PKT_LEN,
SRC_TO_DST_SECOND_BYTES, DST_TO_SRC_SECOND_BYTES,
RETRANSMITTED_IN_BYTES, RETRANSMITTED_IN_PKTS,
RETRANSMITTED_OUT_BYTES, RETRANSMITTED_OUT_PKTS,
SRC_TO_DST_AVG_THROUGHPUT, DST_TO_SRC_AVG_THROUGHPUT,
NUM_PKTS_UP_TO_128_BYTES, NUM_PKTS_128_TO_256_BYTES,
NUM_PKTS_256_TO_512_BYTES, NUM_PKTS_512_TO_1024_BYTES,
NUM_PKTS_1024_TO_1514_BYTES, TCP_WIN_MAX_IN, TCP_WIN_MAX_OUT,
ICMP_TYPE, ICMP_IPV4_TYPE, DNS_QUERY_ID, DNS_QUERY_TYPE,
DNS_TTL_ANSWER, FTP_COMMAND_RET_CODE,
SRC_TO_DST_IAT_MIN, SRC_TO_DST_IAT_MAX, SRC_TO_DST_IAT_AVG,
SRC_TO_DST_IAT_STDDEV, DST_TO_SRC_IAT_MIN, DST_TO_SRC_IAT_MAX,
DST_TO_SRC_IAT_AVG, DST_TO_SRC_IAT_STDDEV, Label, Attack
```

```text
SCHEMA_MATCH_STATUS=PASS_FOR_ACTUAL_53_PLUS_2_RELEASE_SCHEMA
MISSING_COLUMNS=[]
EXTRA_COLUMNS=[]
PAPER_57_FEATURE_STATEMENT_MATCH=false
```

The release provides numeric L7, DNS and FTP metadata, not parsed HTTP method,
URI, status or payload. NF3 can support flow Basic/Temporal/Relation studies,
but not payload/application-content experiments without another source.

## 4. True label distributions

Counts below come from streaming every official CSV row, not from historical
documentation.

### NF-UNSW-NB15-v3 — 2,365,424 rows

| Fine label | N | Percent |
| --- | ---: | ---: |
| Benign | 2,237,731 | 94.601687% |
| Fuzzers | 33,816 | 1.429596% |
| Analysis | 1,226 | 0.051830% |
| Backdoor | 4,659 | 0.196963% |
| DoS | 5,980 | 0.252809% |
| Exploits | 42,748 | 1.807202% |
| Generic | 19,651 | 0.830760% |
| Reconnaissance | 17,074 | 0.721816% |
| Shellcode | 2,381 | 0.100658% |
| Worms | 158 | 0.006680% |

### NF-ToN-IoT-v3 — 27,520,260 rows

| Fine label | N | Percent |
| --- | ---: | ---: |
| Benign | 16,792,214 | 61.017643% |
| Backdoor | 203,384 | 0.739034% |
| ddos | 4,141,256 | 15.048026% |
| dos | 203,456 | 0.739295% |
| injection | 381,777 | 1.387258% |
| mitm | 6,013 | 0.021849% |
| password | 1,594,777 | 5.794920% |
| ransomware | 3,971 | 0.014429% |
| scanning | 1,358,977 | 4.938097% |
| xss | 2,834,435 | 10.299448% |

### NF-BoT-IoT-v3 — 16,933,808 rows

| Fine label | N | Percent |
| --- | ---: | ---: |
| Benign | 51,989 | 0.307013% |
| DDoS | 7,150,882 | 42.228434% |
| DoS | 8,034,190 | 47.444674% |
| Reconnaissance | 1,695,132 | 10.010341% |
| Theft | 1,615 | 0.009537% |

### NF-CICIDS2018-v3 — 20,115,529 rows

| Fine label | N | Percent |
| --- | ---: | ---: |
| Benign | 17,514,626 | 87.070173% |
| Bot | 207,703 | 1.032551% |
| FTP-BruteForce | 386,720 | 1.922495% |
| SSH-Bruteforce | 188,474 | 0.936958% |
| Brute_Force_-Web | 1,618 | 0.008044% |
| Brute_Force_-XSS | 480 | 0.002386% |
| SQL_Injection | 440 | 0.002187% |
| DDoS_attacks-LOIC-HTTP | 288,589 | 1.434658% |
| DDOS_attack-LOIC-UDP | 3,450 | 0.017151% |
| DDOS_attack-HOIC | 1,032,311 | 5.131911% |
| DoS_attacks-GoldenEye | 61,300 | 0.304740% |
| DoS_attacks-Hulk | 100,076 | 0.497506% |
| DoS_attacks-SlowHTTPTest | 105,550 | 0.524719% |
| DoS_attacks-Slowloris | 36,040 | 0.179165% |
| Infilteration | 188,152 | 0.935357% |

CSE's actual fine rows aggregate exactly to the paper's broad counts:
`DDoS=1,324,350`, `DoS=302,966`, `BruteForce=575,194`, and
`Web Attacks=2,538`.

Across all four sources, binary labels have zero nulls and zero row-wise
inconsistencies with the multiclass benign/attack distinction.

## 5. Candidate broad taxonomy (not frozen)

| Source fine labels | Candidate broad label | Status |
| --- | --- | --- |
| all explicit `Benign` | `Benign` | `EXACT_PROVISIONAL` |
| DoS variants / `dos` | `DoS` | `FAMILY_ONLY_PROVISIONAL` |
| DDoS variants / `ddos` | `DDoS` | `FAMILY_ONLY_PROVISIONAL` |
| Reconnaissance / scanning | `Recon_Scanning` | `FAMILY_ONLY_PROVISIONAL` |
| FTP/SSH brute force / password | `Credential` | `FAMILY_ONLY_PROVISIONAL` |
| CSE web fine labels / injection / xss | `Web_Injection` | `FAMILY_ONLY_PROVISIONAL` |
| CSE Bot | `Bot_C2` | `SOURCE_LOCAL_PROVISIONAL` |
| Backdoor / ransomware | `Malware_Persistence` | `OPTIONAL`; UNSW Backdoor count disputed |
| Fuzzers, Exploits, Generic | — | `UNMAPPED` / `CASE_STUDY_CANDIDATE` |
| Analysis, Shellcode, Worms | — | `UNMAPPED`; UNSW counts disputed for first two |
| MITM, Infilteration, Theft | — | `OPTIONAL` / `CASE_STUDY_CANDIDATE` |

No label was silently remapped. The pilot retained every source fine label in
the stratified artifact, but only the seven explicitly listed broad candidates
participated in the pooled classifier.

## 6. Evidence contract tested

### Safe Basic

Safe Basic uses the current flow's protocol/L7, byte/packet/duration, flags,
packet-length bins, throughput, retransmission, TCP-window, ICMP, DNS, FTP and
within-flow IAT statistics. It excludes raw IPs, absolute start/end time,
source dataset, source row identity, binary label and fine label. Both
with-port and without-port variants were tested; ports are not frozen.

### Temporal and Relation precursor

The diagnostic Full view adds sample-local 10/60/300-second statistics from
strictly earlier flow starts: same-source count, unique destinations, unique
destination ports, same-service attempts, same-destination count, flow/packet/
byte rates, source-destination recurrence, destination fan-in and source
host/service neighbourhood. Equal-timestamp rows are queried before any member
of that timestamp is added, so future/equal-time leakage is excluded.

This is deliberately a precursor. Context contains earlier rows from the
106,918-row deterministic sample, not every one of the 66,935,021 release rows;
it cannot generate formal Evidence Utility labels. A future full builder must
sort explicitly: raw CSV order has start-time inversion counts
`UNSW=335,443`, `BoT=40,736`, `CSE=1`, `ToN=0`.

## 7. Cheap pilot and leakage controls

The deterministic systematic sample takes at most 3,000 rows per
`source_dataset × source_fine_label`, retaining all rows for smaller classes.
It contains 106,918 observations. The broad-class model subset contains 77,538:

| Broad candidate | Pilot N |
| --- | ---: |
| Benign | 12,000 |
| Bot_C2 | 3,000 |
| Credential | 9,000 |
| DDoS | 15,000 |
| DoS | 21,000 |
| Recon_Scanning | 9,000 |
| Web_Injection | 8,538 |

The split group is `source + 5-minute UTC block + unordered endpoint pair`,
assigned by deterministic BLAKE2b to 75% train / 25% evaluation. It produces
58,436 train and 19,102 evaluation rows, zero cross-split group overlap and
zero exact flow-identity overlap. Validation/evaluation rows never update the
RandomForest. CSE Hulk has only three pilot groups and all hash to train, so its
fine-level result is `SPLIT_LIMITED`; broad DoS remains represented in both
folds. This is not a final Dataset-v4 split.

The fixed model is a 120-tree class-balanced RandomForest, depth 20, seed
20260815, with no hyperparameter search.

| Probe | Accuracy | Macro-F1 |
| --- | ---: | ---: |
| Identity/shortcut only | 0.964873 | 0.967608 |
| Safe Basic, without ports | 0.920689 | 0.926084 |
| Safe Basic, with ports | 0.918752 | 0.924267 |
| Safe Full, without ports | 0.973825 | 0.975511 |

Identity/time/source/port shortcuts are severe, but Safe Full does not collapse
and slightly exceeds the shortcut model. Ports do not explain the safe score:
adding them changes Macro-F1 by -0.001816.

## 8. Per-class Basic to Full delta

| Broad class | Basic F1 | Full F1 | Delta |
| --- | ---: | ---: | ---: |
| Benign | 0.923025 | 0.966589 | +0.043563 |
| Bot_C2 | 1.000000 | 1.000000 | +0.000000 |
| Credential | 0.860857 | 0.993577 | +0.132720 |
| DDoS | 0.976870 | 0.994670 | +0.017800 |
| DoS | 0.902865 | 0.973793 | +0.070928 |
| Recon_Scanning | 0.863252 | 0.909739 | +0.046488 |
| Web_Injection | 0.955717 | 0.990208 | +0.034492 |

Candidate interpretation, not a formal thresholded Gate:

- `BASIC_SUFFICIENT_CANDIDATE`: Benign, DDoS, DoS and Web_Injection.
- `Bot_C2` is Basic-separable but source-local/perfect and therefore carries a
  strong environment/run shortcut warning.
- `EVIDENCE_RECOVERABLE_CANDIDATE`: Credential is strong; Recon_Scanning is
  weaker but positive. DoS also has incremental Full gain despite adequate
  Basic performance.
- No mapped broad candidate is demonstrably observability-limited under this
  pilot. Unmapped classes remain `UNKNOWN`, not falsely declared limited.

## 9. Cross-source pilot

The same Safe Full representation was trained on all other sources and tested
on the held-out source, restricted to broad labels shared with training.

| Held-out source | Shared labels | Macro-F1 |
| --- | ---: | ---: |
| BoT | 4 | 0.517889 |
| CSE | 5 | 0.261016 |
| ToN | 6 | 0.155354 |
| UNSW | 3 | 0.460036 |

This is a clear `DOMAIN_DEPENDENCE` signal. Pooled grouped performance must not
be interpreted as cross-environment generalization. Dataset-v4 will need an
explicit held-out-source protocol and likely source-balanced training; the
source identity must remain backend-only.

## 10. Unknown and continual suitability

Conditional on source-integrity resolution, Credential, Recon_Scanning and
Web_Injection are plausible mechanism-distinct classes to hold out from Known.
They have substantial populations and Full F1 of 0.994, 0.910 and 0.990 in the
diagnostic grouped pilot. They are candidates because they appear observable,
not because they are difficult. This does not freeze `K0`, `U_dev`, `U_final`
or a continual stream.

Bot_C2 is not recommended as the first Unknown candidate because it is only
mapped from one source and is perfectly separable, making source/run shortcut a
credible explanation. Unmapped or disputed labels must not be used as Unknown
merely because they are hard or unresolved.

## 11. Dataset-v4 recommendation

NF3 finished products eliminate the immediate need to rebuild 400+ GB sources
from raw PCAP and contain the identifiers/timestamps needed for a safe private
grouping layer plus model-safe flow evidence. The release is compact enough for
full local auditing, and six attack mechanisms plus benign remain plausible
after conservative class filtering.

The current Gate is nevertheless blocked for two reasons:

1. official source metadata contradicts the official payload for multiple
   UNSW fine labels and smaller UNSW/BoT summary values; and
2. pooled separability does not transfer across sources.

The first is the immediate hard blocker. Ask the UQ authors/repository owner to
confirm whether the CSV label names/counts or the paper/catalogue table is the
intended authority, and whether the conversion extracted 53 or 57 pre-label
features. If confirmed as documentation typos, record the response/version and
rerun this report without downloading again. If not confirmed, exclude the
disputed UNSW labels or reject that source; do not infer a silent permutation.

No evidence from this gate requires CICIoT2023 for the Core yet. It may later
be useful for domain diversity, but expanding dataset search/download before
resolving this source contract would violate the bounded-gate policy.

## 12. Reproduction and artifacts

The diagnostic model is reproducible with:

```bash
/root/autodl-tmp/conda/flow-data/bin/python \
  tools/run_nf3_feasibility_pilot.py \
  --pilot /root/autodl-tmp/dataset_v4_nf3_gate/artifacts/nf3_stratified_pilot.parquet \
  --output /root/autodl-tmp/dataset_v4_nf3_gate/artifacts/pilot_results.json
```

Large ZIP/Parquet/results remain Git-external. The tracked JSON companion is the
small machine-readable Gate manifest. No formal Dataset-v4 asset was built and
no model-training stage was authorized.
