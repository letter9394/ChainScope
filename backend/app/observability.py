from __future__ import annotations

import json
import logging
import sys
from datetime import UTC, datetime
from threading import Lock
from time import monotonic
from typing import Any


PROCESS_STARTED_MONOTONIC = monotonic()


def utc_iso() -> str:
    return datetime.now(UTC).isoformat()


class JsonFormatter(logging.Formatter):
    """Render-friendly structured logs without adding a logging dependency."""

    _standard_fields = set(logging.makeLogRecord({}).__dict__) | {
        "message",
        "asctime",
    }

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "event": record.getMessage(),
        }
        for key, value in record.__dict__.items():
            if key not in self._standard_fields and not key.startswith("_"):
                payload[key] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, default=str)


def configure_logging(*, level: str = "INFO", json_logs: bool = False) -> None:
    logger = logging.getLogger("chainscope")
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    logger.propagate = False

    handler = next(
        (item for item in logger.handlers if getattr(item, "_chainscope_handler", False)),
        None,
    )
    if handler is None:
        handler = logging.StreamHandler(sys.stdout)
        handler._chainscope_handler = True  # type: ignore[attr-defined]
        logger.addHandler(handler)
    formatter: logging.Formatter = (
        JsonFormatter()
        if json_logs
        else logging.Formatter(
            "%(asctime)s %(levelname)s %(name)s %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%S%z",
        )
    )
    handler.setFormatter(formatter)
    handler.setLevel(logger.level)


class SchedulerRuntime:
    """Process-local scheduler telemetry exposed by the health endpoint."""

    def __init__(self) -> None:
        self._lock = Lock()
        self.reset()

    def reset(self) -> None:
        with self._lock:
            self.running = False
            self.last_started_at: str | None = None
            self.last_completed_at: str | None = None
            self.last_error_at: str | None = None
            self.last_error_type: str | None = None
            self.last_duration_ms: float | None = None
            self.last_evaluated_users = 0
            self.last_triggered_events = 0
            self.last_failed_users = 0
            self._last_cycle_status: str | None = None
            self._cycle_started_monotonic: float | None = None

    def start_cycle(self) -> None:
        with self._lock:
            self.running = True
            self.last_started_at = utc_iso()
            self._cycle_started_monotonic = monotonic()

    def complete_cycle(
        self,
        *,
        evaluated_users: int,
        triggered_events: int,
        failed_users: int,
    ) -> None:
        with self._lock:
            self.running = False
            self.last_completed_at = utc_iso()
            self.last_duration_ms = self._duration_ms()
            self.last_evaluated_users = evaluated_users
            self.last_triggered_events = triggered_events
            self.last_failed_users = failed_users
            if failed_users == 0:
                self._last_cycle_status = "ok"
                self.last_error_at = None
                self.last_error_type = None
            else:
                self._last_cycle_status = "degraded"
                self.last_error_at = utc_iso()
                self.last_error_type = "UserEvaluationError"

    def fail_cycle(self, error: BaseException) -> None:
        with self._lock:
            self.running = False
            self.last_error_at = utc_iso()
            self.last_error_type = type(error).__name__
            self.last_duration_ms = self._duration_ms()
            self._last_cycle_status = "error"

    def snapshot(self, *, enabled: bool, interval_seconds: int) -> dict[str, Any]:
        with self._lock:
            if not enabled:
                status = "disabled"
            elif self._last_cycle_status == "error":
                status = "error"
            elif self._last_cycle_status == "degraded":
                status = "degraded"
            elif self.last_completed_at is None:
                status = "starting"
            else:
                status = "ok"
            return {
                "status": status,
                "interval_seconds": interval_seconds,
                "running": self.running,
                "last_started_at": self.last_started_at,
                "last_completed_at": self.last_completed_at,
                "last_error_at": self.last_error_at,
                "last_error_type": self.last_error_type,
                "last_duration_ms": self.last_duration_ms,
                "last_evaluated_users": self.last_evaluated_users,
                "last_triggered_events": self.last_triggered_events,
                "last_failed_users": self.last_failed_users,
            }

    def _duration_ms(self) -> float | None:
        if self._cycle_started_monotonic is None:
            return None
        return round((monotonic() - self._cycle_started_monotonic) * 1000, 2)


scheduler_runtime = SchedulerRuntime()
