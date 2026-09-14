"""FastAPI application entry point."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI

from app.api import ai, auth, health, languages, logs, plagiarism, problems, submissions, system, users
from app.container import AppContainer
from app.core.config import DEFAULT_DATA_DIR
from app.core.exceptions import register_exception_handlers


# 创建整个fastapi应用,datadir为默认数据保存目录
def create_app(data_dir: Path | None = None) -> FastAPI:
    """Create and configure the FastAPI application."""
    container = AppContainer(data_dir or DEFAULT_DATA_DIR) # 创建服务容器，包括用户、题目、ai、查重、评测器等

    # 应用生命周期，负责启动初始化和关闭后台任务
    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        await container.initialize() # 应用启动时执行
        try:
            yield
        finally:
            await container.close() # 应用关闭时执行

    # 创建fastapi对象
    application = FastAPI(
        title="Online Judge System",
        description="A small online judge built for the Python programming course.",
        version="1.0.0",
        lifespan=lifespan,
    )
    # 保存容器、注册异常处理器、注册路由
    application.state.container = container
    register_exception_handlers(application)
    application.include_router(health.router)
    application.include_router(auth.router)
    application.include_router(problems.router)
    application.include_router(languages.router)
    application.include_router(submissions.router)
    application.include_router(users.router)
    application.include_router(logs.router)
    application.include_router(system.router)
    application.include_router(plagiarism.router)
    application.include_router(ai.router)
    return application


app = create_app()
