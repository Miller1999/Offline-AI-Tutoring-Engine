"""Learning knowledge base backed by ChromaDB.

Exposes the documentation explorer endpoints: categories, topics, content and
semantic search over the ingested Python documentation.
"""

import threading
import time
from typing import Any, cast

import chromadb
from chromadb.utils import embedding_functions

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)

#: Maximum number of chunks returned by a listing query.
MAX_RESULTS_PER_QUERY = 500

#: Number of chunks returned by a semantic search.
MAX_SEARCH_RESULTS = 5

#: Time-to-live of the memoised category aggregation, in seconds.
CATEGORY_CACHE_TTL = 300.0

_client: Any | None = None
_collection: Any | None = None
_client_lock = threading.Lock()

_category_cache: tuple[float, list[dict[str, Any]]] | None = None
_category_cache_lock = threading.Lock()


def get_collection() -> Any | None:
    """Return the shared ChromaDB collection, or ``None`` when unavailable."""
    global _client, _collection

    if _collection is not None:
        return _collection

    settings = get_settings()

    with _client_lock:
        if _collection is not None:
            return _collection

        try:
            settings.chroma_dir.mkdir(parents=True, exist_ok=True)
            _client = chromadb.PersistentClient(path=str(settings.chroma_dir))
            embedding_fn = cast(Any, embedding_functions.DefaultEmbeddingFunction())
            _collection = _client.get_collection(
                name=settings.chroma_collection,
                embedding_function=embedding_fn,
            )
        except Exception as exc:  # noqa: BLE001 - the KB is optional, never crash the API
            logger.warning("Could not connect to ChromaDB: %s", exc)
            return None

    return _collection


def reset_cache() -> None:
    """Drop the memoised category aggregation. Intended for tests."""
    global _category_cache
    with _category_cache_lock:
        _category_cache = None


def get_categories() -> list[dict[str, Any]]:
    """Return every documentation category with its exact number of chunks.

    The prototype sampled the first 5000 chunks, which produced wrong counts
    for large categories. The full metadata set is scanned here and the result
    is memoised for :data:`CATEGORY_CACHE_TTL` seconds.
    """
    global _category_cache

    with _category_cache_lock:
        if _category_cache is not None:
            timestamp, cached = _category_cache
            if time.monotonic() - timestamp < CATEGORY_CACHE_TTL:
                return cached

    collection = get_collection()
    if collection is None:
        return []

    try:
        total = collection.count()
        if total == 0:
            return []

        # Metadata only: documents are never loaded into memory.
        result = collection.get(include=["metadatas"])
        metadatas = result.get("metadatas") or []

        counts: dict[str, int] = {}
        for metadata in metadatas:
            if not metadata:
                continue
            category = metadata.get("categoria")
            if category:
                counts[category] = counts.get(category, 0) + 1

        categories = [
            {"categoria": category, "total": count} for category, count in sorted(counts.items())
        ]
    except Exception as exc:  # noqa: BLE001 - degrade gracefully
        logger.warning("Could not read categories: %s", exc)
        return []

    with _category_cache_lock:
        _category_cache = (time.monotonic(), categories)

    return categories


def get_topics_by_category(category: str) -> list[dict[str, Any]]:
    """Return the topics available inside a category."""
    collection = get_collection()
    if collection is None:
        return []

    try:
        result = collection.get(
            where={"categoria": category},
            limit=MAX_RESULTS_PER_QUERY,
        )
        metadatas = result.get("metadatas") or []
    except Exception as exc:  # noqa: BLE001 - degrade gracefully
        logger.warning("Could not read topics for '%s': %s", category, exc)
        return []

    topics: dict[str, dict[str, Any]] = {}
    for metadata in metadatas:
        if not metadata or "tema" not in metadata:
            continue
        topic = metadata["tema"]
        entry = topics.setdefault(
            topic,
            {
                "tema": topic,
                "total_chunks": 0,
                "secciones": set(),
                "fuente_principal": metadata.get("fuente", ""),
            },
        )
        entry["total_chunks"] += 1
        if metadata.get("seccion"):
            entry["secciones"].add(metadata["seccion"])

    for entry in topics.values():
        entry["secciones"] = sorted(entry["secciones"])[:10]

    return sorted(topics.values(), key=lambda item: item["tema"])


def get_content_by_topic(topic: str, category: str | None = None) -> list[dict[str, Any]]:
    """Return the chunks belonging to a topic."""
    collection = get_collection()
    if collection is None:
        return []

    where_filter: dict[str, Any] = {"tema": topic}
    if category:
        where_filter["categoria"] = category

    try:
        result = collection.get(
            where=where_filter,
            limit=MAX_RESULTS_PER_QUERY,
        )
    except Exception as exc:  # noqa: BLE001 - degrade gracefully
        logger.warning("Could not read content for topic '%s': %s", topic, exc)
        return []

    documents = result.get("documents") or []
    metadatas = result.get("metadatas") or []

    content = []
    for index, document in enumerate(documents):
        metadata = metadatas[index] if index < len(metadatas) else {}
        content.append(
            {
                "seccion": metadata.get("seccion", "No section"),
                "contenido": document,
                "fuente": metadata.get("fuente", ""),
                "archivo": metadata.get("archivo", ""),
            }
        )

    return content


def search(query: str) -> list[dict[str, Any]]:
    """Run a semantic search across the whole knowledge base."""
    collection = get_collection()
    if collection is None:
        return []

    try:
        result = collection.query(query_texts=[query], n_results=MAX_SEARCH_RESULTS)
    except Exception as exc:  # noqa: BLE001 - degrade gracefully
        logger.warning("Semantic search failed: %s", exc)
        return []

    documents = (result.get("documents") or [[]])[0]
    metadatas = (result.get("metadatas") or [[]])[0]
    distances = (result.get("distances") or [[]])[0]

    items = []
    for index, document in enumerate(documents):
        metadata = metadatas[index] if index < len(metadatas) else {}
        distance = distances[index] if index < len(distances) else 0
        relevance = (
            max(0, min(100, round((1 - distance) * 100)))
            if isinstance(distance, int | float)
            else 0
        )
        items.append(
            {
                "contenido": document,
                "relevancia": relevance,
                "tema": metadata.get("tema", "No topic"),
                "seccion": metadata.get("seccion", "No section"),
                "fuente": metadata.get("fuente", ""),
                "categoria": metadata.get("categoria", ""),
            }
        )

    return items


def get_stats() -> dict[str, Any]:
    """Return general statistics about the knowledge base."""
    collection = get_collection()
    if collection is None:
        return {"total_chunks": 0, "total_categorias": 0, "conectado": False}

    try:
        categories = get_categories()
        return {
            "total_chunks": collection.count(),
            "total_categorias": len(categories),
            "categorias": categories,
            "conectado": True,
        }
    except Exception as exc:  # noqa: BLE001 - degrade gracefully
        return {
            "total_chunks": 0,
            "total_categorias": 0,
            "conectado": False,
            "error": str(exc),
        }
