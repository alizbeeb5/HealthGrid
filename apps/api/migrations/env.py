"""Import all module ORM models here before running autogenerate."""

from alembic import context
from sqlalchemy import create_engine, pool

import app.modules.allocation.models  # noqa: F401
import app.modules.facilities.models  # noqa: F401
import app.modules.forecasting.models  # noqa: F401
import app.modules.scenarios.models  # noqa: F401
from app.core.config import get_settings
from app.core.database import Base

target_metadata = Base.metadata
# Tests may set sqlalchemy.url; otherwise use DATABASE_URL from settings.
database_url = context.config.get_main_option("sqlalchemy.url") or get_settings().database_url


def run_migrations_offline() -> None:
    context.configure(
        url=database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = create_engine(database_url, poolclass=pool.NullPool)
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
