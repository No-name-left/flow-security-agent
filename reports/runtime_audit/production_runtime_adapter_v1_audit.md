# Production Runtime Safe Adapter v1 Audit

Audit date: 2026-08-11

`PRODUCTION_RUNTIME_ADAPTER_STATUS=PASS`

`PRODUCTION_RUNTIME_ADAPTER_READY=true`

This is a software safety/integration audit, not a paper result. It did not call or
download Qwen, run SFT, change the Unknown algorithm, rebuild Production data, or
implement a real Supervisor API.

## Frozen interface versions

- Adapter: `production_runtime_adapter_v1`
- Evidence schema: `production_runtime_evidence_v1`
- Production schema/assets:
  `canonical_session_record_v1/edge_split_revision_v2/c4824c5ee2c41eab3ee1961e4d3e0af6669ceb033d0a2a53091ce51dec0cdc88`
- Edge paper split: `CONSTRAINED_CHRONOLOGICAL_BOUNDARY_V2`
- Initial Production view: `primary_no_service_v1`

## Boundary and capability result

`ProductionSafeAdapter` reads only the materialized v2 Parquet assets and emits
typed Runtime `EvidenceItem`, `CapabilityStatus`, `RuntimeInput`, and bound
evidence tools. Source rows use exact allow-list schemas; an extra source field is
rejected by default. Stable `sample_id`, dataset/split/K-U role, labels, source
hashes and capture references remain in a separate backend-only provenance object.
They are absent from Evidence and Traffic Expert/Supervisor prompt rendering.

| Capability | Result | Actual v1 evidence |
| --- | --- | --- |
| Initial Evidence | AVAILABLE | packets 1-8 plus complete safe session summary |
| Packet expansion | AVAILABLE_PER_SESSION | materialized packets 9-16 only; no PCAP read |
| Temporal context | AVAILABLE | materialized 60-second, strictly past-only safe statistics |
| Graph/relation context | AVAILABLE_WITH_LIMITATION | anonymous node roles and prior same-relation presence only |
| Application evidence | UNAVAILABLE | materialized store has zero rows |
| Sanitized payload | UNAVAILABLE | no frozen materialized asset |
| Knowledge RAG | UNAVAILABLE_IN_PRODUCTION_ADAPTER | no production Runtime retrieval tool is integrated |

Application/payload/RAG evidence is not fabricated. Relation hashes, previous
sample references and absolute timestamps are used only for validation and are
never emitted to a model-visible contract.

## Safety and isolation verification

- Initial packets are validated as one session, limited to 1-8, and paired with a
  required whole-session summary.
- `EXPAND_PACKETS` accepts only indices 9-16, preserves order, rejects invalid
  ranges, and associates evidence with the request signature. Runtime and the
  bound tool reject identical repeated requests.
- Temporal evidence requires `context_latest_timestamp < timestamp` when a prior
  context exists. Adapter admission also requires the frozen future-context,
  cross-split temporal and U_final leakage checks to be `PASS`.
- Graph evidence is localized and anonymized; raw node hashes and backend sample
  references are not serialized.
- The frozen Edge/IoT training manifests authorize phase access. U_final requires
  explicit formal-final-evaluation authorization and cannot enter train,
  validation, U_dev or ordinary test paths. Runtime remains read-only for U_final.
- Raw Production rows and `ProductionCatalog` objects are rejected by prompt and
  Traffic Expert boundaries; only typed `EvidenceItem` values can render.
- Model-visible validation explicitly rejects sample identity, labels, K/U role,
  split/SFT metadata, source paths/hashes, raw endpoints/payload and absolute time.
- Repeated adaptation of the same sample and versions produces byte-identical
  Runtime serialization.

## Real-data smoke

The Git-external v2 Production assets were read directly; no PCAP or model was
opened. One legal Near/train sample covered each of Normal, DDoS, scanning,
injection, malware and low-resource MITM. A real session with no past context and
one with strictly earlier context both passed. A real greater-than-eight-packet
session produced packets 1-8 initially and 9-16 on expansion with no overlap.
Application evidence returned `CAPABILITY_UNAVAILABLE`.

## Verification

- Adapter and direct integration tests: `13 passed`
- Production + Runtime + LLM backend targeted suites: `230 passed`
- Full regression: `254 passed`
- Qwen downloaded/run: `false/false`
- SFT run: `false`

## Remaining limitations

- The formal Qwen prompt/response schema, real local provider transport and model
  service are not implemented in this audit.
- Application evidence and sanitized payload require a separate parser,
  sanitizer, whitelist and materialization task.
- Current relation assets do not support invented local degree/fan-in/fan-out
  fields beyond the real materialized signals described above.
- The Parquet store supports deterministic batch prefetch; a future high-throughput
  service may add a backend key index without changing the model-safe contract.
- The Unknown algorithm remains unfrozen and no Supervisor experiment was run.

The next authorized deployment task may connect a local OpenAI-compatible Traffic
Expert backend to Runtime-rendered model-safe prompts. Qwen deployment code must
not read Production Parquet, SQLite, or PCAP directly.
