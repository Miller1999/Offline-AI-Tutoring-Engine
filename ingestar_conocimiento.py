"""
ingestar_conocimiento.py — Fase 4: Ingesta Masiva de Documentación en ChromaDB

Escanea recursivamente los archivos .txt de la documentación oficial de Python
(Libro de Python 3.14), los divide en chunks semánticos por secciones, los
vectoriza con el embedding local (ONNX MiniLM-L6-V2) y los almacena en ChromaDB.

Totalmente OFFLINE. Sin conexión a internet requerida.
"""

import os
import re
import hashlib
import chromadb
from chromadb.utils import embedding_functions
from tqdm import tqdm

# ─── CONFIGURACIÓN ───────────────────────────────────────────────────────────

# Ruta donde están los .txt de la documentación de Python
RUTA_DOCS = r"C:\Users\mille\Downloads\python-3.14-docs-text\python-3.14-docs-text"

# Ruta de la base de datos vectorial (misma que usa el orquestador)
RUTA_CHROMADB = "./bd_vectorial"

# Nombre de la colección (debe coincidir con el que usa orquestador.py)
COLECCION = "material_clase"

# Tamaño máximo de chunk en caracteres (para secciones muy grandes)
CHUNK_MAX_CHARS = 2000

# Tamaño mínimo de chunk para ser considerado válido
CHUNK_MIN_CHARS = 80

# Archivos de la raíz que NO contienen documentación técnica
ARCHIVOS_A_SALTAR = {
    "about.txt", "bugs.txt", "contents.txt", "copyright.txt",
    "glossary.txt", "improve-page.txt", "improve-page-nojs.txt",
    "license.txt", "index.txt",
}

# ─── FUNCIONES DE CHUNKING ──────────────────────────────────────────────────


def extraer_titulo(texto: str) -> str:
    """
    Extrae el título del documento (primera línea significativa).
    Ejemplo: '"json" --- JSON encoder and decoder'
    """
    lineas = texto.strip().split("\n")
    for linea in lineas[:5]:
        linea = linea.strip()
        if linea and not linea.startswith("**") and not linea.startswith("=="):
            # Quita la línea de separadores (***, ===)
            if not re.match(r"^[\*\=\-]{3,}$", linea.strip()):
                return linea.strip()[:120]
    return "Documento sin título"


def extraer_secciones(texto: str):
    """
    Divide el texto del documento en secciones basadas en encabezados.
    
    Detecta patrones como:
        4.1. "if" Statements
        ====================
    
    También detecta:
        Module contents
        ===============
    
    Retorna lista de (nombre_seccion, contenido_seccion)
    """
    lineas = texto.split("\n")
    secciones = []
    seccion_actual = []
    nombre_seccion_actual = "__intro__"
    
    # Patrones de inicio de sección: línea de texto seguida de línea de === o ---
    i = 0
    while i < len(lineas):
        linea = lineas[i]
        
        # Detectar si esta línea es un separador (===, ---, ***)
        if re.match(r"^[\=\-]{3,}$", linea.strip()) and i > 0:
            # La línea anterior es el título de la sección
            nombre_seccion = lineas[i - 1].strip()
            # Guardar sección anterior
            if seccion_actual:
                contenido = "\n".join(seccion_actual).strip()
                if len(contenido) >= CHUNK_MIN_CHARS:
                    secciones.append((nombre_seccion_actual, contenido))
            # Iniciar nueva sección
            seccion_actual = []
            nombre_seccion_actual = nombre_seccion
            i += 1
            continue
        
        # Detectar el patrón de título principal (línea con *** debajo)
        if re.match(r"^[\*]{3,}$", linea.strip()) and i > 0:
            # La línea anterior es el título principal del documento
            # No creamos nueva sección, solo lo registramos
            pass
        
        seccion_actual.append(linea)
        i += 1
    
    # Última sección
    if seccion_actual:
        contenido = "\n".join(seccion_actual).strip()
        if len(contenido) >= CHUNK_MIN_CHARS:
            secciones.append((nombre_seccion_actual, contenido))
    
    return secciones


