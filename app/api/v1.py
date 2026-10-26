from fastapi import APIRouter
from app.routers import auth, project, documents


router = APIRouter(prefix="/v1")
router.include_router(auth.router)
router.include_router(project.router)
router.include_router(documents.router)