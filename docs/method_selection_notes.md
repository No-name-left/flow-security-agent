# Method Selection Notes

This note records the main places where the current pipeline intentionally differs from common default AI/RAG or traffic-classification workflows. It is meant to prevent future maintainers from treating these choices as accidents.

## RAG Retrieval

Current choice: deterministic session-card queries, keyword and metadata scoring, feature-triggered boundary cards, and ordinary top-k snippets.

Common default: embed the query and chunks, then retrieve by vector similarity such as cosine similarity or dot product.

Reason: the input is not an open-ended natural-language question. It is a structured PCAP/session record with exact high-signal tokens: protocol names, port numbers, Zeek fields, TShark fields, attack technique codes, signature names, and behavior indicators. Exact evidence such as `MS17-010`, `port 445`, `conn_state`, `failed_login_count`, `tls_sni`, or `TA43_01` should deterministically retrieve the relevant interpretation or boundary card. Keyword and metadata scoring is easier to audit, reproducible offline, has no embedding-model or vector-database dependency, and preserves closed-set competition boundaries. Vector or hybrid retrieval can still be added later as supplemental fuzzy recall, but it should not replace the deterministic triggers without a retrieval test gate.

## Parser Stack

Current choice: Zeek-first parsing, Docker Zeek fallback when available, TShark packet fallback, and a bounded TShark observable supplement. Suricata is not part of the current mainline.

Common default: use one parser only, or drive classification primarily from IDS alerts.

Reason: Zeek gives stable connection and application logs that map naturally to session cards. TShark fills packet-level gaps and supplies bounded HTTP/body/field evidence when Zeek lacks a specific observable. Suricata alerts are useful for separate alert analysis, but alert coverage and rule configuration can dominate the label, while the competition output requires closed official codes from observable PCAP evidence. Keeping Zeek/TShark as the mainline reduces dependencies and keeps every parser source visible in run summaries.

## Output Granularity

Current choice: Phase-1 defaults to one PCAP-level record and prediction per input PCAP, while still building session cards and behavior groups underneath.

Common default: classify every flow, session, or packet window independently.

Reason: the current Phase-1 answer format aligns to one result per PCAP. The pipeline still preserves scan/auth/C2 groups, candidate evidence, counter-evidence, margins, and conflict flags so the PCAP-level decision is not a blind majority vote. Session-level output remains available with `--granularity session` for debugging or future rounds.

## Technique-First Labels

Current choice: the model predicts an official `technique_code`; `stage_code` is mapped deterministically from that technique.

Common default: ask the model to generate both the stage and technique, or run separate stage and technique prompts.

Reason: the competition hierarchy is fixed. Deterministic mapping prevents impossible stage/technique pairs, reduces the model output surface, and lets Phase-1 stage submissions reuse the same technique-aware prompt path.

## Rule Priors Plus LLM Boundary Decision

Current choice: deterministic evidence profiles produce `candidate_technique_scores`, `top_rule_candidates`, support/counter-evidence, margins, and conflict flags. The LLM then performs the boundary-aware decision, except for optional high-confidence rule-direct routing under strict score, margin, strength, and conflict gates.

Common default: either a pure LLM classifier or a hard rule classifier.

Reason: PCAP evidence contains many exact but incomplete signals. Rules are good at compressing observable evidence and preventing obvious boundary errors; the LLM is better used to arbitrate ambiguous cases with retrieved boundary cards. Rule-direct routing is intentionally conservative and does not direct-normal by default, because weak attack/normal boundaries are high risk.

## Bounded Evidence

Current choice: prompts and session cards include bounded, redacted observables and summaries, not raw packet payloads, full HTTP bodies, secret header values, credentials, or extracted files.

Common default: dump as much raw context as possible into the prompt.

Reason: raw payloads create secret leakage risk, prompt-budget waste, and brittle behavior. The task can usually be supported by structured fields, redacted snippets around relevant strings, direction, timing, size, protocol, and visibility limits. The docs also preserve the network-side limitation: PCAP evidence can suggest upload, access, or callback behavior, but it cannot prove host-side persistence, execution, or account compromise.

## No Reputation Or Cross-PCAP Inference

Current choice: use only current-PCAP relationships and source-grounded general knowledge; do not use IP/domain reputation, answer tables, expected labels, or cross-PCAP conclusions.

Common default: enrich with threat intelligence, reputation, global entity history, or labels from neighboring samples.

Reason: competition data may anonymize IPs and domains, and leakage would make local validation misleading. The pipeline should classify from observable evidence inside the current record/PCAP and from safe general boundary knowledge.

## SFT And LoRA

Current choice: SFT candidates are audited, but immediate LoRA training is not recommended.

Common default: fine-tune once candidate examples exist.

Reason: current data coverage is incomplete, several classes lack reliable PCAP-level samples, many candidates are flow-only or medium confidence, and holdout leakage would damage evaluation. Training should wait for manually reviewed high-confidence coverage.

## Qwen Thinking Mode

Current choice: Qwen/vLLM requests disable chat-template thinking by default for the Phase-1 runner.

Common default: allow model reasoning text or thinking mode.

Reason: the runner requires strict JSON-like outputs and reliable parsing. Disabling thinking reduces the chance that hidden or visible reasoning text breaks the response contract. It remains configurable for experiments.

## Large-Run Routing

Current choice: conservative defaults: one API worker, all records to the LLM, no automatic resume unless requested, dry-run and small batches before large runs. `high-confidence-skip` and more workers are explicit scale-up choices.

Common default: maximize parallelism and skip obvious records immediately.

Reason: the competition VM and local vLLM service can fail under load. The pipeline records routing summaries and throughput before scale-up, and it keeps high-confidence skipping gated so convenience does not silently become a quality regression.

## Survey Result

I did not find a material mainline method choice that appears purely accidental. The deviations above either have explicit documentation, implementation gates, or both.

Open design areas remain, but they are known tradeoffs rather than unexplained choices:

- vector or hybrid RAG is optional future supplemental recall;
- Suricata remains outside the mainline unless alert-driven evaluation becomes useful;
- exploit-to-upload-to-access sequence grouping needs separate validation before it changes final record granularity;
- LoRA should wait for stronger manual data coverage.
