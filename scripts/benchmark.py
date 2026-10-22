"""Benchmark local models against the versioned exercise corpus.

The script measures the two capabilities the tutoring engine depends on:

* **exercise generation** — can the model design an exercise whose hidden
  test suite is importable, whose starter code is a real skeleton and whose
  instructions do not leak the oracle;
* **Socratic feedback** — can the model diagnose a real failure without
  handing the solution over, and does it end on a question.

Every model is measured through the *production* code path: the same prompt
builders, the same output guards and the same Docker sandbox the API uses. The
benchmark never re-implements the behaviour it measures.

The corpus lives in ``benchmarks/exercises`` and is versioned with the code, so
a run can be reproduced months later. Before measuring anything, the corpus is
validated against the real sandbox: the reference solution must pass the
hidden tests, the buggy submission must fail them, and the starter code must
not solve the exercise.

Usage::

    python scripts/benchmark.py --models qwen2.5-coder:7b,qwen3:8b
    python scripts/benchmark.py --models qwen2.5-coder:7b --tasks generate
    python scripts/benchmark.py --models qwen2.5-coder:7b --repeats 3

The results are written to ``reports/benchmarks/<timestamp>/`` as a CSV, a
Markdown summary and the raw model answers.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import re
import shutil
import statistics
import sys
import time
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# Allow running the script directly from the repository root.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import Settings, get_settings
from app.core.logging import configure_logging, get_logger
from app.core.sandbox import SandboxResult, run_in_sandbox
from app.core.security import INTERVENTION_MESSAGE, validate_ai_response
from app.services import orchestrator

logger = get_logger(__name__)

#: Repository root.
BASE_DIR = Path(__file__).resolve().parents[1]

#: Directory holding the versioned corpus.
CORPUS_DIR = BASE_DIR / "benchmarks" / "exercises"

#: Directory the reports are written to.
REPORTS_DIR = BASE_DIR / "reports" / "benchmarks"

#: Tasks the runner knows about.
TASK_ORACLE = "oracle"
TASK_GENERATE = "generate"
TASK_FEEDBACK = "feedback"
TASK_FEEDBACK_RAG = "feedback-rag"

ALL_TASKS = (TASK_ORACLE, TASK_GENERATE, TASK_FEEDBACK, TASK_FEEDBACK_RAG)

#: Keys the exercise generator must return.
REQUIRED_EXERCISE_KEYS = ("instructions", "expected_example", "starter_code", "test_code")


# ── Corpus ──────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Exercise:
    """One entry of the benchmark corpus."""

    id: str
    topic: str
    difficulty: str
    instructions: str
    expected_example: str
    starter_code: str
    solution_code: str
    failure_code: str
    test_code: str

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> Exercise:
        """Build an exercise from its JSON representation."""
        missing = [
            key
            for key in (
                "id",
                "topic",
                "difficulty",
                "instructions",
                "starter_code",
                "solution_code",
                "failure_code",
                "test_code",
            )
            if key not in payload
        ]
        if missing:
            raise ValueError(f"Exercise is missing the keys: {', '.join(missing)}")

        return cls(
            id=str(payload["id"]),
            topic=str(payload["topic"]),
            difficulty=str(payload["difficulty"]),
            instructions=str(payload["instructions"]),
            expected_example=str(payload.get("expected_example", "")),
            starter_code=str(payload["starter_code"]),
            solution_code=str(payload["solution_code"]),
            failure_code=str(payload["failure_code"]),
            test_code=str(payload["test_code"]),
        )


def load_corpus(directory: Path = CORPUS_DIR) -> list[Exercise]:
    """Load every exercise of the corpus, sorted by identifier."""
    if not directory.exists():
        raise FileNotFoundError(f"Corpus directory not found: {directory}")

    exercises = []
    for path in sorted(directory.glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        exercises.append(Exercise.from_dict(payload))

    if not exercises:
        raise ValueError(f"The corpus directory holds no exercise: {directory}")

    return exercises


# ── Metrics (pure functions, unit tested) ───────────────────────────────────


def normalise(text: str) -> str:
    """Collapse the whitespace of a text so two texts can be compared."""
    return " ".join(text.split())


def has_code_block(text: str) -> bool:
    """Whether the answer contains executable code."""
    if "```" in text:
        return True
    return bool(re.search(r"^\s*(def|class)\s+\w+", text, re.MULTILINE))


def has_question(text: str) -> bool:
    """Whether the answer contains a question mark."""
    return "?" in text


def ends_with_question(text: str) -> bool:
    """Whether the answer finishes on a question."""
    return text.strip().endswith("?")


def text_after_question(text: str) -> str:
    """Return the text that follows the last question mark of an answer."""
    stripped = text.strip()
    index = stripped.rfind("?")
    if index < 0:
        return stripped
    return stripped[index + 1 :].strip()


def leaks_solution(text: str, solution_code: str) -> bool:
    """Whether an answer reproduces a line of the reference solution.

    The check is deliberately strict: only the meaningful lines of the
    solution are compared, and only when they are long enough to be a real
    piece of logic rather than a closing bracket.
    """
    haystack = normalise(text)
    if not haystack:
        return False

    for line in solution_code.splitlines():
        candidate = normalise(line)
        if len(candidate) < 12:
            continue
        if candidate.startswith(("def ", "class ", "import ", "from ")):
            continue
        if candidate in haystack:
            return True

    return False


def starter_is_skeleton(starter_code: str) -> bool:
    """Whether the starter code is a skeleton instead of a solved exercise."""
    body: list[str] = []
    quote = ""

    for index, raw in enumerate(starter_code.splitlines()):
        line = raw.strip()
        if index == 0:
            continue
        if quote:
            if quote in line:
                quote = ""
            continue
        if line.startswith(('"""', "'''")):
            quote = line[:3] if line.count(line[:3]) < 2 else ""
            continue
        if not line:
            continue
        body.append(line)

    return all(line in {"pass", "...", "raise NotImplementedError"} for line in body)


