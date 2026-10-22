"""Central logging configuration.

Replaces the ``print`` statements of the original prototype with a single
structured logger shared by every module.
"""

import logging
import sys

_CONFIGURED = False

_LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)-30s | %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def configure_logging(level: str = "INFO") -> None:
    """Install the root log handler. Safe to call more than once."""
    global _CONFIGURED
    if _CONFIGURED:
        return

    handler = logging.StreamHandler(stream=sys.stdout)
    handler.setFormatter(logging.Formatter(fmt=_LOG_FORMAT, datefmt=_DATE_FORMAT))

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(getattr(logging, level.upper(), logging.INFO))

    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    """Return a namespaced logger for the given module."""
    return logging.getLogger(name)
