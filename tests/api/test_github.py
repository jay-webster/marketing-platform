"""Integration tests for /api/v1/github/* endpoints."""
import pytest
import respx
import httpx
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from src.models import GitHubConnection, RepoStructureConfig, ScaffoldingRun

pytestmark = pytest.mark.asyncio

_REPO_URL = "https://github.com/acme/marketing-content"
_TOKEN = "github_pat_validtoken"
_USER_URL = "https://api.github.com/user"
_REPO_API_URL = "https://api.github.com/repos/acme/marketing-content"
_CONTENTS_BASE = "https://api.github.com/repos/acme/marketing-content/contents"

_DEFAULT_FOLDERS = [
    "content/campaigns",
    "content/assets/images",
    "content/assets/documents",
    "content/templates",
    "content/drafts",
    "content/published",
]


# ---------------------------------------------------------------------------
# Security helper
# ---------------------------------------------------------------------------

def assert_no_token(response: httpx.Response, token: str = _TOKEN) -> None:
    """Assert token value never appears in the response body."""
    assert token not in response.text, (
        f"Token value found in response body! This is a security violation.\n"
        f"Response: {response.text[:500]}"
    )


# ---------------------------------------------------------------------------
# respx helpers
# ---------------------------------------------------------------------------

def mock_github_valid(owner: str = "acme", repo: str = "marketing-content"):
    respx.get(_USER_URL).mock(return_value=httpx.Response(200, json={"login": "testuser"}))
    respx.get(f"https://api.github.com/repos/{owner}/{repo}").mock(
        return_value=httpx.Response(200, json={
            "full_name": f"{owner}/{repo}",
            "permissions": {"admin": False, "push": True, "pull": True},
        })
    )


def mock_scaffold_all_new(folders: list[str], owner: str = "acme", repo: str = "marketing-content"):
    for folder in folders:
        path = f"{folder}/.gitkeep"
        respx.get(f"https://api.github.com/repos/{owner}/{repo}/contents/{path}").mock(
            return_value=httpx.Response(404)
        )
        respx.put(f"https://api.github.com/repos/{owner}/{repo}/contents/{path}").mock(
            return_value=httpx.Response(201, json={"content": {}})
        )


def mock_scaffold_all_existing(folders: list[str], owner: str = "acme", repo: str = "marketing-content"):
    for folder in folders:
        path = f"{folder}/.gitkeep"
        respx.get(f"https://api.github.com/repos/{owner}/{repo}/contents/{path}").mock(
            return_value=httpx.Response(200, json={"name": ".gitkeep"})
        )


# ---------------------------------------------------------------------------
# POST /connect — US1
# ---------------------------------------------------------------------------

@respx.mock
async def test_connect_happy_path(
    async_client: AsyncClient,
    admin_token: str,
    db_session: AsyncSession,
):
    mock_github_valid()
    mock_scaffold_all_new(_DEFAULT_FOLDERS)

    resp = await async_client.post(
        "/api/v1/github/connect",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"repository_url": _REPO_URL, "token": _TOKEN},
    )
    assert resp.status_code == 201
    data = resp.json()["data"]
    assert data["repository_url"] == _REPO_URL
    assert data["status"] == "active"
    assert data["scaffolding"]["outcome"] == "success"
    assert data["scaffolding"]["folders_created"] == len(_DEFAULT_FOLDERS)
    assert data["scaffolding"]["folders_skipped"] == 0
    assert_no_token(resp)


@respx.mock
async def test_connect_token_invalid(
    async_client: AsyncClient,
    admin_token: str,
    db_session: AsyncSession,
):
    respx.get(_USER_URL).mock(return_value=httpx.Response(401))

    resp = await async_client.post(
        "/api/v1/github/connect",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"repository_url": _REPO_URL, "token": "bad_token"},
    )
    assert resp.status_code == 422
    assert resp.json()["detail"]["code"] == "TOKEN_INVALID"
    assert_no_token(resp, token="bad_token")

    # Nothing stored
    conn = await db_session.scalar(select(GitHubConnection))
    assert conn is None


