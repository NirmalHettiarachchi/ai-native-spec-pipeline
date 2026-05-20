"""Runtime configuration loaded from environment and optional .env files."""

from __future__ import annotations

import os
from dataclasses import asdict, dataclass
from pathlib import Path

from dotenv import load_dotenv

from pipeline.errors import PipelineError

DEFAULT_AI_PROVIDER_MODE = "auto"
DEFAULT_OPENAI_MODEL = "gpt-5.5"
DEFAULT_OPENAI_REASONING_EFFORT = "medium"
DEFAULT_OPENAI_BASE_URL = "https://api.openai.com/v1"
SUPPORTED_AI_PROVIDER_MODES = {"auto", "local", "openai"}
SUPPORTED_REASONING_EFFORTS = {"none", "low", "medium", "high", "xhigh"}


@dataclass(frozen=True)
class RuntimeConfig:
    """Sanitized runtime configuration safe to display in UI and audit metadata."""

    ai_provider_mode: str
    resolved_ai_provider: str
    openai_model: str
    openai_reasoning_effort: str
    openai_base_url: str
    openai_api_key_configured: bool
    audit_root: str
    spec_root: str
    env_file: str
    env_file_loaded: bool

    def to_public_dict(self) -> dict[str, str | bool]:
        return asdict(self)


def get_runtime_config(env_file: Path | None = None) -> RuntimeConfig:
    """Load .env if present and return a sanitized configuration snapshot."""

    loaded_env_file = _load_dotenv_file(env_file)
    mode = os.getenv("PIPELINE_AI_PROVIDER", DEFAULT_AI_PROVIDER_MODE).strip().lower()
    openai_model = os.getenv("OPENAI_MODEL", DEFAULT_OPENAI_MODEL).strip()
    reasoning_effort = os.getenv(
        "OPENAI_REASONING_EFFORT",
        DEFAULT_OPENAI_REASONING_EFFORT,
    ).strip().lower()
    openai_base_url = os.getenv("OPENAI_BASE_URL", DEFAULT_OPENAI_BASE_URL).strip().rstrip("/")
    api_key_configured = bool(os.getenv("OPENAI_API_KEY", "").strip())

    if mode not in SUPPORTED_AI_PROVIDER_MODES:
        resolved_provider = "unsupported"
    elif mode == "auto":
        resolved_provider = "openai" if api_key_configured else "local"
    else:
        resolved_provider = mode

    if reasoning_effort not in SUPPORTED_REASONING_EFFORTS:
        resolved_reasoning = DEFAULT_OPENAI_REASONING_EFFORT
    else:
        resolved_reasoning = reasoning_effort

    env_path = env_file or Path.cwd() / ".env"
    return RuntimeConfig(
        ai_provider_mode=mode,
        resolved_ai_provider=resolved_provider,
        openai_model=openai_model or DEFAULT_OPENAI_MODEL,
        openai_reasoning_effort=resolved_reasoning,
        openai_base_url=openai_base_url or DEFAULT_OPENAI_BASE_URL,
        openai_api_key_configured=api_key_configured,
        audit_root=os.getenv("PIPELINE_AUDIT_ROOT", "audit/runs"),
        spec_root=os.getenv("PIPELINE_SPEC_ROOT", "specs"),
        env_file=str(env_path),
        env_file_loaded=loaded_env_file,
    )


def get_openai_api_key() -> str:
    """Return the configured API key or fail with a user-correctable error."""

    _load_dotenv_file(None)
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise PipelineError("OPENAI_API_KEY is required when PIPELINE_AI_PROVIDER=openai")
    return api_key


def validate_provider_mode(mode: str) -> None:
    if mode not in SUPPORTED_AI_PROVIDER_MODES:
        supported = ", ".join(sorted(SUPPORTED_AI_PROVIDER_MODES))
        raise PipelineError(f"unsupported PIPELINE_AI_PROVIDER: {mode}. Use one of: {supported}")


def _load_dotenv_file(env_file: Path | None) -> bool:
    env_path = env_file or Path.cwd() / ".env"
    if not env_path.exists():
        return False
    return bool(load_dotenv(env_path, override=False))