def subdividir_seccion_grande(nombre_seccion: str, contenido: str):
    """
    Si una sección es demasiado grande, la subdivide por párrafos o
    por patrones de sub-secciones (líneas con --- debajo).
    
    Retorna lista de (nombre_sub, contenido_sub)
    """
    if len(contenido) <= CHUNK_MAX_CHARS:
        return [(nombre_seccion, contenido)]
    
    fragmentos = []
    
    # Intentar dividir por sub-secciones (detectando ---)
    lineas = contenido.split("\n")
    sub_actual = []
    sub_nombre = nombre_seccion
    i = 0
    
    while i < len(lineas):
        linea = lineas[i]
        
        # Detectar sub-sección (---)
        if re.match(r"^[\-]{3,}$", linea.strip()) and i > 0:
            # Guardar sub-sección anterior
            if sub_actual:
                texto_sub = "\n".join(sub_actual).strip()
                if len(texto_sub) >= CHUNK_MIN_CHARS:
                    fragmentos.append((sub_nombre, texto_sub))
            # Nueva sub-sección
            sub_nombre = lineas[i - 1].strip() if i > 0 else nombre_seccion
            sub_actual = []
            i += 1
            continue
        
        sub_actual.append(linea)
        i += 1
    
    if sub_actual:
        texto_sub = "\n".join(sub_actual).strip()
        if len(texto_sub) >= CHUNK_MIN_CHARS:
            fragmentos.append((sub_nombre, texto_sub))
    
    # Si aún hay fragmentos muy grandes, dividir por párrafos
    fragmentos_finales = []
    for nombre, texto in fragmentos:
        if len(texto) <= CHUNK_MAX_CHARS:
            fragmentos_finales.append((nombre, texto))
        else:
            # Dividir por párrafos agrupados
            parrafos = texto.split("\n\n")
            grupo_actual = []
            chars_actual = 0
            for parrafo in parrafos:
                if chars_actual + len(parrafo) > CHUNK_MAX_CHARS and grupo_actual:
                    fragmentos_finales.append((nombre, "\n\n".join(grupo_actual).strip()))
                    grupo_actual = [parrafo]
                    chars_actual = len(parrafo)
                else:
                    grupo_actual.append(parrafo)
                    chars_actual += len(parrafo) + 2
            
            if grupo_actual:
                texto_grupo = "\n\n".join(grupo_actual).strip()
                if len(texto_grupo) >= CHUNK_MIN_CHARS:
                    fragmentos_finales.append((nombre, texto_grupo))
    
    return fragmentos_finales if fragmentos_finales else [(nombre_seccion, contenido)]


def limpiar_chunk(texto: str) -> str:
    """
    Limpia un chunk de contenido redundante no útil para la tutoría.
    """
    # Eliminar líneas de "Source code:" y similares
    texto = re.sub(r"\*\*Source code:\*\*.*", "", texto)
    
    # Eliminar notas de copyright (detectadas entre [ ] al final)
    texto = re.sub(r"\-\[ Footnotes \]\-.*", "", texto, flags=re.DOTALL)
    
    # Eliminar líneas de separación sueltas
    texto = re.sub(r"^[\*\=\-]{3,}$", "", texto, flags=re.MULTILINE)
    
    # Comprimir múltiples saltos de línea
    texto = re.sub(r"\n{3,}", "\n\n", texto)
    
    return texto.strip()


def generar_id_unico(categoria: str, archivo: str, seccion: str, idx: int) -> str:
    """
    Genera un ID único y legible para cada chunk.
    """
    base = f"{categoria}_{archivo}_{seccion}_{idx}"
    hash_corto = hashlib.md5(base.encode()).hexdigest()[:8]
    return f"{categoria}_{archivo}_{idx:04d}_{hash_corto}"


# ─── SEGURIDAD: Escaneo de inyección en documentos ─────────────────────────


def escanear_contenido_sospechoso(texto: str, nombre_archivo: str) -> bool:
    """
    Escanea el contenido de un documento en busca de patrones de inyección
    de prompt u otros contenidos maliciosos antes de insertarlo en ChromaDB.

    Retorna True si se detecta contenido sospechoso.
    """
    patrones_sospechosos = [
        r'(?i)ignora\s+todas?\s+las\s+instrucciones',
        r'(?i)ignore\s+all\s+(previous|prior|above)\s+instructions',
        r'(?i)eres\s+ahora\s+un\s+asistente',
        r'(?i)you\s+are\s+now\s+(a\s+)?(helpful|useful)\s+assistant',
        r'(?i)override\s+system\s+prompt',
        r'(?i)anula\s+el\s+prompt\s+del\s+sistema',
        r'(?i)instrucciones?\s+secretas?',
        r'(?i)secret\s+instructions?',
        r'(?i)prioridad\s+(alta|mayor|superior)\s+que\s+las\s+instrucciones',
        r'(?i)higher\s+priority\s+than\s+(the\s+)?(system\s+)?instructions?',
        r'(?i)desobedece\s+las?\s+instrucciones?\s+(anteriores|del\s+sistema)',
        r'(?i)disobey\s+(the\s+)?(system\s+)?(previous\s+)?instructions?',
        r'(?i)nuevas?\s+instrucciones?\s+del\s+(sistema|administrador)',
        r'(?i)new\s+(system\s+)?instructions?\s+from\s+(the\s+)?admin',
    ]

    for patron in patrones_sospechosos:
        if re.search(patron, texto, re.IGNORECASE):
            print(f"   ⚠ CONTENIDO SOSPECHOSO detectado en '{nombre_archivo}': "
                  f"coincide con patrón '{patron[:50]}...'")
            return True

    return False