@respx.mock
async def test_connect_repo_not_found(
    async_client: AsyncClient,
    admin_token: str,
    db_session: AsyncSession,
):
    respx.get(_USER_URL).mock(return_value=httpx.Response(200, json={"login": "testuser"}))
    respx.get(_REPO_API_URL).mock(return_value=httpx.Response(404))

    resp = await async_client.post(
        "/api/v1/github/connect",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"repository_url": _REPO_URL, "token": _TOKEN},
    )
    assert resp.status_code == 422
    assert resp.json()["detail"]["code"] == "REPO_NOT_FOUND"
    assert_no_token(resp)

    conn = await db_session.scalar(select(GitHubConnection))
    assert conn is None


@respx.mock
async def test_connect_insufficient_permissions(
    async_client: AsyncClient,
    admin_token: str,
    db_session: AsyncSession,
):
    respx.get(_USER_URL).mock(return_value=httpx.Response(200, json={"login": "testuser"}))
    respx.get(_REPO_API_URL).mock(return_value=httpx.Response(200, json={
        "full_name": "acme/marketing-content",
        "permissions": {"admin": False, "push": False, "pull": True},
    }))

    resp = await async_client.post(
        "/api/v1/github/connect",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"repository_url": _REPO_URL, "token": _TOKEN},
    )
    assert resp.status_code == 422
    assert resp.json()["detail"]["code"] == "INSUFFICIENT_PERMISSIONS"
    assert "contents:write" in resp.json()["detail"]["missing_permissions"]
    assert_no_token(resp)

    conn = await db_session.scalar(select(GitHubConnection))
    assert conn is None


@respx.mock
async def test_connect_github_unavailable(
    async_client: AsyncClient,
    admin_token: str,
    db_session: AsyncSession,
):
    respx.get(_USER_URL).mock(side_effect=httpx.TimeoutException("timeout"))

    resp = await async_client.post(
        "/api/v1/github/connect",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"repository_url": _REPO_URL, "token": _TOKEN},
    )
    assert resp.status_code == 503
    assert resp.json()["detail"]["code"] == "GITHUB_UNAVAILABLE"

    conn = await db_session.scalar(select(GitHubConnection))
    assert conn is None


@respx.mock
async def test_connect_duplicate_returns_409(
    async_client: AsyncClient,
    admin_token: str,
    db_session: AsyncSession,
):
    # First connect
    mock_github_valid()
    mock_scaffold_all_new(_DEFAULT_FOLDERS)
    resp1 = await async_client.post(
        "/api/v1/github/connect",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"repository_url": _REPO_URL, "token": _TOKEN},
    )
    assert resp1.status_code == 201

    # Second connect attempt
    resp2 = await async_client.post(
        "/api/v1/github/connect",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"repository_url": _REPO_URL, "token": _TOKEN},
    )
    assert resp2.status_code == 409
    assert resp2.json()["detail"]["code"] == "CONNECTION_ALREADY_EXISTS"


async def test_connect_non_admin_returns_403(
    async_client: AsyncClient,
    marketer_token: str,
):
    resp = await async_client.post(
        "/api/v1/github/connect",
        headers={"Authorization": f"Bearer {marketer_token}"},
        json={"repository_url": _REPO_URL, "token": _TOKEN},
    )
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# GET /connection — US2
# ---------------------------------------------------------------------------

@respx.mock
async def test_get_connection_returns_status(
    async_client: AsyncClient,
    admin_token: str,
    db_session: AsyncSession,
):
    mock_github_valid()
    mock_scaffold_all_new(_DEFAULT_FOLDERS)
    await async_client.post(
        "/api/v1/github/connect",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"repository_url": _REPO_URL, "token": _TOKEN},
    )

    resp = await async_client.get(
        "/api/v1/github/connection",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["status"] == "active"
    assert data["repository_url"] == _REPO_URL
    assert data["token_on_file"] is True
    assert "encrypted_token" not in data
    assert_no_token(resp)


async def test_get_connection_none_returns_404(
    async_client: AsyncClient,
    admin_token: str,
):
    resp = await async_client.get(
        "/api/v1/github/connection",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 404
    assert resp.json()["detail"]["code"] == "NO_CONNECTION"


async def test_get_connection_non_admin_403(
    async_client: AsyncClient,
    marketer_token: str,
):
    resp = await async_client.get(
        "/api/v1/github/connection",
        headers={"Authorization": f"Bearer {marketer_token}"},
    )
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# PATCH /connection/token — US2
# ---------------------------------------------------------------------------

@respx.mock
async def test_rotate_token_happy_path(
    async_client: AsyncClient,
    admin_token: str,
    db_session: AsyncSession,
):
    # Setup: connect first
    mock_github_valid()
    mock_scaffold_all_new(_DEFAULT_FOLDERS)
    await async_client.post(
        "/api/v1/github/connect",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"repository_url": _REPO_URL, "token": _TOKEN},
    )

    # Rotate
    new_token = "github_pat_newtoken"
    mock_github_valid()
    resp = await async_client.patch(
        "/api/v1/github/connection/token",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"token": new_token},
    )
    assert resp.status_code == 200
    assert "last_validated_at" in resp.json()["data"]
    assert_no_token(resp, token=new_token)


