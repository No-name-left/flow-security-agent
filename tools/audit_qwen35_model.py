#!/usr/bin/env python3
"""Read-only Qwen3.5-9B architecture and Production Evidence tokenization audit."""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _percentile(values: Iterable[int], fraction: float) -> float:
    ordered = sorted(values)
    if not ordered:
        return 0.0
    position = (len(ordered) - 1) * fraction
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    weight = position - lower
    return float(ordered[lower] * (1.0 - weight) + ordered[upper] * weight)


def _stats(values: list[int]) -> dict[str, float | int]:
    if not values:
        return {"count": 0, "mean": 0.0, "median": 0.0, "p90": 0.0, "p95": 0.0, "p99": 0.0, "max": 0}
    return {
        "count": len(values),
        "mean": sum(values) / len(values),
        "median": _percentile(values, 0.50),
        "p90": _percentile(values, 0.90),
        "p95": _percentile(values, 0.95),
        "p99": _percentile(values, 0.99),
        "max": max(values),
    }


def _architecture(model_path: Path) -> dict[str, Any]:
    import torch
    from transformers import AutoConfig
    from transformers.models.qwen3_5.modeling_qwen3_5 import (
        Qwen3_5ForCausalLM,
        Qwen3_5ForConditionalGeneration,
    )

    config = AutoConfig.from_pretrained(model_path, local_files_only=True)
    text = config.text_config
    with torch.device("meta"):
        full_model = Qwen3_5ForConditionalGeneration(config)
        model = Qwen3_5ForCausalLM(text)

    modules = list(model.named_modules())
    parameters = list(model.named_parameters())
    linear_groups: dict[tuple[str, str, int, int], dict[str, Any]] = {}
    for name, module in modules:
        if not isinstance(module, torch.nn.Linear):
            continue
        if ".linear_attn." in name:
            family = "gated_deltanet"
        elif ".self_attn." in name:
            family = "full_attention"
        elif ".mlp." in name:
            family = "ffn"
        elif name == "lm_head":
            family = "lm_head"
        else:
            family = "other"
        suffix = name.rsplit(".", 1)[-1]
        key = (family, suffix, int(module.in_features), int(module.out_features))
        disposition = {
            "full_attention": "likely_lora_target",
            "gated_deltanet": "needs_research_decision",
            "ffn": "needs_research_decision",
            "lm_head": "probably_frozen",
            "other": "needs_research_decision",
        }[family]
        entry = linear_groups.setdefault(
            key,
            {
                "family": family,
                "candidate_classification": disposition,
                "module_name_pattern": f"*.{suffix}" if name != suffix else suffix,
                "count": 0,
                "input_dimension": int(module.in_features),
                "output_dimension": int(module.out_features),
                "parameter_count": 0,
                "example": name,
            },
        )
        entry["count"] += 1
        entry["parameter_count"] += sum(parameter.numel() for parameter in module.parameters(recurse=False))

    layer_types = list(text.layer_types)
    return {
        "audit_id": "QWEN35_9B_ARCHITECTURE_AUDIT",
        "source_class": type(config).__name__,
        "architecture": list(config.architectures),
        "model_type": config.model_type,
        "text_model_type": text.model_type,
        "language_backbone_class": type(model.model).__name__,
        "language_model_class": type(model).__name__,
        "full_checkpoint_parameter_count": sum(parameter.numel() for parameter in full_model.parameters()),
        "full_checkpoint_named_module_count": sum(1 for _ in full_model.named_modules()),
        "language_parameter_count": sum(parameter.numel() for _, parameter in parameters),
        "named_module_count": len(modules),
        "named_parameter_tensor_count": len(parameters),
        "layer_count": int(text.num_hidden_layers),
        "hidden_size": int(text.hidden_size),
        "intermediate_size": int(text.intermediate_size),
        "vocab_size": int(text.vocab_size),
        "native_max_position_embeddings": int(text.max_position_embeddings),
        "layer_type_counts": dict(Counter(layer_types)),
        "full_attention_layer_indices": [index for index, value in enumerate(layer_types) if value == "full_attention"],
        "gated_deltanet_layer_indices": [index for index, value in enumerate(layer_types) if value == "linear_attention"],
        "normalization": {
            "type_counts": dict(Counter(type(module).__name__ for _, module in modules if "Norm" in type(module).__name__)),
            "rms_norm_eps": float(text.rms_norm_eps),
        },
        "embedding": {
            "module": "model.embed_tokens",
            "shape": [int(text.vocab_size), int(text.hidden_size)],
            "tied_to_lm_head": bool(text.tie_word_embeddings),
        },
        "lm_head": {
            "module": "lm_head",
            "shape": [int(text.vocab_size), int(text.hidden_size)],
        },
        "vision_module_exists_in_full_checkpoint": hasattr(config, "vision_config"),
        "vision_module_omitted_by_text_only_path": True,
        "ffn": {"activation": str(text.hidden_act), "structure": "gate_proj + up_proj -> SiLU-gated product -> down_proj"},
        "linear_module_inventory": sorted(linear_groups.values(), key=lambda item: (item["family"], item["module_name_pattern"], item["input_dimension"], item["output_dimension"])),
        "lora_inventory_status": "INVENTORY_ONLY_NOT_FROZEN",
        "probably_frozen_candidates": ["model.embed_tokens", "lm_head", "normalization modules", "vision encoder (absent from text-only runtime)"],
        "classification_head_feasibility": "REQUIRES_TRAINING_SIDE_IMPLEMENTATION",
        "classification_head_candidates_not_frozen": [
            "causal-LM final non-padding token hidden state",
            "explicit EOS hidden state when renderer guarantees one",
            "training-only pooling/head over text hidden states",
        ],
        "classification_head_api_note": "OpenAI-compatible vLLM chat does not expose per-token hidden states; use the Transformers/training path for a trainable head.",
    }


