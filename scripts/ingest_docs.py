"""Ingest the official Python documentation into the ChromaDB vector store.

The script walks a directory of plain-text documentation, splits every file
into semantic chunks based on its section headings, vectorises them with the
offline ONNX MiniLM-L6-V2 embedding model and stores the result in the
persistent collection used by the tutor.

Everything runs locally: no network access is required.

Usage:
    python scripts/ingest_docs.py --source /path/to/python-docs-text
    python scripts/ingest_docs.py --source /path/to/python-docs-text --reset
"""

import argparse
import contextlib
import hashlib
import os
import re
import sys
from pathlib import Path
from typing import Any, cast

import chromadb
from chromadb.utils import embedding_functions
from tqdm import tqdm

# Allow running the script directly from the repository root.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import get_settings
from app.core.logging import configure_logging, get_logger

logger = get_logger(__name__)

#: Maximum size of a chunk, in characters.
CHUNK_MAX_CHARS = 2000

#: Minimum size of a chunk to be considered valid.
CHUNK_MIN_CHARS = 80

#: Root files that do not contain technical documentation.
ARCHIVES_TO_SKIP = {
    "about.txt",
    "bugs.txt",
    "contents.txt",
    "copyright.txt",
    "glossary.txt",
    "improve-page.txt",
    "improve-page-nojs.txt",
    "license.txt",
    "index.txt",
}


# ── Chunking helpers ──────────────────────────────────────────────────────


def extract_title(text: str) -> str:
    """Extract the document title (the first meaningful line)."""
    lines = text.strip().split("\n")
    for line in lines[:5]:
        line = line.strip()
        if (
            line
            and not line.startswith("**")
            and not line.startswith("==")
            and not re.match(r"^[\*\=\-]{3,}$", line)
        ):
            return line[:120]
    return "Untitled document"


def extract_sections(text: str) -> list[tuple[str, str]]:
    """Split a document into sections delimited by underlined headings."""
    lines = text.split("\n")
    sections: list[tuple[str, str]] = []
    current_lines: list[str] = []
    current_name = "__intro__"

    index = 0
    while index < len(lines):
        line = lines[index]

        # A separator line marks the end of the previous section title.
        if re.match(r"^[\=\-]{3,}$", line.strip()) and index > 0:
            section_name = lines[index - 1].strip()
            if current_lines:
                content = "\n".join(current_lines).strip()
                if len(content) >= CHUNK_MIN_CHARS:
                    sections.append((current_name, content))
            current_lines = []
            current_name = section_name
            index += 1
            continue

        # A "***" separator underlines the main document title.
        if re.match(r"^[\*]{3,}$", line.strip()) and index > 0:
            pass

        current_lines.append(line)
        index += 1

    if current_lines:
        content = "\n".join(current_lines).strip()
        if len(content) >= CHUNK_MIN_CHARS:
            sections.append((current_name, content))

    return sections


def subdivide_section(name: str, content: str) -> list[tuple[str, str]]:
    """Split an oversized section into smaller fragments."""
    if len(content) <= CHUNK_MAX_CHARS:
        return [(name, content)]

    fragments: list[tuple[str, str]] = []
    lines = content.split("\n")
    current_lines: list[str] = []
    current_name = name

    index = 0
    while index < len(lines):
        line = lines[index]

        if re.match(r"^[\-]{3,}$", line.strip()) and index > 0:
            if current_lines:
                text = "\n".join(current_lines).strip()
                if len(text) >= CHUNK_MIN_CHARS:
                    fragments.append((current_name, text))
            current_name = lines[index - 1].strip() if index > 0 else name
            current_lines = []
            index += 1
            continue

        current_lines.append(line)
        index += 1

    if current_lines:
        text = "\n".join(current_lines).strip()
        if len(text) >= CHUNK_MIN_CHARS:
            fragments.append((current_name, text))

    # Still too large: split further by paragraph.
    final_fragments: list[tuple[str, str]] = []
    for fragment_name, text in fragments:
        if len(text) <= CHUNK_MAX_CHARS:
            final_fragments.append((fragment_name, text))
            continue

        paragraphs = text.split("\n\n")
        group: list[str] = []
        size = 0
        for paragraph in paragraphs:
            if size + len(paragraph) > CHUNK_MAX_CHARS and group:
                final_fragments.append((fragment_name, "\n\n".join(group).strip()))
                group = [paragraph]
                size = len(paragraph)
            else:
                group.append(paragraph)
                size += len(paragraph) + 2

        if group:
            joined = "\n\n".join(group).strip()
            if len(joined) >= CHUNK_MIN_CHARS:
                final_fragments.append((fragment_name, joined))

    return final_fragments or [(name, content)]


