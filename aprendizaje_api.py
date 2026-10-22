"""
aprendizaje_api.py — Módulo de Aprendizaje basado en ChromaDB

Proporciona funciones para consultar la base de datos vectorial
y devolver contenido de documentación agrupado por categorías,
ideal para la sección "Aprendizaje" del frontend.

Totalmente OFFLINE. Sin conexión a internet requerida.
"""

import chromadb
from chromadb.utils import embedding_functions
import os

# ─── CONFIGURACIÓN ───────────────────────────────────────────────────────────

RUTA_CHROMADB = "./bd_vectorial"
COLECCION = "material_clase"
MAX_RESULTADOS_POR_CONSULTA = 50
MAX_RESULTADOS_BUSQUEDA = 5

# Cache del cliente ChromaDB (singleton)
_cliente = None
_coleccion = None


def _obtener_coleccion():
    """Obtiene o crea la conexión a ChromaDB (singleton)."""
    global _cliente, _coleccion
    
    if _coleccion is not None:
        return _coleccion
    
    try:
        _cliente = chromadb.PersistentClient(path=RUTA_CHROMADB)
        embedding_fn = embedding_functions.DefaultEmbeddingFunction()
        _coleccion = _cliente.get_collection(
            name=COLECCION,
            embedding_function=embedding_fn,
        )
        return _coleccion
    except Exception as e:
        print(f"⚠ Error conectando a ChromaDB: {e}")
        return None


def obtener_categorias():
    """
    Obtiene la lista de categorías disponibles en la documentación.
    Retorna una lista de dicts con {categoria, total_documentos}.
    """
    coleccion = _obtener_coleccion()
    if coleccion is None:
        return []
    
    try:
        # Obtener todos los metadatos (podemos usar get con limit)
        total = coleccion.count()
        if total == 0:
            return []
        
        # Obtener una muestra grande para extraer categorías
        resultados = coleccion.get(limit=min(total, 5000))
        metadatas = resultados.get("metadatas", [])
        
        # Contar documentos por categoría
        categorias = {}
        for meta in metadatas:
            if meta and "categoria" in meta:
                cat = meta["categoria"]
                if cat not in categorias:
                    categorias[cat] = 0
                categorias[cat] += 1
        
        # Ordenar alfabéticamente y formatear
        categorias_ordenadas = [
            {"categoria": cat, "total": total_docs}
            for cat, total_docs in sorted(categorias.items())
        ]
        
        return categorias_ordenadas
    
    except Exception as e:
        print(f"⚠ Error obteniendo categorías: {e}")
        return []


def obtener_temas_por_categoria(categoria: str):
    """
    Obtiene los temas (títulos de documentos) disponibles en una categoría.
    Retorna una lista de dicts con {tema, total_chunks}.
    """
    coleccion = _obtener_coleccion()
    if coleccion is None:
        return []
    
    try:
        # Buscar chunks que pertenezcan a esta categoría
        resultados = coleccion.get(
            where={"categoria": categoria},
            limit=MAX_RESULTADOS_POR_CONSULTA,
        )
        
        metadatas = resultados.get("metadatas", [])
        
        # Agrupar por tema
        temas = {}
        for meta in metadatas:
            if meta and "tema" in meta:
                tema = meta["tema"]
                if tema not in temas:
                    temas[tema] = {
                        "tema": tema,
                        "total_chunks": 0,
                        "secciones": set(),
                        "fuente_principal": meta.get("fuente", ""),
                    }
                temas[tema]["total_chunks"] += 1
                if meta.get("seccion"):
                    temas[tema]["secciones"].add(meta["seccion"])
        
        # Convertir sets a listas y ordenar
        resultado_final = []
        for t in temas.values():
            t["secciones"] = sorted(list(t["secciones"]))[:10]  # top 10 secciones
            resultado_final.append(t)
        
        resultado_final.sort(key=lambda x: x["tema"])
        return resultado_final
    
    except Exception as e:
        print(f"⚠ Error obteniendo temas para categoría '{categoria}': {e}")
        return []


def obtener_contenido_por_tema(tema: str, categoria: str = None):
    """
    Obtiene el contenido (chunks) de un tema específico.
    Retorna una lista de dicts con {seccion, contenido, fuente}.
    """
    coleccion = _obtener_coleccion()
    if coleccion is None:
        return []
    
    try:
        where_filter = {"tema": tema}
        if categoria:
            where_filter["categoria"] = categoria
        
        resultados = coleccion.get(
            where=where_filter,
            limit=MAX_RESULTADOS_POR_CONSULTA,
        )
        
        documents = resultados.get("documents", [])
        metadatas = resultados.get("metadatas", [])
        
        contenido = []
        for i, doc in enumerate(documents):
            meta = metadatas[i] if i < len(metadatas) else {}
            contenido.append({
                "seccion": meta.get("seccion", "Sin sección"),
                "contenido": doc,
                "fuente": meta.get("fuente", ""),
                "archivo": meta.get("archivo", ""),
            })
        
        return contenido
    
    except Exception as e:
        print(f"⚠ Error obteniendo contenido para tema '{tema}': {e}")
        return []


def buscar_contenido(query: str):
    """
    Búsqueda semántica RAG sobre toda la documentación.
    Retorna los fragmentos más relevantes.
    """
    coleccion = _obtener_coleccion()
    if coleccion is None:
        return []
    
    try:
        resultados = coleccion.query(
            query_texts=[query],
            n_results=MAX_RESULTADOS_BUSQUEDA,
        )
        
        documents = resultados.get("documents", [[]])[0]
        metadatas = resultados.get("metadatas", [[]])[0]
        distances = resultados.get("distances", [[]])[0]
        
        items = []
        for i, doc in enumerate(documents):
            meta = metadatas[i] if i < len(metadatas) else {}
            dist = distances[i] if i < len(distances) else 0
            relevance = max(0, min(100, round((1 - dist) * 100))) if isinstance(dist, (int, float)) else 0
            
            items.append({
                "contenido": doc,
                "relevancia": relevance,
                "tema": meta.get("tema", "Sin tema"),
                "seccion": meta.get("seccion", "Sin sección"),
                "fuente": meta.get("fuente", ""),
                "categoria": meta.get("categoria", ""),
            })
        
        return items
    
    except Exception as e:
        print(f"⚠ Error en búsqueda semántica: {e}")
        return []


def obtener_estadisticas():
    """
    Obtiene estadísticas generales de la base de conocimiento.
    """
    coleccion = _obtener_coleccion()
    if coleccion is None:
        return {"total_chunks": 0, "total_categorias": 0, "conectado": False}
    
    try:
        total = coleccion.count()
        categorias = obtener_categorias()
        
        return {
            "total_chunks": total,
            "total_categorias": len(categorias),
            "categorias": categorias,
            "conectado": True,
        }
    except Exception as e:
        return {"total_chunks": 0, "total_categorias": 0, "conectado": False, "error": str(e)}

