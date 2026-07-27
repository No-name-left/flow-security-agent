from __future__ import annotations

import json
from pathlib import Path

from flowsec.rag import build_knowledge_corpus, write_chunks_jsonl


def test_chunks_preserve_metadata_and_source_trace(tmp_path: Path) -> None:
    knowledge = tmp_path / "knowledge"
    knowledge.mkdir()
    document = knowledge / "tcp_behavior.md"
    document.write_text(
        """---
doc_id: tcp_behavior
title: TCP behavior evidence
category: protocol
source: https://example.invalid/standards/tcp
source_type: standard
version: "2026-01"
tags: [tcp, flow]
schema_scope: [netflow-v3]
---
# Evidence

Connection state, packet counts and byte direction can support a Flow-level judgment.

# Boundary

A single unusual flag pattern is insufficient without corroborating behavior.
""",
        encoding="utf-8",
    )
    chunks = build_knowledge_corpus(knowledge, max_chars=300, target_chars=120)

    assert chunks
    assert all(chunk.doc_id == "tcp_behavior" for chunk in chunks)
    assert all(chunk.source_file == "tcp_behavior.md" for chunk in chunks)
    assert all(chunk.source == "https://example.invalid/standards/tcp" for chunk in chunks)
    assert all(chunk.schema_scope == ["netflow-v3"] for chunk in chunks)
    assert all(len(chunk.content_sha256) == 64 for chunk in chunks)

    output = tmp_path / "chunks.jsonl"
    write_chunks_jsonl(output, chunks)
    rows = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()]
    assert rows[0]["source"] == "https://example.invalid/standards/tcp"
    assert rows[0]["metadata"]["tags"] == ["tcp", "flow"]
