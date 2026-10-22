"""Tests for the SQLite persistence layer (gating, history and topic tracking)."""

from pathlib import Path

from app.services import database
from app.services.database import STATUS_APPROVED, STATUS_FAILED


class TestSchema:
    """The schema is created on demand and is safe to call twice."""

    def test_init_db_creates_the_tables(self, tmp_path: Path) -> None:
        database.init_db()
        database.init_db()  # must be idempotent

        with database._connect() as connection:
            tables = {
                row["name"]
                for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
            }

        assert {"progreso", "historial_ejercicios", "temas_alumnos"} <= tables

    def test_init_db_creates_the_indexes(self) -> None:
        database.init_db()

        with database._connect() as connection:
            indexes = {
                row["name"]
                for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'index'")
            }

        assert "idx_progreso_alumno" in indexes
        assert "idx_historial_alumno_tema" in indexes


class TestAttempts:
    """Attempts are counted per student and per exercise."""

    def test_new_student_has_no_attempts(self) -> None:
        database.init_db()

        assert database.get_attempt_count("student_001", "default") == 0

    def test_attempts_are_incremented(self) -> None:
        database.init_db()

        database.record_attempt("student_001", "default", STATUS_FAILED)
        database.record_attempt("student_001", "default", STATUS_FAILED)
        database.record_attempt("student_001", "default", STATUS_APPROVED)

        assert database.get_attempt_count("student_001", "default") == 3

    def test_attempts_are_isolated_per_exercise(self) -> None:
        database.init_db()

        database.record_attempt("student_001", "default", STATUS_FAILED)

        assert database.get_attempt_count("student_001", "dynamic") == 0


class TestApprovedByTopic:
    """The adaptive difficulty engine counts the approved exercises of a topic."""

    def test_counts_only_approved_attempts(self) -> None:
        database.init_db()

        database.record_history("student_001", "Lists", "e1", STATUS_APPROVED, 1)
        database.record_history("student_001", "Lists", "e2", STATUS_APPROVED, 1)
        database.record_history("student_001", "Lists", "e3", STATUS_FAILED, 1)
        database.record_history("student_001", "Dicts", "e4", STATUS_APPROVED, 1)

        assert database.count_approved_by_topic("student_001", "Lists") == 2
        assert database.count_approved_by_topic("student_001", "Dicts") == 1

    def test_unknown_student_has_no_approved_attempts(self) -> None:
        database.init_db()

        assert database.count_approved_by_topic("nobody", "Lists") == 0


class TestStudentTopic:
    """The current topic of a student is remembered between requests."""

    def test_topic_round_trip(self) -> None:
        database.init_db()

        database.set_student_topic("student_001", "Lists")

        assert database.get_student_topic("student_001") == "Lists"

    def test_topic_is_replaced_not_duplicated(self) -> None:
        database.init_db()

        database.set_student_topic("student_001", "Lists")
        database.set_student_topic("student_001", "Dicts")

        assert database.get_student_topic("student_001") == "Dicts"

    def test_unknown_student_returns_a_placeholder(self) -> None:
        database.init_db()

        assert database.get_student_topic("nobody") == "Unknown topic"


class TestHistory:
    """The history table keeps one row per evaluation."""

    def test_history_entries_are_appended(self) -> None:
        database.init_db()

        database.record_history("student_001", "Lists", "e1", STATUS_APPROVED, 1)
        database.record_history("student_001", "Lists", "e1", STATUS_FAILED, 2)

        with database._connect() as connection:
            rows = connection.execute(
                "SELECT estado, intento_numero FROM historial_ejercicios ORDER BY id"
            ).fetchall()

        assert [row["estado"] for row in rows] == [STATUS_APPROVED, STATUS_FAILED]
        assert [row["intento_numero"] for row in rows] == [1, 2]
