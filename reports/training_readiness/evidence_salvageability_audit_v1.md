# Class-Conditional Evidence Salvageability Audit v1

Status: `PASS_WITH_LIMITATIONS`

Dataset salvageability: `MIXED`

Staged Agent viability: `MIXED`

Current primary problem: `MIXED`

## Scope and hard boundaries

This is a deterministic, offline diagnostic over the frozen 330-primary blind sample (seed `20260812`), its existing 330/330 DeepSeek results, 329/330 valid raw-Qwen results, the 99/99 pair cache, Production v2 assets, and verified raw PCAPs. It does not estimate formal paper accuracy and does not modify the Evidence pipeline. Ground truth is backend-only and is used only after label-free observation features are extracted.

`FORMAL_CORPUS_MODIFIED=false`

`FORMAL_SFT_STARTED=false`

`DEEPSEEK_NEW_API_CALLS=0`

`QWEN_NEW_RUNS=0`

The formal corpus SHA256 remained `5b845cf9e5886e5e44fd46562135ba3eb5907de65fd8faf5d9b8777253149123`. U_final isolation was checked only through the existing isolation manifest (`status=PASS`, zero U_final counts); no U_final sample/content was read.

## Zero-cost class × payload/application availability

| class | n | raw payload | payload capability | payload visible | application | application visible | temporal visible | relation visible |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Backdoor | 30 | 0/30 (0.00%) | 0/30 (0.00%) | 0/30 (0.00%) | 0/30 (0.00%) | 0/30 (0.00%) | 5/30 (16.67%) | 2/30 (6.67%) |
| DDoS_HTTP | 30 | 18/30 (60.00%) | 18/30 (60.00%) | 0/30 (0.00%) | 18/30 (60.00%) | 5/30 (16.67%) | 7/30 (23.33%) | 8/30 (26.67%) |
| DDoS_TCP | 30 | 30/30 (100.00%) | 30/30 (100.00%) | 3/30 (10.00%) | 0/30 (0.00%) | 0/30 (0.00%) | 10/30 (33.33%) | 8/30 (26.67%) |
| MITM | 30 | 0/30 (0.00%) | 0/30 (0.00%) | 0/30 (0.00%) | 16/30 (53.33%) | 3/30 (10.00%) | 7/30 (23.33%) | 7/30 (23.33%) |
| Normal | 30 | 30/30 (100.00%) | 30/30 (100.00%) | 5/30 (16.67%) | 0/30 (0.00%) | 0/30 (0.00%) | 3/30 (10.00%) | 8/30 (26.67%) |
| Password | 30 | 24/30 (80.00%) | 24/30 (80.00%) | 7/30 (23.33%) | 24/30 (80.00%) | 5/30 (16.67%) | 5/30 (16.67%) | 4/30 (13.33%) |
| Port_Scanning | 30 | 0/30 (0.00%) | 0/30 (0.00%) | 0/30 (0.00%) | 0/30 (0.00%) | 0/30 (0.00%) | 12/30 (40.00%) | 6/30 (20.00%) |
| Ransomware | 30 | 0/30 (0.00%) | 0/30 (0.00%) | 0/30 (0.00%) | 3/30 (10.00%) | 0/30 (0.00%) | 3/30 (10.00%) | 7/30 (23.33%) |
| SQL_injection | 30 | 28/30 (93.33%) | 28/30 (93.33%) | 11/30 (36.67%) | 28/30 (93.33%) | 2/30 (6.67%) | 4/30 (13.33%) | 6/30 (20.00%) |
| Uploading | 30 | 13/30 (43.33%) | 13/30 (43.33%) | 1/30 (3.33%) | 11/30 (36.67%) | 4/30 (13.33%) | 7/30 (23.33%) | 5/30 (16.67%) |
| Vulnerability_scanner | 30 | 27/30 (90.00%) | 27/30 (90.00%) | 4/30 (13.33%) | 28/30 (93.33%) | 9/30 (30.00%) | 4/30 (13.33%) | 2/30 (6.67%) |

All 330 states have canonical Initial, Temporal, and Relation backend rows. “Raw payload” in this zero-cost table means a decodable backend raw-audit sidecar; the later RAW matrix separately counts any payload bytes observed in PCAP. “Visible” means present in that particular blind-state snapshot, not merely available to a future tool call.

## Blind Audit Cross Table

