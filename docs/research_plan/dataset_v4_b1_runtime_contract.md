# Dataset-v4 B1 Observation and Runtime Contract

> Status: `SCHEMA_FROZEN / SAMPLE_MANIFEST_READY`
>
> Date: 2026-08-15
>
> Scope: DEC-0025 Dataset-v4 B1 and Model B runtime-input boundary. This document refines the B1 engineering contract without changing the canonical research route in [research_plan_detailed.md](research_plan_detailed.md).

## 1. Frozen source and observation unit

The core source is the official final processed `NF3-ToN-IoT-v3.csv` with content SHA256:

```text
53ec8f468a43ede9b1536fabc0390af2fa33ab4312b23ce4d864f186a4651f78
```

One Model B observation is exactly one complete bidirectional NF3 flow row from that CSV. It is not a packet, reconstructed session, time bucket, group, episode, or collection of rows. Temporal and Relation cards are derived context linked to this target observation; they do not change its identity.

The backend preserves:

- `source_row_index`: zero-based data-row ordinal after the header;
- `canonical_row_digest`: SHA256 of the parsed 55-column row encoded as a canonical JSON array in official header order;
- `sample_id`: SHA256 of `NF3_TON_OBSERVATION_V1`, the official CSV SHA256, decimal `source_row_index`, and `canonical_row_digest`, separated by NUL bytes as frozen in `SOURCE_ROW_ID_CONTRACT_V1`.

`sample_id` is a non-semantic routing handle. It may link cards, predictions, traces, and future cache records, but must not be embedded, tokenized as evidence, or used as a predictive feature.

## 2. Field visibility contract

The categories below define both storage permission and runtime projection. Raw backend records may retain every official column, but only `MODEL_VISIBLE` values or derived model-visible aggregates may enter a model or policy card.

### 2.1 `MODEL_VISIBLE`

The B1 Basic card contains the following 47 current-flow fields:

```text
PROTOCOL
L7_PROTO
IN_BYTES
IN_PKTS
OUT_BYTES
OUT_PKTS
TCP_FLAGS
CLIENT_TCP_FLAGS
SERVER_TCP_FLAGS
FLOW_DURATION_MILLISECONDS
DURATION_IN
DURATION_OUT
MIN_TTL
MAX_TTL
LONGEST_FLOW_PKT
SHORTEST_FLOW_PKT
MIN_IP_PKT_LEN
MAX_IP_PKT_LEN
SRC_TO_DST_SECOND_BYTES
DST_TO_SRC_SECOND_BYTES
RETRANSMITTED_IN_BYTES
RETRANSMITTED_IN_PKTS
RETRANSMITTED_OUT_BYTES
RETRANSMITTED_OUT_PKTS
SRC_TO_DST_AVG_THROUGHPUT
DST_TO_SRC_AVG_THROUGHPUT
NUM_PKTS_UP_TO_128_BYTES
NUM_PKTS_128_TO_256_BYTES
NUM_PKTS_256_TO_512_BYTES
NUM_PKTS_512_TO_1024_BYTES
NUM_PKTS_1024_TO_1514_BYTES
TCP_WIN_MAX_IN
TCP_WIN_MAX_OUT
ICMP_TYPE
ICMP_IPV4_TYPE
DNS_QUERY_ID
DNS_QUERY_TYPE
DNS_TTL_ANSWER
FTP_COMMAND_RET_CODE
SRC_TO_DST_IAT_MIN
SRC_TO_DST_IAT_MAX
SRC_TO_DST_IAT_AVG
SRC_TO_DST_IAT_STDDEV
DST_TO_SRC_IAT_MIN
DST_TO_SRC_IAT_MAX
DST_TO_SRC_IAT_AVG
DST_TO_SRC_IAT_STDDEV
```

Values are parsed under the versioned official schema, checked for finite/range-valid representation, and accompanied by explicit missing indicators where needed. Any scaling, signed-log transform, clipping, encoding, or feature selection must be versioned and fit on the legal training partition only. The earlier pilot's transform is diagnostic and is not silently promoted to the formal preprocessing contract.

