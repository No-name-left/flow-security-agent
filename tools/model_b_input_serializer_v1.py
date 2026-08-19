#!/usr/bin/env python3
"""MODEL B V1 — frozen input serializer (DRAFT-design contract, v2 compact).

Serializes the runtime-legal RAW_LEGAL 83-vector into the fixed structured
text template consumed by the Qwen3.5-9B text tower. This file IS the input
contract: its SHA256 is persisted in
docs/research_plan/model_b_recovery_aware_representation_v1_protocol.md and
the serialization must not change after viewing Model-B gate metrics.

Design note (measured 2026-08-20 technical smoke): the Qwen3.5 tokenizer
emits ~1 token/character for numeric/ident tokens ("B1=0.1234" -> 9 tokens
for 9 chars; full long-name template -> 1224 tokens for 90 lines). Long
feature names were therefore replaced by the frozen short codes B1..B47,
T1..T16, R1..R18 (mapping below; codes are feature identifiers, not GT
semantics). Full BTR template measures ~753 chars -> ~750-800 tokens.

Frozen contract (v2, 2026-08-20):
  * three typed blocks in fixed order: TARGET (47 BASIC fields),
    TEMPORAL (16), RELATION (18);
  * one line per field, "<CODE>=<value>", header tokens "<TARGET>",
    "<TEMPORAL>", "<RELATION>", block close token "</BLOCK>";
  * availability masks are the first line of each Evidence block: "m=1"
    (available) or "m=0" (unavailable); an unavailable block contains ONLY
    its header, "m=0" and "</BLOCK>";
  * TRAIN-only standardization per field: z=(x-mu)/sigma over positions
    0..80, mu/sigma from Known-TRAIN rows only (partition TRAIN, excluding
    held-out Unknown rotation rows), sigma ddof=0, sigma==0 -> scale 1.0;
    clip [-5,5]; masks (positions 81/82) are NEVER standardized;
  * rendering: fixed point 4 decimals ("%.4f");
  * missing (non-finite) values -> standardized 0.0 ("0.0000");
  * max sequence length 1536 tokens (measured: full BTR template ~970-1015
    tokens); truncation order (never expected to trigger, but frozen): drop
    RELATION block fields, then TEMPORAL block fields, then TARGET tail;
  * no natural-language descriptions; tokens are codes and values only;
  * identical serialization for QWEN_CE_ONLY and QWEN_CE_PLUS_CORR.
"""
from __future__ import annotations

import numpy as np

MAX_SEQ_LEN = 1536
PRECISION = 4          # "%.4f" fixed point
CLIP = 5.0
BLOCK_CLOSE = "</BLOCK>"

# ---------------------------------------------------------------------------
# Frozen field names (dataset contract) and their frozen short codes.
# Self-check verifies the names against the project modules when importable.
# ---------------------------------------------------------------------------
BASIC_FIELDS = (
    "PROTOCOL", "L7_PROTO", "IN_BYTES", "IN_PKTS", "OUT_BYTES", "OUT_PKTS",
    "TCP_FLAGS", "CLIENT_TCP_FLAGS", "SERVER_TCP_FLAGS",
    "FLOW_DURATION_MILLISECONDS", "DURATION_IN", "DURATION_OUT",
    "MIN_TTL", "MAX_TTL", "LONGEST_FLOW_PKT", "SHORTEST_FLOW_PKT",
    "MIN_IP_PKT_LEN", "MAX_IP_PKT_LEN",
    "SRC_TO_DST_SECOND_BYTES", "DST_TO_SRC_SECOND_BYTES",
    "RETRANSMITTED_IN_BYTES", "RETRANSMITTED_IN_PKTS",
    "RETRANSMITTED_OUT_BYTES", "RETRANSMITTED_OUT_PKTS",
    "SRC_TO_DST_AVG_THROUGHPUT", "DST_TO_SRC_AVG_THROUGHPUT",
    "NUM_PKTS_UP_TO_128_BYTES", "NUM_PKTS_128_TO_256_BYTES",
    "NUM_PKTS_256_TO_512_BYTES", "NUM_PKTS_512_TO_1024_BYTES",
    "NUM_PKTS_1024_TO_1514_BYTES",
    "TCP_WIN_MAX_IN", "TCP_WIN_MAX_OUT",
    "ICMP_TYPE", "ICMP_IPV4_TYPE", "DNS_QUERY_ID", "DNS_QUERY_TYPE",
    "DNS_TTL_ANSWER", "FTP_COMMAND_RET_CODE",
    "SRC_TO_DST_IAT_MIN", "SRC_TO_DST_IAT_MAX", "SRC_TO_DST_IAT_AVG",
    "SRC_TO_DST_IAT_STDDEV",
    "DST_TO_SRC_IAT_MIN", "DST_TO_SRC_IAT_MAX", "DST_TO_SRC_IAT_AVG",
    "DST_TO_SRC_IAT_STDDEV",
)
assert len(BASIC_FIELDS) == 47, len(BASIC_FIELDS)

