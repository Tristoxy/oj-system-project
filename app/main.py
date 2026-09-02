"""FastAPI application entry point."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI

from app.api import auth, health, languages, logs, plagiarism, problems, submissions, system, users
from app.container import AppContainer
from app.core.config import DEFAULT_DATA_DIR
from app.core.exceptions import register_exception_handlers


def create_app(data_dir: Path | None = None) -> FastAPI:
    """Create and configure the FastAPI application."""
    container = AppContainer(data_dir or DEFAULT_DATA_DIR)

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
    return application


app = create_app()