| class | stage | n | payload available | payload visible | Teacher sufficient | DeepSeek T1/T2 | Qwen T1/T2 |
|---|---|---:|---:|---:|---:|---:|---:|
| Backdoor | initial | 20 | 0 | 0 | 0/20 (0.00%) | 0/20 (0.00%) / 0/20 (0.00%) | 0/20 (0.00%) / 0/20 (0.00%) |
| Backdoor | knowledge | 4 | 0 | 0 | 0/4 (0.00%) | 0/4 (0.00%) / 0/4 (0.00%) | 0/4 (0.00%) / 0/4 (0.00%) |
| Backdoor | relation | 1 | 0 | 0 | 0/1 (0.00%) | 0/1 (0.00%) / 0/1 (0.00%) | 0/1 (0.00%) / 0/1 (0.00%) |
| Backdoor | temporal | 5 | 0 | 0 | 0/5 (0.00%) | 0/5 (0.00%) / 0/5 (0.00%) | 0/5 (0.00%) / 0/5 (0.00%) |
| DDoS_HTTP | application | 5 | 5 | 0 | 5/5 (100.00%) | 0/5 (0.00%) / 0/5 (0.00%) | 4/5 (80.00%) / 4/5 (80.00%) |
| DDoS_HTTP | initial | 6 | 2 | 0 | 0/6 (0.00%) | 0/6 (0.00%) / 0/6 (0.00%) | 0/6 (0.00%) / 0/6 (0.00%) |
| DDoS_HTTP | knowledge | 4 | 2 | 0 | 0/4 (0.00%) | 0/4 (0.00%) / 0/4 (0.00%) | 0/4 (0.00%) / 0/4 (0.00%) |
| DDoS_HTTP | packet | 2 | 2 | 0 | 0/2 (0.00%) | 0/2 (0.00%) / 0/2 (0.00%) | 0/2 (0.00%) / 0/2 (0.00%) |
| DDoS_HTTP | relation | 6 | 3 | 0 | 0/6 (0.00%) | 0/6 (0.00%) / 0/6 (0.00%) | 0/6 (0.00%) / 0/6 (0.00%) |
| DDoS_HTTP | temporal | 7 | 4 | 0 | 0/7 (0.00%) | 0/7 (0.00%) / 1/7 (14.29%) | 0/7 (0.00%) / 0/7 (0.00%) |
| DDoS_TCP | initial | 9 | 9 | 0 | 0/9 (0.00%) | 0/9 (0.00%) / 1/9 (11.11%) | 0/9 (0.00%) / 0/9 (0.00%) |
| DDoS_TCP | knowledge | 1 | 1 | 0 | 0/1 (0.00%) | 0/1 (0.00%) / 0/1 (0.00%) | 0/1 (0.00%) / 0/1 (0.00%) |
| DDoS_TCP | payload | 3 | 3 | 3 | 0/3 (0.00%) | 0/3 (0.00%) / 0/3 (0.00%) | 0/3 (0.00%) / 0/3 (0.00%) |
| DDoS_TCP | relation | 8 | 8 | 0 | 0/8 (0.00%) | 0/8 (0.00%) / 0/8 (0.00%) | 0/8 (0.00%) / 0/8 (0.00%) |
| DDoS_TCP | temporal | 9 | 9 | 0 | 5/9 (55.56%) | 0/9 (0.00%) / 6/9 (66.67%) | 0/9 (0.00%) / 0/9 (0.00%) |
| MITM | application | 3 | 0 | 0 | 0/3 (0.00%) | 0/3 (0.00%) / 0/3 (0.00%) | 0/3 (0.00%) / 0/3 (0.00%) |
| MITM | initial | 12 | 0 | 0 | 0/12 (0.00%) | 0/12 (0.00%) / 0/12 (0.00%) | 0/12 (0.00%) / 0/12 (0.00%) |
| MITM | packet | 1 | 0 | 0 | 0/1 (0.00%) | 0/1 (0.00%) / 0/1 (0.00%) | 0/1 (0.00%) / 0/1 (0.00%) |
| MITM | relation | 7 | 0 | 0 | 0/7 (0.00%) | 0/7 (0.00%) / 0/7 (0.00%) | 0/7 (0.00%) / 0/7 (0.00%) |
| MITM | temporal | 7 | 0 | 0 | 0/7 (0.00%) | 0/7 (0.00%) / 0/7 (0.00%) | 0/6 (0.00%) / 0/6 (0.00%) |
| Normal | initial | 7 | 7 | 0 | 0/7 (0.00%) | 7/7 (100.00%) / 7/7 (100.00%) | 6/7 (85.71%) / 7/7 (100.00%) |
| Normal | knowledge | 2 | 2 | 0 | 0/2 (0.00%) | 1/2 (50.00%) / 2/2 (100.00%) | 2/2 (100.00%) / 2/2 (100.00%) |
| Normal | packet | 7 | 7 | 0 | 1/7 (14.29%) | 4/7 (57.14%) / 7/7 (100.00%) | 6/7 (85.71%) / 7/7 (100.00%) |
| Normal | payload | 5 | 5 | 5 | 3/5 (60.00%) | 5/5 (100.00%) / 5/5 (100.00%) | 5/5 (100.00%) / 5/5 (100.00%) |
| Normal | relation | 8 | 8 | 0 | 0/8 (0.00%) | 8/8 (100.00%) / 8/8 (100.00%) | 8/8 (100.00%) / 8/8 (100.00%) |
| Normal | temporal | 1 | 1 | 0 | 1/1 (100.00%) | 0/1 (0.00%) / 1/1 (100.00%) | 1/1 (100.00%) / 1/1 (100.00%) |
| Password | application | 4 | 4 | 0 | 0/4 (0.00%) | 1/4 (25.00%) / 1/4 (25.00%) | 0/4 (0.00%) / 0/4 (0.00%) |
| Password | initial | 5 | 2 | 0 | 0/5 (0.00%) | 0/5 (0.00%) / 0/5 (0.00%) | 0/5 (0.00%) / 0/5 (0.00%) |
| Password | knowledge | 2 | 2 | 0 | 1/2 (50.00%) | 0/2 (0.00%) / 0/2 (0.00%) | 0/2 (0.00%) / 0/2 (0.00%) |
| Password | packet | 3 | 3 | 0 | 0/3 (0.00%) | 0/3 (0.00%) / 0/3 (0.00%) | 0/3 (0.00%) / 0/3 (0.00%) |
| Password | payload | 7 | 7 | 7 | 4/7 (57.14%) | 4/7 (57.14%) / 4/7 (57.14%) | 4/7 (57.14%) / 4/7 (57.14%) |
| Password | relation | 4 | 2 | 0 | 0/4 (0.00%) | 0/4 (0.00%) / 0/4 (0.00%) | 0/4 (0.00%) / 0/4 (0.00%) |
| Password | temporal | 5 | 4 | 0 | 0/5 (0.00%) | 0/5 (0.00%) / 0/5 (0.00%) | 0/5 (0.00%) / 0/5 (0.00%) |
| Port_Scanning | initial | 11 | 0 | 0 | 0/11 (0.00%) | 11/11 (100.00%) / 11/11 (100.00%) | 0/11 (0.00%) / 11/11 (100.00%) |
| Port_Scanning | knowledge | 3 | 0 | 0 | 0/3 (0.00%) | 3/3 (100.00%) / 3/3 (100.00%) | 0/3 (0.00%) / 3/3 (100.00%) |
| Port_Scanning | relation | 5 | 0 | 0 | 0/5 (0.00%) | 5/5 (100.00%) / 5/5 (100.00%) | 0/5 (0.00%) / 5/5 (100.00%) |
| Port_Scanning | temporal | 11 | 0 | 0 | 5/11 (45.45%) | 11/11 (100.00%) / 11/11 (100.00%) | 0/11 (0.00%) / 11/11 (100.00%) |
| Ransomware | initial | 20 | 0 | 0 | 0/20 (0.00%) | 0/20 (0.00%) / 0/20 (0.00%) | 0/20 (0.00%) / 0/20 (0.00%) |
| Ransomware | knowledge | 1 | 0 | 0 | 0/1 (0.00%) | 0/1 (0.00%) / 0/1 (0.00%) | 0/1 (0.00%) / 0/1 (0.00%) |
| Ransomware | relation | 7 | 0 | 0 | 0/7 (0.00%) | 0/7 (0.00%) / 0/7 (0.00%) | 0/7 (0.00%) / 0/7 (0.00%) |
| Ransomware | temporal | 2 | 0 | 0 | 0/2 (0.00%) | 0/2 (0.00%) / 0/2 (0.00%) | 0/2 (0.00%) / 0/2 (0.00%) |
| SQL_injection | application | 1 | 1 | 0 | 1/1 (100.00%) | 1/1 (100.00%) / 1/1 (100.00%) | 1/1 (100.00%) / 1/1 (100.00%) |
| SQL_injection | initial | 4 | 3 | 0 | 0/4 (0.00%) | 0/4 (0.00%) / 0/4 (0.00%) | 0/4 (0.00%) / 0/4 (0.00%) |
| SQL_injection | knowledge | 3 | 3 | 0 | 1/3 (33.33%) | 1/3 (33.33%) / 1/3 (33.33%) | 1/3 (33.33%) / 1/3 (33.33%) |
| SQL_injection | packet | 1 | 1 | 0 | 0/1 (0.00%) | 0/1 (0.00%) / 0/1 (0.00%) | 0/1 (0.00%) / 0/1 (0.00%) |
| SQL_injection | payload | 11 | 11 | 11 | 3/11 (27.27%) | 11/11 (100.00%) / 11/11 (100.00%) | 11/11 (100.00%) / 11/11 (100.00%) |
| SQL_injection | relation | 6 | 5 | 0 | 0/6 (0.00%) | 0/6 (0.00%) / 0/6 (0.00%) | 0/6 (0.00%) / 0/6 (0.00%) |
| SQL_injection | temporal | 4 | 4 | 0 | 0/4 (0.00%) | 0/4 (0.00%) / 0/4 (0.00%) | 0/4 (0.00%) / 0/4 (0.00%) |
| Uploading | application | 2 | 2 | 0 | 1/2 (50.00%) | 0/2 (0.00%) / 0/2 (0.00%) | 0/2 (0.00%) / 0/2 (0.00%) |
| Uploading | initial | 8 | 2 | 0 | 0/8 (0.00%) | 0/8 (0.00%) / 0/8 (0.00%) | 0/8 (0.00%) / 0/8 (0.00%) |
| Uploading | knowledge | 4 | 2 | 0 | 2/4 (50.00%) | 0/4 (0.00%) / 0/4 (0.00%) | 0/4 (0.00%) / 0/4 (0.00%) |
| Uploading | packet | 4 | 4 | 0 | 2/4 (50.00%) | 1/4 (25.00%) / 1/4 (25.00%) | 2/4 (50.00%) / 2/4 (50.00%) |
| Uploading | payload | 1 | 1 | 1 | 0/1 (0.00%) | 0/1 (0.00%) / 0/1 (0.00%) | 0/1 (0.00%) / 0/1 (0.00%) |
| Uploading | relation | 5 | 1 | 0 | 0/5 (0.00%) | 0/5 (0.00%) / 0/5 (0.00%) | 0/5 (0.00%) / 0/5 (0.00%) |
| Uploading | temporal | 6 | 1 | 0 | 0/6 (0.00%) | 0/6 (0.00%) / 0/6 (0.00%) | 0/6 (0.00%) / 0/6 (0.00%) |
| Vulnerability_scanner | application | 9 | 8 | 0 | 2/9 (22.22%) | 5/9 (55.56%) / 7/9 (77.78%) | 6/9 (66.67%) / 8/9 (88.89%) |
| Vulnerability_scanner | initial | 9 | 7 | 0 | 0/9 (0.00%) | 0/9 (0.00%) / 0/9 (0.00%) | 1/9 (11.11%) / 1/9 (11.11%) |
| Vulnerability_scanner | knowledge | 1 | 1 | 0 | 0/1 (0.00%) | 0/1 (0.00%) / 0/1 (0.00%) | 0/1 (0.00%) / 0/1 (0.00%) |
| Vulnerability_scanner | packet | 2 | 2 | 0 | 0/2 (0.00%) | 0/2 (0.00%) / 0/2 (0.00%) | 0/2 (0.00%) / 0/2 (0.00%) |
| Vulnerability_scanner | payload | 4 | 4 | 4 | 3/4 (75.00%) | 2/4 (50.00%) / 4/4 (100.00%) | 2/4 (50.00%) / 3/4 (75.00%) |
| Vulnerability_scanner | relation | 1 | 1 | 0 | 0/1 (0.00%) | 0/1 (0.00%) / 0/1 (0.00%) | 0/1 (0.00%) / 0/1 (0.00%) |
| Vulnerability_scanner | temporal | 4 | 4 | 0 | 0/4 (0.00%) | 0/4 (0.00%) / 0/4 (0.00%) | 0/4 (0.00%) / 0/4 (0.00%) |

