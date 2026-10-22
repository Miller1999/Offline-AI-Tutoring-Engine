"""FastAPI application entry point."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.routes import evaluation, learning, system
from app.core.config import get_settings
from app.core.logging import configure_logging, get_logger
from app.services import database
from app.services import learning as learning_service

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Prepare the runtime environment before serving traffic."""
    settings = get_settings()
    configure_logging(settings.log_level)

    logger.info("Starting %s v%s", settings.app_name, settings.version)
    settings.ensure_directories()
    database.init_db()

    # Warm up the vector store. A missing knowledge base degrades the tutor
    # but must never prevent the API from starting.
    try:
        collection = learning_service.get_collection()
        if collection is None:
            logger.warning(
                "The vector store is not available. "
                "Run 'python scripts/ingest_docs.py' to enable RAG."
            )
        else:
            logger.info("Vector store ready with %s chunks", collection.count())
    except Exception as exc:  # noqa: BLE001 - never block startup
        logger.warning("Could not warm up the vector store: %s", exc)

    yield
    logger.info("Shutting down %s", settings.app_name)


def create_app() -> FastAPI:
    """Build and configure the FastAPI application."""
    settings = get_settings()

    application = FastAPI(
        title=settings.app_name,
        description=(
            "API for automated code evaluation, gating and Socratic RAG feedback. "
            "Runs entirely offline."
        ),
        version=settings.version,
        lifespan=lifespan,
    )

    # The platform is meant to be served locally; the tutor UI and any local
    # tooling may live on a different origin during development.
    application.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    application.include_router(system.router)
    application.include_router(evaluation.router)
    application.include_router(learning.router)

    if settings.frontend_dir.exists():
        application.mount(
            "/static",
            StaticFiles(directory=str(settings.frontend_dir)),
            name="static",
        )
    else:
        logger.warning("Frontend directory not found at %s", settings.frontend_dir)

    return application


app = create_app()
