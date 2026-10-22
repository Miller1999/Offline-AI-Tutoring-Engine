import sqlite3
import os
from datetime import datetime

DB_NAME = "gating_estudiantes.db"

def inicializar_bd():
    """Crea la base de datos y las tablas si no existen."""
    conexion = sqlite3.connect(DB_NAME)
    cursor = conexion.cursor()
    
    # Tabla para registrar el Gating y los intentos (Rote Learning)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS progreso (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            alumno_id TEXT NOT NULL,
            ejercicio_id TEXT NOT NULL,
            estado TEXT NOT NULL,
            intentos INTEGER DEFAULT 1
        )
    ''')

    # Tabla para el historial detallado de evaluaciones (analíticas)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS historial_ejercicios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            alumno_id TEXT NOT NULL,
            tema TEXT,
            ejercicio_id TEXT NOT NULL,
            estado TEXT NOT NULL,
            intento_numero INTEGER DEFAULT 1,
            timestamp TEXT NOT NULL
        )
    ''')

    # Tabla para persistir el tema actual de cada alumno (ejercicios dinámicos)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS temas_alumnos (
            alumno_id TEXT PRIMARY KEY,
            tema TEXT NOT NULL,
            timestamp TEXT NOT NULL
        )
    ''')

    conexion.commit()
    conexion.close()
    print("📦 Base de datos SQLite (Gating + Historial) inicializada correctamente.")

def registrar_intento(alumno_id: str, ejercicio_id: str, estado: str):
    """Guarda o actualiza el intento de un alumno en un ejercicio específico."""
    conexion = sqlite3.connect(DB_NAME)
    cursor = conexion.cursor()
    
    # Verificamos si el alumno ya había intentado este ejercicio antes
    cursor.execute('''
        SELECT id, intentos FROM progreso 
        WHERE alumno_id = ? AND ejercicio_id = ?
    ''', (alumno_id, ejercicio_id))
    registro = cursor.fetchone()
    
    if registro:
        # Si ya existe, sumamos un intento y actualizamos el estado
        registro_id, intentos_previos = registro
        cursor.execute('''
            UPDATE progreso 
            SET estado = ?, intentos = ? 
            WHERE id = ?
        ''', (estado, intentos_previos + 1, registro_id))
    else:
        # Si es la primera vez, insertamos un registro nuevo
        cursor.execute('''
            INSERT INTO progreso (alumno_id, ejercicio_id, estado, intentos)
            VALUES (?, ?, ?, 1)
        ''', (alumno_id, ejercicio_id, estado))
        
    conexion.commit()
    conexion.close()

def obtener_intentos_alumno(alumno_id: str, ejercicio_id: str) -> int:
    """Obtiene el número actual de intentos del alumno en un ejercicio."""
    conexion = sqlite3.connect(DB_NAME)
    cursor = conexion.cursor()
    cursor.execute('''
        SELECT intentos FROM progreso 
        WHERE alumno_id = ? AND ejercicio_id = ?
    ''', (alumno_id, ejercicio_id))
    registro = cursor.fetchone()
    conexion.close()
    return registro[0] if registro else 0

def contar_aprobados_por_tema(alumno_id: str, tema: str) -> int:
    """
    Cuenta cuántos ejercicios ha aprobado un alumno en un tema específico.
    Útil para el Motor de Dificultad Adaptativa.
    """
    conexion = sqlite3.connect(DB_NAME)
    cursor = conexion.cursor()
    cursor.execute('''
        SELECT COUNT(*) FROM historial_ejercicios
        WHERE alumno_id = ? AND tema = ? AND estado = 'aprobado'
    ''', (alumno_id, tema))
    total = cursor.fetchone()[0]
    conexion.close()
    print(f"📊 Dificultad Adaptativa: {alumno_id} tiene {total} ejercicios aprobados en '{tema}'")
    return total

def guardar_tema_alumno(alumno_id: str, tema: str):
    """Guarda o actualiza el tema en que está trabajando el alumno."""
    ahora = datetime.now().isoformat()
    conexion = sqlite3.connect(DB_NAME)
    cursor = conexion.cursor()
    cursor.execute('''
        INSERT OR REPLACE INTO temas_alumnos (alumno_id, tema, timestamp)
        VALUES (?, ?, ?)
    ''', (alumno_id, tema, ahora))
    conexion.commit()
    conexion.close()
    print(f"📝 Tema '{tema}' guardado para alumno '{alumno_id}'.")

def obtener_tema_alumno(alumno_id: str) -> str:
    """Obtiene el último tema guardado para un alumno."""
    conexion = sqlite3.connect(DB_NAME)
    cursor = conexion.cursor()
    cursor.execute('''
        SELECT tema FROM temas_alumnos
        WHERE alumno_id = ?
    ''', (alumno_id,))
    registro = cursor.fetchone()
    conexion.close()
    return registro[0] if registro else "Tema desconocido"

def registrar_historial(alumno_id: str, tema: str, ejercicio_id: str, estado: str, intento_numero: int):
    """Inserta un registro detallado en el historial de evaluaciones."""
    ahora = datetime.now().isoformat()
    conexion = sqlite3.connect(DB_NAME)
    cursor = conexion.cursor()
    cursor.execute('''
        INSERT INTO historial_ejercicios (alumno_id, tema, ejercicio_id, estado, intento_numero, timestamp)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (alumno_id, tema, ejercicio_id, estado, intento_numero, ahora))
    conexion.commit()
    conexion.close()
    print(f"📊 Historial registrado: {alumno_id} | {tema} | {ejercicio_id} | {estado} | intento #{intento_numero}")

# Si ejecutamos este script directamente, creará la base de datos
if __name__ == "__main__":
    inicializar_bd()
