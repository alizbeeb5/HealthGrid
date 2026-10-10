from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_session
from app.modules.demo import service
from app.modules.demo.schemas import AdvanceExercise, ExerciseContext

router = APIRouter(prefix="/demo", tags=["exercise"])


@router.get("", operation_id="get_exercise_context")
def get_context(db: Session = Depends(get_session)) -> ExerciseContext:
    return service.context(db)


@router.post("/advance", operation_id="advance_exercise")
def advance(request: AdvanceExercise, db: Session = Depends(get_session)) -> ExerciseContext:
    service.require_exercise(db)
    # Demo mode is restricted to SQLite. Explicit BEGIN prevents savepoint release
    # from committing the domain services ahead of the outer stage transaction.
    with db.get_bind().connect() as connection:
        connection.exec_driver_sql("BEGIN IMMEDIATE")
        try:
            with Session(bind=connection, join_transaction_mode="create_savepoint") as stage:
                result = service.advance(stage, request)
            connection.commit()
            return result
        except Exception:
            connection.rollback()
            raise
