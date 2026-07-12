import os
from pathlib import Path
from typing import Iterable

from dotenv import load_dotenv
from pydantic import BaseModel, Field

load_dotenv()


class Settings(BaseModel):
    app_name: str = "standard-taxonomy-agent"
    database_url: str = "sqlite:///./data/app.db"
    upload_dir: Path = Field(default_factory=lambda: Path("./data/uploads"))
    export_dir: Path = Field(default_factory=lambda: Path("./data/exports"))
    report_dir: Path = Field(default_factory=lambda: Path("./data/reports"))
    qdrant_url: str = Field(default_factory=lambda: os.getenv("QDRANT_URL", "http://localhost:6333"))
    qdrant_collection: str = Field(default_factory=lambda: os.getenv("QDRANT_COLLECTION", "taxonomy_nodes"))
    deepseek_api_key: str = Field(default_factory=lambda: os.getenv("DEEPSEEK_API_KEY", ""))
    deepseek_base_url: str = Field(default_factory=lambda: os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"))
    deepseek_model: str = Field(default_factory=lambda: os.getenv("DEEPSEEK_MODEL", "deepseek-chat"))
    llm_provider: str = Field(default_factory=lambda: os.getenv("LLM_PROVIDER", "ollama"))
    llm_model: str = Field(default_factory=lambda: os.getenv("LLM_MODEL", "qwen3:8b"))
    ollama_base_url: str = Field(default_factory=lambda: os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434/v1"))
    dashscope_api_key: str = Field(default_factory=lambda: os.getenv("DASHSCOPE_API_KEY", ""))
    embedding_base_url: str = Field(default_factory=lambda: os.getenv("EMBEDDING_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1"))
    embedding_model: str = Field(default_factory=lambda: os.getenv("EMBEDDING_MODEL", "text-embedding-v2"))
    embedding_batch_size: int = Field(default_factory=lambda: int(os.getenv("EMBEDDING_BATCH_SIZE", "10")))
    embedding_max_workers: int = Field(default_factory=lambda: int(os.getenv("EMBEDDING_MAX_WORKERS", "4")))
    agent_llm_max_concurrency: int = Field(default_factory=lambda: int(os.getenv("AGENT_LLM_MAX_CONCURRENCY", "4")))
    agent_qdrant_max_concurrency: int = Field(default_factory=lambda: int(os.getenv("AGENT_QDRANT_MAX_CONCURRENCY", "8")))
    agent_embedding_max_concurrency: int = Field(default_factory=lambda: int(os.getenv("AGENT_EMBEDDING_MAX_CONCURRENCY", "4")))
    agent_work_item_max_attempts: int = Field(default_factory=lambda: int(os.getenv("AGENT_WORK_ITEM_MAX_ATTEMPTS", "3")))
    agent_lease_seconds: int = Field(default_factory=lambda: int(os.getenv("AGENT_LEASE_SECONDS", "120")))
    llm_fallback_enabled: bool = Field(default_factory=lambda: os.getenv("LLM_FALLBACK_ENABLED", "true").lower() in {"1","true","yes"})
    llm_max_calls: int = Field(default_factory=lambda: int(os.getenv("LLM_MAX_CALLS", "100")))
    llm_max_tokens: int = Field(default_factory=lambda: int(os.getenv("LLM_MAX_TOKENS", "100000")))
    max_tree_depth_threshold: int = 7
    max_children_threshold: int = 80
    max_upload_size_bytes: int = 50 * 1024 * 1024
    allowed_upload_suffixes: tuple[str, ...] = (".xlsx",)

    def ensure_directories(self) -> None:
        for directory in self.local_directories():
            directory.mkdir(parents=True, exist_ok=True)

    def local_directories(self) -> Iterable[Path]:
        return (self.upload_dir, self.export_dir, self.report_dir)


def get_settings() -> Settings:
    return Settings()
