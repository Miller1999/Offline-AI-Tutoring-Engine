# Documentación del Proyecto

**Objetivo del Sprint:** Desarrollar una interfaz gráfica de usuario (Frontend) basada en tecnologías web estándar y un diseño ágil con Tailwind CSS, eliminando la dependencia de la consola o herramientas de prueba (Swagger) para simular el entorno final del estudiante.

---

# 1. Resumen Ejecutivo

Durante el Sprint 2 se integró exitosamente la capa de presentación directamente en el servidor **FastAPI** mediante el uso de `FileResponse`. Siguiendo los lineamientos metodológicos de la investigación, se diseñó una interfaz libre de cajas de chat convencionales para reducir el riesgo de *Prompt Injection* y minimizar las distracciones cognitivas durante el proceso de aprendizaje.

El estudiante interactúa exclusivamente mediante un formulario estructurado para el envío de sus ejercicios, mientras que toda la lógica de evaluación permanece encapsulada en el backend.

---

# 2. Flujo de Datos End-to-End

El flujo completo de información entre los diferentes componentes del sistema es el siguiente:

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

Este flujo desacopla la interfaz de usuario, la lógica de negocio, el almacenamiento persistente y el motor de inteligencia artificial, facilitando el mantenimiento y la escalabilidad del sistema.

---

# 3. Implementación del Frontend (`index.html`)

La interfaz fue desarrollada utilizando **HTML**, **JavaScript** y **Tailwind CSS** mediante CDN durante la etapa de prototipado.

## Características del diseño

### Campos de identificación estructurados

El formulario solicita explícitamente:

- `alumno_id`
- `ejercicio_id`

Estos identificadores permiten que el sistema registre el progreso del estudiante de manera unívoca en la base de datos SQLite.

### Control de concurrencia

Cuando el usuario presiona **"Evaluar Código"**, JavaScript:

- Deshabilita temporalmente el botón.
- Reduce su opacidad para indicar que existe un proceso en ejecución.
- Evita múltiples solicitudes simultáneas que puedan afectar el procesamiento dentro del contenedor Docker.

### Estados visuales

La interfaz implementa tres estados mediante manipulación dinámica del DOM:

| Estado | Descripción |
|---------|-------------|
| **Carga** | Animación mientras el sandbox ejecuta la evaluación. |
| **Éxito** | Mensaje indicando que todos los casos de prueba fueron superados. |
| **Fallo** | Presentación del feedback generado por el tutor basado en IA. |

---

# 4. Modificaciones del Backend (`main.py`)

Para convertir el servidor FastAPI en el punto de entrada tanto de la API como de la interfaz gráfica, se reemplazó el endpoint raíz por un `FileResponse`.

```python
from fastapi.responses import FileResponse

@app.get("/")
def read_root():
    """
    Entrega la interfaz web principal del sistema.
    Sustituye el endpoint JSON utilizado durante la fase de desarrollo.
    """
    return FileResponse("index.html")
```

Con esta modificación el navegador recibe directamente la interfaz de usuario al acceder a la dirección principal del servidor.

---

# 5. Validación del Prototipo End-to-End

## A. Restricción Operativa Antidistracciones

Las pruebas realizadas demostraron que la ausencia de un chat conversacional obliga al estudiante a centrar su atención en:

- Su propio código.
- Los mensajes de retroalimentación.
- El proceso de depuración.

En consecuencia, el estudiante no establece una conversación libre con la IA, sino que utiliza el sistema como un tutor orientado exclusivamente a la resolución del ejercicio.

---

## B. Evidencia de las Limitaciones de Modelos SLM

Durante las pruebas con **Qwen 2.5 Coder 3B** se observaron dos comportamientos claramente diferenciados.

### Fortalezas

- Respeta estrictamente las instrucciones del prompt.
- No entrega soluciones completas.
- Mantiene respuestas breves.
- Sigue adecuadamente el formato socrático solicitado.

### Limitaciones

En algunos escenarios el modelo identifica correctamente la existencia del error, pero falla en la interpretación lógica del mismo.

Por ejemplo, durante una evaluación confundió el uso de:

- `.keys()`
- `.values()`

generando una explicación conceptualmente incorrecta aun cuando el diagnóstico general era adecuado.

Este comportamiento evidencia las limitaciones de razonamiento presentes en modelos pequeños ejecutados localmente.

---

# 6. Implicaciones Metodológicas

Los resultados obtenidos durante este sprint permiten extraer dos conclusiones relevantes para la investigación.

- Una interfaz minimalista reduce las posibilidades de distracción y disminuye la superficie de ataque para técnicas de *Prompt Injection*.
- La calidad pedagógica del sistema depende principalmente de la ingeniería de *prompts* y no únicamente de la interfaz de usuario.

En consecuencia, el siguiente sprint se enfocará en mejorar el proceso de razonamiento del modelo mediante técnicas de:

- **Chain-of-Thought (CoT)**.
- **Few-Shot Prompting**.
- Plantillas estructuradas de razonamiento.

Estas estrategias buscan incrementar la precisión conceptual del feedback generado sin incrementar significativamente los requerimientos de hardware del sistema.