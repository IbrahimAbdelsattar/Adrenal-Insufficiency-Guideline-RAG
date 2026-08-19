"""Application logging configuration.

One place decides how every backend log line looks, what level it is emitted
at, and how it is correlated back to a request. Nothing else in the codebase
calls ``logging.basicConfig``.

Two formats are supported (``LOG_FORMAT``):

    text  human-readable, for local development and `uvicorn --reload`
    json  one JSON object per line, for log aggregators in deployment

Every record carries a ``request_id`` taken from a ContextVar, so retrieval,
generation, and HTTP access lines from the same call can be grepped together.
"""

from __future__ import annotations

import json
import logging
import sys
import uuid
from contextvars import ContextVar, Token
from typing import Any

from backend.app.config import Settings, get_settings

# Correlation id for the in-flight request. "-" outside of a request (startup,
# CLI, background pre-warm) so the field is never missing from a log line.
_request_id: ContextVar[str] = ContextVar("request_id", default="-")

_CONFIGURED = False

# Attributes LogRecord always carries; anything else was passed via `extra=`
# and is what we actually want to surface as structured fields.
_RESERVED_RECORD_ATTRS = frozenset(
    {
        "args",
        "asctime",
        "created",
        "exc_info",
        "exc_text",
        "filename",
        "funcName",
        "levelname",
        "levelno",
        "lineno",
        "message",
        "module",
        "msecs",
        "msg",
        "name",
        "pathname",
        "process",
        "processName",
        "relativeCreated",
        "stack_info",
        "taskName",
        "thread",
        "threadName",
        "request_id",
    }
)

# Third-party loggers that are far too chatty at DEBUG/INFO and would bury the
# RAG trace lines this module exists to make readable.
_NOISY_LOGGERS = {
    "httpx": logging.WARNING,
    "httpcore": logging.WARNING,
    "urllib3": logging.WARNING,
    "chromadb": logging.WARNING,
    "chromadb.telemetry": logging.ERROR,
    "sentence_transformers": logging.WARNING,
    "SentenceTransformer": logging.WARNING,
    "transformers": logging.WARNING,
    "torch": logging.WARNING,
    "filelock": logging.WARNING,
    "asyncio": logging.WARNING,
}


def get_request_id() -> str:
    """Correlation id of the in-flight request, or "-" outside one."""
    return _request_id.get()


def set_request_id(value: str | None = None) -> Token[str]:
    """Bind a correlation id to this context. Returns a reset token."""
    return _request_id.set(value or uuid.uuid4().hex[:12])


def reset_request_id(token: Token[str]) -> None:
    _request_id.reset(token)


class RequestIdFilter(logging.Filter):
    """Stamps every record with the current request id."""

    def filter(self, record: logging.LogRecord) -> bool:
        if not hasattr(record, "request_id"):
            record.request_id = get_request_id()
        return True


class JsonFormatter(logging.Formatter):
    """One JSON object per line, including any `extra=` fields."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "request_id": getattr(record, "request_id", "-"),
            "message": record.getMessage(),
        }

        for key, value in record.__dict__.items():
            if key in _RESERVED_RECORD_ATTRS or key.startswith("_"):
                continue
            payload[key] = _jsonable(value)

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        if record.stack_info:
            payload["stack"] = self.formatStack(record.stack_info)

        return json.dumps(payload, ensure_ascii=False, default=str)


class TextFormatter(logging.Formatter):
    """Human-readable line with the request id and any structured extras."""

    default_fmt = "%(asctime)s %(levelname)-7s [%(request_id)s] %(name)s: %(message)s"

    def __init__(self) -> None:
        super().__init__(fmt=self.default_fmt, datefmt="%H:%M:%S")

    def format(self, record: logging.LogRecord) -> str:
        base = super().format(record)
        extras = {
            key: value
            for key, value in record.__dict__.items()
            if key not in _RESERVED_RECORD_ATTRS and not key.startswith("_")
        }
        if extras:
            rendered = " ".join(f"{k}={_render(v)}" for k, v in extras.items())
            base = f"{base} | {rendered}"
        return base


def _render(value: Any) -> str:
    if isinstance(value, float):
        return f"{value:.3f}".rstrip("0").rstrip(".")
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, default=str)
    text = str(value)
    return f'"{text}"' if " " in text else text


def _jsonable(value: Any) -> Any:
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    return str(value)


def configure_logging(settings: Settings | None = None, force: bool = False) -> None:
    """Install the application's handler on the root logger.

    Idempotent: importing the app twice (uvicorn reload, tests) must not stack
    duplicate handlers and print every line twice.
    """
    global _CONFIGURED
    if _CONFIGURED and not force:
        return

    settings = settings or get_settings()
    level = logging.getLevelName(settings.log_level.strip().upper())
    if not isinstance(level, int):
        level = logging.INFO

    formatter: logging.Formatter
    if settings.log_format.strip().lower() == "json":
        formatter = JsonFormatter()
    else:
        formatter = TextFormatter()

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)
    handler.addFilter(RequestIdFilter())
    handler.set_name("eva-app")

    root = logging.getLogger()
    for existing in list(root.handlers):
        if existing.get_name() == "eva-app":
            root.removeHandler(existing)
    root.addHandler(handler)
    root.setLevel(level)

    # Uvicorn installs its own handlers; let ours own the output instead of
    # printing each access line twice in two different formats.
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        uvicorn_logger = logging.getLogger(name)
        uvicorn_logger.handlers.clear()
        uvicorn_logger.propagate = True

    for name, noisy_level in _NOISY_LOGGERS.items():
        logging.getLogger(name).setLevel(max(noisy_level, level))

    # The app's own loggers always honour LOG_LEVEL even if root is raised.
    logging.getLogger("backend").setLevel(level)

    _CONFIGURED = True
    logging.getLogger(__name__).info(
        "Logging configured",
        extra={"log_level": logging.getLevelName(level), "log_format": settings.log_format},
    )
