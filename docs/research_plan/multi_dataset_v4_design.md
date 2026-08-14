# Multi-Dataset Dataset-v4 / Model B Design

> Status: **PLANNING_COMPLETE / NO DATASET-v4 BUILD STARTED**
>
> Date: 2026-08-15
>
> Entry gate: `MODEL_A_ACCEPTED_FOR_WARM_START=true` with `EVIDENCE_STATE_STATUS=FAIL`
> Scope: design, compatibility contracts, and pre-download decisions only

## 1. Design goals

Dataset-v4 is not a concatenation of public CSV files. It is an auditable multi-domain corpus in which every source passes a dataset-specific ground-truth adapter and emits one common session, label, split, and model-safe Evidence contract.

The goals are:

1. extend attack-mechanism and acquisition-domain coverage beyond the six-class Edge controlled benchmark;
2. separate exact shared fine labels from family-only mappings and unsupported semantics;
3. evaluate in-domain, cross-capture/run, and cross-dataset generalization without identity leakage;
4. preserve target-session integrity and strictly-past Observation Evidence;
5. reuse Model A as a controlled initialization and Edge replay anchor without inheriting its Evidence-State collapse;
6. use classification supervision broadly but expensive Teacher supervision sparsely and diagnostically;
7. keep unknown rejection in scope while leaving few-shot new-class registration out of the critical path.

Model A remains the immutable Edge-IIoTset single-domain reference. Its formal classification Macro-F1 is `0.9984831208`; its actual Basic-insufficient Evidence-State F1 and missing-gap micro F1 are both `0.0`. Model B must therefore preserve classification while explicitly repairing Evidence-State calibration.

## 2. Lessons from related work

