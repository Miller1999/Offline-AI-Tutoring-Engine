## Objetivo
Desarrollar una interfaz gráfica de usuario basada en tecnologías web estándar y un diseño ágil, eliminando la dependencia de la consola o herramientas de prueba (Swagger) para simular el entorno final del estudiante.

---

## Resumen Ejecutivo

Se integró exitosamente la capa de presentación directamente en el servidor **FastAPI** mediante `FileResponse`. Siguiendo lineamientos metodológicos de la investigación, se diseñó una interfaz **libre de cajas de chat** para reducir el riesgo de *Prompt Injection* y minimizar distracciones cognitivas.

El estudiante interactúa exclusivamente mediante formularios estructurados para el envío de ejercicios. Toda la lógica de evaluación permanece encapsulada en el backend.

---

## Flujo de Datos End-to-End

```text
[Estudiante (index.html)]
        │
        │ FormData (archivo + IDs)
        ▼
[Servidor REST (main.py)]
        │
        ├────────► [SQLite (base_datos.py)]
        │            (Gating y Rote Learning)
        │
        ▼
[Orquestador Core]
(Docker + RAG + Ollama)
        │
        │ JSON con feedback de IA
        ▼
[Servidor REST]
        │
        ▼
[Frontend]
(Muestra el resultado al estudiante)
```

---

## Implementación del Frontend (`index.html`)

### Arquitectura de Tabs

El frontend se organiza en dos pestañas principales:

| Pestaña | Función |
|---------|---------|
| 📝 **Ejercicios** | Generación de ejercicios por IA + Evaluación socrática |
| 📖 **Aprendizaje** | Exploración de documentación técnica con búsqueda semántica |

### Sección 1: Generador de Ejercicios (IA)

Formulario para solicitar ejercicios personalizados:

- **Campos:** `alumno_id`, `tema` del ejercicio
- **Flujo:** POST `/generar` → IA genera instrucciones + código base + tests secretos
- **Visualización:** Instrucciones, ejemplo esperado (estilo terminal) y código base

### Sección 2: Evaluador Socrático

Formulario de envío de código:

- **Campos:** `alumno_id`, `ejercicio_id` (usar `dinamico` para ejercicios generados), archivo `.py`
- **Control de concurrencia:** Botón se deshabilita durante la evaluación
- **Estados visuales:**
  - ⏳ **Carga:** Animación "pulse" mientras evalúa
  - ✅ **Éxito:** Badge verde + mensaje de aprobación
  - 🧠 **Fallo:** Badge amarillo + feedback socrático del tutor IA
  - ⚠️ **Error:** Badge rojo + mensaje técnico

### Sección 3: Material de Aprendizaje

Explorador de documentación con:

- **Búsqueda semántica:** Consulta RAG sobre ChromaDB
- **Navegación jerárquica:** Categorías → Temas → Contenido (con breadcrumb)
- **Renderizado Markdown:** Parser simple (sin dependencias externas) para visualizar la documentación
- **Diseño responsivo:** Grid adaptativo para categorías y temas

### Características de Diseño

- **Sin chat conversacional:** Reduce riesgo de *Prompt Injection*
- **Identificación estructurada:** Campos `alumno_id` y `ejercicio_id` obligatorios
- **Estados visuales:** Tres estados mediante manipulación dinámica del DOM
- **Markdown inline:** Parser propio sin dependencias externas

---

## Modificaciones del Backend (`main.py`)

### Endpoint raíz con FileResponse

```python
from fastapi.responses import FileResponse

@app.get("/")
def read_root():
    """Entrega la interfaz web principal."""
    return FileResponse("index.html")
```

### Lógica de enrutamiento en `/evaluar`

El endpoint distingue automáticamente entre ejercicios:

- **Estáticos** → usa `test_ejercicio.py` existente
- **Dinámicos** (`ejercicio_id == "dinamico"`) → copia `test_dinamico_{alumno_id}.py` → `test_ejercicio.py`

### Casos de respuesta estructurados

| Caso | Condición | Respuesta |
|------|-----------|-----------|
| 🟢 A | `status == "exito"` | Éxito directo, registra historial |
| 🔴 B | `ejercicio_id == "dinamico"` y falló | Feedback socrático sin RAG |
| 🟡 C | Error crítico (sintaxis) | Mensaje de error técnico |
| 🔵 D | Ejercicio estático y falló lógico | RAG + feedback del orquestador |

---

## Validación del Prototipo

### Restricción Operativa Antidistracciones

La ausencia de chat conversacional obliga al estudiante a centrarse en:
- Su propio código
- Mensajes de retroalimentación
- Proceso de depuración

### Evidencia de Limitaciones SLM

**Fortalezas de Qwen 2.5 Coder 7B:**
- Respeta instrucciones del prompt
- No entrega soluciones completas
- Mantiene respuestas breves
- Sigue formato socrático

**Limitaciones:**
- Alucinaciones lógicas en escenarios complejos
- Confusión entre `.keys()` y `.values()`

---

## Implicaciones Metodológicas

1. Una interfaz minimalista reduce distracciones y superficie de ataque para *Prompt Injection*
2. La calidad pedagógica depende principalmente de la ingeniería de *prompts*, no solo de la UI
3. El siguiente sprint se enfoca en mejorar el razonamiento mediante **Chain-of-Thought** y **Few-Shot Prompting**

