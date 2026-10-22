# Sprint 2 — Minimalist Frontend Layer

## Objective

Develop a graphical user interface based on standard web technologies and an agile design,
removing the dependency on the console or test tools (Swagger) to simulate the final student
environment.

---

## Executive Summary

The presentation layer was successfully integrated directly into the **FastAPI** server through
`FileResponse`. Following the methodological guidelines of the research, the interface was
designed **without chat boxes** in order to reduce the risk of *prompt injection* and to
minimise cognitive distractions.

The student interacts exclusively through structured forms to submit exercises. All the
evaluation logic remains encapsulated in the backend.

---

## End-to-End Data Flow

```text
[Student (index.html)]
        │
        │ FormData (file + IDs)
        ▼
[REST server (main.py)]
        │
        ├────────► [SQLite (base_datos.py)]
        │            (Gating and Rote Learning)
        │
        ▼
[Core orchestrator]
(Docker + RAG + Ollama)
        │
        │ JSON with the AI feedback
        ▼
[REST server]
        │
        ▼
[Frontend]
(shows the result to the student)
```

---

## Frontend Implementation (`index.html`)

### Tab architecture

The frontend is organised around two main tabs:

| Tab | Function |
|-----|----------|
| 📝 **Exercises** | AI exercise generation + Socratic evaluation |
| 📖 **Learning** | Technical documentation explorer with semantic search |

### Section 1: Exercise generator (AI)

Form to request personalised exercises:

- **Fields:** `alumno_id`, exercise `tema`
- **Flow:** POST `/generar` → the AI generates instructions + starter code + secret tests
- **Rendering:** instructions, expected example (terminal style) and starter code

### Section 2: Socratic evaluator

Code submission form:

- **Fields:** `alumno_id`, `ejercicio_id` (use `dynamic` for generated exercises), `.py` file
- **Concurrency control:** the button is disabled while the evaluation runs
- **Visual states:**
  - ⏳ **Loading:** "pulse" animation while it evaluates
  - ✅ **Success:** green badge + approval message
  - 🧠 **Failure:** amber badge + Socratic feedback from the AI tutor
  - ⚠️ **Error:** red badge + technical message

### Section 3: Learning material

Documentation explorer with:

- **Semantic search:** RAG query over ChromaDB
- **Hierarchical navigation:** Categories → Topics → Content (with breadcrumb)
- **Markdown rendering:** simple parser (no external dependencies) to display the documentation
- **Responsive design:** adaptive grid for categories and topics

### Design characteristics

- **No conversational chat:** reduces the risk of *prompt injection*
- **Structured identification:** mandatory `alumno_id` and `ejercicio_id` fields
- **Visual states:** three states through dynamic DOM manipulation
- **Inline Markdown:** own parser, no external dependencies

---

## Backend Modifications (`main.py`)

### Root endpoint with FileResponse

```python
from fastapi.responses import FileResponse


@app.get("/")
def read_root():
    """Serves the main web interface."""
    return FileResponse("index.html")
```

### Routing logic in `/evaluar`

The endpoint automatically distinguishes between exercises:

- **Static** → uses the existing `test_ejercicio.py`
- **Dynamic** (`ejercicio_id == "dynamic"`) → copies `test_dynamic_{alumno_id}.py` →
  `test_exercise.py`

### Structured response cases

| Case | Condition | Response |
|------|-----------|----------|
| 🟢 A | `status == "success"` | Direct success, records the history |
| 🔴 B | `ejercicio_id == "dynamic"` and failed | Socratic feedback without RAG |
| 🟡 C | Critical error (syntax) | Technical error message |
| 🔵 D | Static exercise and logical failure | RAG + feedback from the orchestrator |

---

## Prototype Validation

### Anti-distraction operational constraint

The absence of a conversational chat forces the student to focus on:
- Their own code
- Feedback messages
- The debugging process

### Evidence of SLM limitations

**Strengths of Qwen 2.5 Coder 7B:**
- Follows the prompt instructions
- Does not hand over complete solutions
- Keeps the answers short
- Follows the Socratic format

**Limitations:**
- Logical hallucinations in complex scenarios
- Confusion between `.keys()` and `.values()`

---

## Methodological Implications

1. A minimalist interface reduces distractions and the *prompt injection* attack surface
2. Pedagogical quality depends mostly on *prompt* engineering, not only on the UI
3. The next sprint focuses on improving reasoning through **Chain-of-Thought** and
   **Few-Shot Prompting**

---

## Notes after the 2026 restructure

The frontend now lives in `frontend/` and is split into `index.html`, `styles.css` and `app.js`.
The inline `onclick` handlers were replaced by `data-*` attributes and `addEventListener`, and the
HTML is escaped properly before being inserted into the DOM, which closes the XSS hole of the
prototype.