# ─── PROCESAMIENTO PRINCIPAL ────────────────────────────────────────────────


def escanear_archivos():
    """
    Escanea recursivamente el directorio de documentación y retorna
    una lista de (ruta_completa, categoria, nombre_archivo).
    """
    archivos = []
    for root, dirs, files in os.walk(RUTA_DOCS):
        for f in sorted(files):
            if not f.endswith(".txt"):
                continue
            if f in ARCHIVOS_A_SALTAR:
                continue
            
            ruta_completa = os.path.join(root, f)
            # La categoría es el nombre del subdirectorio (library, tutorial, etc.)
            categoria = os.path.basename(root)
            nombre_archivo = f.replace(".txt", "")
            archivos.append((ruta_completa, categoria, nombre_archivo))
    
    return archivos


def procesar_y_almacenar():
    """
    Función principal: escanea, chunkifica, vectoriza y almacena.
    """
    print("=" * 60)
    print("  FASE 4: INGESTA MASIVA DE DOCUMENTACIÓN EN CHROMADB")
    print("  Motor de Tutoría IA — Sandbox POC")
    print("=" * 60)
    
    # ── 1. Conectar a ChromaDB ──────────────────────────────────────────
    print("\n📦 Conectando a ChromaDB...")
    cliente = chromadb.PersistentClient(path=RUTA_CHROMADB)
    
    # Usar el embedding por defecto (ONNX MiniLM-L6-V2) — 100% offline
    embedding_fn = embedding_functions.DefaultEmbeddingFunction()
    
    # Obtener o crear la colección
    coleccion = cliente.get_or_create_collection(
        name=COLECCION,
        embedding_function=embedding_fn,
    )
    
    # ── 2. Escanear archivos ─────────────────────────────────────────────
    print("\n🔍 Escaneando archivos de documentación...")
    archivos = escanear_archivos()
    print(f"   📄 Encontrados {len(archivos)} archivos .txt para procesar.")
    
    # ── 3. Procesar cada archivo ─────────────────────────────────────────
    total_chunks = 0
    total_errores = 0
    todos_chunks = []  # Acumulamos para inserción masiva
    
    print(f"\n🧩 Chunkificando y vectorizando documentos...\n")
    
    for ruta, categoria, nombre_archivo in tqdm(archivos, desc="Procesando archivos", unit="archivo"):
        try:
            with open(ruta, "r", encoding="utf-8") as f:
                texto = f.read()
        except Exception as e:
            print(f"   ⚠ Error leyendo {ruta}: {e}")
            total_errores += 1
            continue
        
        if not texto.strip():
            continue
        
        # --- SEGURIDAD: Escanear contenido en busca de inyección de prompt ---
        if escanear_contenido_sospechoso(texto, nombre_archivo):
            print(f"   🛑 Documento '{nombre_archivo}' rechazado por contenido sospechoso.")
            total_errores += 1
            continue
        
        # Extraer título del documento
        titulo = extraer_titulo(texto)
        
        # Extraer secciones
        secciones = extraer_secciones(texto)
        if not secciones:
            # Si no hay secciones detectadas, tratar el documento completo como un solo chunk
            texto_limpio = limpiar_chunk(texto)
            if len(texto_limpio) >= CHUNK_MIN_CHARS:
                secciones = [("__completo__", texto_limpio)]
        
        # Procesar cada sección
        for nombre_seccion, contenido_seccion in secciones:
            # Subdividir si es muy grande
            sub_chunks = subdividir_seccion_grande(nombre_seccion, contenido_seccion)
            
            for sub_nombre, sub_contenido in sub_chunks:
                # Limpiar el contenido
                sub_contenido = limpiar_chunk(sub_contenido)
                if len(sub_contenido) < CHUNK_MIN_CHARS:
                    continue
                
                # Generar ID único
                chunk_id = generar_id_unico(categoria, nombre_archivo, sub_nombre, total_chunks)
                
                # Construir metadata
                metadata = {
                    "fuente": f"{categoria}/{nombre_archivo}",
                    "tema": titulo[:100],
                    "categoria": categoria,
                    "seccion": sub_nombre[:100],
                    "archivo": nombre_archivo,
                }
                
                todos_chunks.append({
                    "id": chunk_id,
                    "document": sub_contenido,
                    "metadata": metadata,
                })
                total_chunks += 1
    
    # ── 4. Inserción masiva en ChromaDB ──────────────────────────────────
    print(f"\n💾 Insertando {total_chunks} chunks en ChromaDB (colección '{COLECCION}')...")
    
    if todos_chunks:
        # Insertar en lotes de 100 para no saturar
        BATCH_SIZE = 100
        for i in range(0, len(todos_chunks), BATCH_SIZE):
            lote = todos_chunks[i:i + BATCH_SIZE]
            try:
                coleccion.add(
                    documents=[c["document"] for c in lote],
                    metadatas=[c["metadata"] for c in lote],
                    ids=[c["id"] for c in lote],
                )
            except Exception as e:
                print(f"   ⚠ Error insertando lote {i//BATCH_SIZE + 1}: {e}")
                total_errores += len(lote)
        
        # ── 5. Verificación ──────────────────────────────────────────────
        conteo_final = coleccion.count()
        print(f"\n{'=' * 60}")
        print(f"  ✅ ¡INGESTA COMPLETADA!")
        print(f"  📊 Total chunks insertados: {conteo_final}")
        print(f"  ⚠  Errores: {total_errores}")
        print(f"  📁 Categorías procesadas: {len(set(c['metadata']['categoria'] for c in todos_chunks))}")
        print(f"  💾 Base de datos: {RUTA_CHROMADB}")
        print(f"{'=' * 60}")
    else:
        print("\n⚠ No se generaron chunks para insertar.")
    
    return total_chunks


