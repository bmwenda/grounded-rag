"""ASGI entry point and application lifecycle."""

from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from pathlib import Path
from threading import Lock

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from src.chat_history_service import ManagedChatRepository
from src.chat_repository import SqlChatRepository
from src.config import database_url_from_env
from src.profile_repository import SqlProfileRepository
from src.profile_service import ManagedProfileRepository

from .errors import register_error_handlers
from .routers.chats import router as chat_router
from .routers.profiles import router as profile_router


def _default_repository() -> ManagedProfileRepository:
    return SqlProfileRepository(database_url_from_env())


def _default_chat_repository() -> ManagedChatRepository:
    return SqlChatRepository(database_url_from_env())


def create_app(
    repository_factory: Callable[[], ManagedProfileRepository] = _default_repository,
    chat_repository_factory: Callable[[], ManagedChatRepository] = _default_chat_repository,
) -> FastAPI:
    """Build the API without opening a database connection at import time."""

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        repository = repository_factory()
        application.state.profile_repository = repository
        application.state.chat_repository_factory = chat_repository_factory
        application.state.chat_repository_lock = Lock()
        application.state.chat_repository = None
        try:
            yield
        finally:
            try:
                chat_repository = application.state.chat_repository
                if chat_repository is not None:
                    chat_repository.close()
            finally:
                repository.close()
                del application.state.profile_repository

    application = FastAPI(
        title="Grounded RAG",
        lifespan=lifespan,
        openapi_url=None,
        docs_url=None,
        redoc_url=None,
    )
    register_error_handlers(application)
    application.include_router(profile_router, prefix="/v1")
    application.include_router(chat_router, prefix="/v1")
    static_directory = Path(__file__).resolve().parents[1] / "static"
    application.mount("/static", StaticFiles(directory=static_directory), name="static")

    @application.get("/", include_in_schema=False)
    def chat_page() -> FileResponse:
        return FileResponse(static_directory / "index.html")

    return application


app = create_app()