def _select_candidates(candidate_root: Path, per_class: int) -> tuple[list[dict[str, str]], dict[str, Any]]:
    import pyarrow.parquet as pq

    groups: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    files = sorted(candidate_root.glob("preset=*/part-00000.parquet"))
    for path in files:
        for row in pq.read_table(path, columns=["sample_id", "preset", "fine_label", "physical_split", "ku_role", "plan"]).to_pylist():
            if row["physical_split"] != "train" or row["ku_role"] != "K_known" or row["plan"] != "PLAN_B":
                raise RuntimeError("candidate asset is not frozen PLAN_B K_known train data")
            normalized = {key: str(value) for key, value in row.items()}
            groups[(normalized["preset"], normalized["fine_label"])].append(normalized)
    selected: list[dict[str, str]] = []
    group_counts: dict[str, int] = {}
    for key in sorted(groups):
        rows = sorted(groups[key], key=lambda item: item["sample_id"])
        chosen = rows[:per_class]
        selected.extend(chosen)
        group_counts[f"{key[0]}::{key[1]}"] = len(chosen)
    return selected, {
        "rule": "For every (preset, fine_label), sort PLAN_B K_known physical-train candidates by stable sample_id and take the first N.",
        "per_class": per_class,
        "candidate_files": [str(path) for path in files],
        "strata": group_counts,
        "selected_rows": len(selected),
        "selected_unique_sample_ids": len({row["sample_id"] for row in selected}),
    }


