# 📚 Documentation

Reference documentation for the Offline AI Tutoring Engine.

| Document | Description |
|----------|-------------|
| [Architecture](architecture.md) | Layers, module responsibilities, evaluation flow, configuration and the breaking changes of the 2026 restructure |
| [Security](security.md) | Attack surface, implemented defences, testing the defences and the known gaps |
| [Roadmap](roadmap.md) | Completed work, next steps and technical debt |
| [Sprint notes](sprints/) | The development history of the prototype, from the proof of concept to the documentation API |

## Quick start

```bash
pip install -r requirements.txt
docker build -t sandbox-evaluador .
ollama pull qwen2.5-coder:7b
uvicorn app.main:app --reload --port 8000
```

## Sprint index

| Sprint | Focus | Document |
|--------|-------|----------|
| **Sprint 0** | Proof of concept of the core engine (Docker + ChromaDB + Ollama) | [sprint-0](sprints/sprint-0.md) |
| **Sprint 1** | SQLite integration, gating and the REST API | [sprint-1](sprints/sprint-1.md) |
| **Sprint 2** | Minimalist frontend layer | [sprint-2](sprints/sprint-2.md) |
| **Sprint 3** | Dynamic generation and resilient Socratic evaluation | [sprint-3](sprints/sprint-3.md) |
| **Sprint 4** | Mass documentation ingestion and the learning API | [sprint-4](sprints/sprint-4.md) |

## Architectural overview

```text
┌──────────────────────────────────────────────────────┐
│                    Frontend (frontend/)              │
│  [Exercise form] [Code upload] [Docs explorer]       │
└──────────────────────┬───────────────────────────────┘
                       │ HTTP (FormData / JSON)
                       ▼
┌──────────────────────────────────────────────────────┐
│              API layer (app/api/)                     │
│  /evaluate  /generate  /learning/*  /health  /       │
└───────────┬──────────────────────┬───────────────────┘
            │                      │
            ▼                      ▼
┌───────────────────────┐  ┌──────────────────────────┐
│   Services (app/services) │  │     Core (app/core)      │
│  orchestrator            │  │  config · logging       │
│  database                │  │  prompts · security     │
│  learning · exercises    │  │  sandbox                │
└───────────────────────┘  └──────────────────────────┘
            │
            ▼
┌──────────────────────────────────────────────────────┐
│              Local persistence                        │
│  SQLite (gating)   ChromaDB (RAG)   Docker sandbox   │
└──────────────────────────────────────────────────────┘
```

## Tech stack

| Component | Technology | Purpose |
|-----------|------------|---------|
| **Backend** | Python 3.12+ and FastAPI | REST API |
| **Frontend** | Plain HTML, CSS and JavaScript | User interface, no build step |
| **Sandbox** | Docker (Alpine + pytest) | Safe code execution |
| **Database** | SQLite (via `sqlite3`) | Gating and rote learning |
| **Vector DB** | ChromaDB (ONNX MiniLM-L6-V2) | RAG semantic search |
| **Local AI** | Qwen 2.5 Coder 7B (through Ollama) | Socratic tutor and generation |
| **Documentation** | Python documentation (500+ `.txt` files) | Knowledge base |

## Concepts of the thesis

**Gating** — progression system where each exercise must be passed to unlock the next one.
SQLite records the attempts and the states.

**Rote learning** — objective measurement of how many iterations a student needs to master a
concept, based on the retry history.

**Isolated evaluation** — execution of untrusted code in a Docker container without network,
with limited resources and automatic destruction after the evaluation.

**Local RAG** — context enriched through semantic search in a local vector knowledge base,
100% offline.

**Guardrails** — programmatic restrictions that prevent the AI from revealing direct solutions,
keeping the approach strictly Socratic.
