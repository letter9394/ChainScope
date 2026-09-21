from __future__ import annotations

import asyncio
import logging

from app.config import Settings
from app.database import Database
from app.services.alerts import AlertRepository, evaluate_alert_rules
from app.services.market import CoinGeckoClient
from app.services.notifications import NotificationService


logger = logging.getLogger(__name__)


async def run_alert_scheduler(database: Database, settings: Settings) -> None:
    """Evaluate every user's rules while this web instance is awake."""

    client = CoinGeckoClient(settings)
    notifier = NotificationService(database, settings)
    await asyncio.sleep(5)
    while True:
        try:
            for user_id in AlertRepository.user_ids_with_enabled_rules(database):
                try:
                    result = await evaluate_alert_rules(
                        AlertRepository(database, user_id), client, settings
                    )
                    await notifier.deliver(user_id, result.triggered_events)
                except Exception:
                    logger.exception("Background alert evaluation failed for user %s", user_id)
        except Exception:
            logger.exception("Background alert scheduler cycle failed")
        await asyncio.sleep(max(15, settings.alert_check_seconds))
