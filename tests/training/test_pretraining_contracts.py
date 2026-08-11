from __future__ import annotations

import json
from pathlib import Path

import pytest

from flowsec.integrations.llm.contracts import RawLLMResponse, RawUsage
from flowsec.training.contracts import (
    EvidenceDomain,
    EvidenceEnvelope,
    EvidenceGapType,
    EvidenceSnapshot,
    EvidenceStateV1,
    EvidenceTrustV1,
    MissingEvidenceV1,
    StageType,
    SupportingEvidenceV1,
    validate_evidence_grounding,
)
from flowsec.training.evidence import (
    ApplicationEvidenceV1,
    application_envelope,
    decode_hex_payload,
    payload_envelope,
    sanitize_payload_text,
    SanitizedPayloadV1,
)
from flowsec.training.harness import (
    POOL_LAST_PROMPT_TOKEN,
    POOL_MEAN,
    TrafficExpertTrainingHarness,
    inventory_lora_targets,
    load_near_class_map,
    pool_hidden_state,
)
from flowsec.training.materialization import CaptureSessionMatcher, SessionLocator, _tshark_command
from flowsec.training.prompts import teacher_prompt_v1, traffic_expert_prompt_v1
from flowsec.training.rag import (
    BM25Index,
    HybridRagIndex,
    KnowledgeChunkV1,
    build_safe_query,
    rag_envelope,
    validate_safe_query,
)
from flowsec.training.serialization import (
    COMPACT_SERIALIZATION_CANDIDATE,
    assert_semantic_equivalence,
    decode_compact,
    render_training_input,
    serialize_compact,
)
from flowsec.training.teacher import (
    DeepSeekFlashSettings,
    DeepSeekTeacherClient,
    deepseek_api_preflight,
    parse_judge_response,
    provider_availability,
)


SAMPLE_ID = "fs1_" + "a" * 40


def _initial_evidence() -> EvidenceEnvelope:
    return EvidenceEnvelope(
        evidence_id="ev_initial_12345678",
        evidence_type="initial",
        domain=EvidenceDomain.OBSERVATION,
        trust=EvidenceTrustV1.TRUSTED_OBSERVATION,
        content={"packet_sequence": [{"direction": "initiator_to_responder", "packet_length": 60}]},
        provenance="production_safe_adapter",
    )


def _snapshot(*, sufficient: bool = True) -> EvidenceSnapshot:
    evidence = (_initial_evidence(),)
    return EvidenceSnapshot(
        sample_id=SAMPLE_ID,
        evidence_state_id="state_" + "b" * 24,
        fine_label="Normal",
        coarse_label="Normal",
        split="train",
        ku_role="K_known",
        stage_type=StageType.INITIAL,
        classification_supervision_valid=sufficient,
        available_capabilities=("packet",),
        evidence=evidence,
        source_digest="c" * 64,
    )


def test_evidence_state_has_no_class_field_and_grounding_is_observation_only() -> None:
    state = EvidenceStateV1(
        behavior_summary="One bounded request is visible.",
        supporting_evidence=(
            SupportingEvidenceV1(evidence_id="ev_initial_12345678", claim="One packet is visible."),
        ),
        evidence_sufficient=True,
        gap_type=EvidenceGapType.NONE,
    )
    validate_evidence_grounding(state, (_initial_evidence(),))
    assert "fine_label" not in state.model_dump()

    knowledge = rag_envelope(
        KnowledgeChunkV1(
            chunk_id="kb_" + "1" * 24,
            source_id="src_rfc_test",
            title="Protocol reference",
            source_type="IETF_RFC",
            text="A generic protocol reference explains request and response semantics without session claims.",
            source_sha256="2" * 64,
            ordinal=0,
        ),
        score=0.7,
    )
    bad = state.model_copy(
        update={
            "supporting_evidence": (
                SupportingEvidenceV1(evidence_id=knowledge.evidence_id, claim="The session did this."),
            )
        }
    )
    with pytest.raises(ValueError, match="Knowledge evidence"):
        validate_evidence_grounding(bad, (knowledge,))