def clean_chunk(text: str) -> str:
    """Remove redundant content that is useless for tutoring."""
    text = re.sub(r"\*\*Source code:\*\*.*", "", text)
    text = re.sub(r"\-\[ Footnotes \]\-.*", "", text, flags=re.DOTALL)
    text = re.sub(r"^[\*\=\-]{3,}$", "", text, flags=re.MULTILINE)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def build_chunk_id(category: str, filename: str, section: str, index: int) -> str:
    """Build a unique, readable identifier for a chunk."""
    base = f"{category}_{filename}_{section}_{index}"
    digest = hashlib.md5(base.encode()).hexdigest()[:8]  # noqa: S324 - not a security hash
    return f"{category}_{filename}_{index:04d}_{digest}"


# ── Security ──────────────────────────────────────────────────────────────

SUSPICIOUS_PATTERNS = (
    r"(?i)ignora\s+todas?\s+las\s+instrucciones",
    r"(?i)ignore\s+all\s+(previous|prior|above)\s+instructions",
    r"(?i)eres\s+ahora\s+un\s+asistente",
    r"(?i)you\s+are\s+now\s+(a\s+)?(helpful|useful)\s+assistant",
    r"(?i)override\s+system\s+prompt",
    r"(?i)anula\s+el\s+prompt\s+del\s+sistema",
    r"(?i)instrucciones?\s+secretas?",
    r"(?i)secret\s+instructions?",
    r"(?i)prioridad\s+(alta|mayor|superior)\s+que\s+las\s+instrucciones",
    r"(?i)higher\s+priority\s+than\s+(the\s+)?(system\s+)?instructions?",
    r"(?i)desobedece\s+las?\s+instrucciones?\s+(anteriores|del\s+sistema)",
    r"(?i)disobey\s+(the\s+)?(system\s+)?(previous\s+)?instructions?",
    r"(?i)nuevas?\s+instrucciones?\s+del\s+(sistema|administrador)",
    r"(?i)new\s+(system\s+)?instructions?\s+from\s+(the\s+)?admin",
)


def contains_suspicious_content(text: str, filename: str) -> bool:
    """Detect prompt injection payloads inside a document."""
    for pattern in SUSPICIOUS_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            logger.warning(
                "Suspicious content detected in '%s' (pattern %s...)",
                filename,
                pattern[:50],
            )
            return True
    return False


# ── Main pipeline ─────────────────────────────────────────────────────────


def scan_files(source_dir: Path) -> list[tuple[str, str, str]]:
    """Return every documentation file as ``(path, category, name)``."""
    files: list[tuple[str, str, str]] = []
    for root, _dirs, filenames in os.walk(source_dir):
        for filename in sorted(filenames):
            if not filename.endswith(".txt"):
                continue
            if filename in ARCHIVES_TO_SKIP:
                continue
            category = os.path.basename(root)
            files.append((os.path.join(root, filename), category, filename.replace(".txt", "")))
    return files


