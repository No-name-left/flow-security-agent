from __future__ import annotations

import hashlib
import json
import math
import os
import re
import urllib.request
from collections import Counter
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Iterable, Protocol

from pydantic import Field, field_validator

from flowsec.runtime.contracts import validate_model_visible_value

from .contracts import (
    RAG_EVIDENCE_SCHEMA_VERSION,
    EvidenceDomain,
    EvidenceEnvelope,
    EvidenceTrustV1,
    FrozenModel,
    canonical_json,
    content_digest,
)


RAG_KB_VERSION = "NEAR_GENERIC_SECURITY_KB_V1"
RAG_INDEX_VERSION = "NEAR_HYBRID_RAG_INDEX_V1"
RAG_CHUNKING_VERSION = "PARAGRAPH_WORD_WINDOW_160_32_V1"
DEFAULT_EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
DEFAULT_EMBEDDING_REVISION = "c9745ed1d9f207416be6d2e6f8de32d1f16199bf"
_TOKEN = re.compile(r"[a-z][a-z0-9_-]{1,40}")
_PROHIBITED_QUERY_TERMS = re.compile(
    r"(?i)(?:fs1_[0-9a-f]{40}|edge[-_ ]?iiot|capture|dataset|k[_ -]?known|u[_ -]?(?:dev|final)|"
    r"fine[_ -]?label|ground[_ -]?truth|(?:\d{1,3}\.){3}\d{1,3})"
)
_U_FINAL_TERMS = re.compile(r"(?i)\b(?:xss|cross[- ]site scripting|ddos[_ -]?udp|udp flood)\b")


class KnowledgeSourceV1(FrozenModel):
    source_id: str = Field(pattern=r"^src_[a-z0-9_]{3,64}$")
    title: str = Field(min_length=3, max_length=180)
    source_type: str = Field(min_length=2, max_length=40)
    url: str = Field(pattern=r"^https://")
    topics: tuple[str, ...]
    license_note: str = Field(min_length=3, max_length=240)


class KnowledgeChunkV1(FrozenModel):
    chunk_id: str = Field(pattern=r"^kb_[0-9a-f]{24}$")
    source_id: str = Field(pattern=r"^src_[a-z0-9_]{3,64}$")
    title: str
    source_type: str
    text: str = Field(min_length=40, max_length=2400)
    source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    ordinal: int = Field(ge=0)


class RagEvidenceV1(FrozenModel):
    source_id: str = Field(pattern=r"^src_[a-z0-9_]{3,64}$")
    source_title: str = Field(min_length=3, max_length=180)
    source_type: str = Field(min_length=2, max_length=40)
    retrieved_text: str = Field(min_length=40, max_length=2400)
    retrieval_score: float
    schema_version: str = RAG_EVIDENCE_SCHEMA_VERSION

    @field_validator("retrieved_text")
    @classmethod
    def safe_text(cls, value: str) -> str:
        validate_model_visible_value(value, location="rag.retrieved_text")
        return value


class _VisibleTextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.hidden_depth = 0
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, _attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style", "svg", "nav", "footer"}:
            self.hidden_depth += 1
        elif not self.hidden_depth and tag in {"p", "li", "h1", "h2", "h3", "pre", "br"}:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "svg", "nav", "footer"} and self.hidden_depth:
            self.hidden_depth -= 1
        elif not self.hidden_depth and tag in {"p", "li", "h1", "h2", "h3", "pre"}:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self.hidden_depth:
            self.parts.append(data)


def _normalize_document(raw: bytes, content_type: str) -> str:
    text = raw.decode("utf-8", errors="replace")
    if "html" in content_type.casefold() or "<html" in text[:1000].casefold():
        parser = _VisibleTextParser()
        parser.feed(text)
        text = " ".join(parser.parts)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n\n", text)
    return text.strip()


def fetch_source(source: KnowledgeSourceV1, *, timeout_seconds: float = 30.0) -> bytes:
    request = urllib.request.Request(
        source.url,
        headers={"User-Agent": "flow-security-agent-rag-builder/1.0"},
    )
    with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
        raw = response.read(8 * 1024 * 1024 + 1)
        if len(raw) > 8 * 1024 * 1024:
            raise ValueError(f"RAG source exceeds 8 MiB bound: {source.source_id}")
        content_type = str(response.headers.get("Content-Type", ""))
    return _normalize_document(raw, content_type).encode("utf-8")


