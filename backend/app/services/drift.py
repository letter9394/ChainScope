from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select

from app.database import Database, RiskDriftEventRow, RiskDriftSnapshotRow
from app.models import (
    RiskBacktestResult, RiskDriftAssetState, RiskDriftEvent, RiskDriftSnapshot,
)


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _snapshot_model(row: RiskDriftSnapshotRow) -> RiskDriftSnapshot:
    return RiskDriftSnapshot(
        id=row.id,
        coin_id=row.coin_id,
        symbol=row.symbol,
        status=row.status,
        selected_key=row.selected_key,
        selected_label=row.selected_label,
        horizon_days=row.horizon_days,
        lift_change=row.lift_change,
        brier_skill_change=row.brier_skill_change,
        event_rate_change_percent_points=row.event_rate_change_percent_points,
        latest_lift=row.latest_lift,
        latest_brier_skill_score=row.latest_brier_skill_score,
        observed_at=_aware(row.observed_at).isoformat(),
    )


def _event_model(row: RiskDriftEventRow) -> RiskDriftEvent:
    return RiskDriftEvent(
        id=row.id,
        coin_id=row.coin_id,
        symbol=row.symbol,
        previous_status=row.previous_status,
        current_status=row.current_status,
        severity=row.severity,
        title=row.title,
        message=row.message,
        created_at=_aware(row.created_at).isoformat(),
    )


class RiskDriftRepository:
    """Persist one monitoring snapshot per asset/day and deduplicated transitions."""

    def __init__(self, database: Database) -> None:
        self.database = database

    def record_result(
        self,
        result: RiskBacktestResult,
        *,
        observed_at: datetime | None = None,
    ) -> tuple[RiskDriftSnapshot, RiskDriftEvent | None]:
        observed_at = observed_at or datetime.now(UTC)
        evaluation_date = observed_at.date().isoformat()
        temporal = result.temporal_stability
        latest_period = temporal.periods[-1] if temporal.periods else None

        with self.database.session() as session:
            current = session.scalar(
                select(RiskDriftSnapshotRow).where(
                    RiskDriftSnapshotRow.coin_id == result.coin_id,
                    RiskDriftSnapshotRow.evaluation_date == evaluation_date,
                )
            )
            previous = current or session.scalar(
                select(RiskDriftSnapshotRow)
                .where(RiskDriftSnapshotRow.coin_id == result.coin_id)
                .order_by(RiskDriftSnapshotRow.observed_at.desc())
                .limit(1)
            )
            previous_status = previous.status if previous is not None else None
            values = {
                "symbol": result.symbol,
                "status": temporal.status,
                "selected_key": temporal.selected_key,
                "selected_label": temporal.selected_label,
                "horizon_days": temporal.horizon_days,
                "lift_change": temporal.lift_change,
                "brier_skill_change": temporal.brier_skill_change,
                "event_rate_change_percent_points": temporal.event_rate_change_percent_points,
                "latest_lift": latest_period.lift if latest_period is not None else 0.0,
                "latest_brier_skill_score": (
                    latest_period.brier_skill_score if latest_period is not None else 0.0
                ),
                "observed_at": observed_at,
            }
            if current is None:
                current = RiskDriftSnapshotRow(
                    coin_id=result.coin_id,
                    evaluation_date=evaluation_date,
                    **values,
                )
                session.add(current)
            else:
                for key, value in values.items():
                    setattr(current, key, value)
            session.flush()

            event_row = None
            if previous_status is not None and previous_status != temporal.status:
                event_row = self._transition_event(
                    coin_id=result.coin_id,
                    symbol=result.symbol,
                    previous_status=previous_status,
                    current_status=temporal.status,
                    transition_date=evaluation_date,
                    created_at=observed_at,
                )
                duplicate = session.scalar(
                    select(RiskDriftEventRow).where(
                        RiskDriftEventRow.coin_id == result.coin_id,
                        RiskDriftEventRow.previous_status == previous_status,
                        RiskDriftEventRow.current_status == temporal.status,
                        RiskDriftEventRow.transition_date == evaluation_date,
                    )
                )
                if duplicate is None:
                    session.add(event_row)
                    session.flush()
                else:
                    event_row = None
            session.commit()
            snapshot = _snapshot_model(current)
            event = _event_model(event_row) if event_row is not None else None
        return snapshot, event

    def asset_states(
        self,
        assets: dict[str, str],
        *,
        history_limit: int = 14,
    ) -> list[RiskDriftAssetState]:
        states: list[RiskDriftAssetState] = []
        with self.database.session() as session:
            for coin_id, symbol in assets.items():
                rows = list(session.scalars(
                    select(RiskDriftSnapshotRow)
                    .where(RiskDriftSnapshotRow.coin_id == coin_id)
                    .order_by(RiskDriftSnapshotRow.observed_at.desc())
                    .limit(history_limit)
                ))
                history = [_snapshot_model(row) for row in rows]
                states.append(RiskDriftAssetState(
                    coin_id=coin_id,
                    symbol=symbol,
                    current=history[0] if history else None,
                    history=history,
                ))
        return states

    def recent_events(self, *, limit: int = 20) -> list[RiskDriftEvent]:
        with self.database.session() as session:
            rows = list(session.scalars(
                select(RiskDriftEventRow)
                .order_by(RiskDriftEventRow.created_at.desc())
                .limit(limit)
            ))
        return [_event_model(row) for row in rows]

    @staticmethod
    def _transition_event(
        *,
        coin_id: str,
        symbol: str,
        previous_status: str,
        current_status: str,
        transition_date: str,
        created_at: datetime,
    ) -> RiskDriftEventRow:
        if current_status == "deteriorating":
            severity = "warning"
            title = f"{symbol} 模型检测到性能衰减"
            message = "最近留出期表现相对早期下降，已进入人工复核队列；线上模型不会自动切换。"
        elif previous_status == "deteriorating":
            severity = "info"
            title = f"{symbol} 模型脱离衰减状态"
            message = f"监控状态已由性能衰减变为 {current_status}，继续保留观察记录。"
        else:
            severity = "info"
            title = f"{symbol} 模型监控状态变化"
            message = f"时间稳定性状态已由 {previous_status} 变为 {current_status}。"
        return RiskDriftEventRow(
            coin_id=coin_id,
            symbol=symbol,
            previous_status=previous_status,
            current_status=current_status,
            transition_date=transition_date,
            severity=severity,
            title=title,
            message=message,
            created_at=created_at,
        )
