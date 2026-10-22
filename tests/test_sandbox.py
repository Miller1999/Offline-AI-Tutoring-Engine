"""Regression tests for the parser of the sandbox JSON report.

The report written by ``pytest-json-report`` has three different shapes when
something goes wrong, and each one of them has to reach the student as a
failure. The most dangerous case is the *collection* error: pytest leaves the
``tests`` list empty, so a naive parser concludes that every test passed.
"""

from typing import Any

from app.core.sandbox import parse_report

#: Report produced when the student module does not even import.
COLLECTION_ERROR_REPORT: dict[str, Any] = {
    "exitcode": 2,
    "summary": {"total": 0, "collected": 0},
    "collectors": [
        {"nodeid": "", "outcome": "passed", "result": []},
        {
            "nodeid": "test_exercise.py",
            "outcome": "failed",
            "result": [],
            "longrepr": (
                "test_exercise.py:8: in <module>\n"
                "    from exercise_student import imprimir_numeros\n"
                'E     File "/app/exercise_student.py", line 1\n'
                "E       def imprimir_numeros(n: int) -> None\n"
                "E                                           ^\n"
                "E     SyntaxError: expected ':'"
            ),
        },
    ],
    "tests": [],
}

#: Report produced when an assertion fails.
ASSERTION_REPORT: dict[str, Any] = {
    "exitcode": 1,
    "summary": {"failed": 1, "passed": 3, "total": 4, "collected": 4},
    "collectors": [{"nodeid": "", "outcome": "passed", "result": []}],
    "tests": [
        {
            "nodeid": "test_exercise.py::test_imprimir_numeros[1-1\\n]",
            "outcome": "failed",
            "setup": {"outcome": "passed"},
            "call": {
                "outcome": "failed",
                "crash": {"message": "AssertionError: assert '' == '1\\n'"},
                "longrepr": "assert captured.out == expected_output\nE   AssertionError",
            },
            "teardown": {"outcome": "passed"},
        }
    ],
}

#: Report produced when a fixture fails before the test body runs.
SETUP_FAILURE_REPORT: dict[str, Any] = {
    "exitcode": 1,
    "summary": {"failed": 1, "passed": 0, "total": 1, "collected": 1},
    "collectors": [{"nodeid": "", "outcome": "passed", "result": []}],
    "tests": [
        {
            "nodeid": "test_exercise.py::test_thing",
            "outcome": "failed",
            "setup": {
                "outcome": "failed",
                "crash": {"message": "RuntimeError: the fixture exploded"},
                "longrepr": "E   RuntimeError: the fixture exploded",
            },
        }
    ],
}

#: Report of a run where every test passed.
PASSING_REPORT: dict[str, Any] = {
    "exitcode": 0,
    "summary": {"passed": 4, "total": 4, "collected": 4},
    "collectors": [{"nodeid": "", "outcome": "passed", "result": []}],
    "tests": [
        {
            "nodeid": "test_exercise.py::test_thing",
            "outcome": "passed",
            "setup": {"outcome": "passed"},
            "call": {"outcome": "passed"},
            "teardown": {"outcome": "passed"},
        }
    ],
}


class TestCollectionErrors:
    """A module that does not import must never look like a success."""

    def test_is_not_reported_as_passed(self) -> None:
        result = parse_report(COLLECTION_ERROR_REPORT)

        assert result.passed is False

    def test_surfaces_the_syntax_error(self) -> None:
        result = parse_report(COLLECTION_ERROR_REPORT)

        assert result.error is not None
        assert "SyntaxError" in result.error
        assert "expected ':'" in result.error

    def test_keeps_the_offending_line(self) -> None:
        result = parse_report(COLLECTION_ERROR_REPORT)

        assert result.error is not None
        assert "imprimir_numeros" in result.error

    def test_reports_the_module_as_the_failed_test(self) -> None:
        result = parse_report(COLLECTION_ERROR_REPORT)

        assert result.failed_test == "test_exercise.py"

    def test_keeps_the_traceback(self) -> None:
        result = parse_report(COLLECTION_ERROR_REPORT)

        assert "from exercise_student import" in (result.traceback or "")


class TestAssertionFailures:
    """The regular failure path keeps working."""

    def test_reports_the_assertion_message(self) -> None:
        result = parse_report(ASSERTION_REPORT)

        assert result.passed is False
        assert result.error == "AssertionError: assert '' == '1\\n'"
        assert result.failed_test == "test_exercise.py::test_imprimir_numeros[1-1\\n]"


class TestSetupFailures:
    """A broken fixture is a failure too, and it lives in another phase."""

    def test_reads_the_crash_of_the_setup_phase(self) -> None:
        result = parse_report(SETUP_FAILURE_REPORT)

        assert result.passed is False
        assert result.error == "RuntimeError: the fixture exploded"


class TestIncompleteRuns:
    """A run that died without a failing test is not a success either."""

    def test_non_zero_exit_without_failed_tests_is_a_failure(self) -> None:
        result = parse_report({"exitcode": 5, "summary": {"total": 0, "collected": 0}, "tests": []})

        assert result.passed is False
        assert result.error == "The test run did not complete."

    def test_a_passing_run_still_passes(self) -> None:
        result = parse_report(PASSING_REPORT)

        assert result.passed is True
        assert result.error is None
