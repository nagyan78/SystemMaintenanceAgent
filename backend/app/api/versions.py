from fastapi import APIRouter

from backend.app.api._placeholder import not_implemented

router = APIRouter(prefix="/versions", tags=["versions"])


@router.get("")
def list_versions() -> None:
    not_implemented("versions", "list")


@router.get("/{version_id}")
def get_version(version_id: int) -> None:
    not_implemented("versions", f"detail:{version_id}")


@router.get("/{version_id}/diff")
def get_version_diff(version_id: int) -> None:
    not_implemented("versions", f"diff:{version_id}")


@router.post("/{version_id}/rollback")
def rollback_version(version_id: int) -> None:
    not_implemented("versions", f"rollback:{version_id}")


@router.get("/{version_id}/export")
def export_version(version_id: int) -> None:
    not_implemented("versions", f"export:{version_id}")