The Payload-stage 70.97% is composition-bound: DDoS_TCP n=3, DS-T1=0, Normal n=5, DS-T1=5, Password n=7, DS-T1=4, SQL_injection n=11, DS-T1=11, Uploading n=1, DS-T1=0, Vulnerability_scanner n=4, DS-T1=2. Its 22/31 correct cases are SQL_injection 11, Normal 5, Password 4, and Vulnerability_scanner 2; DDoS_TCP contributes 0/3 and Uploading 0/1. It therefore does **not** establish generalized Payload value for Backdoor, MITM, Ransomware, DDoS_HTTP, DDoS_TCP, or Uploading.

## Exact session and context contract

- `SESSION_GROUPING_KEY=(L3, L4, sorted((IP,port),(IP,port)))`: order-normalized bidirectional endpoint/transport identity (`src/flowsec/production/core.py`, `canonical_endpoint_key`).
- `SESSION_DIRECTIONALITY=bidirectional aggregation; first observed packet fixes initiator/responder orientation`, and later packets receive relative direction (`src/flowsec/production/schema.py`, `SessionAccumulator.add`).
- `SESSION_TIMEOUT=60.0 seconds` from `configs/data/production_freeze_v1.yaml`.
- `SESSION_BOUNDARY_RULE=new session only when the same canonical key has an inter-packet idle gap >60s`; continuously active sessions may exceed 60 seconds (`src/flowsec/production/adapters.py`, `EdgeAdapter.process_capture`).
- `TEMPORAL_WINDOW_ROLE=external strict past-only 60s context`, reset per dataset/capture/split; equal-timestamp sessions are withheld until the full timestamp group is evaluated (`src/flowsec/production/manifests.py`).
- `RELATION_WINDOW_ROLE=external past-only exact communication-pair predecessor`, not part of session construction.

