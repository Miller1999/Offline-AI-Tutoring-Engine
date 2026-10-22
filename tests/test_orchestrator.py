"""Regression tests for the defensive patches applied to generated exercises.

The hidden test suite is written by a local language model. Small models
regularly forget the import of the student module, import a name that does
not exist in the starter code, or import the module under a different name.
Every one of those cases produces an exercise the student cannot solve, so the
generator output is normalised before it is stored.
"""

from typing import Any
from unittest.mock import Mock

from app.core.config import get_settings
from app.services import orchestrator
from app.services.orchestrator import (
    _ensure_student_import,
    _import_insertion_index,
    _starter_function_name,
)

STARTER = "def squares(numbers):\n    pass\n"


class TestStarterFunctionName:
    """The name of the function is read from the starter code."""

    def test_finds_the_function(self) -> None:
        assert _starter_function_name(STARTER) == "squares"

    def test_returns_none_without_a_function(self) -> None:
        assert _starter_function_name("numbers = [1, 2, 3]\n") is None


class TestEnsureStudentImport:
    """The generated test always imports the student module."""

    def test_adds_the_missing_import(self) -> None:
        test_code = "import pytest\n\ndef test_squares():\n    assert squares([2]) == [4]\n"

        patched = _ensure_student_import(test_code, STARTER, "exercise_student")

        assert "from exercise_student import squares" in patched

    def test_keeps_a_correct_import(self) -> None:
        test_code = (
            "import pytest\nfrom exercise_student import squares\n\ndef test_squares():\n    pass\n"
        )

        patched = _ensure_student_import(test_code, STARTER, "exercise_student")

        assert patched == test_code

    def test_corrects_a_wrong_function_name(self) -> None:
        test_code = "import pytest\nfrom exercise_student import square\n"

        patched = _ensure_student_import(test_code, STARTER, "exercise_student")

        assert "from exercise_student import squares" in patched
        assert "import square\n" not in patched

    def test_corrects_a_foreign_module_name(self) -> None:
        test_code = "import pytest\nfrom solution import squares\n"

        patched = _ensure_student_import(test_code, STARTER, "exercise_student")

        assert "from exercise_student import squares" in patched
        assert "from solution import" not in patched

    def test_leaves_the_code_untouched_without_a_starter_function(self) -> None:
        test_code = "import pytest\nfrom whatever import thing\n"

        patched = _ensure_student_import(test_code, "numbers = [1]\n", "exercise_student")

        assert patched == test_code

    def test_does_not_duplicate_an_existing_import(self) -> None:
        test_code = "from exercise_student import squares\nimport pytest\n"

        patched = _ensure_student_import(test_code, STARTER, "exercise_student")

        assert patched.count("from exercise_student import squares") == 1


class TestImportInsertionIndex:
    """The import is inserted in a position that keeps the file valid."""

    def test_inserts_at_the_top_of_a_plain_file(self) -> None:
        assert _import_insertion_index(["import pytest", "", "def test_x():", "    pass"]) == 0

    def test_inserts_after_a_module_docstring(self) -> None:
        lines = ['"""Hidden test suite."""', "", "import pytest"]

        assert _import_insertion_index(lines) == 1

    def test_inserts_after_a_multiline_docstring(self) -> None:
        lines = ['"""Hidden', "test suite.", '"""', "import pytest"]

        assert _import_insertion_index(lines) == 3

    def test_keeps_future_imports_first(self) -> None:
        lines = ["from __future__ import annotations", "import pytest"]

        assert _import_insertion_index(lines) == 1


class TestChatPayload:
    """Every request pins the context window and the keep-alive.

    Both values are inherited from the Ollama server configuration otherwise,
    and a 32k context does not fit in a modest GPU: the model spills into
    system RAM and every answer takes minutes.
    """

    @staticmethod
    def _capture(monkeypatch: Any) -> dict[str, Any]:
        captured: dict[str, Any] = {}

        def fake_post(
            url: str, json: dict[str, Any] | None = None, timeout: float | None = None
        ) -> Any:
            captured.update(json or {})
            response = Mock()
            response.json.return_value = {"message": {"content": "ok"}}
            return response

        monkeypatch.setattr(orchestrator.requests, "post", fake_post)
        return captured

    def test_pins_the_context_window(self, monkeypatch: Any) -> None:
        captured = self._capture(monkeypatch)

        orchestrator.ask_model("system", "user", get_settings())

        assert captured["options"]["num_ctx"] == get_settings().ollama_context_length

    def test_asks_the_server_to_keep_the_model_loaded(self, monkeypatch: Any) -> None:
        captured = self._capture(monkeypatch)

        orchestrator.ask_model("system", "user", get_settings())

        assert captured["keep_alive"] == get_settings().ollama_keep_alive

    def test_keeps_the_extra_parameters(self, monkeypatch: Any) -> None:
        captured = self._capture(monkeypatch)

        orchestrator.ask_model("system", "user", get_settings(), temperature=0.2, format="json")

        assert captured["temperature"] == 0.2
        assert captured["format"] == "json"


class TestWarmUpModel:
    """The model is loaded in the background when the API starts."""

    def test_reports_success(self, monkeypatch: Any) -> None:
        monkeypatch.setattr(orchestrator, "ask_model", lambda *args, **kwargs: "ready")

        assert orchestrator.warm_up_model() is True

    def test_survives_an_unreachable_server(self, monkeypatch: Any) -> None:
        def boom(*args: Any, **kwargs: Any) -> str:
            raise orchestrator.requests.exceptions.ConnectionError("no server")

        monkeypatch.setattr(orchestrator, "ask_model", boom)

        assert orchestrator.warm_up_model() is False
