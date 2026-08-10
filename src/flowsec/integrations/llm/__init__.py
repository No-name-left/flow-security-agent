"""Provider-neutral LLM integration preparation layer.

This package contains only replaceable configuration, prompt, raw-response,
parser, retry and fake-transport boundaries. It performs no real network call.
"""

from .adapters import LLMSupervisorBackend, LLMTrafficExpertBackend
from .contracts import (
    LLMBackendConfig,
    LLMBackendError,
    LLMFailureKind,
    LLMTransportRequest,
    RawLLMResponse,
    ResponseMode,
    RetryPolicy,
)
from .parsing import (
    FixtureSupervisorResponseParserV0,
    FixtureTrafficExpertResponseParserV0,
)
from .prompting import (
    SupervisorPromptRenderer,
    ToolSpecification,
    TrafficExpertPromptRenderer,
    fixture_supervisor_prompt,
    fixture_traffic_expert_prompt,
)
from .transport import (
    FakeFailure,
    FakeLLMTransport,
    FixtureProviderAProfile,
    FixtureProviderBProfile,
    LLMTransport,
)

__all__ = [
    "FakeFailure",
    "FakeLLMTransport",
    "FixtureProviderAProfile",
    "FixtureProviderBProfile",
    "FixtureSupervisorResponseParserV0",
    "FixtureTrafficExpertResponseParserV0",
    "LLMBackendConfig",
    "LLMBackendError",
    "LLMFailureKind",
    "LLMSupervisorBackend",
    "LLMTrafficExpertBackend",
    "LLMTransport",
    "LLMTransportRequest",
    "RawLLMResponse",
    "ResponseMode",
    "RetryPolicy",
    "SupervisorPromptRenderer",
    "ToolSpecification",
    "TrafficExpertPromptRenderer",
    "fixture_supervisor_prompt",
    "fixture_traffic_expert_prompt",
]
