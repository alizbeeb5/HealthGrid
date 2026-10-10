"""Create/resume an isolated Beirut rehearsal and serve its API. No paid AI calls."""

import argparse
import os
import sys
from datetime import datetime
from pathlib import Path


def main():
    ROOT = Path(__file__).resolve().parents[3]
    sys.path.insert(0, str(ROOT / "apps/api"))
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--fresh",
        action="store_true",
        help="Create a new rehearsal file, preserving existing runs.",
    )
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    folder = ROOT / "work/beirut-demo"
    folder.mkdir(parents=True, exist_ok=True)
    active = folder / "active-path.txt"
    if args.fresh or not active.exists():
        path = folder / f"exercise-{datetime.now().strftime('%Y%m%d-%H%M%S-%f')}.sqlite"
    else:
        path = Path(active.read_text().strip()).resolve()
        if path.parent != folder.resolve():
            raise SystemExit("Invalid saved exercise path.")
    os.environ["DATABASE_URL"] = f"sqlite:///{path}"
    os.environ["DEMO_SCENARIO"] = "beirut"
    # Exercise mode does not automatically enable external AI providers.
    from alembic import command
    from alembic.config import Config
    from sqlalchemy.orm import Session

    from app.core.database import get_engine
    from app.modules.demo.service import seed

    config = Config(str(ROOT / "apps/api/alembic.ini"))
    command.upgrade(config, "head")
    with get_engine().connect() as connection:
        connection.exec_driver_sql("BEGIN IMMEDIATE")
        try:
            with Session(bind=connection, join_transaction_mode="create_savepoint") as db:
                exercise = seed(db)
            connection.commit()
        except Exception:
            connection.rollback()
            raise
    active.write_text(str(path) + "\n")
    print(f"Beirut exercise ready: {exercise.phase}; clock {exercise.clock}; database {path}")
    if not args.prepare_only:
        import uvicorn

        uvicorn.run("app.main:app", host="127.0.0.1", port=args.port)


if __name__ == "__main__":
    main()
