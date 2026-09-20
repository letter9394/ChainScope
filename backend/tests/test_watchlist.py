from pathlib import Path

import pytest

from app.services.watchlist import WatchlistRepository


@pytest.fixture
def repository(tmp_path: Path) -> WatchlistRepository:
    return WatchlistRepository(str(tmp_path / "watchlist.db"))


def test_watchlist_starts_empty(repository: WatchlistRepository) -> None:
    assert repository.list_items() == []


def test_add_and_list_watchlist(repository: WatchlistRepository) -> None:
    repository.add("bitcoin")
    items = repository.list_items()
    assert len(items) == 1
    assert items[0].symbol == "BTC"


def test_add_is_idempotent(repository: WatchlistRepository) -> None:
    repository.add("ethereum")
    repository.add("ethereum")
    assert len(repository.list_items()) == 1


def test_remove_watchlist_item(repository: WatchlistRepository) -> None:
    repository.add("solana")
    assert repository.remove("solana") is True
    assert repository.remove("solana") is False
    assert repository.list_items() == []


def test_rejects_unknown_coin(repository: WatchlistRepository) -> None:
    with pytest.raises(ValueError, match="Unsupported coin"):
        repository.add("unknown")


def test_add_gold_to_watchlist(repository: WatchlistRepository) -> None:
    item = repository.add("gold")
    assert item.symbol == "XAU"
    assert repository.list_items()[0].coin_id == "gold"
