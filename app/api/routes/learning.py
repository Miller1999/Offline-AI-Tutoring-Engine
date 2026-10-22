"""Learning routes: browse and search the ingested documentation."""

from fastapi import APIRouter, Query

from app.core.config import get_settings
from app.core.security import ValidationError, validate_length
from app.schemas.responses import (
    CategoriesResponse,
    ContentResponse,
    SearchResponse,
    StatsResponse,
    TopicsResponse,
)
from app.services import learning

router = APIRouter(prefix="/learning", tags=["learning"])


@router.get("/stats", response_model=StatsResponse, summary="Knowledge base statistics")
def stats() -> StatsResponse:
    """Return general statistics about the vector store."""
    data = learning.get_stats()
    return StatsResponse(
        status="success",
        total_chunks=data.get("total_chunks", 0),
        total_categorias=data.get("total_categorias", 0),
        conectado=data.get("conectado", False),
        categorias=data.get("categorias", []),
    )


@router.get("/categories", response_model=CategoriesResponse, summary="Documentation categories")
def categories() -> CategoriesResponse:
    """Return every documentation category with its chunk count."""
    return CategoriesResponse(status="success", categorias=learning.get_categories())


@router.get("/topics", response_model=TopicsResponse, summary="Topics of a category")
def topics(
    categoria: str = Query(..., description="Documentation category", min_length=1),
) -> TopicsResponse:
    """Return the topics available inside a category."""
    settings = get_settings()
    try:
        categoria = validate_length(categoria, settings.max_query_length, "categoria")
    except ValidationError:
        return TopicsResponse(status="error", temas=[])

    return TopicsResponse(status="success", temas=learning.get_topics_by_category(categoria))


@router.get("/content", response_model=ContentResponse, summary="Content of a topic")
def content(
    tema: str = Query(..., description="Topic title", min_length=1),
    categoria: str | None = Query(None, description="Optional category filter"),
) -> ContentResponse:
    """Return the documentation chunks belonging to a topic."""
    settings = get_settings()
    try:
        tema = validate_length(tema, settings.max_query_length, "tema")
        if categoria:
            categoria = validate_length(categoria, settings.max_query_length, "categoria")
    except ValidationError:
        return ContentResponse(status="error", contenido=[])

    return ContentResponse(
        status="success", contenido=learning.get_content_by_topic(tema, categoria)
    )


@router.get("/search", response_model=SearchResponse, summary="Semantic search")
def search(
    q: str = Query(..., description="Search query", min_length=1),
) -> SearchResponse:
    """Run a semantic search across the whole knowledge base."""
    settings = get_settings()
    try:
        q = validate_length(q, settings.max_query_length, "query")
    except ValidationError:
        return SearchResponse(status="error", resultados=[])

    return SearchResponse(status="success", resultados=learning.search(q))
