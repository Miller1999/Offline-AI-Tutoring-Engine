# 🧠 Motor de Tutoría IA Offline — Sandbox POC

Documentación completa del proyecto dividida por sprints, diseñada para Obsidian.

---

## 📋 Índice de Sprints

| Sprint | Enfoque Principal | Archivo |
|--------|-------------------|---------|
| **Sprint 0** | Prueba de concepto del motor base (Docker + ChromaDB + Ollama) | [[Sprint 0 - Prueba de concepto del motor base]] |
| **Sprint 1** | Integración SQLite, Gating y API REST | [[Sprint 1 - Integración SQLite y Gating]] |
| **Sprint 2** | Capa de presentación Frontend minimalista | [[Sprint 2 - Capa de Presentacion Frontend Minimalista]] |
| **Sprint 3** | Generación dinámica de ejercicios y evaluación socrática resiliente | [[Sprint 3 - Generación Dinámica y Evaluación Socrática Resiliente]] |
| **Sprint 4** | Ingesta masiva de documentación y API de aprendizaje | [[Sprint 4 - Ingesta Masiva de Documentación y API de Aprendizaje]] |

---

## 🏗️ Arquitectura General

```text
┌──────────────────────────────────────────────────────┐
│                    Frontend (index.html)              │
│  [Formulario de Ejercicios] [Explorador de Docs]     │
└──────────────────────┬───────────────────────────────┘
                       │ HTTP (FormData / JSON)
                       ▼
┌──────────────────────────────────────────────────────┐
│              Backend API (main.py)                     │
│  FastAPI 1.1                                          │
│  ┌─────────────────┐  ┌──────────────────────────┐   │
│  │ /evaluar         │  │ /generar                 │   │
│  │ / (index.html)   │  │ /aprendizaje/*           │   │
│  └────────┬────────┘  └──────────┬───────────────┘   │
└───────────┼──────────────────────┼───────────────────┘
            │                      │
            ▼                      ▼
┌───────────────────────┐  ┌──────────────────────────┐
│  Orquestador Core      │  │  API de Aprendizaje       │
│  (orquestador.py)     │  │  (aprendizaje_api.py)    │
│  ┌─────────────────┐  │  │  ┌─────────────────────┐  │
│  │ Docker Sandbox   │  │  │  │ ChromaDB (RAG)      │  │
│  │ pytest + reporte │  │  │  │ consultas semánticas│  │
│  └────────┬────────┘  │  │  └─────────────────────┘  │
│  ┌─────────────────┐  │  └──────────────────────────┘
│  │ Ollama + Qwen    │  │
│  │ 2.5 Coder 7B     │  │
│  └─────────────────┘  │
│  ┌─────────────────┐  │
│  │ ChromaDB (RAG)   │  │
│  └─────────────────┘  │
└───────────────────────┘
            │
            ▼
┌──────────────────────────────────────────────────────┐
│              Persistencia Local                        │
│  ┌─────────────────┐  ┌──────────────────────────┐   │
│  │ SQLite           │  │ ChromaDB (bd_vectorial/)│   │
│  │ gating_estudian- │  │ embedding ONNX offline  │   │
│  │ tes.db           │  │ (MiniLM-L6-V2)          │   │
│  └─────────────────┘  └──────────────────────────┘   │
└──────────────────────────────────────────────────────┘
```

---

## 🔧 Stack Tecnológico

| Componente | Tecnología | Propósito |
|------------|------------|-----------|
| **Backend** | Python 3.14 + FastAPI | API REST |
| **Frontend** | HTML + CSS + JS vanilla | Interfaz de usuario |
| **Sandbox** | Docker (Alpine + pytest) | Ejecución segura de código |
| **Base de datos** | SQLite (vía sqlite3) | Gating y Rote Learning |
| **Vector DB** | ChromaDB (ONNX MiniLM-L6-V2) | Búsqueda semántica RAG |
| **IA Local** | Qwen 2.5 Coder 7B (via Ollama) | Tutor socrático + generación |
| **Documentación** | Python 3.14 Docs (528+ archivos .txt) | Base de conocimiento |

---

