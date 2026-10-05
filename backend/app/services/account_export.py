from __future__ import annotations

from sqlalchemy import select

from app.database import (
    AlertEventRow, AlertRuleRow, Database, EmailVerificationRow, NotificationDeliveryRow,
    NotificationPreferenceRow, RiskDriftDeliveryRow, RiskDriftEventRow,
    UserRow, WatchlistRow, utcnow,
)


def export_account_data(database: Database, user: UserRow) -> dict:
    """Export only the signed-in user's portable, non-secret account data."""

    with database.session() as session:
        verification = session.get(EmailVerificationRow, user.id)
        watchlist = session.scalars(
            select(WatchlistRow).where(WatchlistRow.user_id == user.id).order_by(WatchlistRow.id)
        ).all()
        rules = session.scalars(
            select(AlertRuleRow).where(AlertRuleRow.user_id == user.id).order_by(AlertRuleRow.id)
        ).all()
        events = session.scalars(
            select(AlertEventRow).where(AlertEventRow.user_id == user.id).order_by(AlertEventRow.id)
        ).all()
        preferences = session.get(NotificationPreferenceRow, user.id)
        deliveries = session.scalars(
            select(NotificationDeliveryRow)
            .where(NotificationDeliveryRow.user_id == user.id)
            .order_by(NotificationDeliveryRow.id)
        ).all()
        drift_deliveries = session.execute(
            select(RiskDriftDeliveryRow, RiskDriftEventRow)
            .join(RiskDriftEventRow, RiskDriftEventRow.id == RiskDriftDeliveryRow.event_id)
            .where(RiskDriftDeliveryRow.user_id == user.id)
            .order_by(RiskDriftDeliveryRow.id)
        ).all()

        return {
            "format": "chainscope-account-export",
            "schema_version": 1,
            "exported_at": utcnow().isoformat(),
            "account": {
                "email": user.email,
                "created_at": user.created_at.isoformat(),
                "email_verified": verification is None or verification.verified_at is not None,
            },
            "watchlist": [
                {"coin_id": row.coin_id, "symbol": row.symbol, "added_at": row.added_at.isoformat()}
                for row in watchlist
            ],
            "alert_rules": [
                {
                    "id": row.id, "coin_id": row.coin_id, "symbol": row.symbol,
                    "metric": row.metric, "operator": row.operator, "threshold": row.threshold,
                    "enabled": row.enabled, "is_triggered": row.is_triggered,
                    "created_at": row.created_at.isoformat(),
                    "last_triggered_at": row.last_triggered_at.isoformat() if row.last_triggered_at else None,
                }
                for row in rules
            ],
            "alert_events": [
                {
                    "id": row.id, "rule_id": row.rule_id, "coin_id": row.coin_id,
                    "symbol": row.symbol, "metric": row.metric, "operator": row.operator,
                    "threshold": row.threshold, "observed_value": row.observed_value,
                    "severity": row.severity, "title": row.title, "message": row.message,
                    "triggered_at": row.triggered_at.isoformat(),
                    "acknowledged_at": row.acknowledged_at.isoformat() if row.acknowledged_at else None,
                }
                for row in events
            ],
            "notification_preferences": {
                "email_enabled": preferences.email_enabled if preferences else False,
                "drift_email_enabled": preferences.drift_email_enabled if preferences else False,
            },
            "notification_deliveries": [
                {
                    "event_id": row.event_id, "channel": row.channel,
                    "status": row.status, "attempted_at": row.attempted_at.isoformat(),
                }
                for row in deliveries
            ],
            "risk_drift_deliveries": [
                {
                    "event_id": event.id, "coin_id": event.coin_id, "symbol": event.symbol,
                    "title": event.title, "status": delivery.status,
                    "attempted_at": delivery.attempted_at.isoformat(),
                    "provider_event_at": (
                        delivery.provider_event_at.isoformat() if delivery.provider_event_at else None
                    ),
                }
                for delivery, event in drift_deliveries
            ],
        }
