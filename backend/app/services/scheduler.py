from __future__ import annotations

import asyncio
import logging

from app.config import Settings
from app.database import Database
from app.observability import scheduler_runtime
from app.services.alerts import AlertRepository, evaluate_alert_rules
from app.services.market import CoinGeckoClient
from app.services.notifications import NotificationService


logger = logging.getLogger("chainscope.scheduler")


async def run_alert_scheduler(database: Database, settings: Settings) -> None:
    """Evaluate every user's rules while this web instance is awake."""

    client = CoinGeckoClient(settings)
    notifier = NotificationService(database, settings)
    await asyncio.sleep(5)
    while True:
        scheduler_runtime.start_cycle()
        evaluated_users = 0
        triggered_events = 0
        failed_users = 0
        try:
            user_ids = AlertRepository.user_ids_with_enabled_rules(database)
            for user_id in user_ids:
                try:
                    result = await evaluate_alert_rules(
                        AlertRepository(database, user_id), client, settings
                    )
                    await notifier.deliver(user_id, result.triggered_events)
                    evaluated_users += 1
                    triggered_events += len(result.triggered_events)
                except Exception as exc:
                    failed_users += 1
                    logger.error(
                        "alert_scheduler_user_failed",
                        extra={"user_id": user_id, "error_type": type(exc).__name__},
                    )
            scheduler_runtime.complete_cycle(
                evaluated_users=evaluated_users,
                triggered_events=triggered_events,
                failed_users=failed_users,
            )
            logger.info(
                "alert_scheduler_cycle_completed",
                extra={
                    "evaluated_users": evaluated_users,
                    "triggered_events": triggered_events,
                    "failed_users": failed_users,
                },
            )
        except Exception as exc:
            scheduler_runtime.fail_cycle(exc)
            logger.error(
                "alert_scheduler_cycle_failed",
                extra={"error_type": type(exc).__name__},
            )
        await asyncio.sleep(max(15, settings.alert_check_seconds))
