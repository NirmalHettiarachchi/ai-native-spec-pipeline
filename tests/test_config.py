import json
import os
from pathlib import Path

from pipeline.config import get_runtime_config


def test_runtime_config_loads_env_file_without_exposing_secret(
    tmp_path: Path,
    monkeypatch,
) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text(
        "\n".join(
            [
                "PIPELINE_AI_PROVIDER=auto",
                "OPENAI_API_KEY=sk-test-secret",
                "OPENAI_MODEL=gpt-5.5",
                "OPENAI_REASONING_EFFORT=high",
                "PIPELINE_AUDIT_ROOT=tmp-audit",
                "PIPELINE_SPEC_ROOT=tmp-specs",
            ]
        ),
        encoding="utf-8",
    )
    for key in [
        "PIPELINE_AI_PROVIDER",
        "OPENAI_API_KEY",
        "OPENAI_MODEL",
        "OPENAI_REASONING_EFFORT",
        "PIPELINE_AUDIT_ROOT",
        "PIPELINE_SPEC_ROOT",
    ]:
        monkeypatch.delenv(key, raising=False)

    try:
        config = get_runtime_config(env_path)

        public = config.to_public_dict()
        assert config.env_file_loaded is True
        assert config.ai_provider_mode == "auto"
        assert config.resolved_ai_provider == "openai"
        assert config.openai_api_key_configured is True
        assert config.openai_reasoning_effort == "high"
        assert config.audit_root == "tmp-audit"
        assert config.spec_root == "tmp-specs"
        assert "sk-test-secret" not in json.dumps(public)
        assert "openai_api_key" not in public
    finally:
        for key in [
            "PIPELINE_AI_PROVIDER",
            "OPENAI_API_KEY",
            "OPENAI_MODEL",
            "OPENAI_REASONING_EFFORT",
            "PIPELINE_AUDIT_ROOT",
            "PIPELINE_SPEC_ROOT",
        ]:
            os.environ.pop(key, None)


def test_runtime_config_auto_falls_back_to_local_without_key(monkeypatch) -> None:
    monkeypatch.delenv("PIPELINE_AI_PROVIDER", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    config = get_runtime_config()

    assert config.ai_provider_mode == "auto"
    assert config.resolved_ai_provider == "local"
    assert config.openai_api_key_configured is False
