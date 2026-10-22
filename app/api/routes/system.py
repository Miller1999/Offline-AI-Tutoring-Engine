"""System routes: liveness probe and frontend delivery."""

from fastapi import APIRouter
from fastapi.responses import FileResponse

from app.core.config import get_settings
from app.core.logging import get_logger
from app.schemas.responses import HealthResponse
from app.services import learning

logger = get_logger(__name__)

router = APIRouter(tags=["system"])


@router.get("/health", response_model=HealthResponse, summary="Liveness probe")
def health() -> HealthResponse:
    """Report the health of the API and of its local dependencies."""
    settings = get_settings()
    vector_store = learning.get_collection() is not None

    return HealthResponse(
        status="healthy" if vector_store else "degraded",
        version=settings.version,
        llm=settings.ollama_model,
        vector_store=vector_store,
    )


@router.get("/", include_in_schema=False)
def index() -> FileResponse:
    """Serve the single-page frontend."""
    settings = get_settings()
    index_file = settings.frontend_dir / "index.html"

    if not index_file.exists():
        logger.warning("Frontend not found at %s", index_file)

    return FileResponse(index_file)
