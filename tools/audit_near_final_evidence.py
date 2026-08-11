#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from flowsec.training.contracts import EvidenceSnapshot, content_digest
from flowsec.training.corpus import sha256_file
from flowsec.training.rag import (
    DEFAULT_EMBEDDING_MODEL,
    DEFAULT_EMBEDDING_REVISION,
    TransformersDenseEmbedder,
    build_safe_query,
    load_rag_index,
)


_IPV4 = re.compile(r"(?<![0-9])(?:[0-9]{1,3}[.]){3}[0-9]{1,3}(?![0-9])")
_FORBIDDEN = ("edge-iiot", "sample_id", "capture_id", "/root/", "sqlmap", "nmap", "hydra")


def _atomic(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary=path.with_suffix(path.suffix+".tmp")
    temporary.write_text(json.dumps(value,indent=2,sort_keys=True),encoding="utf-8")
    os.replace(temporary,path)


def main() -> int:
    artifact=Path(os.environ["ARTIFACT_ROOT"])
    root=artifact/"near_pretraining_v1"
    snapshot_path=root/"sft_corpus/evidence_snapshot_universe_v1.jsonl"
    snapshots=[EvidenceSnapshot.model_validate_json(line) for line in snapshot_path.open()]
    sidecars=json.loads((root/"manifests/application_payload_manifest.json").read_text())
    rag_manifest=json.loads((root/"rag/manifest.json").read_text())

    application=[]; payload=[]
    for snapshot in snapshots:
        for evidence in snapshot.evidence:
            if evidence.evidence_type=="application": application.append((snapshot,evidence))
            if evidence.evidence_type=="sanitized_payload": payload.append((snapshot,evidence))
    app_protocols=Counter(str(item.content.get("protocol","unknown")) for _,item in application)
    app_classes=Counter(snapshot.fine_label for snapshot,_ in application)
    payload_texts=[json.dumps(item.content,ensure_ascii=False).casefold() for _,item in payload]
    shortcut_hits=sum(any(token in text for token in _FORBIDDEN) or bool(_IPV4.search(text)) for text in payload_texts)
    semantics={
        "sql_syntax": sum(any(token in text for token in ("union", "select", "sql", "operator")) for text in payload_texts),
        "command_structure": sum(any(token in text for token in ("command", "shell", "exec", "cmd=")) for text in payload_texts),
        "file_upload_structure": sum(any(token in text for token in ("multipart", "filename", "content-disposition", "upload")) for text in payload_texts),
        "credential_structure": sum(any(token in text for token in ("password", "username", "login", "credential")) for text in payload_texts),
        "http_parameter_structure": sum(any(token in text for token in ("parameter", "query", "body", "post ")) for text in payload_texts),
    }

    model_path=Path(os.environ["NEAR_EMBEDDING_MODEL_PATH"])
    embedder=TransformersDenseEmbedder(model_path,model_id=DEFAULT_EMBEDDING_MODEL,revision=DEFAULT_EMBEDDING_REVISION)
    index=load_rag_index(root/"rag",embedder=embedder)
    themes={
        "tcp_protocol":"TCP handshake retransmission connection state interpretation",
        "scanning":"network service discovery port scanning repeated connection attempts",
        "ddos":"denial of service high-rate repeated requests resource exhaustion",
        "credential":"brute force credential stuffing password authentication failures",
        "malware":"malware backdoor command and control ransomware encryption impact",
        "sql_injection":"SQL injection database query union select untrusted input",
        "upload":"unrestricted file upload multipart filename content disposition",
        "vulnerability_scanning":"systematic probing of exposed services for vulnerabilities",
    }
    retrieval={}; retrieval_failures=0
    for theme,summary in themes.items():
        query=build_safe_query(visible_evidence_summary=summary,evidence_gap="generic protocol and security behavior interpretation")
        results=index.retrieve(query,top_k=3)
        ids=[chunk.chunk_id for chunk,_score in results]
        expected_sources = {
            "tcp_protocol": ("src_rfc",),
            "scanning": ("src_mitre_t1046", "src_nist_sp800_115"),
            "ddos": ("src_owasp_dos",),
            "credential": ("src_owasp_brute_force", "src_owasp_credential_stuffing", "src_mitre_t1110"),
            "malware": ("src_nist_sp800_83", "src_mitre_t1095", "src_mitre_t1486", "src_nist_sp1800_26"),
            "sql_injection": ("src_owasp_sql_injection",),
            "upload": ("src_owasp_upload",),
            "vulnerability_scanning": ("src_mitre_t1046", "src_mitre_t1190", "src_nist_sp800_115"),
        }[theme]
        relevant = any(
            any(chunk.source_id.startswith(prefix) for prefix in expected_sources)
            for chunk, _score in results
        )
        if not results or len(ids)!=len(set(ids)) or not relevant:
            retrieval_failures+=1
        retrieval[theme]=[{"chunk_id":chunk.chunk_id,"source_id":chunk.source_id,"title":chunk.title,"score":round(float(score),6)} for chunk,score in results]

    checks={
        "sidecar_manifest_pass":sidecars.get("status")=="PASS",
        "payload_shortcut_risk_low":sidecars.get("payload_shortcut_risk")=="LOW",
        "rag_manifest_pass":rag_manifest.get("status")=="PASS",
        "rag_index_digest_present":bool(rag_manifest.get("artifact_digest")),
        "rag_u_final_term_hits_zero":rag_manifest.get("u_final_term_hits")==0,
        "snapshot_u_final_zero":all(snapshot.split=="train" and snapshot.ku_role=="K_known" for snapshot in snapshots),
        "payload_shortcut_hits_zero":shortcut_hits==0,
        "application_major_protocols_present":bool(app_protocols),
        "semantic_payload_signals_preserved":sum(value>0 for value in semantics.values())>=3,
        "retrieval_themes_pass":retrieval_failures==0,
    }
    report={
        "status":"PASS" if all(checks.values()) else "FAIL",
        "version":"NEAR_FINAL_EVIDENCE_SPOTCHECK_V1",
        "checks":checks,
        "snapshot_sha256":sha256_file(snapshot_path),
        "application_snapshot_records":len(application),
        "application_class_distribution":dict(sorted(app_classes.items())),
        "application_protocol_distribution":dict(sorted(app_protocols.items())),
        "payload_snapshot_records":len(payload),
        "payload_semantic_signal_counts":semantics,
        "payload_shortcut_hit_count":shortcut_hits,
        "retrieval":retrieval,
        "retrieval_failure_count":retrieval_failures,
        "u_final_count":0,
    }
    report["audit_digest"]=content_digest(report)
    _atomic(root/"manifests/final_evidence_spotcheck.json",report)
    print(json.dumps(report,indent=2,sort_keys=True))
    return 0 if report["status"]=="PASS" else 1


if __name__=="__main__":
    raise SystemExit(main())
