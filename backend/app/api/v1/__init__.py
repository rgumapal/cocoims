"""Aggregates every v1 router into one for app.main to include."""
from fastapi import APIRouter

from app.api.v1.counts import router as counts_router
from app.api.v1.items import router as items_router
from app.api.v1.locations import router as locations_router
from app.api.v1.receiving import router as receiving_router
from app.api.v1.refdata import router as refdata_router
from app.api.v1.sales import router as sales_router
from app.api.v1.stock import router as stock_router
from app.api.v1.transfers import router as transfers_router
from app.api.v1.users import router as users_router
from app.api.v1.waste import router as waste_router

router = APIRouter()
router.include_router(items_router)
router.include_router(locations_router)
router.include_router(refdata_router)
router.include_router(stock_router)
router.include_router(receiving_router)
router.include_router(sales_router)
router.include_router(waste_router)
router.include_router(transfers_router)
router.include_router(counts_router)
router.include_router(users_router)
