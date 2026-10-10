from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

import app.modules.allocation.models  # noqa: F401
import app.modules.facilities.models  # noqa: F401
import app.modules.forecasting.models  # noqa: F401
import app.modules.investments.models  # noqa: F401
import app.modules.scenarios.models  # noqa: F401
from app.core.database import Base, get_session
from app.main import app
from app.modules.facilities.router import server_now
from app.modules.facilities.seed import load_feature_1_examples

# The as_of time used by the shared fixtures.
FIXTURE_NOW = datetime(2026, 10, 10, 9, 0, tzinfo=UTC)


class Clock:
    def __init__(self) -> None:
        self.now = FIXTURE_NOW

    def __call__(self) -> datetime:
        return self.now


@pytest.fixture
def engine() -> Engine:
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    event.listen(engine, "connect", lambda conn, _: conn.execute("PRAGMA foreign_keys=ON"))
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        load_feature_1_examples(session)
        session.commit()
    return engine


@pytest.fixture
def clock() -> Clock:
    return Clock()


@pytest.fixture
def client(engine: Engine, clock: Clock) -> Iterator[TestClient]:
    def session() -> Iterator[Session]:
        with Session(engine) as db:
            yield db

    app.dependency_overrides[get_session] = session
    app.dependency_overrides[server_now] = clock
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
