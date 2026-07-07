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
    dashscope_api_key: str = Field(default_factory=lambda: os.getenv("DASHSCOPE_API_KEY", ""))
    embedding_base_url: str = Field(default_factory=lambda: os.getenv("EMBEDDING_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1"))
    embedding_model: str = Field(default_factory=lambda: os.getenv("EMBEDDING_MODEL", "text-embedding-v2"))
    embedding_batch_size: int = Field(default_factory=lambda: int(os.getenv("EMBEDDING_BATCH_SIZE", "10")))
    embedding_max_workers: int = Field(default_factory=lambda: int(os.getenv("EMBEDDING_MAX_WORKERS", "4")))
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
