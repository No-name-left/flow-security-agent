# Dataset-v4 Source Compatibility Round 1

> Status: **COMPLETE — RESEARCHER REVIEW REQUIRED**
>
> Baseline: `6d94bb19d68b83cb18c2188f354daaaa1d88197c`
>
> Scope: official-source inventory, taxonomy/GT contract, one bounded raw micro test, observability, leakage and cost only
>
> Data downloaded: `977,619,426` bytes; all samples remain Git-external
>
> Canonical taxonomy: **PROVISIONAL**

## 1. Executive verdict

Round 1 is complete, but none of the three sources earns an unconditional compatibility PASS.

| Dataset | Round-1 verdict | Exact stop reason | Round 2 |
| --- | --- | --- | --- |
| CICIDS2017 | `BLOCKED_BY_ASSET_SIZE` | The current official gateway requires registration and the smallest raw day exposed by the official page is 7.8 GB. Timezone and NAT capture-vantage semantics remain unproved. | Blocked pending explicit large-download/registration decision. |
| CSE-CIC-IDS2018 | `BLOCKED_BY_ASSET_SIZE` | The smallest official PCAP archive is 38,535,667,707 bytes. The official taxonomy includes Heartbleed, but the current 10-day S3 release has no Heartbleed date/object. The downloadable ML CSV drops the endpoints required for a raw join. | Blocked pending cost decision and taxonomy review. |
| ToN-IoT | `NEEDS_DESIGN_REVIEW` | A real 174 MB PCAP/GT micro test found a fixed 28,800-second PCAP↔GT clock difference. Zero-offset direct matching is 0. A diagnostic offset recovers only the rows belonging to this raw shard, but the offset is not an authorized labeling rule and unmatched sessions are not formally proven benign. | Recommended as a design-review-only Round 2 using the already downloaded micro assets. |

No capture, day, directory or filename label was assigned to a reconstructed session. No formal Dataset-v4 build, taxonomy freeze, Model B training, Unknown experiment, Evidence Utility experiment, continual experiment or RL run is authorized.

## 2. Contract used

The audit applies the current repository contract without changing it:

- target identity is a bidirectional canonical endpoint tuple;
- a new target session is created only after an inter-packet idle gap greater than 60 seconds;
- sessions do not cross source captures;
- source label evidence must join through fields the official release actually provides;
- `capture/day/folder = attack` is never a session-label rule;
- PCAP, Zeek/Bro, CICFlowMeter CSV and NetFlow derivatives from one source event are observation views, not independent domains or independent split samples;
- model-visible Evidence remains label-free and test-time available; dataset, path, capture/run, raw host identity, split, GT and future context stay backend-only.

## 3. Cross-source compatibility matrix

| Dataset | Raw PCAP | Official GT | Fine labels | Time | Endpoints / ports / protocol | Session mapping | Payload | Application | Temporal | Relation | Leakage risk | Estimated cost | Verdict |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| CICIDS2017 | Yes; five days, official total 51.1 GB | Schedule plus labeled CICFlowMeter rows | 15 including benign | Human clock and flow timestamp; timezone not declared | Official flow join claims all tuple fields; NAT chains documented | Not measured; flow/session 1:1 forbidden as an assumption | Full-payload PCAP | Feasible; encrypted traffic limited | Feasible past-only | Feasible, but NAT/vantage unresolved | High: day/run/host and derived-flow coupling | Large; ~120–160 GB working storage | `BLOCKED_BY_ASSET_SIZE` |
| CSE-CIC-IDS2018 | Yes; 10 archives, 477.3 GB compressed | Official web schedule and documented tuple/time flow-label procedure | 16 official; Heartbleed unverified in release | `dd/mm/yyyy HH:MM:SS`; timezone absent | Schedule has public/private pairs; published ML CSV has only destination port + protocol, no endpoints/source port | Not measured; CICFlowMeter timeout may be 600s and is not project session semantics | Raw PCAP yes | Raw + host logs feasible | Feasible past-only | Feasible after public/private endpoint review | Very high: same AWS environment, day/run and many derived variants | Very large; ~1–2 TB extracted workspace | `BLOCKED_BY_ASSET_SIZE` |
| ToN-IoT | Yes; 64 PCAP, 51.66 GB | 18 GT CSV with integer `ts`, endpoints, ports, protocol, type | 10 including normal | **Unresolved +8h GT offset** in real micro | Direct private tuples match after diagnostic offset; no NAT observed in sample | 380 diagnostic direct 1:1 matches; formal zero-offset matching fails; negative semantics unresolved | Raw PCAP yes | 9.40 GB official Zeek/Bro view | Feasible only after clock contract | Network/link and Zeek relation feasible; host/telemetry kept separate | High: PCAP/Zeek/processed/train-test are the same events | Large but chunkable; ~120–180 GB workspace | `NEEDS_DESIGN_REVIEW` |