### 2.2 `LOOKUP_ONLY`

These raw values may be used only inside deterministic backend grouping/history/relation builders:

```text
FLOW_START_MILLISECONDS
FLOW_END_MILLISECONDS
IPV4_SRC_ADDR
IPV4_DST_ADDR
L4_SRC_PORT
L4_DST_PORT
```

They may produce bounded aggregate counts or durations, but their literal values never enter Basic, Temporal, Relation, classifier, utility-selector, Teacher, or novelty-detector inputs.

### 2.3 `SPLIT_ONLY`

The following are stored only for identity, provenance, grouping, OOF, and split audits:

```text
source_row_index
canonical_row_digest
artifact digest and member identity
private group key / group digest
split assignment
OOF fold
Unknown rotation membership
source_dataset or source-file identity
```

They never enter a model, controller, Teacher request, threshold model, or explanation prompt.

### 2.4 `LABEL_ONLY`

```text
Label
Attack
frozen broad-label mapping
class index
Known/held-out evaluation role
correctness or recovery outcome
```

Official GT is available to offline training and evaluation according to the split/rotation protocol. It is not runtime state and is not a Teacher input.

### 2.5 `FORBIDDEN_RUNTIME`

The runtime projection must fail closed if it contains any literal `LOOKUP_ONLY`, `SPLIT_ONLY`, or `LABEL_ONLY` value, or any path, archive member, dataset name, absolute timestamp, raw address/port, attack interval, capture/day identity, future record, utility target, `recoverable_known` flag, or true-Unknown flag. Hashed identities remain metadata-only and are excluded from decision features.

## 3. Minimum Evidence families

Only `BASIC`, `TEMPORAL`, and `RELATION` are B1 core. `APPLICATION`, `PACKET_PAYLOAD`, and `KNOWLEDGE/RAG` are `OPTIONAL_NOT_B1_CORE` and require a later data-support and utility Gate.

### 3.1 BASIC

- **Available fields:** the 47 `MODEL_VISIBLE` current-row fields above plus missingness/provenance version, never raw lookup fields.
- **Derivation:** one-to-one from the completed target flow; no other row contributes.
- **Past-only requirement:** not applicable to cross-row context. The observation becomes available only when the target flow row is complete/exported.
- **Runtime cost proxy:** `0` incremental units; Basic is mandatory initial state.
- **Target linkage:** exact `sample_id`, one Basic card per observation.
- **Leakage prohibitions:** no GT, row/split/group identity, raw address/port/time, source name, or feature transform fit outside legal training data.

### 3.2 TEMPORAL

- **Available fields:** for each fixed `10 s`, `60 s`, and `300 s` horizon: prior source flow/packet/byte counts and rates; prior destination flow count; same-source last-seen gap; bounded burst/count summaries. An explicit availability/count mask is required.
- **Derivation:** deterministic aggregation of rows in the same legal history scope whose `FLOW_END_MILLISECONDS < target.FLOW_START_MILLISECONDS`. Equal-start rows, overlapping flows, future rows, and rows outside the target's split/history scope are excluded. Values are derived after split assignment and never cross split boundaries.
- **Past-only requirement:** strict; only already completed flows may contribute. A target or same-time group is staged only after all target cards have been computed.
- **Runtime cost proxy:** `1` acquisition unit for the complete versioned Temporal card; measured wall time/bytes may be logged separately and never replace the preregistered proxy silently.
- **Target linkage:** card contains the target `sample_id`, evidence version, horizon list, contributing-row count, and an input-set digest. Contributor identities remain backend-only.
- **Leakage prohibitions:** no future/concurrent flow totals, GT, attack interval, dataset/capture/day label, raw endpoint/time, held-out role, correctness, or Full-Evidence outcome.

### 3.3 RELATION