## 🚀 Cómo Ejecutar

### Prerrequisitos
- Python 3.14+
- Docker Desktop
- Ollama con modelo `qwen2.5-coder:7b`

### Instalación
```bash
# 1. Construir imagen Docker del sandbox
docker build -t sandbox-evaluador .

# 2. Ingestar documentación en ChromaDB (opcional, para RAG completo)
python ingestar_conocimiento.py

# 3. Iniciar el servidor
uvicorn main:app --host 0.0.0.0 --port 8000

# 4. Abrir navegador en http://localhost:8000
```

### Comandos Útiles
```bash
# Modo desarrollo (sin live reload para evitar conflictos)
uvicorn main:app --reload --reload-exclude "ejercicio_alumno.py"

# Probar generación de ejercicios directamente
python orquestador.py
```

---

## 📁 Estructura del Proyecto

```
sandbox_poc/
│
├── main.py                     # Servidor FastAPI (endpoints REST)
├── orquestador.py              # Núcleo: Docker + RAG + Ollama
├── base_datos.py               # Abstracción SQLite (Gating)
├── aprendizaje_api.py          # API de consulta ChromaDB
├── ingestar_conocimiento.py    # Ingesta masiva de documentación
├── cargar_rag.py               # Prototipo inicial RAG
│
├── index.html                  # Frontend completo (Tabs + UI)
├── Dockerfile                  # Sandbox Docker (pytest Alpine)
│
├── gating_estudiantes.db       # SQLite (Gating + Rote Learning)
├── bd_vectorial/               # ChromaDB persistente
│
├── test_ejercicio.py           # Tests Pytest estáticos
├── test_dinamico_*.py          # Tests dinámicos generados por IA
├── ejercicio_alumno.py         # Código subido por el estudiante
│
├── apuntes.md                  # Apuntes iniciales del profesor
│
├── docs/                       # 📚 Documentación (este directorio)
│   ├── README.md
│   ├── Sprint 0 - Prueba de concepto del motor base.md
│   ├── Sprint 1 - Integración SQLite y Gating.md
│   ├── Sprint 2 - Capa de Presentacion Frontend Minimalista.md
│   ├── Sprint 3 - Generación Dinámica y Evaluación Socrática.md
│   └── Sprint 4 - Ingesta Masiva de Documentación y API.md
│
└── Sprint *.md                 # Documentación original (raíz)
```

---

## 📊 Estado del Proyecto

| Componente | Estado | Sprint |
|------------|--------|--------|
| Sandbox Docker (pytest + reporte JSON) | ✅ Completado | 0 |
| RAG con ChromaDB (embedding offline) | ✅ Completado | 0 |
| Tutor IA (Qwen 2.5 Coder via Ollama) | ✅ Completado | 0 |
| Guardrail anti-solución | ✅ Completado | 0 |
| SQLite + Gating (progreso de estudiantes) | ✅ Completado | 1 |
| API REST FastAPI (endpoints) | ✅ Completado | 1 |
| Frontend minimalista (index.html) | ✅ Completado | 2 |
| Generación dinámica de ejercicios | ✅ Completado | 3 |
| Fallback feedback dinámico | ✅ Completado | 3 |
| Motor de dificultad adaptativa | ✅ Completado | 3 |
| Ingesta masiva documentación Python | ✅ Completado | 4 |
| API de aprendizaje + frontend docs | ✅ Completado | 4 |

---

## 🔐 Conceptos Clave de la Tesis

### Gating
Sistema de progresión donde cada ejercicio debe ser superado para desbloquear el siguiente. SQLite registra intentos y estados.

### Rote Learning
Medición objetiva de cuántas iteraciones necesita un estudiante para dominar un concepto, basado en el historial de reintentos.

### Evaluación Aislada
Ejecución de código no confiable en contenedor Docker sin red, con recursos limitados y destrucción automática post-evaluación.

### RAG Local
Contexto enriquecido mediante búsqueda semántica en base de conocimiento vectorial, 100% offline.

### Guardrails
Restricciones programáticas que impiden que la IA revele soluciones directas, manteniendo un enfoque estrictamente socrático.

