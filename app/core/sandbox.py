"""Docker sandbox used to execute untrusted student code in isolation.

The sandbox mounts a single, request-scoped working directory — never the
repository itself — so that concurrent evaluations cannot interfere with each
other and the host filesystem stays out of reach.
"""

import json
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

from app.core.config import Settings, get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)

#: Name of the JSON report produced by ``pytest-json-report`` inside the container.
REPORT_FILENAME: Final[str] = "report.json"

#: Message shown when every assertion passed.
ALL_TESTS_PASSED_MESSAGE: Final[str] = "All tests passed correctly. Great work!"

#: Pytest phases, in the order in which they run.
TEST_PHASES: Final[tuple[str, ...]] = ("setup", "call", "teardown")


@dataclass
class SandboxResult:
    """Outcome of a sandboxed evaluation."""

    passed: bool
    failed_test: str | None = None
    error: str | None = None
    traceback: str | None = None
    stdout: str = ""
    stderr: str = ""
    infrastructure_error: str | None = None

    def to_payload(self) -> dict[str, Any]:
        """Return the normalised payload consumed by the API layer."""
        if self.infrastructure_error is not None:
            return {
                "status": "error",
                "message": f"Evaluation infrastructure error: {self.infrastructure_error}",
            }

        if self.passed:
            return {"status": "success", "message": ALL_TESTS_PASSED_MESSAGE}

        return {
            "status": "failure",
            "failed_test": self.failed_test,
            "error": self.error,
            "traceback": self.traceback,
        }


def build_docker_command(workdir: Path, settings: Settings) -> list[str]:
    """Build the ``docker run`` command used for the sandbox."""
    mount = workdir.resolve().as_posix()
    return [
        "docker",
        "run",
        "--rm",
        "--network",
        "none",
        "--memory",
        settings.sandbox_memory,
        "--cpus",
        settings.sandbox_cpus,
        "-v",
        f"{mount}:/app",
        settings.sandbox_image,
    ]


def parse_report(report: dict[str, Any]) -> SandboxResult:
    """Turn a ``pytest-json-report`` payload into a :class:`SandboxResult`.

    Three failure shapes are distinguished, because they reach the student
    through very different messages:

    * a **collection** error — the test module does not even import, typically
      because the student code has a syntax error or does not define the
      expected function. Pytest reports it on the collector and leaves the
      ``tests`` list empty, so it has to be handled *before* the test loop;
    * a failure in the **setup** phase — a broken fixture;
    * a regular **assertion** failure, reported in the ``call`` phase.
    """
    collector = _failed_collector(report)
    if collector is not None:
        longrepr = collector.get("longrepr") or ""
        return SandboxResult(
            passed=False,
            failed_test=collector.get("nodeid") or None,
            error=_extract_error_message(longrepr) or "The test module could not be imported.",
            traceback=longrepr,
        )

    for test in report.get("tests", []):
        if test.get("outcome") != "failed":
            continue

        for phase in TEST_PHASES:
            phase_data = test.get(phase) or {}
            if phase_data.get("outcome") != "failed":
                continue

            crash = phase_data.get("crash") or {}
            return SandboxResult(
                passed=False,
                failed_test=test.get("nodeid"),
                error=crash.get("message") or phase_data.get("longrepr") or "Unknown error",
                traceback=phase_data.get("longrepr", ""),
            )

    if report.get("exitcode") not in (0, None) and not (report.get("summary") or {}).get("failed"):
        # The run died without reporting a single failing test (an interrupted
        # session, a crashed interpreter, no test collected at all).
        return SandboxResult(
            passed=False,
            error="The test run did not complete.",
            traceback=(report.get("stderr") or ""),
        )

    return SandboxResult(passed=True)


def _failed_collector(report: dict[str, Any]) -> dict[str, Any] | None:
    """Return the first collector that failed, if any."""
    for collector in report.get("collectors", []):
        if collector.get("outcome") == "failed":
            return collector
    return None


def _extract_error_message(longrepr: str) -> str:
    """Extract the human readable error block out of a pytest longrepr.

    Pytest prefixes the offending lines with ``E ``. Those lines carry the
    actual exception — the most useful part for the tutor — so they are
    extracted and the traceback machinery around them discarded.
    """
    if not longrepr:
        return ""

    error_lines = [
        line[2:] if line.startswith("E ") else line[1:]
        for line in longrepr.splitlines()
        if line.startswith("E")
    ]
    if error_lines:
        return "\n".join(error_lines).strip()

    lines = [line.strip() for line in longrepr.splitlines() if line.strip()]
    return lines[-1] if lines else ""


def run_in_sandbox(workdir: Path, settings: Settings | None = None) -> SandboxResult:
    """Execute the pytest suite contained in ``workdir`` inside a Docker container.

    Args:
        workdir: A directory containing ``exercise_student.py`` and
            ``test_exercise.py``. It is the only path mounted into the container.
        settings: Optional settings override, mostly useful for tests.

    Returns:
        A :class:`SandboxResult`. Infrastructure failures are reported through
        the ``infrastructure_error`` field instead of raising.
    """
    settings = settings or get_settings()

    if not workdir.exists():
        return SandboxResult(passed=False, infrastructure_error=f"Missing workdir: {workdir}")

    command = build_docker_command(workdir, settings)
    logger.info("Starting Docker sandbox for %s", workdir.name)

    try:
        completed = subprocess.run(  # noqa: S603 - fixed command, no shell
            command,
            capture_output=True,
            text=True,
            timeout=settings.sandbox_timeout_seconds,
            check=False,
            cwd=str(workdir),
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        )
    except subprocess.TimeoutExpired:
        logger.error("Sandbox timed out after %ss", settings.sandbox_timeout_seconds)
        return SandboxResult(
            passed=False,
            infrastructure_error=f"Execution timed out after {settings.sandbox_timeout_seconds}s.",
        )
    except FileNotFoundError:
        logger.error("Docker executable not found")
        return SandboxResult(
            passed=False, infrastructure_error="Docker is not installed or not in PATH."
        )

    stdout = completed.stdout or ""
    stderr = completed.stderr or ""

    if completed.returncode != 0 and not (workdir / REPORT_FILENAME).exists():
        logger.error("Sandbox exited with code %s", completed.returncode)
        return SandboxResult(
            passed=False,
            stdout=stdout,
            stderr=stderr,
            infrastructure_error=_summarise_stderr(stderr) or "The sandbox container failed.",
        )

    report_path = workdir / REPORT_FILENAME
    if not report_path.exists():
        return SandboxResult(
            passed=False,
            stdout=stdout,
            stderr=stderr,
            infrastructure_error="The sandbox did not produce a report.",
        )

    try:
        report = json.loads(report_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return SandboxResult(
            passed=False,
            stdout=stdout,
            stderr=stderr,
            infrastructure_error=f"Could not read the sandbox report: {exc}",
        )

    result = parse_report(report)
    result.stdout = stdout
    result.stderr = stderr
    return result


def _summarise_stderr(stderr: str) -> str:
    """Extract the most relevant line out of the container stderr."""
    lines = [line.strip() for line in stderr.splitlines() if line.strip()]
    return lines[-1] if lines else ""
