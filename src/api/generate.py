"""Content generation API — create and manage marketing content generation requests.

CONSTITUTION compliance:
  - AUTH_SAFE   : All routes depend on get_current_user; history and delete are
                  scoped to the requesting user.
  - DRY         : Generation via utils/generator.py; PDF via utils/pdf_renderer.py;
                  GCS via utils/gcs.py; DB via utils/db.py.
  - NON_BLOCKING: All handlers are async; WeasyPrint render runs in asyncio.to_thread.
"""
from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import get_settings
from src.models.brand_image import BrandImage
from src.models.generation_request import GenerationRequest
from src.models.user import User
from utils.auth import get_current_user
from utils.db import get_db
from utils.generator import NoKBContentError, generate_content
from utils.gcs import delete_from_gcs, generate_signed_url

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/generate", tags=["generation"])

_ALLOWED_OUTPUT_TYPES = {"email", "linkedin", "pdf"}
_ALLOWED_PDF_TEMPLATES = {"one_pager", "campaign_brief"}
_MAX_PROMPT_LENGTH = 2000


# -----------------------------------------------------------------
# Request / response models
# -----------------------------------------------------------------

class GenerateRequest(BaseModel):
    output_type: str
    prompt: str
    pdf_template: str | None = None
    image_ids: list[str] | None = None


# -----------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------

def _request_id(request: Request) -> str:
    return getattr(request.state, "request_id", "unknown")


async def _get_owned_request(
    request_id: uuid.UUID,
    user_id: uuid.UUID,
    db: AsyncSession,
) -> GenerationRequest:
    req = await db.get(GenerationRequest, request_id)
    if req is None or req.user_id != user_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "Generation request not found", "code": "NOT_FOUND"},
        )
    return req


async def _result_payload(req: GenerationRequest, settings: Any) -> dict[str, Any]:
    """Build the result dict for a completed request, generating fresh PDF signed URLs."""
    if req.status != "completed":
        return {}

    raw = req.result_text
    if raw:
        try:
            result = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            result = {"body": raw}
    else:
        result = {}

    if req.output_type == "pdf" and req.result_pdf_gcs_name:
        filename = req.result_pdf_gcs_name.rsplit("/", 1)[-1]
        try:
            result["pdf_url"] = await generate_signed_url(
                settings.BRAND_IMAGES_BUCKET,
                req.result_pdf_gcs_name,
                settings.PDF_SIGNED_URL_EXPIRY_SECONDS,
            )
            result["pdf_filename"] = filename
        except Exception:
            logger.warning("Failed to generate signed URL for request %s", req.id)
            result["pdf_url"] = None
            result["pdf_filename"] = filename

    return result


def _list_item(req: GenerationRequest) -> dict[str, Any]:
    return {
        "id": str(req.id),
        "output_type": req.output_type,
        "status": req.status,
        "prompt": req.prompt,
        "failure_reason": req.failure_reason,
        "created_at": req.created_at.isoformat(),
    }


# -----------------------------------------------------------------
# POST /generate — create generation request
# -----------------------------------------------------------------

@router.post("/", status_code=status.HTTP_200_OK)
async def create_generation(
    request: Request,
    body: GenerateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # Validate prompt
    if not body.prompt.strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"error": "Prompt cannot be empty", "code": "EMPTY_PROMPT"},
        )
    if len(body.prompt) > _MAX_PROMPT_LENGTH:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "error": f"Prompt exceeds {_MAX_PROMPT_LENGTH} character limit",
                "code": "PROMPT_TOO_LONG",
            },
        )
    if body.output_type not in _ALLOWED_OUTPUT_TYPES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"error": f"Invalid output_type: {body.output_type}", "code": "INVALID_OUTPUT_TYPE"},
        )
    if body.output_type == "pdf":
        if not body.pdf_template:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={"error": "pdf_template is required for PDF output", "code": "MISSING_PDF_TEMPLATE"},
            )
        if body.pdf_template not in _ALLOWED_PDF_TEMPLATES:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={"error": f"Invalid pdf_template: {body.pdf_template}", "code": "INVALID_PDF_TEMPLATE"},
            )

    # Validate image_ids if provided for PDF
    validated_image_ids: list[str] = []
    if body.output_type == "pdf" and body.image_ids:
        for raw_id in body.image_ids:
            try:
                img_uuid = uuid.UUID(raw_id)
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail={"error": f"Invalid image_id: {raw_id}", "code": "INVALID_IMAGE_ID"},
                )
            img = await db.get(BrandImage, img_uuid)
            if img is None or not img.is_active:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail={"error": f"Brand image not found: {raw_id}", "code": "IMAGE_NOT_FOUND"},
                )
            validated_image_ids.append(str(img_uuid))

    # Create pending record
    gen_req = GenerationRequest(
        user_id=current_user.id,
        output_type=body.output_type,
        prompt=body.prompt,
        pdf_template=body.pdf_template,
        selected_image_ids=validated_image_ids or None,
        status="pending",
    )
    db.add(gen_req)
    await db.commit()
    await db.refresh(gen_req)

    settings = get_settings()

    # Execute generation
    try:
        if body.output_type == "pdf":
            result_data = await _generate_pdf(
                db, gen_req, body.prompt, body.pdf_template, validated_image_ids, settings
            )
        else:
            result_data = await generate_content(db, body.output_type, body.prompt)

        gen_req.result_text = json.dumps(result_data) if body.output_type != "pdf" else None
        gen_req.status = "completed"
        gen_req.updated_at = datetime.now(timezone.utc)
        await db.commit()
        await db.refresh(gen_req)

        result_payload = await _result_payload(gen_req, settings)
        return {
            "data": {**_list_item(gen_req), "result": result_payload},
            "request_id": _request_id(request),
        }

    except NoKBContentError:
        gen_req.status = "failed"
        gen_req.failure_reason = "no_kb_content"
        gen_req.updated_at = datetime.now(timezone.utc)
        await db.commit()
        return {
            "data": _list_item(gen_req),
            "request_id": _request_id(request),
        }

    except Exception as exc:
        logger.exception("Generation failed for request %s: %s", gen_req.id, exc)
        gen_req.status = "failed"
        gen_req.failure_reason = str(exc)[:500]
        gen_req.updated_at = datetime.now(timezone.utc)
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": "Content generation failed", "code": "GENERATION_ERROR"},
        )


