from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

from .contracts import (
    AgentAction,
    CallMetrics,
    Capability,
    EvidenceItem,
    ToolRequest,
    ToolResult,
    ToolStatus,
)


class EvidenceTool(Protocol):
    action: AgentAction
    capability: Capability

    def execute(
        self,
        request: ToolRequest,
        current_evidence: tuple[EvidenceItem, ...],
    ) -> ToolResult:
        ...


ToolHandler = Callable[[ToolRequest, tuple[EvidenceItem, ...]], ToolResult]


class SyntheticEvidenceTool:
    """Deterministic test double for a future production evidence adapter."""

    action: AgentAction
    capability: Capability

    def __init__(
        self,
        handler: ToolHandler | None = None,
        *,
        default_evidence: tuple[EvidenceItem, ...] = (),
        default_metrics: CallMetrics | None = None,
    ):
        self.handler = handler
        self.default_evidence = default_evidence
        self.default_metrics = default_metrics or CallMetrics()
        self.requests: list[ToolRequest] = []

    def execute(
        self,
        request: ToolRequest,
        current_evidence: tuple[EvidenceItem, ...],
    ) -> ToolResult:
        self.requests.append(request)
        if request.action is not self.action:
            return ToolResult(
                status=ToolStatus.FAILURE,
                request_signature=request.signature,
                error=f"tool cannot execute action {request.action}",
            )
        if self.handler is not None:
            return self.handler(request, current_evidence)
        return ToolResult(
            status=ToolStatus.SUCCESS,
            request_signature=request.signature,
            evidence=self.default_evidence,
            metrics=self.default_metrics,
        )


class PacketExpansionTool(SyntheticEvidenceTool):
    action = AgentAction.EXPAND_PACKETS
    capability = Capability.PACKET_EXPANSION


class TemporalContextTool(SyntheticEvidenceTool):
    action = AgentAction.EXPAND_TEMPORAL_CONTEXT
    capability = Capability.TEMPORAL_CONTEXT


class GraphContextTool(SyntheticEvidenceTool):
    action = AgentAction.EXPAND_GRAPH_CONTEXT
    capability = Capability.GRAPH_CONTEXT


class ApplicationEvidenceTool(SyntheticEvidenceTool):
    action = AgentAction.REQUEST_APPLICATION_EVIDENCE
    capability = Capability.APPLICATION_EVIDENCE


class KnowledgeRetrievalTool(SyntheticEvidenceTool):
    action = AgentAction.RETRIEVE_KNOWLEDGE
    capability = Capability.KNOWLEDGE_RETRIEVAL
