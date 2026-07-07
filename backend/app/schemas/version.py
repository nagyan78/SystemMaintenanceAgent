from pydantic import BaseModel, Field

from backend.app.schemas.taxonomy import TaxonomyNodeRecord


class CreateVersionResult(BaseModel):
    version_id: int
    file_id: int
    version_no: str
    node_count: int
    root_count: int
    max_depth: int
    max_children_count: int


class VersionRecord(BaseModel):
    id: int
    file_id: int
    version_no: str
    description: str | None = None
    quality_score: float | None = None
    snapshot_path: str | None = None
    created_time: str | None = None


class ExecuteActionsResult(BaseModel):
    source_version_id: int
    review_batch_id: str
    action_batch_id: str
    executed_count: int
    failed_count: int
    nodes: list[TaxonomyNodeRecord]
    failures: list[dict] = []


class SaveVersionResult(BaseModel):
    source_version_id: int
    new_version_id: int
    new_version_no: str
    node_count: int
    executed_count: int = 0
    failed_count: int = 0
    quality_score: float | None = None


class VersionDiff(BaseModel):
    from_version_id: int
    to_version_id: int
    added: list[dict] = Field(default_factory=list)
    deleted: list[dict] = Field(default_factory=list)
    renamed: list[dict] = Field(default_factory=list)
    moved: list[dict] = Field(default_factory=list)
    synonym_changed: list[dict] = Field(default_factory=list)


class ExportResult(BaseModel):
    version_id: int
    version_no: str
    file_name: str
    export_path: str
    download_url: str
