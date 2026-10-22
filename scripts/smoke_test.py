"""End-to-end smoke test of the tutoring engine.

The script exercises the complete student journey against a running API:

    /health -> /exercises/default -> /evaluate (pass, fail, broken)
    -> /generate -> /evaluate (dynamic) -> /learning/stats

Every step prints its outcome and its elapsed time. The process exits with a
non-zero status when a step does not behave as expected, which makes it usable
both as a manual check and as a CI gate.

Usage::

    python scripts/smoke_test.py --start-server      # spawns uvicorn itself
    python scripts/smoke_test.py --base-url http://localhost:8000
    python scripts/smoke_test.py --start-server --json report.json

It requires the Docker sandbox image to be built (``make build-sandbox``) and
a local Ollama server with the configured model available.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import requests

#: Repository root, used to resolve the default exercise resources.
BASE_DIR = Path(__file__).resolve().parents[1]

#: Canonical solution of the built-in exercise (prints 1..n, one per line).
CORRECT_SOLUTION = (
    "def imprimir_numeros(n: int) -> None:\n    for i in range(1, n + 1):\n        print(i)\n"
)

#: Solution that compiles but fails the assertions (prints nothing).
WRONG_SOLUTION = "def imprimir_numeros(n: int) -> None:\n    return n\n"

#: Solution with a syntax error: the module cannot even be imported.
BROKEN_SOLUTION = "def imprimir_numeros(n: int) -> None\n    print(n)\n"


@dataclass
class Step:
    """Outcome of a single smoke test step."""

    name: str
    ok: bool
    detail: str
    seconds: float
    payload: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "ok": self.ok,
            "detail": self.detail,
            "seconds": round(self.seconds, 3),
            "payload": self.payload,
        }


class SmokeRunner:
    """Drive the API and collect the outcome of every step."""

    def __init__(self, base_url: str, student_id: str, timeout: float) -> None:
        self.base_url = base_url.rstrip("/")
        self.student_id = student_id
        self.timeout = timeout
        self.steps: list[Step] = []

    # ── Low level helpers ────────────────────────────────────────────────

    def _record(
        self,
        name: str,
        ok: bool,
        detail: str,
        seconds: float,
        payload: dict[str, Any] | None = None,
    ) -> None:
        step = Step(name=name, ok=ok, detail=detail, seconds=seconds, payload=payload or {})
        self.steps.append(step)
        mark = "PASS" if ok else "FAIL"
        print(f"[{mark}] {name:<34} {seconds:6.2f}s  {detail}", flush=True)

    def _timed(self, name: str, action: Any, check: Any) -> Step:
        """Run ``action``, measure it and validate the result with ``check``."""
        started = time.perf_counter()
        try:
            result = action()
        except Exception as exc:  # noqa: BLE001 - the smoke test reports everything
            elapsed = time.perf_counter() - started
            self._record(name, False, f"raised {type(exc).__name__}: {exc}", elapsed)
            return Step(name=name, ok=False, detail=str(exc), seconds=elapsed)

        elapsed = time.perf_counter() - started
        ok, detail, payload = check(result)
        self._record(name, ok, detail, elapsed, payload)
        return Step(name=name, ok=ok, detail=detail, seconds=elapsed, payload=payload)

    # ── Steps ────────────────────────────────────────────────────────────

    def check_health(self) -> None:
        def action() -> Any:
            return requests.get(f"{self.base_url}/health", timeout=self.timeout)

        def check(response: Any) -> tuple[bool, str, dict[str, Any]]:
            body = response.json()
            ok = response.status_code == 200 and body.get("status") in {"healthy", "degraded"}
            detail = (
                f"status={body.get('status')} llm={body.get('llm')} "
                f"vector_store={body.get('vector_store')} model_ready={body.get('model_ready')}"
            )
            return ok, detail, body

        self._timed("health", action, check)

    def wait_for_model(self, timeout: float = 300.0) -> bool:
        """Wait until the local model reports itself as loaded.

        The API loads the model in the background when it starts. Waiting for
        it here keeps the measurements of the following steps comparable.
        """
        deadline = time.time() + timeout

        while time.time() < deadline:
            try:
                if requests.get(f"{self.base_url}/health", timeout=10).json().get("model_ready"):
                    return True
            except requests.RequestException:
                pass
            time.sleep(2)

        return False

    def check_default_exercise(self) -> None:
        def action() -> Any:
            return requests.get(f"{self.base_url}/exercises/default", timeout=self.timeout)

        def check(response: Any) -> tuple[bool, str, dict[str, Any]]:
            body = response.json()
            data = body.get("data") or {}
            ok = (
                response.status_code == 200
                and body.get("status") == "success"
                and bool(data.get("instructions"))
                and bool(data.get("starter_code"))
            )
            return (
                ok,
                f"status={body.get('status')} instructions={len(data.get('instructions', ''))} chars",
                body,
            )

        self._timed("exercises/default", action, check)

    def evaluate(
        self, label: str, code: str, exercise_id: str = "default", expect: str = "failure"
    ) -> None:
        def action() -> Any:
            return requests.post(
                f"{self.base_url}/evaluate",
                data={"student_id": self.student_id, "exercise_id": exercise_id},
                files={"file": ("exercise_student.py", code, "text/x-python")},
                timeout=self.timeout,
            )

        def check(response: Any) -> tuple[bool, str, dict[str, Any]]:
            body = response.json()
            status = body.get("status")
            ok = response.status_code == 200 and status == expect
            detail = f"status={status}"
            if status == "failure":
                feedback = body.get("tutor_feedback") or ""
                detail += f" feedback={len(feedback)} chars"
                ok = ok and bool(feedback.strip())
                ok = ok and "SYSTEM INTERVENTION" not in feedback
            elif status == "success":
                detail += f" message={body.get('message')!r}"
            return ok, detail, body

        self._timed(f"evaluate/{label}", action, check)

    def generate(self, topic: str) -> None:
        def action() -> Any:
            return requests.post(
                f"{self.base_url}/generate",
                data={"topic": topic, "student_id": self.student_id},
                timeout=self.timeout,
            )

        def check(response: Any) -> tuple[bool, str, dict[str, Any]]:
            body = response.json()
            data = body.get("data") or {}
            ok = (
                response.status_code == 200
                and body.get("status") == "success"
                and bool(data.get("instructions"))
                and bool(data.get("starter_code"))
            )
            leaked = "test_code" in body or "test_code" in data
            ok = ok and not leaked
            detail = f"status={body.get('status')} instructions={len(data.get('instructions', ''))} chars"
            if leaked:
                detail += " LEAKED TEST CODE"
            return ok, detail, body

        self._timed("generate", action, check)

    def check_learning(self) -> None:
        def action() -> Any:
            return requests.get(f"{self.base_url}/learning/stats", timeout=self.timeout)

        def check(response: Any) -> tuple[bool, str, dict[str, Any]]:
            body = response.json()
            total = body.get("total_chunks", 0)
            ok = response.status_code == 200 and body.get("status") == "success" and total > 0
            return ok, f"total_chunks={total} connected={body.get('conectado')}", body

        self._timed("learning/stats", action, check)

    # ── Orchestration ────────────────────────────────────────────────────

    def run(self, topic: str, skip_generate: bool) -> bool:
        self.check_health()
        self.check_default_exercise()
        self.evaluate("correct", CORRECT_SOLUTION, expect="success")

        if self.wait_for_model():
            self._record("model/warm-up", True, "the local model is loaded", 0.0)
        else:
            self._record("model/warm-up", False, "the model did not report itself as ready", 0.0)

        self.evaluate("wrong", WRONG_SOLUTION, expect="failure")
        self.evaluate("broken-syntax", BROKEN_SOLUTION, expect="failure")

        if not skip_generate:
            self.generate(topic)
            self.evaluate(
                "dynamic-starter",
                "def placeholder():\n    pass\n",
                exercise_id="dynamic",
                expect="failure",
            )

        self.check_learning()
        return all(step.ok for step in self.steps)

    def as_dict(self) -> dict[str, Any]:
        return {
            "base_url": self.base_url,
            "student_id": self.student_id,
            "ok": all(step.ok for step in self.steps),
            "total_seconds": round(sum(step.seconds for step in self.steps), 3),
            "steps": [step.as_dict() for step in self.steps],
        }


def start_server(host: str, port: int, log_file: Path) -> subprocess.Popen[bytes]:
    """Spawn uvicorn and wait until it answers."""
    log_handle = log_file.open("wb")
    process = subprocess.Popen(  # noqa: S603 - fixed command, no shell
        [sys.executable, "-m", "uvicorn", "app.main:app", "--host", host, "--port", str(port)],
        cwd=str(BASE_DIR),
        stdout=log_handle,
        stderr=subprocess.STDOUT,
    )

    base_url = f"http://{host}:{port}"
    deadline = time.time() + 60
    while time.time() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"uvicorn exited early. See {log_file}")
        try:
            if requests.get(f"{base_url}/health", timeout=2).status_code == 200:
                return process
        except requests.RequestException:
            time.sleep(0.5)

    process.terminate()
    raise RuntimeError(f"uvicorn did not become ready. See {log_file}")


def main() -> int:
    parser = argparse.ArgumentParser(description="End-to-end smoke test of the tutoring engine.")
    parser.add_argument("--base-url", default="http://localhost:8000", help="URL of a running API.")
    parser.add_argument(
        "--start-server", action="store_true", help="Spawn uvicorn for the duration of the test."
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8013)
    parser.add_argument("--student-id", default="smoke_tester")
    parser.add_argument("--topic", default="list comprehensions")
    parser.add_argument(
        "--timeout", type=float, default=180.0, help="Timeout of every HTTP call, in seconds."
    )
    parser.add_argument(
        "--skip-generate", action="store_true", help="Skip the LLM-backed generation steps."
    )
    parser.add_argument("--json", type=Path, help="Write the machine readable report to this file.")
    args = parser.parse_args()

    process: subprocess.Popen[bytes] | None = None
    base_url = args.base_url

    try:
        if args.start_server:
            log_file = BASE_DIR / "logs" / "smoke-server.log"
            log_file.parent.mkdir(parents=True, exist_ok=True)
            process = start_server(args.host, args.port, log_file)
            base_url = f"http://{args.host}:{args.port}"
            print(f"uvicorn ready on {base_url}\n")

        runner = SmokeRunner(base_url=base_url, student_id=args.student_id, timeout=args.timeout)
        ok = runner.run(topic=args.topic, skip_generate=args.skip_generate)
        report = runner.as_dict()

        if args.json:
            args.json.parent.mkdir(parents=True, exist_ok=True)
            args.json.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
            print(f"\nreport written to {args.json}")

        failed = [step for step in runner.steps if not step.ok]
        print(f"\n{'=' * 72}")
        print(
            f"{len(runner.steps) - len(failed)}/{len(runner.steps)} steps passed in {report['total_seconds']}s"
        )
        for step in failed:
            print(f"  FAILED: {step.name} -> {step.detail}")
        return 0 if ok else 1
    finally:
        if process is not None:
            process.terminate()
            try:
                process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                process.kill()


if __name__ == "__main__":
    raise SystemExit(main())