def chunk_document(
    source: KnowledgeSourceV1,
    document: bytes,
    *,
    window_words: int = 160,
    overlap_words: int = 32,
) -> list[KnowledgeChunkV1]:
    if window_words < 40 or overlap_words < 0 or overlap_words >= window_words:
        raise ValueError("invalid RAG chunking bounds")
    source_sha = hashlib.sha256(document).hexdigest()
    words = document.decode("utf-8", errors="replace").split()
    chunks: list[KnowledgeChunkV1] = []
    step = window_words - overlap_words
    for ordinal, start in enumerate(range(0, len(words), step)):
        text = " ".join(words[start : start + window_words]).strip()[:2400].rstrip()
        if len(text) < 40:
            continue
        # U_final is prohibited from pre-training design and source indexing.
        if _U_FINAL_TERMS.search(text):
            continue
        try:
            validate_model_visible_value(text, location=f"rag_source.{source.source_id}")
        except ValueError:
            # Do not normalize source identities into model-visible text: omit the
            # bounded chunk and preserve the source hash/ordinal audit trail.
            continue
        chunk_id = "kb_" + content_digest(
            [RAG_KB_VERSION, source.source_id, source_sha, ordinal, text]
        )[:24]
        chunks.append(
            KnowledgeChunkV1(
                chunk_id=chunk_id,
                source_id=source.source_id,
                title=source.title,
                source_type=source.source_type,
                text=text,
                source_sha256=source_sha,
                ordinal=ordinal,
            )
        )
    return chunks


def tokenize(text: str) -> list[str]:
    return _TOKEN.findall(text.casefold())


@dataclass(frozen=True, slots=True)
class BM25Index:
    documents: tuple[Counter[str], ...]
    document_lengths: tuple[int, ...]
    document_frequency: Counter[str]
    average_length: float
    k1: float = 1.5
    b: float = 0.75

    @classmethod
    def build(cls, texts: Iterable[str], *, k1: float = 1.5, b: float = 0.75) -> "BM25Index":
        docs = tuple(Counter(tokenize(text)) for text in texts)
        if not docs:
            raise ValueError("BM25 index requires documents")
        lengths = tuple(sum(doc.values()) for doc in docs)
        frequency: Counter[str] = Counter()
        for doc in docs:
            frequency.update(doc.keys())
        return cls(docs, lengths, frequency, sum(lengths) / len(lengths), k1, b)

    def scores(self, query: str) -> list[float]:
        query_terms = tokenize(query)
        count = len(self.documents)
        output = [0.0] * count
        for term in query_terms:
            df = self.document_frequency.get(term, 0)
            if not df:
                continue
            inverse = math.log(1.0 + (count - df + 0.5) / (df + 0.5))
            for index, doc in enumerate(self.documents):
                frequency = doc.get(term, 0)
                if not frequency:
                    continue
                norm = self.k1 * (
                    1.0 - self.b + self.b * self.document_lengths[index] / self.average_length
                )
                output[index] += inverse * frequency * (self.k1 + 1.0) / (frequency + norm)
        return output


class DenseEmbedder(Protocol):
    model_id: str
    revision: str

    def encode(self, texts: list[str]) -> Any: ...


class TransformersDenseEmbedder:
    def __init__(self, model_path: str | Path, *, model_id: str, revision: str):
        import torch
        from transformers import AutoModel, AutoTokenizer

        self.model_id = model_id
        self.revision = revision
        self._torch = torch
        self._tokenizer = AutoTokenizer.from_pretrained(str(model_path), local_files_only=True)
        self._model = AutoModel.from_pretrained(str(model_path), local_files_only=True)
        self._model.eval()

    def encode(self, texts: list[str]) -> Any:
        torch = self._torch
        batches = []
        with torch.inference_mode():
            for start in range(0, len(texts), 64):
                encoded = self._tokenizer(
                    texts[start : start + 64],
                    padding=True,
                    truncation=True,
                    max_length=256,
                    return_tensors="pt",
                )
                hidden = self._model(**encoded).last_hidden_state
                mask = encoded["attention_mask"].unsqueeze(-1).to(hidden.dtype)
                pooled = (hidden * mask).sum(dim=1) / mask.sum(dim=1).clamp_min(1.0)
                pooled = torch.nn.functional.normalize(pooled, p=2, dim=1)
                batches.append(pooled.cpu().numpy())
        import numpy as np

        return np.concatenate(batches, axis=0)


