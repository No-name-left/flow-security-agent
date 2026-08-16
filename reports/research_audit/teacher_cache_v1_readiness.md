# Dataset-v4 B1 and Teacher Cache v1 Readiness

> Audit date: 2026-08-15
>
> Repository baseline: `main@b0b4ed40b3bd11d88555a192d57ed09e52007cdb`
>
> Scope: static filesystem/cache verification, B1 contract freeze, and operational-document conflict cleanup only. No API, model, training, data download, sample materialization, or Teacher-response generation was performed.
>
> Historical snapshot: its final-split blocker was resolved by DEC-0026 on
> 2026-08-16. Current status is recorded in
> [dataset_v4_final_split_report.md](../dataset_v4/dataset_v4_final_split_report.md);
> the original precondition findings below are intentionally preserved.

## 1. Result

```text
DATASET_V4_B1_STATUS=SCHEMA_FROZEN_SAMPLE_MANIFEST_BLOCKED_BY_FINAL_SPLIT
NF3_TON_ARTIFACT_STATUS=VERIFIED_FROZEN
OBSERVATION_UNIT_FROZEN=true
BASIC_CONTRACT_FROZEN=true
TEMPORAL_CONTRACT_FROZEN=true
RELATION_CONTRACT_FROZEN=true
RUNTIME_STATE_CONTRACT_V1=FROZEN
AGENT_ACTION_CONTRACT_V1=FROZEN
NOVELTY_ENTRY_CONTRACT_FROZEN=true
EXISTING_TEACHER_CACHE_REUSABLE=false
TEACHER_CACHE_V1_IO_SCHEMA_FROZEN=true
TEACHER_CACHE_V1_TARGET_N=2000
TEACHER_CACHE_V1_SAMPLING_PLAN_STATUS=DESIGN_FROZEN_SAMPLE_LIST_NOT_GENERATED
CACHE_SAMPLE_SELECTION_BLOCKED_BY_FINAL_SPLIT=true
SEMANTIC_REFERENCE_V1_STATUS=DESIGN_FROZEN_NO_RESPONSES
SEMANTIC_REFERENCE_TARGET_N=63
NONCANONICAL_CONFLICTS_FOUND=6
NONCANONICAL_CONFLICTS_RESOLVED=6
LEGACY_TEACHER_PATHS_MARKED_DEPRECATED=true
DEEPSEEK_CALLS_REQUIRED_NOW=false
TEACHER_CACHE_V1_READY_TO_GENERATE=false
SEMANTIC_REFERENCE_V1_READY_TO_GENERATE=true
MODEL_B_INPUT_CONTRACT_READY=true
NEXT_ACTION=FINALIZE_DATASET_V4_SPLIT_THEN_GENERATE_TEACHER_CACHE
```

`MODEL_B_INPUT_CONTRACT_READY=true` means the legal input/action schema is ready for implementation. It does not mean formal Dataset-v4 rows, a final split, Model B, or paid Teacher outputs exist.

## 2. Existing cache inventory

The audit searched the repository plus the accessible Git-external `processed/` and `experiments/` roots for DeepSeek responses, Teacher annotations, Supervisor labels, policy demonstrations, semantic reviews, RLAIF/preferences, and Evidence-State outputs. The following response-bearing stores exist:

| Store | Files/records on disk | Valid logical result | Schema | Model B reuse |
| --- | ---: | ---: | --- | --- |
| `/root/autodl-tmp/processed/near_pretraining_v1/teacher_annotations/pilot/{records,cache}` | 252 + 252 | historical pilot; stale retries retained | `TEACHER_PROMPT_V2`: `evidence_sufficient`, `missing_evidence`, `gap_type`, support/summary/confidence | `LEGACY_REFERENCE_ONLY` |
| `/root/autodl-tmp/processed/near_pretraining_v1/teacher_annotations/bulk/{records,cache}` | 23,023 + 23,023; quarantine 2 | superseded historical bulk | same Model A V2 schema | `LEGACY_REFERENCE_ONLY` |
| `/root/autodl-tmp/processed/near_pretraining_v1/teacher_annotations/v3/pilot/{records,cache}` | 250 + 250 | 250/250 valid | `TEACHER_PROMPT_V3`: Model A Evidence-State fields | `LEGACY_REFERENCE_ONLY` |
| `/root/autodl-tmp/processed/near_pretraining_v1/teacher_annotations/v3/bulk/{records,cache}` | 22,957 + 22,957 | 22,957/22,957 valid | `TEACHER_PROMPT_V3`: Model A Evidence-State fields | `LEGACY_REFERENCE_ONLY` |
| `/root/autodl-tmp/processed/teacher_v2_observable_dataset_v3/annotations/diagnostic/{records,cache}` | 10 + 10 | 10/10 valid | `EVIDENCE_STATE_SCHEMA_V2` | `LEGACY_REFERENCE_ONLY` |
| `/root/autodl-tmp/processed/teacher_v2_observable_dataset_v3/annotations/pilot/{records,cache}` | 40 + 40 | 40/40 valid | Teacher-v2: adds `primary_gap`, multi-gap, `recoverability` | `LEGACY_REFERENCE_ONLY` |
| `/root/autodl-tmp/processed/teacher_v2_observable_dataset_v3/annotations/bulk/{records,cache}` | 20,807 + 20,807 | 20,807/20,807 valid | Teacher-v2 `EVIDENCE_STATE_SCHEMA_V2` | `LEGACY_REFERENCE_ONLY` |
| `/root/autodl-tmp/experiments/blind_sufficiency_calibration_v1/deepseek/records` | 330 | 330/330 valid; 332 requests including repair | blind top-1/top-2 classification/confidence/basis | `LEGACY_CALIBRATION_REFERENCE_ONLY` |
| `/root/autodl-tmp/experiments/blind_sufficiency_calibration_v1/pairs/deepseek/records` | 197 | 99/99 complete pairs; 529 total audit requests including primary | same blind-classification schema | `LEGACY_CALIBRATION_REFERENCE_ONLY` |

