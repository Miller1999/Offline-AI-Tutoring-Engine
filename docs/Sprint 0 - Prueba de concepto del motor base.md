## Objetivo
Validar empíricamente la viabilidad técnica del núcleo de la arquitectura propuesta en la tesis (Evaluación Aislada + RAG Local + IA Cuantizada en un solo turno), operando 100% offline y en hardware de recursos limitados.

---

## Resumen

Se construyó exitosamente un orquestador en Python (`orquestador.py`) que automatiza el ciclo completo de evaluación de un estudiante. El sistema es capaz de instanciar un contenedor Docker efímero y sin red para ejecutar código no confiable, extraer el error estructurado generado por Pytest, enriquecer el contexto mediante una base de datos vectorial local (ChromaDB) e interactuar con un Modelo de Lenguaje de 7B parámetros (Qwen 2.5 Coder) vía Ollama para generar retroalimentación socrática segura.

---

## Componentes Construidos

### `orquestador.py` — Núcleo del sistema

El archivo principal que orquesta todo el flujo de evaluación. Contiene:

| Función | Propósito |
|---------|-----------|
| `evaluar_codigo_en_sandbox()` | Lanza contenedor Docker, ejecuta Pytest, extrae `reporte.json` y parsea resultados |
| `obtener_pista_socratica()` | Consulta ChromaDB (RAG), construye prompt contextual y llama a Ollama para feedback |
| `generar_ejercicio_dinamico()` | Solicita a la IA generar un ejercicio completo con tests (Sprint 3) |
| `generar_feedback_dinamico()` | Fallback para ejercicios dinámicos sin RAG (Sprint 3) |

### `Dockerfile` — Sandbox de evaluación

```dockerfile
FROM python:3.14-alpine
WORKDIR /app
RUN pip install --no-cache-dir pytest pytest-json-report
CMD ["pytest", "test_ejercicio.py", "--json-report", "--json-report-file=reporte.json"]
```

Características:
- Imagen Alpine extremadamente ligera
- Sin red (`--network none`)
- Límite de memoria (`--memory 256m`)
- Límite de CPU (`--cpus 0.5`)
- Contenedor efímero (flag `--rm`)

### `cargar_rag.py` — Prototipo inicial de RAG

Primera versión del cargador de documentos a ChromaDB. Lee `apuntes.md` y lo vectoriza en la colección `material_clase`. Reemplazado posteriormente por `ingestar_conocimiento.py`.

### `bd_vectorial/` — Base de datos vectorial

Directorio persistente de ChromaDB que almacena los embeddings de la documentación.

---

## Flujo de Operación

```text
[Estudiante] → sube código .py
       ↓
[main.py] → recibe archivo via POST /evaluar
       ↓
[orquestador.evaluar_codigo_en_sandbox()]
       ↓
[Docker] → pytest test_ejercicio.py → reporte.json
       ↓
[Parseo de resultados] → ¿tests pasaron?
       ↓                    ↓
   ✅ Éxito           ❌ FALLO
                      ↓
           [ChromaDB] → búsqueda semántica del error
                      ↓
           [Ollama + Qwen 2.5 Coder] → prompt contextual
                      ↓
           [Guardrails] → filtro de solución directa
                      ↓
           [Respuesta socrática al estudiante]
```

---

## Hitos Técnicos y Validación de Hipótesis

### ✅ Sandbox Docker sin red
- Contenedor efímero que se destruye automáticamente
- Sin acceso a internet (seguridad)
- Límites de recursos (memoria y CPU)

### ✅ Pipeline RAG funcional
- ChromaDB consulta la base de conocimiento vectorial
- Embeddings generados localmente (ONNX MiniLM-L6-V2)
- 3 fragmentos recuperados por consulta para contexto rico

### ✅ Integración con SLM local
- Qwen 2.5 Coder 7B via Ollama
- 100% offline, sin dependencia de APIs externas
- Temperatura controlada (0.3) para consistencia

### ✅ Guardrail anti-solución
- Sistema de intervención si la IA intenta escribir código (` ``` ` o `def `)
- Bloquea la fuga de solución (*Solution Leakage*)

---

## Lecciones Aprendidas

### Límites de SLMs pequeños
Los modelos de 3B-7B parámetros pueden alucinar lógica (ej. confundir `.keys()` con `.values()`). La mitigación requiere:
- **Chain-of-Thought (CoT)**
- **Few-Shot Prompting**
- Inyección del código del alumno en el prompt

### Conflicto con Live Reload
Uvicorn con `--reload` detecta el archivo `ejercicio_alumno.py` y reinicia el servidor. Solución: ejecutar en modo estático `uvicorn main:app`.

