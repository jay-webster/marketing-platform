"""API tests for src/api/generate.py — content generation endpoints."""
import json
import uuid
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio

_async = pytest.mark.asyncio(loop_scope="function")

EMAIL_RESULT = {"subject": "Test Subject", "body": "Test body content."}
LINKEDIN_RESULT = {"post_text": "Exciting news! #marketing", "hashtags": ["#marketing"]}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _patch_workers():
    return patch.multiple(
        "utils.queue",
        startup_recovery=AsyncMock(),
        start_queue_workers=AsyncMock(),
        stop_queue_workers=AsyncMock(),
        start_indexing_workers=AsyncMock(),
        stop_indexing_workers=AsyncMock(),
    )


def _patch_generate_email():
    return patch("src.api.generate.generate_content", new=AsyncMock(return_value=EMAIL_RESULT))


def _patch_generate_linkedin():
    return patch("src.api.generate.generate_content", new=AsyncMock(return_value=LINKEDIN_RESULT))


def _patch_no_kb():
    from utils.generator import NoKBContentError
    return patch("src.api.generate.generate_content", side_effect=NoKBContentError("No content"))


# ---------------------------------------------------------------------------
# US1 — Email generation
# ---------------------------------------------------------------------------

@_async
async def test_generate_email_success(async_client, marketer_token):
    with _patch_workers(), _patch_generate_email():
        res = await async_client.post(
            "/api/v1/generate/",
            json={"output_type": "email", "prompt": "Write a nurture email for our prospects."},
            headers={"Authorization": f"Bearer {marketer_token}"},
        )
    assert res.status_code == 200
    data = res.json()["data"]
    assert data["status"] == "completed"
    assert data["output_type"] == "email"
    assert data["result"]["subject"] == EMAIL_RESULT["subject"]
    assert data["result"]["body"] == EMAIL_RESULT["body"]


@_async
async def test_generate_no_kb_content(async_client, marketer_token):
    with _patch_workers(), _patch_no_kb():
        res = await async_client.post(
            "/api/v1/generate/",
            json={"output_type": "email", "prompt": "Write about something not in the KB."},
            headers={"Authorization": f"Bearer {marketer_token}"},
        )
    assert res.status_code == 200
    data = res.json()["data"]
    assert data["status"] == "failed"
    assert data["failure_reason"] == "no_kb_content"


@_async
async def test_generate_empty_prompt(async_client, marketer_token):
    res = await async_client.post(
        "/api/v1/generate/",
        json={"output_type": "email", "prompt": "   "},
        headers={"Authorization": f"Bearer {marketer_token}"},
    )
    assert res.status_code == 422


@_async
async def test_generate_prompt_too_long(async_client, marketer_token):
    res = await async_client.post(
        "/api/v1/generate/",
        json={"output_type": "email", "prompt": "x" * 2001},
        headers={"Authorization": f"Bearer {marketer_token}"},
    )
    assert res.status_code == 422


@_async
async def test_generate_unauthenticated(async_client):
    res = await async_client.post(
        "/api/v1/generate/",
        json={"output_type": "email", "prompt": "Write something."},
    )
    assert res.status_code == 401


@_async
async def test_generate_pdf_no_template(async_client, marketer_token):
    res = await async_client.post(
        "/api/v1/generate/",
        json={"output_type": "pdf", "prompt": "Create a one-pager."},
        headers={"Authorization": f"Bearer {marketer_token}"},
    )
    assert res.status_code == 422
    assert res.json()["detail"]["code"] == "MISSING_PDF_TEMPLATE"


# ---------------------------------------------------------------------------
# History scoping and ownership
# ---------------------------------------------------------------------------

