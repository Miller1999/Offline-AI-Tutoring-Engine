# 🧠 Offline AI Tutoring Engine

[![Python](https://img.shields.io/badge/Python-3.12+-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.136-009688?style=for-the-badge&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![Docker](https://img.shields.io/badge/Docker-Required-2496ED?style=for-the-badge&logo=docker&logoColor=white)](https://docker.com)
[![Ollama](https://img.shields.io/badge/Ollama-Required-000000?style=for-the-badge&logo=ollama&logoColor=white)](https://ollama.com)
[![ChromaDB](https://img.shields.io/badge/ChromaDB-Offline_RAG-FC60A8?style=for-the-badge&logo=chromadb&logoColor=white)](https://www.trychroma.com)
[![SQLite](https://img.shields.io/badge/SQLite-003B57?style=for-the-badge&logo=sqlite&logoColor=white)](https://sqlite.org)

A **fully offline**, AI-powered programming tutoring platform. It evaluates student code inside an
isolated Docker sandbox, gives Socratic feedback through a local LLM (Qwen 2.5 Coder 7B), and
tracks student progress with SQLite gating and rote-learning metrics.

> **Core philosophy**: the tutor NEVER writes code for the student. It uses Socratic questioning
> and RAG over the official Python documentation to guide students towards discovering the
> solution themselves.

---

## 📋 Table of contents

- [Features](#-features)
- [Prerequisites](#-prerequisites)
- [Installation](#-installation)
- [Usage](#-usage)
- [API reference](#-api-reference)
- [Project structure](#-project-structure)
- [Key concepts](#-key-concepts)
- [Configuration](#-configuration)
- [Development](#-development)
- [Troubleshooting](#-troubleshooting)
- [Documentation](#-documentation)

---

## ✨ Features

| Feature | Description | Status |
|---------|-------------|--------|
| 🐳 **Safe code execution** | Student code runs in an isolated Docker container with no network and a 256MB RAM limit | ✅ |
| 🤖 **Local AI tutor** | Qwen 2.5 Coder 7B through Ollama — fully offline, no API key | ✅ |
| 🧠 **Socratic method** | The AI never writes code; it asks questions that lead the student to the solution | ✅ |
| 📚 **RAG knowledge base** | ChromaDB vector search over the Python documentation | ✅ |
| 📊 **Gating system** | Each exercise must be passed to progress; SQLite records every attempt | ✅ |
| 🔄 **Adaptive difficulty** | The difficulty scales automatically (beginner → intermediate → advanced) | ✅ |
| 📝 **Dynamic exercise generation** | The AI writes unique exercises with hidden test suites | ✅ |
| 🔍 **Semantic documentation search** | Browse and search the documentation from the frontend | ✅ |
| 🚫 **Hard guardrails** | Several layers prevent the AI from revealing the solution | ✅ |
| 🧪 **Test suite** | Unit and API tests covering security, persistence, RAG and routing | ✅ |
| 🔎 **Smoke test** | An end-to-end harness that drives the real API, the real sandbox and the real LLM | ✅ |

---

## 🛠️ Prerequisites

| Component | Version | Purpose |
|-----------|---------|---------|
| **Python** | 3.12+ | Backend runtime |
| **Docker Desktop** | Latest | Sandboxed code execution |
| **Ollama** | Latest | Local LLM server |
| **Git** | Latest | Version control (optional) |

The project was developed on Windows 11 and also runs on macOS and Linux.

---

## 🚀 Installation

### 1. Install Python 3.12+

```bash
python --version
# Expected: Python 3.12.x or newer
```

### 2. Install Docker Desktop

Docker runs the student code in a secure, isolated sandbox.

```bash
docker --version
docker ps
```

> **Note**: allocate at least 2GB of RAM to Docker Desktop (Settings → Resources → Advanced).

### 3. Install Ollama and pull the model

```bash
ollama --version
ollama pull qwen2.5-coder:7b   # ~7.6 GB
ollama list
```

Smaller alternatives: `qwen2.5-coder:1.5b`, `codellama:7b`, `deepseek-coder:6.7b`. Change
`OLLAMA_MODEL` in your `.env` file to use another one.

### 4. Clone and set up the project

```bash
git clone <repository-url>
cd <repository-folder>

python -m venv .venv
.venv\Scripts\activate          # Windows
source .venv/bin/activate       # macOS / Linux

pip install -r requirements.txt
pip install -r requirements-dev.txt   # only for development
```

### 5. Configure the environment

```bash
cp .env.example .env            # Windows: copy .env.example .env
```

Edit `.env` if your setup differs from the defaults (paths, model, limits).

### 6. Build the sandbox image

```bash
docker build -t sandbox-evaluador .
docker images
```

### 7. (Optional) Ingest the documentation

This loads the official Python documentation into ChromaDB so the tutor can answer with the real
documentation instead of the model's own memory.

1. Download the text version of the documentation from
   [python.org/downloads](https://www.python.org/downloads/) and extract it.
2. Point the ingester at the extracted folder:

```bash
python scripts/ingest_docs.py --source /path/to/python-docs-text --verify
```

Without this step the platform still works, but the knowledge base stays limited to the
professor's notes (`scripts/seed_rag.py`).

### 8. Run the server

```bash
uvicorn app.main:app --reload --port 8000
```

Open <http://localhost:8000>. The interface has two tabs:

- **📝 Exercises** — the exercise generator and the code evaluator
- **📖 Learning** — the documentation explorer with semantic search

---

## 🎮 Usage

### Generate → Solve → Submit → Feedback

**Step 1 — Generate an exercise**

1. Open the **Exercises** tab
2. Enter your **Student ID** (e.g. `student_001`)
3. Choose a **topic** (e.g. `Dictionary Manipulation`)
4. Click **Generate Exercise**

**Step 2 — Solve it**

Copy the **Starter Code** into a `.py` file and write your solution.

**Step 3 — Submit**

1. Enter the same **Student ID**
2. Set **Exercise ID** to `dynamic` (for a generated exercise) or `default` (for the built-in one)
3. Upload your `.py` file
4. Click **Evaluate Code**

**Step 4 — Read the feedback**

- ✅ **Success** — every test passed
- 🧠 **Failure** — the tutor asks you a Socratic question based on the official documentation
- ⚠️ **Error** — the evaluation itself could not be completed

### Explore the documentation

1. Switch to the **Learning** tab
2. Browse **Categories → Topics → Content**
3. Use the semantic search bar for questions such as "how to use dictionaries"

---

## 📡 API reference

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/` | Serves the frontend |
| `GET` | `/health` | Liveness probe |
| `GET` | `/static/*` | Frontend assets |
| `POST` | `/evaluate` | Evaluates an uploaded solution in the sandbox |
| `POST` | `/generate` | Generates a dynamic exercise with hidden tests |
| `GET` | `/exercises/default` | Returns the built-in exercise |
| `GET` | `/learning/categories` | Documentation categories |
| `GET` | `/learning/topics?categoria=` | Topics of a category |
| `GET` | `/learning/content?tema=` | Content of a topic |
| `GET` | `/learning/search?q=` | Semantic search |
| `GET` | `/learning/stats` | Knowledge base statistics |

Every response carries a `status` field: `success`, `failure` or `error`.

### `POST /evaluate`

**Body** (`multipart/form-data`):

| Field | Type | Description |
|-------|------|-------------|
| `student_id` | string | Student identifier |
| `exercise_id` | string | `dynamic` or `default` |
| `file` | file | The `.py` solution |

**Success:**

```json
{
  "status": "success",
  "message": "All tests passed. Great work!"
}
```

**Socratic feedback:**

```json
{
  "status": "failure",
  "tutor_feedback": "Look at your 'calculate_discounts' function. Are you iterating over prices.items() or only over prices? Check how you access the dictionary keys...",
  "failed_test": "test_discount"
}
```

### `POST /generate`

**Body** (`multipart/form-data`): `student_id`, `topic`.

```json
{
  "status": "success",
  "data": {
    "instructions": "Write a function called ...",
    "expected_example": "input: {...} -> output: {...}",
    "starter_code": "def my_function(param):\n    pass"
  }
}
```

The hidden test suite is never part of the response.

> The previous prototype used `/evaluar`, `/generar`, `/aprendizaje/*`, `alumno_id`, `tema` and the
> `exito` / `fallo` statuses. The complete list of breaking changes is in
> [docs/architecture.md](docs/architecture.md#additive-and-breaking-changes).

---

## 📁 Project structure

```text
.
├── app/                        # Application package
│   ├── main.py                 # FastAPI application factory and lifespan
│   ├── core/                   # config, logging, prompts, security, sandbox
│   ├── services/               # orchestrator, database, learning, exercises
│   ├── api/                    # routes, dependencies, response schemas
│   └── schemas/                # Pydantic models
│
├── frontend/                   # Static UI (no build step)
│   ├── index.html
│   ├── styles.css
│   └── app.js
│
├── resources/                  # Versioned learning resources
│   ├── exercises/default/      # The built-in exercise
│   └── professor_notes.md      # Baseline knowledge base
│
├── scripts/
│   ├── ingest_docs.py          # Mass ingestion of the documentation
│   ├── seed_rag.py             # Loads the professor notes into the store
│   └── smoke_test.py           # End-to-end verification of the whole stack
│
├── tests/                      # pytest suite
│   ├── conftest.py
│   ├── test_security.py
│   ├── test_database.py
│   ├── test_learning.py
│   ├── test_sandbox.py
│   ├── test_orchestrator.py
│   └── test_api.py
│
├── docs/                       # Architecture, security, roadmap, sprint notes
├── data/                       # Runtime data (ignored by git)
│
├── Dockerfile                  # Sandbox image (Alpine + pytest)
├── docker-compose.yml
├── Makefile
├── pyproject.toml
└── requirements.txt
```

---

## 🔑 Key concepts

### 🧪 Sandboxed execution

Student code runs in an isolated Docker container:

- ❌ No network (`--network none`)
- 💾 256MB RAM limit (`--memory 256m`)
- ⚙️ 0.5 CPU limit (`--cpus 0.5`)
- 🗑️ The container is destroyed right after the run (`--rm`)
- 📁 Every evaluation uses its own workspace, so concurrent students never interfere

### 🚪 Gating system

Each exercise must be passed to move forward. SQLite records every attempt per student and per
exercise, which enables the **rote learning** metrics: how many iterations a student needs to
master a concept.

### 🔍 RAG

Before answering, the tutor:

1. takes the error reported by Pytest
2. searches ChromaDB for semantically similar documentation
3. injects the retrieved context into the prompt
4. answers with the official documentation as the ground truth, not from memory

### 🛡️ Guardrails

1. **Prompt level** — the system prompt forbids writing code
2. **Input level** — user content is sanitised and wrapped in delimiters
3. **Response level** — the answer is scanned and replaced by an intervention notice if it
   contains code or a direct solution
4. **Fallback** — a hardcoded Socratic question when everything else fails

### 🎯 Adaptive difficulty

| Approved exercises | Level | Focus |
|--------------------|-------|-------|
| 0 | Beginner | Fundamental concepts |
| 1-2 | Intermediate | Combining methods |
| 3+ | Advanced | Edge cases, complex algorithms |

---

## ⚙️ Configuration

Every setting comes from the environment or the `.env` file. See [`.env.example`](.env.example)
for the full list.

| Variable | Default | Purpose |
|----------|---------|---------|
| `TUTOR_LOCALE` | `es` | Language the tutor speaks to the students (`es` / `en`) |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Local LLM server |
| `OLLAMA_MODEL` | `qwen2.5-coder:7b` | Model used by the tutor |
| `CHROMA_DIR` | `data/chroma` | Vector store location |
| `CHROMA_COLLECTION` | `material_clase` | Collection name |
| `SQLITE_PATH` | `data/tutor.db` | Gating and history database |
| `SANDBOX_DIR` | `data/sandbox` | Sandbox workspaces |
| `SANDBOX_IMAGE` | `sandbox-evaluador` | Docker image used for the evaluation |
| `SANDBOX_MEMORY` | `256m` | Memory limit of the sandbox |
| `SANDBOX_CPUS` | `0.5` | CPU limit of the sandbox |
| `MAX_UPLOAD_BYTES` | `100000` | Maximum size of an uploaded file |
| `RATE_LIMIT_REQUESTS` | `10` | Requests allowed per IP and per window |
| `RATE_LIMIT_WINDOW_SECONDS` | `60` | Length of the rate limit window |
| `DOCS_SOURCE_DIR` | `data/docs-source` | Default source of the ingestion |

---

## 🧑‍💻 Development

```bash
make install     # Install the runtime and the development dependencies
make dev         # Run the server with auto-reload
make test        # Run the test suite
make lint        # ruff check
make format      # ruff format
make typecheck   # mypy
make check       # lint + typecheck + test
```

Without `make`:

```bash
python -m pytest -q
python -m ruff check .
python -m ruff format .
python -m mypy app
```

The CI workflow (`.github/workflows/ci.yml`) runs the same checks on Python 3.12 and 3.13.

---

## 🔎 Verifying the installation

The unit tests stub the sandbox and the vector store, so they prove the logic but not the
installation. The smoke test exercises the **real** stack: the real Docker sandbox, the real
ChromaDB store and the real local model.

```bash
make build-sandbox          # docker build -t sandbox-evaluador .
make smoke                  # starts a server, drives the API, prints timings
```

It walks the whole student journey and fails loudly on any deviation:

| Step | What it proves |
|------|----------------|
| `health` | The API, the model and the vector store are reachable |
| `exercises/default` | The built-in exercise is served |
| `evaluate/correct` | A correct solution is reported as `success` |
| `evaluate/wrong` | A failing solution produces Socratic feedback — and *not* an intervention notice |
| `evaluate/broken-syntax` | A submission that does not compile is reported as a **failure**, never as a success |
| `generate` | The model returns a valid exercise and never leaks the hidden test suite |
| `evaluate/dynamic-starter` | A generated exercise is evaluated against its own hidden tests |
| `learning/stats` | The knowledge base holds chunks |

Add `--json report.json` to keep the machine-readable report, and `--skip-generate` to run
everything except the two model-backed steps.

> The first call after a period of inactivity pays the **model cold start** (around 25 s on a
> GPU); the following ones answer in a couple of seconds. Keep the model warm with
> `OLLAMA_KEEP_ALIVE=30m` on the Ollama side if the demo cannot afford that wait.

---

## 🔧 Troubleshooting

### `docker: command not found`

Docker Desktop is not installed or not in `PATH`. Start Docker Desktop and reopen the terminal.

### `Error connecting to Ollama`

```bash
ollama list
ollama pull qwen2.5-coder:7b
```

### `ModuleNotFoundError: No module named 'fastapi'`

The virtual environment is not active, or the dependencies are missing:

```bash
.venv\Scripts\activate
pip install -r requirements.txt
```

### ChromaDB raises `sqlite3.OperationalError`

Incompatible SQLite version on Windows:

```bash
pip install pysqlite3-binary
```

### The sandbox times out

The first run is slow because Docker has to start the image. Make sure Docker Desktop is fully
running and has enough resources allocated.

### The tutor generates poor exercises

- Use `qwen2.5-coder:7b` rather than the 1.5B variant
- Lower the temperature in `app/core/prompts.py` for a more deterministic output

### The tutor takes minutes to answer

Check what Ollama actually has loaded:

```bash
ollama ps
```

If another model is loaded and the runner is stuck in `Stopping...`, every request queues
behind it. Free the runner with:

```bash
ollama stop <model>
```

A response that takes ~25 s only on the first call is the normal **cold start** of the model;
the following ones are much faster.

### The search returns nothing

Ingest the documentation first:

```bash
python scripts/ingest_docs.py --source /path/to/python-docs-text
```

Check how many chunks the store holds:

```bash
curl http://localhost:8000/learning/stats
```

---

## 📚 Documentation

| Document | Description |
|----------|-------------|
| [Architecture](docs/architecture.md) | Layers, flows, configuration and the breaking changes |
| [Security](docs/security.md) | Attack surface, defences and known gaps |
| [Roadmap](docs/roadmap.md) | What is done, what comes next and the technical debt |
| [Sprint notes](docs/sprints/) | The development history of the prototype |

---

## 📄 License

MIT — see [LICENSE](LICENSE). Developed for educational purposes as part of a thesis on
AI-assisted programming tutoring.

---

<div align="center">
  <strong>Built for offline AI education</strong><br>
  <sub>100% local. 100% private. No data leaves your machine.</sub>
</div>
