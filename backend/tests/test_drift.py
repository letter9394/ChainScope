from datetime import UTC, datetime

from app.database import Database
from app.models import (
    RiskBacktestResult, RiskTemporalStabilityPeriod, RiskTemporalStabilityResult,
)
from app.services.drift import RiskDriftRepository


def result_with_status(status: str) -> RiskBacktestResult:
    temporal = RiskTemporalStabilityResult(
        model_name="v0.7 时间稳定性与漂移监控",
        status=status,
        selected_key="fixed",
        selected_label="固定跌幅",
        horizon_days=7,
        lift_change=-0.6 if status == "deteriorating" else 0.1,
        brier_skill_change=-0.1 if status == "deteriorating" else 0.02,
        event_rate_change_percent_points=3.5,
        verdict="test fixture",
        periods=[
            RiskTemporalStabilityPeriod(
                period=1,
                holdout_start=1,
                holdout_end=2,
                holdout_points=60,
                event_days=18,
                signal_count=6,
                baseline_hit_rate_percent=30,
                precision_percent=60,
                lift=2.0,
                brier_skill_score=0.08,
                calibration_error_percent=5,
                passed=True,
            )
        ],
    )
    return RiskBacktestResult.model_construct(
        coin_id="bitcoin",
        symbol="BTC",
        temporal_stability=temporal,
    )


def test_same_day_snapshot_is_updated_without_duplicate_event(tmp_path) -> None:
    repository = RiskDriftRepository(Database(str(tmp_path / "drift.db")))

    first, first_event = repository.record_result(
        result_with_status("stable"),
        observed_at=datetime(2026, 9, 28, 1, tzinfo=UTC),
    )
    second, second_event = repository.record_result(
        result_with_status("stable"),
        observed_at=datetime(2026, 9, 28, 2, tzinfo=UTC),
    )
    state = repository.asset_states({"bitcoin": "BTC"})[0]

    assert first_event is None
    assert second_event is None
    assert first.id == second.id
    assert len(state.history) == 1
    assert state.current is not None
    assert state.current.observed_at.startswith("2026-09-28T02:00:00")


def test_status_transition_is_recorded_once_and_recovery_is_preserved(tmp_path) -> None:
    repository = RiskDriftRepository(Database(str(tmp_path / "transitions.db")))
    repository.record_result(
        result_with_status("stable"),
        observed_at=datetime(2026, 9, 27, 1, tzinfo=UTC),
    )

    _, deterioration = repository.record_result(
        result_with_status("deteriorating"),
        observed_at=datetime(2026, 9, 28, 1, tzinfo=UTC),
    )
    _, duplicate = repository.record_result(
        result_with_status("deteriorating"),
        observed_at=datetime(2026, 9, 28, 2, tzinfo=UTC),
    )
    _, recovery = repository.record_result(
        result_with_status("stable"),
        observed_at=datetime(2026, 9, 29, 1, tzinfo=UTC),
    )
    events = repository.recent_events()

    assert deterioration is not None
    assert deterioration.severity == "warning"
    assert duplicate is None
    assert recovery is not None
    assert recovery.severity == "info"
    assert len(events) == 2
    assert events[0].previous_status == "deteriorating"
    assert events[0].current_status == "stable"
    assert events[1].previous_status == "stable"
    assert events[1].current_status == "deteriorating"


def test_asset_states_include_assets_without_history(tmp_path) -> None:
    repository = RiskDriftRepository(Database(str(tmp_path / "states.db")))
    repository.record_result(
        result_with_status("mixed"),
        observed_at=datetime(2026, 9, 29, 1, tzinfo=UTC),
    )

    states = repository.asset_states({"bitcoin": "BTC", "ethereum": "ETH"})

    assert states[0].current is not None
    assert states[0].current.status == "mixed"
    assert states[1].current is None
    assert states[1].history == []
