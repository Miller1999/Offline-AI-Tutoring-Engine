# Architecture

This document describes how the platform is put together after the 2026 restructure.

## Layers

```text
┌──────────────────────────────────────────────────────────────────────┐
│                       FRONTEND (frontend/)                            │
│  index.html · styles.css · app.js — no build step, no framework      │
│  [Exercise generator] [Code upload] [Documentation explorer]          │
└──────────────────────────┬───────────────────────────────────────────┘
                           │ HTTP (multipart/form-data, JSON)
                           ▼
┌──────────────────────────────────────────────────────────────────────┐
│                        API LAYER (app/api/)                           │
│  routes/system.py     routes/evaluation.py     routes/learning.py    │
│  dependencies.py      schemas/responses.py                          │
└───────┬───────────────────────────────┬──────────────────────────────┘
        │                               │
        ▼                               ▼
┌────────────────────────────┐  ┌──────────────────────────────────────┐
│      SERVICES (app/services)│  │        CORE (app/core)               │
│  orchestrator.py            │  │  config.py · logging.py              │
│  database.py                │  │  prompts.py · security.py            │
│  learning.py · exercises.py │  │  sandbox.py                          │
└───────┬────────────────────┘  └───────────┬──────────────────────────┘
        │                                   │
        ▼                                   ▼
┌────────────────────────────┐  ┌──────────────────────────────────────┐
│      LOCAL DEPENDENCIES      │  │            PERSISTENCE                │
│  Docker sandbox (pytest)    │  │  SQLite: data/tutor.db               │
│  Ollama (local LLM)          │  │  ChromaDB: data/chroma/              │
│  ChromaDB (RAG)              │  │  Sandbox workspaces: data/sandbox/   │
└────────────────────────────┘  └──────────────────────────────────────┘
```

## Modules

| Module | Responsibility |
|--------|----------------|
| `app/main.py` | Application factory, lifespan, CORS, static mount |
| `app/core/config.py` | Every tunable, read from the environment and `.env` |
| `app/core/logging.py` | Single structured logger for the whole project |
| `app/core/prompts.py` | System prompts (ES/EN) and the difficulty definitions |
| `app/core/security.py` | Sanitisation, validation, output guardrails, rate limiter |
| `app/core/sandbox.py` | Docker command, report parsing, execution with a timeout |
| `app/services/orchestrator.py` | Ollama calls, RAG lookups, exercise generation |
| `app/services/database.py` | SQLite: gating, attempts, history, current topic |
| `app/services/learning.py` | ChromaDB: categories, topics, content, search, stats |
| `app/services/exercises.py` | The built-in exercise shipped in `resources/` |
| `app/api/routes/*` | Thin HTTP layer: validation, rate limit, delegation |
| `app/schemas/responses.py` | Pydantic models that define the public contract |

## Evaluation flow

```text
student uploads a .py file
        ↓
POST /evaluate
        ↓
validate student_id  → 400 on failure
        ↓
per-IP rate limit    → 429 on failure
        ↓
read the hidden test suite (dynamic: per student, static: built-in)
        ↓
create an isolated workspace data/sandbox/<uuid>/
        ↓
write exercise_student.py + test_exercise.py
        ↓
docker run --rm --network none --memory 256m --cpus 0.5
        ↓
read report.json, parse the results, delete the workspace
        ↓
record the attempt and the history in SQLite
        ↓
passed?  → success
failed?  → RAG lookup + Ollama → Socratic feedback (guarded)
```

## Reading the sandbox report

`pytest-json-report` describes a failing run in three different ways, and the parser has to
tell them apart — the difference between "the student failed" and "the student's code did not
even compile" is exactly what the tutor needs to give a useful hint.

| Failure | Where pytest puts it | What the tutor receives |
|----------|----------------------|-------------------------|
| **Collection error** — the module does not import (syntax error, missing function) | `collectors[].outcome == "failed"` and an **empty** `tests` list | The exception extracted from the `E ` lines of the traceback |
| **Setup error** — a fixture fails before the test body | `tests[].setup.outcome == "failed"` | The crash message of the `setup` phase |
| **Assertion error** | `tests[].call.outcome == "failed"` | The crash message of the `call` phase |

The collection error is the dangerous one: a parser that only iterates over `tests` finds an
empty list, concludes that everything passed and reports a broken submission as a success —
which also advances the gating of that student. `app/core/sandbox.py` therefore inspects the
collectors first, and `tests/test_sandbox.py` locks the behaviour down with the three real
report shapes.

## Isolation model

Every evaluation gets its own directory, so two students evaluating at the same time can never
interfere with each other. The Docker container adds a second boundary:

- no network (`--network none`)
- memory and CPU limits
- the container is destroyed right after the run (`--rm`)
- the workspace is deleted in a `finally` block, even when the run fails

## Local model footprint

The latency of the tutor is not only a matter of model size: it depends on how the model is
*configured* on the Ollama side, and the API does not leave that to chance.

