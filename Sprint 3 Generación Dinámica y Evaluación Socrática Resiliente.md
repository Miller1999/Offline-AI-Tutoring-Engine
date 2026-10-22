# 🎯 Objetivos del Sprint

- Implementar la generación dinámica de ejercicios de programación mediante IA.
- Establecer un flujo seguro para la evaluación de código generado dinámicamente sin exponer los tests al cliente.
- Desarrollar un sistema de intercepción de errores (*Fallback*) para cuando el entorno de pruebas (Pytest) colapsa.
- Refinar el *Prompt Engineering* del Tutor IA para evitar la **Fuga de Solución** (*Solution Leakage*) y garantizar un enfoque estrictamente socrático.

---

# 🏗️ Arquitectura y Toma de Decisiones: El Modelo con Estado

Durante este sprint se debatió el manejo del estado para los ejercicios dinámicos. Se evaluaron dos enfoques:

## Opción A: Sin Estado (*Stateless*)

El test viaja al frontend y regresa durante la evaluación.

**Resultado:** ❌ Descartado por vulnerabilidad académica, ya que el estudiante podría inspeccionar o modificar el test desde el navegador.

## Opción B: Con Estado (*Stateful*)

El backend almacena temporalmente el test y únicamente envía al estudiante las instrucciones del ejercicio.

### 💡 Decisión Arquitectónica (Aporte a la Tesis)

Se seleccionó la **Opción B**.

Esta arquitectura fortalece la seguridad mediante el concepto de **Gating**, garantizando que el código evaluador nunca sea enviado al navegador del estudiante.

Cada test dinámico se almacena temporalmente en el servidor con un nombre similar a:

```text
test_dinamico_{alumno_id}.py
```

---

# ⚙️ Implementación Técnica

## 1. Endpoint de Generación (`/generar`)

Se creó un endpoint en **FastAPI** encargado de orquestar la generación completa del ejercicio.

La IA produce:

- Contexto del ejercicio.
- Código base.
- Código de pruebas (`codigo_test`).

El código de pruebas permanece únicamente en el servidor, mientras que el frontend recibe exclusivamente la información necesaria para que el estudiante resuelva el ejercicio.

---

## 2. Enrutamiento Inteligente en Evaluación (`/evaluar`)

Se modificó el endpoint de evaluación para distinguir automáticamente entre ejercicios:

- Estáticos.
- Generados dinámicamente por IA.

### Mecanismo

Cuando:

```text
ejercicio_id == "dinamico"
```

el backend:

1. Busca el archivo temporal del estudiante (`test_dinamico_alumno_xxx.py`).
2. Sustituye el archivo `test_ejercicio.py` que el contenedor Docker espera ejecutar.

### Ventajas

- Reutiliza completamente el contenedor Docker desarrollado en el Sprint 1.
- No requiere modificar la lógica interna del evaluador.
- Mantiene una arquitectura modular y desacoplada.

---

## 3. Intercepción Dinámica de Errores (*Fallback*)

Los ejercicios generados dinámicamente no existen en la base de conocimiento (**ChromaDB**).

Como consecuencia, el orquestador original fallaba al intentar recuperar documentación relacionada.

### Solución

Se implementó la función:

```python
generar_feedback_dinamico()
```

Esta función:

1. Captura el error bruto producido por Pytest.
2. Lo envía directamente a Ollama.
3. Genera retroalimentación sin depender de la base de datos vectorial.

De esta manera, el sistema continúa funcionando incluso cuando no existe contexto previamente indexado.

---

# 🧠 Evolución del Prompt Engineering (Tutor IA)

El desarrollo del Tutor Socrático requirió múltiples iteraciones para controlar el comportamiento del **SLM (Qwen 3B)** y evitar la filtración de respuestas.

| Iteración | Problema Detectado | Solución Implementada |
|-----------|--------------------|-----------------------|
| **V1: Zero-Shot Genérico** | El modelo divagaba sobre teoría innecesaria o respondía de forma demasiado abstracta. | Se restringió explícitamente al tema **Tipos de Datos**. |
| **V2: Sobre-restricción** | El modelo atribuía erróneamente errores de tipos cuando el problema era puramente lógico. | Se implementó un análisis condicional para clasificar primero el tipo de error antes de responder. |
| **V3: Corrección a Ciegas** | Solo observaba el error de Pytest (`assert X == Y`) y no el código del estudiante, por lo que inventaba causas incorrectas. | Se inyectó el código del alumno (`ejercicio_alumno.py`) dentro del contexto enviado al modelo. |
| **V4: Fuga de Solución** | Con el contexto completo, la IA comenzaba a indicar directamente cómo resolver el problema. | Se implementaron **Guardrails** para obligar al modelo a formular preguntas reflexivas en lugar de revelar la solución. |

---

# 🔒 Prompt Final Consolidado

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

---

# 🚀 Resultados y Conclusiones del Sprint

## ✅ Ciclo End-to-End Completado

El flujo completo funciona correctamente en un entorno local:

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

---

## ✅ Estabilidad del Modelo

Se comprobó que un **Small Language Model (SLM)** de aproximadamente **3 mil millones de parámetros** puede ofrecer retroalimentación pedagógica de calidad cuando dispone de:

- El código del estudiante.
- El error generado por Pytest.
- Restricciones explícitas (*Guardrails*).

En estas condiciones, el modelo reduce significativamente las alucinaciones y evita revelar directamente la solución.

---

## ✅ Robustez ante Fallos

La plataforma ahora tolera errores como:

- Errores de sintaxis.
- Importaciones inexistentes.
- Excepciones durante la ejecución.

En lugar de interrumpir el flujo, dichos errores son capturados, procesados y presentados al estudiante como mensajes técnicos comprensibles dentro de la interfaz, mejorando la resiliencia general del sistema.