"""Security primitives: prompt sanitisation, output validation and rate limiting.

This module is the defensive core of the platform. The regular expressions are
carried over verbatim from the original prototype — they are battle-tested and
form the main mitigation against prompt injection, so they are not rewritten.
"""

import re
import threading
import time
from collections import deque
from typing import Final

# ── Delimiters used to isolate user content from the system prompt ─────────
DELIMITER_START: Final[str] = "===###USR_CONTENT_START###==="
DELIMITER_END: Final[str] = "===###USR_CONTENT_END###==="

# ── Maximum lengths accepted for each kind of untrusted input ─────────────
MAX_INPUT_LENGTH: Final[int] = 5000
MAX_TOPIC_LENGTH: Final[int] = 200
MAX_ERROR_LENGTH: Final[int] = 2000

#: Message returned to the student when the tutor tries to leak a solution.
INTERVENTION_MESSAGE: Final[str] = (
    "⚠️ **SYSTEM INTERVENTION**: The tutor attempted to provide a direct solution. "
    "Remember that you must discover the answer on your own. Review the notes and try again."
)

# Patterns that signal an attempt to override the system prompt.
_INJECTION_PATTERNS: Final[tuple[str, ...]] = (
    # Spanish
    r"(?i)ignora\s+todas?\s+las\s+instrucciones(?:\s+anteriores)?.*",
    r"(?i)olvida\s+todas?\s+las\s+instrucciones(?:\s+anteriores)?.*",
    r"(?i)nuevas?\s+instrucciones:?.*",
    r"(?i)eres\s+ahora.*",
    r"(?i)a\s+partir\s+de\s+ahora.*",
    r"(?i)prompt\s+del\s+sistema.*",
    r"(?i)system\s+prompt.*",
    r"(?i)instrucciones?\s+del\s+sistema.*",
    r"(?i)prioridad\s+(alta|mayor|superior).*",
    r"(?i)anula\s+las?\s+instrucciones.*",
    r"(?i)sobreescribe\s+las?\s+instrucciones.*",
    r"(?i)desobedece\s+las?\s+instrucciones.*",
    # English
    r"(?i)ignore\s+all\s+(previous|prior|above)\s+instructions.*",
    r"(?i)forget\s+all\s+(previous|prior|above)\s+instructions.*",
    r"(?i)new\s+instructions?:.*",
    r"(?i)you\s+are\s+now.*",
    r"(?i)from\s+now\s+on.*",
    r"(?i)disregard\s+(all\s+)?(previous|prior|above)\s+instructions.*",
    r"(?i)override\s+(all\s+)?(previous|prior)\s+(instructions|prompts?).*",
    r"(?i)you\s+must\s+now.*",
    r"(?i)act\s+as\s+if.*",
    r"(?i)you\s+are\s+not\s+(a\s+)?(socratic|tutor).*",
)

# Patterns that indicate the model is about to hand over a direct solution.
_BLOCKED_RESPONSE_PATTERNS: Final[tuple[str, ...]] = (
    r"```",  # Markdown code blocks
    r"def\s+\w+\s*\(",  # Python function definitions
    r"class\s+\w+",  # Class definitions
    r"print\s*\(",  # Print statements (direct solutions)
    # A return statement carrying a concrete value. The value has to be a
    # literal or a call: prose such as "what should it return so that the
    # assertion passes?" is a legitimate Socratic question and must survive.
    r"return\s*(?:[\"'\d]|True\b|False\b|None\b|[A-Za-z_]\w*\s*\()",
    # Spanish leaks
    r"soluci[oó]n\s*:",  # "Solución:" headers
    r"respuesta\s*:",  # "Respuesta:" headers
    r"aqu[ií]\s+(est[aá]n?\s+)?(el|la|los|las)\s+(c[oó]digo|soluci[oó]n|respuesta)",
    r"te\s+(voy\s+)?a\s+(dar|decir|mostrar|escribir)\s+(la\s+)?(soluci[oó]n|respuesta|c[oó]digo)",
    r"el\s+siguiente\s+c[oó]digo",
    r"(c[oó]digo|soluci[oó]n)\s+(correct[oa]|complet[oa]|final)",
    # English leaks — the tutor can be configured to speak English, so the
    # guardrails cannot rely on the Spanish wording only.
    r"solution\s*:",
    r"answer\s*:",
    r"here\s+(is|are)\s+the\s+(code|solution|answer)",
    r"(i|we)\s+(will|can|am going to)\s+(give|show|tell)\s+you\s+the\s+(code|solution|answer)",
    r"the\s+(next|following)\s+code",
    r"(code|solution)\s+(correct|complete|final)",
)