Therefore the current “session” is a bidirectional flow/connection-like aggregate. The 60s contextual window is **not** the session definition.

## Per-Class Evidence Coverage Matrix

| class | n | raw signal | retained | raw payload | capability | visible | relevant payload | first8 | later | app | current temporal | current relation | current snapshot | Basic-v2 | FULL | dominant failure | salvageability |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---|
| Backdoor | 30 | 0.00% | 0.00% | 6.67% | 0.00% | 0.00% | 0.00% | 0.00% | 0.00% | 0.00% | 0.00% | 0.00% | 0.00% | 0.00% | 0.00% | NETWORK_OBSERVABILITY_LIMITED | NETWORK_OBSERVABILITY_LIMITED |
| DDoS_HTTP | 30 | 60.00% | 60.00% | 60.00% | 60.00% | 0.00% | 0.00% | 0.00% | 0.00% | 0.00% | 60.00% | 0.00% | 0.00% | 0.00% | 60.00% | TEMPORAL_FEATURE_GAP | SALVAGEABLE_WITH_RICHER_EVIDENCE |
| DDoS_TCP | 30 | 100.00% | 100.00% | 100.00% | 100.00% | 10.00% | 0.00% | 0.00% | 0.00% | 0.00% | 100.00% | 0.00% | 0.00% | 0.00% | 100.00% | TEMPORAL_FEATURE_GAP | SALVAGEABLE_WITH_RICHER_EVIDENCE |
| MITM | 30 | 100.00% | 0.00% | 63.33% | 0.00% | 0.00% | 0.00% | 0.00% | 0.00% | 0.00% | 0.00% | 0.00% | 0.00% | 0.00% | 100.00% | SESSIONIZATION_LOSS | SESSIONIZATION_OR_GRANULARITY_RISK |
| Normal | 30 | 100.00% | 100.00% | 100.00% | 100.00% | 16.67% | 16.67% | 16.67% | 0.00% | 0.00% | 100.00% | 0.00% | 0.00% | 100.00% | 100.00% | APPLICATION_EXTRACTION_LOSS | SALVAGEABLE_WITH_BASIC_V2 |
| Password | 30 | 26.67% | 26.67% | 80.00% | 80.00% | 23.33% | 26.67% | 26.67% | 0.00% | 0.00% | 0.00% | 0.00% | 13.33% | 26.67% | 26.67% | NETWORK_OBSERVABILITY_LIMITED | NETWORK_OBSERVABILITY_LIMITED |
| Port_Scanning | 30 | 90.00% | 90.00% | 3.33% | 0.00% | 0.00% | 0.00% | 0.00% | 0.00% | 0.00% | 0.00% | 0.00% | 0.00% | 0.00% | 0.00% | AMBIGUOUS | SESSIONIZATION_OR_GRANULARITY_RISK |
| Ransomware | 30 | 0.00% | 0.00% | 16.67% | 0.00% | 0.00% | 0.00% | 0.00% | 0.00% | 0.00% | 0.00% | 0.00% | 0.00% | 0.00% | 0.00% | NETWORK_OBSERVABILITY_LIMITED | NETWORK_OBSERVABILITY_LIMITED |
| SQL_injection | 30 | 93.33% | 93.33% | 93.33% | 93.33% | 36.67% | 93.33% | 93.33% | 0.00% | 93.33% | 0.00% | 0.00% | 43.33% | 93.33% | 93.33% | EVIDENCE_SELECTION_LOSS | SALVAGEABLE_WITH_BASIC_V2 |
| Uploading | 30 | 6.67% | 6.67% | 43.33% | 43.33% | 3.33% | 6.67% | 6.67% | 0.00% | 0.00% | 0.00% | 0.00% | 0.00% | 6.67% | 6.67% | NETWORK_OBSERVABILITY_LIMITED | NETWORK_OBSERVABILITY_LIMITED |
| Vulnerability_scanner | 30 | 90.00% | 50.00% | 96.67% | 90.00% | 13.33% | 43.33% | 23.33% | 20.00% | 26.67% | 0.00% | 0.00% | 10.00% | 43.33% | 90.00% | EVIDENCE_SELECTION_LOSS | SALVAGEABLE_WITH_RICHER_EVIDENCE |

