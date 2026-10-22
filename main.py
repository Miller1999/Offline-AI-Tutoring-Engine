from fastapi import FastAPI, UploadFile, File, Form, Query, HTTPException
from fastapi.responses import FileResponse
from collections import defaultdict
import time
import os
import re
import shutil

# Importamos la lógica de evaluación y la base de datos
from orquestador import evaluar_codigo_en_sandbox, obtener_pista_socratica,generar_ejercicio_dinamico,generar_feedback_dinamico
from base_datos import inicializar_bd, registrar_intento, guardar_tema_alumno, obtener_tema_alumno, obtener_intentos_alumno, registrar_historial, contar_aprobados_por_tema
from aprendizaje_api import (
    obtener_categorias,
    obtener_temas_por_categoria,
    obtener_contenido_por_tema,
    buscar_contenido,
    obtener_estadisticas,
)

# --- SEGURIDAD: Rate Limiting (Límite de solicitudes por IP) ---
solicitudes_por_ip = defaultdict(list)
LIMITE_SOLICITUDES = 10       # Máximo de solicitudes por ventana de tiempo
VENTANA_TIEMPO = 60           # Ventana de tiempo en segundos
MAX_ALUMNO_ID_LENGTH = 100    # Longitud máxima para alumno_id
MAX_EJERCICIO_ID_LENGTH = 100 # Longitud máxima para ejercicio_id
MAX_TEMA_LENGTH = 200         # Longitud máxima para tema
MAX_QUERY_LENGTH = 500        # Longitud máxima para consultas de búsqueda


def verificar_rate_limit(ip: str):
    """
    Verifica si la IP ha excedido el límite de solicitudes en la ventana de tiempo.
    Lanza HTTPException si se excede el límite.
    """
    ahora = time.time()
    # Limpiar entradas antiguas
    solicitudes_por_ip[ip] = [t for t in solicitudes_por_ip[ip] if ahora - t < VENTANA_TIEMPO]
    
    if len(solicitudes_por_ip[ip]) >= LIMITE_SOLICITUDES:
        raise HTTPException(
            status_code=429,
            detail="Demasiadas solicitudes. Intenta de nuevo en un minuto."
        )
    
    solicitudes_por_ip[ip].append(ahora)


def validar_alumno_id(alumno_id: str) -> str:
    """
    Valida y sanitiza el ID del alumno para prevenir path traversal.
    Solo permite caracteres alfanuméricos, guiones y guiones bajos.
    """
    if not alumno_id or not isinstance(alumno_id, str):
        raise HTTPException(status_code=400, detail="ID de alumno inválido.")
    
    alumno_id = alumno_id.strip()[:MAX_ALUMNO_ID_LENGTH]
    
    # Prevenir path traversal: eliminar cualquier referencia a directorios
    alumno_id = alumno_id.replace("..", "").replace("/", "").replace("\\", "")
    
    # Solo permitir caracteres seguros (alfanuméricos, guiones, guion bajo)
    if not re.match(r'^[a-zA-Z0-9_\-]+$', alumno_id):
        raise HTTPException(
            status_code=400,
            detail="ID de alumno inválido. Solo se permiten caracteres alfanuméricos, guiones y guiones bajos."
        )
    
    return alumno_id


def validar_longitud(texto: str, max_length: int, nombre_campo: str = "Campo") -> str:
    """
    Valida que un texto no exceda la longitud máxima permitida.
    """
    if not texto or not isinstance(texto, str):
        raise HTTPException(status_code=400, detail=f"{nombre_campo} inválido.")
    
    texto = texto.strip()[:max_length]
    return texto


app = FastAPI(
    title="Motor de Tutoría IA Offline",
    description="API para evaluación automatizada, Gating y RAG Socrático",
    version="1.1"
)

# Inicializamos la base de datos local al arrancar FastAPI
inicializar_bd()

