"""Application settings loaded from environment variables and an optional `.env` file.

Every tunable of the project lives here so that nothing is hardcoded in the
business logic. Values are read from the process environment first and fall
back to the `.env` file, then to the defaults declared below.
"""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# Repository root — used to resolve relative paths regardless of the working directory.
BASE_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """Runtime configuration for the tutoring engine."""

    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ── Application ──────────────────────────────────────────────────────
    app_name: str = "Offline AI Tutor Engine"
    version: str = "1.2.0"
    log_level: str = "INFO"
    #: Language the tutor speaks to the students: ``es`` | ``en``.
    tutor_locale: str = "es"

    # ── Ollama (local LLM) ───────────────────────────────────────────────
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "qwen2.5-coder:7b"
    ollama_timeout_seconds: float = 120.0
    #: Context window requested for every generation. The KV cache of a large
    #: context does not fit in a modest GPU and spills into system RAM, which
    #: turns every request into a slow one. The value is pinned here instead
    #: of being inherited from the Ollama server configuration.
    ollama_context_length: int = 8192
    #: How long the model stays in memory after a request. The Ollama default
    #: is five minutes, which forces a cold start in the middle of a session.
    ollama_keep_alive: str = "30m"

    # ── ChromaDB (vector store) ─────────────────────────────────────────
    chroma_dir: Path = BASE_DIR / "data" / "chroma"
    chroma_collection: str = "material_clase"

    # ── SQLite (gating & history) ───────────────────────────────────────
    sqlite_path: Path = BASE_DIR / "data" / "tutor.db"

    # ── Docker sandbox ──────────────────────────────────────────────────
    sandbox_dir: Path = BASE_DIR / "data" / "sandbox"
    sandbox_image: str = "sandbox-evaluador"
    sandbox_memory: str = "256m"
    sandbox_cpus: str = "0.5"
    sandbox_timeout_seconds: int = 60

    # ── Generated module names (shared between the LLM prompt and the sandbox) ──
    student_module_name: str = "exercise_student"
    test_module_name: str = "test_exercise"

    # ── Documentation ingestion ──────────────────────────────────────────
    docs_source_dir: Path = BASE_DIR / "data" / "docs-source"

    # ── Limits ───────────────────────────────────────────────────────────
    max_upload_bytes: int = 100_000
    rate_limit_requests: int = 10
    rate_limit_window_seconds: int = 60
    max_student_id_length: int = 100
    max_topic_length: int = 200
    max_query_length: int = 500

    # ── Derived paths ────────────────────────────────────────────────────
    @property
    def ollama_chat_url(self) -> str:
        """Full URL of the Ollama chat endpoint."""
        return f"{self.ollama_base_url.rstrip('/')}/api/chat"

    @property
    def sandbox_tests_dir(self) -> Path:
        """Directory holding the generated test suite of each student."""
        return self.sandbox_dir / "tests"

    @property
    def frontend_dir(self) -> Path:
        """Directory holding the static frontend assets."""
        return BASE_DIR / "frontend"

    @property
    def resources_dir(self) -> Path:
        """Directory holding versioned learning resources."""
        return BASE_DIR / "resources"

    def ensure_directories(self) -> None:
        """Create every runtime directory the application expects to exist."""
        for directory in (
            self.chroma_dir,
            self.sqlite_path.parent,
            self.sandbox_dir,
            self.sandbox_tests_dir,
        ):
            directory.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    """Return the cached application settings."""
    return Settings()
