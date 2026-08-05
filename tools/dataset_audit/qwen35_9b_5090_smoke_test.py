#!/usr/bin/env python3
"""Prepared, opt-in Qwen3.5-9B QLoRA smoke test for one 32 GiB GPU.

The default mode is a non-mutating preflight.  Loading weights requires an
explicit --execute flag and either a local checkpoint or --allow-download.
It does not launch formal training and writes only the requested JSON report.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import sys
import time
from pathlib import Path


DEFAULT_TARGETS = [
    "q_proj",
    "k_proj",
    "v_proj",
    "o_proj",
    "gate_proj",
    "up_proj",
    "down_proj",
    "in_proj_qkv",
    "in_proj_z",
    "in_proj_b",
    "in_proj_a",
    "out_proj",
]


def emit(report: dict[str, object], path: Path | None) -> None:
    payload = json.dumps(report, ensure_ascii=False, indent=2)
    if path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(payload + "\n", encoding="utf-8")
    print(payload)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="Qwen/Qwen3.5-9B-Base")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--allow-download", action="store_true")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--max-seq-length", type=int, default=2048)
    parser.add_argument("--prompt", default='Flow evidence: {"protocol":"TCP","dst_port":443}. Return JSON.')
    args = parser.parse_args()

    model_path = Path(args.model)
    is_local = model_path.exists()
    report: dict[str, object] = {
        "mode": "execute" if args.execute else "preflight_only",
        "formal_training_started": False,
        "model": args.model,
        "model_is_local": is_local,
        "allow_download": args.allow_download,
        "python": sys.version,
        "platform": platform.platform(),
        "max_seq_length": args.max_seq_length,
        "candidate_lora_targets": DEFAULT_TARGETS,
        "recommended_training_envelope": {
            "quantization": "4-bit NF4",
            "compute_dtype": "bfloat16 when supported",
            "micro_batch_size": 1,
            "gradient_accumulation": "use to reach effective batch",
            "gradient_checkpointing": True,
            "optimizer": "paged_adamw_8bit",
            "freeze_vision_tower": True,
            "initial_sequence_length": "2048; increase to 4096 only after measured headroom",
        },
    }

    try:
        import torch

        report["torch_version"] = torch.__version__
        report["cuda_available"] = torch.cuda.is_available()
        report["cuda_version"] = torch.version.cuda
        if torch.cuda.is_available():
            props = torch.cuda.get_device_properties(0)
            report["gpu"] = {
                "name": props.name,
                "total_memory_bytes": props.total_memory,
                "compute_capability": f"{props.major}.{props.minor}",
            }
    except Exception as exc:  # pragma: no cover - environment dependent
        report["torch_import_error"] = repr(exc)
        if args.execute:
            emit(report, args.output)
            return 2

    if not args.execute:
        report["status"] = "PREPARED_NOT_RUN"
        report["reason"] = "Use --execute on the target NVIDIA host after dependencies and checkpoint are available."
        emit(report, args.output)
        return 0

    if not report.get("cuda_available"):
        report["status"] = "BLOCKED_NO_CUDA"
        emit(report, args.output)
        return 3
    if not is_local and not args.allow_download:
        report["status"] = "BLOCKED_DOWNLOAD_NOT_AUTHORIZED"
        emit(report, args.output)
        return 4

    started = time.time()
    try:  # pragma: no cover - intentionally requires target GPU stack
        from peft import LoraConfig, get_peft_model
        from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig

        quant = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_compute_dtype=torch.bfloat16,
            bnb_4bit_use_double_quant=True,
        )
        tokenizer = AutoTokenizer.from_pretrained(args.model, local_files_only=not args.allow_download)
        model = AutoModelForCausalLM.from_pretrained(
            args.model,
            quantization_config=quant,
            device_map={"": 0},
            torch_dtype=torch.bfloat16,
            local_files_only=not args.allow_download,
            trust_remote_code=False,
        )
        for name, parameter in model.named_parameters():
            if name.startswith("model.visual") or ".visual." in name:
                parameter.requires_grad_(False)
        model.gradient_checkpointing_enable()
        lora = LoraConfig(
            r=8,
            lora_alpha=16,
            lora_dropout=0.05,
            bias="none",
            task_type="CAUSAL_LM",
            target_modules=DEFAULT_TARGETS,
        )
        model = get_peft_model(model, lora)
        inputs = tokenizer(args.prompt, return_tensors="pt", truncation=True, max_length=args.max_seq_length)
        inputs = {key: value.to(0) for key, value in inputs.items()}
        with torch.inference_mode():
            output = model.generate(**inputs, max_new_tokens=32, do_sample=False)
        report["loaded_class"] = type(model).__name__
        report["trainable_parameter_summary"] = model.get_nb_trainable_parameters()
        report["generated_text"] = tokenizer.decode(output[0], skip_special_tokens=True)
        report["peak_allocated_bytes"] = torch.cuda.max_memory_allocated(0)
        report["peak_reserved_bytes"] = torch.cuda.max_memory_reserved(0)
        report["elapsed_seconds"] = round(time.time() - started, 3)
        report["status"] = "SMOKE_PASS"
    except Exception as exc:
        report["status"] = "SMOKE_FAIL"
        report["error_type"] = type(exc).__name__
        report["error"] = str(exc)
        report["elapsed_seconds"] = round(time.time() - started, 3)
        emit(report, args.output)
        return 5

    emit(report, args.output)
    return 0


if __name__ == "__main__":
    os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
    raise SystemExit(main())
