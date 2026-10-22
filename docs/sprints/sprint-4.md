# Sprint 4 — Mass Documentation Ingestion and Learning API

## Sprint Objectives

- Implement the mass ingestion of the official Python documentation (528+ `.txt` files) into
  ChromaDB
- Create a structured query API for the "Learning" section of the frontend
- Improve the RAG context of the orchestrator with multiple fragments and enriched metadata
- Keep the system 100% offline with local embeddings (ONNX MiniLM-L6-V2)

---

## Components Built

### `scripts/ingest_docs.py` — Mass ingester

Main script that scans, chunks, vectorises and stores the official Python 3.14 documentation in
ChromaDB.

**Key characteristics:**

| Characteristic | Detail |
|----------------|--------|
| Recursive scan | Walks every subdirectory of the documentation |
| Smart filtering | Skips non-technical files (`about.txt`, `copyright.txt`, ...) |
| Semantic chunking | Splits by sections (detecting `===`, `---`, `***`) |
| Adaptive subdivision | Fragments large sections by paragraph |
| Noise cleaning | Removes copyrights, "Source code:", footnotes |
| Unique IDs | Generates hashed + sequential identifiers |
| Batch insertion | Batches of 100 chunks to avoid saturating ChromaDB |
| Verification pass | Sample semantic queries after the ingestion |

**Chunking pipeline:**

```text
.txt file (Python documentation)
        ↓
extract_title() → document title
        ↓
extract_sections() → [(section, content), ...]
        ↓
subdivide_section() → fragmentation when > 2000 characters
        ↓
clean_chunk() → noise removal
        ↓
build_chunk_id() → hashed ID for ChromaDB
        ↓
collection.add() → bulk insertion into the vector store
```

### `app/services/learning.py` — Query API for the frontend

Module that exposes the knowledge base to `app/main.py`.

**Architecture:**
- **Singleton:** lazy connection to ChromaDB (created on the first query)
- **Cache:** client and collection are kept in a global
- **100% offline:** local ONNX MiniLM-L6-V2 embeddings

**Exposed functions:**

| Function | HTTP endpoint | Purpose |
|----------|---------------|---------|
| `get_categories()` | `GET /learning/categories` | List of categories with the chunk count |
| `get_topics_by_category()` | `GET /learning/topics` | Topics inside a category |
| `get_content_by_topic()` | `GET /learning/content` | Content chunks of a topic |
| `search()` | `GET /learning/search` | RAG semantic search |
| `get_stats()` | `GET /learning/stats` | General statistics |

---

## Ingester Configuration

The configuration now comes from the environment (`.env` file) instead of hardcoded paths:

```ini
DOCS_SOURCE_DIR=C:/Users/you/Downloads/python-3.14-docs-text/python-3.14-docs-text
CHROMA_DIR=./data/chroma
CHROMA_COLLECTION=material_clase
```

**Files excluded by default:**
`about.txt`, `bugs.txt`, `contents.txt`, `copyright.txt`, `glossary.txt`, `improve-page.txt`,
`improve-page-nojs.txt`, `license.txt`, `index.txt`

---

## Orchestrator Improvements

### Enriched RAG

`get_socratic_hint()` was improved:

- **More fragments:** it now retrieves `n_results=3` (previously 1)
- **Enriched metadata:** each fragment includes the source, topic, section and relevance distance
- **Logging:** shows the ChromaDB statistics on every query
- **Improved prompt:** a richer context with multiple RAG fragments

```python
# Before: 1 fragment without metadata
result = collection.query(query_texts=[search_text], n_results=1)

# After: 3 fragments with full metadata
result = collection.query(query_texts=[search_text], n_results=3)
# Each fragment includes: source, topic, section, relevance distance
```

### Updated system prompt

```python
system_prompt = f"""You are a Socratic programming tutor. Your goal is to help
the student understand why their code failed, using ONLY the professor's notes.

PROFESSOR'S NOTES (Retrieved from the RAG):
{retrieved_notes}

STRICT INSTRUCTIONS:
1. Speak DIRECTLY to the student (e.g. "In your code, the error happens because...").
2. Compare the student error with the professor's notes.
3. Formulate ONE SINGLE Socratic question at the end.
4. DO NOT add anything after the question. End with (?).
5. UNDER NO CIRCUMSTANCE WRITE CODE.
"""
```

---

## Vector Database Layout

```
data/chroma/
├── chroma.sqlite3          # ChromaDB metadata and configuration
└── <uuid>/                 # Directories with the vector data of each collection
    ├── data_level0.bin     # Embedding vectors
    ├── header.bin          # Index header
    ├── index_metadata.pickle # Index metadata
    ├── length.bin          # Lengths
    └── link_lists.bin      # Link lists
```

---

## Post-Ingestion Statistics

- **Total chunks inserted:** depends on the documentation available
- **Categories processed:** `library`, `tutorial`, `reference`, `howto`, `using`, `extending`,
  `distributing`, `install`, `faq`
- **Embeddings:** ONNX MiniLM-L6-V2 (100% offline)
- **Collection:** `material_clase`

---

## Verification Pass

The script exposes a `--verify` flag that runs 5 sample semantic queries:

```python
queries = [
    "How to use lists and list methods in Python",
    "How to open and read a file",
    "How to use dictionaries with keys and values",
    "How to handle exceptions with try except",
    "How to define a class and create objects",
]
```

Run it with:

```bash
python scripts/ingest_docs.py --source /path/to/python-docs-text --verify
```

---

## Files Changed

| File | Type | Purpose |
|------|------|---------|
| `scripts/ingest_docs.py` | New | Mass ingestion of the documentation into ChromaDB |
| `app/services/learning.py` | New | Query API for the learning frontend |
| `app/services/orchestrator.py` | Modified | RAG enriched with `n_results=3` and full metadata |
| `app/api/routes/learning.py` | New | The 5 learning endpoints |
| `frontend/` | Modified | "Learning" tab with the documentation browser |

---

## Notes after the 2026 restructure

The ingester no longer asks for interactive input: the source directory comes from
`--source` or `DOCS_SOURCE_DIR`, and the verification pass runs with `--verify`. The category
counter no longer samples the first 5000 chunks (which produced wrong counts on large
categories): the full metadata set is scanned and memoised for 5 minutes.