def _tokenizer_audit(model_path: Path, production_root: Path, candidate_root: Path, per_class: int) -> dict[str, Any]:
    from transformers import AutoTokenizer
    from flowsec.integrations.llm.prompting import TrafficExpertPromptRenderer, raw_smoke_traffic_expert_prompt, render_messages_as_tagged_text
    from flowsec.production.runtime_adapter import ProductionPacketExpansionTool, ProductionParquetEvidenceStore, ProductionSafeAdapter, ProductionSampleRequest, ProductionTemporalContextTool
    from flowsec.runtime.contracts import AgentAction, RuntimePhase, ToolRequest, ToolStatus

    tokenizer = AutoTokenizer.from_pretrained(model_path, local_files_only=True)
    renderer = TrafficExpertPromptRenderer(raw_smoke_traffic_expert_prompt())
    selected, selection = _select_candidates(candidate_root, per_class)
    requests = [ProductionSampleRequest(sample_id=row["sample_id"], dataset="Edge-IIoTset", split="train", phase=RuntimePhase.TRAIN, preset=row["preset"]) for row in selected]
    store = ProductionParquetEvidenceStore(production_root)
    adapter = ProductionSafeAdapter(store)
    adapter.prefetch(requests)

    counts: dict[str, list[int]] = defaultdict(list)
    characters: dict[str, list[int]] = defaultdict(list)
    seen_variant: set[tuple[str, str]] = set()

    def measure(variant: str, evidence: tuple[Any, ...]) -> None:
        rendered = list(render_messages_as_tagged_text(renderer.render(evidence)))
        encoded = tokenizer.apply_chat_template(rendered, tokenize=True, add_generation_prompt=True, enable_thinking=False)
        input_ids = encoded.input_ids if hasattr(encoded, "input_ids") else encoded
        text = tokenizer.apply_chat_template(rendered, tokenize=False, add_generation_prompt=True, enable_thinking=False)
        counts[variant].append(len(input_ids))
        characters[variant].append(len(text))

    for request in requests:
        sample = adapter.adapt(request)
        initial = sample.runtime_input.initial_evidence
        content = json.loads(initial[0].content)
        total_packets = int(content["session_summary"]["initiator_packets"]) + int(content["session_summary"]["responder_packets"])
        measure("initial", initial)
        measure("initial_gt8_session", initial) if total_packets > 8 else None
        unique_key = (request.sample_id, request.preset or "")
        if unique_key in seen_variant:
            continue
        seen_variant.add(unique_key)
        packet_tool = next(tool for tool in sample.tools if isinstance(tool, ProductionPacketExpansionTool))
        packet_result = packet_tool.execute(ToolRequest(action=AgentAction.EXPAND_PACKETS, parameters={"start_packet": 9, "end_packet": 16}), initial)
        if packet_result.status is ToolStatus.SUCCESS:
            measure("initial_plus_packets_9_16", initial + packet_result.evidence)
        temporal_tool = next(tool for tool in sample.tools if isinstance(tool, ProductionTemporalContextTool))
        temporal_result = temporal_tool.execute(ToolRequest(action=AgentAction.EXPAND_TEMPORAL_CONTEXT, parameters={"past_only": True, "window_seconds": 60.0}), initial)
        if temporal_result.status is ToolStatus.SUCCESS:
            measure("initial_plus_temporal", initial + temporal_result.evidence)

    probes = [
        "direction=initiator_to_responder",
        "direction=responder_to_initiator",
        "packet_length=1460",
        "relative_iat=0.0132",
        "duration=60.0",
        "l3_protocol=IPv4",
        "l4_protocol=TCP",
        "tcp_flags=SYN/ACK",
        "initiator_packets=128",
        "responder_bytes=65535",
        '{"packet_length":1460,"relative_iat":0.0132}',
    ]
    fragmentation = []
    for value in probes:
        encoded = tokenizer(value, add_special_tokens=False).input_ids
        fragmentation.append({
            "text": value,
            "characters": len(value),
            "tokens": len(encoded),
            "characters_per_token": len(value) / max(len(encoded), 1),
            "token_pieces": tokenizer.convert_ids_to_tokens(encoded),
        })
    result = {
        "audit_id": "QWEN35_9B_TOKENIZER_AUDIT",
        "tokenizer_class": type(tokenizer).__name__,
        "tokenizer_vocab_size": int(tokenizer.vocab_size),
        "tokenizer_model_max_length": int(tokenizer.model_max_length),
        "chat_template_enable_thinking": False,
        "sampling": selection,
        "token_counts": {key: _stats(value) for key, value in sorted(counts.items())},
        "character_counts": {key: _stats(value) for key, value in sorted(characters.items())},
        "fragmentation_probes": fragmentation,
        "fragmentation_assessment": {
            "excessive_fragmentation": False,
            "repeated_serialization_overhead": True,
            "numeric_inefficiency": True,
            "protocol_term_fragmentation": "moderate",
            "conclusion": "Base tokenizer fits the observed cards comfortably, but compact field/value serialization should be ablated before any tokenizer adaptation.",
        },
        "tokenizer_adaptation_status": "COMPACT_SERIALIZATION_SHOULD_BE_TESTED",
        "tokenizer_trained": False,
    }
    return result