Raw/session coverage is from all 330 selected sessions, matched by verified PCAP identity, exact production canonical key, and frame interval. `FULL_OBSERVATIONAL` remains target-session plus legal past-only Observation; RAG is excluded. These rates are deterministic feature-audit coverage, not classifier accuracy or proof of sufficiency.

## Offline Evidence Ladder

| class | E0 | E1 | E2 | E3 | E4 | E5 | FULL | RAG potentially useful |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Backdoor | 0/30 (0.00%) | 0/30 (0.00%) | 0/30 (0.00%) | 0/30 (0.00%) | 0/30 (0.00%) | 0/30 (0.00%) | 0/30 (0.00%) | 0.00% |
| DDoS_HTTP | 0/30 (0.00%) | 0/30 (0.00%) | 0/30 (0.00%) | 0/30 (0.00%) | 18/30 (60.00%) | 18/30 (60.00%) | 18/30 (60.00%) | 60.00% |
| DDoS_TCP | 0/30 (0.00%) | 0/30 (0.00%) | 0/30 (0.00%) | 0/30 (0.00%) | 30/30 (100.00%) | 30/30 (100.00%) | 30/30 (100.00%) | 100.00% |
| MITM | 0/30 (0.00%) | 0/30 (0.00%) | 0/30 (0.00%) | 0/30 (0.00%) | 0/30 (0.00%) | 30/30 (100.00%) | 30/30 (100.00%) | 100.00% |
| Normal | 30/30 (100.00%) | 30/30 (100.00%) | 30/30 (100.00%) | 30/30 (100.00%) | 30/30 (100.00%) | 30/30 (100.00%) | 30/30 (100.00%) | 0.00% |
| Password | 0/30 (0.00%) | 8/30 (26.67%) | 8/30 (26.67%) | 8/30 (26.67%) | 8/30 (26.67%) | 8/30 (26.67%) | 8/30 (26.67%) | 0.00% |
| Port_Scanning | 0/30 (0.00%) | 0/30 (0.00%) | 0/30 (0.00%) | 0/30 (0.00%) | 0/30 (0.00%) | 0/30 (0.00%) | 0/30 (0.00%) | 0.00% |
| Ransomware | 0/30 (0.00%) | 0/30 (0.00%) | 0/30 (0.00%) | 0/30 (0.00%) | 0/30 (0.00%) | 0/30 (0.00%) | 0/30 (0.00%) | 0.00% |
| SQL_injection | 0/30 (0.00%) | 28/30 (93.33%) | 28/30 (93.33%) | 28/30 (93.33%) | 28/30 (93.33%) | 28/30 (93.33%) | 28/30 (93.33%) | 0.00% |
| Uploading | 0/30 (0.00%) | 2/30 (6.67%) | 2/30 (6.67%) | 2/30 (6.67%) | 2/30 (6.67%) | 2/30 (6.67%) | 2/30 (6.67%) | 0.00% |
| Vulnerability_scanner | 0/30 (0.00%) | 13/30 (43.33%) | 13/30 (43.33%) | 13/30 (43.33%) | 27/30 (90.00%) | 27/30 (90.00%) | 27/30 (90.00%) | 90.00% |