`FUTURE_CONTEXT_REQUIRED=false`, `CAPTURE_LABEL_REQUIRED=false`, and `GT_REQUIRED_AT_INFERENCE=false` for every proposed source role. These are inference contracts; backend GT is still required to create training/evaluation labels.

## 4. Source provenance and remote assets

### 4.1 CICIDS2017

Authority:

- [UNB CIC official dataset page](https://www.unb.ca/cic/datasets/ids-2017.html)
- [current official registration gateway](https://cicresearch.ca/CICDataset/CIC-IDS-2017/)

The official page identifies the July 3–7, 2017 capture, full-payload PCAP, `GeneratedLabelledFlows.zip`, `MachineLearningCSV.zip`, CICFlowMeter and the complete attack schedule. It reports daily raw sizes of 11.0, 11, 13, 7.8 and 8.3 GB (`51.1 GB` total). The current gateway does not expose an immutable version/checksum manifest or file sizes before registration. The audit did not submit personal registration data.

Release alignment is therefore established only at the official-page level, not by local raw/archive hashes.

### 4.2 CSE-CIC-IDS2018

Authority:

- [UNB CIC official dataset page](https://www.unb.ca/cic/datasets/ids-2018.html)
- [AWS Open Data registry](https://registry.opendata.aws/cse-cic-ids2018)
- official public bucket `s3://cse-cic-ids2018/`

The bucket is currently readable without credentials. Its complete top-level inventory is:

| Asset | Objects | Bytes |
| --- | ---: | ---: |
| Daily PCAP archives | 10 | 477,321,665,202 |
| Daily system-log archives | 10 | 1,932,428,474 |
| Daily processed CICFlowMeter CSV | 10 | 6,886,649,507 |

The smallest raw archive is `Friday-16-02-2018/pcap.zip` at 38,535,667,707 bytes. The smallest processed object is `Thursday-01-03-2018_TrafficForML_CICFlowMeter.csv` at 107,842,858 bytes; it was the only CSE data object downloaded.

### 4.3 ToN-IoT

Authority:

- [UNSW official ToN-IoT page](https://research.unsw.edu.au/projects/toniot-datasets)
- the official SharePoint folder linked from that page
- [author paper DOI](https://doi.org/10.1016/j.scs.2021.102994)

The official SharePoint tree was inventoried through its read-only API rather than inferred from a mirror:

| Network-view asset | Objects | Bytes |
| --- | ---: | ---: |
| PCAP | 64 | 51,661,411,274 |
| Zeek/Bro log and CSV files | 922 | 9,395,016,980 |
| GT CSV | 18 | 1,063,673,030 |
| Processed network CSV | 23 | 3,372,475,448 |
| `train_test_network.csv` | 1 | 29,902,775 |

PCAP, Zeek/Bro, processed CSV, GT and train/test rows are views or subsets of the same ToN-IoT events. They must not be treated as separate domains.

## 5. Taxonomy audit

### 5.1 CICIDS2017

`OFFICIAL_SOURCE_TAXONOMY`:

```text
BENIGN
FTP-Patator
SSH-Patator
DoS slowloris
DoS Slowhttptest
DoS Hulk
DoS GoldenEye
Heartbleed
Web Attack - Brute Force
Web Attack - XSS
Web Attack - Sql Injection
Infiltration
Bot
PortScan
DDoS
```

The official attack families are brute force, DoS/DDoS, web attacks, infiltration, botnet, scanning and Heartbleed. The current official page advertises all label/flow archives, so the release taxonomy is provisionally the same set, but file-level presence was not checked behind the registration gateway. `MICRO_SAMPLE_TAXONOMY=[]`.

Naming aliases include `Brute Force FTP`/`FTP-Patator`, `Brute Force SSH`/`SSH-Patator`, `Botnet`/`Bot`, and `Port Scan`/`PortScan`.

### 5.2 CSE-CIC-IDS2018

The official page defines seven scenario families and these fine schedule labels:

```text
Benign
FTP-BruteForce
SSH-Bruteforce
DoS-GoldenEye
DoS-Slowloris
DoS-SlowHTTPTest
DoS-Hulk
Heartbleed
DDoS attacks-LOIC-HTTP
DDoS-LOIC-UDP
DDOS-HOIC
Brute Force -Web
Brute Force -XSS
SQL Injection
Infiltration
Bot
```

`TAXONOMY_ASSET_STATUS=GAP`: Heartbleed is described in the official scenario taxonomy but is absent from the official dated attack table and from the 10 raw/processed dates in the current S3 release. It is therefore not an available verified class. Port scan is a scenario component, not a separately verified release fine label.

The 107.8 MB micro CSV contains 238,037 `Benign` and 93,063 `Infilteration` rows. It also contains 25 repeated header rows whose final field is the string `Label`; these are format artifacts, not a class. The spelling `Infilteration` differs from the official page's `Infiltration`; `DDoS`/`DDOS` variants and the object name `Thuesday-20-02-2018` are additional official-release aliases/typos.

### 5.3 ToN-IoT

The official network statistics and actual train/test asset both contain:

```text
normal
backdoor
ddos
dos
injection
mitm
password
ransomware
scanning
xss
```

The official full-population statistics report 22,339,021 rows:

| Type | Rows |
| --- | ---: |
| backdoor | 508,116 |
| ddos | 6,165,008 |
| dos | 3,375,328 |
| injection | 452,659 |
| mitm | 1,052 |
| normal | 796,380 |
| password | 1,718,568 |
| ransomware | 72,805 |
| scanning | 7,140,161 |
| xss | 2,108,944 |

The label set is complete, but the current official statistics document says the training/testing subset has 461,043 rows including 300,000 normal, while the actual current `train_test_network.csv` has 211,043 rows including 50,000 normal. The exact difference is 250,000 normal rows. This is a population-count asset gap, not permission to repair or resample the release.

Official folder aliases include the misspelling `normal_runsomware`; actual row label is `ransomware`.

## 6. Candidate common-family mapping (not frozen)

| Source label | Candidate common family | Status |
| --- | --- | --- |
| Any explicit benign/normal | `BENIGN` | `EXACT_PROVISIONAL` |
| FTP/SSH brute force, ToN password | `CREDENTIAL_ACCESS` | exact/family-only provisional |
| DoS/DDoS variants | `AVAILABILITY` | `FAMILY_ONLY_PROVISIONAL` unless mechanism identity is proven |
| SQL injection/XSS/injection | `WEB_EXPLOITATION` | exact or family-only provisional |
| PortScan/scanning | `RECONNAISSANCE` | exact/family-only provisional |
| Bot/backdoor | `MALWARE_C2` | `FAMILY_ONLY_PROVISIONAL` |
| Infiltration/Heartbleed | `INFILTRATION_EXPLOIT` | `FAMILY_ONLY_PROVISIONAL` |
| CIC web brute force | — | `UNMAPPED_PROVISIONAL` |
| ToN MITM/ransomware | — | `UNMAPPED_PROVISIONAL`, observability review required |

Potential Known candidates are `BENIGN`, `AVAILABILITY`, `CREDENTIAL_ACCESS`, `WEB_EXPLOITATION` and `RECONNAISSANCE`. Potential Unknown candidates are only planning references: `MALWARE_C2`, `INFILTRATION_EXPLOIT` and source-local MITM/ransomware. No K/U role is frozen and no Unknown experiment is authorized.

## 7. Ground-truth contracts and time/NAT audit

### CICIDS2017

The official page states that labeled flows use timestamp, source/destination IP, source/destination ports, protocol and attack. It also publishes attack intervals and endpoints. Monday is explicitly benign-only; the other days mix attacks and normal activity.

The page documents NAT chains, but the raw capture vantage has not been checked. Examples include:

1. Kali `205.174.165.73` → firewall `205.174.165.80` → `172.16.0.1` → local victim `192.168.10.50` for FTP/SSH and web attacks.
2. Heartbleed names `172.16.0.11` on the attack path but `172.16.0.1` on the reply path; this official-page inconsistency must be resolved against raw packets.
3. DDoS sources `205.174.165.69-71` traverse the firewall to the victim network.

The human schedule does not declare a timezone. `TIME_ALIGNMENT_STATUS=AMBIGUOUS` and `NAT_MAPPING_STATUS=DOCUMENTED_BUT_CAPTURE_VANTAGE_UNVERIFIED`.

### CSE-CIC-IDS2018

The official page provides attacker, victim, attack, date, start and finish, frequently with both private and public AWS addresses. It states that flow labels use schedule, source/destination IP and ports, and protocol. Examples are:

1. FTP attacker `172.31.70.4` / public `18.221.219.4` to victim `172.31.69.25` / public `18.217.21.148`.
2. SSH attacker `172.31.70.6` / public `13.58.98.64` to the same victim pair.
3. Infiltration public attacker `13.58.225.34` to public/private victim pairs.
4. DDoS uses ten public attackers and a public/private victim pair.

The actual ML CSV has 80 columns beginning with destination port, protocol and timestamp. It has no FlowID, source IP, destination IP or source port. It therefore cannot reproduce the page's labeling join or establish raw session identity. The timestamps have no declared timezone. Raw capture vantage and public/private endpoint choice remain unresolved.

### ToN-IoT

Each official network GT row has:

```text
ts,src_ip,src_port,dst_ip,dst_port,proto,type
```

`ts` is an integer Unix-like second. The official page says the four modalities were labeled by attacker IPs and timestamps, but it does not provide an exhaustive negative rule saying every non-GT network session is benign.

An integrity check also found that `GroundTruth_Network_6.csv` exactly matches its official `Content-Length` yet ends with a truncated row after `dst_port=4`, without protocol or type. This malformed row must fail closed.

## 8. ToN-IoT raw micro alignment

### 8.1 Predeclared selection and identity

The chosen raw object was the smallest official mixed normal+attack PCAP under 1 GiB before match quality was inspected:

```text
PCAP=normal_DDoS_1.pcap
PCAP_BYTES=174070750
PCAP_SHA256=9de31c18e9f1123262fe01e40e1de4309307462695a34c7a1b6892424a97fc1b
GT=GroundTruth_Network_11.csv
GT_BYTES=57153006
GT_SHA256=864b940ac93a6160a7ae4730d8c61eb6442c26f80b9c943f8672371f34c7d546
```

GT11 was selected by numeric epoch overlap after reading the PCAP, not by the `normal_DDoS` folder name.

### 8.2 Extraction

The project production packet parser and exact production sessionization semantics were used without modification.

```text
RAW_PACKET_COUNT=896836
PARSED_IP_PACKET_COUNT=894182
SKIPPED_NON_IP_OR_UNPARSEABLE=2654
RECONSTRUCTED_SESSION_COUNT=147849
PCAP_EPOCH_START=1556203726.876922
PCAP_EPOCH_END=1556205014.255466
PCAP_BACKWARD_TIMESTAMP_STEPS=51
MAX_BACKWARD_SECONDS=0.003326
```

The tiny out-of-order steps are disclosed; none approaches the 60-second session boundary.

### 8.3 Formal zero-offset result

The official GT window that visually corresponds to the PCAP has timestamps exactly 28,800 seconds later. Without modifying official time:

```text
OFFICIAL_LABELED_EVENT_COUNT=168376
SESSION_MATCHED_COUNT=0
SESSION_UNMATCHED_COUNT=147849
SESSION_AMBIGUOUS_COUNT=0
SESSION_CONFLICT_COUNT=0
MATCH_RATE=0
```

This is the formal result. It blocks a production label adapter.

### 8.4 Diagnostic offset only

For diagnosis only, GT time was shifted by `-28800s`; no fuzzy tolerance was added. Direct matching then required exact bidirectional endpoints, ports, protocol and integer second.

```text
DIAGNOSTIC_TOLERANCE_NEEDED=true
DIAGNOSTIC_OFFSET_SECONDS=-28800
FORMAL_RULE_ADOPTED=false

SESSION_MATCHED_COUNT=380
SESSION_UNMATCHED_COUNT=147469
SESSION_AMBIGUOUS_COUNT=0
SESSION_CONFLICT_COUNT=0
SESSION_MATCH_RATE=0.257018986%
UNMATCHED_RATE=99.742981014%

GT_EVENTS_MATCHED_TO_THIS_PCAP=380 / 168376 (0.225685371%)
ONE_TO_ONE_DIRECT_MATCHES=380
ONE_TO_ONE_RATE_AMONG_DIRECT_MATCHES=100%
ONE_TO_MANY_DIRECT_MATCHES=0
MANY_TO_ONE_DIRECT_MATCHES=0
```

The low GT-to-PCAP rate is consistent with a globally chunked GT file covering simultaneous raw shards; it is not evidence that the other GT rows are wrong. It does prove that GT-file number and PCAP-file number are not a pair identity.

### 8.5 Manual deterministic checks

Five matched attack sessions were checked. Endpoint tuples are hashed in this tracked report; raw identities remain Git-external.

| Session | Start–end (PCAP epoch) | Proto | Direct events | Label | Mapping |
| --- | --- | --- | ---: | --- | --- |
| `tnr1_348e4e0491d25d5791e4` | 1556203788.616316–1556203788.617611 | UDP | 1 | ddos | exact tuple/proto/second after diagnostic `GT-28800` |
| `tnr1_9b35292870d4a839a2d7` | 1556203791.204928–1556203791.205456 | TCP | 1 | ddos | same |
| `tnr1_f905d56cd186b4501836` | 1556203791.205459–1556203791.205464 | TCP | 1 | ddos | same |
| `tnr1_cb382c55817e8b52adc0` | 1556203791.205468–1556203791.205468 | TCP | 1 | ddos | same |
| `tnr1_ceb84501e49c2ef309c8` | 1556203776.662722–1556203808.127199 | TCP | 1 | ddos | same |

Five unmatched sessions were checked; each has no exact GT evidence and remains `UNLABELED`, not `normal`:

```text
tnr1_cb590a697fa14b8fec3a TCP tuple=a85a22663ba0a614
tnr1_0226f6b17b6cc4a77892 TCP tuple=ebf2c73384524a7b
tnr1_0e2b44f50243eb42ba69 UDP tuple=39ecb95a6d5a671d
tnr1_e2e5517ab9b8998cb284 UDP tuple=9c2706111d24ff7a
tnr1_a583091b90e12acf34c3 UDP tuple=1144f182cbbd0ed6
```

Five matched benign sessions cannot be supplied without violating the contract: the GT exposes attack-type rows, while the official release text does not prove that every unmatched mixed-PCAP session is benign.

## 9. Label completeness and contamination

| Source | Unlabeled semantics | Benign semantics | Conflict finding |
| --- | --- | --- | --- |
| CICIDS2017 | Attack-day schedule complement is not a label | Monday is explicitly benign-only; attack days require explicit benign flow rows | No session test; Heartbleed NAT path text is inconsistent |
| CSE-CIC-IDS2018 | Day/interval complement is not a label | Explicit `Benign` flow rows only | No session conflict measured; Heartbleed release gap and repeated CSV headers |
| ToN-IoT | `UNKNOWN_NOT_BENIGN` | Explicit processed `normal` exists, but unmatched raw complement is not proven exhaustive benign | 0 direct multi-label session conflicts; GT6 truncated row and 250,000-row train/test statistics mismatch |

`ANY_GT_CONFLICT=true` refers to these official artifact/contract inconsistencies. The ToN direct session-label conflict count is zero.

## 10. Evidence observability

| Source | Basic / packet | Payload | Application | Temporal | Relation | Limitation |
| --- | --- | --- | --- | --- | --- | --- |
| CICIDS2017 | Raw-capable | Full PCAP | Deterministic protocol parsing; encrypted traffic limited | Past-only within capture | Endpoint/link context possible; NAT unresolved | Raw micro unavailable under budget |
| CSE-CIC-IDS2018 | Raw-capable; processed-only micro is insufficient | Raw PCAP | Deterministic raw network parsing; system logs stay a separate non-network capability | Past-only within day | Topology possible after private/public endpoint resolution | Current micro is flow-only; raw very large |
| ToN-IoT | Raw-capable | Raw PCAP; completeness not release-wide audited | Official Zeek/Bro and deterministic raw parsers | Past-only after clock contract | Raw link/endpoint + Zeek; host/telemetry must be a separate capability | Formal PCAP↔GT clock and negative semantics unresolved |

This table is availability, not evidence utility. It does not authorize the Evidence Utility Gate.

## 11. Leakage and identity design

`DERIVED_VARIANT_IDENTITY_COLLISION_RISK=true` for all three sources.

Future adapters must use:

```text
IDENTITY_UNIT_CANDIDATE =
  source release
  + source content hash
  + capture/file
  + source frame span
  + canonical bidirectional tuple
  + session start
  + deterministic ordinal

GROUP_SPLIT_UNIT_CANDIDATE =
  capture/day + attack run/event + host identity set
  (use the strongest grouping available)

DERIVED_VIEW_DEDUP_RULE =
  one source event -> one event_view_group_id
  across PCAP / Zeek / CICFlowMeter CSV / NetFlow derivatives
```

The following may be used for backend grouping/alignment but not as model features: source name, day, file/folder, capture/run, raw public/private IP, absolute timestamp and source object key. No random row split is acceptable.

## 12. Processing cost

| Source | Remote scale | Working-storage estimate | Processing strategy |
| --- | --- | --- | --- |
| CICIDS2017 | 51.1 GB raw; GT/processed sizes hidden before registration | 120–160 GB | Per-day streaming after an explicit download decision |
| CSE-CIC-IDS2018 | 477.3 GB compressed PCAP + 1.93 GB logs + 6.89 GB processed | 1–2 TB | Per-day streaming only; no unconditional full sync |
| ToN-IoT | 51.66 GB PCAP + 9.40 GB Zeek + 1.06 GB GT + 3.37 GB processed | 120–180 GB | Per-file streaming; derived views grouped with source PCAP |

## 13. Unresolved issues and exact stop reasons

1. **CICIDS2017:** registration-gated archive inventory; raw minimum 7.8 GB; timezone absent; NAT path and raw vantage unverified; official Heartbleed NAT text contains a `172.16.0.11`/`172.16.0.1` inconsistency.
2. **CSE-CIC-IDS2018:** 38.5 GB minimum raw archive; Heartbleed taxonomy has no current release date/object; processed CSV lacks endpoint/source-port join fields; timezone and public/private capture endpoint unresolved; repeated-header contamination.
3. **ToN-IoT:** exact +8h PCAP↔GT offset requires an authoritative clock explanation; untagged mixed-PCAP sessions cannot yet be declared benign; GT is globally chunked across raw shards; GT6 has a truncated row; train/test statistics differ from the actual asset by 250,000 normal rows.

No complex workaround was designed. In particular, the diagnostic 8-hour shift is not a formal adapter rule.

## 14. Recommendation for Round 2

Only ToN-IoT should advance immediately, and only to a bounded **design review using the existing downloaded micro assets**:

1. obtain or identify authoritative documentation for the 28,800-second clock transform;
2. prove the GT negative/unmatched semantics;
3. define global-GT-row to raw-shard identity without filename inheritance;
4. quarantine malformed GT rows and reconcile the train/test population-count discrepancy;
5. rerun the same direct join without a diagnostic-only rule.

CICIDS2017 and CSE-CIC-IDS2018 remain scientifically promising but are Round-2 blocked until the researcher explicitly approves their large raw acquisition and, for CSE-CIC-IDS2018, reviews the Heartbleed taxonomy/asset gap. No replacement dataset search is authorized.

## 15. Acceptance block

```text
DATASET_V4_SOURCE_PREFLIGHT_R1_STATUS=COMPLETE_NEEDS_DESIGN_REVIEW

CICIDS2017_SOURCE_PROVENANCE=OFFICIAL_PAGE_VERIFIED_NO_IMMUTABLE_RELEASE_MANIFEST
CICIDS2017_RELEASE_ALIGNMENT=NOT_RAW_VERIFIED_REGISTRATION_AND_SIZE_BLOCKED
CICIDS2017_TAXONOMY_STATUS=PASS_WITH_FILE_LEVEL_VERIFICATION_PENDING
CICIDS2017_LABEL_CONTRACT=FLOW_ROW_PLUS_SCHEDULE_FIELDS; NO_CAPTURE_PROPAGATION
CICIDS2017_MICRO_RAW_TEST=BLOCKED_BY_SIZE_AND_REGISTRATION
CICIDS2017_SESSION_ALIGNMENT=NEEDS_DESIGN_REVIEW
CICIDS2017_CAPTURE_PROPAGATION_REQUIRED=false
CICIDS2017_EVIDENCE_OBSERVABILITY=RAW_CAPABLE_WITH_NAT_LIMITATION
CICIDS2017_ROUND1_VERDICT=BLOCKED_BY_ASSET_SIZE

CSE_CIC_IDS2018_SOURCE_PROVENANCE=OFFICIAL_PAGE_AND_PUBLIC_S3_INVENTORY_VERIFIED
CSE_CIC_IDS2018_RELEASE_ALIGNMENT=PASS_FOR_10_LISTED_DAYS_WITH_HEARTBLEED_TAXONOMY_GAP
CSE_CIC_IDS2018_TAXONOMY_STATUS=GAP
CSE_CIC_IDS2018_LABEL_CONTRACT=BIFLOW_BY_SCHEDULE_ENDPOINT_PORT_PROTOCOL; PUBLISHED_CSV_DROPS_JOIN_FIELDS
CSE_CIC_IDS2018_MICRO_RAW_TEST=BLOCKED_BY_SIZE
CSE_CIC_IDS2018_SESSION_ALIGNMENT=NEEDS_DESIGN_REVIEW_BLOCKED_BY_RAW_SIZE
CSE_CIC_IDS2018_CAPTURE_PROPAGATION_REQUIRED=false
CSE_CIC_IDS2018_EVIDENCE_OBSERVABILITY=RAW_CAPABLE_CURRENT_MICRO_FLOW_ONLY
CSE_CIC_IDS2018_ROUND1_VERDICT=BLOCKED_BY_ASSET_SIZE

TON_IOT_SOURCE_PROVENANCE=OFFICIAL_PAGE_AND_OFFICIAL_SHAREPOINT_INVENTORY_VERIFIED
TON_IOT_RELEASE_ALIGNMENT=RAW_PROCESSED_GT_VIEWS_PRESENT_BUT_CLOCK_AND_COUNT_RECONCILIATION_UNRESOLVED
TON_IOT_TAXONOMY_STATUS=LABEL_SET_PASS_POPULATION_COUNT_GAP
TON_IOT_LABEL_CONTRACT=GT_ROW_TIMESTAMP_PLUS_FIVE_TUPLE; UNTAGGED_COMPLEMENT_NOT_PROVEN_BENIGN
TON_IOT_MICRO_RAW_TEST=COMPLETE_WITH_TIME_ALIGNMENT_BLOCKER
TON_IOT_SESSION_ALIGNMENT=NEEDS_DESIGN_REVIEW
TON_IOT_CAPTURE_PROPAGATION_REQUIRED=false
TON_IOT_EVIDENCE_OBSERVABILITY=PASS_WITH_RELEASE_LIMITATIONS
TON_IOT_ROUND1_VERDICT=NEEDS_DESIGN_REVIEW

CANONICAL_TAXONOMY_STATUS=PROVISIONAL

ANY_CAPTURE_TO_SESSION_LABEL_PROPAGATION=false
ANY_GT_CONFLICT=true
ANY_UNRESOLVED_TIME_ALIGNMENT=true
ANY_UNRESOLVED_NAT_ALIGNMENT=true
ANY_DERIVED_VARIANT_IDENTITY_COLLISION=true

DOWNLOAD_BYTES_USED=977619426

ROUND2_RECOMMENDED_DATASETS=[ToN-IoT design-review-only using current micro assets]
ROUND2_BLOCKED_DATASETS=[CICIDS2017,CSE-CIC-IDS2018]
RESEARCHER_REVIEW_REQUIRED=true

FULL_DATASET_DOWNLOAD_AUTHORIZED=false
FULL_DATASET_V4_BUILD_AUTHORIZED=false
MODEL_B_TRAINING_AUTHORIZED=false
EVIDENCE_UTILITY_GATE_AUTHORIZED=false
UNKNOWN_EXPERIMENT_AUTHORIZED=false
CONTINUAL_EXPERIMENT_AUTHORIZED=false
RL_AUTHORIZED=false
```
