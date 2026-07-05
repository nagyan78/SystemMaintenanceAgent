from fastapi import APIRouter

from backend.app.api._placeholder import not_implemented

router = APIRouter(prefix="/taxonomy", tags=["taxonomy"])


@router.get("/overview")
def get_taxonomy_overview() -> None:
    not_implemented("taxonomy", "overview")


@router.get("/tree")
def get_taxonomy_tree() -> None:
    not_implemented("taxonomy", "tree")


@router.get("/nodes/{node_id}")
def get_taxonomy_node(node_id: int) -> None:
    not_implemented("taxonomy", f"node:{node_id}")


@router.get("/search")
def search_taxonomy_nodes(q: str = "") -> None:
    not_implemented("taxonomy", f"search:{q}")