def test_application_payload_schema_redaction_and_plaintext_gate() -> None:
    app = ApplicationEvidenceV1(
        protocol="http",
        observations=({"kind": "http", "method": "POST", "uri_shape": "/<SEG>"},),
        frame_count=2,
    )
    assert application_envelope(SAMPLE_ID, app).domain is EvidenceDomain.OBSERVATION
    raw = (
        "POST /dvwa/login?username=alice HTTP/1.1\r\nHost: 192.168.1.2\r\n"
        "User-Agent: sqlmap\r\nCookie: secret\r\n\r\nid=1 UNION SELECT password"
    )
    safe = sanitize_payload_text(raw)
    assert safe is not None
    assert "192.168.1.2" not in safe and "sqlmap" not in safe.casefold() and "/dvwa" not in safe
    assert "UNION SELECT" in safe
    value = SanitizedPayloadV1(
        protocol="TCP", fragments=(safe,), raw_fragment_count=1, max_fragment_chars=768, truncated=False
    )
    envelope = payload_envelope(SAMPLE_ID, value)
    assert envelope.trust is EvidenceTrustV1.UNTRUSTED_PAYLOAD
    assert decode_hex_payload("66ff80aa00") is None
    assert decode_hex_payload("474554202f20485454502f312e310d0a") == "GET / HTTP/1.1\r\n"
    assert sanitize_payload_text("HTTP/1.1 200 OK\r\nContent-Type: text/html\r\n\r\nfixed page") is None
    normalized = sanitize_payload_text(
        "POST /fixed/site.php?id=1 HTTP/1.1\r\nAccept-Encoding: gzip\r\nHost: lab.invalid\r\n\r\nid=1 UNION SELECT secret"
    )
    assert normalized is not None
    assert "/fixed/site.php" not in normalized and "gzip" not in normalized
    assert "UNION SELECT" in normalized


def test_compact_serialization_is_lossless_and_prompt_is_frozen() -> None:
    evidence = (_initial_evidence(),)
    assert_semantic_equivalence(evidence)
    assert decode_compact(serialize_compact(evidence)) == [evidence[0].model_dump(mode="json")]
    rendered = render_training_input(
        traffic_expert_prompt_v1(), evidence, serialization_version=COMPACT_SERIALIZATION_CANDIDATE
    )
    assert "Classification representation:" in rendered
    assert teacher_prompt_v1().digest != traffic_expert_prompt_v1().digest


def test_capture_matcher_is_bidirectional_and_bounded(tmp_path: Path) -> None:
    locator = SessionLocator(
        sample_id=SAMPLE_ID,
        fine_label="Normal",
        coarse_label="Normal",
        capture_id="legal_capture",
        pcap_path=tmp_path / "a.pcap",
        pcap_sha256="0" * 64,
        first_frame=10,
        last_frame=20,
        l4_protocol="TCP",
        initiator_ip="10.0.0.1",
        responder_ip="10.0.0.2",
        initiator_port=1234,
        responder_port=80,
    )
    matcher = CaptureSessionMatcher([locator])
    reverse = {
        "ip.src": "10.0.0.2",
        "ip.dst": "10.0.0.1",
        "tcp.srcport": "80",
        "tcp.dstport": "1234",
    }
    assert matcher.match(15, reverse) == locator
    assert matcher.match(21, reverse) is None
    command = _tshark_command(tmp_path / "a.pcap")
    assert "separator=/t" in command and "-n" in command


class _FakeEmbedder:
    model_id = "fixture-dense"
    revision = "fixture-v1"

    def encode(self, texts: list[str]):
        np = pytest.importorskip("numpy")
        rows = []
        for text in texts:
            lower = text.casefold()
            vector = np.asarray(
                [lower.count("tcp") + lower.count("connection"), lower.count("sql") + lower.count("query")],
                dtype="float32",
            )
            norm = float(np.linalg.norm(vector)) or 1.0
            rows.append(vector / norm)
        return np.asarray(rows, dtype="float32")


