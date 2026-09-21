import sqlite3
import threading
from datetime import UTC, datetime
from pathlib import Path

from app.config import Settings
from app.models import AlertEvaluationResponse, AlertEvent, AlertRule, AlertRuleCreate
from app.services.derivatives import get_derivatives_snapshot
from app.services.market import CoinGeckoClient, SUPPORTED_COINS
from app.services.news import get_news
from app.services.risk import assess_risk


METRIC_LABELS = {
    "risk_score": "综合风险分",
    "price_change_24h": "24 小时涨跌幅",
}


class AlertRepository:
    """Persists alert rules, transition state, and triggered events in SQLite."""

    def __init__(self, database_path: str) -> None:
        self.database_path = Path(database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=5)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS alert_rules (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    coin_id TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    metric TEXT NOT NULL,
                    operator TEXT NOT NULL,
                    threshold REAL NOT NULL,
                    enabled INTEGER NOT NULL DEFAULT 1,
                    is_triggered INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    last_triggered_at TEXT
                );

                CREATE TABLE IF NOT EXISTS alert_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    rule_id INTEGER NOT NULL,
                    coin_id TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    metric TEXT NOT NULL,
                    operator TEXT NOT NULL,
                    threshold REAL NOT NULL,
                    observed_value REAL NOT NULL,
                    severity TEXT NOT NULL,
                    title TEXT NOT NULL,
                    message TEXT NOT NULL,
                    triggered_at TEXT NOT NULL,
                    acknowledged_at TEXT
                );
                """
            )

    @staticmethod
    def _rule_from_row(row: sqlite3.Row) -> AlertRule:
        payload = dict(row)
        payload["enabled"] = bool(payload["enabled"])
        payload["is_triggered"] = bool(payload["is_triggered"])
        return AlertRule(**payload)

    @staticmethod
    def _event_from_row(row: sqlite3.Row) -> AlertEvent:
        return AlertEvent(**dict(row))

    def list_rules(self, *, enabled_only: bool = False) -> list[AlertRule]:
        query = "SELECT * FROM alert_rules"
        parameters: tuple[object, ...] = ()
        if enabled_only:
            query += " WHERE enabled = 1"
        query += " ORDER BY created_at DESC, id DESC"
        with self._connect() as connection:
            rows = connection.execute(query, parameters).fetchall()
        return [self._rule_from_row(row) for row in rows]

    def add_rule(self, rule: AlertRuleCreate) -> AlertRule:
        if rule.coin_id not in SUPPORTED_COINS:
            raise ValueError(f"Unsupported coin: {rule.coin_id}")
        created_at = datetime.now(UTC).isoformat()
        with self._lock, self._connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO alert_rules
                    (coin_id, symbol, metric, operator, threshold, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    rule.coin_id,
                    SUPPORTED_COINS[rule.coin_id],
                    rule.metric,
                    rule.operator,
                    rule.threshold,
                    created_at,
                ),
            )
            row = connection.execute(
                "SELECT * FROM alert_rules WHERE id = ?", (cursor.lastrowid,)
            ).fetchone()
        assert row is not None
        return self._rule_from_row(row)

    def remove_rule(self, rule_id: int) -> bool:
        with self._lock, self._connect() as connection:
            cursor = connection.execute("DELETE FROM alert_rules WHERE id = ?", (rule_id,))
        return cursor.rowcount > 0

    def list_events(self, *, unacknowledged_only: bool = False, limit: int = 50) -> list[AlertEvent]:
        query = "SELECT * FROM alert_events"
        parameters: list[object] = []
        if unacknowledged_only:
            query += " WHERE acknowledged_at IS NULL"
        query += " ORDER BY triggered_at DESC, id DESC LIMIT ?"
        parameters.append(limit)
        with self._connect() as connection:
            rows = connection.execute(query, parameters).fetchall()
        return [self._event_from_row(row) for row in rows]

    def acknowledge_event(self, event_id: int) -> AlertEvent | None:
        acknowledged_at = datetime.now(UTC).isoformat()
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                UPDATE alert_events
                SET acknowledged_at = COALESCE(acknowledged_at, ?)
                WHERE id = ?
                """,
                (acknowledged_at, event_id),
            )
            row = connection.execute(
                "SELECT * FROM alert_events WHERE id = ?", (event_id,)
            ).fetchone()
        return self._event_from_row(row) if row is not None else None

    def evaluate(self, readings: dict[tuple[str, str], float]) -> list[AlertEvent]:
        """Create one event when a rule changes from safe to triggered.

        A rule must return to the safe side before it can create another event,
        preventing a new notification on every 60-second refresh.
        """

        triggered: list[AlertEvent] = []
        now = datetime.now(UTC).isoformat()
        with self._lock, self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM alert_rules WHERE enabled = 1 ORDER BY id"
            ).fetchall()
            for row in rows:
                rule = self._rule_from_row(row)
                observed = readings.get((rule.coin_id, rule.metric))
                if observed is None:
                    continue
                condition_met = observed >= rule.threshold if rule.operator == "gte" else observed <= rule.threshold
                if not condition_met:
                    if rule.is_triggered:
                        connection.execute(
                            "UPDATE alert_rules SET is_triggered = 0 WHERE id = ?", (rule.id,)
                        )
                    continue
                if rule.is_triggered:
                    continue

                severity = self._severity(rule, observed)
                title, message = self._event_copy(rule, observed)
                cursor = connection.execute(
                    """
                    INSERT INTO alert_events
                        (rule_id, coin_id, symbol, metric, operator, threshold,
                         observed_value, severity, title, message, triggered_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        rule.id,
                        rule.coin_id,
                        rule.symbol,
                        rule.metric,
                        rule.operator,
                        rule.threshold,
                        observed,
                        severity,
                        title,
                        message,
                        now,
                    ),
                )
                connection.execute(
                    """
                    UPDATE alert_rules
                    SET is_triggered = 1, last_triggered_at = ?
                    WHERE id = ?
                    """,
                    (now, rule.id),
                )
                event_row = connection.execute(
                    "SELECT * FROM alert_events WHERE id = ?", (cursor.lastrowid,)
                ).fetchone()
                assert event_row is not None
                triggered.append(self._event_from_row(event_row))
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
        metric_label = METRIC_LABELS[rule.metric]
        comparator = "达到或高于" if rule.operator == "gte" else "达到或低于"
        suffix = "分" if rule.metric == "risk_score" else "%"
        title = f"{rule.symbol} {metric_label}已越过阈值"
        message = (
            f"当前值 {observed:.2f}{suffix}，已{comparator}你设置的 "
            f"{rule.threshold:g}{suffix}。"
        )
        return title, message


async def evaluate_alert_rules(
    repository: AlertRepository,
    client: CoinGeckoClient,
    settings: Settings | None = None,
) -> AlertEvaluationResponse:
    rules = repository.list_rules(enabled_only=True)
    readings: dict[tuple[str, str], float] = {}

    price_rules = [rule for rule in rules if rule.metric == "price_change_24h"]
    if price_rules:
        markets = await client.get_markets()
        market_by_id = {market.id: market for market in markets}
        for rule in price_rules:
            change = market_by_id.get(rule.coin_id)
            if change is not None and change.price_change_percentage_24h is not None:
                readings[(rule.coin_id, rule.metric)] = change.price_change_percentage_24h

    risk_coin_ids = {rule.coin_id for rule in rules if rule.metric == "risk_score"}
    for coin_id in risk_coin_ids:
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
            coin_id,
            SUPPORTED_COINS[coin_id],
            history,
            derivatives=derivatives,
            news_articles=articles,
        )
        readings[(coin_id, "risk_score")] = float(assessment.score)

    triggered_events = repository.evaluate(readings)
    evaluated_count = sum((rule.coin_id, rule.metric) in readings for rule in rules)
    return AlertEvaluationResponse(
        evaluated_rules=evaluated_count,
        triggered_events=triggered_events,
        active_events=repository.list_events(unacknowledged_only=True),
    )
