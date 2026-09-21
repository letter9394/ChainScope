from __future__ import annotations

from sqlalchemy import delete, select

from app.database import Database, WatchlistRow, utcnow
from app.models import WatchlistItem
from app.services.market import SUPPORTED_ASSETS


class WatchlistRepository:
    """User-scoped watchlist backed by PostgreSQL or local SQLite."""

    def __init__(self, database: Database | str, user_id: int = 1) -> None:
        self.database = database if isinstance(database, Database) else Database(database)
        self.user_id = user_id

    @staticmethod
    def _model(row: WatchlistRow) -> WatchlistItem:
        return WatchlistItem(coin_id=row.coin_id, symbol=row.symbol, added_at=row.added_at.isoformat())

    def list_items(self) -> list[WatchlistItem]:
        with self.database.session() as session:
            rows = session.scalars(
                select(WatchlistRow)
                .where(WatchlistRow.user_id == self.user_id)
                .order_by(WatchlistRow.added_at.desc())
            ).all()
            return [self._model(row) for row in rows]

    def add(self, coin_id: str) -> WatchlistItem:
        if coin_id not in SUPPORTED_ASSETS:
            raise ValueError(f"Unsupported coin: {coin_id}")
        with self.database.session() as session:
            row = session.scalar(
                select(WatchlistRow).where(
                    WatchlistRow.user_id == self.user_id,
                    WatchlistRow.coin_id == coin_id,
                )
            )
            if row is None:
                row = WatchlistRow(
                    user_id=self.user_id,
                    coin_id=coin_id,
                    symbol=SUPPORTED_ASSETS[coin_id],
                    added_at=utcnow(),
                )
                session.add(row)
            else:
                row.symbol = SUPPORTED_ASSETS[coin_id]
                row.added_at = utcnow()
            session.commit()
            session.refresh(row)
            return self._model(row)

    def remove(self, coin_id: str) -> bool:
        with self.database.session() as session:
            result = session.execute(
                delete(WatchlistRow).where(
                    WatchlistRow.user_id == self.user_id,
                    WatchlistRow.coin_id == coin_id,
                )
            )
            session.commit()
            return bool(result.rowcount)
