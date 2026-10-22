# Sprint 1 — SQLite Integration and Gating

## Objective

Introduce a local relational database (SQLite) to implement the **Gating** system (progression by
passing exercises) and **Rote Learning** (attempt measurement), together with a REST API built
with FastAPI.

---

## Inventory of New Components

### `base_datos.py` — SQL abstraction

Module in charge of all the relational persistence logic. It provides safe, transactional
functions for the Gating system.

| Function | Purpose |
|----------|---------|
| `inicializar_bd()` | Creates the tables if they do not exist |
| `registrar_intento()` | Inserts or updates a student attempt |
| `obtener_intentos_alumno()` | Returns the current attempt count |
| `contar_aprobados_por_tema()` | Counts approved exercises (adaptive difficulty) |
| `guardar_tema_alumno()` | Persists the current topic of the student |
| `obtener_tema_alumno()` | Retrieves the last stored topic |
| `registrar_historial()` | Inserts a detailed record into the history |

### `main.py` — Web API entry point

FastAPI server exposing the REST endpoints and managing the application lifecycle.

```python
app = FastAPI(title="Motor de Tutoría IA Offline", version="1.1")
inicializar_bd()  # Runs on startup
```

### `gating_estudiantes.db` — SQLite database

Physical file holding the persistent student state, 100% local and offline.

---

## Data Model and Gating Strategy

### Table `progreso`

Main record of the Gating system:

```sql
CREATE TABLE IF NOT EXISTS progreso (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    alumno_id TEXT NOT NULL,
    ejercicio_id TEXT NOT NULL,
    estado TEXT NOT NULL,
    intentos INTEGER DEFAULT 1
);
```

### Table `historial_ejercicios`

Detailed evaluation history (analytics and statistics):

```sql
CREATE TABLE IF NOT EXISTS historial_ejercicios (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    alumno_id TEXT NOT NULL,
    tema TEXT,
    ejercicio_id TEXT NOT NULL,
    estado TEXT NOT NULL,
    intento_numero INTEGER DEFAULT 1,
    timestamp TEXT NOT NULL
);
```

### Table `temas_alumnos`

Persistence of the current topic of the student (dynamic exercises):

```sql
CREATE TABLE IF NOT EXISTS temas_alumnos (
    alumno_id TEXT PRIMARY KEY,
    tema TEXT NOT NULL,
    timestamp TEXT NOT NULL
);
```

### Dynamic update logic

The system maintains progress with an upsert strategy:

1. If the pair `(alumno_id, ejercicio_id)` **does not exist** → it is inserted with `intentos = 1`
2. If the pair **already exists** → `intentos = intentos + 1` is applied atomically and the
   `estado` is updated

---

## Technical API Specification

### `POST /evaluar`

Main endpoint for processing student code submissions.

**Content type:** `multipart/form-data`

| Parameter | Type | Description |
|-----------|------|-------------|
| `alumno_id` | `string` | Unique student identifier |
| `ejercicio_id` | `string` | Code of the exercise being evaluated |
| `file` | `file` | Student `.py` file |

**Responses:**

#### ✅ Total success (correct code)
```json
{
  "status": "exito",
  "mensaje": "¡Felicidades! Todos los tests pasaron. Has desbloqueado el siguiente ejercicio."
}
```

#### ❌ Logical or syntactic failure (RAG + LLM activated)
```json
{
  "status": "fallo",
  "error_tecnico": "AssertionError: Se esperaba [1, 2, 3] pero se obtuvo ['a', 'b', 'c']...",
  "feedback_tutor": "En tu código, el error ocurre porque... ¿Puedes modificar...?"
}
```

#### 🔴 System error (sandbox exception)
```json
{
  "status": "error_servidor",
  "mensaje": "Error interno: El contenedor no generó el reporte.json"
}
```

### `GET /`

Serves the web interface (`index.html`) through `FileResponse`.

---

## Learning Endpoints (ChromaDB)

### `GET /aprendizaje/categorias`
Returns the categories available in the documentation.

### `GET /aprendizaje/temas?categoria=...`
Returns the topics inside a category.

### `GET /aprendizaje/contenido?tema=...&categoria=...`
Returns the content chunks of a specific topic.

### `GET /aprendizaje/buscar?q=...`
RAG semantic search across the whole documentation.

### `GET /aprendizaje/estadisticas`
General statistics about the knowledge base.

---

## Scientific Findings

### Environment conflict: live reload

Uvicorn's `--reload` flag detects changes in `ejercicio_alumno.py` and restarts the server,
interrupting the Docker run.

**Solution:** run in static mode (`uvicorn main:app`) or configure exclusions in the watcher.

### Reasoning limits of SLMs

Qwen 2.5 Coder 3B showed logical hallucinations (confusing `.keys()` with `.values()`). The
following are required:
- **Chain-of-Thought (CoT)**
- **Few-Shot Prompting**
- Injection of the student's code into the prompt

---

## Notes after the 2026 restructure

The persistence layer now lives in `app/services/database.py` and the API in `app/api/routes/`.
The table and column names were kept on purpose so an existing database can be migrated by
renaming the file. The response contract changed: `status` is now `success` / `failure` / `error`
and the endpoints live under `/learning`.
