"""Import daily history (DailyHistoryImport JSON) into the DATABASE_URL database.

Usage: python apps/api/scripts/import_daily_history.py [path]
Default path: data/synthetic/feature-4/daily-history.json. Run migrations and
seed_feature_1.py first. All-or-nothing; existing days are never overwritten.
"""

import sys
from datetime import UTC, datetime
from pathlib import Path

API_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(API_ROOT))

from sqlalchemy.orm import Session  # noqa: E402

from app.core.database import get_engine  # noqa: E402
from app.modules.forecasting.schemas import DailyHistoryImport  # noqa: E402
from app.modules.forecasting.service import (  # noqa: E402
    HistoryImportError,
    import_daily_history,
)

DEFAULT = API_ROOT.parents[1] / "data" / "synthetic" / "feature-4" / "daily-history.json"

path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT
payload = DailyHistoryImport.model_validate_json(path.read_text(encoding="utf-8"))
with Session(get_engine()) as session:
    try:
        result = import_daily_history(session, payload, datetime.now(UTC))
    except HistoryImportError as error:
        print(f"Import rejected; nothing was written ({len(error.errors)} problems):")
        print("\n".join(f"  {problem}" for problem in error.errors))
        sys.exit(1)
print(f"Imported {path}: {result.model_dump_json()}")
