## Objetivos del Sprint

- Implementar la generación dinámica de ejercicios de programación mediante IA
- Establecer un flujo seguro para la evaluación de código generado dinámicamente sin exponer los tests al cliente
- Desarrollar un sistema de intercepción de errores (*Fallback*) para cuando el entorno de pruebas (Pytest) colapsa
- Refinar el *Prompt Engineering* del Tutor IA para evitar la **Fuga de Solución** (*Solution Leakage*)

---

## Arquitectura y Decisión: El Modelo con Estado

### Opción A: Sin Estado (*Stateless*) ❌
El test viaja al frontend y regresa durante la evaluación.
**Descartado** por vulnerabilidad académica: el estudiante podría inspeccionar o modificar el test desde el navegador.

### Opción B: Con Estado (*Stateful*) ✅
El backend almacena temporalmente el test y únicamente envía al estudiante las instrucciones del ejercicio.

**Decisión Arquitectónica:** Opción B. Esta arquitectura fortalece la seguridad mediante el concepto de **Gating**, garantizando que el código evaluador nunca sea enviado al navegador del estudiante.

Cada test dinámico se almacena temporalmente en el servidor con el formato:
```text
test_dinamico_{alumno_id}.py
```

---

## Implementación Técnica en `main.py`

### Endpoint `POST /generar`

```python
@app.post("/generar")
async def generar_ejercicio(tema: str, alumno_id: str):
```

**Flujo:**
1. Recibe `tema` y `alumno_id` del formulario
2. Consulta **Motor de Dificultad Adaptativa** en SQLite
3. Llama a `orquestador.generar_ejercicio_dinamico(tema, dificultad)`
4. Guarda el `codigo_test` en `test_dinamico_{alumno_id}.py` (secreto en backend)
5. Persiste el tema del alumno en `temas_alumnos`
6. Retorna solo `instrucciones`, `ejemplo_esperado`, `codigo_base` al frontend

### Enrutamiento inteligente en `POST /evaluar`

Cuando `ejercicio_id == "dinamico"`:
1. Busca `test_dinamico_{alumno_id}.py`
2. Copia sobre `test_ejercicio.py` (el que Docker espera ejecutar)
3. Reutiliza completamente el contenedor Docker del Sprint 1

### Intercepción Dinámica de Errores (*Fallback*)

Los ejercicios dinámicos NO existen en ChromaDB (son generados al vuelo). Para evitar que el RAG falle, se implementó:

```python
generar_feedback_dinamico(error_crudo, codigo_alumno)
```

Esta función:
1. Captura el error bruto de Pytest
2. Lo envía directamente a Ollama **sin depender de ChromaDB**
3. Genera retroalimentación socrática contextualizada

---

## Implementación del Generador en `orquestador.py`

### `generar_ejercicio_dinamico(tema, dificultad)`

Función que solicita a la IA generar un ejercicio completo desde cero.

**Prompt de sistema estructurado:**
- Define el nivel de dificultad (básico/intermedio/avanzado)
- Exige respuesta en **formato JSON estricto** con 4 llaves:
  - `instrucciones` — texto del problema
  - `ejemplo_esperado` — caso de prueba explícito
  - `codigo_base` — código inicial con `pass`
  - `codigo_test` — prueba Pytest (NUNCA enviada al frontend)

**Motor de Dificultad Adaptativa:**
- **0 aprobados** → Nivel Básico (conceptos fundamentales)
- **1-2 aprobados** → Nivel Intermedio (combinación de métodos)
- **3+ aprobados** → Nivel Avanzado (casos límite, algoritmos complejos)

**Parches Defensivos:**
1. Si la IA omite `ejemplo_esperado`, se asigna mensaje por defecto
2. Si el `codigo_test` carece de `from ejercicio_alumno import`, se inyecta automáticamente

### `generar_feedback_dinamico(error_crudo, codigo_alumno)`

Prompt socrático especializado para ejercicios dinámicos:
- No usa ChromaDB (no hay documentación del tema específico)
- Recibe el código del alumno + el error de Pytest
- Clasifica el error: `TypeError` (nombres de parámetros) vs `AssertionError` (valores)
- Prohíbe explícitamente respuestas en JSON
- Prohíbe mencionar la solución correcta o escribir código corregido

---

## Evolución del Prompt Engineering (Tutor IA)

| Iteración | Problema | Solución |
|-----------|----------|----------|
| **V1: Zero-Shot Genérico** | Modelo divagaba con teoría innecesaria | Restricción explícita al tema "Tipos de Datos" |
| **V2: Sobre-restricción** | Atribuía errores de tipos cuando era lógico | Análisis condicional para clasificar error |
| **V3: Corrección a Ciegas** | Solo veía el `assert` de Pytest, no el código | Inyección del código alumno en el prompt |
| **V4: Fuga de Solución** | IA revelaba cómo resolver | Guardrails para preguntas reflexivas, no soluciones |

### Prompt Final Consolidado

```python
prompt_sistema = """
Eres un tutor de programación estrictamente socrático.

Tu objetivo es guiar al alumno para que descubra su error por sí mismo.

REGLA 1 (CRÍTICA):
BAJO NINGUNA CIRCUNSTANCIA debes mencionar la solución correcta,
ni escribir métodos o funciones que el alumno no haya usado.

REGLA 2:
Compara el 'Código del alumno' con el 'Error de Pytest'.

REGLA 3:
Haz UNA sola pregunta reflexiva.

- Si el alumno usó un método incorrecto,
  pregúntale QUÉ devuelve exactamente el método que él escribió.

- Si el error es matemático,
  pregúntale qué valores está tomando su fórmula.

MANTÉN LA PREGUNTA CORTA,
AMIGABLE Y ENFOCADA EN EL CÓDIGO DEL ALUMNO,
NUNCA EN LA SOLUCIÓN.
"""
```

### Guardrail Duro de Seguridad

```python
if "```" in respuesta_ia or "def " in respuesta_ia:
    return "INTERVENCION DEL SISTEMA: El tutor intentó darte la respuesta directa..."
```

---

## Resultados y Conclusiones

### ✅ Ciclo End-to-End Completado

```text
Solicitud del tema
        ↓
Generación del ejercicio
        ↓
Resolución por el estudiante
        ↓
Evaluación automática
        ↓
Retroalimentación socrática
```

### ✅ Estabilidad del SLM

Un modelo de ~3B-7B parámetros puede ofrecer retroalimentación pedagógica de calidad cuando dispone de:
- El código del estudiante
- El error generado por Pytest
- Restricciones explícitas (*Guardrails*)

### ✅ Robustez ante Fallos

El sistema tolera:
- Errores de sintaxis
- Importaciones inexistentes
- Excepciones durante ejecución

Todos son capturados, procesados y presentados como mensajes comprensibles en la interfaz.

---

## Archivos Modificados

| Archivo | Cambio |
|---------|--------|
| `orquestador.py` | Nuevas funciones `generar_ejercicio_dinamico()` y `generar_feedback_dinamico()` |
| `main.py` | Nuevo endpoint `POST /generar`, enrutamiento dinámico en `/evaluar` |
| `index.html` | Sección de generación de ejercicios con formulario y visualización |

