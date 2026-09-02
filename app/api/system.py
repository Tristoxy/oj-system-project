"""System reset and import/export endpoints."""

import json

from fastapi import APIRouter, Depends, File, Response, UploadFile
from pydantic import ValidationError

from app.container import AppContainer
from app.core.config import SESSION_COOKIE
from app.core.exceptions import ApiError
from app.core.responses import success_response
from app.dependencies import get_container, require_admin
from app.models.system import ImportBundle
from app.models.user import User


router = APIRouter(prefix="/api", tags=["system"])


@router.post("/reset/")
async def reset_system(
    response: Response,
    admin: User = Depends(require_admin),
    container: AppContainer = Depends(get_container),
) -> dict[str, object]:
    del admin
    await container.system.reset()
    response.delete_cookie(SESSION_COOKIE)
    return success_response(None, msg="system reset successfully")


@router.get("/export/")
async def export_data(
    admin: User = Depends(require_admin),
    container: AppContainer = Depends(get_container),
) -> dict[str, object]:
    del admin
    return success_response(await container.system.export_data())


@router.post("/import/")
async def import_data(
    file: UploadFile = File(...),
    admin: User = Depends(require_admin),
    container: AppContainer = Depends(get_container),
) -> dict[str, object]:
    del admin
    if not (file.filename or "").lower().endswith(".json"):
        raise ApiError(400, "only JSON files are supported")
    try:
        raw = json.loads((await file.read()).decode("utf-8"))
        bundle = ImportBundle.model_validate(raw)
    except (UnicodeDecodeError, json.JSONDecodeError, ValidationError) as exc:
        raise ApiError(400, "invalid import data") from exc
    await container.system.import_data(bundle)
    return success_response(None, msg="import success")
