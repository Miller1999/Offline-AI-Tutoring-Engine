"""Seed the vector store with the professor's notes.

This is the lightweight counterpart of ``scripts/ingest_docs.py``: it loads a
single Markdown file into the collection so that the tutor has a baseline
knowledge base even when the full Python documentation has not been ingested.

Usage:
    python scripts/seed_rag.py
"""

import argparse
import contextlib
import sys
from pathlib import Path
from typing import Any, cast

import chromadb
from chromadb.utils import embedding_functions

# Allow running the script directly from the repository root.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import get_settings
from app.core.logging import configure_logging, get_logger

logger = get_logger(__name__)

DEFAULT_NOTES_NAME = "professor_notes.md"
NOTES_TOPIC = "python_dictionaries"
NOTES_AUTHOR = "professor"
NOTES_ID = "note_python_dictionaries_01"


def seed(notes_path: Path | None = None) -> bool:
    """Load the professor notes into the vector store."""
    settings = get_settings()
    notes_path = notes_path or (settings.resources_dir / DEFAULT_NOTES_NAME)

    if not notes_path.exists():
        logger.error("Notes file not found: %s", notes_path)
        return False

    settings.chroma_dir.mkdir(parents=True, exist_ok=True)
    content = notes_path.read_text(encoding="utf-8")

    client = chromadb.PersistentClient(path=str(settings.chroma_dir))
    embedding_fn = cast(Any, embedding_functions.DefaultEmbeddingFunction())
    collection = client.get_or_create_collection(
        name=settings.chroma_collection,
        embedding_function=embedding_fn,
    )

    with contextlib.suppress(Exception):
        collection.delete(ids=[NOTES_ID])

    collection.add(
        documents=[content],
        metadatas=[
            {
                "tema": NOTES_TOPIC,
                "autor": NOTES_AUTHOR,
                "categoria": "handbook",
                "seccion": "dictionaries",
                "fuente": DEFAULT_NOTES_NAME,
                "archivo": DEFAULT_NOTES_NAME,
            }
        ],
        ids=[NOTES_ID],
    )

    logger.info(
        "Professor notes stored in '%s' (collection '%s', %s chunk(s))",
        settings.chroma_dir,
        settings.chroma_collection,
        collection.count(),
    )
    return True


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse the command line arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--notes",
        type=Path,
        default=None,
        help="Markdown file to load into the vector store",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Entry point of the seeding script."""
    settings = get_settings()
    configure_logging(settings.log_level)

    args = parse_args(argv)
    return 0 if seed(args.notes) else 1


if __name__ == "__main__":
    raise SystemExit(main())