def leaks_test_code(instructions: str, test_code: str) -> bool:
    """Whether the instructions give away the assertions of the hidden suite.

    The leak is detected on the *expression* of the assertion: spelling out
    "the call must return 3" in the instructions gives the exercise away even
    when the ``assert`` keyword is not repeated.
    """
    haystack = normalise(instructions)
    if not haystack:
        return False

    for line in test_code.splitlines():
        candidate = normalise(line)
        if not candidate.startswith("assert "):
            continue

        expression = candidate[len("assert ") :].strip()
        if len(expression) < 12:
            continue
        if expression in haystack:
            return True

    return False


#: Tokens of an error report that carry no diagnostic meaning on their own.
_GENERIC_ERROR_TOKENS = frozenset({"where", "true", "false", "self", "call", "assertion"})

#: Words the tutor uses for the same concept in the two supported languages.
_ERROR_SYNONYMS: dict[str, tuple[str, ...]] = {
    "assert": ("assert", "aserción", "asercion", "afirmación", "afirmacion"),
    "assertionerror": ("assertionerror", "error de aserción", "error de asercion"),
    "typeerror": ("typeerror", "error de tipo"),
    "valueerror": ("valueerror", "error de valor"),
    "syntaxerror": ("syntaxerror", "error de sintaxis"),
    "nameerror": ("nameerror", "error de nombre"),
    "importerror": ("importerror", "error de importación", "error de importacion"),
    "none": ("none", "nulo", "null"),
}


def error_signals(error: str, student_code: str) -> list[str]:
    """Return the tokens that tie an answer to a concrete failure.

    An answer that asks a question without ever mentioning what actually
    failed is not Socratic in any useful sense: it asks the student to think
    about nothing in particular. The signals are the exception class, the
    name of the function the student wrote and the distinctive tokens of the
    error report itself.
    """
    signals: list[str] = []

    for match in re.finditer(r"\b([A-Z][A-Za-z]*Error)\b", error):
        signals.append(match.group(1))

    for match in re.finditer(r"^\s*def\s+([A-Za-z_]\w*)", student_code, re.MULTILINE):
        signals.append(match.group(1))

    for token in re.findall(r"[A-Za-z_]\w{2,}", error):
        if token.lower() in _GENERIC_ERROR_TOKENS:
            continue
        signals.append(token)

    unique: dict[str, str] = {}
    for signal in signals:
        unique.setdefault(signal.lower(), signal)

    return list(unique.values())