async def _generate_pdf(
    db: AsyncSession,
    gen_req: GenerationRequest,
    prompt: str,
    pdf_template: str,
    image_ids: list[str],
    settings: Any,
) -> dict[str, Any]:
    """Run PDF generation pipeline: generate body → render PDF → upload to GCS."""
    from utils.gcs import upload_bytes_to_gcs
    from utils.pdf_renderer import render_pdf

    content = await generate_content(db, "pdf_body", prompt)

    images = []
    if image_ids:
        for raw_id in image_ids:
            img = await db.get(BrandImage, uuid.UUID(raw_id))
            if img and img.is_active:
                images.append({
                    "gcs_object_name": img.gcs_object_name,
                    "display_title": img.display_title or img.filename,
                })

    pdf_bytes = await render_pdf(pdf_template, content, images, settings.BRAND_IMAGES_BUCKET)

    slug = content.get("title", "document").lower().replace(" ", "-")[:40]
    object_name = f"generated-pdfs/{gen_req.id}/{slug}.pdf"

    await upload_bytes_to_gcs(pdf_bytes, settings.BRAND_IMAGES_BUCKET, object_name, "application/pdf")

    gen_req.result_pdf_gcs_name = object_name
    return {}


# -----------------------------------------------------------------
# GET /generate — list history
# -----------------------------------------------------------------

@router.get("/")
async def list_generations(
    request: Request,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    settings = get_settings()

    stmt = (
        select(GenerationRequest)
        .where(GenerationRequest.user_id == current_user.id)
        .order_by(GenerationRequest.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    result = await db.execute(stmt)
    requests = result.scalars().all()

    count_stmt = select(GenerationRequest).where(GenerationRequest.user_id == current_user.id)
    count_result = await db.execute(count_stmt)
    total = len(count_result.scalars().all())

    items = []
    for req in requests:
        item = _list_item(req)
        if req.output_type == "pdf" and req.result_pdf_gcs_name and req.status == "completed":
            try:
                item["pdf_url"] = await generate_signed_url(
                    settings.BRAND_IMAGES_BUCKET,
                    req.result_pdf_gcs_name,
                    settings.PDF_SIGNED_URL_EXPIRY_SECONDS,
                )
            except Exception:
                item["pdf_url"] = None
        items.append(item)

    return {
        "data": items,
        "total": total,
        "limit": limit,
        "offset": offset,
        "request_id": _request_id(request),
    }


# -----------------------------------------------------------------
# GET /generate/{id} — full detail
# -----------------------------------------------------------------

@router.get("/{generation_id}")
async def get_generation(
    request: Request,
    generation_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    settings = get_settings()
    gen_req = await _get_owned_request(generation_id, current_user.id, db)
    result_payload = await _result_payload(gen_req, settings)
    return {
        "data": {**_list_item(gen_req), "result": result_payload},
        "request_id": _request_id(request),
    }


# -----------------------------------------------------------------
# DELETE /generate/{id}
# -----------------------------------------------------------------

@router.delete("/{generation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_generation(
    generation_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    settings = get_settings()
    gen_req = await _get_owned_request(generation_id, current_user.id, db)

    if gen_req.result_pdf_gcs_name:
        await delete_from_gcs(settings.BRAND_IMAGES_BUCKET, gen_req.result_pdf_gcs_name)

    await db.delete(gen_req)
    await db.commit()