#: Characters allowed in a student identifier.
_STUDENT_ID_PATTERN: Final[re.Pattern[str]] = re.compile(r"^[a-zA-Z0-9_\-]+$")


class RateLimitError(Exception):
    """Raised when a client exceeds the configured request budget."""

    def __init__(self, retry_after: int) -> None:
        super().__init__("Too many requests.")
        self.retry_after = retry_after


class ValidationError(ValueError):
    """Raised when a user supplied value fails validation."""


def sanitize_for_prompt(text: str, max_length: int = MAX_TOPIC_LENGTH) -> str:
    """Sanitise untrusted text before it is injected into an LLM prompt.

    1. Truncates to ``max_length`` characters.
    2. Neutralises known instruction-override patterns.
    3. Removes Markdown code fences that could break out of the context.
    4. Removes control characters (newlines and tabs are preserved).
    """
    if not isinstance(text, str):
        return ""

    text = text.strip()[:max_length]

    for pattern in _INJECTION_PATTERNS:
        text = re.sub(pattern, "[INJECTION DETECTED]", text, count=1)

    text = text.replace("```", "")
    text = re.sub(r"[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]", "", text)

    return text.strip()


def validate_ai_response(response: str) -> str:
    """Validate a model answer and replace it with an intervention message if needed.

    Returns the original response when it passes the checks, otherwise a
    system intervention notice.
    """
    if not isinstance(response, str):
        return INTERVENTION_MESSAGE

    for pattern in _BLOCKED_RESPONSE_PATTERNS:
        if re.search(pattern, response, re.IGNORECASE):
            return INTERVENTION_MESSAGE

    return response


def validate_student_id(student_id: str, max_length: int = 100) -> str:
    """Validate and sanitise a student identifier.

    Only alphanumeric characters, hyphens and underscores are accepted. The
    value is validated as-is — it is never silently rewritten — so that a
    path traversal attempt is rejected instead of being turned into a
    different, unexpected identifier.
    """
    if not student_id or not isinstance(student_id, str):
        raise ValidationError("Invalid student ID.")

    student_id = student_id.strip()

    if len(student_id) > max_length:
        raise ValidationError(f"Invalid student ID. Maximum length is {max_length} characters.")

    if not _STUDENT_ID_PATTERN.match(student_id):
        raise ValidationError(
            "Invalid student ID. Only alphanumeric characters, hyphens and underscores are allowed."
        )

    return student_id


def validate_length(text: str, max_length: int, field_name: str = "Field") -> str:
    """Validate that a text field is present and within its maximum length.

    A value made of whitespace only is treated as missing.
    """
    if not text or not isinstance(text, str):
        raise ValidationError(f"Invalid {field_name}.")

    text = text.strip()
    if not text:
        raise ValidationError(f"Invalid {field_name}.")

    return text[:max_length]


class RateLimiter:
    """Sliding-window request limiter keyed by client IP.

    The implementation is thread-safe and bounds its own memory: expired
    buckets are swept periodically and the bucket map is capped.
    """

    def __init__(self, limit: int, window_seconds: int, max_keys: int = 10_000) -> None:
        self._limit = limit
        self._window = window_seconds
        self._max_keys = max_keys
        self._hits: dict[str, deque[float]] = {}
        self._lock = threading.Lock()
        self._operations = 0

    def check(self, key: str) -> None:
        """Register a hit for ``key``.

        Raises:
            RateLimitError: when the client exceeded the request budget.
        """
        now = time.monotonic()

        with self._lock:
            self._operations += 1
            if self._operations % 100 == 0:
                self._sweep(now)

            bucket = self._hits.setdefault(key, deque())
            cutoff = now - self._window
            while bucket and bucket[0] <= cutoff:
                bucket.popleft()

            if len(bucket) >= self._limit:
                retry_after = max(1, int(self._window - (now - bucket[0])) + 1)
                raise RateLimitError(retry_after)

            bucket.append(now)

            if len(self._hits) > self._max_keys:
                self._evict()

    def reset(self) -> None:
        """Drop every recorded hit. Intended for tests."""
        with self._lock:
            self._hits.clear()

    # ── Internals ────────────────────────────────────────────────────────
    def _sweep(self, now: float) -> None:
        """Remove buckets whose window has fully expired."""
        cutoff = now - self._window
        expired = [key for key, bucket in self._hits.items() if not bucket or bucket[-1] <= cutoff]
        for key in expired:
            del self._hits[key]

    def _evict(self) -> None:
        """Drop the oldest buckets once the key map exceeds its cap."""
        overflow = len(self._hits) - self._max_keys
        for key in list(self._hits)[:overflow]:
            del self._hits[key]
