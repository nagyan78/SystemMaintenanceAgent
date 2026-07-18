from fastapi import APIRouter, HTTPException, Query, Request, status

from backend.app.repositories.taxonomy_repo import TaxonomyRepository
from backend.app.services.taxonomy_service import TaxonomyService
from backend.app.services.version_service import VersionService

router = APIRouter(prefix="/taxonomy", tags=["taxonomy"])


def _require_version(version_id: int, request: Request) -> None:
    if VersionService(request.app.state.settings).get_version(version_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Version not found.")


@router.get("/overview")
def get_taxonomy_overview(request: Request, version_id: int = Query(...)) -> dict:
    _require_version(version_id, request)
    return TaxonomyService(request.app.state.settings).get_overview(version_id).model_dump()


@router.get("/tree")
def get_taxonomy_tree(request: Request, version_id: int = Query(...)) -> dict:
    _require_version(version_id, request)
    nodes = TaxonomyRepository(request.app.state.settings).list_nodes(version_id)
    return {"version_id": version_id, "nodes": nodes}


@router.get("/nodes/{node_id}")
def get_taxonomy_node(node_id: int, request: Request, version_id: int = Query(...)) -> dict:
    _require_version(version_id, request)
    node = TaxonomyRepository(request.app.state.settings).get_node_detail(version_id, node_id)
    if node is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Taxonomy node not found.")
    return node


@router.get("/search")
def search_taxonomy_nodes(
    request: Request,
    version_id: int = Query(...),
    q: str = Query(min_length=1),
) -> dict:
    _require_version(version_id, request)
    normalized = q.strip().lower()
    nodes = TaxonomyRepository(request.app.state.settings).list_nodes(version_id)
    matches = [
        node for node in nodes
        if normalized in str(node["category_name"]).lower()
        or normalized in str(node.get("path_names") or "").lower()
    ]
    return {"version_id": version_id, "query": q, "nodes": matches[:100]}
