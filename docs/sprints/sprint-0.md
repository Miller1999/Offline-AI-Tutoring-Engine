# Sprint 0 — Proof of Concept of the Core Engine

## Objective

Empirically validate the technical viability of the core architecture proposed in the thesis
(Isolated Evaluation + Local RAG + Quantised AI in a single turn), running 100% offline on
resource-constrained hardware.

---

## Summary

A Python orchestrator (`orquestador.py`) was successfully built to automate the full student
evaluation cycle. The system is able to spin up an ephemeral, network-less Docker container to
run untrusted code, extract the structured error produced by Pytest, enrich the context through a
local vector database (ChromaDB) and interact with a 7B parameter language model
(Qwen 2.5 Coder) through Ollama to produce safe Socratic feedback.

---

## Components Built

### `orquestador.py` — System core

The main file orchestrating the whole evaluation flow:

| Function | Purpose |
|----------|---------|
| `evaluar_codigo_en_sandbox()` | Launches the Docker container, runs Pytest, reads `reporte.json` and parses the results |
| `obtener_pista_socratica()` | Queries ChromaDB (RAG), builds a contextual prompt and calls Ollama for feedback |
| `generar_ejercicio_dinamico()` | Asks the AI to generate a complete exercise with tests (Sprint 3) |
| `generar_feedback_dinamico()` | Fallback for dynamic exercises without RAG (Sprint 3) |

### `Dockerfile` — Evaluation sandbox

```dockerfile
FROM python:3.14-alpine
WORKDIR /app
RUN pip install --no-cache-dir pytest pytest-json-report
CMD ["pytest", "test_ejercicio.py", "--json-report", "--json-report-file=reporte.json"]
```

Characteristics:
- Extremely lightweight Alpine image
- No network (`--network none`)
- Memory limit (`--memory 256m`)
- CPU limit (`--cpus 0.5`)
- Ephemeral container (`--rm` flag)

### `cargar_rag.py` — Initial RAG prototype

First version of the document loader for ChromaDB. It reads `apuntes.md` and vectorises it into
the `material_clase` collection. It was later replaced by `ingestar_conocimiento.py`.

### `bd_vectorial/` — Vector database

Persistent ChromaDB directory holding the documentation embeddings.

---

## Operation Flow

```text
[Student] → uploads a .py file
       ↓
[main.py] → receives the file via POST /evaluar
       ↓
[orquestador.evaluar_codigo_en_sandbox()]
       ↓
[Docker] → pytest test_ejercicio.py → reporte.json
       ↓
[Result parsing] → did the tests pass?
       ↓                     ↓
   ✅ Success          ❌ Failure
                         ↓
             [ChromaDB] → semantic search of the error
                         ↓
             [Ollama + Qwen 2.5 Coder] → contextual prompt
                         ↓
             [Guardrails] → direct solution filter
                         ↓
             [Socratic answer to the student]
```

---

## Technical Milestones and Hypothesis Validation

### ✅ Network-less Docker sandbox
- Ephemeral container destroyed automatically
- No internet access (security)
- Resource limits (memory and CPU)

### ✅ Working RAG pipeline
- ChromaDB queries the vector knowledge base
- Embeddings generated locally (ONNX MiniLM-L6-V2)
- 3 fragments retrieved per query for a rich context

### ✅ Local SLM integration
- Qwen 2.5 Coder 7B through Ollama
- 100% offline, no dependency on external APIs
- Controlled temperature (0.3) for consistency

### ✅ Anti-solution guardrail
- Intervention system when the AI tries to write code (```` ``` ```` or `def `)
- Blocks solution leakage

---

## Lessons Learned

### Limits of small SLMs
Models with 3B-7B parameters can hallucinate logic (for example confusing `.keys()` with
`.values()`). The mitigation requires:
- **Chain-of-Thought (CoT)**
- **Few-Shot Prompting**
- Injection of the student's code into the prompt

### Conflict with live reload
Uvicorn with `--reload` detects the `ejercicio_alumno.py` file and restarts the server. The
solution is to run in static mode: `uvicorn main:app`.

---

## Notes after the 2026 restructure

This sprint describes the original prototype. The code has since been reorganised into the
`app/` package (see [Architecture](../architecture.md)); the concepts validated here — isolated
evaluation, local RAG, local SLM and guardrails — are unchanged.
