from fastapi import APIRouter
from app.routers import auth, project


router = APIRouter(prefix="/v1")
router.include_router(auth.router)
router.include_router(project.router)