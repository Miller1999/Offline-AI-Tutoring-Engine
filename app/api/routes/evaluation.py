"""Evaluation routes: exercise generation and sandboxed code evaluation."""

import shutil
import uuid

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile

from app.api.dependencies import get_client_ip, get_rate_limiter
from app.core.config import get_settings
from app.core.logging import get_logger
from app.core.sandbox import ALL_TESTS_PASSED_MESSAGE
from app.core.security import (
    RateLimitError,
    ValidationError,
    sanitize_for_prompt,
    validate_length,
    validate_student_id,
)
from app.schemas.responses import EvaluationResponse, ExerciseData, ExerciseResponse
from app.services import database, exercises, orchestrator
from app.services.database import STATUS_APPROVED, STATUS_FAILED

logger = get_logger(__name__)

router = APIRouter(tags=["evaluation"])

#: Exercise id that selects the dynamically generated exercises.
DYNAMIC_EXERCISE_ID = "dynamic"


def _enforce_rate_limit(request: Request) -> None:
    """Apply the per-IP request budget."""
    limiter = get_rate_limiter()
    try:
        limiter.check(get_client_ip(request))
    except RateLimitError as exc:
        raise HTTPException(
            status_code=429,
            detail="Too many requests. Please try again in a minute.",
            headers={"Retry-After": str(exc.retry_after)},
        ) from exc


def _resolve_difficulty(approved: int) -> str:
    """Map the number of approved exercises to a difficulty level."""
    if approved >= 3:
        return "advanced"
    if approved >= 1:
        return "intermediate"
    return "beginner"


@router.post("/evaluate", response_model=EvaluationResponse, summary="Evaluate student code")
async def evaluate(
    request: Request,
    student_id: str = Form(...),
    exercise_id: str = Form(...),
    file: UploadFile = File(...),  # noqa: B008 - FastAPI dependency declaration
) -> EvaluationResponse:
    """Evaluate a submitted solution inside the Docker sandbox.

    Every request runs in its own isolated working directory, so concurrent
    evaluations of different students can never interfere with each other.
    """
    settings = get_settings()

    # Validate before rate limiting so an invalid id cannot pollute the limiter.
    try:
        student_id = validate_student_id(student_id, settings.max_student_id_length)
    except ValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    _enforce_rate_limit(request)

    try:
        exercise_id = validate_length(exercise_id, 100, "exercise_id")
    except ValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    uploaded = await file.read()
    if len(uploaded) > settings.max_upload_bytes:
        raise HTTPException(status_code=413, detail="The uploaded file is too large.")

    student_code = uploaded.decode("utf-8", errors="replace")
    is_dynamic = exercise_id.strip().lower() == DYNAMIC_EXERCISE_ID

    if is_dynamic:
        test_code = orchestrator.get_generated_test(student_id)
        if test_code is None:
            return EvaluationResponse(
                status="error",
                message="No active dynamic exercise was found for this student.",
            )
    else:
        if exercise_id.strip().lower() != exercises.DEFAULT_EXERCISE_ID:
            return EvaluationResponse(
                status="error",
                message=f"Unknown exercise ID '{exercise_id}'.",
            )
        test_code = exercises.get_default_test_code()
        if test_code is None:
            return EvaluationResponse(
                status="error",
                message=f"Unknown exercise ID '{exercise_id}'.",
            )

    logger.info(
        "Evaluating submission of student '%s' for exercise '%s'",
        student_id,
        exercise_id,
    )

    workdir = settings.sandbox_dir / uuid.uuid4().hex
    workdir.mkdir(parents=True, exist_ok=True)

    try:
        (workdir / f"{settings.student_module_name}.py").write_text(student_code, encoding="utf-8")
        (workdir / f"{settings.test_module_name}.py").write_text(test_code, encoding="utf-8")

        result = orchestrator.evaluate_code(workdir, settings)
    finally:
        shutil.rmtree(workdir, ignore_errors=True)

    topic = database.get_student_topic(student_id)
    attempt_number = database.get_attempt_count(student_id, exercise_id) + 1

    if result.infrastructure_error is not None:
        logger.error("Sandbox infrastructure error: %s", result.infrastructure_error)
        return EvaluationResponse(
            status="error",
            message=f"Evaluation infrastructure error: {result.infrastructure_error}",
        )

    if result.passed:
        database.record_history(student_id, topic, exercise_id, STATUS_APPROVED, attempt_number)
        database.record_attempt(student_id, exercise_id, STATUS_APPROVED)
        return EvaluationResponse(status="success", message=ALL_TESTS_PASSED_MESSAGE)

    database.record_history(student_id, topic, exercise_id, STATUS_FAILED, attempt_number)
    database.record_attempt(student_id, exercise_id, STATUS_FAILED)

    payload = {
        "error": result.error,
        "traceback": result.traceback,
        "failed_test": result.failed_test,
    }

    if is_dynamic:
        feedback = orchestrator.generate_dynamic_feedback(result.error or "", student_code)
    else:
        feedback = orchestrator.get_socratic_hint(payload)

    return EvaluationResponse(
        status="failure",
        tutor_feedback=feedback,
        failed_test=result.failed_test,
    )


@router.post("/generate", response_model=ExerciseResponse, summary="Generate an exercise")
async def generate(
    request: Request,
    topic: str = Form(...),
    student_id: str = Form(...),
) -> ExerciseResponse:
    """Generate a dynamic exercise with a hidden test suite.

    The test suite never leaves the server; only the instructions, the example
    and the starter code are returned to the student.
    """
    settings = get_settings()

    try:
        student_id = validate_student_id(student_id, settings.max_student_id_length)
    except ValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    _enforce_rate_limit(request)

    try:
        topic = validate_length(topic, settings.max_topic_length, "topic")
    except ValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    sanitized_topic = sanitize_for_prompt(topic, max_length=settings.max_topic_length)

    approved = database.count_approved_by_topic(student_id, sanitized_topic)
    difficulty = _resolve_difficulty(approved)
    logger.info(
        "Student '%s' approved %s exercise(s) in '%s' -> difficulty '%s'",
        student_id,
        approved,
        sanitized_topic,
        difficulty,
    )

    result = orchestrator.generate_exercise(sanitized_topic, difficulty)
    if "error" in result:
        return ExerciseResponse(status="error", message=result["error"])

    orchestrator.save_generated_test(student_id, result.get("test_code", "") or "")
    database.set_student_topic(student_id, sanitized_topic)

    return ExerciseResponse(
        status="success",
        data=ExerciseData(
            instructions=result.get("instructions", ""),
            expected_example=result.get("expected_example", ""),
            starter_code=result.get("starter_code", ""),
        ),
    )


@router.get("/exercises/default", response_model=ExerciseResponse, summary="Built-in exercise")
def default_exercise() -> ExerciseResponse:
    """Return the built-in exercise so a student can try the loop immediately."""
    exercise = exercises.load_default_exercise()
    if exercise is None:
        return ExerciseResponse(status="error", message="No built-in exercise available.")

    return ExerciseResponse(
        status="success",
        data=ExerciseData(
            instructions=exercise["instructions"],
            expected_example=exercise["expected_example"],
            starter_code=exercise["starter_code"],
        ),
    )