The Teacher annotation roots contain `67,339` response records and the same number of validated-cache files; the blind DeepSeek stores add `527` response records. Counts include superseded versions/stale retry products and must not be summed as a new training population.

Additional Evidence-State-bearing artifacts exist as completed Model A corpora:

- `near_pretraining_v1/sft_corpus/final/near_sft_corpus_v2.jsonl`: 22,957 records;
- `near_pretraining_v3/sft_corpus/final/observable_sft_corpus_v3.jsonl`: 14,350 records over 11,958 sessions;
- `teacher_v2_snapshot_universe.jsonl`: 20,807 pre-Teacher states.

No realized Model B Supervisor-label cache, four-action policy-demonstration cache, semantic-admissibility response cache, RLAIF preference/reward response set, or `teacher_cache_v1` sample/response store was found. The historical 6,000-record RL prompt pool contains prompts, not preferences or Judge responses.

### Reuse decision

```text
EXISTING_TEACHER_CACHE_FILES=MODEL_A_TEACHER_V2_V3;MODEL_A_TEACHER_V2_OBSERVABLE;BLIND_CALIBRATION
EXISTING_CACHE_RECORD_COUNTS=TEACHER_RESPONSE_RECORD_FILES_67339;BLIND_DEEPSEEK_RECORD_FILES_527;V3_VALID_22957;TEACHER_V2_VALID_20807;BLIND_PRIMARY_VALID_330;PAIR_VALID_99
EXISTING_CACHE_SCHEMA=MODEL_A_EVIDENCE_STATE_AND_BLIND_CLASSIFICATION_NOT_MODEL_B_FOUR_ACTION
EXISTING_CACHE_REUSABLE_FOR_MODEL_B=false
```

The population, evidence cards, prompt digests, class taxonomy, and action vocabulary do not match Model B. In particular, `evidence_sufficient`, `missing_evidence`, `primary_gap`, and `recoverability` are `LEGACY_REFERENCE`; they cannot be operational utility, classification, Unknown, or continual GT. Preserving and checksumming the old stores is useful; importing their labels into Model B is prohibited.

## 3. NF3-ToN identity and observation freeze

The official CSV member was streamed from the already-present archive and independently hashed:

```text
NF3-ToN-IoT-v3.csv SHA256
53ec8f468a43ede9b1536fabc0390af2fa33ab4312b23ce4d864f186a4651f78
```

No data was downloaded or extracted into a new formal asset. The B1 contract freezes one official complete bidirectional flow row as one observation. Backend identity uses source-row ordinal plus a canonical-row digest bound to the artifact hash. The stable `sample_id` is routing/provenance metadata and is never a predictive feature.

The exact 47 model-visible current-flow fields and the `LOOKUP_ONLY`, `SPLIT_ONLY`, `LABEL_ONLY`, and `FORBIDDEN_RUNTIME` projections are frozen in:

- [dataset_v4_b1_runtime_contract.md](../../docs/research_plan/dataset_v4_b1_runtime_contract.md);
- [nf3_ton_b1_runtime_contract_v1.json](../../configs/dataset_v4/nf3_ton_b1_runtime_contract_v1.json).

Raw IPs, ports, and absolute timestamps may only support private grouping/history/relation lookup. They, official GT, dataset/file identity, split/rotation role, and future records cannot enter a model, controller, novelty detector, or Teacher request.

## 4. Evidence, runtime state, and actions

Only `BASIC`, `TEMPORAL`, and `RELATION` are B1 core. Application, Payload, and Knowledge/RAG remain optional.

- Basic is the completed target row's 47 safe fields and missingness only, at incremental cost `0`.
- Temporal uses fixed 10/60/300-second, split-local aggregates from contributors satisfying `contributor.end < target.start`, at cost `1`.
- Relation uses raw endpoints/ports only as private lookup keys over that same strict history; only bounded aggregate fan-in/fan-out/repetition/diversity counts leave the backend, at cost `1`.

The strict end-before-start predicate is intentionally safer than the earlier bounded pilot, which excluded equal start timestamps but was only diagnostic. Formal builders must implement the frozen predicate rather than cite pilot output as a completed B1 asset.