@app.post("/evaluar")
async def evaluar(
    alumno_id: str = Form(...),
    ejercicio_id: str = Form(...),
    file: UploadFile = File(...),
    request_req = None  # No needed - we use client IP
):
    # --- SEGURIDAD: Rate limiting ---
    # Nota: En producción usar request.client.host. Aquí usamos alumno_id como identificador
    verificar_rate_limit(alumno_id)
    
    # --- SEGURIDAD: Validar alumno_id (path traversal prevention) ---
    alumno_id = validar_alumno_id(alumno_id)
    
    # --- SEGURIDAD: Validar longitud del ejercicio_id ---
    ejercicio_id = validar_longitud(ejercicio_id, MAX_EJERCICIO_ID_LENGTH, "ejercicio_id")
    
    print(f"Recibiendo evaluación de {alumno_id} para el ejercicio {ejercicio_id}")
    
    # 1. Guardamos el código fuente que subió el alumno
    contenido_archivo = await file.read()
    if len(contenido_archivo) > 100000:  # 100KB limit
        return {"status": "error", "mensaje": "El archivo es demasiado grande."}
    with open("ejercicio_alumno.py", "wb") as f:
        f.write(contenido_archivo)

    # 2. LÓGICA DE ENRUTAMIENTO DE PRUEBAS
    if ejercicio_id.lower() == "dinamico":
        test_dinamico = f"test_dinamico_{alumno_id}.py"
        if not os.path.exists(test_dinamico):
            return {
                "status": "error", 
                "mensaje": "No se encontró un ejercicio dinámico activo."
            }
        import shutil
        shutil.copy(test_dinamico, "test_ejercicio.py")
        print(f"🔄 Usando test dinámico: {test_dinamico}")

    # 3. Llamamos al orquestador (Docker + IA)
    resultado = evaluar_codigo_en_sandbox()
    
    # 🔍 LOG DE DIAGNÓSTICO: Esto nos dirá qué está respondiendo Docker realmente
    print(f"🔍 DEBUG - Resultado del orquestador: {resultado}")

    # --- PREPARACIÓN PARA HISTORIAL SQLITE ---
    tema = obtener_tema_alumno(alumno_id)
    intento_actual = obtener_intentos_alumno(alumno_id, ejercicio_id) + 1  # +1 porque este es el intento nuevo
    
    # 4. INTERCEPCIÓN ESTRUCTURADA (Fase 1 del Sprint 4)
    
    # 🟢 CASO A: El código es 100% correcto
    if resultado.get("status") == "exito":
        print("✅ Evaluación exitosa. Retornando éxito al frontend.")
        registrar_historial(alumno_id, tema, ejercicio_id, "aprobado", intento_actual)
        registrar_intento(alumno_id, ejercicio_id, "aprobado")
        return resultado
        
    # 🔴 CASO B: Es un ejercicio dinámico y falló (ya sea por sintaxis, importación o lógica)
    if ejercicio_id.lower() == "dinamico":
        print("🧠 Generando feedback socrático improvisado...")
        registrar_historial(alumno_id, tema, ejercicio_id, "fallido", intento_actual)
        registrar_intento(alumno_id, ejercicio_id, "fallido")

        with open("ejercicio_alumno.py", "r", encoding="utf-8") as f_alumno:
            codigo_alumno = f_alumno.read()
            
        # Capturamos el error real. Dependiendo de cómo falló, la llave puede llamarse "error" o "feedback_tutor"
        error_crudo = resultado.get("error") or resultado.get("feedback_tutor") or "Error de evaluación desconocido."
        
        pregunta_socratica = generar_feedback_dinamico(error_crudo, codigo_alumno)
        return {
            "status": "fallo",
            "feedback_tutor": pregunta_socratica
        }
        
    # 🟡 CASO C: Es un ejercicio estático y falló críticamente (ej. error de sintaxis)
    if "error" in resultado:
        registrar_historial(alumno_id, tema, ejercicio_id, "fallido", intento_actual)
        registrar_intento(alumno_id, ejercicio_id, "fallido")
        return {
            "status": "error", 
            "mensaje": f"Error crítico en el código: {resultado['error']}"
        }
    
    # 🔵 CASO D: Es un ejercicio estático y falló lógicamente (el orquestador original ya hizo RAG)
    registrar_historial(alumno_id, tema, ejercicio_id, "fallido", intento_actual)
    registrar_intento(alumno_id, ejercicio_id, "fallido")
    return resultado

