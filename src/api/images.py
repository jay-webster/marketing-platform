"""Brand image API — list, upload (admin), and delete (admin) brand images.

CONSTITUTION compliance:
  - AUTH_SAFE   : GET requires authentication; POST and DELETE require admin role.
  - DRY         : GCS via utils/gcs.py; DB via utils/db.py; auth via utils/auth.py.
  - NON_BLOCKING: All I/O is async; GCS calls run via asyncio.to_thread in utils/gcs.py.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import get_settings
from src.models.brand_image import BrandImage
from src.models.user import Role, User
from utils.auth import get_current_user, require_role
from utils.db import get_db
from utils.gcs import delete_from_gcs, generate_signed_url, upload_bytes_to_gcs

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/images", tags=["images"])

_ALLOWED_CONTENT_TYPES = {"image/png", "image/jpeg", "image/webp", "image/gif"}
_MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB


def _request_id(request: Request) -> str:
    return getattr(request.state, "request_id", "unknown")


async def _image_response(img: BrandImage, settings) -> dict:
    try:
        thumbnail_url = await generate_signed_url(
            settings.BRAND_IMAGES_BUCKET,
            img.gcs_object_name,
            settings.PDF_SIGNED_URL_EXPIRY_SECONDS,
        )
    except Exception:
        thumbnail_url = None

    return {
        "id": str(img.id),
        "filename": img.filename,
        "display_title": img.display_title or _stem(img.filename),
        "content_type": img.content_type,
        "source": img.source,
        "thumbnail_url": thumbnail_url,
        "created_at": img.created_at.isoformat(),
    }


def _stem(filename: str) -> str:
    """Return filename without extension as a display title."""
    name = filename.rsplit(".", 1)[0] if "." in filename else filename
    return name.replace("-", " ").replace("_", " ").title()


# -----------------------------------------------------------------
# GET /images — list active brand images
# -----------------------------------------------------------------

@router.get("/")
async def list_images(
    request: Request,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    settings = get_settings()

    stmt = (
        select(BrandImage)
        .where(BrandImage.is_active == True)  # noqa: E712
        .order_by(BrandImage.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    result = await db.execute(stmt)
    images = result.scalars().all()

    count_result = await db.execute(
        select(func.count()).select_from(BrandImage).where(BrandImage.is_active == True)  # noqa: E712
    )
    total = count_result.scalar_one()

    items = [await _image_response(img, settings) for img in images]
    return {
        "data": items,
        "total": total,
        "limit": limit,
        "offset": offset,
        "request_id": _request_id(request),
    }


# -----------------------------------------------------------------
# POST /images — upload brand image (admin only)
# -----------------------------------------------------------------

@router.post("/", status_code=status.HTTP_201_CREATED)
async def upload_image(
    request: Request,
    file: UploadFile = File(...),
    display_title: str | None = Form(default=None),
    current_user: User = require_role(Role.ADMIN),
    db: AsyncSession = Depends(get_db),
):
    settings = get_settings()

    content_type = file.content_type or ""
    if content_type not in _ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "error": f"Unsupported file type: {content_type}. Allowed: PNG, JPEG, WEBP, GIF",
                "code": "INVALID_FILE_TYPE",
            },
        )

    data = await file.read()
    if len(data) > _MAX_FILE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"error": "File exceeds 10MB limit", "code": "FILE_TOO_LARGE"},
        )

    image_id = uuid.uuid4()
    safe_filename = (file.filename or "image").replace(" ", "-")
    object_name = f"brand-images/{image_id}/{safe_filename}"

    await upload_bytes_to_gcs(data, settings.BRAND_IMAGES_BUCKET, object_name, content_type)

    img = BrandImage(
        id=image_id,
        filename=safe_filename,
        gcs_object_name=object_name,
        content_type=content_type,
        display_title=display_title,
        source="admin_upload",
        file_size_bytes=len(data),
        is_active=True,
    )
    db.add(img)
    await db.commit()
    await db.refresh(img)

    return {
        "data": await _image_response(img, settings),
        "request_id": _request_id(request),
    }


# -----------------------------------------------------------------
# DELETE /images/{id} — delete brand image (admin only)
# -----------------------------------------------------------------

@router.delete("/{image_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_image(
    image_id: uuid.UUID,
    current_user: User = require_role(Role.ADMIN),
    db: AsyncSession = Depends(get_db),
):
    settings = get_settings()

    img = await db.get(BrandImage, image_id)
    if img is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "Image not found", "code": "NOT_FOUND"},
        )

    await delete_from_gcs(settings.BRAND_IMAGES_BUCKET, img.gcs_object_name)
    await db.delete(img)
    await db.commit()
