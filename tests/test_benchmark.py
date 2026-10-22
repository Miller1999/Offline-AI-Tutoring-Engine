"""Tests for the benchmark harness.

The metrics of the benchmark are the numbers a thesis is built on, so they
are tested on their own: a metric that silently changes its meaning would
invalidate every run recorded before it.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

import pytest

# The benchmark lives in ``scripts/`` and is not an installed package.
SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "benchmark.py"
SPEC = importlib.util.spec_from_file_location("benchmark", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
benchmark = importlib.util.module_from_spec(SPEC)
# The module has to be registered before it runs, otherwise the dataclasses
# it declares cannot resolve their own module.
sys.modules[SPEC.name] = benchmark
SPEC.loader.exec_module(benchmark)

CORPUS_DIR = Path(__file__).resolve().parents[1] / "benchmarks" / "exercises"


class TestCorpus:
    """The corpus is versioned with the code and is well formed."""

    def test_the_corpus_is_not_empty(self) -> None:
        corpus = benchmark.load_corpus(CORPUS_DIR)

        assert len(corpus) >= 6

    def test_every_identifier_is_unique(self) -> None:
        corpus = benchmark.load_corpus(CORPUS_DIR)
        identifiers = [exercise.id for exercise in corpus]

        assert len(set(identifiers)) == len(identifiers)

    def test_every_exercise_declares_its_difficulty(self) -> None:
        corpus = benchmark.load_corpus(CORPUS_DIR)

        for exercise in corpus:
            assert exercise.difficulty in {"beginner", "intermediate", "advanced"}

    def test_every_exercise_declares_a_topic(self) -> None:
        corpus = benchmark.load_corpus(CORPUS_DIR)

        for exercise in corpus:
            assert exercise.topic.strip()

    def test_every_test_suite_imports_the_student_module(self) -> None:
        corpus = benchmark.load_corpus(CORPUS_DIR)

        for exercise in corpus:
            assert "from exercise_student import" in exercise.test_code

    def test_an_incomplete_exercise_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="missing the keys"):
            benchmark.Exercise.from_dict({"id": "broken"})


class TestHasCodeBlock:
    """The answer is checked for executable code."""

    def test_detects_a_markdown_fence(self) -> None:
        assert benchmark.has_code_block("```python\nprint(1)\n```") is True

    def test_detects_a_function_definition(self) -> None:
        assert benchmark.has_code_block("def sumar(a, b):\n    return a + b") is True

    def test_ignores_plain_prose(self) -> None:
        assert benchmark.has_code_block("Tu función debe devolver el total.") is False


class TestQuestions:
    """The Socratic shape of an answer is measured."""

    def test_detects_a_question(self) -> None:
        assert benchmark.has_question("¿Qué devuelve tu función?") is True

    def test_detects_a_missing_question(self) -> None:
        assert benchmark.has_question("Revisa el bucle.") is False

    def test_detects_an_answer_that_ends_on_a_question(self) -> None:
        assert benchmark.ends_with_question("¿Qué falta?  ") is True

    def test_detects_an_answer_that_continues_after_the_question(self) -> None:
        assert benchmark.ends_with_question("¿Qué falta? Porque el índice.") is False

    def test_returns_the_text_after_the_question(self) -> None:
        assert benchmark.text_after_question("¿Qué falta? Porque el índice.") == "Porque el índice."

    def test_returns_everything_when_there_is_no_question(self) -> None:
        assert benchmark.text_after_question("Sin pregunta.") == "Sin pregunta."


class TestLeaksSolution:
    """A copied solution is detected in the answer."""

    def test_detects_a_copied_line(self) -> None:
        solution = "def total(lista):\n    suma = 0\n    for numero in lista:\n        suma += numero\n    return suma\n"
        answer = "Prueba con esto: suma = 0 for numero in lista: suma += numero"

        assert benchmark.leaks_solution(answer, solution) is True

    def test_ignores_a_generic_answer(self) -> None:
        solution = "def total(lista):\n    suma = 0\n    for numero in lista:\n        suma += numero\n    return suma\n"
        answer = "¿Qué variable acumula el resultado de tu recorrido?"

        assert benchmark.leaks_solution(answer, solution) is False

    def test_ignores_the_signature_alone(self) -> None:
        solution = "def total(lista):\n    return 0\n"
        answer = "La función total debería devolver 0."

        assert benchmark.leaks_solution(answer, solution) is False

    def test_ignores_an_empty_answer(self) -> None:
        assert benchmark.leaks_solution("", "def total():\n    return 0\n") is False


class TestStarterIsSkeleton:
    """A starter code that already solves the exercise is detected."""

    def test_accepts_a_pass_skeleton(self) -> None:
        assert benchmark.starter_is_skeleton("def total(lista):\n    pass\n") is True

    def test_accepts_a_skeleton_with_a_docstring(self) -> None:
        starter = 'def total(lista):\n    """Devuelve el total."""\n    pass\n'

        assert benchmark.starter_is_skeleton(starter) is True

    def test_rejects_a_solved_starter(self) -> None:
        starter = "def total(lista):\n    return sum(lista)\n"

        assert benchmark.starter_is_skeleton(starter) is False

    def test_rejects_a_partially_solved_starter(self) -> None:
        starter = "def total(lista):\n    suma = 0\n    return suma\n"

        assert benchmark.starter_is_skeleton(starter) is False


class TestLeaksTestCode:
    """The hidden oracle must not appear in the instructions."""

    def test_detects_a_copied_assertion(self) -> None:
        test_code = "def test_x():\n    assert sumar([1, 2]) == 3\n"
        instructions = "Escribe sumar de forma que sumar([1, 2]) == 3 sea cierto."

        assert benchmark.leaks_test_code(instructions, test_code) is True

    def test_ignores_clean_instructions(self) -> None:
        test_code = "def test_x():\n    assert sumar([1, 2]) == 3\n"
        instructions = "Escribe una función que devuelva la suma de los elementos."

        assert benchmark.leaks_test_code(instructions, test_code) is False


class TestPercentile:
    """The latency percentiles are computed with a linear interpolation."""

    def test_returns_zero_without_values(self) -> None:
        assert benchmark.percentile([], 0.5) == 0.0

    def test_returns_the_only_value(self) -> None:
        assert benchmark.percentile([4.2], 0.95) == 4.2

    def test_interpolates_between_two_values(self) -> None:
        assert benchmark.percentile([1.0, 3.0], 0.5) == pytest.approx(2.0)

    def test_returns_the_maximum_at_the_top_percentile(self) -> None:
        assert benchmark.percentile([1.0, 2.0, 3.0, 4.0], 1.0) == pytest.approx(4.0)


class TestSummarise:
    """The aggregation of the observations is correct."""

    @staticmethod
    def _observation(**kwargs: Any) -> benchmark.Observation:
        defaults: dict[str, Any] = {
            "model": "model-a",
            "task": "feedback",
            "exercise_id": "e1",
            "topic": "topic",
            "difficulty": "beginner",
            "latency_s": 2.0,
            "ok": True,
            "metrics": {"has_question": True},
        }
        defaults.update(kwargs)
        return benchmark.Observation(**defaults)

    def test_groups_by_model_and_task(self) -> None:
        observations = [
            self._observation(),
            self._observation(model="model-b"),
            self._observation(task="generate"),
        ]

        summaries = benchmark.summarise(observations)

        assert len(summaries) == 3

    def test_computes_the_rate_of_a_boolean_metric(self) -> None:
        observations = [
            self._observation(metrics={"has_question": True}),
            self._observation(metrics={"has_question": False}),
        ]

        row = benchmark.summarise(observations)[0]

        assert row["has_question"] == pytest.approx(0.5)
        assert row["ok_rate"] == pytest.approx(1.0)

    def test_computes_the_latency_percentiles(self) -> None:
        observations = [
            self._observation(latency_s=1.0),
            self._observation(latency_s=2.0),
            self._observation(latency_s=3.0),
        ]

        row = benchmark.summarise(observations)[0]

        assert row["latency_p50"] == pytest.approx(2.0)
        assert row["latency_max"] == pytest.approx(3.0)
