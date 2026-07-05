from pathlib import Path
from typing import Iterable

from pydantic import BaseModel, Field


class Settings(BaseModel):
    app_name: str = "standard-taxonomy-agent"
    database_url: str = "sqlite:///./data/app.db"
    upload_dir: Path = Field(default_factory=lambda: Path("./data/uploads"))
    export_dir: Path = Field(default_factory=lambda: Path("./data/exports"))
    report_dir: Path = Field(default_factory=lambda: Path("./data/reports"))
    qdrant_url: str = "http://localhost:6333"
    qdrant_collection: str = "taxonomy_nodes"
    max_tree_depth_threshold: int = 7
    max_children_threshold: int = 80
    allowed_upload_suffixes: tuple[str, ...] = (".xlsx",)

    def ensure_directories(self) -> None:
        for directory in self.local_directories():
            directory.mkdir(parents=True, exist_ok=True)

    def local_directories(self) -> Iterable[Path]:
        return (self.upload_dir, self.export_dir, self.report_dir)


def get_settings() -> Settings:
    return Settings()

