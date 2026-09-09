"""FastAPI application entry point."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI

from app.api import ai, auth, health, languages, logs, plagiarism, problems, submissions, system, users
from app.container import AppContainer
from app.core.config import DEFAULT_DATA_DIR
from app.core.exceptions import register_exception_handlers


# 创建一套可指定数据目录的 FastAPI 应用，便于生产运行和测试隔离。
def create_app(data_dir: Path | None = None) -> FastAPI:
    """Create and configure the FastAPI application."""
    container = AppContainer(data_dir or DEFAULT_DATA_DIR)

    # 启动时初始化数据和待处理任务，退出时可靠取消所有后台任务。
    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        await container.initialize()
        try:
            yield
        finally:
            await container.close()

    application = FastAPI(
        title="Python Course OJ",
        description="A small online judge built for the Python programming course.",
        version="1.0.0",
        lifespan=lifespan,
    )
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
