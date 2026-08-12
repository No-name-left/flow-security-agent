# Formal Near Multi-task SFT Runtime Preflight

Status: **PASS**

Audit date: 2026-08-13

Formal SFT started: **false**

## Decision

The frozen six-class Near runtime is ready for a separately authorized formal SFT run. A disposable 64-record smoke used the real Qwen3.5-9B BF16 model, PEFT LoRA, Fine Classification Head, formal multi-task loss, AdamW optimizer, cosine scheduler, gradient accumulation, checkpoint implementation, and EXACT_EVAL_CLEAN validation path. It completed four optimizer steps, including a full model/runtime destruction and checkpoint reload after step three.

This smoke is **not a formal training run or a paper result**. The formal output root remained absent, and the disposable checkpoint is explicitly marked `DISPOSABLE_NOT_FORMAL` and must never be resumed as a formal run.

## Resolved formal entry

```text
FORMAL_SFT_ENTRYPOINT=python -m flowsec.training.train_near_sft
FORMAL_SFT_CONFIG=configs/training/near_sft_config_v2.yaml
MODEL_ID_OR_PATH=/root/autodl-tmp/models/Qwen3.5-9B
TRAIN_CORPUS_PATH=/root/autodl-tmp/processed/near_pretraining_v3/sft_corpus/final/observable_sft_corpus_v3.jsonl
VALIDATION_PATH=/root/autodl-tmp/processed/near_pretraining_v3/validation/near_known_validation_v3.jsonl
OUTPUT_ROOT=/root/autodl-tmp/processed/training_runs/near_sft_v3
```

The formal output root was absent before and after the smoke. The disposable audit is external to Git at `/root/autodl-tmp/processed/sft_runtime_smoke/formal_near_multitask_sft_preflight_v1`.

## Real instantiated model and parameter boundary

- Model/config identity: `Qwen/Qwen3.5-9B`, revision and tokenizer revision `c202236235762e1c871ad0ccb60c8ee5ba337b9a`.
- Label order from the frozen class-map contract: `Normal`, `DDoS_HTTP`, `DDoS_TCP`, `Password`, `SQL_injection`, `Vulnerability_scanner`.
- Fine Classification Head: attention-masked mean pooling followed by `Linear(4096, 6)`.
- Total parameters: 9,431,477,494.
- Trainable parameters: 21,663,750 (0.229696%).
- Trainable LoRA parameters: 21,639,168 across 496 tensors.
- Trainable Fine Head parameters: 24,582 across two tensors.
- Trainable base parameters: 0.
- Trainable original LM Head parameters: 0; all 1,017,118,720 original LM Head parameters remained frozen.
- Optimizer membership exactly matched the 498 trainable LoRA/Fine Head tensors.
- After a real backward, 248 LoRA tensors and both Fine Head tensors had nonzero gradients. No frozen parameter had a gradient.

A sample of instantiated trainable names included `fine_head.projection.weight`, `fine_head.projection.bias`, and PEFT `lora_A`/`lora_B` parameters under attention, DeltaNet, output-projection, and MLP target modules. No embedding, base, or original LM Head name entered the optimizer.

## Runtime and resource result

```text
GPU=NVIDIA GeForce RTX 4090
GPU_MEMORY_TOTAL=50,864,390,144 bytes (47.371 GiB reported by Torch)
PEAK_GPU_MEMORY=38,540,288,512 bytes (35.893 GiB)
TORCH_VERSION=2.11.0+cu130
CUDA_VERSION=13.0
TRANSFORMERS_VERSION=5.15.0
PEFT_VERSION=0.18.1
BF16_SUPPORTED=true
```

BF16 LoRA ran with the frozen operational settings (`micro_batch_size=1`, `gradient_accumulation_steps=16`, effective batch size 16, gradient checkpointing enabled, maximum sequence length 8,192). There was no OOM and no operational override. QLoRA fallback is not required.

## Frozen corpus and multi-task path

The runtime recomputed the formal corpus SHA256 as `d93789de29b746d923660bb2e4ccad501412e75303ddf95f7087c85f6c67d6ca` and parsed all 14,350 records through the same formal preflight and V2 record contract.

The deterministic smoke subset contained 64 records / 62 sessions and covered all six classes, 51 primary and 13 auxiliary states, 52 sufficient and 12 insufficient states, single-gap and multi-gap targets, and Basic/Application/Temporal/Relation stages. Its longest encoded sequence was 4,697 tokens, below the frozen 8,192 limit.

All 64 runtime records verified that weighted Evidence loss equalled unweighted per-record LM loss multiplied by `session_weight`. The selected multi-state session had total state weight 1.0 and exactly one classification-supervised primary. A real eligible primary with `evidence_sufficient=false` produced classification CE, while auxiliary records produced an explicit zero supervised count and masked classification loss. This confirms the frozen classification/sufficiency decoupling in the instantiated path.

Observed finite loss ranges across the smoke were:

```text
CLS_LOSS_RANGE=[-0.0, 2.5625]
EVIDENCE_LOSS_RANGE=[0.1875, 0.92578125]
TOTAL_LOSS_RANGE=[0.06640625, 2.796875]
```

The total loss was checked record-by-record against the frozen formula `1.0 * classification_loss + 0.35 * weighted_evidence_loss`. Zeros occurred only on explicitly classification-masked auxiliary states; they were not accidental numeric zeros.