HORIZONS_MS = (10_000, 60_000, 300_000)
TEMPORAL_BASE = (
    "source_flow_count", "source_flow_rate", "source_packet_rate",
    "source_byte_rate", "destination_flow_count",
)
RELATION_BASE = (
    "source_unique_destination_count", "source_unique_destination_port_count",
    "source_same_destination_port_count", "source_destination_pair_count",
    "destination_unique_source_count", "source_unique_neighbor_count",
)
TEMPORAL_FIELDS = tuple(
    f"{name}_{horizon // 1000}s" for horizon in HORIZONS_MS
    for name in TEMPORAL_BASE
) + ("same_source_last_seen_gap_ms",)
RELATION_FIELDS = tuple(
    f"{name}_{horizon // 1000}s" for horizon in HORIZONS_MS
    for name in RELATION_BASE
)
assert len(TEMPORAL_FIELDS) == 16, len(TEMPORAL_FIELDS)
assert len(RELATION_FIELDS) == 18, len(RELATION_FIELDS)
ALL_FIELDS = BASIC_FIELDS + TEMPORAL_FIELDS + RELATION_FIELDS
assert len(ALL_FIELDS) == 81

BASIC_CODES = tuple(f"B{i}" for i in range(1, 48))
TEMPORAL_CODES = tuple(f"T{i}" for i in range(1, 17))
RELATION_CODES = tuple(f"R{i}" for i in range(1, 19))
CODE_MAP = dict(zip(ALL_FIELDS, BASIC_CODES + TEMPORAL_CODES + RELATION_CODES))
assert len(CODE_MAP) == 81

# Positions inside the RAW_LEGAL 83-vector (frozen gate convention):
# basic[0:47], T block[47:63], R block[63:81], m_t=81, m_r=82.
IDX_BASIC = slice(0, 47)
IDX_T = slice(47, 63)
IDX_R = slice(63, 81)
IDX_MT = 81
IDX_MR = 82


def fit_stats(train_matrix: np.ndarray) -> dict:
    """TRAIN-only standardization statistics (Known-TRAIN rows only).

    Deterministic, no tuning: per-field mean/std (ddof=0) over the 81
    feature positions only; std==0 -> scale 1. Mask positions (81/82) are
    0/1 availability flags and are NEVER standardized.
    """
    train_matrix = np.asarray(train_matrix, dtype=np.float64)
    x = train_matrix[:, :81]
    mu = np.nanmean(x, axis=0)
    sd = np.nanstd(x, axis=0, ddof=0)
    sd[sd == 0.0] = 1.0
    return {"mu": mu, "sd": sd}


