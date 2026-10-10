"""Seed the DATABASE_URL database with the synthetic Feature 1 fixtures.

Run `alembic -c apps/api/alembic.ini upgrade head` first. Safe to rerun.
"""

import sys
from pathlib import Path

API_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(API_ROOT))

from sqlalchemy.orm import Session  # noqa: E402

from app.core.database import get_engine  # noqa: E402
from app.modules.facilities.seed import load_feature_1_examples  # noqa: E402

with Session(get_engine()) as session:
    load_feature_1_examples(session)
    session.commit()
print("Seeded synthetic Feature 1 facilities, resources and observations.")