def test_hybrid_rag_safe_query_and_knowledge_boundary() -> None:
    np = pytest.importorskip("numpy")
    chunks = [
        KnowledgeChunkV1(chunk_id="kb_" + "1" * 24, source_id="src_rfc_tcp", title="TCP", source_type="RFC", text="TCP connection state and retransmission are transport observations interpreted by protocol rules.", source_sha256="a" * 64, ordinal=0),
        KnowledgeChunkV1(chunk_id="kb_" + "2" * 24, source_id="src_owasp_sql", title="SQL", source_type="OWASP", text="SQL query input can alter intended database command semantics when injection controls syntax.", source_sha256="b" * 64, ordinal=0),
    ]
    embedder = _FakeEmbedder()
    index = HybridRagIndex(chunks, embedder.encode([item.text for item in chunks]), embedder)
    query = build_safe_query(visible_evidence_summary="TCP connection attempts", evidence_gap="transport behavior")
    assert index.retrieve(query, top_k=1)[0][0].source_id == "src_rfc_tcp"
    assert BM25Index.build([item.text for item in chunks]).scores("SQL query")[1] > 0
    with pytest.raises(ValueError):
        validate_safe_query("Edge-IIoTset capture fine label")
    envelope = rag_envelope(chunks[0], score=0.8)
    assert envelope.domain is EvidenceDomain.KNOWLEDGE
    assert envelope.trust is EvidenceTrustV1.UNTRUSTED_KNOWLEDGE
    assert np.isfinite(index.embeddings).all()


class _QueueTransport:
    def __init__(self, payloads: list[dict[str, object]]):
        self.payloads = list(payloads)
        self.requests = []

    def send(self, request):
        self.requests.append(request)
        payload = self.payloads.pop(0)
        return RawLLMResponse(
            structured_payload=payload,
            provider="deepseek",
            model_id="deepseek-v4-flash",
            request_id="fixture-request",
            usage=RawUsage(input_tokens=10, output_tokens=10, total_tokens=20),
        )


def _valid_teacher_payload() -> dict[str, object]:
    return {
        "behavior_summary": "One short packet observation is visible.",
        "supporting_evidence": [
            {"evidence_id": "ev_initial_12345678", "claim": "One packet is visible."}
        ],
        "missing_evidence": [],
        "evidence_sufficient": True,
        "gap_type": "none",
        "teacher_confidence": 0.9,
    }


def test_teacher_bounded_repair_provider_mock_and_judge_parse(monkeypatch) -> None:
    bad = {**_valid_teacher_payload(), "supporting_evidence": [{"evidence_id": "ev_missing_12345678", "claim": "Bad."}]}
    transport = _QueueTransport([bad, _valid_teacher_payload()])
    annotation, audit = DeepSeekTeacherClient(
        transport, settings=DeepSeekFlashSettings()
    ).annotate(_snapshot())
    assert annotation.evidence_sufficient is True
    assert audit["repair_used"] is True and len(transport.requests) == 2
    failed_transport = _QueueTransport([bad, bad])
    with pytest.raises(ValueError, match="bounded repair"):
        DeepSeekTeacherClient(
            failed_transport, settings=DeepSeekFlashSettings(max_attempts=3)
        ).annotate(_snapshot())
    assert len(failed_transport.requests) == 2
    assert provider_availability({})["api_key_available"] is False
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    assert deepseek_api_preflight()["reason"] == "NO_API_KEY"
    configured = {
        "DEEPSEEK_MODEL": "configured-model",
        "DEEPSEEK_BASE_URL": "https://provider.invalid",
    }
    assert provider_availability(configured)["model_id"] == "configured-model"
    monkeypatch.setenv("DEEPSEEK_MODEL", "configured-model")
    monkeypatch.setenv("DEEPSEEK_BASE_URL", "https://provider.invalid")
    settings = DeepSeekFlashSettings.from_environment()
    assert settings.model_id == "configured-model"
    assert settings.base_url == "https://provider.invalid"
    judge = parse_judge_response(
        RawLLMResponse(
            structured_payload={
                "grounding": 1,
                "evidence_sufficiency": 0.8,
                "missing_evidence_quality": 0.7,
                "gap_correctness": 0.9,
                "hallucination_avoidance": 1,
                "backoff_appropriateness": 0.8,
                "reliability_note": "Grounded fixture.",
            },
            provider="deepseek",
        )
    )
    assert judge.grounding == 1


