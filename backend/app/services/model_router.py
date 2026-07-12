import threading
from backend.app.schemas.model_routing import ModelBudget, ModelProfile, ModelUsage

class ModelUnavailableError(RuntimeError):
    code = "MODEL_UNAVAILABLE"

class ModelBudgetExceededError(RuntimeError):
    code = "MODEL_BUDGET_EXCEEDED"

class ModelRouter:
    def __init__(self, *, profiles: dict[str, ModelProfile], budget: ModelBudget) -> None:
        self.profiles, self.budget, self.usage = profiles, budget, ModelUsage()
        self._locks = {name: threading.BoundedSemaphore(profile.max_concurrency) for name, profile in profiles.items()}

    def invoke(self, task_type: str, messages, **kwargs):
        profile = self.profiles.get(task_type)
        if profile is None:
            raise ModelUnavailableError(f"MODEL_UNAVAILABLE: profile {task_type}")
        with self._locks[task_type]:
            try:
                return self._call(profile.primary, messages, **kwargs)
            except Exception as exc:
                if profile.fallback is None or not _retryable(exc):
                    raise
                self.usage.fallback_calls += 1
                return self._call(profile.fallback, messages, **kwargs)

    def _call(self, endpoint, messages, **kwargs):
        if self.usage.calls >= self.budget.max_calls:
            raise ModelBudgetExceededError("MODEL_BUDGET_EXCEEDED: calls")
        if endpoint.client is None:
            raise ModelUnavailableError(f"MODEL_UNAVAILABLE: {endpoint.model}")
        self.usage.calls += 1
        result = endpoint.client.invoke(messages, **kwargs)
        tokens = int(getattr(result, "usage_metadata", {}).get("total_tokens", 0) if getattr(result, "usage_metadata", None) else 0)
        self.usage.tokens += tokens
        if self.usage.tokens > self.budget.max_tokens:
            raise ModelBudgetExceededError("MODEL_BUDGET_EXCEEDED: tokens")
        return result

def _retryable(exc: Exception) -> bool:
    code = getattr(exc, "status_code", None)
    return isinstance(exc, (TimeoutError, ConnectionError)) or code == 429 or (isinstance(code, int) and code >= 500)