| Knob | Where | Why it matters |
|------|-------|----------------|
| `OLLAMA_CONTEXT_LENGTH` | `options.num_ctx` of every request | The KV cache grows with the context. A 32k context on a 7B model needs ~17GB of memory instead of ~5GB; on a 12GB GPU it spills into system RAM and every answer takes minutes. The API pins the value instead of inheriting the server-wide setting. |
| `OLLAMA_KEEP_ALIVE` | `keep_alive` of every request | The Ollama default unloads the model after five minutes. The tutor asks for it to stay loaded so a session never pays a cold start mid-conversation. |
| Warm-up | `orchestrator.warm_up_model()` | The API loads the model in a background thread during startup. `GET /health` exposes `model_ready` so a client can wait for it. |

Measured on an RTX 5070 Ti (12GB) with `qwen2.5-coder:7b`: the end-to-end journey went from
**436 s to 16 s** once the context window was pinned and the model was kept warm.

## Knowledge base

`scripts/ingest_docs.py` walks a directory of `.txt` documentation, splits every file into
semantic chunks (sections, then paragraphs), vectorises them with the offline ONNX
MiniLM-L6-V2 model and stores them in the ChromaDB collection configured in `CHROMA_COLLECTION`.

`app/services/learning.py` reads that collection and exposes it through the `/learning` routes.
The category aggregation is memoised for 5 minutes because it scans the full metadata set.

## Adaptive difficulty

The number of approved exercises of a student in a topic drives the level of the next generated
exercise:

| Approved exercises | Level | Focus |
|--------------------|-------|-------|
| 0 | Beginner | Fundamental concepts |
| 1-2 | Intermediate | Combining methods |
| 3+ | Advanced | Edge cases, complex algorithms |

## Configuration

Every value comes from the environment (or the `.env` file, see `.env.example`):

| Variable | Default | Purpose |
|----------|---------|---------|
| `TUTOR_LOCALE` | `es` | Language the tutor speaks to the students |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Local LLM server |
| `OLLAMA_MODEL` | `qwen2.5-coder:7b` | Model used by the tutor |
| `OLLAMA_TIMEOUT_SECONDS` | `120` | Timeout of every LLM call |
| `CHROMA_DIR` | `data/chroma` | Vector store location |
| `CHROMA_COLLECTION` | `material_clase` | Collection name |
| `SQLITE_PATH` | `data/tutor.db` | Gating and history database |
| `SANDBOX_DIR` | `data/sandbox` | Sandbox workspaces |
| `SANDBOX_IMAGE` | `sandbox-evaluador` | Docker image used for the evaluation |
| `SANDBOX_MEMORY` | `256m` | Memory limit of the sandbox |
| `SANDBOX_CPUS` | `0.5` | CPU limit of the sandbox |
| `SANDBOX_TIMEOUT_SECONDS` | `60` | Maximum duration of an evaluation |
| `MAX_UPLOAD_BYTES` | `100000` | Maximum size of an uploaded file |
| `RATE_LIMIT_REQUESTS` | `10` | Requests allowed per IP and per window |
| `RATE_LIMIT_WINDOW_SECONDS` | `60` | Length of the rate limit window |
| `DOCS_SOURCE_DIR` | `data/docs-source` | Default source of the ingestion |

## API contract

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/` | Serves the frontend |
| `GET` | `/health` | Liveness probe (API, vector store, model) |
| `GET` | `/static/*` | Frontend assets |
| `POST` | `/evaluate` | Evaluates an uploaded solution in the sandbox |
| `POST` | `/generate` | Generates a dynamic exercise with a hidden test suite |
| `GET` | `/exercises/default` | Returns the built-in exercise |
| `GET` | `/learning/categories` | Documentation categories |
| `GET` | `/learning/topics` | Topics of a category |
| `GET` | `/learning/content` | Content of a topic |
| `GET` | `/learning/search` | Semantic search |
| `GET` | `/learning/stats` | Knowledge base statistics |

Every response carries a `status` field with one of three values:

- `success` — the operation succeeded
- `failure` — the operation ran but the student code did not pass the tests
- `error` — the operation could not be completed (validation, infrastructure, unknown exercise)

## Additive and breaking changes

The 2026 restructure kept the behaviour of the platform but changed the public contract:

| Before | Now |
|--------|-----|
| `status: "exito"` | `status: "success"` |
| `status: "fallo"` | `status: "failure"` |
| `status: "error_servidor"` | `status: "error"` |
| `POST /evaluar` | `POST /evaluate` |
| `POST /generar` | `POST /generate` |
| `GET /aprendizaje/*` | `GET /learning/*` |
| `alumno_id` | `student_id` |
| `tema` | `topic` |
| `ejercicio_id: "dinamico"` | `exercise_id: "dynamic"` |
| `data.datos.instrucciones` | `data.instructions` |
| `data.datos.ejemplo_esperado` | `data.expected_example` |
| `data.datos.codigo_base` | `data.starter_code` |
| `feedback_tutor` | `tutor_feedback` |
