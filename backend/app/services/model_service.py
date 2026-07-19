"""Single provider boundary for all business LLM calls."""

from typing import Any

from langchain_openai import ChatOpenAI

from backend.app.config import Settings, get_settings
class ModelService:
    """Build the single supported cloud chat model (DeepSeek)."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def get_chat_model(self, *, temperature: float = 0.1) -> Any:
        if not self.settings.deepseek_api_key:
            return None
        return ChatOpenAI(
            model=self.settings.deepseek_model,
            base_url=self.settings.deepseek_base_url,
            api_key=self.settings.deepseek_api_key,
            temperature=temperature,
            request_timeout=self.settings.llm_request_timeout_seconds,
        )