def test_dynamic_near_class_map(tmp_path: Path) -> None:
    manifest = tmp_path / "presets.json"
    manifest.write_text(json.dumps({"Near": {"K_known": ["Normal", "Backdoor"]}}))
    labels, mapping = load_near_class_map(manifest)
    assert labels == ("Normal", "Backdoor")
    assert mapping == {"Normal": 0, "Backdoor": 1}


def test_pooling_head_mask_and_lora_inventory() -> None:
    torch = pytest.importorskip("torch")
    hidden = torch.tensor([[[1.0, 0.0], [2.0, 0.0], [9.0, 0.0]], [[3.0, 0.0], [4.0, 0.0], [5.0, 0.0]]])
    mask = torch.tensor([[1, 1, 0], [1, 1, 1]])
    assert pool_hidden_state(hidden, mask, method=POOL_LAST_PROMPT_TOKEN)[:, 0].tolist() == [2.0, 5.0]
    assert pool_hidden_state(hidden, mask, method=POOL_MEAN)[:, 0].tolist() == pytest.approx([1.5, 4.0])
    inventory = inventory_lora_targets(
        [("m.q_proj", object()), ("m.in_proj_qkv", object()), ("m.gate_proj", object())]
    )
    assert inventory["family_counts"] == {"gated_attention": 1, "gated_deltanet": 1, "ffn": 1}

    class Output:
        def __init__(self, logits, hidden_states, loss):
            self.logits, self.hidden_states, self.loss = logits, hidden_states, loss

    class TinyLM(torch.nn.Module):
        def __init__(self):
            super().__init__()
            self.embedding = torch.nn.Embedding(20, 4)
            self.lm_head = torch.nn.Linear(4, 20)

        def forward(self, input_ids, attention_mask, labels, **_kwargs):
            state = self.embedding(input_ids)
            logits = self.lm_head(state)
            return Output(logits, (state,), logits.mean() if labels is not None else None)

    harness = TrafficExpertTrainingHarness(TinyLM(), hidden_size=4, num_classes=3, pooling_method=POOL_LAST_PROMPT_TOKEN)
    with pytest.raises(ValueError, match="prompt-only classification mask"):
        harness(
            input_ids=torch.tensor([[1, 2]]),
            attention_mask=torch.ones(1, 2, dtype=torch.long),
            lm_labels=torch.tensor([[1, 2]]),
            fine_labels=torch.tensor([0]),
            classification_supervision_valid=torch.tensor([True]),
        )

    output = harness(
        input_ids=torch.tensor([[1, 2], [3, 4]]),
        attention_mask=torch.ones(2, 2, dtype=torch.long),
        classification_attention_mask=torch.tensor([[1, 0], [1, 0]]),
        lm_labels=torch.tensor([[1, 2], [3, 4]]),
        fine_labels=torch.tensor([0, 1]),
        classification_supervision_valid=torch.tensor([True, False]),
    )
    output["loss"].backward()
    assert output["fine_logits"].shape == (2, 3)
    assert output["classification_supervised_count"].item() == 1
    assert harness.fine_head.projection.weight.grad is not None
