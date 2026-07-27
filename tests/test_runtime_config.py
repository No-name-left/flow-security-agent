from __future__ import annotations

from pathlib import Path

from flowsec.config import load_runtime_profile


def test_runtime_profile_injects_secret_without_exposing_it(tmp_path: Path) -> None:
    config = tmp_path / "runtime.yaml"
    config.write_text(
        """
profiles:
  local:
    base_url: http://127.0.0.1:8000/v1
    base_url_env: TEST_BASE_URL
    model: local-model
    model_env: TEST_MODEL
    api_key_env: TEST_API_KEY
""".strip(),
        encoding="utf-8",
    )
    runtime = load_runtime_profile(
        config,
        "local",
        {
            "TEST_BASE_URL": "http://localhost:9000/v1",
            "TEST_MODEL": "test-model",
            "TEST_API_KEY": "secret-value",
        },
    )
    assert runtime.model == "test-model"
    assert runtime.api_key == "secret-value"
    assert "secret-value" not in repr(runtime)
    assert "api_key" not in runtime.public_identity()