# ─── PRUEBA DE VERIFICACIÓN ────────────────────────────────────────────────


def test_consulta_rag(alumno_id: str = "test-ingenieria"):
    """
    Prueba que el RAG funcione correctamente después de la ingesta.
    Simula una consulta que el orquestador haría.
    """
    print("\n" + "=" * 60)
    print("  🧪 PRUEBA DE VERIFICACIÓN: BÚSQUEDA SEMÁNTICA RAG")
    print("=" * 60)
    
    cliente = chromadb.PersistentClient(path=RUTA_CHROMADB)
    coleccion = cliente.get_collection(name=COLECCION)
    
    # Consultas de prueba sobre distintos temas
    consultas = [
        "How to use lists and list methods in Python",
        "How to open and read a file",
        "How to use dictionaries with keys and values",
        "How to handle exceptions with try except",
        "How to define a class and create objects",
    ]
    
    print("\n🔎 Ejecutando consultas de prueba...\n")
    
    for consulta in consultas:
        print(f"  ▶ Consulta: \"{consulta}\"")
        try:
            resultados = coleccion.query(
                query_texts=[consulta],
                n_results=2,
            )
            
            if resultados and resultados["documents"] and resultados["documents"][0]:
                for j, doc in enumerate(resultados["documents"][0]):
                    metadatos = resultados["metadatas"][0][j]
                    score = resultados["distances"][0][j] if resultados.get("distances") else "N/A"
                    # Mostrar un resumen
                    preview = doc[:200].replace("\n", " ").strip()
                    print(f"    [{j+1}] Score: {score:.4f}" if isinstance(score, float) else f"    [{j+1}] Distancia: {score}")
                    print(f"        Fuente: {metadatos.get('fuente', 'desconocida')}")
                    print(f"        Tema: {metadatos.get('tema', 'N/A')}")
                    print(f"        Sección: {metadatos.get('seccion', 'N/A')}")
                    print(f"        Preview: {preview}...\n")
            else:
                print("    ⚠ Sin resultados\n")
        except Exception as e:
            print(f"    ⚠ Error en consulta: {e}\n")
    
    print("  ✅ Prueba de verificación completada.")


# ─── ENTRY POINT ────────────────────────────────────────────────────────────


if __name__ == "__main__":
    import sys
    
    print("""
╔══════════════════════════════════════════════════╗
║   🧠 MOTOR DE TUTORÍA IA - INGESTOR DE CONOCIMIENTO  ║
║   Fase 4: Ingesta Masiva de Documentación        ║
║   Python 3.14 Docs → ChromaDB (Offline)          ║
╚══════════════════════════════════════════════════╝
    """)
    
    # Verificar que la ruta de docs existe
    if not os.path.exists(RUTA_DOCS):
        print(f"❌ ERROR: No se encontró la ruta de documentación:")
        print(f"   {RUTA_DOCS}")
        print("   Por favor, verifica que los .txt de Python docs estén descargados.")
        sys.exit(1)
    
    # Ejecutar ingesta
    total = procesar_y_almacenar()
    
    # Preguntar si ejecutar prueba
    respuesta = input("\n¿Ejecutar prueba de verificación semántica? (s/n): ")
    if respuesta.lower() in ("s", "si", "sí", "y", "yes"):
        test_consulta_rag()
    
    print("\n🎉 Proceso completado. Ahora el orquestador.py tiene más")
    print("   conocimiento para asistir a los alumnos.")