def validate_safe_query(query: str) -> str:
    query = re.sub(r"\s+", " ", query).strip()
    if not 8 <= len(query) <= 500:
        raise ValueError("RAG query must be bounded and meaningful")
    if _PROHIBITED_QUERY_TERMS.search(query) or _U_FINAL_TERMS.search(query):
        raise ValueError("RAG query contains backend, identity, label, or U_final material")
    validate_model_visible_value(query, location="rag.query")
    return query


def build_safe_query(*, visible_evidence_summary: str, evidence_gap: str) -> str:
    return validate_safe_query(
        f"Network security protocol behavior: {visible_evidence_summary}. "
        f"Relevant generic interpretation for this evidence gap: {evidence_gap}."
    )


def rag_envelope(chunk: KnowledgeChunkV1, *, score: float) -> EvidenceEnvelope:
    value = RagEvidenceV1(
        source_id=chunk.source_id,
        source_title=chunk.title,
        source_type=chunk.source_type,
        retrieved_text=chunk.text,
        retrieval_score=round(float(score), 6),
    )
    return EvidenceEnvelope(
        evidence_id="ev_knowledge_" + content_digest([chunk.chunk_id, score])[:20],
        evidence_type="knowledge",
        domain=EvidenceDomain.KNOWLEDGE,
        trust=EvidenceTrustV1.UNTRUSTED_KNOWLEDGE,
        content=value.model_dump(mode="json"),
        provenance=f"rag:{RAG_INDEX_VERSION}",
        metadata={"chunk_id": chunk.chunk_id, "knowledge_not_observation": True},
    )


class HybridRagIndex:
    def __init__(self, chunks: list[KnowledgeChunkV1], embeddings: Any, embedder: DenseEmbedder):
        import numpy as np

        if len(chunks) == 0 or tuple(embeddings.shape)[0] != len(chunks):
            raise ValueError("RAG chunks and embeddings disagree")
        self.chunks = chunks
        self.embeddings = np.asarray(embeddings, dtype="float32")
        self.embedder = embedder
        self.bm25 = BM25Index.build(item.text for item in chunks)

    def retrieve(self, query: str, *, top_k: int = 4) -> list[tuple[KnowledgeChunkV1, float]]:
        import numpy as np

        query = validate_safe_query(query)
        if not 1 <= top_k <= 20:
            raise ValueError("RAG top_k must be in 1..20")
        dense = np.asarray(self.embedder.encode([query])[0], dtype="float32")
        dense_scores = self.embeddings @ dense
        lexical = np.asarray(self.bm25.scores(query), dtype="float32")

        def normalized(values: Any) -> Any:
            low, high = float(values.min()), float(values.max())
            return (values - low) / (high - low) if high > low else np.zeros_like(values)

        scores = 0.55 * normalized(dense_scores) + 0.45 * normalized(lexical)
        order = sorted(range(len(self.chunks)), key=lambda i: (-float(scores[i]), self.chunks[i].chunk_id))
        return [(self.chunks[index], float(scores[index])) for index in order[:top_k]]

    def retrieve_many(
        self, queries: list[str], *, top_k: int = 4
    ) -> list[list[tuple[KnowledgeChunkV1, float]]]:
        import numpy as np

        safe_queries = [validate_safe_query(query) for query in queries]
        if not 1 <= top_k <= 20:
            raise ValueError("RAG top_k must be in 1..20")
        if not safe_queries:
            return []
        dense_queries = np.asarray(self.embedder.encode(safe_queries), dtype="float32")
        output: list[list[tuple[KnowledgeChunkV1, float]]] = []
        for query, dense in zip(safe_queries, dense_queries, strict=True):
            dense_scores = self.embeddings @ dense
            lexical = np.asarray(self.bm25.scores(query), dtype="float32")

            def normalized(values: Any) -> Any:
                low, high = float(values.min()), float(values.max())
                return (values - low) / (high - low) if high > low else np.zeros_like(values)

            scores = 0.55 * normalized(dense_scores) + 0.45 * normalized(lexical)
            order = sorted(
                range(len(self.chunks)),
                key=lambda index: (-float(scores[index]), self.chunks[index].chunk_id),
            )
            output.append(
                [(self.chunks[index], float(scores[index])) for index in order[:top_k]]
            )
        return output