## Checkpoint and validation smoke

The runtime saved a real step-3 checkpoint containing PEFT adapter, Fine Head safetensors, optimizer, cosine scheduler, trainer state, and Python/NumPy/Torch/CUDA RNG state. It destroyed the first runtime, loaded a fresh frozen base, restored every component, verified exact LoRA and Fine Head tensor equality, restored optimizer/scheduler/step/RNG state, and completed optimizer step four. Both LoRA and Fine Head changed after the resumed step.

The validation smoke used one current EXACT_EVAL_CLEAN record per class. It produced six-dimensional Fine logits, validated stored labels against the frozen class map, executed the metric code, and generated 32 Evidence-State tokens. No smoke accuracy or F1 is retained as a formal result.

## Frozen formal configuration

The accepted config is unchanged and has SHA256 `b11e651592231cf8fcc7fc503e5a09b04d19b5d3bb35c7b02f68137030444dc1`.

- LoRA: PEFT, rank 8, alpha 16, dropout 0.05, no bias; targets `q_proj`, `k_proj`, `v_proj`, `o_proj`, `in_proj_qkv`, `in_proj_z`, `in_proj_a`, `in_proj_b`, `out_proj`, `gate_proj`, `up_proj`, `down_proj`.
- Precision: BF16, no quantization.
- Optimizer: AdamW, learning rate `2e-4`, weight decay `0.01`, max gradient norm `1.0`.
- Scheduler: cosine with warmup ratio `0.03`.
- Schedule: two epochs, 1 x 16 accumulation, formal scheduler total 1,794 optimizer steps, deterministic per-epoch order, seed `20260809`, no DataLoader workers.
- Checkpoint/evaluation: save every 500 steps and each epoch, retain two; evaluate each epoch on the frozen validation asset.
- Loss: Fine classification CE weight `1.0`; session-normalized Evidence-State LM weight `0.35`.
- Reproducibility: Python, NumPy, Torch, and CUDA seeds are set. Record order and checkpoint RNG are preserved. Exact cross-run equality is not promised for every CUDA kernel.

The launcher fix in this task centralizes the actual formal runtime/record forward path for both formal execution and smoke, completes NumPy RNG checkpointing, and uses explicit non-weights-only loads for trusted local optimizer/scheduler/RNG state under PyTorch 2.11. No data, label, Teacher, Evidence, loss weighting, or hyperparameter definition changed.

## Verification

```text
TARGETED_PYTEST=25 passed
FULL_PYTEST=395 passed
COMPILEALL=PASS
GIT_DIFF_CHECK=PASS
```

## Exact acceptance fields

```text
FORMAL_SFT_RUNTIME_PREFLIGHT_STATUS=PASS
MODEL_LOAD_STATUS=PASS
MODEL_ID_OR_PATH=/root/autodl-tmp/models/Qwen3.5-9B
MODEL_REVISION=c202236235762e1c871ad0ccb60c8ee5ba337b9a
GPU_MODEL=NVIDIA GeForce RTX 4090
GPU_MEMORY_TOTAL=50864390144_bytes
PEAK_GPU_MEMORY=38540288512_bytes
BASE_MODEL_FROZEN=true
LM_HEAD_FROZEN=true
LORA_TRAINABLE=true
FINE_HEAD_TRAINABLE=true
FINE_HEAD_DIMENSION=6
TOTAL_PARAMETERS=9431477494
TRAINABLE_PARAMETERS=21663750
GRADIENT_AUDIT_STATUS=PASS
OPTIMIZER_PARAMETER_AUDIT_STATUS=PASS
CORPUS_SHA256_STATUS=PASS
SESSION_WEIGHT_RUNTIME_STATUS=PASS
CLS_LOSS_STATUS=PASS_FINITE_AND_MASKED_BY_CONTRACT
EVIDENCE_LOSS_STATUS=PASS_FINITE_SESSION_WEIGHT_APPLIED
TOTAL_LOSS_STATUS=PASS_CONFIGURED_MULTI_TASK_FORMULA
TOKENIZER_RUNTIME_STATUS=PASS_MAX_4697_OF_8192
SFT_RUNTIME_SMOKE_STATUS=PASS
SMOKE_OPTIMIZER_STEPS=4
CHECKPOINT_SAVE_STATUS=PASS
CHECKPOINT_RESUME_STATUS=PASS
FINE_HEAD_CHECKPOINT_STATUS=PASS
LORA_CHECKPOINT_STATUS=PASS
VALIDATION_RUNTIME_STATUS=PASS_NOT_A_FORMAL_RESULT
BF16_LORA_STATUS=PASS
QLORA_FALLBACK_REQUIRED=false
FORMAL_CONFIG_STATUS=PASS_FROZEN_UNCHANGED
FORMAL_SFT_COMMAND=ARTIFACT_ROOT=/root/autodl-tmp/processed QWEN_MODEL_PATH=/root/autodl-tmp/models/Qwen3.5-9B PYTHONPATH=src /root/autodl-tmp/conda/qwen35-runtime/bin/python -m flowsec.training.train_near_sft --config configs/training/near_sft_config_v2.yaml --execute
FORMAL_SFT_STARTED=false
READY_TO_START_FORMAL_SFT=true
NEXT_ACTION=START_FORMAL_NEAR_MULTI_TASK_SFT
```
