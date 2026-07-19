from dataclasses import dataclass


@dataclass(frozen=True)
class RetryPolicy:
    max_attempts: int = 3
    base_delay: float = 1.0
    max_delay: float = 30.0

    def classify(self, exc: Exception) -> str:
        status = getattr(exc, "status_code", None)
        if status == 429 or (isinstance(status, int) and status >= 500):
            return "retryable_external"
        if isinstance(exc, (TimeoutError, ConnectionError)):
            return "retryable_external"
        return "permanent_internal"

    def delay(self, attempt: int, retry_after: float | None = None) -> float:
        if retry_after is not None:
            return min(retry_after, self.max_delay)
        return min(self.base_delay * (2 ** max(attempt - 1, 0)), self.max_delay)

    def retry_after(self, exc: Exception) -> float | None:
        response = getattr(exc, "response", None)
        headers = getattr(response, "headers", {}) or {}
        value = headers.get("Retry-After") or headers.get("retry-after")
        try:
            return float(value) if value is not None else None
        except (TypeError, ValueError):
            return None