def load_source_manifest(path: Path) -> list[KnowledgeSourceV1]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    sources = [KnowledgeSourceV1.model_validate(item) for item in value.get("sources", [])]
    if len(sources) < 20 or len({item.source_id for item in sources}) != len(sources):
        raise ValueError("formal RAG V1 requires at least twenty unique authoritative sources")
    return sources


def _atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True), encoding="utf-8")
    os.replace(temporary, path)


def build_rag_index(
    source_manifest: Path,
    output_root: Path,
    *,
    embedder: DenseEmbedder,
    retrieved_at: str,
) -> dict[str, Any]:
    import numpy as np

    sources = load_source_manifest(source_manifest)
    documents: dict[str, bytes] = {}
    chunks: list[KnowledgeChunkV1] = []
    for source in sources:
        document = fetch_source(source)
        documents[source.source_id] = document
        chunks.extend(chunk_document(source, document))
    if len(chunks) < 100:
        raise ValueError("formal RAG V1 produced too few safe generic chunks")
    embeddings = np.asarray(embedder.encode([item.text for item in chunks]), dtype="float32")
    if embeddings.ndim != 2 or embeddings.shape[0] != len(chunks):
        raise ValueError("dense embedding output shape is invalid")

    output_root = Path(output_root)
    document_root = output_root / "documents"
    document_root.mkdir(parents=True, exist_ok=True)
    document_hashes: dict[str, str] = {}
    for source_id, document in documents.items():
        target = document_root / f"{source_id}.txt"
        target.write_bytes(document)
        document_hashes[source_id] = hashlib.sha256(document).hexdigest()
    chunks_path = output_root / "chunks.jsonl"
    chunks_path.write_text(
        "".join(canonical_json(item.model_dump(mode="json")) + "\n" for item in chunks),
        encoding="utf-8",
    )
    embeddings_path = output_root / "dense_embeddings.npy"
    np.save(embeddings_path, embeddings, allow_pickle=False)
    chunk_digest = content_digest([item.model_dump(mode="json") for item in chunks])
    manifest = {
        "status": "PASS",
        "kb_version": RAG_KB_VERSION,
        "index_version": RAG_INDEX_VERSION,
        "evidence_schema_version": RAG_EVIDENCE_SCHEMA_VERSION,
        "retrieved_at": retrieved_at,
        "source_count": len(sources),
        "source_manifest_sha256": hashlib.sha256(Path(source_manifest).read_bytes()).hexdigest(),
        "document_hashes": document_hashes,
        "chunking_version": RAG_CHUNKING_VERSION,
        "chunk_count": len(chunks),
        "chunk_digest": chunk_digest,
        "u_final_term_hits": 0,
        "embedding_model": embedder.model_id,
        "embedding_revision": embedder.revision,
        "embedding_dimensions": int(embeddings.shape[1]),
        "bm25": {"k1": 1.5, "b": 0.75},
        "hybrid_weights": {"dense": 0.55, "bm25": 0.45},
        "top_k_default": 4,
        "artifacts": {
            "chunks": hashlib.sha256(chunks_path.read_bytes()).hexdigest(),
            "embeddings": hashlib.sha256(embeddings_path.read_bytes()).hexdigest(),
        },
        "scope": "generic public security knowledge; no Edge-IIoTset or U_final design inputs",
    }
    manifest["artifact_digest"] = content_digest(manifest["artifacts"])
    _atomic_json(output_root / "manifest.json", manifest)
    return manifest


def load_rag_index(output_root: Path, *, embedder: DenseEmbedder) -> HybridRagIndex:
    import numpy as np

    output_root = Path(output_root)
    chunks = [
        KnowledgeChunkV1.model_validate_json(line)
        for line in (output_root / "chunks.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    embeddings = np.load(output_root / "dense_embeddings.npy", allow_pickle=False)
    return HybridRagIndex(chunks, embeddings, embedder)
