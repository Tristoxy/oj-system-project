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
MAX_IMPORT_BYTES = 16 * 1024 * 1024


# 仅管理员可停止后台任务、清空持久化数据、重建默认项并退出当前会话。
@router.post("/reset/")
async def reset_system(
    response: Response,
    admin: User = Depends(require_admin),
    container: AppContainer = Depends(get_container),
) -> dict[str, object]:
    del admin
    await container.cancel_background_tasks()
    await container.system.reset()
    response.delete_cookie(SESSION_COOKIE)
    return success_response(None, msg="system reset successfully")


# 仅管理员可按课程固定结构导出用户、题目和提交数据。
@router.get("/export/")
async def export_data(
    admin: User = Depends(require_admin),
    container: AppContainer = Depends(get_container),
) -> dict[str, object]:
    del admin
    return success_response(await container.system.export_data())


# 校验管理员上传的 JSON 大小、结构和引用后，合并数据并恢复后台任务。
@router.post("/import/")
async def import_data(
    file: UploadFile = File(...),
    admin: User = Depends(require_admin),
    container: AppContainer = Depends(get_container),
) -> dict[str, object]:
    del admin
    if not (file.filename or "").lower().endswith(".json"):
        raise ApiError(400, "only JSON files are supported")
    content = await file.read(MAX_IMPORT_BYTES + 1)
    if len(content) > MAX_IMPORT_BYTES:
        raise ApiError(400, "import file is too large")
    try:
        raw = json.loads(content.decode("utf-8"))
        bundle = ImportBundle.model_validate(raw)
    except (UnicodeDecodeError, json.JSONDecodeError, ValidationError) as exc:
        raise ApiError(400, "invalid import data") from exc
    await container.system.validate_import(bundle)
    await container.cancel_background_tasks()
    try:
        await container.system.import_data(bundle)
    finally:
        # 第二阶段导入失败时也必须恢复验证后暂停的任务。
        # 成功导入也可能保留待处理的查重任务，因为课程固定数据包不会替换该进阶功能集合。
        await container.submissions.resume_pending()
        await container.plagiarism.resume_pending()
    return success_response(None, msg="import success")
