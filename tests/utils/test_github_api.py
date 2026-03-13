"""Unit tests for utils/github_api.py — all GitHub HTTP calls mocked with respx."""
import pytest
import respx
import httpx

from utils.github_api import (
    GitHubUnavailableError,
    GitHubValidationError,
    parse_repository_url,
    scaffold_repository,
    validate_and_check_access,
)

_async = pytest.mark.asyncio(loop_scope="function")

_REPO_URL = "https://github.com/acme/marketing-content"
_TOKEN = "github_pat_testtoken"
_USER_URL = "https://api.github.com/user"
_REPO_API_URL = "https://api.github.com/repos/acme/marketing-content"


# ---------------------------------------------------------------------------
# parse_repository_url
# ---------------------------------------------------------------------------

def test_parse_valid_url():
    owner, repo = parse_repository_url("https://github.com/acme/marketing-content")
    assert owner == "acme"
    assert repo == "marketing-content"


def test_parse_url_strips_git_suffix():
    owner, repo = parse_repository_url("https://github.com/acme/marketing-content.git")
    assert owner == "acme"
    assert repo == "marketing-content"


def test_parse_invalid_scheme_raises():
    with pytest.raises(GitHubValidationError) as exc_info:
        parse_repository_url("http://github.com/acme/repo")
    assert exc_info.value.code == "INVALID_REPOSITORY_URL"


def test_parse_non_github_raises():
    with pytest.raises(GitHubValidationError) as exc_info:
        parse_repository_url("https://gitlab.com/acme/repo")
    assert exc_info.value.code == "INVALID_REPOSITORY_URL"


# ---------------------------------------------------------------------------
# validate_and_check_access — error code mapping
# ---------------------------------------------------------------------------

@_async
@respx.mock
async def test_validate_token_invalid():
    respx.get(_USER_URL).mock(return_value=httpx.Response(401))
    with pytest.raises(GitHubValidationError) as exc_info:
        await validate_and_check_access(_REPO_URL, _TOKEN)
    assert exc_info.value.code == "TOKEN_INVALID"


@_async
@respx.mock
async def test_validate_repo_not_found():
    respx.get(_USER_URL).mock(return_value=httpx.Response(200, json={"login": "testuser"}))
    respx.get(_REPO_API_URL).mock(return_value=httpx.Response(404))
    with pytest.raises(GitHubValidationError) as exc_info:
        await validate_and_check_access(_REPO_URL, _TOKEN)
    assert exc_info.value.code == "REPO_NOT_FOUND"


@_async
@respx.mock
async def test_validate_repo_access_denied():
    respx.get(_USER_URL).mock(return_value=httpx.Response(200, json={"login": "testuser"}))
    respx.get(_REPO_API_URL).mock(return_value=httpx.Response(403))
    with pytest.raises(GitHubValidationError) as exc_info:
        await validate_and_check_access(_REPO_URL, _TOKEN)
    assert exc_info.value.code == "REPO_ACCESS_DENIED"


@_async
@respx.mock
async def test_validate_insufficient_permissions():
    respx.get(_USER_URL).mock(return_value=httpx.Response(200, json={"login": "testuser"}))
    respx.get(_REPO_API_URL).mock(return_value=httpx.Response(200, json={
        "full_name": "acme/marketing-content",
        "permissions": {"admin": False, "push": False, "pull": True},
    }))
    with pytest.raises(GitHubValidationError) as exc_info:
        await validate_and_check_access(_REPO_URL, _TOKEN)
    assert exc_info.value.code == "INSUFFICIENT_PERMISSIONS"
    assert "contents:write" in exc_info.value.missing_permissions


@_async
@respx.mock
async def test_validate_github_server_error_on_user():
    respx.get(_USER_URL).mock(return_value=httpx.Response(503))
    with pytest.raises(GitHubUnavailableError):
        await validate_and_check_access(_REPO_URL, _TOKEN)


@_async
@respx.mock
async def test_validate_github_server_error_on_repo():
    respx.get(_USER_URL).mock(return_value=httpx.Response(200, json={"login": "testuser"}))
    respx.get(_REPO_API_URL).mock(return_value=httpx.Response(500))
    with pytest.raises(GitHubUnavailableError):
        await validate_and_check_access(_REPO_URL, _TOKEN)


@_async
@respx.mock
async def test_validate_timeout_raises_unavailable():
    respx.get(_USER_URL).mock(side_effect=httpx.TimeoutException("timeout"))
    with pytest.raises(GitHubUnavailableError):
        await validate_and_check_access(_REPO_URL, _TOKEN)


@_async
@respx.mock
async def test_validate_happy_path():
    respx.get(_USER_URL).mock(return_value=httpx.Response(200, json={"login": "testuser"}))
    respx.get(_REPO_API_URL).mock(return_value=httpx.Response(200, json={
        "full_name": "acme/marketing-content",
        "permissions": {"admin": False, "push": True, "pull": True},
    }))
    # Should not raise
    await validate_and_check_access(_REPO_URL, _TOKEN)


# ---------------------------------------------------------------------------
# scaffold_repository
# ---------------------------------------------------------------------------

@_async
@respx.mock
async def test_scaffold_creates_missing_folders():
    folders = ["content/campaigns", "content/drafts"]
    for folder in folders:
        path = f"{folder}/.gitkeep"
        respx.get(f"https://api.github.com/repos/acme/marketing-content/contents/{path}").mock(
            return_value=httpx.Response(404)
        )
        respx.put(f"https://api.github.com/repos/acme/marketing-content/contents/{path}").mock(
            return_value=httpx.Response(201, json={"content": {}})
        )
    created, skipped = await scaffold_repository(_REPO_URL, _TOKEN, folders)
    assert created == 2
    assert skipped == 0


@_async
@respx.mock
async def test_scaffold_skips_existing_folders():
    folders = ["content/campaigns", "content/drafts"]
    for folder in folders:
        path = f"{folder}/.gitkeep"
        respx.get(f"https://api.github.com/repos/acme/marketing-content/contents/{path}").mock(
            return_value=httpx.Response(200, json={"name": ".gitkeep"})
        )
    created, skipped = await scaffold_repository(_REPO_URL, _TOKEN, folders)
    assert created == 0
    assert skipped == 2


@_async
@respx.mock
async def test_scaffold_mixed_creates_and_skips():
    # campaigns exists, drafts does not
    respx.get("https://api.github.com/repos/acme/marketing-content/contents/content/campaigns/.gitkeep").mock(
        return_value=httpx.Response(200, json={"name": ".gitkeep"})
    )
    respx.get("https://api.github.com/repos/acme/marketing-content/contents/content/drafts/.gitkeep").mock(
        return_value=httpx.Response(404)
    )
    respx.put("https://api.github.com/repos/acme/marketing-content/contents/content/drafts/.gitkeep").mock(
        return_value=httpx.Response(201, json={"content": {}})
    )
    created, skipped = await scaffold_repository(
        _REPO_URL, _TOKEN, ["content/campaigns", "content/drafts"]
    )
    assert created == 1
    assert skipped == 1


@_async
@respx.mock
async def test_scaffold_timeout_raises_unavailable():
    respx.get(
        "https://api.github.com/repos/acme/marketing-content/contents/content/campaigns/.gitkeep"
    ).mock(side_effect=httpx.TimeoutException("timeout"))
    with pytest.raises(GitHubUnavailableError):
        await scaffold_repository(_REPO_URL, _TOKEN, ["content/campaigns"])
