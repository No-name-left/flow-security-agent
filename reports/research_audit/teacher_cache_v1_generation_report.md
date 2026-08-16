# Teacher Cache v1 & Semantic Reference v1 — Pre-Price DeepSeek Generation Report

> Status: `COMPLETE`
>
> Generation date: 2026-08-17
>
> Repository: `flow-security-agent` @ `main` `ec7cd45bd0d015f568293ac98ed893f7058c48f5`
>
> Scope: researcher-authorized paid DeepSeek generation of the frozen
> `teacher_cache_v1` (2,000 logical policy responses) and
> `semantic_reference_v1` (63 semantic-admissibility responses). No other
> research work was performed: no Qwen, no Model B training, no RL, no continual,
> no dataset/split/taxonomy/protocol changes, no push.

## 1. Result

```text
DEEPSEEK_PREPRICE_GENERATION_STATUS=COMPLETE
TEACHER_CACHE_V1_VALID_N=2000
TEACHER_CACHE_V1_FAILED_N=0
SEMANTIC_REFERENCE_VALID_N=63
SEMANTIC_REFERENCE_FAILED_N=0
CORE_HIGH_TOKEN_DEEPSEEK_DEPENDENCY_COMPLETE=true
```

Both frozen request artifacts were generated end-to-end with zero failures, zero
parse failures, and zero retries. Generation is resume-safe: every record is
keyed by `teacher_cache_id` / `reference_id` and skips any record whose
schema-valid response matches the current prompt SHA256 and model ID.

## 2. Frozen configuration

| Item | Value |
| --- | --- |
| DeepSeek model | `deepseek-v4-flash` (operator-managed env file, matches project Teacher default) |
| API base | `https://api.deepseek.com` (no credential recorded or printed) |
| Teacher prompt | `TEACHER_CACHE_V1_PROMPT_V1`, renderer `TEACHER_CACHE_V1_RENDERER_V1` |
| Teacher prompt SHA256 | `dd86d4acac26c6ae7f89806c9511752f62a3c5ad1365498dc9bba8163cf87096` |
| Semantic prompt | `SEMANTIC_REFERENCE_V1_PROMPT_V1`, renderer `SEMANTIC_REFERENCE_V1_RENDERER_V1` |
| Semantic prompt SHA256 | `4898b803253e2b6ff4aaf08662c0180905160683b7738be8a3f73ad779abb961` |
| Temperature / max output | `0` / `256` tokens |
| Thinking mode | explicitly disabled (`extra_body.thinking.type=disabled`) |
| Teacher hard attempt cap | `2150` (used `2000`) |
| Semantic hard attempt cap | `80` (audit precedent; used `63`) |
| Retry policy | max 2 transport retries (2s/8s backoff); tolerant local JSON extraction; max 1 identical-prompt retry; prompt never modified after a failure |
| Concurrency | 4 workers |

All 2,000 normalized teacher records carry the identical `prompt_sha256`
`dd86d4ac…` and model `deepseek-v4-flash`; the prompt was never modified after
the first paid call. Prompt-spec SHA256 covers system instruction, user
template, response schema, model ID, temperature, and output bound.

## 3. Request manifest identities

| Artifact | SHA256 |
| --- | --- |
| `teacher_cache_v1_requests.jsonl` (2,000 frozen rows) | `584388897a5aebcaf5bb42fea4e60c1cd1c96d09c8302641690317873a83d8bb` |
| `teacher_cache_v1_offline_manifest.jsonl` (2,000 offline truths) | `a8f2e070dccfaaa7963a5346bd0ff20fc6604dc55a26af9c0e4dd7d766718d5c` |
| `semantic_reference_v1_request_manifest.json` (63 frozen cells) | `308d419b104069934d349960333809026d7a865d4649164145c820c610eba2e2` |

Per-row `teacher_input_payload_hash` cross-check between request and offline
manifest: 0 mismatches. No request was re-sampled, re-designed, or modified;
payloads were sent verbatim.

