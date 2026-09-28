from pathlib import Path

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import create_engine, inspect, select, text

from app.database import Base, Database, UserRow
from app.migrations import BASELINE_REVISION, SchemaCompatibilityError, upgrade_database


def sqlite_url(path: Path) -> str:
    return f"sqlite:///{path.as_posix()}"


def test_migrations_create_a_fresh_database(tmp_path: Path) -> None:
    url = sqlite_url(tmp_path / "fresh.db")

    upgrade_database(url)

    engine = create_engine(url)
    try:
        tables = set(inspect(engine).get_table_names())
        assert set(Base.metadata.tables) <= tables
        assert "alembic_version" in tables
        with engine.connect() as connection:
            version = connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
        assert version == BASELINE_REVISION
    finally:
        engine.dispose()


def test_migration_schema_matches_sqlalchemy_models(tmp_path: Path) -> None:
    url = sqlite_url(tmp_path / "metadata.db")
    upgrade_database(url)

    engine = create_engine(url)
    try:
        with engine.connect() as connection:
            context = MigrationContext.configure(connection, opts={"compare_type": True})
            differences = compare_metadata(context, Base.metadata)
        assert differences == []
    finally:
        engine.dispose()


def test_migrations_adopt_existing_schema_without_losing_data(tmp_path: Path) -> None:
    url = sqlite_url(tmp_path / "legacy.db")
    legacy = Database(url)
    with legacy.session() as session:
        session.add(UserRow(email="legacy@example.com", password_hash="existing-hash"))
        session.commit()
    legacy.engine.dispose()

    upgrade_database(url)

    migrated = Database(url, initialize_schema=False)
    try:
        with migrated.session() as session:
            user = session.scalar(select(UserRow).where(UserRow.email == "legacy@example.com"))
        assert user is not None
        assert user.password_hash == "existing-hash"
        with migrated.engine.connect() as connection:
            version = connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
        assert version == BASELINE_REVISION
    finally:
        migrated.engine.dispose()


def test_migrations_refuse_to_stamp_a_partial_legacy_schema(tmp_path: Path) -> None:
    url = sqlite_url(tmp_path / "partial.db")
    engine = create_engine(url)
    try:
        UserRow.__table__.create(engine)
    finally:
        engine.dispose()

    with pytest.raises(SchemaCompatibilityError, match="missing tables"):
        upgrade_database(url)

    check_engine = create_engine(url)
    try:
        assert "alembic_version" not in inspect(check_engine).get_table_names()
    finally:
        check_engine.dispose()
