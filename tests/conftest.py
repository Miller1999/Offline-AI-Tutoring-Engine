"""Shared pytest fixtures.

Every test runs against a temporary directory so that the suite never touches
the real SQLite database, the ChromaDB store or the sandbox working folders.
"""

import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.api.dependencies import get_rate_limiter  # noqa: E402
from app.core.config import get_settings  # noqa: E402
from app.services import learning as learning_service  # noqa: E402


@pytest.fixture(autouse=True)
def isolated_environment(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Point every runtime path to a temporary directory."""
    monkeypatch.setenv("SQLITE_PATH", str(tmp_path / "tutor.db"))
    monkeypatch.setenv("CHROMA_DIR", str(tmp_path / "chroma"))
    monkeypatch.setenv("SANDBOX_DIR", str(tmp_path / "sandbox"))
    monkeypatch.setenv("RATE_LIMIT_REQUESTS", "1000")

    get_settings.cache_clear()
    get_rate_limiter.cache_clear()
    learning_service.reset_cache()

    yield

    get_settings.cache_clear()
    get_rate_limiter.cache_clear()
    learning_service.reset_cache()


@pytest.fixture(autouse=True)
def stub_vector_store(monkeypatch: pytest.MonkeyPatch) -> None:
    """Disable the real ChromaDB connection.

    The default embedding function downloads an ONNX model on first use, which
    would make the suite depend on the network. Tests that need a collection
    install their own fake.
    """
    monkeypatch.setattr(learning_service, "get_collection", lambda: None)


class FakeCollection:
    """Minimal in-memory stand-in for a ChromaDB collection."""

    def __init__(
        self,
        metadatas: list[dict[str, Any]] | None = None,
        documents: list[str] | None = None,
    ) -> None:
        self.metadatas = metadatas or []
        self.documents = documents or ["content"] * len(self.metadatas)
        self.get_calls = 0

    def count(self) -> int:
        """Return the number of stored chunks."""
        return len(self.metadatas)

    def get(
        self,
        include: list[str] | None = None,
        where: dict[str, Any] | None = None,
        limit: int | None = None,
    ) -> dict[str, Any]:
        """Return the chunks matching the optional filter."""
        self.get_calls += 1
        indexes = list(range(len(self.metadatas)))

        if where:
            indexes = [
                index
                for index in indexes
                if all(self.metadatas[index].get(key) == value for key, value in where.items())
            ]

        if limit is not None:
            indexes = indexes[:limit]

        return {
            "metadatas": [self.metadatas[index] for index in indexes],
            "documents": [self.documents[index] for index in indexes],
        }

    def query(self, query_texts: list[str] | None = None, n_results: int = 5) -> dict[str, Any]:
        """Return the first chunks as a fake semantic search result."""
        selected = slice(0, min(n_results, len(self.metadatas)))
        return {
            "documents": [self.documents[selected]],
            "metadatas": [self.metadatas[selected]],
            "distances": [[0.25] * len(self.metadatas[selected])],
        }


@pytest.fixture
def fake_collection(monkeypatch: pytest.MonkeyPatch) -> FakeCollection:
    """Install a fake vector store and return it."""
    collection = FakeCollection(
        metadatas=[
            {
                "categoria": "library",
                "tema": "Data Structures",
                "seccion": "lists",
                "fuente": "library/list.txt",
            },
            {
                "categoria": "library",
                "tema": "Data Structures",
                "seccion": "dicts",
                "fuente": "library/dict.txt",
            },
            {
                "categoria": "tutorial",
                "tema": "Introduction",
                "seccion": "intro",
                "fuente": "tutorial/intro.txt",
            },
        ]
    )
    monkeypatch.setattr(learning_service, "get_collection", lambda: collection)
    learning_service.reset_cache()
    return collection
