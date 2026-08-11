from __future__ import annotations

import json
import os
from pathlib import Path

import pytest


ARTIFACT_ROOT_ENV = "ARTIFACT_ROOT"


def _configured_root() -> Path | None:
    configured = os.environ.get(ARTIFACT_ROOT_ENV)
    return Path(configured) / "near_pretraining_v1" if configured else None


def _available(root: Path | None) -> bool:
    if root is None:
        return False
    try:
        return (root / "manifests/application_payload_manifest.json").is_file()
    except OSError:
        return False


@pytest.fixture(scope="module")
def real_root() -> Path:
    root = _configured_root()
    if not _available(root):
        pytest.skip(f"Git-external Near pre-training assets unavailable; configure {ARTIFACT_ROOT_ENV}")
    assert root is not None
    return root


def test_real_application_payload_and_rag_manifests(real_root: Path) -> None:
    sidecars = json.loads(
        (real_root / "manifests/application_payload_manifest.json").read_text()
    )
    assert sidecars["status"] == "PASS"
    assert sidecars["candidate_sessions"] == 16979
    assert sidecars["capture_count"] == 20
    assert sidecars["payload_shortcut_risk"] == "LOW"
    assert sidecars["u_final_count"] == 0
    assert all(
        item["materializer_version"] == "near_application_payload_materializer_v5"
        for item in sidecars["checkpoints"]
    )

    rag = json.loads((real_root / "rag/manifest.json").read_text())
    assert rag["status"] == "PASS"
    assert rag["source_count"] >= 20
    assert rag["chunk_count"] >= 100
    assert rag["u_final_term_hits"] == 0


def test_real_snapshot_and_rl_scope_when_materialized(real_root: Path) -> None:
    path = real_root / "manifests/snapshot_corpus_rl_manifest.json"
    if not path.is_file():
        pytest.skip("snapshot universe is not materialized yet")
    manifest = json.loads(path.read_text())
    assert manifest["status"] == "PASS"
    assert manifest["candidate_sessions"] == 16979
    assert manifest["unique_sessions"] == 16979
    assert manifest["primary_count"] == 16979
    assert manifest["rl_prompt_pool"]["count"] == 6000
    assert manifest["validation_count"] == 0
    assert manifest["test_count"] == 0
    assert manifest["u_dev_count"] == 0
    assert manifest["u_final_count"] == 0
    assert manifest["sft_run"] is False
    assert manifest["rl_run"] is False