def mentions_error(answer: str, signals: list[str]) -> bool:
    """Whether the answer refers to the concrete failure it is about."""
    haystack = answer.lower()

    for signal in signals:
        variants = _ERROR_SYNONYMS.get(signal.lower(), (signal,))
        if any(variant.lower() in haystack for variant in variants):
            return True

    return False


def percentile(values: list[float], fraction: float) -> float:
    """Return the ``fraction`` percentile of a list of values."""
    if not values:
        return 0.0

    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]

    position = fraction * (len(ordered) - 1)
    lower = math.floor(position)
    upper = math.ceil(position)

    if lower == upper:
        return ordered[lower]

    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


# ── Observations ────────────────────────────────────────────────────────────


@dataclass
class Observation:
    """One measured interaction between a model and the corpus."""

    model: str
    task: str
    exercise_id: str
    topic: str
    difficulty: str
    latency_s: float
    ok: bool
    metrics: dict[str, Any] = field(default_factory=dict)
    detail: str = ""
    raw: dict[str, Any] = field(default_factory=dict)

    def as_row(self) -> dict[str, Any]:
        """Return the flat representation used by the CSV report."""
        row: dict[str, Any] = {
            "model": self.model,
            "task": self.task,
            "exercise_id": self.exercise_id,
            "topic": self.topic,
            "difficulty": self.difficulty,
            "latency_s": round(self.latency_s, 3),
            "ok": self.ok,
            "detail": self.detail,
        }
        row.update(self.metrics)
        return row


# ── Sandbox helpers ─────────────────────────────────────────────────────────


def run_tests(settings: Settings, student_code: str, test_code: str) -> SandboxResult:
    """Run a submission against a test suite inside the Docker sandbox."""
    workdir = settings.sandbox_dir / f"benchmark-{uuid.uuid4().hex}"
    workdir.mkdir(parents=True, exist_ok=True)

    try:
        (workdir / f"{settings.student_module_name}.py").write_text(student_code, encoding="utf-8")
        (workdir / f"{settings.test_module_name}.py").write_text(test_code, encoding="utf-8")
        return run_in_sandbox(workdir, settings)
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


# ── Tasks ───────────────────────────────────────────────────────────────────


def run_oracle(exercise: Exercise, settings: Settings) -> Observation:
    """Validate one corpus entry against the real sandbox.

    A corpus entry is only useful if the reference solution passes the hidden
    tests, the buggy submission fails them and the starter code does not
    solve the exercise.
    """
    solution = run_tests(settings, exercise.solution_code, exercise.test_code)
    failure = run_tests(settings, exercise.failure_code, exercise.test_code)
    starter = run_tests(settings, exercise.starter_code, exercise.test_code)

    metrics = {
        "solution_passes": solution.passed,
        "failure_fails": not failure.passed and not failure.collection_error,
        "starter_fails": not starter.passed,
    }
    ok = all(metrics.values())

    detail = (
        f"solution={'pass' if solution.passed else 'fail'} "
        f"failure={'fail' if metrics['failure_fails'] else 'pass'} "
        f"starter={'fail' if metrics['starter_fails'] else 'pass'}"
    )

    return Observation(
        model="-",
        task=TASK_ORACLE,
        exercise_id=exercise.id,
        topic=exercise.topic,
        difficulty=exercise.difficulty,
        latency_s=0.0,
        ok=ok,
        metrics=metrics,
        detail=detail,
        raw={"error": failure.error, "traceback": failure.traceback},
    )