E0 is current Initial only; E1 adds corresponding first-8 bounded/sanitized payload and cheap deterministic application metadata; E2 adds packet/payload 9–16; E3 adds richer structured Application; E4 adds class-relevant but label-free past-only Temporal vocabulary; E5 adds relation/path signals. The ladder is simulated only—no Context-v2 asset was constructed.

## Payload location finding

`BASIC_V2_RECOMMENDED=true`, but not as a universal terminal view. First-8 payload is materially useful for SQL injection and a subset of Password/Uploading/Vulnerability sessions; later payload remains non-zero for those classes. Generic DDoS_TCP payload and random DDoS_HTTP header fragments are payload-present but not fine-class evidence. Backdoor, MITM, Port_Scanning, and Ransomware usually have no class-relevant decoded payload in the selected target sessions. First-8 metadata + corresponding bounded payload + summary + cheap app metadata is a better Basic than metadata-only Initial, while staged tools remain necessary.

## Temporal and Relation vocabulary audit

`CURRENT_TEMPORAL_FEATURES=['window_seconds', 'prior_session_count', 'unique_destination_count', 'unique_destination_service_category_count', 'same_destination_distinct_source_count', 'repeated_pair_count', 'incomplete_handshake_ratio', 'inter_session_gap', 'prior_packets', 'prior_bytes']`

