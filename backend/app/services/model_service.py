"""Single provider boundary for all business LLM calls."""

from typing import Any

from langchain_openai import ChatOpenAI

from backend.app.config import Settings, get_settings


class ModelService:
    """Build the configured chat model without routing or automatic fallback."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def get_chat_model(self, *, temperature: float = 0.1) -> Any:
        provider = self.settings.llm_provider.strip().lower()
        if provider == "ollama":
            return ChatOpenAI(
                model=self.settings.llm_model,
                base_url=self.settings.ollama_base_url,
                api_key="ollama",
                temperature=temperature,
                request_timeout=120,
            )
        if provider == "deepseek":
            if not self.settings.deepseek_api_key:
                return None
            return ChatOpenAI(
                model=self.settings.llm_model,
                base_url=self.settings.deepseek_base_url,
                api_key=self.settings.deepseek_api_key,
                temperature=temperature,
                request_timeout=120,
            )
        raise ValueError(f"Unsupported LLM_PROVIDER: {self.settings.llm_provider}")
