"""SQLite persistence layer: gating, attempt history and topic tracking.

The schema keeps the original table and column names so that an existing
database can be migrated by simply renaming the file. Two indexes that the
prototype was missing are created on top of it.
"""

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)

# ── Persisted status values ───────────────────────────────────────────────
STATUS_APPROVED = "approved"
STATUS_FAILED = "failed"


def _db_path() -> Path:
    """Return the resolved SQLite path, honouring the current settings."""
    return get_settings().sqlite_path


@contextmanager
def _connect() -> Iterator[sqlite3.Connection]:
    """Open a connection with row access by name and commit on success."""
    path = _db_path()
    path.parent.mkdir(parents=True, exist_ok=True)

    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    try:
        yield connection
        connection.commit()
    finally:
        connection.close()


def init_db() -> None:
    """Create the tables and indexes if they do not exist yet."""
    with _connect() as connection:
        cursor = connection.cursor()

        # Gating and attempt counter (Rote Learning).
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS progreso (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                alumno_id TEXT NOT NULL,
                ejercicio_id TEXT NOT NULL,
                estado TEXT NOT NULL,
                intentos INTEGER DEFAULT 1
            )
            """
        )

        # Detailed evaluation history used for learning analytics.
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS historial_ejercicios (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                alumno_id TEXT NOT NULL,
                tema TEXT,
                ejercicio_id TEXT NOT NULL,
                estado TEXT NOT NULL,
                intento_numero INTEGER DEFAULT 1,
                timestamp TEXT NOT NULL
            )
            """
        )

        # Current topic of each student (needed by dynamic exercises).
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS temas_alumnos (
                alumno_id TEXT PRIMARY KEY,
                tema TEXT NOT NULL,
                timestamp TEXT NOT NULL
            )
            """
        )

        # Indexes required by the per-student lookups.
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_progreso_alumno ON progreso(alumno_id, ejercicio_id)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_historial_alumno_tema "
            "ON historial_ejercicios(alumno_id, tema, estado)"
        )
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_temas_alumnos ON temas_alumnos(alumno_id)")

    logger.info("SQLite database ready (gating + history) at %s", _db_path())


def record_attempt(student_id: str, exercise_id: str, status: str) -> None:
    """Insert or update the attempt record of a student for a given exercise."""
    with _connect() as connection:
        cursor = connection.cursor()
        cursor.execute(
            "SELECT id, intentos FROM progreso WHERE alumno_id = ? AND ejercicio_id = ?",
            (student_id, exercise_id),
        )
        record = cursor.fetchone()

        if record:
            cursor.execute(
                "UPDATE progreso SET estado = ?, intentos = ? WHERE id = ?",
                (status, record["intentos"] + 1, record["id"]),
            )
        else:
            cursor.execute(
                "INSERT INTO progreso (alumno_id, ejercicio_id, estado, intentos) VALUES (?, ?, ?, 1)",
                (student_id, exercise_id, status),
            )


def get_attempt_count(student_id: str, exercise_id: str) -> int:
    """Return how many times a student attempted a given exercise."""
    with _connect() as connection:
        row = connection.execute(
            "SELECT intentos FROM progreso WHERE alumno_id = ? AND ejercicio_id = ?",
            (student_id, exercise_id),
        ).fetchone()

    return row["intentos"] if row else 0


def count_approved_by_topic(student_id: str, topic: str) -> int:
    """Count the exercises a student has passed within a topic."""
    with _connect() as connection:
        row = connection.execute(
            "SELECT COUNT(*) AS total FROM historial_ejercicios "
            "WHERE alumno_id = ? AND tema = ? AND estado = ?",
            (student_id, topic, STATUS_APPROVED),
        ).fetchone()

    total = row["total"] if row else 0
    logger.info("Adaptive difficulty: %s approved %s exercise(s) in '%s'", student_id, total, topic)
    return total


def set_student_topic(student_id: str, topic: str) -> None:
    """Persist the topic a student is currently working on."""
    now = datetime.now(UTC).isoformat()
    with _connect() as connection:
        connection.execute(
            "INSERT OR REPLACE INTO temas_alumnos (alumno_id, tema, timestamp) VALUES (?, ?, ?)",
            (student_id, topic, now),
        )
    logger.info("Topic '%s' stored for student '%s'", topic, student_id)


def get_student_topic(student_id: str) -> str:
    """Return the last topic stored for a student."""
    with _connect() as connection:
        row = connection.execute(
            "SELECT tema FROM temas_alumnos WHERE alumno_id = ?",
            (student_id,),
        ).fetchone()

    return row["tema"] if row else "Unknown topic"


def record_history(
    student_id: str,
    topic: str,
    exercise_id: str,
    status: str,
    attempt_number: int,
) -> None:
    """Append a detailed evaluation record to the history."""
    now = datetime.now(UTC).isoformat()
    with _connect() as connection:
        connection.execute(
            "INSERT INTO historial_ejercicios "
            "(alumno_id, tema, ejercicio_id, estado, intento_numero, timestamp) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (student_id, topic, exercise_id, status, attempt_number, now),
        )
    logger.info(
        "History recorded: %s | %s | %s | %s | attempt #%s",
        student_id,
        topic,
        exercise_id,
        status,
        attempt_number,
    )