## 4. Pre-call safety gates

```text
TEACHER_PAYLOAD_GT_LEAKAGE=false        (checked on all 2,000 payloads before the first paid call)
SEMANTIC_PAYLOAD_GT_LEAKAGE=false       (checked on all 63 requests)
TEACHER_CACHE_FINAL_TEST_CONTAMINATION=false
```

The leakage precheck verifies the payload key envelope, rejects GT/recoverability/
stratum/rotation/split markers, verifies the rotation-aware probability map
(7-class `CANONICAL_TAXONOMY_V1` for 1,600 rows; the 6-class held-out map for the
400 whole-class rotation rows, consistent with each row's offline rotation role),
and confirms probability ranges. Offline metadata (`sampling_stratum`,
`policy_role`, `unknown_rotation_if_any`, `canonical_label`, source partition)
was merged into output records only after generation and was never sent to the
provider. All 2,000 rows have `allowed_for_final_test=false`; source partitions
are TRAIN/VALIDATION only.

## 5. Token accounting (API-reported usage)

| Task | Attempts | Input tokens | Output tokens |
| --- | ---: | ---: | ---: |
| Teacher smoke (5 of the official 2,000) | 5 | 11,135 | 380 |
| Teacher full batch | 1,995 | 4,476,721 | 148,716 |
| **Teacher total** | **2,000** | **4,487,856** | **149,096** |
| Semantic reference | 63 | 40,788 | 7,373 |
| **Grand total** | **2,063** | **4,528,644** | **156,469** |

Cached-input-token fields are not reported by the API envelope used and are
`null` per record. No cost estimate is fabricated; totals above are
API-reported usage. Teacher input exposure falls inside the dependency audit's
2.2–5.5M input / 0.22–0.55M output pre-price estimates.

## 6. Teacher cache validation

```text
TEACHER_CACHE_V1_EXPECTED_N=2000
TEACHER_CACHE_V1_VALID_N=2000
TEACHER_CACHE_V1_FAILED_N=0
TEACHER_CACHE_V1_SKIPPED_EXISTING_N=0 (fresh start; existing-response check ran first)
DUPLICATE_LOGICAL_RECORDS=0
PARSE_FAILURE_RATE=0.000000
RETRY_RATE=0.000000
```

Every normalized record is strict-schema valid: exact five-key response object,
`recommended_action` in the frozen four-action vocabulary, `predicted_class` in
the payload's current Known class map (rotation-aware) or null, `confidence` in
[0,1], `semantic_gap` in the frozen vocabulary, and the frozen
STOP/acquire/novelty consistency rules (`STOP_AND_CLASSIFY` requires a known
class and `semantic_gap=NONE`).

### Action distribution

| Action | Count |
| --- | ---: |
| `STOP_AND_CLASSIFY` | 741 |
| `ACQUIRE_TEMPORAL` | 1,259 |
| `ACQUIRE_RELATION` | 0 |
| `ENTER_NOVELTY_DETECTION` | 0 |

### Action distribution by stratum

| Stratum | STOP_AND_CLASSIFY | ACQUIRE_TEMPORAL |
| --- | ---: | ---: |
| `BASIC_SUFFICIENT_KNOWN` (750) | 415 | 335 |
| `RECOVERABLE_KNOWN` (850) | 206 | 644 |
| `TRUE_UNKNOWN_ROTATIONS` (400) | 120 | 280 |

Confidence (in the recommended action): mean `0.7153`, min `0.55`, max `1.0`.

**Observed characteristic (recorded, not post-hoc corrected):** the frozen
prompt produced no `ACQUIRE_RELATION` and no `ENTER_NOVELTY_DETECTION`
recommendations. Per the frozen protocol, the prompt was NOT modified after
seeing results — this is a real empirical property of the frozen Teacher
baseline and must be reported as such in any downstream use. Teacher behavior
is a baseline; it is never operational utility, classification, Unknown, or
continual GT.

## 7. Semantic reference validation

```text
SEMANTIC_REFERENCE_EXPECTED_N=63
SEMANTIC_REFERENCE_VALID_N=63
SEMANTIC_REFERENCE_FAILED_N=0
```

All 63 responses satisfy the frozen `SEMANTIC_ADMISSIBILITY_REFERENCE_V1`
response contract: `semantic_relevance` in
`SUPPORTIVE | NEUTRAL | CONTRADICTORY | CONTEXT_DEPENDENT`, with non-empty
`allowed_claim`, `forbidden_claim`, and `short_reason`. Role is exclusively
`SEMANTIC_ADMISSIBILITY_REFERENCE`; it can never become `OPERATIONAL_UTILITY_GT`.

## 8. Artifacts (Git-external)

| Artifact | Location | SHA256 |
| --- | --- | --- |
| Teacher normalized (canonical) | `processed/dataset_v4_nf3_ton_v1/teacher/teacher_cache_v1_responses_normalized.jsonl` | `e2bc5599a98419cca723cf9b8a3f542e17a2afdfd720256e759931ab2b64a964` |
| Teacher raw (secondary) | `processed/dataset_v4_nf3_ton_v1/teacher/teacher_cache_v1_responses_raw.jsonl` | `9f671d360249d5078f92188eec1c86b2de5ff01817b6c44102f2f8a38f146bff` |
| Teacher generation metadata | `processed/dataset_v4_nf3_ton_v1/teacher/teacher_cache_v1_generation_metadata.json` | — |
| Teacher generation summary | `processed/dataset_v4_nf3_ton_v1/teacher/teacher_cache_v1_generation_summary.json` | — |
| Semantic normalized (canonical) | `processed/dataset_v4_nf3_ton_v1/semantic_reference/semantic_reference_v1_responses_normalized.jsonl` | `9830704256bcfd05c6c3fae40ea8b055a2dbef63565a5f03c9894ce71009ad74` |
| Semantic raw (secondary) | `processed/dataset_v4_nf3_ton_v1/semantic_reference/semantic_reference_v1_responses_raw.jsonl` | `2d38a9153c982216087107645b2a304edfd6092fc4658d22b6e878138d838cbf` |
| Semantic generation metadata | `processed/dataset_v4_nf3_ton_v1/semantic_reference/semantic_reference_v1_generation_metadata.json` | — |

Raw responses stay Git-external. Formal experiment identity uses the normalized
canonical hashes above.

## 9. Security

```text
SECRET_SCAN=PASS
```

The API key lives only in the operator-managed file
`/root/autodl-tmp/secrets/deepseek.env` (never printed, never committed). A
secret scan over generated artifacts, metadata, summaries, and the repository
found no key material. Generation errors pass through the project transport
redactor.

## 10. Resume instructions

Re-run the generator; validated records are skipped automatically:

```bash
/root/autodl-tmp/conda/flow-data/bin/python \
  tools/generate_teacher_cache_v1.py --mode teacher   # idempotent; skips 2000 valid
/root/autodl-tmp/conda/flow-data/bin/python \
  tools/generate_teacher_cache_v1.py --mode semantic  # idempotent; skips 63 valid
/root/autodl-tmp/conda/flow-data/bin/python \
  tools/generate_teacher_cache_v1.py --mode validate  # distributions + hashes
```

A record is reused only when its `validation_status=VALID`, `prompt_sha256`, and
`model_id` match the current frozen spec. Changing the prompt text, schema, or
model changes the fingerprint and would intentionally force fresh calls — do
not do this without a new Decision.

## 11. Git policy

Only two new small files are candidates for tracking (left untracked for
researcher review; no commit, no push):

- `tools/generate_teacher_cache_v1.py` (resume-safe generation tool);
- `tests/tools/test_generate_teacher_cache_v1.py` (15 targeted tests, all pass).

Raw/normalized response artifacts remain Git-external.

```text
MODEL_B_TRAINING_STARTED=false
RL_TRAINING_STARTED=false
PUSHED=false
```
