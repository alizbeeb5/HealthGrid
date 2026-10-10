"""Domain router registration."""

from fastapi import APIRouter

from app.modules.allocation.router import router as allocation_router
from app.modules.capacity.router import router as capacity_router
from app.modules.facilities.router import router as facilities_router
from app.modules.forecasting.router import router as forecasting_router
from app.modules.ingestion.router import router as ingestion_router
from app.modules.intelligence.router import router as intelligence_router
from app.modules.investments.router import router as investments_router
from app.modules.scenarios.router import router as scenarios_router

router = APIRouter()
router.include_router(facilities_router)
router.include_router(ingestion_router)
router.include_router(capacity_router)
router.include_router(forecasting_router)
router.include_router(scenarios_router)
router.include_router(allocation_router)
router.include_router(investments_router)
router.include_router(intelligence_router)
