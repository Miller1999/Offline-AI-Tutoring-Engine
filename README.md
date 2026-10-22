# Offline AI Tutor Engine

An offline-first Socratic programming tutor that runs entirely on local infrastructure. The engine combines a local LLM (Ollama), a vector knowledge base (ChromaDB) and an isolated Docker sandbox to guide students through Python exercises without leaking answers or giving direct solutions.

## Features

- **Socratic tutoring** – The tutor never gives the solution. It asks questions grounded in the official Python documentation stored in the local knowledge base.
- **Isolated evaluation** – Student code runs inside a `--network none` Docker sandbox with strict resource limits. Results are parsed from `pytest-json-report`.
- **Adaptive exercises** – The difficulty level of newly generated exercises scales with the number of approved exercises per student.
- **Offline by design** – Everything runs locally: the model, the embeddings, the vector store and the database.
- **Security hardened** – Prompt injection detection, output validation to block solution leaks, per-IP rate limiting and strict input validation.
- **Reproducible verification** – A deterministic smoke test exercises the full student journey and checks every critical contract.

## Quick start

### Prerequisites

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) with the Linux engine running
- [Ollama](https://ollama.com/) with a coding model available (e.g. `ollama pull qwen2.5-coder:7b`)
- [Python 3.12](https://www.python.org/)

### Installation

```bash
git clone https://github.com/Miller1999/Offline-AI-Tutoring-Engine.git
cd Offline-AI-Tutoring-Engine
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # Linux/macOS
pip install -r requirements.txt
cp .env.example .env
```

### Build the sandbox and run the API

```bash
make build-sandbox
make run-api
```

Open <http://localhost:8000> in your browser.

### Populate the knowledge base

The tutor grounds its answers in the official Python documentation. Download the text version of the Python docs and ingest it:

```bash
# Option 1: use the helper script (downloads from docs.python.org)
# Option 2: point to an existing directory
python scripts/ingest_docs.py --source data/docs-source --verify
```

`resources/professor_notes.md` is kept as a lightweight fallback when the vector store is empty.

## Configuration

All settings are loaded from `.env` (see `.env.example`). The most relevant ones:

| Variable | Default | Description |
|----------|---------|-------------|
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Local LLM server |
| `OLLAMA_MODEL` | `qwen2.5-coder:7b` | Model used by the tutor |
| `OLLAMA_CONTEXT_LENGTH` | `8192` | Context window requested on every generation |
| `OLLAMA_KEEP_ALIVE` | `30m` | How long the model stays loaded after a request |
| `TUTOR_LOCALE` | `es` | Language of the tutor (`es` or `en`). The language of the code is never affected. |
| `SANDBOX_IMAGE` | `sandbox-evaluador` | Docker image used to evaluate submissions |
| `SANDBOX_MEMORY` | `256m` | Memory limit for each sandbox run |
| `SANDBOX_CPUS` | `0.5` | CPU limit for each sandbox run |
| `SANDBOX_TIMEOUT_SECONDS` | `60` | Maximum time allowed for a test run |
| `DOCS_SOURCE_DIR` | `data/docs-source` | Source directory used by `scripts/ingest_docs.py` |

## Verifying the installation

The smoke test drives the API through the exact journey a student would take. It requires Docker (the sandbox image built) and a running Ollama instance with the configured model.

```bash
# Start the API and run the full suite in one go
python scripts/smoke_test.py --start-server --json report.json

# Or run against an already started server
python scripts/smoke_test.py --base-url http://localhost:8000
```

| Step | What it proves |
|------|----------------|
| `health` | The API, the model and the vector store are reachable |
| `exercises/default` | The built-in exercise is served |
| `evaluate/correct` | A correct solution is reported as `success` |
| `model/warm-up` | The local model is loaded and answers |
| `evaluate/wrong` | A failing solution produces Socratic feedback — and *not* an intervention notice |
| `evaluate/broken-syntax` | A submission that does not compile is reported as a **failure**, never as a success |
| `generate` | The model returns a valid exercise and never leaks the hidden test suite |
| `evaluate/dynamic-starter` | A generated exercise is evaluated against its own hidden tests |
| `learning/stats` | The knowledge base holds chunks |

Add `--json report.json` to keep the machine-readable report, and `--skip-generate` to run everything except the two model-backed steps.

> The harness waits for the model to report itself as ready, so the measured times are the ones of a warm model. The very first answer of a session also pays the **cold start** of the model (around 25 s on a GPU); the API loads it in the background when it starts.

## Troubleshooting

### Docker is not available
The sandbox uses `docker run`. Make sure Docker Desktop is running and your user has permission to run Docker. The API reports infrastructure errors through the `/evaluate` response when Docker is unreachable.

### The tutor takes minutes to answer

Three things control the latency of a local model, and the API pins the two that are usually left to the server configuration:

| Setting | Effect |
|---------|--------|
| `OLLAMA_CONTEXT_LENGTH` | The KV cache of a wide context does not fit in a modest GPU. A 32k context on a 7B model needs ~17GB of RAM instead of ~5GB, and the model spills into system RAM — which turns every answer into a two-minute one. |
| `OLLAMA_KEEP_ALIVE` | The Ollama default unloads the model after five minutes. The tutor asks for it to stay loaded, so a session does not pay a cold start in the middle of a conversation. |
| Warm-up at startup | The API loads the model in a background thread when it starts. `GET /health` reports `model_ready` so a client can wait instead of timing out. |

Check what Ollama actually has loaded:

```bash
ollama ps
```

If another model is loaded and the runner is stuck in `Stopping...`, every request queues behind it. Free the runner with:

```bash
ollama stop <model>
```

A response that takes ~25 s only on the first call is the normal **cold start** of the model; the following ones are much faster.

### The search returns nothing
Run `python scripts/ingest_docs.py --source <path-to-python-docs-text> --verify` to rebuild the knowledge base. If the directory is empty the tutor falls back to `resources/professor_notes.md` (which is intentionally small).

### A generated exercise fails to import the student module
The engine normalises the test suite of every generated exercise before storing it. If an old `data/sandbox/tests/*.py` file was written by a previous version, regenerate the exercise or delete the cached test for that student.

## Project structure

```text
app/                FastAPI application (routes, schemas, core logic)
frontend/           Static web UI
scripts/            Operational scripts (ingestion, seeding, smoke test)
tests/              Test suite
resources/          Versioned teaching resources and built-in exercises
data/               Runtime state (ChromaDB, SQLite, sandbox workdirs) — gitignored
docker/             Additional Dockerfiles
```

## Testing

```bash
pytest
```

The tests cover the sandbox parser, the defensive patches for generated exercises, the security guards, the database layer and the API contracts.

## Benchmarking

Compare local models against a versioned corpus using the same production paths (prompts, guards, sandbox):

```bash
# Validate the corpus against the real sandbox
python scripts/benchmark.py --tasks oracle --models none

# Compare models on exercise generation and Socratic feedback
python scripts/benchmark.py --models qwen2.5-coder:7b,qwen3:8b,deepseek-r1:14b
```

## License

This project is provided for educational and research purposes.
