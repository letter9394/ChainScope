import sqlite3
import threading
from datetime import UTC, datetime
from pathlib import Path

from app.models import WatchlistItem
from app.services.market import SUPPORTED_ASSETS


class WatchlistRepository:
    """SQLite-backed repository for the single-user local MVP."""

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
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS watchlist (
                    coin_id TEXT PRIMARY KEY,
                    symbol TEXT NOT NULL,
                    added_at TEXT NOT NULL
                )
                """
            )

    def list_items(self) -> list[WatchlistItem]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT coin_id, symbol, added_at FROM watchlist ORDER BY added_at DESC"
            ).fetchall()
        return [WatchlistItem(**dict(row)) for row in rows]

    def add(self, coin_id: str) -> WatchlistItem:
        if coin_id not in SUPPORTED_ASSETS:
            raise ValueError(f"Unsupported coin: {coin_id}")
        item = WatchlistItem(
            coin_id=coin_id,
            symbol=SUPPORTED_ASSETS[coin_id],
            added_at=datetime.now(UTC).isoformat(),
        )
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                INSERT INTO watchlist (coin_id, symbol, added_at)
                VALUES (?, ?, ?)
                ON CONFLICT(coin_id) DO UPDATE SET
                    symbol = excluded.symbol,
                    added_at = excluded.added_at
                """,
                (item.coin_id, item.symbol, item.added_at),
            )
        return item

    def remove(self, coin_id: str) -> bool:
        with self._lock, self._connect() as connection:
            cursor = connection.execute("DELETE FROM watchlist WHERE coin_id = ?", (coin_id,))
        return cursor.rowcount > 0
