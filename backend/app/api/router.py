from fastapi import APIRouter

from app.api.routes.auth import router as auth_router
from app.api.routes.health import router as health_router
from app.api.routes.jobs import router as jobs_router
from app.api.routes.strategies import router as strategies_router

api_router = APIRouter()
# Keep route registration centralized so `app.main` only has to include one
# router. Each route module owns one feature area.
api_router.include_router(health_router)
api_router.include_router(auth_router)
api_router.include_router(jobs_router)
api_router.include_router(strategies_router)
