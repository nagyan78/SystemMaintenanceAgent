from fastapi import HTTPException, status


def not_implemented(module: str, feature: str) -> None:
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail={
            "module": module,
            "feature": feature,
            "message": "This API boundary is scaffolded for later implementation.",
        },
    )

