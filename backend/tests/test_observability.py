import json
import logging

from app.observability import JsonFormatter, SchedulerRuntime


def test_json_formatter_emits_searchable_fields() -> None:
    record = logging.LogRecord(
        name="chainscope.http",
        level=logging.INFO,
        pathname=__file__,
        lineno=10,
        msg="http_request_completed",
        args=(),
        exc_info=None,
    )
    record.request_id = "request-123"
    record.status_code = 200
    record.duration_ms = 12.5

    payload = json.loads(JsonFormatter().format(record))

    assert payload["event"] == "http_request_completed"
    assert payload["request_id"] == "request-123"
    assert payload["status_code"] == 200
    assert payload["duration_ms"] == 12.5
    assert "timestamp" in payload


def test_scheduler_runtime_records_successful_cycle() -> None:
    runtime = SchedulerRuntime()

    assert runtime.snapshot(enabled=True, interval_seconds=60)["status"] == "starting"
    runtime.start_cycle()
    runtime.complete_cycle(evaluated_users=3, triggered_events=2, failed_users=0)
    snapshot = runtime.snapshot(enabled=True, interval_seconds=60)

    assert snapshot["status"] == "ok"
    assert snapshot["last_completed_at"]
    assert snapshot["last_duration_ms"] is not None
    assert snapshot["last_evaluated_users"] == 3
    assert snapshot["last_triggered_events"] == 2


def test_scheduler_runtime_reports_failures_without_error_text() -> None:
    runtime = SchedulerRuntime()
    runtime.start_cycle()
    runtime.complete_cycle(evaluated_users=1, triggered_events=0, failed_users=0)
    runtime.start_cycle()
    runtime.fail_cycle(RuntimeError("contains-sensitive-upstream-response"))

    snapshot = runtime.snapshot(enabled=True, interval_seconds=60)

    assert snapshot["status"] == "error"
    assert snapshot["last_error_type"] == "RuntimeError"
    assert "contains-sensitive" not in json.dumps(snapshot)