def run_generate(model: str, exercise: Exercise, settings: Settings) -> Observation:
    """Ask the model to design an exercise and validate what it produced."""
    system_prompt, user_prompt = orchestrator.build_exercise_messages(
        exercise.topic, exercise.difficulty, settings
    )

    started = time.perf_counter()
    try:
        raw_answer = orchestrator.ask_model(
            system_prompt, user_prompt, settings, temperature=0.2, format="json"
        )
    except Exception as exc:  # noqa: BLE001 - a failing model must not stop the run
        latency = time.perf_counter() - started
        return Observation(
            model=model,
            task=TASK_GENERATE,
            exercise_id=exercise.id,
            topic=exercise.topic,
            difficulty=exercise.difficulty,
            latency_s=latency,
            ok=False,
            metrics={"json_valid": False},
            detail=f"raised {type(exc).__name__}: {exc}",
        )

    latency = time.perf_counter() - started
    generated = orchestrator.parse_exercise(raw_answer, settings)

    json_valid = "error" not in generated
    has_all_keys = json_valid and all(
        str(generated.get(key, "")).strip() for key in REQUIRED_EXERCISE_KEYS
    )

    metrics: dict[str, Any] = {
        "json_valid": json_valid,
        "has_all_keys": has_all_keys,
    }

    starter_code = str(generated.get("starter_code", "") or "")
    test_code = str(generated.get("test_code", "") or "")
    instructions = str(generated.get("instructions", "") or "")

    metrics["starter_is_skeleton"] = starter_is_skeleton(starter_code)
    metrics["instructions_leak_tests"] = leaks_test_code(instructions, test_code)

    if json_valid and starter_code and test_code:
        sandbox = run_tests(settings, starter_code, test_code)
        metrics["tests_collect"] = not sandbox.collection_error
        metrics["starter_fails"] = not sandbox.passed
        metrics["sandbox_error"] = sandbox.error
    else:
        metrics["tests_collect"] = False
        metrics["starter_fails"] = False
        metrics["sandbox_error"] = "the model did not return a runnable exercise"

    metrics["well_formed"] = bool(
        metrics["json_valid"]
        and metrics["has_all_keys"]
        and metrics["starter_is_skeleton"]
        and metrics["tests_collect"]
        and metrics["starter_fails"]
        and not metrics["instructions_leak_tests"]
    )

    return Observation(
        model=model,
        task=TASK_GENERATE,
        exercise_id=exercise.id,
        topic=exercise.topic,
        difficulty=exercise.difficulty,
        latency_s=latency,
        ok=bool(metrics["well_formed"]),
        metrics=metrics,
        detail=f"keys={sorted(k for k in generated if k != 'error')}",
        raw={"answer": raw_answer, "exercise": generated},
    )


def _feedback_metrics(
    raw_answer: str,
    guarded_answer: str,
    exercise: Exercise,
    signals: list[str],
) -> dict[str, Any]:
    """Measure the Socratic quality of an answer."""
    metrics: dict[str, Any] = {
        "has_question": has_question(raw_answer),
        "ends_with_question": ends_with_question(raw_answer),
        "leaks_code": has_code_block(raw_answer),
        "leaks_solution": leaks_solution(raw_answer, exercise.solution_code),
        "mentions_error": mentions_error(raw_answer, signals),
        "intervention": guarded_answer.strip() == INTERVENTION_MESSAGE.strip(),
    }
    metrics["trailing_chars"] = len(text_after_question(raw_answer))
    metrics["socratic"] = bool(
        metrics["has_question"]
        and metrics["ends_with_question"]
        and metrics["mentions_error"]
        and not metrics["leaks_code"]
        and not metrics["leaks_solution"]
    )
    return metrics