`CURRENT_RELATION_FEATURES=['node_roles=current_source,target_cluster', 'repeated_relation']`

Missing Temporal vocabulary includes explicit SYN count/rate, handshake-completion counts, burstiness, HTTP request/method/URI ratios, target concentration at the relevant service, port diversity, authentication outcome sequences, and service-normalized periodicity. Missing Relation vocabulary includes destination/service fan-in/fan-out, port/path diversity, ARP identity mapping changes/conflicts, DNS answer mapping changes, and protocol/responder path changes. Low current Temporal/Relation blind accuracy therefore does not show those evidence families are useless; it shows the present vocabulary is too generic for several classes.

## Class-conditional interpretation

- **Backdoor → NETWORK_OBSERVABILITY_LIMITED.** The sampled target sessions are mostly one/two-packet incomplete TCP exchanges to a stable service; the audited raw sessions have no decoded command payload. Service-normalized periodic/C2 behavior may help, but Backdoor versus Ransomware remains a granularity/observability risk. Dominant failure: `NETWORK_OBSERVABILITY_LIMITED`; next: service-normalized temporal pattern / application decoder.
- **DDoS_HTTP → SALVAGEABLE_WITH_RICHER_EVIDENCE.** HTTP exists in a subset of full sessions, while a single request is not sufficient. The discriminating signal is HTTP-aware rate, same-target concentration, concurrency/burst, and response behavior; current Temporal omits HTTP request counts. Dominant failure: `TEMPORAL_FEATURE_GAP`; next: HTTP-aware 60s temporal.
- **DDoS_TCP → SALVAGEABLE_WITH_RICHER_EVIDENCE.** Payload is present but generic and is not a class signal. Near-unanimous incomplete SYN behavior plus extreme same-target past rate is the useful path, so this class is Temporal-first rather than Payload-first. Dominant failure: `TEMPORAL_FEATURE_GAP`; next: SYN/handshake/rate temporal.
- **MITM → SESSIONIZATION_OR_GRANULARITY_RISK.** The raw capture contains repeated ARP replies in which one MAC claims multiple protocol IPs. Those non-IP relation events are excluded from the current IP session builder, so ordinary DNS/multicast target sessions cannot inherit the mechanism without a safe relation/path view. Dominant failure: `SESSIONIZATION_LOSS`; next: ARP/DNS relation-path evidence.
- **Normal → SALVAGEABLE_WITH_BASIC_V2.** Established MQTT telemetry sessions and bounded payload provide useful benign application evidence, though capture-specific sensor text must be guarded against shortcut learning. Dominant failure: `APPLICATION_EXTRACTION_LOSS`; next: terminal or temporal consistency.
- **Password → NETWORK_OBSERVABILITY_LIMITED.** Explicit credential-form structure is network-visible in 8/30 sampled sessions. The remaining available HTTP evidence is mostly a login page/request without an observed attempt; repeated-auth/application outcomes are legitimate next evidence but are not established for every session. Dominant failure: `NETWORK_OBSERVABILITY_LIMITED`; next: payload expansion then repeated-auth temporal.
- **Port_Scanning → SESSIONIZATION_OR_GRANULARITY_RISK.** Short incomplete connections are retained but overlap TCP flooding. In the audited raw range the SYN traffic targets one destination IP:port, so classic port-diversity evidence is absent; this capture/session label needs a granularity warning rather than assumed scan semantics. Dominant failure: `AMBIGUOUS`; next: port-diversity/probe-rate temporal.
- **Ransomware → NETWORK_OBSERVABILITY_LIMITED.** Most sampled sessions are generic incomplete TCP or background name/time traffic and contain no network-visible ransomware semantics. Host-side encryption is not inferred; this remains a real network-observability/task-granularity warning. Dominant failure: `NETWORK_OBSERVABILITY_LIMITED`; next: application/payload then terminal if absent.
- **SQL_injection → SALVAGEABLE_WITH_BASIC_V2.** Sanitized SQL expression/request structure is a strong real-network positive control and is often recoverable in early bounded payload. Dominant failure: `EVIDENCE_SELECTION_LOSS`; next: payload expansion/application.
- **Uploading → NETWORK_OBSERVABILITY_LIMITED.** Payload/Application is available for a subset, but class-relevant transferred script content appears in only 2/30 sampled sessions; many targets are generic GETs or traffic to another service. Session/label granularity is the primary risk. Dominant failure: `NETWORK_OBSERVABILITY_LIMITED`; next: payload expansion/application.
- **Vulnerability_scanner → SALVAGEABLE_WITH_RICHER_EVIDENCE.** Application is often available, but explicit probe/exploit shapes are present only in a subset; strict past-only method/URI-shape diversity adds legitimate scan evidence for some remaining sessions. Dominant failure: `EVIDENCE_SELECTION_LOSS`; next: application then probe-rate temporal.

