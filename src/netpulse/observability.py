"""Structured logging + FastAPI request middleware.

What you get:

- ``configure_logging(json=..., level=...)`` configures the root logger
  once at process startup. JSON mode emits one record per line as
  ``{"ts": ..., "level": ..., "logger": ..., "msg": ..., **extra}``,
  suitable for Fly.io / Cloud Logging ingest. Text mode falls back to
  a human-readable formatter.
- ``RequestLoggingMiddleware`` logs every HTTP request with timing,
  status, and request id; if a ``request_duration_seconds`` histogram
  is wired in, it observes the elapsed time per endpoint so an
  operator can graph p50/p95/p99 in Grafana.

Both pieces are deliberately stdlib-only so they cost nothing at
import and run cleanly on Fly.io's slim image.
"""

from __future__ import annotations

import json
import logging
import sys
import time
import uuid
from collections.abc import Awaitable, Callable
from typing import Any, Literal

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

from netpulse.api.metrics import _Histogram

LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]


class JsonFormatter(logging.Formatter):
    """One JSON object per record, line-delimited.

    Includes any ``extra`` fields passed to the logger -- the
    middleware pushes ``request_id``, ``path``, ``status``, ``duration_ms``
    so an operator can grep / filter on them in production logs.
    """

    # Logging record attributes that are not user-supplied "extras".
    _RESERVED = {
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
        "thread",
        "threadName",
        "taskName",
    }

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": _iso_z(record.created),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        for k, v in record.__dict__.items():
            if k in self._RESERVED or k.startswith("_"):
                continue
            payload[k] = v
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def _iso_z(epoch_seconds: float) -> str:
    """ISO-8601 with a Z suffix, millisecond precision."""
    from datetime import UTC, datetime

    stamp = datetime.fromtimestamp(epoch_seconds, tz=UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    return stamp[:-4] + "Z"


def configure_logging(json_mode: bool = True, level: LogLevel = "INFO") -> None:
    """Idempotent root-logger setup.

    Safe to call multiple times -- existing handlers on the root logger
    are removed first so re-configuration (e.g. in tests) doesn't pile
    up duplicate output.
    """
    root = logging.getLogger()
    for h in list(root.handlers):
        root.removeHandler(h)

    handler = logging.StreamHandler(stream=sys.stdout)
    if json_mode:
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(
            logging.Formatter(
                fmt="%(asctime)s %(levelname)-8s %(name)s :: %(message)s",
                datefmt="%Y-%m-%dT%H:%M:%S",
            )
        )
    root.addHandler(handler)
    root.setLevel(level)

    # Quiet uvicorn's noisy access log -- our middleware is the canonical
    # source. Both 'uvicorn.access' and 'uvicorn.error' would otherwise
    # duplicate output through their default handlers.
    for noisy in ("uvicorn.access",):
        logging.getLogger(noisy).handlers = []
        logging.getLogger(noisy).propagate = False


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Log every request with timing + a stable request id.

    If ``duration_histogram`` is supplied, also observes the elapsed
    time per endpoint so p50/p95/p99 latency is graphable in Grafana
    via ``histogram_quantile``.

    Endpoint labels come from the route path (the part the client
    typed), not the URL path with parameters substituted, so the
    histogram cardinality stays low.
    """

    def __init__(
        self,
        app: ASGIApp,
        *,
        logger_name: str = "netpulse.access",
        duration_histogram: _Histogram | None = None,
    ) -> None:
        super().__init__(app)
        self._logger = logging.getLogger(logger_name)
        self._hist = duration_histogram

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        request_id = request.headers.get("x-request-id") or uuid.uuid4().hex[:16]
        start = time.perf_counter()
        status = 500
        try:
            response = await call_next(request)
            status = response.status_code
            response.headers["x-request-id"] = request_id
            return response
        except Exception:
            elapsed = time.perf_counter() - start
            self._logger.exception(
                "request failed",
                extra={
                    "request_id": request_id,
                    "method": request.method,
                    "path": request.url.path,
                    "status": status,
                    "duration_ms": round(elapsed * 1000, 2),
                },
            )
            raise
        finally:
            elapsed = time.perf_counter() - start
            self._logger.info(
                "request",
                extra={
                    "request_id": request_id,
                    "method": request.method,
                    "path": request.url.path,
                    "status": status,
                    "duration_ms": round(elapsed * 1000, 2),
                },
            )
            if self._hist is not None:
                self._hist.observe(elapsed, label_value=request.url.path)
