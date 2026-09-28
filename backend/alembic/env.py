import os

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.database import Base


config = context.config
target_metadata = Base.metadata

runtime_database_url = os.getenv("DATABASE_URL")
if runtime_database_url and not config.attributes.get("database_url_configured"):
    if runtime_database_url.startswith("postgresql://"):
        runtime_database_url = runtime_database_url.replace(
            "postgresql://", "postgresql+psycopg://", 1
        )
    config.set_main_option("sqlalchemy.url", runtime_database_url.replace("%", "%%"))


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