@_async
async def test_generate_history_user_scoped(
    async_client, marketer_token, admin_token, marketer_user, admin_user, db_session
):
    from src.models.generation_request import GenerationRequest

    # Create a request owned by marketer
    req = GenerationRequest(
        user_id=marketer_user.id,
        output_type="email",
        prompt="marketer prompt",
        status="completed",
        result_text=json.dumps(EMAIL_RESULT),
    )
    db_session.add(req)
    await db_session.commit()

    # Admin should NOT see marketer's request
    res = await async_client.get(
        "/api/v1/generate/",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert res.status_code == 200
    ids = [item["id"] for item in res.json()["data"]]
    assert str(req.id) not in ids

    # Marketer should see their own request
    res = await async_client.get(
        "/api/v1/generate/",
        headers={"Authorization": f"Bearer {marketer_token}"},
    )
    assert res.status_code == 200
    ids = [item["id"] for item in res.json()["data"]]
    assert str(req.id) in ids


@_async
async def test_generate_delete_own(async_client, marketer_token, marketer_user, db_session):
    from src.models.generation_request import GenerationRequest

    req = GenerationRequest(
        user_id=marketer_user.id,
        output_type="email",
        prompt="test prompt",
        status="completed",
        result_text=json.dumps(EMAIL_RESULT),
    )
    db_session.add(req)
    await db_session.commit()

    res = await async_client.delete(
        f"/api/v1/generate/{req.id}",
        headers={"Authorization": f"Bearer {marketer_token}"},
    )
    assert res.status_code == 204


@_async
async def test_generate_delete_other_user(
    async_client, marketer_token, admin_user, db_session
):
    from src.models.generation_request import GenerationRequest

    # Request owned by admin
    req = GenerationRequest(
        user_id=admin_user.id,
        output_type="email",
        prompt="admin prompt",
        status="completed",
        result_text=json.dumps(EMAIL_RESULT),
    )
    db_session.add(req)
    await db_session.commit()

    # Marketer tries to delete admin's request
    res = await async_client.delete(
        f"/api/v1/generate/{req.id}",
        headers={"Authorization": f"Bearer {marketer_token}"},
    )
    assert res.status_code == 404


# ---------------------------------------------------------------------------
# Additional coverage from Phase 6 (US4)
# ---------------------------------------------------------------------------

@_async
async def test_generate_history_pagination(async_client, marketer_token, marketer_user, db_session):
    from src.models.generation_request import GenerationRequest

    for i in range(5):
        db_session.add(GenerationRequest(
            user_id=marketer_user.id,
            output_type="email",
            prompt=f"prompt {i}",
            status="completed",
            result_text=json.dumps(EMAIL_RESULT),
        ))
    await db_session.commit()

    res = await async_client.get(
        "/api/v1/generate/?limit=2&offset=0",
        headers={"Authorization": f"Bearer {marketer_token}"},
    )
    assert res.status_code == 200
    assert len(res.json()["data"]) == 2

    res2 = await async_client.get(
        "/api/v1/generate/?limit=2&offset=2",
        headers={"Authorization": f"Bearer {marketer_token}"},
    )
    assert res2.status_code == 200
    assert len(res2.json()["data"]) == 2


@_async
async def test_generate_get_detail_not_owned(
    async_client, marketer_token, admin_user, db_session
):
    from src.models.generation_request import GenerationRequest

    req = GenerationRequest(
        user_id=admin_user.id,
        output_type="email",
        prompt="admin only",
        status="completed",
        result_text=json.dumps(EMAIL_RESULT),
    )
    db_session.add(req)
    await db_session.commit()

    res = await async_client.get(
        f"/api/v1/generate/{req.id}",
        headers={"Authorization": f"Bearer {marketer_token}"},
    )
    assert res.status_code == 404


@_async
async def test_generate_delete_removes_gcs(async_client, marketer_token, marketer_user, db_session):
    from src.models.generation_request import GenerationRequest

    req = GenerationRequest(
        user_id=marketer_user.id,
        output_type="pdf",
        prompt="pdf prompt",
        pdf_template="one_pager",
        status="completed",
        result_pdf_gcs_name="generated-pdfs/test-id/document.pdf",
    )
    db_session.add(req)
    await db_session.commit()

    with patch("src.api.generate.delete_from_gcs", new=AsyncMock()) as mock_delete:
        res = await async_client.delete(
            f"/api/v1/generate/{req.id}",
            headers={"Authorization": f"Bearer {marketer_token}"},
        )
    assert res.status_code == 204
    mock_delete.assert_called_once()
