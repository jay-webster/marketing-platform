from fastapi import APIRouter

from src.config import settings

router = APIRouter(tags=["system"])


@router.get("/health")
async def health():
    return {"status": "ok", "version": settings.APP_VERSION}
