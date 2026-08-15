# Multi-Dataset Dataset-v4 / Model B Design

> Status: **DEC-0024 REVISED / SOURCE PREFLIGHT NOT STARTED**
>
> Date: 2026-08-15
>
> Entry evidence: Model A classification is frozen and `EVIDENCE_STATE_STATUS=FAIL`; warm start remains conditional on a matched ablation.
> Scope: design, compatibility contracts, and pre-download decisions only

## 1. Design goals

Dataset-v4 is not a concatenation of public CSV files. It is an auditable multi-domain corpus in which every source passes a dataset-specific ground-truth adapter and emits one common session, label, split, and model-safe Evidence contract.

The goals are:

1. extend attack-mechanism and acquisition-domain coverage beyond the six-class Edge controlled benchmark;
2. separate exact shared fine labels from family-only mappings and unsupported semantics;
3. evaluate in-domain, cross-capture/run, and cross-dataset generalization without identity leakage;
4. preserve target-session integrity and strictly-past Observation Evidence;
5. preserve Model A as a controlled baseline and optional replay source without assuming its LoRA is the best initialization;
6. freeze semantic-class `K0/U_dev/U_final/U_inc` roles before training and build both static and continual-stream views;
7. use classification supervision broadly but expensive Teacher supervision sparsely and only after deterministic eligibility;
8. verify operational Evidence utility with out-of-fold probes before building an Evidence Decision Head or Evidence RL;
9. support verified-feedback class registration, replay adaptation and regression-gated model releases;
10. keep few-shot as `OUT_OF_SCOPE_FOR_CORE_PLAN`.

Model A remains the immutable Edge-IIoTset single-domain reference. Its formal classification Macro-F1 is `0.9984831208`; a 3,600-record balanced frozen-Qwen linear probe reaches `0.9815630113`, while actual Basic-insufficient Evidence-State F1 and missing-gap micro F1 are both `0.0`. Dataset-v4 must test whether Qwen adds value under cross-domain/open-world/continual conditions. It must not carry Model A's Evidence-State targets forward as operational utility labels.

## 2. Related-work boundary

