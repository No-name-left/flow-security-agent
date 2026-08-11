# Qwen3.5-9B Local Deployment and Runtime Evidence Audit

Date: 2026-08-11
Branch: `feat/local-qwen35-9b-runtime`
Scope: deployment/fidelity/inspection only; no SFT, RL, Unknown experiment, Supervisor experiment, or paper benchmark.

## Gates

- `ADAPTER_EVIDENCE_FIDELITY_GATE=PASS`
- `LOCAL_QWEN_DEPLOYMENT_STATUS=PASS`
- `MODEL_SERVICE_STATUS=PASS`
- `LOCAL_QWEN_RAW_SMOKE=PASS`
- `RUNTIME_TO_QWEN_REAL_SMOKE=PASS`
- `PRETRAINING_DESIGN_DISCUSSION_READY=TRUE`

## Adapter Evidence Fidelity

`PRODUCTION_RUNTIME_EVIDENCE_CONTRACT_V1` maps every formal safe Production field to Runtime/model visibility, conversion, unit, cardinality, null policy and ordering. Real source-to-output checks cover Normal, DDoS, scanning, injection, malware and MITM; TCP/UDP; short and >8-packet sessions; packet 1–8 and 9–16; whole-session summaries; past-only temporal stats; and anonymous relation semantics.

- Value comparison uses `rel=0`, `abs=1e-12` for floats; byte, packet and second units remain unchanged.
- Initial cardinality is `min(total session packets, 8)`; expanded evidence is the ordered materialized subset of packets 9–16.
- Missing required packet/summary fields and null required values fail closed; no synthetic zero/empty defaults are created.
- Backend sample/dataset/split/K-U/GT/source/capture identity remains outside the rendered model request.

Contract: [`production_runtime_evidence_contract_v1.json`](production_runtime_evidence_contract_v1.json)

## Model and Runtime

| Item | Value |
| --- | --- |
| Model | `Qwen/Qwen3.5-9B` official post-trained checkpoint |
| Revision | `c202236235762e1c871ad0ccb60c8ee5ba337b9a` |
| Download | 16/16 files, 19,329,393,661 bytes, no incomplete files |
| Git-external path | `/root/autodl-tmp/models/Qwen3.5-9B` |
| Independent env | `/root/autodl-tmp/conda/qwen35-runtime` (Python venv) |
| Stack | Python 3.12.3; Torch 2.11.0+cu130; vLLM 0.25.1; Transformers 5.15.0 |
| GPU | 1× RTX 4090, 49,140 MiB; driver 580.105.08 |
| Serve mode | BF16, single GPU, `--language-model-only`, `--max-model-len 8192` |
| Direct response | `--reasoning-parser qwen3`, server/API `enable_thinking=false` |
| Base URL / name | `http://127.0.0.1:8000/v1`; `Qwen/Qwen3.5-9B` |
| Final health | `/health` 200; `/v1/models` 200; service left running |

The first launch reached model/CUDA warmup but failed because the venv Ninja executable was not on `PATH`. The launch script now prepends the independent venv `bin`; the successful startup took about 108 s. This was an environment-path failure, not a model/CUDA failure.

