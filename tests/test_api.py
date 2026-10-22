"""API level tests: routing, validation, status codes and the rate limiter."""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.api.dependencies import get_rate_limiter
from app.core.config import get_settings
from app.main import app


@pytest.fixture
def client() -> Iterator[TestClient]:
    """Return a test client with the application lifespan running."""
    with TestClient(app) as test_client:
        yield test_client


class TestSystem:
    """Liveness probe and frontend delivery."""

    def test_health_reports_the_degraded_state(self, client: TestClient) -> None:
        response = client.get("/health")

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "degraded"
        assert body["vector_store"] is False

    def test_health_reports_the_model_in_use(self, client: TestClient) -> None:
        body = client.get("/health").json()

        assert body["llm"]
        assert body["version"]

    def test_index_serves_the_frontend(self, client: TestClient) -> None:
        response = client.get("/")

        assert response.status_code == 200
        assert "<!DOCTYPE html>" in response.text

    def test_static_assets_are_served(self, client: TestClient) -> None:
        assert client.get("/static/styles.css").status_code == 200
        assert client.get("/static/app.js").status_code == 200


class TestLearningRoutes:
    """The documentation explorer degrades gracefully without a vector store."""

    def test_categories_are_empty_without_a_vector_store(self, client: TestClient) -> None:
        body = client.get("/learning/categories").json()

        assert body["status"] == "success"
        assert body["categorias"] == []

    def test_topics_require_a_category(self, client: TestClient) -> None:
        assert client.get("/learning/topics").status_code == 422

    def test_topics_are_empty_without_a_vector_store(self, client: TestClient) -> None:
        body = client.get("/learning/topics", params={"categoria": "library"}).json()

        assert body["status"] == "success"
        assert body["temas"] == []

    def test_content_requires_a_topic(self, client: TestClient) -> None:
        assert client.get("/learning/content").status_code == 422

    def test_search_requires_a_query(self, client: TestClient) -> None:
        assert client.get("/learning/search").status_code == 422

    def test_stats_report_the_missing_vector_store(self, client: TestClient) -> None:
        body = client.get("/learning/stats").json()

        assert body["status"] == "success"
        assert body["conectado"] is False
        assert body["total_chunks"] == 0


class TestEvaluationRoutes:
    """Every untrusted field is validated before it reaches the sandbox."""

    def test_student_id_cannot_escape_the_project(self, client: TestClient) -> None:
        response = client.post(
            "/evaluate",
            data={"student_id": "../../etc/passwd", "exercise_id": "default"},
            files={"file": ("solution.py", b"print(1)", "text/x-python")},
        )

        assert response.status_code == 400

    def test_a_file_is_required(self, client: TestClient) -> None:
        response = client.post(
            "/evaluate",
            data={"student_id": "student_001", "exercise_id": "default"},
        )

        assert response.status_code == 422

    def test_unknown_exercise_is_reported_as_an_error(self, client: TestClient) -> None:
        response = client.post(
            "/evaluate",
            data={"student_id": "student_001", "exercise_id": "does-not-exist"},
            files={"file": ("solution.py", b"print(1)", "text/x-python")},
        )

        assert response.status_code == 200
        assert response.json()["status"] == "error"

    def test_oversized_uploads_are_rejected(self, client: TestClient) -> None:
        response = client.post(
            "/evaluate",
            data={"student_id": "student_001", "exercise_id": "default"},
            files={"file": ("solution.py", b"x" * 200_000, "text/x-python")},
        )

        assert response.status_code == 413


class TestGenerationRoutes:
    """Exercise generation validates its inputs before calling the model."""

    def test_empty_topic_is_rejected(self, client: TestClient) -> None:
        response = client.post(
            "/generate",
            data={"student_id": "student_001", "topic": ""},
        )

        assert response.status_code == 422

    def test_blank_topic_is_rejected(self, client: TestClient) -> None:
        response = client.post(
            "/generate",
            data={"student_id": "student_001", "topic": "   "},
        )

        assert response.status_code == 400

    def test_invalid_student_id_is_rejected(self, client: TestClient) -> None:
        response = client.post(
            "/generate",
            data={"student_id": "student 001", "topic": "Lists"},
        )

        assert response.status_code == 400


class TestBuiltInExercise:
    """The built-in exercise lets a student try the loop immediately."""

    def test_default_exercise_is_exposed(self, client: TestClient) -> None:
        body = client.get("/exercises/default").json()

        assert body["status"] == "success"
        assert body["data"]["instructions"]
        assert body["data"]["starter_code"]

    def test_the_hidden_test_suite_is_never_exposed(self, client: TestClient) -> None:
        body = client.get("/exercises/default").json()

        assert "test_exercise" not in body["data"]["starter_code"]


class TestRateLimiting:
    """The per-IP budget protects the model from unbounded usage."""

    def test_the_budget_is_enforced(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("RATE_LIMIT_REQUESTS", "2")
        monkeypatch.setenv("MAX_UPLOAD_BYTES", "5")
        get_settings.cache_clear()
        get_rate_limiter.cache_clear()

        payload = {"student_id": "student_001", "exercise_id": "default"}
        files = {"file": ("solution.py", b"print(1)", "text/x-python")}

        assert client.post("/evaluate", data=payload, files=files).status_code == 413
        assert client.post("/evaluate", data=payload, files=files).status_code == 413

        blocked = client.post("/evaluate", data=payload, files=files)

        assert blocked.status_code == 429
        assert "Retry-After" in blocked.headers

    def test_invalid_payloads_do_not_consume_the_budget(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("RATE_LIMIT_REQUESTS", "1")
        monkeypatch.setenv("MAX_UPLOAD_BYTES", "5")
        get_settings.cache_clear()
        get_rate_limiter.cache_clear()

        for _ in range(3):
            response = client.post(
                "/evaluate",
                data={"student_id": "../../etc/passwd", "exercise_id": "default"},
                files={"file": ("solution.py", b"print(1)", "text/x-python")},
            )
            assert response.status_code == 400

        payload = {"student_id": "student_001", "exercise_id": "default"}
        files = {"file": ("solution.py", b"print(1)", "text/x-python")}

        assert client.post("/evaluate", data=payload, files=files).status_code == 413