def ingest(source_dir: Path, reset: bool = False, batch_size: int = 100) -> int:
    """Chunk, vectorise and store every documentation file."""
    settings = get_settings()
    settings.chroma_dir.mkdir(parents=True, exist_ok=True)

    client = chromadb.PersistentClient(path=str(settings.chroma_dir))
    embedding_fn = cast(Any, embedding_functions.DefaultEmbeddingFunction())

    if reset:
        logger.info("Resetting collection '%s'", settings.chroma_collection)
        with contextlib.suppress(Exception):
            client.delete_collection(name=settings.chroma_collection)

    collection = client.get_or_create_collection(
        name=settings.chroma_collection,
        embedding_function=embedding_fn,
    )

    logger.info("Scanning %s for documentation files", source_dir)
    files = scan_files(source_dir)
    logger.info("Found %s .txt files to process", len(files))

    chunks: list[dict] = []
    errors = 0

    for path, category, filename in tqdm(files, desc="Processing files", unit="file"):
        try:
            with open(path, encoding="utf-8") as handle:
                text = handle.read()
        except OSError as exc:
            logger.warning("Could not read %s: %s", path, exc)
            errors += 1
            continue

        if not text.strip():
            continue

        if contains_suspicious_content(text, filename):
            logger.warning("Document '%s' rejected because of suspicious content.", filename)
            errors += 1
            continue

        title = extract_title(text)
        sections = extract_sections(text)

        if not sections:
            cleaned = clean_chunk(text)
            if len(cleaned) >= CHUNK_MIN_CHARS:
                sections = [("__full__", cleaned)]

        for section_name, section_content in sections:
            for sub_name, sub_content in subdivide_section(section_name, section_content):
                cleaned = clean_chunk(sub_content)
                if len(cleaned) < CHUNK_MIN_CHARS:
                    continue

                chunks.append(
                    {
                        "id": build_chunk_id(category, filename, sub_name, len(chunks)),
                        "document": cleaned,
                        "metadata": {
                            "fuente": f"{category}/{filename}",
                            "tema": title[:100],
                            "categoria": category,
                            "seccion": sub_name[:100],
                            "archivo": filename,
                        },
                    }
                )

    logger.info("Inserting %s chunks into the vector store", len(chunks))

    for start in range(0, len(chunks), batch_size):
        batch = chunks[start : start + batch_size]
        try:
            collection.add(
                documents=[chunk["document"] for chunk in batch],
                metadatas=[chunk["metadata"] for chunk in batch],
                ids=[chunk["id"] for chunk in batch],
            )
        except Exception as exc:  # noqa: BLE001 - keep ingesting the rest
            logger.warning("Error inserting batch %s: %s", start // batch_size + 1, exc)
            errors += len(batch)

    final_count = collection.count()
    logger.info("Ingestion complete: %s chunks in the collection, %s error(s)", final_count, errors)
    logger.info("Vector store location: %s", settings.chroma_dir)
    return final_count


def verify() -> None:
    """Run a few sample queries to confirm the knowledge base answers."""
    settings = get_settings()
    client = chromadb.PersistentClient(path=str(settings.chroma_dir))
    collection = client.get_collection(name=settings.chroma_collection)

    queries = [
        "How to use lists and list methods in Python",
        "How to open and read a file",
        "How to use dictionaries with keys and values",
        "How to handle exceptions with try except",
        "How to define a class and create objects",
    ]

    logger.info("Running %s verification queries", len(queries))
    for query in queries:
        results = collection.query(query_texts=[query], n_results=2)
        documents = (results.get("documents") or [[]])[0]
        metadatas = (results.get("metadatas") or [[]])[0]
        logger.info("Query: %s -> %s result(s)", query, len(documents))
        for index, document in enumerate(documents):
            metadata = metadatas[index] if index < len(metadatas) else {}
            logger.info(
                "  [%s] %s | %s | %s",
                index + 1,
                metadata.get("fuente", "unknown"),
                metadata.get("tema", "N/A"),
                document[:120].replace("\n", " "),
            )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse the command line arguments."""
    settings = get_settings()

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source",
        type=Path,
        default=settings.docs_source_dir,
        help="Directory holding the .txt documentation files",
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Delete the collection before ingesting",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=100,
        help="Number of chunks inserted per batch",
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="Run sample queries after the ingestion",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Entry point of the ingestion script."""
    settings = get_settings()
    configure_logging(settings.log_level)

    args = parse_args(argv)
    source = args.source.expanduser()

    if not source.exists():
        logger.error("Documentation directory not found: %s", source)
        logger.error("Pass --source PATH or set DOCS_SOURCE_DIR in your .env file.")
        return 1

    logger.info("Ingesting documentation from %s", source)
    ingest(source, reset=args.reset, batch_size=args.batch_size)

    if args.verify:
        verify()

    logger.info("The tutor can now rely on the expanded knowledge base.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
