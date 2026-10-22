# Sprint 3 — Dynamic Generation and Resilient Socratic Evaluation

## Sprint Objectives

- Implement dynamic generation of programming exercises through AI
- Establish a safe flow to evaluate dynamically generated code without exposing the tests to the
  client
- Develop an error interception system (*fallback*) for when the test environment (Pytest) breaks
- Refine the *prompt engineering* of the AI tutor to avoid **solution leakage**

---

## Architecture Decision: The Stateful Model

### Option A: Stateless ❌
The test travels to the frontend and comes back during the evaluation.
**Rejected** because of the academic vulnerability: a student could inspect or modify the test from
the browser.

### Option B: Stateful ✅
The backend stores the test temporarily and only sends the exercise instructions to the student.

**Architectural decision:** Option B. This architecture strengthens security through the concept of
**Gating**, guaranteeing that the evaluating code is never sent to the student's browser.

Each dynamic test is temporarily stored on the server with the format:
```text
test_dynamic_{student_id}.py
```

---

## Technical Implementation

### `POST /generate` endpoint

**Flow:**
1. Receives `topic` and `student_id` from the form
2. Queries the **adaptive difficulty engine** in SQLite
3. Calls `orchestrator.generate_exercise(topic, difficulty)`
4. Stores the `test_code` server-side (secret in the backend)
5. Persists the student topic in `temas_alumnos`
6. Returns only `instructions`, `expected_example` and `starter_code` to the frontend

### Smart routing in `POST /evaluate`

When `exercise_id == "dynamic"`:
1. Looks up the stored test for that student
2. Writes it into the isolated working directory as `test_exercise.py`
3. Reuses the Docker container of Sprint 1

### Dynamic error interception (*fallback*)

Dynamic exercises do not exist in ChromaDB (they are generated on the fly). To avoid a failing
RAG lookup, the following was implemented:

```python
generate_dynamic_feedback(raw_error, student_code)
```

This function:
1. Captures the raw Pytest error
2. Sends it directly to Ollama **without depending on ChromaDB**
3. Generates contextualised Socratic feedback

---

## Generator Implementation

### `generate_exercise(topic, difficulty)`

Asks the AI to generate a complete exercise from scratch.

**Structured system prompt:**
- Defines the difficulty level (beginner/intermediate/advanced)
- Requires a response in **strict JSON format** with four keys:
  - `instructions` — the problem statement
  - `expected_example` — an explicit test case
  - `starter_code` — initial code with `pass`
  - `test_code` — the Pytest suite (NEVER sent to the frontend)

**Adaptive difficulty engine:**
- **0 approved** → Beginner (fundamental concepts)
- **1-2 approved** → Intermediate (combination of methods)
- **3+ approved** → Advanced (edge cases, complex algorithms)

**Defensive patches:**
1. If the AI omits `expected_example`, a default message is assigned
2. If the `test_code` lacks `from exercise_student import`, it is injected automatically

### `generate_dynamic_feedback(raw_error, student_code)`

Socratic prompt specialised for dynamic exercises:
- Does not use ChromaDB (there is no documentation for the specific topic)
- Receives the student code plus the Pytest error
- Classifies the error: `TypeError` (parameter names) vs `AssertionError` (values)
- Explicitly forbids JSON answers
- Forbids mentioning the correct solution or writing corrected code

---

## Evolution of the Prompt Engineering (AI Tutor)

| Iteration | Problem | Solution |
|-----------|---------|----------|
| **V1: Generic zero-shot** | The model wandered off with unnecessary theory | Explicit restriction to the "Data Types" topic |
| **V2: Over-restriction** | It attributed type errors to logical ones | Conditional analysis to classify the error |
| **V3: Blind correction** | It only saw the Pytest `assert`, not the code | Injection of the student code into the prompt |
| **V4: Solution leakage** | The AI revealed how to solve it | Guardrails for reflective questions, not solutions |

### Consolidated final prompt

```python
system_prompt = """
You are a strictly Socratic programming tutor.

Your goal is to guide the student until they discover their own mistake.

RULE 1 (CRITICAL):
UNDER NO CIRCUMSTANCE must you mention the correct solution,
nor write methods or functions the student has not used.

RULE 2:
Compare the 'Student code' with the 'Pytest error'.

RULE 3:
Ask ONE single reflective question.

- If the student used the wrong method,
  ask them WHAT exactly the method they wrote returns.

- If the error is mathematical,
  ask them which values their formula is taking.

KEEP THE QUESTION SHORT,
FRIENDLY AND FOCUSED ON THE STUDENT'S CODE,
NEVER ON THE SOLUTION.
"""
```

### Hard safety guardrail

```python
if "```" in ai_response or "def " in ai_response:
    return "SYSTEM INTERVENTION: The tutor tried to give you the direct answer..."
```

---

## Results and Conclusions

### ✅ Complete end-to-end cycle

```text
Topic request
        ↓
Exercise generation
        ↓
Student solves it
        ↓
Automatic evaluation
        ↓
Socratic feedback
```

### ✅ SLM stability

A model of ~3B-7B parameters can offer quality pedagogical feedback when it has:
- The student code
- The error produced by Pytest
- Explicit restrictions (*guardrails*)

### ✅ Robustness against failures

The system tolerates:
- Syntax errors
- Missing imports
- Exceptions during execution

All of them are caught, processed and presented as understandable messages in the interface.

---

## Files Changed

| File | Change |
|------|--------|
| `orquestador.py` | New `generar_ejercicio_dinamico()` and `generar_feedback_dinamico()` functions |
| `main.py` | New `POST /generar` endpoint, dynamic routing in `/evaluate` |
| `index.html` | Exercise generation section with form and rendering |

---

## Notes after the 2026 restructure

The generator now lives in `app/services/orchestrator.py` (`generate_exercise` and
`generate_dynamic_feedback`), the endpoint in `app/api/routes/evaluation.py`, and the hidden test
suites are stored per student under `data/sandbox/tests/`. The static exercise used by the
platform ships in `resources/exercises/default/`.