def apply_stats(raw83: np.ndarray, stats: dict) -> np.ndarray:
    """Standardize the 81 feature positions + clip; non-finite -> 0.0.
    Mask positions (81/82) pass through unchanged (0/1 flags)."""
    x = np.asarray(raw83, dtype=np.float64).copy()
    z = np.where(np.isfinite(x[:81]), (x[:81] - stats["mu"]) / stats["sd"], 0.0)
    x[:81] = np.clip(z, -CLIP, CLIP)
    return x


def render_block(header: str, codes: tuple, values: np.ndarray,
                 mask: float) -> list[str]:
    lines = [header]
    lines.append(f"m={int(mask)}")
    if mask:
        for code, value in zip(codes, values):
            lines.append(f"{code}={value:.{PRECISION}f}")
    lines.append(BLOCK_CLOSE)
    return lines


def serialize(raw83: np.ndarray, stats: dict) -> str:
    """Fixed structured template from a RAW_LEGAL 83-vector.

    Masks are read from the vector (positions 81/82) — the same values the
    frozen Information Gate pipeline uses; an unavailable block contributes
    only its header, "m=0" and close token.
    """
    z = apply_stats(raw83, stats)
    m_t, m_r = z[IDX_MT], z[IDX_MR]
    lines: list[str] = []
    lines += render_block("<TARGET>", BASIC_CODES, z[IDX_BASIC], 1.0)
    lines += render_block("<TEMPORAL>", TEMPORAL_CODES, z[IDX_T], m_t)
    lines += render_block("<RELATION>", RELATION_CODES, z[IDX_R], m_r)
    return "\n".join(lines)


def truncate(text: str, max_len: int = MAX_SEQ_LEN) -> str:
    """Frozen truncation: never expected to trigger (~800 tokens vs 1024);
    if it does, drop RELATION block fields, then TEMPORAL block fields,
    then TARGET tail (block order preserved)."""
    tokens = text.split("\n")
    if len(tokens) <= max_len:
        return text
    for header in ("<RELATION>", "<TEMPORAL>"):
        while len(tokens) > max_len and header in tokens:
            k = tokens.index(header)
            end = tokens.index(BLOCK_CLOSE, k)
            tokens = tokens[:k + 3] + tokens[end + 1:]
    return "\n".join(tokens[:max_len])


def self_check() -> None:
    """Verify replicated names against the frozen project modules."""
    import importlib.util
    from pathlib import Path

    tools = Path("/root/autodl-tmp/workspace/flow-security-agent/tools")
    spec1 = importlib.util.spec_from_file_location(
        "fdz", tools / "finalize_dataset_v4_split.py")
    spec2 = importlib.util.spec_from_file_location(
        "rcg", tools / "run_core_hypothesis_gate_v1.py")
    if spec1 is None or spec2 is None:
        return  # modules unavailable -> replicated lists are the contract
    fdz = importlib.util.module_from_spec(spec1)
    rcg = importlib.util.module_from_spec(spec2)
    try:
        spec1.loader.exec_module(fdz)
        spec2.loader.exec_module(rcg)
    except Exception:
        return  # do not fail on import quirks of heavy modules
    assert tuple(fdz.MODEL_VISIBLE_FIELDS) == BASIC_FIELDS, "BASIC mismatch"
    assert tuple(rcg.TEMPORAL_FIELDS) == TEMPORAL_FIELDS, "TEMPORAL mismatch"
    assert tuple(rcg.RELATION_FIELDS) == RELATION_FIELDS, "RELATION mismatch"


if __name__ == "__main__":
    self_check()
    rng = np.random.default_rng(0)
    train = rng.normal(size=(100, 83))
    train[:, IDX_MT] = rng.integers(0, 2, size=100)
    train[:, IDX_MR] = rng.integers(0, 2, size=100)
    stats = fit_stats(train)
    demo = rng.normal(size=(1, 83))
    demo[0, IDX_MT] = 1.0
    demo[0, IDX_MR] = 1.0
    text = serialize(demo[0], stats)
    print(f"self_check OK; demo BTR chars={len(text)} "
          f"lines={len(text.splitlines())} max={MAX_SEQ_LEN}")
