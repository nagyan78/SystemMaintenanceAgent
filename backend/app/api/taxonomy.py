from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel

from backend.app.repositories.taxonomy_repo import TaxonomyRepository
from backend.app.services.taxonomy_service import TaxonomyService
from backend.app.services.version_service import VersionService

router = APIRouter(prefix="/taxonomy", tags=["taxonomy"])


class ImportRequest(BaseModel):
    file_id: int


@router.post("/import")
def import_taxonomy(payload: ImportRequest, request: Request) -> dict:
    result = VersionService(request.app.state.settings).create_initial_version(payload.file_id)
    overview = TaxonomyService(request.app.state.settings).get_overview(result.version_id)
    return {**overview.model_dump(), "version_no": result.version_no, "status": "completed"}


@router.get("/overview")
def get_taxonomy_overview(version_id: int, request: Request) -> dict:
    try:
        return TaxonomyService(request.app.state.settings).get_overview(version_id).model_dump()
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get("/tree")
def get_taxonomy_tree(version_id: int, request: Request, parent_id: int | None = None) -> list[dict]:
    repo = TaxonomyRepository(request.app.state.settings)
    if parent_id is not None:
        return repo.get_children(version_id, parent_id)
    return repo.list_root_overview(version_id)


@router.get("/nodes/{node_id}")
def get_taxonomy_node(node_id: int, version_id: int, request: Request) -> dict:
    repo = TaxonomyRepository(request.app.state.settings)
    node = repo.get_node_detail(version_id, node_id)
    if node is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Node not found.")
    parent = repo.get_node_detail(version_id, node["parent_id"]) if node.get("parent_id") else None
    siblings = repo.get_children(version_id, node["parent_id"]) if node.get("parent_id") else []
    return {**node, "parent": parent, "children": repo.get_children(version_id, node_id), "siblings": [item for item in siblings if item["category_id"] != node_id]}


@router.get("/search")
def search_taxonomy_nodes(version_id: int, request: Request, q: str = "") -> list[dict]:
    return [node for node in TaxonomyRepository(request.app.state.settings).list_nodes(version_id) if q.lower() in str(node["category_name"]).lower()][:100]
