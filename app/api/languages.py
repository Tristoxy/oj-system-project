"""Dynamic judge-language endpoints."""

from fastapi import APIRouter, Depends

from app.container import AppContainer
from app.core.responses import success_response
from app.dependencies import get_container, get_current_user
from app.models.language import LanguageCreate
from app.models.user import User


router = APIRouter(prefix="/api/languages", tags=["languages"])


@router.get("/")
async def list_languages(
    current_user: User = Depends(get_current_user),
    container: AppContainer = Depends(get_container),
) -> dict[str, object]:
    del current_user
    return success_response({"name": await container.languages.list_languages()})


@router.post("/")
async def register_language(
    payload: LanguageCreate,
    current_user: User = Depends(get_current_user),
    container: AppContainer = Depends(get_container),
) -> dict[str, object]:
    del current_user
    language = await container.languages.register(payload)
    return success_response({"name": language.name}, msg="language registered")
