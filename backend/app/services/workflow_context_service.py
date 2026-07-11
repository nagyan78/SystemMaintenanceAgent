from pydantic import BaseModel, Field

from backend.app.config import Settings
from backend.app.repositories.file_repo import FileRepository
from backend.app.repositories.version_repo import VersionRepository
from backend.app.schemas.workflow import StartWorkflowRequest, WorkflowMode


class ResolvedWorkflowContext(BaseModel):
    mode: WorkflowMode
    file_id: int
    base_version_id: int | None = None
    result_version_id: int | None = None
    affected_node_ids: list[int] = Field(default_factory=list)
    max_rounds: int = 2


class WorkflowContextService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.versions = VersionRepository(settings)

    def resolve(self, request: StartWorkflowRequest) -> ResolvedWorkflowContext:
        if request.mode == "import":
            file_record = FileRepository(self.settings).get_file(int(request.file_id))
            if file_record is None:
                raise ValueError("File not found")
            return ResolvedWorkflowContext(
                mode="import",
                file_id=int(request.file_id),
                affected_node_ids=request.affected_node_ids,
                max_rounds=request.max_rounds,
            )

        if request.base_version_id is not None:
            base = self.versions.get_version(request.base_version_id)
        else:
            base = self.versions.get_latest_for_file(int(request.file_id))
        if base is None:
            raise ValueError("Base version not found")

        result = None
        if request.mode == "verify":
            result = self.versions.get_version(int(request.result_version_id))
            if result is None or int(result["file_id"]) != int(base["file_id"]):
                raise ValueError("Result version does not belong to base file")
            if not self.versions.is_descendant(int(base["id"]), int(result["id"])):
                raise ValueError("Result version must be a descendant of base version")
            if not request.affected_node_ids and not self._has_version_diff(
                int(base["id"]), int(result["id"])
            ):
                raise ValueError("Verify requires a version diff or affected_node_ids")

        return ResolvedWorkflowContext(
            mode=request.mode,
            file_id=int(base["file_id"]),
            base_version_id=int(base["id"]),
            result_version_id=int(result["id"]) if result else None,
            affected_node_ids=request.affected_node_ids,
            max_rounds=request.max_rounds,
        )

    def _has_version_diff(self, base_version_id: int, result_version_id: int) -> bool:
        from backend.app.services.version_service import VersionService

        diff = VersionService(self.settings).get_version_diff(
            base_version_id,
            result_version_id,
        )
        return any(
            (
                diff.added,
                diff.deleted,
                diff.renamed,
                diff.moved,
                diff.synonym_changed,
            )
        )
