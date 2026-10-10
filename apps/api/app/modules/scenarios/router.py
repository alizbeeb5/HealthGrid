"""Assumptions, immutable snapshots and saved runs. Owner: backend/data.

No endpoints implemented yet.
"""

from fastapi import APIRouter

router = APIRouter(prefix="/scenarios", tags=["scenarios"])
