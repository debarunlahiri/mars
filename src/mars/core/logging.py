"""Logging with a per-run correlation id (plain text or JSON lines)."""

from __future__ import annotations

import json
import logging
import sys
from contextvars import ContextVar

run_id_var: ContextVar[str] = ContextVar("mars_run_id", default="-")


class _RunIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.run_id = run_id_var.get()
        return True


class _JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "logger": record.name,
            "run_id": getattr(record, "run_id", "-"),
            "msg": record.getMessage(),
        }
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload)


def setup_logging(level: str = "INFO", json_logs: bool = False) -> None:
    """Idempotent: safe to call from the CLI, the API lifespan and tests."""
    root = logging.getLogger("mars")
    root.setLevel(level.upper())
    root.propagate = False
    if any(getattr(h, "_mars", False) for h in root.handlers):
        return
    handler = logging.StreamHandler(sys.stderr)
    handler._mars = True  # type: ignore[attr-defined]
    handler.addFilter(_RunIdFilter())
    handler.setFormatter(
        _JsonFormatter()
        if json_logs
        else logging.Formatter("%(asctime)s %(levelname)-7s [%(run_id)s] %(name)s: %(message)s")
    )
    root.addHandler(handler)
    # Third-party chatter at INFO would drown out the run log.
    for noisy in ("httpx", "httpcore", "trafilatura", "primp", "ddgs"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(f"mars.{name}")