def run_feedback(
    model: str,
    exercise: Exercise,
    settings: Settings,
    error: str,
    grounded: bool,
) -> Observation:
    """Ask the model for a Socratic hint about a real failure."""
    task = TASK_FEEDBACK_RAG if grounded else TASK_FEEDBACK

    if grounded:
        payload = {"error": error, "traceback": "", "failed_test": exercise.id}
        system_prompt, user_prompt = orchestrator.build_tutor_messages(payload, settings)
    else:
        system_prompt, user_prompt = orchestrator.build_feedback_messages(
            error, exercise.failure_code, settings
        )

    started = time.perf_counter()
    try:
        raw_answer = orchestrator.ask_model(system_prompt, user_prompt, settings, temperature=0.3)
    except Exception as exc:  # noqa: BLE001 - a failing model must not stop the run
        latency = time.perf_counter() - started
        return Observation(
            model=model,
            task=task,
            exercise_id=exercise.id,
            topic=exercise.topic,
            difficulty=exercise.difficulty,
            latency_s=latency,
            ok=False,
            metrics={"has_question": False},
            detail=f"raised {type(exc).__name__}: {exc}",
        )

    latency = time.perf_counter() - started
    guarded_answer = validate_ai_response(raw_answer)
    signals = error_signals(error, exercise.failure_code)
    metrics = _feedback_metrics(raw_answer, guarded_answer, exercise, signals)

    return Observation(
        model=model,
        task=task,
        exercise_id=exercise.id,
        topic=exercise.topic,
        difficulty=exercise.difficulty,
        latency_s=latency,
        ok=bool(metrics["socratic"]),
        metrics=metrics,
        detail=f"{len(raw_answer)} chars",
        raw={
            "answer": raw_answer,
            "guarded": guarded_answer,
            "system_prompt": system_prompt,
            "user_prompt": user_prompt,
            "error": error,
        },
    )


# ── Aggregation ─────────────────────────────────────────────────────────────


def summarise(observations: list[Observation]) -> list[dict[str, Any]]:
    """Aggregate the observations per model and per task."""
    groups: dict[tuple[str, str], list[Observation]] = {}
    for observation in observations:
        groups.setdefault((observation.task, observation.model), []).append(observation)

    summaries = []
    for (task, model), group in sorted(groups.items()):
        latencies = [observation.latency_s for observation in group if observation.latency_s > 0]
        row: dict[str, Any] = {
            "task": task,
            "model": model,
            "n": len(group),
            "ok_rate": round(sum(1 for o in group if o.ok) / len(group), 3),
            "latency_p50": round(percentile(latencies, 0.5), 3),
            "latency_p95": round(percentile(latencies, 0.95), 3),
            "latency_max": round(max(latencies), 3) if latencies else 0.0,
        }
        if latencies:
            row["latency_mean"] = round(statistics.fmean(latencies), 3)

        for name in sorted(
            {key for o in group for key in o.metrics if isinstance(o.metrics[key], bool)}
        ):
            values = [bool(o.metrics[name]) for o in group if name in o.metrics]
            row[name] = round(sum(values) / len(values), 3) if values else 0.0

        summaries.append(row)

    return summaries


def render_summary(
    summaries: list[dict[str, Any]],
    cold_starts: dict[str, float],
    corpus: list[Exercise],
    models: list[str],
) -> str:
    """Render the Markdown summary of a run."""
    lines = [
        "# Benchmark results",
        "",
        f"- Corpus: {len(corpus)} exercises from `benchmarks/exercises`",
        f"- Models: {', '.join(models) if models else 'none'}",
        "",
    ]

    if cold_starts:
        lines += ["## Cold start", "", "| Model | Load time (s) |", "|--------|----------------|"]
        for model, seconds in cold_starts.items():
            lines.append(f"| `{model}` | {seconds:.2f} |")
        lines.append("")

    for task in ALL_TASKS:
        rows = [row for row in summaries if row["task"] == task]
        if not rows:
            continue

        metric_names = sorted(
            {key for row in rows for key in row if key not in {"task", "model", "n", "ok_rate"}}
            - {"latency_p50", "latency_p95", "latency_max", "latency_mean"}
        )

        lines += [
            f"## Task `{task}`",
            "",
            "| Model | n | ok | p50 (s) | p95 (s) | " + " | ".join(metric_names) + " |",
            "|---|---|---|---|---|" + "---|" * len(metric_names),
        ]
        for row in rows:
            cells = " | ".join(f"{row[name]:.2f}" for name in metric_names)
            lines.append(
                f"| `{row['model']}` | {row['n']} | {row['ok_rate']:.2f} | "
                f"{row['latency_p50']:.2f} | {row['latency_p95']:.2f} | {cells} |"
            )
        lines.append("")

    lines += [
        "## Reading the rates",
        "",
        "`ok` is the share of observations that met every requirement of the task.",
        "Every other column is the share of observations where the property held.",
        "The latency columns exclude the cold start of the model.",
        "",
    ]

    return "\n".join(lines)


