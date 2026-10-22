"""Built-in exercises shipped with the platform.

The platform always offers one static exercise so that a student can try the
evaluation loop without first asking the model to generate one.
"""

import json
from typing import Any

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)

DEFAULT_EXERCISE_ID = "default"


def _default_dir():
    """Return the directory holding the built-in exercise."""
    return get_settings().resources_dir / "exercises" / DEFAULT_EXERCISE_ID


def get_default_test_code() -> str | None:
    """Return the hidden test suite of the built-in exercise."""
    path = _default_dir() / "test_exercise.py"
    if not path.exists():
        logger.warning("Built-in exercise test suite not found at %s", path)
        return None
    return path.read_text(encoding="utf-8")


def load_default_exercise() -> dict[str, Any] | None:
    """Return the student-facing description of the built-in exercise."""
    directory = _default_dir()
    metadata_path = directory / "metadata.json"
    starter_path = directory / "starter.py"

    if not metadata_path.exists() or not starter_path.exists():
        logger.warning("Built-in exercise resources are incomplete in %s", directory)
        return None

    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Could not read the built-in exercise metadata: %s", exc)
        return None

    return {
        "instructions": metadata.get("instructions", ""),
        "expected_example": metadata.get("expected_example", ""),
        "starter_code": starter_path.read_text(encoding="utf-8"),
    }
