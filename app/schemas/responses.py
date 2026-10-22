"""Pydantic models describing the API responses."""

from typing import Any, Literal

from pydantic import BaseModel, Field

Status = Literal["success", "failure", "error"]


class HealthResponse(BaseModel):
    """Liveness probe payload."""

    status: Literal["healthy", "degraded"] = "healthy"
    version: str
    llm: str = Field(description="Name of the local model the tutor uses")
    vector_store: bool = Field(description="Whether the ChromaDB collection is reachable")
    model_ready: bool = Field(description="Whether the local model is loaded and can answer")


class EvaluationResponse(BaseModel):
    """Result of a code evaluation.

    Exactly one of ``message`` and ``tutor_feedback`` is populated, depending
    on the outcome.
    """

    status: Status
    message: str | None = None
    tutor_feedback: str | None = None
    failed_test: str | None = None


class ExerciseData(BaseModel):
    """The parts of a generated exercise that are safe to show to a student.

    The hidden test suite is deliberately absent from this model.
    """

    instructions: str
    expected_example: str
    starter_code: str


class ExerciseResponse(BaseModel):
    """Result of an exercise generation request."""

    status: Status
    message: str | None = None
    data: ExerciseData | None = None


class CategoriesResponse(BaseModel):
    """List of documentation categories."""

    status: Status
    categorias: list[dict[str, Any]] = []


class TopicsResponse(BaseModel):
    """List of topics inside a category."""

    status: Status
    temas: list[dict[str, Any]] = []


class ContentResponse(BaseModel):
    """Documentation chunks belonging to a topic."""

    status: Status
    contenido: list[dict[str, Any]] = []


class SearchResponse(BaseModel):
    """Semantic search results."""

    status: Status
    resultados: list[dict[str, Any]] = []


class StatsResponse(BaseModel):
    """Knowledge base statistics."""

    status: Status
    total_chunks: int = 0
    total_categorias: int = 0
    conectado: bool = False
    categorias: list[dict[str, Any]] = []