- [TrafficLLM](https://arxiv.org/abs/2504.04222) motivates heterogeneous raw-traffic representation and staged adaptation rather than one dataset-specific classifier. Dataset-v4 adopts a shared outer contract but retains source-specific preprocessing and GT adapters.
- [ETooL](https://arxiv.org/abs/2505.20866) reports non-IID traffic instruction tuning and uses traffic-structure knowledge. Dataset-v4 therefore treats multi-flow temporal/relation context as first-class Evidence and evaluates domain shift explicitly.
- [NIDS-GPT / Take Package as Language](https://arxiv.org/abs/2412.04473) demonstrates packet-oriented language modeling on CICIDS2017. It supports retaining bounded packet sequences as a common representation, but does not remove the need for label-provenance validation.
- [MalRAG](https://arxiv.org/abs/2511.14129) separates content, structural, and temporal retrieval views for open-set malicious-traffic identification. Dataset-v4 retains Observation versus Knowledge separation and does not allow RAG to create missing network facts.
- [open-set TrafficLLM](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=5074974) highlights dataset-specific preprocessing and open-set evaluation across multiple encrypted-traffic datasets. Dataset-v4 pre-registers domain-held-out evaluation rather than claiming transfer from pooled IID results.
- [TrafficGPT](https://arxiv.org/abs/2403.05822) motivates longer traffic context and efficient sequence modeling. Dataset-v4 keeps bounded target sessions but exposes legal temporal/relation expansions instead of silently increasing the target unit.
- [ICT-META](https://ieeexplore.ieee.org/document/11488357) directly studies few-shot and cross-domain encrypted-traffic classification. To keep the contribution distinct, 1/5/10-shot class registration remains `OUT_OF_SCOPE`; Model B focuses on unknown rejection and active Observation-Evidence acquisition.

These works are design inputs, not evidence that their preprocessing or reported labels are automatically compatible with this project.

## 3. Dataset candidate matrix

`CONFIRMED` means supported by the linked official source or the completed local Edge audit. Every source still requires a local hash/provenance preflight before download acceptance. `TO_VERIFY` fields must not be promoted to facts from filenames or secondary mirrors.

| Dataset | Raw PCAP | Official GT form | Attack labels | Sample unit | Payload | Temporal | Relation | Known LLM-traffic use | Canonical mapping | Main risk | Recommended role | Priority |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Edge-IIoTset | CONFIRMED local, 24 PCAP/CSV pairs | companion packet/frame CSV with pure `Attack_label`/`Attack_type`; locally validated capture fallback | six accepted Model A fine labels plus excluded/stress labels | project 60s bidirectional session | CONFIRMED bounded packet-aligned v2 | CONFIRMED 10/60/180/300s past-only | CONFIRMED scoped ARP/DNS/endpoint contract | current Model A | six `EXACT`; excluded labels remain non-main | single-domain/capture coupling; Evidence-State collapse | controlled anchor, replay, regression | P0 existing |
| CICIDS2017 | [official PCAP + labeled flows/ML CSV](https://www.unb.ca/cic/datasets/ids-2017.html) | official page says flow labels use timestamp, endpoints, ports, protocol, and attack schedule | benign, brute force, DoS/DDoS, web attacks, infiltration, bot, scan, Heartbleed | official labeled flow; common 60s session mapping `TO_VERIFY` | CONFIRMED full-payload PCAP | feasible; schedule and flow timestamps available | feasible from raw PCAP; endpoint sanitation needed | NIDS-GPT; other traffic models | promising `EXACT` and `FAMILY_ONLY`; preflight required | known CSV/flow-label defects and environment shortcuts must be audited | first external domain | P1 |
| ToN-IoT | [official PCAP, Zeek logs, CSV](https://research.unsw.edu.au/projects/toniot-datasets) | heterogeneous network/Zeek, OS, telemetry labels; exact PCAP-to-row identity `TO_VERIFY` | official page confirms multiple normal/cyberattack events including DoS, DDoS, ransomware; complete source vocabulary `TO_VERIFY` | Zeek connection/flow plus raw packets; common session mapping `TO_VERIFY` | PCAP available; sanitization feasibility `TO_VERIFY` | strong multi-source potential; network-only contract required | network relation feasible; host/telemetry must remain separate capability | heterogeneous-traffic literature, specific use `TO_VERIFY` | likely family coverage; exact fine mappings pre-register | accidentally mixing host/telemetry facts into network Observation | second external domain | P1 |
| CSE-CIC-IDS2018 | [official AWS PCAP/logs/flow CSV](https://www.unb.ca/cic/datasets/ids-2018.html) | schedule + attacker/victim/IP/port/protocol labeling; CICFlowMeter biflows | brute force, Heartbleed, botnet, DoS, DDoS, web attacks, infiltration | official flow; common session mapping `TO_VERIFY` | PCAP available | feasible; daily schedules | feasible but large topology identifiers are shortcut risks | use by LLM traffic papers `TO_VERIFY` | broad overlap with CICIDS2017; exact mapping preflight | scale, AWS transfer, duplication of CIC family/environment | optional third domain after P1 gates | P2 |
| ISCX-Botnet 2014 | official page documents mixed trace construction but says [dataset no longer available](https://www.unb.ca/cic/datasets/botnet.html) | training/test composition from overlaid botnet and benign traces | many named botnets and benign | flow distribution documented; raw join semantics `TO_VERIFY` | historical traces; availability BLOCKED | long-horizon bot behavior is relevant | overlay relations may be artificial | ETooL reports ISCX-Botnet OOD | malware/C2 family, fine bot names `TO_VERIFY` | unavailable official asset; overlay artifacts | literature reference only unless lawful authoritative asset emerges | P4/BLOCKED |
| Bot-IoT | [official PCAP, Argus, CSV](https://research.unsw.edu.au/projects/bot-iot-dataset) | files separated by attack category/subcategory | DDoS, DoS, OS/service scan, keylogging, exfiltration | packet/Argus flow; identity mapping `TO_VERIFY` | 69.3 GB PCAP confirmed | feasible but extreme attack dominance | topology feasible; environment identity risk | specific LLM use `TO_VERIFY` | good family coverage, fine semantics preflight | size and severe imbalance; file-label inheritance risk | targeted compatibility pilot, not first download | P3 |
| USTC-TFC2016 | public [PCAP repository](https://github.com/yungshenglu/USTC-TFC2016) with 10 benign and 10 malware categories | class-directory/file identity; independent per-flow official GT `TO_VERIFY` | named applications and malware families | trace/file; common session GT contract `TO_VERIFY` | PCAP available | within-trace feasible | cross-host meaning uncertain | TrafficGPT/TrafficLLM-style literature uses this corpus | malware/C2 family; fine malware mapping `TO_VERIFY` | capture/file identity may be the only label source | auxiliary malware representation pilot | P3 |
| CIRA-CIC-DoHBrw-2020 | [official capture/flow dataset](https://www.unb.ca/cic/datasets/dohbrw-2020.html) | browser/tool, resolver, DoH/non-DoH and malicious tunnel scenario | non-DoH HTTPS, benign DoH, malicious DoH tools | flow/time-series; PCAP join `TO_VERIFY` | PCAP confirmed by official/publication sources | strong timing use | resolver/browser relation is possible but shortcut-prone | encrypted-traffic literature; exact LLM use `TO_VERIFY` | encrypted tunnel/exfiltration family | browser/resolver identity shortcuts; narrow task | encrypted-observation stress/auxiliary domain | P2/P3 |

Primary Dataset-v4 pilot: **Edge replay + CICIDS2017 + ToN-IoT**. CSE-CIC-IDS2018 is secondary only after it adds non-redundant capture/domain evidence. DoHBrw is a focused encrypted-observability auxiliary. Bot-IoT and USTC-TFC2016 require smaller compatibility pilots. ISCX-Botnet is blocked by official availability.

## 4. Proposed canonical taxonomy

The taxonomy has two explicit levels and never coerces a family-only source label into a false fine subtype.

| Canonical family | Candidate fine concepts | Notes |
| --- | --- | --- |
| BENIGN | Normal | source/domain-conditioned benign remains one family; domain identity is not a model feature |
| AVAILABILITY | DDoS_HTTP, DDoS_TCP, DDoS_UDP, DoS_HTTP, DoS_TCP/UDP, slow-rate DoS | exact mechanism/protocol only when official GT and observation both support it |
| RECONNAISSANCE | Port_Scanning, OS_Scanning, Service_Scanning, Vulnerability_Scanning | scan subtype may remain family-only |
| CREDENTIAL_ACCESS | Password/Brute_Force, SSH_Brute_Force, FTP_Brute_Force | protocol-specific mapping requires official semantics |
| WEB_EXPLOITATION | SQL_Injection, XSS, Command_Injection, Web_Brute_Force | application/payload observation contract required |
| MALWARE_C2 | Botnet/C2 and supported named families | named malware is source-local unless cross-source semantics are proven |
| EXFILTRATION_TUNNEL | Data_Exfiltration, malicious_DoH/tunnel | do not merge ordinary encrypted traffic with malicious tunneling |
| INFILTRATION_EXPLOIT | Infiltration, Heartbleed, supported exploit behaviors | often `FAMILY_ONLY` because network observations may not support an exact exploit label |

MITM, ransomware, upload, keylogging, and other host-semantic labels enter main fine classification only if the target network observation passes the same Full Observational Sufficiency contract. Otherwise they remain observability stress, source-local auxiliary, or unsupported.

Every mapping row uses `EXACT`, `FAMILY_ONLY`, or `UNSUPPORTED`, plus `classification_ce_eligible`, `observation_eligibility_required`, source provenance, and review status.

## 5. Source-label mapping draft

| Source | Source label examples | Draft canonical mapping | Quality | Required resolution |
| --- | --- | --- | --- | --- |
| Edge | current six Model A labels | same canonical fine labels | EXACT | frozen |
| CICIDS2017 | BENIGN, DDoS, PortScan, FTP/SSH-Patator, Web Attack-SQL Injection | BENIGN; AVAILABILITY/DDoS family; RECONNAISSANCE; protocol brute force; SQL_Injection | EXACT or FAMILY_ONLY `TO_VERIFY` | run official flow/PCAP/schedule provenance and observation audit |
| CICIDS2017 | Bot, Infiltration, Heartbleed | MALWARE_C2 or INFILTRATION_EXPLOIT | FAMILY_ONLY/UNSUPPORTED pending evidence | determine whether session-level network evidence supports fine GT |
| ToN-IoT | normal, DoS/DDoS, scanning, password/injection-like labels | corresponding family; fine mapping `TO_VERIFY` | TO_VERIFY | freeze official network-label vocabulary and distinguish network from host/telemetry labels |
| CSE-CIC-IDS2018 | FTP/SSH brute force, DoS variants, DDoS, web attacks, Bot, Infiltration, Heartbleed | family/fine candidates above | TO_VERIFY | validate daily raw assets and generated flow labels independently of filenames |
| Bot-IoT | DDoS/DoS protocol subcategories, OS/service scan, exfiltration/keylogging | AVAILABILITY, RECONNAISSANCE, EXFILTRATION_TUNNEL; keylogging likely unsupported from network alone | TO_VERIFY | packet/Argus/CSV join and observability audit |
| USTC-TFC2016 | named benign apps and malware files | source-local application or MALWARE_C2 label | FAMILY_ONLY/UNSUPPORTED | prove a session label without file identity |
| DoHBrw | non-DoH, benign DoH, dns2tcp/DNSCat2/Iodine | benign encrypted traffic or EXFILTRATION_TUNNEL | EXACT/FAMILY_ONLY `TO_VERIFY` | remove browser/resolver/tool identity shortcuts and validate flow join |

No draft mapping authorizes a download or training label.

## 6. Common Session Contract

Each accepted source emits:

```text
sample_id (opaque, stable, source-salted)
dataset_domain_backend_only
source_asset_hash_backend_only
source_record_locator_backend_only
capture/run identity_backend_only
five-tuple or source-native connection identity
session_start/session_end
initiator/responder orientation
packet_count/byte_count
source_label + canonical_family + canonical_fine_label
mapping_quality
physical_split + domain_split
exact/near identity groups
classification_ce_eligible
eligibility/exclusion reason
```

Default target unit remains a bounded bidirectional session. A 60s cap is preferred for compatibility with Model A but is not assumed universally: each source pilot must quantify native-flow boundaries, timeout semantics, truncation, and label changes. Any adapter-specific conversion to 60s must preserve packet identity and may not cross source capture, official label interval, or connection boundary without an explicit contract.

## 7. Common Evidence Contract

All sources emit the same model-visible envelope and trust/domain fields. Basic-v2 remains cheap but useful: session summary, first-eight packet metadata, first-eight packet-aligned sanitized payload, and cheap deterministic application metadata.

Observation families remain `PACKET_PAYLOAD`, `APPLICATION`, `TEMPORAL`, and `RELATION`; `KNOWLEDGE` remains non-observational. Temporal windows remain fixed and strictly past-only at 10/60/180/300 seconds when the source timeline supports them. Relation Evidence must be scoped to the target endpoints/MAC/DNS path and may never be capture-wide inheritance.

Unsupported source capabilities are explicit masks, not zero-valued fake Evidence. Every model-visible object must be reproducible from a backend locator while paths, capture names, dataset names, GT, split, and future information remain hidden.

## 8. Dataset-specific GT Adapter contract

Before any source reaches Dataset-v4, its adapter must produce a small tracked provenance manifest and a Git-external row/session evidence table.

Required gates:

1. raw asset identity and checksum;
2. official label artifact identity and checksum;
3. documented GT unit: packet, flow, time interval, host event, capture, or combination;
4. deterministic raw-record to official-label join with direct, conflict, ambiguous, and unmatched counts;
5. session aggregation rule; direct evidence must be unanimous unless official semantics explicitly authorize another rule;
6. capture fallback only when official capture purity and semantics are proven;
7. `GENERIC_BACKGROUND`, `NETWORK_UNOBSERVABLE`, `WRONG_GRANULARITY`, and `LABEL_PROPAGATION_ONLY` exclusions across train/validation/test;
8. no session crossing capture, source, official label interval, or split;
9. repeatable model-safe serialization and sample-ID locator audit;
10. fail closed when raw/label provenance is incomplete.

## 9. Leakage sanitation

- Hash/deduplicate exact model views and near signatures before assignment.
- Group source files, captures, runs, endpoints, and synthetic replay ancestry so related identities cannot cross a declared evaluation boundary.
- Strip dataset, capture, file, raw path, label, split, run, absolute host/IP identity, and future context from model input.
- Treat port, URI, protocol, and payload signatures as diagnostic behavioral shortcuts unless they encode environment identity rather than attack behavior.
- Run leave-capture/run and leave-domain probes for suspected acquisition shortcuts.
- Preserve an `EXACT_EVAL_CLEAN` view; report any `NEAR_EVAL_CLEAN` attrition rather than silently changing the test population.

## 10. Split protocol

Dataset-v4 records carry two orthogonal axes:

1. **within-domain physical split:** grouped/chronological, source-specific, no random row split;
2. **domain evaluation split:** in-domain validation/test, cross-capture/run, and held-out-domain test.

The first pilot uses Edge, CICIDS2017, and ToN-IoT train/validation/test partitions created independently before pooling. Dataset-balanced training never moves a source test record into train. Cross-dataset evaluation reports only canonical labels at a mapping quality supported by every compared source. `FAMILY_ONLY` mappings are scored at family level, not against invented fine labels. Unknown rejection sets remain isolated; Model A `U_final` is untouched.

## 11. Classification-only versus Teacher-supervised sampling

All eligible TRAIN records may supply classification CE, subject to one primary CE state per session and dataset/class-balanced weights. Teacher-v2 is not applied to the full external population.

Sparse Teacher sampling is selected before responses by source, canonical class/family, Basic sufficiency proxy, evidence-family availability, stage, capture/run diversity, and ambiguity. It targets a bounded diagnostic and training set with sufficient/insufficient balance and controlled single-/multi-gap states. Teacher does not relabel fine GT. Classification-only records receive no fabricated Evidence-State target.

Teacher budget is expanded only after a 20–50-state smoke passes schema, grounding, multi-gap, calibration, resume, and cost gates. Caches are source/prompt/schema/model-digest bound. Model A's insufficient-state collapse makes balanced negative examples and a frozen negative-control validation set mandatory.

## 12. Model A to Model B warm start

Model B begins from the immutable Model A checkpoint only after Dataset-v4 Compatibility Gate passes.

- Copy backbone/LoRA/LM Head state as an initialization, not as a claim of cross-domain competence.
- Expand the Fine Head from six to canonical K by copying rows for exact retained labels and deterministically initializing new rows. Family-only labels use a separate compatible objective or deterministic aggregation; they do not reuse an unrelated fine row.
- Train with Edge replay plus dataset-balanced and class-aware sampling. Report Edge clean-validation regression every epoch.
- Compare warm-start against at least a base-Qwen initialization under the same Dataset-v4 training budget; do not assume Model A is always superior.
- Freeze a balanced Evidence-State evaluation containing sufficient and insufficient states before Model B tuning. Model A is expected to fail this gate; Model B must show real improvement rather than only schema validity.
- Do not start RLAIF until classification retention, insufficient-state detection, missing-family prediction, and runtime action legality all pass.

## 13. Expected compute and API cost

No download sizes, session counts, tokens, or currency totals are treated as confirmed until each source inventory is complete.

The pre-download budget sheet must calculate:

```text
raw_storage = advertised_download + unpacked + 2 * working/checkpoint margin
packet_scan = total_pcap_bytes and frames per source
evidence_storage = eligible_sessions * bounded sidecar bytes
classification_SFT = selected_primary_tokens * epochs
teacher_calls = smoke + sparse_selected_states + bounded_repair_ceiling
teacher_cost = input_tokens * provider_input_rate + output_tokens * provider_output_rate
```

Resource policy: run metadata/GT compatibility pilots before full PCAP transfer; stream packet extraction; checkpoint per asset; reuse canonical packet/session derivatives; never call Teacher for records that fail deterministic observation eligibility; do not materialize combinatorial Evidence states.

## 14. Compatibility Gate

A source can enter the pilot only if all are PASS:

```text
LICENSE_AND_ACCESS
RAW_ASSET_IDENTITY
OFFICIAL_GT_UNIT_KNOWN
RAW_TO_GT_JOIN_REPRODUCIBLE
SESSION_CONTRACT_COMPATIBLE
OBSERVATION_ELIGIBILITY_FEASIBLE
PACKET_ALIGNMENT_FEASIBLE
STRICT_PAST_TEMPORAL_FEASIBLE
RELATION_SCOPE_FEASIBLE_OR_EXPLICITLY_UNAVAILABLE
CANONICAL_MAPPING_REVIEWED
LEAKAGE_SANITATION_PASS
GROUPED_CHRONOLOGICAL_SPLIT_FEASIBLE
RESOURCE_BUDGET_ACCEPTED
```

Failure of an optional Evidence capability does not automatically reject a source, but it must be represented by a capability mask. Unknown GT semantics, label-propagation-only supervision, or unresolvable identity leakage are hard failures.

## 15. Go/No-Go criteria

**GO for Dataset-v4 build** only when CICIDS2017 and ToN-IoT each pass the Compatibility Gate, the canonical overlap contains scientifically meaningful shared families/fines, source-specific splits can be frozen without identity leakage, and compute/API budgets are accepted.

**GO for Model B SFT** only after Dataset-v4 manifests pass, label maps and class indices are audited, Edge replay is present, classification and Evidence losses respect per-session weighting, and the balanced Evidence-State validation is frozen.

**NO-GO** if GT is only inferred from filenames, session aggregation is ambiguous, cross-source labels require false fine mappings, full legal Observation cannot support a main GT, held-out domain evaluation is contaminated, or Model B training cannot preserve the Edge anchor within a pre-registered tolerance.

## 16. Open questions before download

1. What exact official GT unit and join keys exist in every CICIDS2017 raw day, including known duplicate/flow-generator anomalies?
2. Which ToN-IoT network PCAPs, Zeek rows, and security-event labels have a reproducible common clock and endpoint identity? Which labels rely on host/telemetry evidence unavailable to network-only inference?
3. Which canonical fine labels have at least two independent acquisition domains, and which must remain family-only or source-local?
4. Does CSE-CIC-IDS2018 add non-redundant domain/capture diversity after CICIDS2017, enough to justify its storage and scan cost?
5. Can DoHBrw be sanitized against browser, resolver, and tool fingerprints while retaining malicious-tunnel evidence?
6. Are Bot-IoT subcategory labels packet/flow-aligned, and can its extreme imbalance be sampled without losing run diversity?
7. Is there an authoritative, legally available ISCX-Botnet asset? The official page currently says unavailable; no mirror is pre-authorized.
8. Can USTC-TFC2016 provide session-level GT independent of class-directory/file identity?
9. What balanced sufficient/insufficient distribution and minimum per-gap support should be frozen for Model B before Teacher calls?
10. What Edge replay ratio and regression tolerance preserve Model A without letting Edge dominate multi-domain learning?

## 17. Frozen scope and recommended next action

```text
MULTI_DATASET_V4_PLANNING_STATUS=PASS
PRIMARY_DATASETS=[Edge-IIoTset,CICIDS2017,ToN-IoT]
SECONDARY_DATASETS=[CSE-CIC-IDS2018,CIRA-CIC-DoHBrw-2020,Bot-IoT,USTC-TFC2016]
ISCX_BOTNET_STATUS=BLOCKED_OFFICIAL_ASSET_UNAVAILABLE
CANONICAL_TAXONOMY_STATUS=DRAFT_REQUIRES_SOURCE_PREFLIGHT
COMMON_SESSION_CONTRACT_STATUS=DESIGNED
COMMON_EVIDENCE_CONTRACT_STATUS=DESIGNED
SPARSE_TEACHER_PLAN=DESIGNED_NOT_STARTED
FEW_SHOT_STATUS=OUT_OF_SCOPE
RLAIF_STATUS=DEFERRED
DATASET_V4_BUILD_STARTED=false
MODEL_B_TRAINING_STARTED=false
TEACHER_API_CALLED=false
```

Next action is a separate, explicitly authorized **CICIDS2017 + ToN-IoT metadata/GT Compatibility Gate**. This document does not authorize download, extraction, Teacher calls, Model B training, or changes to Model A.
