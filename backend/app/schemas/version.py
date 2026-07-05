from pydantic import BaseModel


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
