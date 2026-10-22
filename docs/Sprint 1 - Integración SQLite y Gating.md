## Objetivo
Incorporar una base de datos relacional local (SQLite) para implementar el sistema de **Gating** (progresión por superación de ejercicios) y **Rote Learning** (medición de intentos), junto con una API REST en FastAPI.

---

## Inventario de Nuevos Componentes

### `base_datos.py` — Abstracción SQL

Módulo encargado de toda la lógica de persistencia relacional. Proporciona funciones transaccionales seguras para el sistema de Gating.

| Función | Propósito |
|---------|-----------|
| `inicializar_bd()` | Crea las tablas si no existen |
| `registrar_intento()` | Inserta o actualiza intento de un alumno |
| `obtener_intentos_alumno()` | Consulta número de intentos actuales |
| `contar_aprobados_por_tema()` | Cuenta ejercicios aprobados (dificultad adaptativa) |
| `guardar_tema_alumno()` | Persiste el tema actual del alumno |
| `obtener_tema_alumno()` | Recupera el último tema guardado |
| `registrar_historial()` | Inserta registro detallado en historial |

### `main.py` — Punto de entrada de la API Web

Servidor FastAPI que expone los endpoints REST y gestiona el ciclo de vida de la aplicación.

```python
# App config
app = FastAPI(title="Motor de Tutoría IA Offline", version="1.1")
inicializar_bd()  # Se ejecuta al arrancar
```

### `gating_estudiantes.db` — Base de datos SQLite

Archivo físico que almacena el estado persistente de los estudiantes 100% local y offline.

---

## Modelo de Datos y Estrategia de Gating

### Tabla `progreso`

Registro principal del sistema de Gating:

```sql
CREATE TABLE IF NOT EXISTS progreso (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    alumno_id TEXT NOT NULL,
    ejercicio_id TEXT NOT NULL,
    estado TEXT NOT NULL,
    intentos INTEGER DEFAULT 1
);
```

### Tabla `historial_ejercicios`

Historial detallado de evaluaciones (analíticas y estadísticas):

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

### Tabla `temas_alumnos`

Persistencia del tema actual del alumno (ejercicios dinámicos):

```sql
CREATE TABLE IF NOT EXISTS temas_alumnos (
    alumno_id TEXT PRIMARY KEY,
    tema TEXT NOT NULL,
    timestamp TEXT NOT NULL
);
```

### Lógica de Actualización Dinámica

El sistema mantiene el progreso mediante estrategia de upsert:

1. Si el par `(alumno_id, ejercicio_id)` **no existe** → se inserta con `intentos = 1`
2. Si el par **ya existe** → se incrementa `intentos = intentos + 1` atómicamente y se actualiza el `estado`

---

## Especificación Técnica de la API

### `POST /evaluar`

Endpoint principal para el procesamiento de entregas de código de los estudiantes.

**Tipo de contenido:** `multipart/form-data`

| Parámetro | Tipo | Descripción |
|-----------|------|-------------|
| `alumno_id` | `string` | Identificador único del estudiante |
| `ejercicio_id` | `string` | Código del ejercicio evaluado |
| `file` | `file` | Archivo `.py` del estudiante |

**Respuestas:**

#### ✅ Éxito total (código correcto)
```json
{
  "status": "exito",
  "mensaje": "¡Felicidades! Todos los tests pasaron. Has desbloqueado el siguiente ejercicio."
}
```

#### ❌ Fallo lógico o sintáctico (activación de RAG + LLM)
```json
{
  "status": "fallo",
  "error_tecnico": "AssertionError: Se esperaba [1, 2, 3] pero se obtuvo ['a', 'b', 'c']...",
  "feedback_tutor": "En tu código, el error ocurre porque... ¿Puedes modificar...?"
}
```

#### 🔴 Error del sistema (excepción en Sandbox)
```json
{
  "status": "error_servidor",
  "mensaje": "Error interno: El contenedor no generó el reporte.json"
}
```

### `GET /`

Sirve la interfaz web (`index.html`) usando `FileResponse`.

---

## Endpoints de Aprendizaje (ChromaDB)

### `GET /aprendizaje/categorias`
Devuelve categorías disponibles en la documentación.

### `GET /aprendizaje/temas?categoria=...`
Devuelve temas dentro de una categoría.

### `GET /aprendizaje/contenido?tema=...&categoria=...`
Devuelve chunks de contenido de un tema específico.

### `GET /aprendizaje/buscar?q=...`
Búsqueda semántica RAG sobre toda la documentación.

### `GET /aprendizaje/estadisticas`
Estadísticas generales de la base de conocimiento.

---

## Hallazgos Científicos

### Conflicto de Entorno: Live Reload

El parámetro `--reload` de Uvicorn detecta cambios en `ejercicio_alumno.py` y reinicia el servidor, interrumpiendo Docker.

**Solución:** Ejecutar en modo estático `uvicorn main:app` o configurar exclusiones en el watcher.

### Límites de Razonamiento en SLM

Qwen 2.5 Coder 3B mostró alucinaciones lógicas (confundir `.keys()` con `.values()`). Se requiere:
- **Chain-of-Thought (CoT)**
- **Few-Shot Prompting**
- Inyección del código del alumno en el prompt

