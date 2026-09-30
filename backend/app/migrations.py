from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect

from app.database import Base, Database


BASELINE_REVISION = "20260928_0001"
HEAD_REVISION = "20260930_0004"
DRIFT_TABLES = {"risk_drift_snapshots", "risk_drift_events", "risk_drift_deliveries"}


class SchemaCompatibilityError(RuntimeError):
    """Raised when an unversioned database cannot be adopted safely."""


def _alembic_config(database_url: str) -> Config:
    backend_root = Path(__file__).resolve().parents[1]
    config = Config(str(backend_root / "alembic.ini"))
    config.attributes["database_url_configured"] = True
    config.set_main_option("script_location", str(backend_root / "alembic"))
    config.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))
    return config


def _validate_current_schema(database_url: str) -> None:
    engine = create_engine(database_url, pool_pre_ping=True)
    try:
        inspector = inspect(engine)
        existing_tables = set(inspector.get_table_names())
        expected_tables = set(Base.metadata.tables)
        missing_tables = sorted(expected_tables - existing_tables)
        if missing_tables:
            raise SchemaCompatibilityError(
                "Database schema is incomplete; missing tables: " + ", ".join(missing_tables)
            )

        missing_columns: list[str] = []
        for table_name, table in Base.metadata.tables.items():
            actual_columns = {column["name"] for column in inspector.get_columns(table_name)}
            for column in table.columns:
                if column.name not in actual_columns:
                    missing_columns.append(f"{table_name}.{column.name}")
        if missing_columns:
            raise SchemaCompatibilityError(
                "Database schema is incomplete; missing columns: " + ", ".join(missing_columns)
            )
    finally:
        engine.dispose()


def upgrade_database(url_or_path: str) -> None:
    """Upgrade a database, safely adopting the pre-Alembic schema when present."""

    database_url = Database._normalize_url(url_or_path)
    config = _alembic_config(database_url)
    engine = create_engine(database_url, pool_pre_ping=True)
    try:
        existing_tables = set(inspect(engine).get_table_names())
    finally:
        engine.dispose()

    application_tables = set(Base.metadata.tables)
    if application_tables & existing_tables and "alembic_version" not in existing_tables:
        missing_tables = application_tables - existing_tables
        if not missing_tables:
            _validate_current_schema(database_url)
            command.stamp(config, HEAD_REVISION)
        elif missing_tables <= DRIFT_TABLES and (application_tables - DRIFT_TABLES) <= existing_tables:
            v08_tables = {"risk_drift_snapshots", "risk_drift_events"}
            present_v08_tables = v08_tables & existing_tables
            if not present_v08_tables:
                command.stamp(config, BASELINE_REVISION)
            elif present_v08_tables == v08_tables:
                command.stamp(config, "20260929_0002")
            else:
                raise SchemaCompatibilityError(
                    "Database schema is incomplete; missing tables: "
                    + ", ".join(sorted(missing_tables))
                )
        else:
            raise SchemaCompatibilityError(
                "Database schema is incomplete; missing tables: "
                + ", ".join(sorted(missing_tables))
            )

    command.upgrade(config, "head")
    _validate_current_schema(database_url)


if __name__ == "__main__":
    from app.config import get_settings

    upgrade_database(get_settings().resolved_database_url)
