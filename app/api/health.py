"""Service health endpoint."""

from fastapi import APIRouter

from app.core.responses import success_response


router = APIRouter(tags=["health"])


@router.get("/health")
async def health_check() -> dict[str, object]:
    """Return a response proving that the API process is healthy."""
    return success_response({"status": "ok"})