- **Available fields:** for each fixed `10 s`, `60 s`, and `300 s` horizon: source unique-destination count; source unique-destination-port count; prior same source→destination count; prior same source→destination-port count; destination fan-in/unique-source count; source bounded-neighbor count. Only aggregate values and availability masks are model-visible.
- **Derivation:** use the same strict completed-before-target history predicate as Temporal. Raw endpoints and ports form private lookup keys; the card exposes only bounded counts/statistics. No global graph embedding or absolute node identifier is B1 core.
- **Past-only requirement:** strict and split-local; equal-time, overlapping, future, and cross-split rows are excluded.
- **Runtime cost proxy:** `1` acquisition unit for the complete versioned Relation card.
- **Target linkage:** exact target `sample_id`, evidence version, horizon list, contributor count, and input-set digest; no raw node key leaves the backend.
- **Leakage prohibitions:** no raw IP/port/node ID, future edge, GT, attack schedule/interval, source identity, split/rotation role, or capture/day fingerprint.

## 4. `RUNTIME_STATE_CONTRACT_V1`

The controller/utility selector receives one versioned state:

```json
{
  "contract_version": "RUNTIME_STATE_CONTRACT_V1",
  "sample_handle": "<routing-only sample_id>",
  "current_evidence_card": {
    "BASIC": {},
    "TEMPORAL": null,
    "RELATION": null
  },
  "known_prediction_summary": {
    "class_map_version": "<version>",
    "known_class_probabilities": {"<known_class>": 0.0},
    "predicted_class": "<known_class>",
    "max_probability": 0.0,
    "top1_top2_margin": 0.0,
    "entropy": 0.0
  },
  "current_evidence_mask": {
    "BASIC": true,
    "TEMPORAL": false,
    "RELATION": false
  },
  "remaining_available_evidence": ["TEMPORAL", "RELATION"],
  "representation": null
}
```

`known_class_probabilities` must be a complete finite distribution aligned to `class_map_version`; summary scalars are recomputed rather than trusted. `remaining_available_evidence` is the intersection of backend availability, current mask, budget, and permission. `representation` is optional and may contain only a model-derived bounded summary vector or an opaque handle resolved inside the same trusted runtime. It cannot contain source identity.

The `sample_handle` is for joins/traces only and must be removed from any learned policy feature tensor or prompt evidence body. State construction fails if GT, recovery truth, true-Unknown status, future Evidence, dataset/file/split identity, raw lookup values, or hidden absolute identity is present.

## 5. `AGENT_ACTION_CONTRACT_V1`

The online Evidence-acquisition policy has exactly four actions:

| Action | Precondition | Effect | Allowed next state | Cost proxy |
| --- | --- | --- | --- | ---: |
| `STOP_AND_CLASSIFY` | Basic present; a valid Known distribution exists | emit current Known class prediction and terminate this online decision | `TERMINAL_KNOWN_CLASSIFICATION` | 0 |
| `ACQUIRE_TEMPORAL` | Temporal is available, not acquired, and budget permits | deterministic runtime materializes and validates the Temporal card, then recomputes Known prediction | `DECISION_REQUIRED` with `TEMPORAL=true` | 1 |
| `ACQUIRE_RELATION` | Relation is available, not acquired, and budget permits | deterministic runtime materializes and validates the Relation card, then recomputes Known prediction | `DECISION_REQUIRED` with `RELATION=true` | 1 |
| `ENTER_NOVELTY_DETECTION` | Basic present; no further acquisition is selected under availability/budget/utility semantics | freeze current Evidence state and submit it to the independent novelty detector | `NOVELTY_DECISION_PENDING` | 1 |

An unavailable, repeated, over-budget, or schema-invalid acquisition is rejected by Runtime and is not silently mapped to another action. `REQUEST_LABEL`, `REGISTER_NEW_CLASS`, and `TRIGGER_TRAINING` are downstream continual-control operations and are excluded from this action space.

`ENTER_NOVELTY_DETECTION` is not `PREDICT_UNKNOWN`. The independent detector returns Known-versus-Unknown after the Evidence gate. Therefore:

