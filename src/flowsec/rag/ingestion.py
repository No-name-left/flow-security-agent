from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field

from flowsec.llm.fingerprint import sha256_text


class KnowledgeMetadata(BaseModel):
    """Required provenance for one knowledge document."""

    model_config = ConfigDict(extra="allow", frozen=True)

    doc_id: str = Field(min_length=1, pattern=r"^[a-z0-9][a-z0-9_.-]*$")
    title: str = Field(min_length=1)
    category: str = Field(min_length=1)
    source: str = Field(min_length=1)
    source_type: str = Field(min_length=1)
    version: str = Field(default="1", min_length=1)
    tags: list[str] = Field(default_factory=list)
    schema_scope: list[str] = Field(default_factory=list)


class KnowledgeDocument(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    metadata: KnowledgeMetadata
    body: str = Field(min_length=1)
    source_file: str = Field(min_length=1)


class RagChunk(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    chunk_id: str
    chunk_index: int = Field(ge=1)
    doc_id: str
    title: str
    category: str
    source: str
    source_type: str
    source_file: str
    document_version: str
    tags: list[str]
    schema_scope: list[str]
    text: str
    content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    metadata: dict[str, Any]


def parse_knowledge_document(path: Path, knowledge_root: Path | None = None) -> KnowledgeDocument:
    text = path.read_text(encoding="utf-8-sig").replace("\r\n", "\n").replace("\r", "\n")
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        raise ValueError(f"missing YAML front matter: {path}")
    try:
        closing = next(index for index, line in enumerate(lines[1:], start=1) if line.strip() == "---")
    except StopIteration as exc:
        raise ValueError(f"missing closing YAML front matter: {path}") from exc
    raw_metadata = yaml.safe_load("\n".join(lines[1:closing]))
    if not isinstance(raw_metadata, dict):
        raise ValueError(f"front matter must be a mapping: {path}")
    body = "\n".join(lines[closing + 1 :]).strip()
    if not body:
        raise ValueError(f"knowledge document is empty: {path}")
    root = path.parent if knowledge_root is None else knowledge_root
    try:
        source_file = path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        source_file = path.name
    return KnowledgeDocument(
        metadata=KnowledgeMetadata.model_validate(raw_metadata),
        body=body,
        source_file=source_file,
    )


def _split_units(body: str) -> list[str]:
    units: list[str] = []
    current: list[str] = []
    for line in body.splitlines():
        if line.startswith("#") or not line.strip():
            if current:
                units.append("\n".join(current).strip())
                current = []
            if line.startswith("#"):
                units.append(line.strip())
            continue
        current.append(line.rstrip())
    if current:
        units.append("\n".join(current).strip())
    return [unit for unit in units if unit]


def _split_long_unit(unit: str, max_chars: int) -> list[str]:
    if len(unit) <= max_chars:
        return [unit]
    words = re.split(r"(\s+)", unit)
    parts: list[str] = []
    current = ""
    for word in words:
        if current and len(current) + len(word) > max_chars:
            parts.append(current.strip())
            current = word
        else:
            current += word
    if current.strip():
        parts.append(current.strip())
    return parts


def build_chunks_for_document(
    path: Path,
    *,
    knowledge_root: Path,
    max_chars: int = 1600,
    target_chars: int = 1000,
) -> list[RagChunk]:
    if max_chars < 200:
        raise ValueError("max_chars must be at least 200")
    if not 100 <= target_chars <= max_chars:
        raise ValueError("target_chars must satisfy 100 <= target_chars <= max_chars")
    document = parse_knowledge_document(path, knowledge_root)
    units = [
        part
        for unit in _split_units(document.body)
        for part in _split_long_unit(unit, max_chars)
    ]
    texts: list[str] = []
    current: list[str] = []
    for unit in units:
        candidate = "\n\n".join([*current, unit])
        if current and len(candidate) > max_chars:
            texts.append("\n\n".join(current).strip())
            current = [unit]
        else:
            current.append(unit)
        if len("\n\n".join(current)) >= target_chars:
            texts.append("\n\n".join(current).strip())
            current = []
    if current:
        tail = "\n\n".join(current).strip()
        if texts and len(texts[-1]) + len(tail) + 2 <= max_chars:
            texts[-1] = f"{texts[-1]}\n\n{tail}"
        else:
            texts.append(tail)

    metadata = document.metadata
    metadata_dump = metadata.model_dump(mode="json")
    return [
        RagChunk(
            chunk_id=f"{metadata.doc_id}__{index:03d}",
            chunk_index=index,
            doc_id=metadata.doc_id,
            title=metadata.title,
            category=metadata.category,
            source=metadata.source,
            source_type=metadata.source_type,
            source_file=document.source_file,
            document_version=metadata.version,
            tags=metadata.tags,
            schema_scope=metadata.schema_scope,
            text=text,
            content_sha256=sha256_text(text),
            metadata=metadata_dump,
        )
        for index, text in enumerate(texts, start=1)
    ]


def build_knowledge_corpus(
    knowledge_dir: Path,
    *,
    max_chars: int = 1600,
    target_chars: int = 1000,
) -> list[RagChunk]:
    paths = sorted(path for path in knowledge_dir.rglob("*.md") if path.is_file())
    chunks: list[RagChunk] = []
    seen_docs: set[str] = set()
    for path in paths:
        document_chunks = build_chunks_for_document(
            path,
            knowledge_root=knowledge_dir,
            max_chars=max_chars,
            target_chars=target_chars,
        )
        if not document_chunks:
            continue
        doc_id = document_chunks[0].doc_id
        if doc_id in seen_docs:
            raise ValueError(f"duplicate doc_id {doc_id!r}: {path}")
        seen_docs.add(doc_id)
        chunks.extend(document_chunks)
    return chunks


def write_chunks_jsonl(path: Path, chunks: list[RagChunk]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = "".join(
        json.dumps(chunk.model_dump(mode="json"), ensure_ascii=False, sort_keys=True) + "\n"
        for chunk in chunks
    )
    path.write_text(text, encoding="utf-8")
