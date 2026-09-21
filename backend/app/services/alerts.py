from __future__ import annotations

from sqlalchemy import delete, select

from app.config import Settings
from app.database import AlertEventRow, AlertRuleRow, Database, utcnow
from app.models import AlertEvaluationResponse, AlertEvent, AlertRule, AlertRuleCreate
from app.services.derivatives import get_derivatives_snapshot
from app.services.market import CoinGeckoClient, SUPPORTED_COINS
from app.services.news import get_news
from app.services.risk import assess_risk


METRIC_LABELS = {"risk_score": "综合风险分", "price_change_24h": "24 小时涨跌幅"}


class AlertRepository:
    """User-scoped alert rules, transition state, and events."""

    def __init__(self, database: Database | str, user_id: int = 1) -> None:
        self.database = database if isinstance(database, Database) else Database(database)
        self.user_id = user_id

    @staticmethod
    def _rule_model(row: AlertRuleRow) -> AlertRule:
        return AlertRule(
            id=row.id, coin_id=row.coin_id, symbol=row.symbol, metric=row.metric,
            operator=row.operator, threshold=row.threshold, enabled=row.enabled,
            is_triggered=row.is_triggered, created_at=row.created_at.isoformat(),
            last_triggered_at=row.last_triggered_at.isoformat() if row.last_triggered_at else None,
        )

    @staticmethod
    def _event_model(row: AlertEventRow) -> AlertEvent:
        return AlertEvent(
            id=row.id, rule_id=row.rule_id, coin_id=row.coin_id, symbol=row.symbol,
            metric=row.metric, operator=row.operator, threshold=row.threshold,
            observed_value=row.observed_value, severity=row.severity, title=row.title,
            message=row.message, triggered_at=row.triggered_at.isoformat(),
            acknowledged_at=row.acknowledged_at.isoformat() if row.acknowledged_at else None,
        )

    @staticmethod
    def user_ids_with_enabled_rules(database: Database) -> list[int]:
        with database.session() as session:
            return list(session.scalars(
                select(AlertRuleRow.user_id).where(AlertRuleRow.enabled.is_(True)).distinct()
            ).all())

    def list_rules(self, *, enabled_only: bool = False) -> list[AlertRule]:
        query = select(AlertRuleRow).where(AlertRuleRow.user_id == self.user_id)
        if enabled_only:
            query = query.where(AlertRuleRow.enabled.is_(True))
        query = query.order_by(AlertRuleRow.created_at.desc(), AlertRuleRow.id.desc())
        with self.database.session() as session:
            return [self._rule_model(row) for row in session.scalars(query).all()]

    def add_rule(self, rule: AlertRuleCreate) -> AlertRule:
        if rule.coin_id not in SUPPORTED_COINS:
            raise ValueError(f"Unsupported coin: {rule.coin_id}")
        row = AlertRuleRow(
            user_id=self.user_id, coin_id=rule.coin_id, symbol=SUPPORTED_COINS[rule.coin_id],
            metric=rule.metric, operator=rule.operator, threshold=rule.threshold,
        )
        with self.database.session() as session:
            session.add(row)
            session.commit()
            session.refresh(row)
            return self._rule_model(row)

    def remove_rule(self, rule_id: int) -> bool:
        with self.database.session() as session:
            result = session.execute(delete(AlertRuleRow).where(
                AlertRuleRow.id == rule_id, AlertRuleRow.user_id == self.user_id,
            ))
            session.commit()
            return bool(result.rowcount)

    def list_events(self, *, unacknowledged_only: bool = False, limit: int = 50) -> list[AlertEvent]:
        query = select(AlertEventRow).where(AlertEventRow.user_id == self.user_id)
        if unacknowledged_only:
            query = query.where(AlertEventRow.acknowledged_at.is_(None))
        query = query.order_by(AlertEventRow.triggered_at.desc(), AlertEventRow.id.desc()).limit(limit)
        with self.database.session() as session:
            return [self._event_model(row) for row in session.scalars(query).all()]

    def acknowledge_event(self, event_id: int) -> AlertEvent | None:
        with self.database.session() as session:
            row = session.scalar(select(AlertEventRow).where(
                AlertEventRow.id == event_id, AlertEventRow.user_id == self.user_id,
            ))
            if row is None:
                return None
            if row.acknowledged_at is None:
                row.acknowledged_at = utcnow()
                session.commit()
                session.refresh(row)
            return self._event_model(row)

    def evaluate(self, readings: dict[tuple[str, str], float]) -> list[AlertEvent]:
        triggered: list[AlertEvent] = []
        now = utcnow()
        with self.database.session() as session:
            rows = session.scalars(select(AlertRuleRow).where(
                AlertRuleRow.user_id == self.user_id, AlertRuleRow.enabled.is_(True),
            ).order_by(AlertRuleRow.id)).all()
            for row in rows:
                rule = self._rule_model(row)
                observed = readings.get((rule.coin_id, rule.metric))
                if observed is None:
                    continue
                condition_met = observed >= rule.threshold if rule.operator == "gte" else observed <= rule.threshold
                if not condition_met:
                    row.is_triggered = False
                    continue
                if row.is_triggered:
                    continue
                severity = self._severity(rule, observed)
                title, message = self._event_copy(rule, observed)
                event_row = AlertEventRow(
                    user_id=self.user_id, rule_id=row.id, coin_id=row.coin_id, symbol=row.symbol,
                    metric=row.metric, operator=row.operator, threshold=row.threshold,
                    observed_value=observed, severity=severity, title=title, message=message,
                    triggered_at=now,
                )
                session.add(event_row)
                row.is_triggered = True
                row.last_triggered_at = now
                session.flush()
                triggered.append(self._event_model(event_row))
            session.commit()
        return triggered

    @staticmethod
    def _severity(rule: AlertRule, observed: float) -> str:
        if rule.metric == "risk_score" and observed >= 75:
            return "critical"
        if rule.metric == "price_change_24h" and observed <= -8:
            return "critical"
        return "warning"

    @staticmethod
    def _event_copy(rule: AlertRule, observed: float) -> tuple[str, str]:
        comparator = "达到或高于" if rule.operator == "gte" else "达到或低于"
        suffix = "分" if rule.metric == "risk_score" else "%"
        return (
            f"{rule.symbol} {METRIC_LABELS[rule.metric]}已越过阈值",
            f"当前值 {observed:.2f}{suffix}，已{comparator}你设置的 {rule.threshold:g}{suffix}。",
        )


