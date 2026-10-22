# Roadmap

## Done

### Core engine

- [x] Ephemeral Docker sandbox without network, with memory and CPU limits
- [x] Pytest execution with a structured JSON report
- [x] Local LLM (Qwen 2.5 Coder through Ollama), 100% offline
- [x] RAG over ChromaDB with local ONNX embeddings
- [x] Anti-solution guardrail on the model output

### Persistence

- [x] SQLite: gating, attempt counter, evaluation history, current topic
- [x] Indexes for the per-student lookups
- [x] Upsert strategy for the attempt records

### API

- [x] REST endpoints for evaluation, generation and the learning explorer
- [x] Pydantic schemas for every response
- [x] Per-IP rate limiting
- [x] Upload size limit

### Frontend

- [x] Two-tab interface (exercises, learning)
- [x] Documentation explorer with categories, topics and semantic search
- [x] XSS-free rendering, no inline event handlers

### Ingestion

- [x] Mass ingestion of the Python documentation with semantic chunking
- [x] Injection payload scanner for the ingested documents
- [x] Verification pass with sample queries

### Engineering

- [x] Package layout (`app/`), configuration through the environment
- [x] Structured logging instead of `print()`
- [x] Test suite (security, database, learning, sandbox, orchestrator, API)
- [x] Lint and format configuration (ruff), type checking (mypy)
- [x] CI workflow, Makefile, `.gitignore`, `.editorconfig`, `.gitattributes`
- [x] English documentation
- [x] End-to-end smoke test driving the real sandbox, vector store and model

## Next

### Short term

- [ ] Integrate the tutor prompts with a real evaluation rubric
- [ ] Move the dynamic test suites from the filesystem to the database
- [ ] Add a streaming endpoint for the Socratic feedback
- [ ] Export the student history as CSV for the lecturer

### Medium term

- [ ] Authentication and per-student sessions
- [ ] Instructor view: dashboard with the progress of every student
- [ ] Exercise catalogue with difficulty tags
- [ ] Multilingual tutor (`TUTOR_LOCALE=en` is already supported, the prompts need reviewing)
- [ ] Structured output for the model (JSON schema) instead of regex parsing

### Long term

- [ ] Compare several local models (Qwen, Codellama, DeepSeek Coder) on the same exercises
- [ ] Measure the learning effect: attempts before/after the intervention
- [ ] Federated deployment across a campus without sending data outside

## Known technical debt

| Item | Where | Impact |
|------|-------|--------|
| Table and column names are still Spanish | `app/services/database.py` | Cosmetic; kept for migration compatibility |
| The category counter scans every metadata row | `app/services/learning.py` | Fine for ~26k chunks, memoised for 5 minutes |
| The rate limiter is in-process | `app/api/dependencies.py` | Not shared between workers |
| The guardrails are blocklists | `app/core/security.py` | Bypassable with unusual phrasing |
| No authentication | — | Anonymous clients, self-declared student id |
