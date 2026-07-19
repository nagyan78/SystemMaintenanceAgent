"""Single provider boundary for all business LLM calls."""

from typing import Any

from langchain_openai import ChatOpenAI

from backend.app.config import Settings, get_settings
from backend.app.schemas.model_routing import ModelBudget, ModelEndpoint, ModelProfile
from backend.app.services.model_router import ModelRouter


class ModelService:
    """Build the configured chat model without routing or automatic fallback."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def get_chat_model(self, *, temperature: float = 0.1) -> Any:
        provider = self.settings.llm_provider.strip().lower()
        primary = self._provider_model(provider, temperature)
        if primary is None:
            return None
        fallback = None
        if self.settings.llm_fallback_enabled:
            alternate = "deepseek" if provider == "ollama" else "ollama"
            fallback = self._provider_model(alternate, temperature)
        if fallback is None:
            return primary
        return RoutedChatModel(primary, fallback, self.settings, temperature)

    def _provider_model(self, provider: str, temperature: float) -> Any | None:
        if provider == "ollama":
            return ChatOpenAI(
                model=self.settings.llm_model,
                base_url=self.settings.ollama_base_url,
                api_key="ollama",
                temperature=temperature,
                request_timeout=self.settings.llm_request_timeout_seconds,
            )
        if provider == "deepseek":
            if not self.settings.deepseek_api_key:
                return None
            return ChatOpenAI(
                model=self.settings.llm_model,
                base_url=self.settings.deepseek_base_url,
                api_key=self.settings.deepseek_api_key,
                temperature=temperature,
                request_timeout=self.settings.llm_request_timeout_seconds,
            )
        return None


class RoutedChatModel:
    def __init__(self, primary: Any, fallback: Any, settings: Settings, temperature: float) -> None:
        self.primary, self.fallback, self.settings, self.temperature = primary, fallback, settings, temperature
        profile = ModelProfile(task_type="diagnosis", primary=ModelEndpoint(model=str(getattr(primary, "model_name", "primary")), client=primary), fallback=ModelEndpoint(model=str(getattr(fallback, "model_name", "fallback")), client=fallback), temperature=temperature, max_concurrency=settings.agent_llm_max_concurrency)
        self.router = ModelRouter(profiles={"diagnosis": profile}, budget=ModelBudget(max_calls=settings.llm_max_calls, max_tokens=settings.llm_max_tokens))

    def bind_tools(self, tools: list[Any]) -> "RoutedChatModel":
        return RoutedChatModel(self.primary.bind_tools(tools), self.fallback.bind_tools(tools), self.settings, self.temperature)

    def invoke(self, messages: Any, **kwargs: Any) -> Any:
        return self.router.invoke("diagnosis", messages, **kwargs)