@respx.mock
async def test_rotate_token_bad_token_leaves_existing_unchanged(
    async_client: AsyncClient,
    admin_token: str,
    db_session: AsyncSession,
):
    # Setup: connect first
    mock_github_valid()
    mock_scaffold_all_new(_DEFAULT_FOLDERS)
    await async_client.post(
        "/api/v1/github/connect",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"repository_url": _REPO_URL, "token": _TOKEN},
    )

    # Get current encrypted token
    conn_before = await db_session.scalar(select(GitHubConnection))
    old_encrypted = conn_before.encrypted_token

    # Attempt rotation with bad token
    respx.get(_USER_URL).mock(return_value=httpx.Response(401))
    resp = await async_client.patch(
        "/api/v1/github/connection/token",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"token": "bad_token"},
    )
    assert resp.status_code == 422

    # Existing token unchanged
    await db_session.refresh(conn_before)
    assert conn_before.encrypted_token == old_encrypted


async def test_rotate_token_no_connection_404(
    async_client: AsyncClient,
    admin_token: str,
):
    resp = await async_client.patch(
        "/api/v1/github/connection/token",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"token": _TOKEN},
    )
    assert resp.status_code == 404
    assert resp.json()["detail"]["code"] == "NO_CONNECTION"


async def test_rotate_token_non_admin_403(
    async_client: AsyncClient,
    marketer_token: str,
):
    resp = await async_client.patch(
        "/api/v1/github/connection/token",
        headers={"Authorization": f"Bearer {marketer_token}"},
        json={"token": _TOKEN},
    )
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# DELETE /connection — US2
# ---------------------------------------------------------------------------

