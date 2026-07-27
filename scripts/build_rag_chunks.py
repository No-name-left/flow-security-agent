#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from flowsec.rag.ingestion import build_knowledge_corpus, write_chunks_jsonl  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build source-traceable RAG chunks from Flow security knowledge documents."
    )
    parser.add_argument("--knowledge-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--max-chars", type=int, default=1600)
    parser.add_argument("--target-chars", type=int, default=1000)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    chunks = build_knowledge_corpus(
        args.knowledge_dir,
        max_chars=args.max_chars,
        target_chars=args.target_chars,
    )
    write_chunks_jsonl(args.output, chunks)
    print(f"wrote {len(chunks)} chunks to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
