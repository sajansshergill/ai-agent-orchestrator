from fastapi import APIRouter
from app.api.v1.health import router as health_router
from app.api.v1.tasks import router as tasks_router
from app.api.v1.conversations import router as conversations_router

router = APIRouter()
router.include_router(health_router, tags=["health"])
router.include_router(tasks_router, tags=["tasks"])
router.include_router(conversations_router, tags=["conversations"])