## Decision questions

1. **Does Payload 70.97% generalize?** No. It is dominated by SQL_injection/Normal plus smaller Password/Vulnerability contributions and excludes several hard classes entirely.
2. **Where do difficult classes fail?** DDoS_HTTP/DDoS_TCP are primarily feature-design/Temporal problems; MITM is a relation plus session/granularity problem; Password is payload selection plus Application/Temporal; Uploading is mixed payload/application selection and label granularity; Backdoor and especially Ransomware retain serious network-observability/granularity risk.
3. **Is Basic-v2 better?** Yes, as an initial state, because it recovers real early application/payload semantics without adding backend identity. It is not a replacement for staged acquisition.
4. **Is staged class-conditional acquisition viable?** Mixed but supported for specific classes. SQL/Password/Uploading/Vulnerability can benefit from Payload/Application, DDoS classes from Temporal, and MITM from Relation; several capture-labeled target sessions still lack a discriminating observation. RAG is potentially useful only after an Observation exists and needs protocol/threat interpretation; aggregate estimated applicability is 31.82%.
5. **Which classes remain risky under full Observation?** Backdoor and Ransomware remain the strongest real risks; MITM additionally requires a relation observation unit that retains the captured ARP/DNS mechanism. These are mixed warnings, not a global rejection of Edge-IIoTset.

## Limitations

- This is an observation-feature coverage audit, not a trained ablation; thresholds are conservative diagnostic rules and must not be reported as paper performance.
- Fine labels are verified pure-capture labels, but capture-level purity does not guarantee every reconstructed flow contains class-specific semantics. That mismatch is precisely what the per-session audit exposes.
- Existing Application/Payload sidecars are bounded and sanitized. The raw scan locates real packet positions but never makes raw identities or unsanitized payload model-visible.
- `FULL_OBSERVATIONAL` does not include host activity, synthetic evidence, future traffic, RAG, or U_final.

## Final fields

```text
EVIDENCE_SALVAGE_AUDIT_STATUS=PASS_WITH_LIMITATIONS
DATASET_SALVAGEABILITY=MIXED
STAGED_AGENT_VIABILITY=MIXED
CURRENT_PRIMARY_PROBLEM=MIXED
BASIC_V2_RECOMMENDED=true
FORMAL_CORPUS_MODIFIED=false
FORMAL_SFT_STARTED=false
DEEPSEEK_NEW_API_CALLS=0
QWEN_NEW_RUNS=0
```
