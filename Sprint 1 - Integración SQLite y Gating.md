# Inventario de Nuevos Componentes

- **`base_datos.py`**
  - Módulo encargado de la abstracción SQL.
  - Inicializa el esquema de datos relacional.
  - Expone funciones seguras, como `registrar_intento`, para transaccionar con el motor de base de datos.

- **`main.py`**
  - Punto de entrada de la aplicación web.
  - Configura la API.
  - Inicializa el ciclo de vida de la base de datos relacional al arrancar.
  - Gestiona la recepción asíncrona de archivos binarios (*File Uploads*).

- **`gating_estudiantes.db`**
  - Archivo físico de base de datos SQLite.
  - Almacena de forma local y offline el estado persistente de los estudiantes.

---

# Especificación Técnica de la API

## `POST /evaluar`

Punto de acceso principal para el procesamiento de entregas de código de los estudiantes.

### Tipo de contenido

```text
multipart/form-data
```

### Parámetros de entrada

| Parámetro | Tipo | Ubicación | Descripción |
|-----------|------|-----------|-------------|
| `alumno_id` | `string` | Form Field | Identificador único del estudiante (ej. `alumno_001`). |
| `ejercicio_id` | `string` | Form Field | Código identificador del problema evaluado (ej. `dict_01`). |
| `file` | `file` | Binary | Archivo fuente de Python (`.py`) desarrollado por el estudiante. |

### Respuestas de la API

#### Caso A: Éxito total (código correcto)

```json
{
  "status": "exito",
  "mensaje": "¡Felicidades! Todos los tests pasaron. Has desbloqueado el siguiente ejercicio."
}
```

---

#### Caso B: Fallo lógico o sintáctico (activación de RAG + LLM)

```json
{
  "status": "fallo",
  "error_tecnico": "AssertionError: Se esperaba [1, 2, 3] pero se obtuvo ['a', 'b', 'c']...",
  "feedback_tutor": "En tu código, el error ocurre porque estás intentando... ¿Puedes modificar...?"
}
```

---

#### Caso C: Error del sistema (excepción en el Sandbox)

```json
{
  "status": "error_servidor",
  "mensaje": "Error interno: El contenedor no generó el reporte.json"
}
```

---

# Modelo de Datos y Estrategia de Gating (SQLite)

Para cumplir con las premisas de la tesis sobre **Gating** y **Rote Learning**, el esquema relacional modela el historial transaccional de reintentos.

## Tabla `progreso`

```sql
CREATE TABLE IF NOT EXISTS progreso (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    alumno_id TEXT NOT NULL,
    ejercicio_id TEXT NOT NULL,
    estado TEXT NOT NULL,
    intentos INTEGER DEFAULT 1
);
```

## Lógica de Actualización Dinámica

El sistema mantiene el progreso de cada estudiante mediante una estrategia de actualización incremental:

- Si el par **(`alumno_id`, `ejercicio_id`)** no existe en la base de datos, se inserta un nuevo registro con:
  - `intentos = 1`
  - `estado = "fallo"` o `estado = "exito"`, según el resultado de la evaluación.

- Si el par ya existe, el sistema:
  - Incrementa de forma atómica el número de intentos (`intentos = intentos + 1`).
  - Actualiza el estado con el resultado más reciente de la evaluación.

Esta estrategia permite conservar el historial de progreso del estudiante y medir la cantidad de iteraciones necesarias para dominar un ejercicio, proporcionando una métrica objetiva sobre su proceso de aprendizaje.

---

# Hallazgos Científicos y Lecciones Aprendidas

El desarrollo del **Sprint 1** permitió identificar dos fenómenos relevantes para la construcción del marco metodológico de la investigación.

## A. Conflicto de Entorno: Ciclo de Vida del Servidor (*Live Reload*)

### Fenómeno

Durante el desarrollo utilizando el parámetro `--reload` de Uvicorn, el guardado del archivo enviado por el estudiante (`ejercicio_alumno.py`) era detectado por el *File System Watcher*, provocando el reinicio automático del servidor.

Como consecuencia, el proceso de ejecución dentro del contenedor Docker era interrumpido antes de finalizar, impidiendo la correcta generación y lectura del archivo de resultados.

### Solución metodológica

Para entornos de producción o laboratorios educativos se establecen dos alternativas:

- Ejecutar el servidor en modo estático:

```bash
uvicorn main:app
```

- Configurar reglas de exclusión para que el mecanismo de *Live Reload* ignore el directorio donde se almacenan temporalmente las entregas de los estudiantes.

Este hallazgo valida la necesidad de mantener un aislamiento físico entre los archivos del servidor y los archivos procesados por el sandbox.

---

## B. Límites de Razonamiento en Modelos SLM (Alucinación Lógica Cuantizada)

### Fenómeno

Las pruebas realizadas con **Qwen 2.5 Coder 3B** evidenciaron que el modelo presenta un comportamiento consistente para seguir restricciones de formato, tales como:

- No generar directamente la solución.
- Mantener respuestas breves.
- Utilizar un estilo socrático.

Sin embargo, bajo escenarios con errores sintácticos o de lógica más complejos, el modelo mostró errores de razonamiento formal. Un caso observado fue atribuir incorrectamente el uso de `.values()` cuando el estudiante realmente utilizaba `.keys()`.

### Mitigación para el Sprint 2

Este resultado sugiere que los modelos pequeños (SLM menores de 7B parámetros) no deben depender únicamente de instrucciones declarativas.

Para mejorar la calidad del razonamiento, la estrategia de ingeniería de *prompts* se orientará hacia:

- **Chain-of-Thought (CoT)**, incentivando un razonamiento paso a paso antes de producir una respuesta.
- **Few-Shot Prompting**, proporcionando ejemplos estructurados que guíen el proceso inferencial del modelo.

Con ello se busca reducir las alucinaciones lógicas y aumentar la consistencia del feedback generado al estudiante.