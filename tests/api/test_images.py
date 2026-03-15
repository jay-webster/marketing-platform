"""API tests for src/api/images.py — brand image endpoints."""
import io
import uuid
from unittest.mock import AsyncMock, patch

import pytest

_async = pytest.mark.asyncio(loop_scope="function")

# Minimal valid 1x1 PNG bytes
_TINY_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00"
    b"\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
)


def _patch_workers():
    return patch.multiple(
        "utils.queue",
        startup_recovery=AsyncMock(),
        start_queue_workers=AsyncMock(),
        stop_queue_workers=AsyncMock(),
        start_indexing_workers=AsyncMock(),
        stop_indexing_workers=AsyncMock(),
    )


def _patch_gcs_upload():
    return patch("src.api.images.upload_bytes_to_gcs", new=AsyncMock(return_value="brand-images/test/img.png"))


def _patch_gcs_delete():
    return patch("src.api.images.delete_from_gcs", new=AsyncMock())


def _patch_gcs_signed_url():
    return patch("src.api.images.generate_signed_url", new=AsyncMock(return_value="https://signed.url/img.png"))


# ---------------------------------------------------------------------------
# GET /images — list
# ---------------------------------------------------------------------------

@_async
async def test_list_images_authenticated(async_client, marketer_token):
    with _patch_workers(), _patch_gcs_signed_url():
        res = await async_client.get(
            "/api/v1/images/",
            headers={"Authorization": f"Bearer {marketer_token}"},
        )
    assert res.status_code == 200
    assert "data" in res.json()
    assert isinstance(res.json()["data"], list)


@_async
async def test_list_images_unauthenticated(async_client):
    res = await async_client.get("/api/v1/images/")
    assert res.status_code == 401


# ---------------------------------------------------------------------------
# POST /images — upload
# ---------------------------------------------------------------------------

@_async
async def test_upload_image_admin_only(async_client, marketer_token):
    res = await async_client.post(
        "/api/v1/images/",
        headers={"Authorization": f"Bearer {marketer_token}"},
        files={"file": ("test.png", io.BytesIO(_TINY_PNG), "image/png")},
    )
    assert res.status_code == 403


@_async
async def test_upload_image_admin_success(async_client, admin_token):
    with _patch_workers(), _patch_gcs_upload(), _patch_gcs_signed_url():
        res = await async_client.post(
            "/api/v1/images/",
            headers={"Authorization": f"Bearer {admin_token}"},
            files={"file": ("hero.png", io.BytesIO(_TINY_PNG), "image/png")},
        )
    assert res.status_code == 201
    data = res.json()["data"]
    assert data["filename"] == "hero.png"
    assert data["content_type"] == "image/png"
    assert data["source"] == "admin_upload"


@_async
async def test_upload_image_invalid_type(async_client, admin_token):
    with _patch_workers():
        res = await async_client.post(
            "/api/v1/images/",
            headers={"Authorization": f"Bearer {admin_token}"},
            files={"file": ("doc.pdf", io.BytesIO(b"%PDF-1.4"), "application/pdf")},
        )
    assert res.status_code == 422
    assert res.json()["detail"]["code"] == "INVALID_FILE_TYPE"


@_async
async def test_upload_image_too_large(async_client, admin_token):
    big_data = b"x" * (10 * 1024 * 1024 + 1)
    with _patch_workers():
        res = await async_client.post(
            "/api/v1/images/",
            headers={"Authorization": f"Bearer {admin_token}"},
            files={"file": ("big.png", io.BytesIO(big_data), "image/png")},
        )
    assert res.status_code == 422
    assert res.json()["detail"]["code"] == "FILE_TOO_LARGE"


# ---------------------------------------------------------------------------
# DELETE /images/{id}
# ---------------------------------------------------------------------------

@_async
async def test_delete_image_admin_only(async_client, marketer_token):
    fake_id = uuid.uuid4()
    res = await async_client.delete(
        f"/api/v1/images/{fake_id}",
        headers={"Authorization": f"Bearer {marketer_token}"},
    )
    assert res.status_code == 403


@_async
async def test_delete_image_not_found(async_client, admin_token):
    with _patch_workers():
        res = await async_client.delete(
            f"/api/v1/images/{uuid.uuid4()}",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
    assert res.status_code == 404


@_async
async def test_delete_image_success(async_client, admin_token, db_session):
    from src.models.brand_image import BrandImage

    img = BrandImage(
        filename="test.png",
        gcs_object_name=f"brand-images/{uuid.uuid4()}/test.png",
        content_type="image/png",
        source="admin_upload",
        is_active=True,
    )
    db_session.add(img)
    await db_session.commit()

    with _patch_workers(), _patch_gcs_delete():
        res = await async_client.delete(
            f"/api/v1/images/{img.id}",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
    assert res.status_code == 204
