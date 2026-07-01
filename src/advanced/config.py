"""Application configuration loaded from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - convenience fallback before dependencies are installed.
    def load_dotenv() -> bool:
        return False


load_dotenv()


@dataclass(frozen=True)
class Settings:
    """Runtime settings for model access and rule thresholds."""

    model_provider: str = os.getenv("MODEL_PROVIDER", "").strip()
    model_name: str = os.getenv("MODEL_NAME", "").strip()
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "").strip()
    google_api_key: str = os.getenv("GOOGLE_API_KEY", "").strip()
    max_depth: int = int(os.getenv("MAX_DEPTH", "8"))
    max_children: int = int(os.getenv("MAX_CHILDREN", "2000"))

    @property
    def has_llm_config(self) -> bool:
        """Return whether enough configuration exists to attempt LLM calls."""

        if not self.model_provider or not self.model_name:
            return False
        provider = self.model_provider.lower()
        if provider in {"openai", "azure_openai"}:
            return bool(self.openai_api_key)
        if provider in {"google_genai", "google_vertexai", "google"}:
            return bool(self.google_api_key)
        return bool(self.openai_api_key or self.google_api_key)


settings = Settings()