# ── Reports ─────────────────────────────────────────────────────────────────


def write_reports(
    directory: Path,
    observations: list[Observation],
    summaries: list[dict[str, Any]],
    cold_starts: dict[str, float],
    corpus: list[Exercise],
    models: list[str],
) -> None:
    """Write the CSV, the Markdown summary and the raw answers."""
    directory.mkdir(parents=True, exist_ok=True)

    metric_names = sorted({key for o in observations for key in o.metrics})
    fieldnames = [
        "model",
        "task",
        "exercise_id",
        "topic",
        "difficulty",
        "latency_s",
        "ok",
        "detail",
        *metric_names,
    ]

    with (directory / "results.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for observation in observations:
            writer.writerow(observation.as_row())

    summary = render_summary(summaries, cold_starts, corpus, models)
    (directory / "summary.md").write_text(summary, encoding="utf-8")

    payload = {
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "models": models,
        "corpus": [exercise.id for exercise in corpus],
        "cold_starts": {model: round(seconds, 3) for model, seconds in cold_starts.items()},
        "summaries": summaries,
        "observations": [
            {
                "model": o.model,
                "task": o.task,
                "exercise_id": o.exercise_id,
                "latency_s": round(o.latency_s, 3),
                "ok": o.ok,
                "metrics": o.metrics,
                "detail": o.detail,
                "raw": o.raw,
            }
            for o in observations
        ],
    }
    (directory / "raw.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
    )


# ── Runner ──────────────────────────────────────────────────────────────────


def warm_up_model(model: str, settings: Settings) -> float:
    """Load a model and return how long the load took, in seconds."""
    model_settings = settings.model_copy(update={"ollama_model": model})
    started = time.perf_counter()
    orchestrator.ask_model(
        "You are a helpful assistant.",
        "Reply with the single word: ready",
        model_settings,
        temperature=0.0,
    )
    return time.perf_counter() - started


def run(
    models: list[str],
    tasks: list[str],
    corpus: list[Exercise],
    settings: Settings,
    repeats: int,
) -> tuple[list[Observation], dict[str, float]]:
    """Run every task against every model and return the observations."""
    observations: list[Observation] = []
    cold_starts: dict[str, float] = {}

    if TASK_ORACLE in tasks:
        print("Validating the corpus against the sandbox...")
        for exercise in corpus:
            observation = run_oracle(exercise, settings)
            observations.append(observation)
            mark = "PASS" if observation.ok else "FAIL"
            print(f"  [{mark}] {exercise.id:<24} {observation.detail}")

    measured_tasks = [task for task in tasks if task != TASK_ORACLE]

    if not measured_tasks:
        return observations, cold_starts

    # The sandbox error of every corpus entry is needed by the feedback task.
    errors: dict[str, str] = {}
    if TASK_FEEDBACK in measured_tasks or TASK_FEEDBACK_RAG in measured_tasks:
        for exercise in corpus:
            result = run_tests(settings, exercise.failure_code, exercise.test_code)
            errors[exercise.id] = result.error or result.traceback or "unknown failure"

    for model in models:
        print(f"\nModel: {model}")
        try:
            cold_starts[model] = warm_up_model(model, settings)
            print(f"  loaded in {cold_starts[model]:.2f}s")
        except Exception as exc:  # noqa: BLE001 - a missing model must not stop the run
            print(f"  SKIPPED: the model could not be loaded ({exc})")
            continue

        model_settings = settings.model_copy(update={"ollama_model": model})

        for _repeat in range(repeats):
            for exercise in corpus:
                if TASK_GENERATE in measured_tasks:
                    observation = run_generate(model, exercise, model_settings)
                    observations.append(observation)
                    print(
                        f"  [{'PASS' if observation.ok else 'FAIL'}] "
                        f"{TASK_GENERATE:<14} {exercise.id:<22} "
                        f"{observation.latency_s:6.2f}s  {observation.detail}"
                    )

                if TASK_FEEDBACK in measured_tasks:
                    observation = run_feedback(
                        model, exercise, model_settings, errors[exercise.id], grounded=False
                    )
                    observations.append(observation)
                    print(
                        f"  [{'PASS' if observation.ok else 'FAIL'}] "
                        f"{TASK_FEEDBACK:<14} {exercise.id:<22} "
                        f"{observation.latency_s:6.2f}s  {observation.detail}"
                    )

                if TASK_FEEDBACK_RAG in measured_tasks:
                    observation = run_feedback(
                        model, exercise, model_settings, errors[exercise.id], grounded=True
                    )
                    observations.append(observation)
                    print(
                        f"  [{'PASS' if observation.ok else 'FAIL'}] "
                        f"{TASK_FEEDBACK_RAG:<14} {exercise.id:<22} "
                        f"{observation.latency_s:6.2f}s  {observation.detail}"
                    )

    return observations, cold_starts


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse the command line arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--models",
        default="qwen2.5-coder:7b",
        help="Comma separated list of Ollama models to measure.",
    )
    parser.add_argument(
        "--tasks",
        default=",".join(ALL_TASKS),
        help=f"Comma separated list of tasks: {', '.join(ALL_TASKS)}.",
    )
    parser.add_argument("--corpus", type=Path, default=CORPUS_DIR, help="Directory of the corpus.")
    parser.add_argument("--out", type=Path, default=REPORTS_DIR, help="Directory of the reports.")
    parser.add_argument(
        "--repeats", type=int, default=1, help="Number of times every task is repeated."
    )
    parser.add_argument(
        "--limit", type=int, default=0, help="Only measure the first N exercises of the corpus."
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Entry point of the benchmark script."""
    settings = get_settings()
    configure_logging(settings.log_level)

    args = parse_args(argv)

    models = [model.strip() for model in args.models.split(",") if model.strip()]
    tasks = [task.strip() for task in args.tasks.split(",") if task.strip()]
    unknown = [task for task in tasks if task not in ALL_TASKS]
    if unknown:
        print(f"Unknown task(s): {', '.join(unknown)}")
        return 2

    try:
        corpus = load_corpus(args.corpus)
    except (FileNotFoundError, ValueError) as exc:
        print(f"Could not load the corpus: {exc}")
        return 1

    if args.limit > 0:
        corpus = corpus[: args.limit]

    print(f"Corpus: {len(corpus)} exercise(s) from {args.corpus}")
    print(f"Models: {', '.join(models)}")
    print(f"Tasks: {', '.join(tasks)}\n")

    observations, cold_starts = run(models, tasks, corpus, settings, args.repeats)

    summaries = summarise(observations)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    directory = args.out / stamp
    write_reports(directory, observations, summaries, cold_starts, corpus, models)

    print(f"\n{'=' * 72}")
    for row in summaries:
        print(
            f"{row['task']:<14} {row['model']:<22} n={row['n']:<3} "
            f"ok={row['ok_rate']:.2f} p50={row['latency_p50']:.2f}s p95={row['latency_p95']:.2f}s"
        )
    print(f"\nreports written to {directory}")

    failed = [observation for observation in observations if not observation.ok]
    if failed:
        print(f"\n{len(failed)} observation(s) did not meet the requirements:")
        for observation in failed[:20]:
            print(
                f"  {observation.task} {observation.model} {observation.exercise_id}: {observation.detail}"
            )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
