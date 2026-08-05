#!/usr/bin/env python3
"""Statically inspect the public Qwen3.5 configuration and model source.

This script never downloads or loads model weights.  It is intended to freeze
the architecture facts used by the August 2026 model-resource audit and to
derive *candidate* LoRA target suffixes that must still be checked by the GPU
smoke test before formal training.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import re
from pathlib import Path


TEXT_TARGET_ALLOWLIST = {
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
}

VISION_ONLY_EXCLUSIONS = {"linear_fc1", "linear_fc2", "qkv", "proj"}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_linear_assignments(source: str) -> list[dict[str, object]]:
    tree = ast.parse(source)
    class_stack: list[str] = []
    rows: list[dict[str, object]] = []

    class Visitor(ast.NodeVisitor):
        def visit_ClassDef(self, node: ast.ClassDef) -> None:  # noqa: N802
            class_stack.append(node.name)
            self.generic_visit(node)
            class_stack.pop()

        def visit_Assign(self, node: ast.Assign) -> None:  # noqa: N802
            call = node.value
            if not isinstance(call, ast.Call):
                return self.generic_visit(node)
            func = call.func
            is_linear = (
                isinstance(func, ast.Attribute)
                and isinstance(func.value, ast.Name)
                and func.value.id == "nn"
                and func.attr == "Linear"
            )
            if not is_linear:
                return self.generic_visit(node)
            for target in node.targets:
                if (
                    isinstance(target, ast.Attribute)
                    and isinstance(target.value, ast.Name)
                    and target.value.id == "self"
                ):
                    rows.append(
                        {
                            "class": class_stack[-1] if class_stack else None,
                            "attribute": target.attr,
                            "line": node.lineno,
                        }
                    )
            self.generic_visit(node)

    Visitor().visit(tree)
    return rows


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    config = json.loads(args.config.read_text(encoding="utf-8"))
    source = args.source.read_text(encoding="utf-8")
    rows = parse_linear_assignments(source)
    attributes = sorted({str(row["attribute"]) for row in rows})
    candidates = sorted(set(attributes) & TEXT_TARGET_ALLOWLIST)
    vision_exclusions = sorted(set(attributes) & VISION_ONLY_EXCLUSIONS)
    text_config = config.get("text_config", config)
    vision_config = config.get("vision_config")
    report = {
        "inspection_type": "static_config_and_source_only",
        "weights_loaded": False,
        "config_path": str(args.config),
        "config_sha256": sha256(args.config),
        "source_path": str(args.source),
        "source_sha256": sha256(args.source),
        "architectures": config.get("architectures", []),
        "model_type": config.get("model_type"),
        "dtype": config.get("dtype") or config.get("torch_dtype") or text_config.get("dtype"),
        "is_multimodal_checkpoint": vision_config is not None,
        "text_config": {
            "hidden_size": text_config.get("hidden_size"),
            "num_hidden_layers": text_config.get("num_hidden_layers"),
            "intermediate_size": text_config.get("intermediate_size"),
            "vocab_size": text_config.get("vocab_size"),
            "max_position_embeddings": text_config.get("max_position_embeddings"),
            "layer_types": text_config.get("layer_types"),
        },
        "vision_config": None
        if vision_config is None
        else {
            "depth": vision_config.get("depth"),
            "hidden_size": vision_config.get("hidden_size"),
            "out_hidden_size": vision_config.get("out_hidden_size"),
        },
        "linear_assignments": rows,
        "candidate_text_lora_target_suffixes": candidates,
        "vision_only_suffixes_excluded": vision_exclusions,
        "source_declares_text_only_classes": bool(
            re.search(r"class\s+Qwen3_5TextModel\b", source)
            and re.search(r"class\s+Qwen3_5ForCausalLM\b", source)
        ),
        "caveat": (
            "Suffixes are static candidates, not a successful-load claim. "
            "Run qwen35_9b_5090_smoke_test.py with the intended checkpoint "
            "and software stack before freezing LoRA targets."
        ),
    }
    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