async def evaluate_alert_rules(
    repository: AlertRepository,
    client: CoinGeckoClient,
    settings: Settings | None = None,
) -> AlertEvaluationResponse:
    rules = repository.list_rules(enabled_only=True)
    readings: dict[tuple[str, str], float] = {}
    if any(rule.metric == "price_change_24h" for rule in rules):
        markets = await client.get_markets()
        market_by_id = {market.id: market for market in markets}
        for rule in rules:
            market = market_by_id.get(rule.coin_id)
            if rule.metric == "price_change_24h" and market and market.price_change_percentage_24h is not None:
                readings[(rule.coin_id, rule.metric)] = market.price_change_percentage_24h
    for coin_id in {rule.coin_id for rule in rules if rule.metric == "risk_score"}:
        history = await client.get_history(coin_id, 30)
        derivatives = None
        articles = None
        if settings is not None:
            try:
                derivatives = await get_derivatives_snapshot(settings, coin_id)
                articles = (await get_news(settings, coin_id=coin_id, limit=6)).articles
            except (RuntimeError, ValueError):
                pass
        assessment = assess_risk(
            coin_id, SUPPORTED_COINS[coin_id], history,
            derivatives=derivatives, news_articles=articles,
        )
        readings[(coin_id, "risk_score")] = float(assessment.score)
    triggered_events = repository.evaluate(readings)
    return AlertEvaluationResponse(
        evaluated_rules=sum((rule.coin_id, rule.metric) in readings for rule in rules),
        triggered_events=triggered_events,
        active_events=repository.list_events(unacknowledged_only=True),
    )