```text
UNKNOWN_AFTER_EVIDENCE_GATE=true
```

## 6. `TEACHER_CACHE_V1` input/output contract

The cache is authorized only as `TEACHER_SUPERVISOR_BASELINE`, `OPTIONAL_POLICY_DEMONSTRATION`, or `OPTIONAL_IMITATION_INITIALIZATION`. It is never classification GT, operational utility GT, Unknown GT, or continual/new-class GT.

The request envelope contains only:

```text
schema_version
sample_id                 # routing/audit only, not semantic evidence
current_evidence_card
known_prediction_summary
current_evidence_mask
available_next_evidence
```

The request builder must perform a leakage Gate that rejects GT/class index, backend stratum, `recoverable_known`, true-Unknown role, future/full Evidence, OOF utility target/outcome, raw lookup fields, and dataset/file/split/rotation identity.

The response is strict JSON:

```json
{
  "predicted_class": null,
  "recommended_action": "ENTER_NOVELTY_DETECTION",
  "confidence": 0.0,
  "semantic_gap": "NOVELTY_OR_UNRESOLVABLE",
  "short_reason": "<bounded reason grounded only in visible Evidence>"
}
```

`recommended_action` must be one of the four exact action names. `semantic_gap` is one of `NONE`, `NEEDS_TEMPORAL`, `NEEDS_RELATION`, `NOVELTY_OR_UNRESOLVABLE`, or `AMBIGUOUS`. For `STOP_AND_CLASSIFY`, `predicted_class` must be a current Known class and `semantic_gap=NONE`. For an acquisition action, `predicted_class` may be a tentative Known class or `null`; the corresponding Evidence must be available. For novelty entry, `predicted_class` may be `null` to abstain and must never invent a new class. `confidence` is confidence in the recommended action, lies in `[0,1]`, and is not a calibrated Known/Unknown probability.

## 7. Sampling and semantic-reference freeze boundary

The deterministic `teacher_cache_v1` design is tracked in [teacher_cache_v1_sampling_manifest_design.json](../../configs/dataset_v4/teacher_cache_v1_sampling_manifest_design.json). It freezes `N=2000`, strata, seed, group-safe meta partitions, and selection rules. DEC-0026 froze the Dataset-v4 split/taxonomy/rotations and materialized the leakage-audited list in [teacher_cache_v1_sampling_manifest.json](../../configs/dataset_v4/teacher_cache_v1_sampling_manifest.json):

```text
CACHE_SAMPLE_SELECTION_BLOCKED_BY_FINAL_SPLIT=false
TEACHER_CACHE_V1_SAMPLE_MANIFEST_READY=true
TEACHER_RESPONSES_GENERATED=false
```

The `semantic_admissibility_reference_v1` design is tracked in [semantic_admissibility_reference_v1_design.json](../../configs/dataset_v4/semantic_admissibility_reference_v1_design.json). It contains no response and never supplies operational utility.

## 8. Freeze status

```text
NF3_TON_ARTIFACT_STATUS=VERIFIED_FROZEN
OBSERVATION_UNIT_FROZEN=true
BASIC_CONTRACT_FROZEN=true
TEMPORAL_CONTRACT_FROZEN=true
RELATION_CONTRACT_FROZEN=true
RUNTIME_STATE_CONTRACT_V1=FROZEN
AGENT_ACTION_CONTRACT_V1=FROZEN
NOVELTY_ENTRY_CONTRACT_FROZEN=true
TEACHER_CACHE_V1_IO_SCHEMA_FROZEN=true
DATASET_V4_B1_STATUS=FROZEN_PASS_SAMPLE_MANIFEST_READY
```

This contract still does not authorize Model B training, DeepSeek calls, data download, or raw reprocessing. The split details are frozen separately in [dataset_v4_split_protocol.md](dataset_v4_split_protocol.md). Response generation requires an explicit researcher action; this file only records that nonleaking request inputs are ready.
