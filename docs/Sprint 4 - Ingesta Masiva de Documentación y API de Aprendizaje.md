## Objetivos del Sprint

- Implementar la ingesta masiva de la documentación oficial de Python (528+ archivos `.txt`) en ChromaDB
- Crear una API de consulta estructurada para la sección "Aprendizaje" del frontend
- Mejorar el contexto RAG del orquestador con múltiples fragmentos y metadatos enriquecidos
- Mantener el funcionamiento 100% offline con embeddings locales (ONNX MiniLM-L6-V2)

---

## Componentes Construidos

### `ingestar_conocimiento.py` — Ingestor Masivo

Script principal que escanea, chunkifica, vectoriza y almacena la documentación oficial de Python 3.14 en ChromaDB.

**Características clave:**

| Característica | Detalle |
|----------------|---------|
| Escaneo recursivo | Recorre todos los subdirectorios de la documentación |
| Filtrado inteligente | Salta archivos no técnicos (`about.txt`, `copyright.txt`, etc.) |
| Chunking semántico | Divide por secciones (detectando `===`, `---`, `***`) |
| Subdivisión adaptativa | Fragmenta secciones grandes por párrafos |
| Limpieza de ruido | Elimina copyrights, "Source code:", footnotes |
| IDs únicos | Genera identificadores hash + secuenciales |
| Inserción por lotes | Lotes de 100 chunks para no saturar ChromaDB |
| Prueba de verificación | Consultas semánticas de prueba post-ingesta |

**Pipeline de chunking:**

```text
Archivo .txt (documentación Python)
        ↓
extraer_titulo() → Título del documento
        ↓
extraer_secciones() → [(sección, contenido), ...]
        ↓
subdividir_seccion_grande() → Fragmentación si >2000 caracteres
        ↓
limpiar_chunk() → Eliminación de ruido
        ↓
generar_id_unico() → ID hash para ChromaDB
        ↓
coleccion.add() → Inserción masiva en BD vectorial
```

### `aprendizaje_api.py` — API de Consulta para Frontend

Módulo que expone funciones para consultar la base de conocimiento desde `main.py`.

**Arquitectura:**
- **Singleton:** Conexión perezosa a ChromaDB (se crea en la primera consulta)
- **Cache:** Cliente y colección se mantienen en memoria global
- **100% offline:** Embeddings locales ONNX MiniLM-L6-V2

**Funciones expuestas:**

| Función | Endpoint HTTP | Propósito |
|---------|--------------|-----------|
| `obtener_categorias()` | `GET /aprendizaje/categorias` | Lista de categorías con conteo de documentos |
| `obtener_temas_por_categoria()` | `GET /aprendizaje/temas` | Temas dentro de una categoría |
| `obtener_contenido_por_tema()` | `GET /aprendizaje/contenido` | Chunks de contenido de un tema |
| `buscar_contenido()` | `GET /aprendizaje/buscar` | Búsqueda semántica RAG |
| `obtener_estadisticas()` | `GET /aprendizaje/estadisticas` | Estadísticas generales |

---

## Configuración del Ingestor

```python
RUTA_DOCS = r"C:\Users\mille\Downloads\python-3.14-docs-text\python-3.14-docs-text"
RUTA_CHROMADB = "./bd_vectorial"
COLECCION = "material_clase"
CHUNK_MAX_CHARS = 2000  # Tamaño máximo por chunk
CHUNK_MIN_CHARS = 80    # Tamaño mínimo para considerar válido
```

**Archivos excluidos por defecto:**
`about.txt`, `bugs.txt`, `contents.txt`, `copyright.txt`, `glossary.txt`, `improve-page.txt`, `improve-page-nojs.txt`, `license.txt`, `index.txt`

---

## Mejoras en el Orquestador (`orquestador.py`)

### RAG Enriquecido

La función `obtener_pista_socratica()` fue mejorada:

- **Más fragmentos:** Ahora recupera `n_results=3` (antes 1)
- **Metadatos enriquecidos:** Cada fragmento incluye fuente, tema, sección y distancia de relevancia
- **Logging:** Muestra estadísticas de ChromaDB en cada consulta
- **Prompt mejorado:** Contexto más rico con múltiples fragmentos del RAG

```python
# Antes: 1 fragmento sin metadatos
resultado_rag = coleccion.query(query_texts=[texto_busqueda], n_results=1)

# Después: 3 fragmentos con metadatos completos
resultado_rag = coleccion.query(query_texts=[texto_busqueda], n_results=3)
# Cada fragmento incluye: fuente, tema, sección, distancia de relevancia
```

### Prompt del Sistema Actualizado

```python
prompt_sistema = f"""Eres un tutor de programación socrático. Tu objetivo es ayudar 
al alumno a entender por qué falló su código, usando EXCLUSIVAMENTE los apuntes del profesor.

APUNTES DEL PROFESOR (Recuperados del RAG):
{apuntes_recuperados}

INSTRUCCIONES ESTRICTAS:
1. Háblale DIRECTAMENTE al alumno (ej. "En tu código, el error ocurre porque...").
2. Compara el error del alumno con los apuntes del profesor.
3. Formula UNA SOLA pregunta socrática al final.
4. NO agregues nada después de la pregunta. Termina con (?).
5. BAJO NINGUNA CIRCUNSTANCIA ESCRIBAS CÓDIGO.
"""
```

---

## Estructura de la Base de Datos Vectorial

```
bd_vectorial/
├── chroma.sqlite3          # Metadatos y configuración de ChromaDB
└── <uuid>/                 # Directorios con datos vectoriales por colección
    ├── data_level0.bin     # Vectores de embeddings
    ├── header.bin          # Cabecera de índice
    ├── index_metadata.pickle # Metadatos del índice
    ├── length.bin          # Longitudes
    └── link_lists.bin      # Listas de enlaces
```

---

## Estadísticas Post-Ingesta

- **Total de chunks insertados:** Depende de la documentación disponible
- **Categorías procesadas:** `library`, `tutorial`, `reference`, `howto`, `using`, `extending`, `distributing`, `install`, `faq`
- **Embeddings:** ONNX MiniLM-L6-V2 (100% offline)
- **Colección:** `material_clase`

---

## Prueba de Verificación

El script incluye `test_consulta_rag()` que ejecuta 5 consultas semánticas de prueba:

```python
consultas = [
    "How to use lists and list methods in Python",
    "How to open and read a file",
    "How to use dictionaries with keys and values",
    "How to handle exceptions with try except",
    "How to define a class and create objects",
]
```

Para ejecutar la prueba:
```bash
python ingestar_conocimiento.py
# Responder "s" cuando pregunte por la verificación
```

---

## Archivos Modificados/Creados

| Archivo | Tipo | Propósito |
|---------|------|-----------|
| `ingestar_conocimiento.py` | Nuevo | Ingesta masiva de documentación en ChromaDB |
| `aprendizaje_api.py` | Nuevo | API de consulta para frontend de aprendizaje |
| `orquestador.py` | Modificado | RAG enriquecido con `n_results=3` y metadatos completos |
| `main.py` | Modificado | 5 endpoints nuevos de aprendizaje |
| `index.html` | Modificado | Pestaña "Aprendizaje" con navegador de documentación |

