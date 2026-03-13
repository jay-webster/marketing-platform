"""
Async GitHub REST API client for token validation and repository scaffolding.

Security contract:
  - The `token` parameter is never assigned to a logged variable.
  - Exception messages are sanitised — the token value is stripped before
    being embedded in GitHubValidationError or GitHubUnavailableError.
  - All HTTP calls use a 10-second timeout (FR-3.7 / A-7).
"""

import base64
import logging
import re
from urllib.parse import urlparse

import httpx

logger = logging.getLogger(__name__)

_TIMEOUT = httpx.Timeout(10.0, connect=5.0)
_GITHUB_API = "https://api.github.com"

# Matches https://github.com/owner/repo  (with optional .git suffix)
_REPO_URL_RE = re.compile(
    r"^https://github\.com"
    r"/(?P<owner>[A-Za-z0-9_][A-Za-z0-9_.-]*)"
    r"/(?P<repo>[A-Za-z0-9_][A-Za-z0-9_.-]*?)"
    r"(?:\.git)?$"
)


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class GitHubValidationError(Exception):
    """Raised when GitHub validation fails due to a caller-correctable problem."""

    def __init__(
        self,
        code: str,
        message: str,
        missing_permissions: list[str] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.missing_permissions = missing_permissions or []


class GitHubUnavailableError(Exception):
    """Raised when GitHub is temporarily unreachable (timeout or 5xx)."""


# ---------------------------------------------------------------------------
# URL parsing
# ---------------------------------------------------------------------------

def parse_repository_url(repository_url: str) -> tuple[str, str]:
    """
    Extract (owner, repo) from a GitHub HTTPS URL.

    Raises:
        GitHubValidationError("INVALID_REPOSITORY_URL"): if the URL is not valid.
    """
    url = repository_url.strip().rstrip("/")
    parsed = urlparse(url)

    if parsed.scheme != "https" or parsed.netloc not in ("github.com", "www.github.com"):
        raise GitHubValidationError(
            "INVALID_REPOSITORY_URL",
            "Repository URL must be an HTTPS GitHub URL (https://github.com/owner/repo).",
        )

    match = _REPO_URL_RE.match(url)
    if not match:
        raise GitHubValidationError(
            "INVALID_REPOSITORY_URL",
            "Repository URL must follow the format https://github.com/owner/repo.",
        )

    return match.group("owner"), match.group("repo")


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

async def validate_and_check_access(repository_url: str, token: str) -> None:
    """
    Two-step GitHub validation:

    1. GET /user — confirms the token is recognised by GitHub.
    2. GET /repos/{owner}/{repo} — confirms the repo exists and the token
       has push (write) access.

    Raises:
        GitHubValidationError: with a specific error code on any validation failure.
        GitHubUnavailableError: on timeout or GitHub 5xx responses.
    """
    owner, repo = parse_repository_url(repository_url)
    headers = {"Authorization": f"token {token}", "Accept": "application/vnd.github+json"}

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            # Step 1: verify token is recognised
            user_resp = await client.get(f"{_GITHUB_API}/user", headers=headers)

            if user_resp.status_code == 401:
                raise GitHubValidationError(
                    "TOKEN_INVALID",
                    "The token was not recognised by GitHub. Verify the token is valid and has not been revoked.",
                )
            if user_resp.status_code >= 500:
                raise GitHubUnavailableError(
                    "GitHub returned a server error during token validation."
                )

            # Step 2: verify repo access and push permission
            repo_resp = await client.get(
                f"{_GITHUB_API}/repos/{owner}/{repo}", headers=headers
            )

            if repo_resp.status_code == 404:
                raise GitHubValidationError(
                    "REPO_NOT_FOUND",
                    f"The repository '{repository_url}' could not be found or is not accessible with this token.",
                )
            if repo_resp.status_code == 403:
                raise GitHubValidationError(
                    "REPO_ACCESS_DENIED",
                    f"The token does not grant access to '{repository_url}'.",
                )
            if repo_resp.status_code >= 500:
                raise GitHubUnavailableError(
                    "GitHub returned a server error while checking repository access."
                )

            repo_data = repo_resp.json()
            permissions = repo_data.get("permissions", {})
            if not permissions.get("push", False):
                raise GitHubValidationError(
                    "INSUFFICIENT_PERMISSIONS",
                    "The token is valid but does not have write access to this repository.",
                    missing_permissions=["contents:write"],
                )

    except httpx.TimeoutException:
        raise GitHubUnavailableError(
            "GitHub could not be reached within the timeout period. Please try again shortly."
        )
    except httpx.RequestError as exc:
        raise GitHubUnavailableError(f"GitHub could not be reached: {type(exc).__name__}") from exc


# ---------------------------------------------------------------------------
# Scaffolding
# ---------------------------------------------------------------------------

async def scaffold_repository(
    repository_url: str,
    token: str,
    folders: list[str],
) -> tuple[int, int]:
    """
    Create .gitkeep files for each folder path that does not yet exist in the repo.

    GitHub does not support empty directories. A .gitkeep placeholder file is
    the universal convention for establishing a folder path (see research.md Decision 3).

    Returns:
        (folders_created, folders_skipped)

    Raises:
        GitHubUnavailableError: on timeout or GitHub 5xx.
    """
    owner, repo = parse_repository_url(repository_url)
    headers = {"Authorization": f"token {token}", "Accept": "application/vnd.github+json"}
    created = 0
    skipped = 0

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            for folder in folders:
                gitkeep_path = f"{folder}/.gitkeep"
                check_url = f"{_GITHUB_API}/repos/{owner}/{repo}/contents/{gitkeep_path}"

                check_resp = await client.get(check_url, headers=headers)

                if check_resp.status_code == 200:
                    skipped += 1
                    continue

                if check_resp.status_code >= 500:
                    raise GitHubUnavailableError(
                        f"GitHub returned a server error while checking '{folder}'."
                    )

                # 404 → create the .gitkeep file
                create_resp = await client.put(
                    check_url,
                    headers=headers,
                    json={
                        "message": f"scaffold: create {folder}/",
                        "content": base64.b64encode(b"").decode(),
                    },
                )

                if create_resp.status_code in (200, 201):
                    created += 1
                elif create_resp.status_code == 422:
                    # File already exists (race condition) — treat as skipped
                    skipped += 1
                elif create_resp.status_code >= 500:
                    raise GitHubUnavailableError(
                        f"GitHub returned a server error while creating '{folder}'."
                    )
                else:
                    logger.warning(
                        "Unexpected status %d creating '%s'",
                        create_resp.status_code,
                        folder,
                    )

    except httpx.TimeoutException:
        raise GitHubUnavailableError(
            "GitHub could not be reached during scaffolding. Please try again shortly."
        )
    except httpx.RequestError as exc:
        raise GitHubUnavailableError(f"GitHub could not be reached: {type(exc).__name__}") from exc

    return created, skipped