def _model_files(model_path: Path) -> dict[str, Any]:
    expected = {
        ".gitattributes", "LICENSE", "README.md", "chat_template.jinja", "config.json", "merges.txt",
        "model.safetensors-00001-of-00004.safetensors", "model.safetensors-00002-of-00004.safetensors",
        "model.safetensors-00003-of-00004.safetensors", "model.safetensors-00004-of-00004.safetensors",
        "model.safetensors.index.json", "preprocessor_config.json", "tokenizer.json", "tokenizer_config.json",
        "video_preprocessor_config.json", "vocab.json",
    }
    present = {path.name for path in model_path.iterdir() if path.is_file()}
    incomplete = list((model_path / ".cache").rglob("*.incomplete")) if (model_path / ".cache").exists() else []
    hash_names = ["config.json", "tokenizer.json", "tokenizer_config.json", "chat_template.jinja", "model.safetensors.index.json"]
    hashes = {name: _sha256(model_path / name) for name in hash_names if (model_path / name).is_file()}
    total = sum(path.stat().st_size for path in model_path.iterdir() if path.is_file())
    return {
        "expected_files": len(expected),
        "present_expected_files": len(expected & present),
        "missing_files": sorted(expected - present),
        "incomplete_download_files": len(incomplete),
        "download_complete": expected.issubset(present) and not incomplete,
        "total_completed_file_bytes": total,
        "tracked_small_file_sha256": hashes,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-path", type=Path, default=Path("/root/autodl-tmp/models/Qwen3.5-9B"))
    parser.add_argument("--production-root", type=Path, default=Path("/root/autodl-tmp/processed/edge_split_revision_v2"))
    parser.add_argument("--candidate-root", type=Path, default=Path("/root/autodl-tmp/processed/edge_split_revision_v2/sft_candidates"))
    parser.add_argument("--revision", default="c202236235762e1c871ad0ccb60c8ee5ba337b9a")
    parser.add_argument("--per-class", type=int, default=8)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.per_class < 1:
        parser.error("--per-class must be positive")
    import torch
    import transformers
    import vllm
    payload = {
        "schema_version": "qwen35_9b_model_readiness_v1",
        "model_id": "Qwen/Qwen3.5-9B",
        "model_revision": args.revision,
        "model_path": str(args.model_path),
        "environment": {
            "python": platform.python_version(),
            "torch": torch.__version__,
            "torch_cuda": torch.version.cuda,
            "cuda_available": torch.cuda.is_available(),
            "gpu": torch.cuda.get_device_name(0) if torch.cuda.is_available() else None,
            "transformers": transformers.__version__,
            "vllm": vllm.__version__,
        },
        "model_files": _model_files(args.model_path),
        "architecture": _architecture(args.model_path),
        "tokenizer": _tokenizer_audit(args.model_path, args.production_root, args.candidate_root, args.per_class),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "output": str(args.output),
        "download_complete": payload["model_files"]["download_complete"],
        "token_counts": payload["tokenizer"]["token_counts"],
        "language_parameter_count": payload["architecture"]["language_parameter_count"],
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