`RUNTIME_STATE_CONTRACT_V1` contains the current Evidence card, aligned Known probabilities/prediction/max/margin/entropy, Evidence mask, remaining availability, and optional model-derived representation summary/opaque handle. GT, recoverability truth, true-Unknown status, future Evidence, and absolute identity are rejected.

`AGENT_ACTION_CONTRACT_V1` has exactly:

```text
STOP_AND_CLASSIFY
ACQUIRE_TEMPORAL
ACQUIRE_RELATION
ENTER_NOVELTY_DETECTION
```

The last action submits the current state to an independent novelty detector; it does not assert Unknown. `REQUEST_LABEL`, `REGISTER_NEW_CLASS`, and training triggers belong downstream and are not online acquisition actions.

## 5. Teacher Cache v1 readiness

The I/O schema is frozen and uses a legal subset of the runtime state. Output action names are exactly the four runtime names; arbitrary `STOP`/`GET_*` aliases are rejected. `predicted_class` is a Known class or `null`, with explicit abstention rules. The only authorized roles are optional Supervisor baseline, policy demonstration, and imitation initialization.

The deterministic [sampling design](../../configs/dataset_v4/teacher_cache_v1_sampling_manifest_design.json) freezes:

| Stratum | Total | Policy-demo development | Policy meta-evaluation |
| --- | ---: | ---: | ---: |
| `BASIC_SUFFICIENT_KNOWN` | 750 | 450 | 300 |
| `RECOVERABLE_KNOWN` | 850 | 510 | 340 |
| `TRUE_UNKNOWN_ROTATIONS` | 400 | 240 | 160 |
| **Total** | **2,000** | **1,200** | **800** |

Within each stratum/subpartition, selection is deterministic and balanced by eligible core class or held-out development rotation and OOF Basic confidence bins `[0,.4)`, `[.4,.7)`, `[.7,1]`. Groups cannot cross demo/evaluation partitions. Teacher and empirical utility selectors are compared on the same 800 policy meta-evaluation rows; optional imitation may use only the 1,200 development rows.

The actual final Dataset-v4 split, final taxonomy, development Unknown rotations, and OOF confidence provenance are not frozen. Consequently there is no legal population from which to emit `sample_id`s, and the design intentionally contains `output_sample_list=null`.

## 6. Semantic admissibility reference

[semantic_admissibility_reference_v1_design.json](../../configs/dataset_v4/semantic_admissibility_reference_v1_design.json) freezes a 63-cell design: seven current candidate class/mechanism keys × Basic/Temporal/Relation × mechanism-relevant, ambiguous/confounded, and weak/absent/contradictory pattern roles.

Each future response contains `semantic_relevance`, `allowed_claim`, `forbidden_claim`, and `short_reason`. The reference is class/evidence-level rather than per-sample. Its schema can be reviewed/generated independently of the final row split, but no call is authorized by this audit and all outputs require researcher review. It never defines utility or sample recoverability.

## 7. Six operational conflicts

The dependency audit identified six noncanonical surfaces. All are now resolved without changing canonical DEC-0025 plans:

| Surface | Resolution |
| --- | --- |
| `AGENTS.md` | current NF3/Model B/OOF-utility/optional-DeepSeek route replaces stale mandatory Model A Teacher/Supervisor/RLAIF instructions |
| `README.md` | current method/data roles and completed Model A state replace stale Edge-primary/no-SFT/mandatory-RLAIF wording |
| `docs/SERVER_MIGRATION.md` | prominent `LEGACY_MODEL_A_RECOVERY / DEPRECATED / DO_NOT_EXECUTE_FOR_MODEL_B`; old Teacher restart path marked completed and forbidden |
| `docs/runbooks/deepseek_api.md` | prominent legacy warning; old Teacher commands retained only for lineage and forbidden for Model B |
| `src/flowsec/training/README.md` | Model A training path marked completed/legacy; old Teacher fields explicitly barred from Model B GT |
| `configs/training/near_sft_config_v2.yaml` | completed Model A config changed from launch-ready to `COMPLETED_MODEL_A_LEGACY`, `formal_run_authorized=false`, with a fail-closed regression test |

`docs/PROJECT_HANDOFF.md` was synchronized with the new B1 engineering status and next action. Canonical research plans were not rewritten.

## 8. Researcher decision boundary

The schema work is complete, but paid generation remains blocked for a scientific reason rather than an API/configuration reason:

```text
SCHEMA_FROZEN=true
SAMPLE_MANIFEST_NOT_YET_FROZEN=true
UNIQUE_BLOCKER=DATASET_V4_FINAL_SPLIT_TAXONOMY_DEVELOPMENT_ROTATIONS_AND_OOF_PROVENANCE
```

Finalizing that B1 package must not reopen dataset search. After it is frozen, the 2,000-row sample manifest can be materialized and leakage-audited, then a researcher may separately authorize the optional cache. The 63-cell semantic-reference schema is technically ready for researcher-reviewed generation, but this task made zero calls.

```text
RESEARCHER_REVIEW_REQUIRED=true
```