Official references: [Qwen model card](https://huggingface.co/Qwen/Qwen3.5-9B), [vLLM Qwen3.5 recipe](https://docs.vllm.ai/projects/recipes/en/latest/Qwen/Qwen3.5.html), [vLLM package](https://pypi.org/project/vllm/).

## Real Smoke

| Layer | Result | Evidence |
| --- | --- | --- |
| `/v1/models` + direct JSON chat | PASS | 37 input / 6 output tokens; 1.22s; no reasoning content |
| Typed fake-safe Traffic Expert | PASS | 409 / 307 tokens; strict parse |
| Six real Production classes | PASS | All strict parse; GT added only after each response in backend control plane |
| Packet round 1 → explicit 9–16 expansion → round 2 | PASS | input 974 → 1621 tokens |
| Initial → explicit past-only temporal context | PASS | input 523 → 828 tokens; latest < current |
| Repeated deterministic request | PASS | parse/schema/classification candidate projections stable |

Per-class calls (smoke only, not accuracy):

| Control-plane GT | Input | Output | Latency | Fine candidates |
| --- | ---: | ---: | ---: | ---: |
| Backdoor | 974 | 341 | 6.08s | 0 |
| DDoS_TCP | 638 | 310 | 5.49s | 0 |
| MITM | 518 | 354 | 6.25s | 0 |
| Normal | 792 | 399 | 7.07s | 0 |
| Port_Scanning | 637 | 303 | 5.38s | 0 |
| SQL_injection | 954 | 372 | 6.61s | 0 |

The raw model returned parseable Evidence-State-shaped JSON but no fine candidate on these six samples. No prompt tuning or performance conclusion was made.

## Architecture and LoRA Inventory

The real config/meta `named_modules()`/`named_parameters()` inspection found 9,409,813,744 parameters in the full checkpoint and 8,953,803,264 in the text causal LM. The text path has 32 layers, hidden size 4096, FFN size 12288, vocab 248320, 24 Gated DeltaNet layers and 8 full gated-attention layers. It uses RMSNorm/RMSNormGated, untied embedding and LM head. The full checkpoint contains a vision encoder; `--language-model-only` sets all multimodal limits to zero.

| Family / pattern | Count | In → Out | Parameters | Inventory classification |
| --- | ---: | ---: | ---: | --- |
| ffn `*.down_proj` | 32 | 12288 → 4096 | 1,610,612,736 | needs_research_decision |
| ffn `*.gate_proj` | 32 | 4096 → 12288 | 1,610,612,736 | needs_research_decision |
| ffn `*.up_proj` | 32 | 4096 → 12288 | 1,610,612,736 | needs_research_decision |
| full_attention `*.k_proj` | 8 | 4096 → 1024 | 33,554,432 | likely_lora_target |
| full_attention `*.o_proj` | 8 | 4096 → 4096 | 134,217,728 | likely_lora_target |
| full_attention `*.q_proj` | 8 | 4096 → 8192 | 268,435,456 | likely_lora_target |
| full_attention `*.v_proj` | 8 | 4096 → 1024 | 33,554,432 | likely_lora_target |
| gated_deltanet `*.in_proj_a` | 24 | 4096 → 32 | 3,145,728 | needs_research_decision |
| gated_deltanet `*.in_proj_b` | 24 | 4096 → 32 | 3,145,728 | needs_research_decision |
| gated_deltanet `*.in_proj_qkv` | 24 | 4096 → 8192 | 805,306,368 | needs_research_decision |
| gated_deltanet `*.in_proj_z` | 24 | 4096 → 4096 | 402,653,184 | needs_research_decision |
| gated_deltanet `*.out_proj` | 24 | 4096 → 4096 | 402,653,184 | needs_research_decision |
| lm_head `lm_head` | 1 | 4096 → 248320 | 1,017,118,720 | probably_frozen |

No LoRA rank, alpha, dropout or target set is frozen. `CLASSIFICATION_HEAD_FEASIBILITY=REQUIRES_TRAINING_SIDE_IMPLEMENTATION`: final non-padding token, guaranteed EOS, or a training-only pooled text state are candidates, but OpenAI-compatible vLLM chat does not expose hidden states.

## Tokenizer Audit

Sampling is deterministic: for each `(preset, fine_label)` PLAN_B `K_known ∩ train` stratum, sort stable sample IDs and take 8. This yields 272 rows across 34 strata (120 unique sessions).

| Variant | N | Mean | Median | P90 | P95 | P99 | Max |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| initial | 272 | 744.7 | 641.0 | 960.0 | 964.0 | 968.2 | 971 |
| initial_gt8_session | 93 | 955.0 | 957.0 | 965.0 | 966.4 | 971.0 | 971 |
| initial_plus_packets_9_16 | 93 | 1494.3 | 1488.0 | 1601.0 | 1603.0 | 1607.0 | 1607 |
| initial_plus_temporal | 272 | 1061.5 | 965.0 | 1272.8 | 1280.0 | 1285.9 | 1288 |

The observed maximum is 1,607 input tokens; with the 768-token smoke output budget, 8,192 context provides more than 3× headroom. Protocol terms are acceptable, but digit-by-digit numbers and repeated JSON keys create measurable overhead. Therefore `TOKENIZER_ADAPTATION_STATUS=COMPACT_SERIALIZATION_SHOULD_BE_TESTED`: first ablate compact serialization; do not train or extend a tokenizer yet.

## Resource Profile

- Checkpoint: 17.98 GiB; model load: 16.8 GiB GPU.
- Idle loaded service: 41,791 MiB; observed request peak: 41,795 MiB. Most of the difference from model weights is the configured vLLM reservation and 21.82 GiB KV cache.
- KV capacity: 583,787 tokens; reported maximum 8,192-token concurrency 71.26×.
- Observed generation: about 54–56.6 tokens/s. Non-streaming API did not expose TTFT.

## Verification

- Fidelity/Runtime/backend/provider targeted tests: **191 passed**.
- Full regression: **261 passed**.
- `compileall`: **PASS**; conflict-marker scan: **PASS**; `git diff --check`: **PASS**.

## Known Limitations and Stop Point

- RAW_SMOKE_TRAFFIC_EXPERT_PROMPT_V0 and response schema are deliberately non-frozen.
- Raw smoke produced no fine-class candidates for the six representative Production samples; this is not a benchmark and motivates later authorized training.
- OpenAI-compatible non-streaming smoke did not expose TTFT.
- vLLM reserves most of the configured 85% GPU budget for KV cache, so idle process memory is much larger than model weights alone.
- The inference API does not expose hidden states; a classification head requires a training-side Transformers path.
- Application evidence, sanitized payload and production Knowledge RAG remain unavailable.
- Numeric values and repeated JSON keys are token-inefficient; compact serialization should be tested before tokenizer adaptation.
- Training Protocol remains UNDER DESIGN / NOT RUN. No SFT, LoRA training, classification-head training, DPO/GRPO/PPO, Unknown experiment, Supervisor experiment or formal Raw benchmark was run.

Machine manifest: [`qwen35_9b_local_deployment_manifest.json`](qwen35_9b_local_deployment_manifest.json)
Detailed model/tokenizer inspection: [`qwen35_9b_model_inspection.json`](qwen35_9b_model_inspection.json)