- Generic representation: [TrafficLLM](https://arxiv.org/abs/2504.04222) motivates heterogeneous raw-traffic representation and staged adaptation. Dataset-v4 therefore evaluates Qwen as a shared representation, not as a claim that LLM traffic classification is new.
- Non-IID structure: [ETooL](https://arxiv.org/abs/2505.20866) studies traffic-structure-aware LLM tuning under distribution shift. Temporal/relation context and cross-domain evaluation are therefore mandatory comparisons.
- GPT-style traffic classification: [NIDS-GPT / Take Package as Language](https://arxiv.org/abs/2412.04473) directly applies a GPT-style packet model to CICIDS2017. Closed-set packet classification is prior art, not this project's primary contribution.
- Open-set traffic: [open-set TrafficLLM](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=5074974), [RoNeTC](https://ieeexplore.ieee.org/document/10900396) and [Facing Unknown](https://arxiv.org/abs/2308.16861) motivate strong Unknown baselines rather than an untested K+1 head.
- Open-world/continual traffic: [OWETC](https://ieeexplore.ieee.org/document/10491883) and [SOUL](https://arxiv.org/abs/2412.00911) show that replay, class-incremental learning and open-world intrusion handling are established research areas. Our boundary is a verified-feedback, regression-gated LLM traffic Agent rather than the first continual traffic classifier.
- Few-shot: [ICT-META](https://ieeexplore.ieee.org/document/11488357) covers few-shot and cross-domain encrypted traffic; 1/5/10-shot remains outside the core plan.
- Self-evolving Agent RL: [WebRL](https://openreview.net/forum?id=oVKEAFjEqv) is a mechanism reference for policy learning, but web rewards are more directly verifiable. Security-traffic reward is delayed, sparse and noisy, so WebRL cannot be copied as an execution recipe.

These works are design inputs, not evidence that their preprocessing or reported labels are automatically compatible with this project.

## 3. Dataset candidate matrix

`CONFIRMED` means supported by the linked official source or the completed local Edge audit. Every source still requires a local hash/provenance preflight before download acceptance. `TO_VERIFY` fields must not be promoted to facts from filenames or secondary mirrors.

| Dataset | Raw PCAP | Official GT form | Attack labels | Sample unit | Payload | Temporal | Relation | Known LLM-traffic use | Canonical mapping | Main risk | Recommended role | Priority |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Edge-IIoTset | CONFIRMED local, 24 PCAP/CSV pairs | companion packet/frame CSV with pure `Attack_label`/`Attack_type`; locally validated capture fallback | six accepted Model A fine labels plus excluded/stress labels | project 60s bidirectional session | CONFIRMED bounded packet-aligned v2 | CONFIRMED 10/60/180/300s past-only | CONFIRMED scoped ARP/DNS/endpoint contract | current Model A | six `EXACT`; excluded labels remain non-main | single-domain/capture coupling; Evidence-State collapse | legacy controlled domain, baseline, optional replay | P0 existing |
| CICIDS2017 | [official PCAP + labeled flows/ML CSV](https://www.unb.ca/cic/datasets/ids-2017.html) | official page says flow labels use timestamp, endpoints, ports, protocol, and attack schedule | benign, brute force, DoS/DDoS, web attacks, infiltration, bot, scan, Heartbleed | official labeled flow; common 60s session mapping `TO_VERIFY` | CONFIRMED full-payload PCAP | feasible; schedule and flow timestamps available | feasible from raw PCAP; endpoint sanitation needed | NIDS-GPT; other traffic models | promising `EXACT` and `FAMILY_ONLY`; preflight required | known CSV/flow-label defects and environment shortcuts must be audited | first external domain | P1 |
| ToN-IoT | [official PCAP, Zeek logs, CSV](https://research.unsw.edu.au/projects/toniot-datasets) | heterogeneous network/Zeek, OS, telemetry labels; exact PCAP-to-row identity `TO_VERIFY` | official page confirms multiple normal/cyberattack events including DoS, DDoS, ransomware; complete source vocabulary `TO_VERIFY` | Zeek connection/flow plus raw packets; common session mapping `TO_VERIFY` | PCAP available; sanitization feasibility `TO_VERIFY` | strong multi-source potential; network-only contract required | network relation feasible; host/telemetry must remain separate capability | heterogeneous-traffic literature, specific use `TO_VERIFY` | likely family coverage; exact fine mappings pre-register | accidentally mixing host/telemetry facts into network Observation | second external domain | P1 |
| CSE-CIC-IDS2018 | [official AWS PCAP/logs/flow CSV](https://www.unb.ca/cic/datasets/ids-2018.html) | schedule + attacker/victim/IP/port/protocol labeling; CICFlowMeter biflows | brute force, Heartbleed, botnet, DoS, DDoS, web attacks, infiltration | official flow; common session mapping `TO_VERIFY` | PCAP available | feasible; daily schedules | feasible but large topology identifiers are shortcut risks | use by LLM traffic papers `TO_VERIFY` | broad overlap with CICIDS2017; exact mapping preflight | scale, AWS transfer, duplication of CIC family/environment | primary compatibility candidate; final inclusion remains gated | P1 |
| UNSW-NB15 | official raw/flow availability and event provenance `TO_VERIFY` | source flow/label artifacts; raw-to-project-session join `TO_VERIFY` | benign and multiple malicious families | source flow/session semantics `TO_VERIFY` | `TO_VERIFY` | `TO_VERIFY` | `TO_VERIFY` | widely used NIDS baseline | likely family-only plus selected exact mapping | legacy feature/capture identity and session compatibility | fallback/gap-filling only | P3 |
| ISCX-Botnet 2014 | official page documents mixed trace construction but says [dataset no longer available](https://www.unb.ca/cic/datasets/botnet.html) | training/test composition from overlaid botnet and benign traces | many named botnets and benign | flow distribution documented; raw join semantics `TO_VERIFY` | historical traces; availability BLOCKED | long-horizon bot behavior is relevant | overlay relations may be artificial | ETooL reports ISCX-Botnet OOD | malware/C2 family, fine bot names `TO_VERIFY` | unavailable official asset; overlay artifacts | literature reference only unless lawful authoritative asset emerges | P4/BLOCKED |
| Bot-IoT | [official PCAP, Argus, CSV](https://research.unsw.edu.au/projects/bot-iot-dataset) | files separated by attack category/subcategory | DDoS, DoS, OS/service scan, keylogging, exfiltration | packet/Argus flow; identity mapping `TO_VERIFY` | 69.3 GB PCAP confirmed | feasible but extreme attack dominance | topology feasible; environment identity risk | specific LLM use `TO_VERIFY` | good family coverage, fine semantics preflight | size and severe imbalance; file-label inheritance risk | targeted compatibility pilot, not first download | P3 |
| USTC-TFC2016 | public [PCAP repository](https://github.com/yungshenglu/USTC-TFC2016) with 10 benign and 10 malware categories | class-directory/file identity; independent per-flow official GT `TO_VERIFY` | named applications and malware families | trace/file; common session GT contract `TO_VERIFY` | PCAP available | within-trace feasible | cross-host meaning uncertain | TrafficGPT/TrafficLLM-style literature uses this corpus | malware/C2 family; fine malware mapping `TO_VERIFY` | capture/file identity may be the only label source | auxiliary malware representation pilot | P3 |
| CIRA-CIC-DoHBrw-2020 | [official capture/flow dataset](https://www.unb.ca/cic/datasets/dohbrw-2020.html) | browser/tool, resolver, DoH/non-DoH and malicious tunnel scenario | non-DoH HTTPS, benign DoH, malicious DoH tools | flow/time-series; PCAP join `TO_VERIFY` | PCAP confirmed by official/publication sources | strong timing use | resolver/browser relation is possible but shortcut-prone | encrypted-traffic literature; exact LLM use `TO_VERIFY` | encrypted tunnel/exfiltration family | browser/resolver identity shortcuts; narrow task | encrypted-observation stress/auxiliary domain | P2/P3 |

Primary source preflight: **CICIDS2017 + CSE-CIC-IDS2018 + ToN-IoT**, with **Edge-IIoTset-clean** as the legacy controlled reference. Passing preflight does not require all three external candidates to enter the final build. Bot-IoT, UNSW-NB15, DoHBrw and USTC-TFC2016 are fallback/gap-filling candidates. ISCX-Botnet remains blocked by official availability.

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

Dataset-v4 records carry three orthogonal axes:

1. **within-domain physical split:** grouped/chronological, source-specific, no random row split;
2. **domain evaluation split:** in-domain validation/test, cross-capture/run, and held-out-domain test;
3. **continual stream stage:** `t0` K0/domain foundation followed by ordered drift and first appearances of `U_inc_t`, with future GT hidden.

Each source creates independent partitions before pooling. Dataset-balanced training never moves a source test record into train. Cross-dataset evaluation reports only canonical labels at a mapping quality supported by every compared source. `FAMILY_ONLY` mappings are scored at family level, not against invented fine labels. Unknown partitions are frozen by canonical semantic class across all sources: `K0`, `U_dev`, sealed `U_final`, and staged `U_inc_1...n`. Model A `U_final` remains untouched.

## 11. Classification-only versus Teacher-supervised sampling

All eligible TRAIN records may supply classification CE, subject to one primary CE state per session and dataset/class-balanced weights. Teacher-v2 is not applied to the full external population.

Sparse Teacher sampling, if still justified, is selected before responses by source, canonical class/family, evidence-family availability, stage, capture/run diversity, and ambiguity. Teacher provides semantic review, not operational utility labels. Operational utility comes from OOF/cross-fitted classifiers that did not train on the evaluated sample. Classification-only records receive no fabricated Evidence-State target.

Teacher budget is expanded only after a 20–50-state smoke passes schema, grounding, multi-gap, calibration, resume, and cost gates. Caches are source/prompt/schema/model-digest bound. Model A's insufficient-state collapse makes balanced negative examples and a frozen negative-control validation set mandatory.

## 12. Model A to Model B0 warm-start ablation

Model A initialization is not the default. After source compatibility, run a matched short pilot: base Qwen + fresh LoRA versus Model A LoRA warm start, with the same data, steps, learning rate, heads and evaluation.

- Copy Model A LoRA only in the warm-start arm; base Qwen remains identical and frozen in both arms.
- Expand the Fine Head from six to canonical K by copying rows for exact retained labels and deterministically initializing new rows. Family-only labels use a separate compatible objective or deterministic aggregation; they do not reuse an unrelated fine row.
- Train with Edge replay plus dataset-balanced and class-aware sampling. Report Edge clean-validation regression every epoch.
- Select warm start only if it improves convergence or legal validation without Evidence/Unknown bias and passes Edge regression.
- Do not inherit Model A generative Evidence-State targets as utility supervision. Any future Evidence Decision Head requires the separate Utility Gate below.

## 12.1 Evidence Utility Gate

Before full Teacher labeling, Evidence Decision Head work or Evidence RL, use hundreds of representative sessions to compare `Basic` against `Basic + one legal Evidence family`. Extract frozen representations once and evaluate with stratified 5-fold OOF probes or equivalent cross-fitting; no sample may be assigned utility by a probe trained on that sample.

Report accuracy/Macro-F1 delta, cross-entropy delta, correctness flip and confidence change by class/subset. Active Evidence proceeds only if at least one family produces stable, repeatable gains on a meaningful difficult subset, its bootstrap interval does not materially center across zero, and a second seed/reference model agrees in direction. Thresholds and cost coefficient are frozen after the pilot, not invented here.

## 12.2 Hidden oracle and continual stream

The stream introduces domain drift and `U_inc_t` classes over ordered stages. Dataset GT remains hidden until `REQUEST_ANALYST_FEEDBACK`, which simulates delayed analyst/sandbox/threat-intelligence confirmation. The Unknown Buffer stores representation, scores, Evidence, stage and feedback status. Class registration requires multiple consistent verified labels; cluster tightness or model confidence is never GT.

Incremental updates are periodic batches of verified new-class samples plus balanced old-class replay. They update heads and, when justified, LoRA; base Qwen remains frozen. Every `B_t -> B_{t+1}` candidate must pass old-class, new-class, Unknown and cross-domain regression or roll back.

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

**GO for Dataset-v4 build** only after the primary candidates have individual source outcomes, at least two scientifically meaningful external domains pass or pass with bounded limitations, the canonical overlap/coverage supports K0 and held-out semantic classes, source-specific static/stream splits can be frozen without identity leakage, and compute/API budgets are accepted. The final source set may contain fewer than all three primary candidates.

**GO for Model B0 SFT** only after Dataset-v4 manifests pass, label maps/class indices are audited, the fresh-vs-warm-start experiment is registered, replay is available if Model A is used, and classification/family/fine loss masks and weights are verified. Evidence loss is optional and must not use Teacher sufficiency as operational utility.

**NO-GO** if GT is only inferred from filenames, session aggregation is ambiguous, cross-source labels require false fine mappings, full legal Observation cannot support a main GT, held-out domain evaluation is contaminated, or Model B training cannot preserve the Edge anchor within a pre-registered tolerance.

## 16. Open questions before download

1. What exact official GT unit and join keys exist in every CICIDS2017 raw day, including known duplicate/flow-generator anomalies?
2. Which ToN-IoT network PCAPs, Zeek rows, and security-event labels have a reproducible common clock and endpoint identity? Which labels rely on host/telemetry evidence unavailable to network-only inference?
3. Which canonical fine labels have at least two independent acquisition domains, and which must remain family-only or source-local?
4. Does CSE-CIC-IDS2018 add non-redundant domain/capture diversity beyond CICIDS2017, enough to justify its storage and scan cost?
5. Can DoHBrw be sanitized against browser, resolver, and tool fingerprints while retaining malicious-tunnel evidence?
6. Are Bot-IoT subcategory labels packet/flow-aligned, and can its extreme imbalance be sampled without losing run diversity?
7. Is there an authoritative, legally available ISCX-Botnet asset? The official page currently says unavailable; no mirror is pre-authorized.
8. Can USTC-TFC2016 provide session-level GT independent of class-directory/file identity?
9. Which class/subset shows reproducible OOF operational gain from each additional Evidence family?
10. Does Model A warm start outperform fresh LoRA under an equal pilot budget, and what replay/regression tolerance is needed if selected?
11. Which canonical classes become K0, U_dev, sealed U_final and U_inc stages without cross-dataset synonym leakage?

## 17. Frozen scope and recommended next action

```text
MULTI_DATASET_V4_PLANNING_STATUS=REVISED_PASS
PRIMARY_PREFLIGHT_DATASETS=[CICIDS2017,CSE-CIC-IDS2018,ToN-IoT]
LEGACY_DATASET=[Edge-IIoTset-clean]
FALLBACK_DATASETS=[Bot-IoT,UNSW-NB15,CIRA-CIC-DoHBrw-2020,USTC-TFC2016]
ISCX_BOTNET_STATUS=BLOCKED_OFFICIAL_ASSET_UNAVAILABLE
CANONICAL_TAXONOMY_STATUS=DRAFT_REQUIRES_SOURCE_PREFLIGHT
COMMON_SESSION_CONTRACT_STATUS=DESIGNED
COMMON_EVIDENCE_CONTRACT_STATUS=DESIGNED
SPARSE_TEACHER_PLAN=DESIGNED_NOT_STARTED
EVIDENCE_UTILITY_GATE_STATUS=NOT_RUN
ACTIVE_EVIDENCE_STATUS=PROVISIONAL_PENDING_GATE
UNKNOWN_PROTOCOL_STATUS=DESIGNED_NOT_RUN
CONTINUAL_STREAM_STATUS=DESIGNED_NOT_BUILT
MODEL_A_WARM_START_STATUS=PROVISIONAL_PENDING_ABLATION
FEW_SHOT_STATUS=OUT_OF_SCOPE
RLAIF_OLD_STATUS=DOWNGRADED
DATASET_V4_BUILD_STARTED=false
MODEL_B0_TRAINING_STARTED=false
TEACHER_API_CALLED=false
```

Next action is a separately authorized metadata/small-asset Source Compatibility Preflight for CICIDS2017, CSE-CIC-IDS2018 and ToN-IoT, plus a bounded Evidence Utility Pilot design. This document does not authorize full download, extraction, Teacher calls, Model B0 training, RL, U_final access or changes to Model A.
