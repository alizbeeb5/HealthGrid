from pathlib import Path

from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import create_engine, inspect

import app.modules.allocation.models  # noqa: F401
import app.modules.facilities.models  # noqa: F401
import app.modules.forecasting.models  # noqa: F401
import app.modules.scenarios.models  # noqa: F401
from app.core.database import Base

ALEMBIC_INI = Path(__file__).resolve().parents[1] / "alembic.ini"


def test_migrations_match_models_and_downgrade(tmp_path):
    url = f"sqlite:///{(tmp_path / 'migrated.db').as_posix()}"
    config = Config(str(ALEMBIC_INI))
    config.set_main_option("sqlalchemy.url", url)
    engine = create_engine(url)

    command.upgrade(config, "head")
    with engine.connect() as connection:
        assert compare_metadata(MigrationContext.configure(connection), Base.metadata) == []

    command.downgrade(config, "base")
    assert set(inspect(engine).get_table_names()) == {"alembic_version"}
