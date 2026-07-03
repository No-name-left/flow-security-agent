# PCAP-LLM RAG Knowledge Base

This RAG library supports the current session-level competition task. It is a local knowledge base, not an online search system, and it must not contain test answers or private credentials.

## Goal

RAG provides compact, source-grounded context for Qwen3.5-27B session-level classification into official competition codes:

- stage codes: `TA43`, `TA01`, `TA03`, `TA11`, `TN01`
- technique codes: `TA43_01`, `TA43_02`, `TA01_01`, `TA01_02`, `TA03_01`, `TA11_01`, `TA11_02`, `TN01_01`

Legacy labels such as `normal`, `port_scan`, `exploit`, `backdoor`, `trojan_callback`, `c2`, and `other_attack` may appear in older documents or intermediate mappings, but they are not final submission labels.

## Position in the Current Workflow

```text
PCAP
-> Zeek / tshark fallback parsing
-> sessionization / session card
-> deterministic RAG query builder
-> RAG retriever
-> session card + retrieved knowledge
-> Qwen3.5 technique_code prediction
-> deterministic stage_code mapping
-> competition CSV submission
-> human-readable analysis report
```

RAG should help interpret evidence at the session level: tool fields, signatures, protocols, attack technique boundaries, false positives, and normal traffic boundaries. It should not decide by PCAP-level aggregation or by cross-PCAP inference.

## Directory Structure

```text
rag/
├── README.md
├── knowledge/
│   ├── attack_types/          # legacy semantic attack-type docs; map carefully to official codes
│   ├── attack_stages/         # stage concepts; map carefully to official stage codes
│   ├── tool_fields/
│   ├── protocols/
│   ├── signatures/
│   ├── false_positive_rules/
│   ├── competition_decision_boundaries/ # short feature-triggered closed-set cards
│   └── aggregation_policy/    # legacy aggregation docs need session-level review
├── metadata/
├── chunks/
├── index/
├── sources/
└── reports/
```

## Knowledge Coverage

The RAG library should cover:

- official label boundaries for stage and technique codes;
- attack stages and attack techniques;
- tshark and Zeek field interpretation;
- protocol behavior for TCP, UDP, DNS, HTTP, TLS/SNI, SMB, ICMP/ICMPv6, SSH/FTP/RDP, and common ports;
- signature-family explanations for scanning, brute force, exploitation, backdoor access, malware callback, C2, and protocol anomalies;
- false-positive boundaries for weak evidence, normal browsing/business access, normal SMB/DNS/HTTP, periodic traffic, high-volume normal traffic, and low-confidence alerts;
- event/session-to-CSV auxiliary judgment rules.

Existing docs that discuss event-level or PCAP-level aggregation are legacy material and should be re-read before being used in competition prompts.

## Safety Boundary

- RAG must not contain current test answers.
- RAG must not contain expected labels or sample-id-to-label mappings.
- RAG must not contain MTA answers PDF concrete answers.
- RAG must not contain raw private PCAP paths, tokens, API keys, cookies, or credentials.
- RAG may contain general public security knowledge, field explanations, protocol behavior, source-grounded signature interpretation, and false-positive boundaries.

## Retrieval Strategy

Current baseline:

```text
deterministic query from session card
+ keyword strong recall
+ metadata weighting
+ feature-triggered confusion-boundary cards
+ top-k ordinary snippets
```

This is deliberately not embedding vector-similarity retrieval. A standard vector RAG would embed the query and each chunk, then rank chunks by cosine similarity, dot product, or another vector distance. The current retriever instead scores exact phrase hits, title/keyword/body token overlap, metadata bonuses, signature bonuses, and feature-triggered boundary document IDs.

Exact protocol names, port numbers, Zeek fields, behavior indicators, and tshark fields should remain strong keyword signals. This matters because records contain precise evidence such as `MS17-010`, `port 445`, `conn_state`, `failed_login_count`, `tls_sni`, `TA43_01`, scanner User-Agent hints, and beacon timing fields. Keyword and metadata retrieval is deterministic, auditable, offline-friendly, and aligned with the closed-set competition boundary cards. Vector or hybrid retrieval may be added later as supplemental fuzzy recall, but it is optional and not a current dependency.

Current boundary-oriented triggers prioritize these hard Phase-1 distinctions:

- `TA43_01` versus `TA43_02`: port/target fanout, failed-rate, probe-rate, and burstiness favor port scan; URI fanout, scanner User-Agent, CVE/probe paths, directory scanning, and HTTP 404 patterns favor vulnerability scan.
- `TA01_01`: require repeated authentication evidence such as `auth_attempt_group`, `failed_login_count`, `attempt_rate`, inter-attempt intervals, failure burst, credential fields, or success-after-failures hints. A single login failure is not brute force.
- `TA01_02` versus `TA03_01` versus `TA11_01`: exploit requests, upload/payload delivery, and later access to the same backdoor endpoint are separate network-side stages. PCAP evidence does not prove host persistence success.
- `TA11_02` versus `TN01_01`: periodicity alone is not C2. Fixed endpoint, small repeated payloads, regularity, DNS/SNI, suspicious ports/domains, and benign periodic hints must be weighed together.

## Main Reference Sources

Reference notes are stored under `rag/sources/`. They should point to official or public references and local rule metadata without copying full webpages, full rule bodies, answer documents, or evaluation labels.

## Current Engineering Notes

- `rag/chunks/rag_chunks.jsonl` and `rag/index/keyword_index.json` exist in the current project.
- `rag/metadata/rag_manifest.csv` and `rag/metadata/source_manifest.csv` exist in the current project.
- Future updates should add or revise documents that explicitly describe the official competition code boundaries.
- The old event-card RAG query path should be migrated to session-card query building before formal use.
