#!/usr/bin/env bash
set -euo pipefail

QWEN_RUNTIME_BIN=/root/autodl-tmp/conda/qwen35-runtime/bin
export PATH="${QWEN_RUNTIME_BIN}:${PATH}"

# Official post-trained Qwen3.5-9B, text-only local inference.
# max_model_len=8192 is based on the deterministic PLAN_B audit:
# observed maximum prompt 1,607 tokens; smoke output budget 768 tokens.
exec "${QWEN_RUNTIME_BIN}/vllm" serve \
  /root/autodl-tmp/models/Qwen3.5-9B \
  --served-model-name Qwen/Qwen3.5-9B \
  --host 127.0.0.1 \
  --port 8000 \
  --tensor-parallel-size 1 \
  --dtype bfloat16 \
  --language-model-only \
  --max-model-len 8192 \
  --gpu-memory-utilization 0.85 \
  --reasoning-parser qwen3 \
  --default-chat-template-kwargs '{"enable_thinking":false}' \
  --seed 7