@app.post("/generar")
async def generar_ejercicio(tema: str = Form(...), alumno_id: str = Form(...)):
    """
    Genera un ejercicio con IA y guarda el test de forma segura en el servidor
    (Opción B: Arquitectura con Estado).
    Incluye Motor de Dificultad Adaptativa (Fase 3).
    """
    # --- SEGURIDAD: Rate limiting ---
    verificar_rate_limit(alumno_id)
    
    # --- SEGURIDAD: Validar alumno_id (path traversal prevention) ---
    alumno_id = validar_alumno_id(alumno_id)
    
    # --- SEGURIDAD: Validar y limitar longitud del tema ---
    tema = validar_longitud(tema, MAX_TEMA_LENGTH, "tema")
    
    print(f"Generando ejercicio de '{tema}' para {alumno_id}...")

    # --- MOTOR DE DIFICULTAD ADAPTATIVA (Fase 3) ---
    # Consultamos SQLite: cuantos ejercicios de este tema ha aprobado el alumno
    aprobados = contar_aprobados_por_tema(alumno_id, tema)

    # Logica de Niveles:
    # 0 aprobados = Nivel Basico (conceptos fundamentales)
    # 1-2 aprobados = Nivel Intermedio (combinacion de metodos)
    # 3+ aprobados = Nivel Avanzado (casos limite o algoritmos complejos)
    if aprobados >= 3:
        dificultad = "avanzado"
    elif aprobados >= 1:
        dificultad = "intermedio"
    else:
        dificultad = "basico"

    print(f"📊 Dificultad Adaptativa: {alumno_id} ha aprobado {aprobados} veces '{tema}' -> Nivel: {dificultad}")

    # 1. Llamamos a nuestro orquestador con la dificultad calculada
    resultado = generar_ejercicio_dinamico(tema, dificultad)
    
    if "error" in resultado:
        return {"status": "error", "mensaje": resultado["error"]}
    
    # 2. Guardamos el test en secreto en el backend
    nombre_archivo_test = f"test_dinamico_{alumno_id}.py"
    with open(nombre_archivo_test, "w", encoding="utf-8") as f:
        f.write(resultado["codigo_test"])
    print(f"🔒 Test seguro guardado como: {nombre_archivo_test}")

    # 2b. Persistimos el tema del alumno para el historial de evaluaciones
    guardar_tema_alumno(alumno_id, tema)
    
    # 3. Le enviamos al frontend SOLO lo que el alumno debe ver
    return {
        "status": "exito",
        "datos": {
            "instrucciones": resultado["instrucciones"],
            "ejemplo_esperado": resultado.get("ejemplo_esperado", "No se proporcionó un ejemplo."),
            "codigo_base": resultado["codigo_base"]
            # ¡Fíjate que NO enviamos el codigo_test al frontend!
        }
    }

@app.get("/aprendizaje/estadisticas")
def get_estadisticas():
    """Obtiene estadísticas de la base de conocimiento (ChromaDB)."""
    return obtener_estadisticas()

@app.get("/aprendizaje/categorias")
def get_categorias():
    """Obtiene las categorías disponibles en la documentación."""
    categorias = obtener_categorias()
    return {"status": "exito", "categorias": categorias}

@app.get("/aprendizaje/temas")
def get_temas(categoria: str = Query(..., description="Categoría de la documentación")):
    """Obtiene los temas disponibles dentro de una categoría."""
    # --- SEGURIDAD: Validar longitud ---
    categoria = validar_longitud(categoria, MAX_QUERY_LENGTH, "categoria")
    temas = obtener_temas_por_categoria(categoria)
    return {"status": "exito", "temas": temas}

@app.get("/aprendizaje/contenido")
def get_contenido(tema: str = Query(...), categoria: str = Query(None)):
    """Obtiene el contenido (chunks) de un tema específico."""
    # --- SEGURIDAD: Validar longitud ---
    tema = validar_longitud(tema, MAX_QUERY_LENGTH, "tema")
    if categoria:
        categoria = validar_longitud(categoria, MAX_QUERY_LENGTH, "categoria")
    contenido = obtener_contenido_por_tema(tema, categoria)
    return {"status": "exito", "contenido": contenido}

@app.get("/aprendizaje/buscar")
def get_buscar(q: str = Query(..., description="Consulta de búsqueda semántica")):
    """Búsqueda semántica RAG sobre toda la documentación."""
    # --- SEGURIDAD: Validar longitud ---
    q = validar_longitud(q, MAX_QUERY_LENGTH, "consulta")
    resultados = buscar_contenido(q)
    return {"status": "exito", "resultados": resultados}

@app.get("/")
def read_root():
    # En lugar de un JSON, devolvemos nuestra página web
    return FileResponse("index.html")