@respx.mock
async def test_disconnect_happy_path(
    async_client: AsyncClient,
    admin_token: str,
    db_session: AsyncSession,
):
    mock_github_valid()
    mock_scaffold_all_new(_DEFAULT_FOLDERS)
    await async_client.post(
        "/api/v1/github/connect",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"repository_url": _REPO_URL, "token": _TOKEN},
    )

    resp = await async_client.delete(
        "/api/v1/github/connection",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 204

    conn = await db_session.scalar(select(GitHubConnection))
    assert conn.status == "inactive"


async def test_disconnect_no_connection_404(
    async_client: AsyncClient,
    admin_token: str,
):
    resp = await async_client.delete(
        "/api/v1/github/connection",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 404
    assert resp.json()["detail"]["code"] == "NO_CONNECTION"


async def test_disconnect_non_admin_403(
    async_client: AsyncClient,
    marketer_token: str,
):
    resp = await async_client.delete(
        "/api/v1/github/connection",
        headers={"Authorization": f"Bearer {marketer_token}"},
    )
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# POST /scaffold — US3
# ---------------------------------------------------------------------------

@respx.mock
async def test_scaffold_happy_path(
    async_client: AsyncClient,
    admin_token: str,
    db_session: AsyncSession,
):
    # Connect first (scaffold happens automatically on connect)
    mock_github_valid()
    mock_scaffold_all_new(_DEFAULT_FOLDERS)
    await async_client.post(
        "/api/v1/github/connect",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"repository_url": _REPO_URL, "token": _TOKEN},
    )

    # Re-scaffold — all folders already exist
    mock_scaffold_all_existing(_DEFAULT_FOLDERS)
    resp = await async_client.post(
        "/api/v1/github/scaffold",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["outcome"] == "success"
    assert data["folders_created"] == 0
    assert data["folders_skipped"] == len(_DEFAULT_FOLDERS)


@respx.mock
async def test_scaffold_idempotent(
    async_client: AsyncClient,
    admin_token: str,
    db_session: AsyncSession,
):
    mock_github_valid()
    mock_scaffold_all_new(_DEFAULT_FOLDERS)
    await async_client.post(
        "/api/v1/github/connect",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"repository_url": _REPO_URL, "token": _TOKEN},
    )

    # Run scaffold twice — second run finds all folders existing
    mock_scaffold_all_existing(_DEFAULT_FOLDERS)
    resp1 = await async_client.post(
        "/api/v1/github/scaffold",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp1.status_code == 200
    assert resp1.json()["data"]["folders_created"] == 0

    mock_scaffold_all_existing(_DEFAULT_FOLDERS)
    resp2 = await async_client.post(
        "/api/v1/github/scaffold",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp2.status_code == 200
    assert resp2.json()["data"]["folders_created"] == 0


async def test_scaffold_no_connection_404(
    async_client: AsyncClient,
    admin_token: str,
):
    resp = await async_client.post(
        "/api/v1/github/scaffold",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 404
    assert resp.json()["detail"]["code"] == "NO_CONNECTION"


async def test_scaffold_non_admin_403(
    async_client: AsyncClient,
    marketer_token: str,
):
    resp = await async_client.post(
        "/api/v1/github/scaffold",
        headers={"Authorization": f"Bearer {marketer_token}"},
    )
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# GET /config — US3
# ---------------------------------------------------------------------------

async def test_get_config_returns_default(
    async_client: AsyncClient,
    admin_token: str,
    db_session: AsyncSession,
):
    # Seed default config directly
    config = RepoStructureConfig(
        folders={"folders": _DEFAULT_FOLDERS},
        is_default=True,
    )
    db_session.add(config)
    await db_session.commit()

    resp = await async_client.get(
        "/api/v1/github/config",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["folders"] == _DEFAULT_FOLDERS
    assert data["is_default"] is True


async def test_get_config_non_admin_403(
    async_client: AsyncClient,
    marketer_token: str,
):
    resp = await async_client.get(
        "/api/v1/github/config",
        headers={"Authorization": f"Bearer {marketer_token}"},
    )
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# PUT /config — US3
# ---------------------------------------------------------------------------

async def test_update_config_valid(
    async_client: AsyncClient,
    admin_token: str,
):
    new_folders = ["campaigns/q1", "campaigns/q2", "assets/logos"]
    resp = await async_client.put(
        "/api/v1/github/config",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"folders": new_folders},
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["folders"] == new_folders
    assert resp.json()["data"]["is_default"] is False


async def test_update_config_empty_folders_400(
    async_client: AsyncClient,
    admin_token: str,
):
    resp = await async_client.put(
        "/api/v1/github/config",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"folders": []},
    )
    assert resp.status_code == 400
    assert resp.json()["detail"]["code"] == "CONFIG_INVALID"


async def test_update_config_path_traversal_400(
    async_client: AsyncClient,
    admin_token: str,
):
    resp = await async_client.put(
        "/api/v1/github/config",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"folders": ["content/../../../etc"]},
    )
    assert resp.status_code == 400
    assert resp.json()["detail"]["code"] == "CONFIG_INVALID"


async def test_update_config_leading_slash_400(
    async_client: AsyncClient,
    admin_token: str,
):
    resp = await async_client.put(
        "/api/v1/github/config",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"folders": ["/content/campaigns"]},
    )
    assert resp.status_code == 400
    assert resp.json()["detail"]["code"] == "CONFIG_INVALID"


async def test_update_config_non_admin_403(
    async_client: AsyncClient,
    marketer_token: str,
):
    resp = await async_client.put(
        "/api/v1/github/config",
        headers={"Authorization": f"Bearer {marketer_token}"},
        json={"folders": ["content/campaigns"]},
    )
    assert resp.status_code == 403
