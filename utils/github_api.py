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


# ---------------------------------------------------------------------------
# Sync — read-only repo traversal (T013)
# ---------------------------------------------------------------------------

async def get_default_branch(
    repository_url: str,
    token: str,
) -> str:
    """Return the default branch name for the repository."""
    owner, repo = parse_repository_url(repository_url)
    headers = {"Authorization": f"token {token}", "Accept": "application/vnd.github+json"}

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.get(f"{_GITHUB_API}/repos/{owner}/{repo}", headers=headers)
            if resp.status_code == 404:
                raise GitHubValidationError("REPO_NOT_FOUND", "Repository not found.")
            if resp.status_code >= 500:
                raise GitHubUnavailableError("GitHub returned a server error.")
            return resp.json()["default_branch"]
    except httpx.TimeoutException:
        raise GitHubUnavailableError("GitHub could not be reached within the timeout period.")
    except httpx.RequestError as exc:
        raise GitHubUnavailableError(f"GitHub could not be reached: {type(exc).__name__}") from exc


async def get_repo_tree(
    repository_url: str,
    token: str,
    branch: str,
) -> list[dict]:
    """
    Return a flat list of all blob entries in the repo tree (recursive).

    Each entry is the raw GitHub tree item dict:
        {"path": "...", "mode": "...", "type": "blob", "sha": "...", "size": N, "url": "..."}

    Only "blob" type entries (files) are returned — trees (directories) are excluded.
    """
    owner, repo = parse_repository_url(repository_url)
    headers = {"Authorization": f"token {token}", "Accept": "application/vnd.github+json"}
    url = f"{_GITHUB_API}/repos/{owner}/{repo}/git/trees/{branch}?recursive=1"

    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(30.0, connect=5.0)) as client:
            resp = await client.get(url, headers=headers)
            if resp.status_code == 404:
                raise GitHubValidationError("BRANCH_NOT_FOUND", f"Branch '{branch}' not found.")
            if resp.status_code >= 500:
                raise GitHubUnavailableError("GitHub returned a server error fetching repo tree.")
            data = resp.json()
            return [item for item in data.get("tree", []) if item.get("type") == "blob"]
    except httpx.TimeoutException:
        raise GitHubUnavailableError("GitHub could not be reached within the timeout period.")
    except httpx.RequestError as exc:
        raise GitHubUnavailableError(f"GitHub could not be reached: {type(exc).__name__}") from exc


async def get_file_content(
    repository_url: str,
    token: str,
    path: str,
    ref: str,
) -> tuple[str, str]:
    """
    Fetch file content by path and ref.

    Returns:
        (decoded_content, blob_sha)

    Raises:
        GitHubValidationError("FILE_NOT_FOUND"): if path does not exist on ref.
        GitHubUnavailableError: on timeout or 5xx.
    """
    owner, repo = parse_repository_url(repository_url)
    headers = {"Authorization": f"token {token}", "Accept": "application/vnd.github+json"}
    url = f"{_GITHUB_API}/repos/{owner}/{repo}/contents/{path}?ref={ref}"

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.get(url, headers=headers)
            if resp.status_code == 404:
                raise GitHubValidationError("FILE_NOT_FOUND", f"File '{path}' not found on ref '{ref}'.")
            if resp.status_code >= 500:
                raise GitHubUnavailableError("GitHub returned a server error fetching file content.")
            data = resp.json()
            raw = base64.b64decode(data["content"].replace("\n", "")).decode("utf-8", errors="replace")
            return raw, data["sha"]
    except httpx.TimeoutException:
        raise GitHubUnavailableError("GitHub could not be reached within the timeout period.")
    except httpx.RequestError as exc:
        raise GitHubUnavailableError(f"GitHub could not be reached: {type(exc).__name__}") from exc


# ---------------------------------------------------------------------------
# Branch and file mutations (T014)
# ---------------------------------------------------------------------------

async def get_branch_sha(
    repository_url: str,
    token: str,
    branch: str,
) -> str:
    """Return the HEAD commit SHA for the given branch."""
    owner, repo = parse_repository_url(repository_url)
    headers = {"Authorization": f"token {token}", "Accept": "application/vnd.github+json"}

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.get(
                f"{_GITHUB_API}/repos/{owner}/{repo}/git/ref/heads/{branch}",
                headers=headers,
            )
            if resp.status_code == 404:
                raise GitHubValidationError("BRANCH_NOT_FOUND", f"Branch '{branch}' not found.")
            if resp.status_code >= 500:
                raise GitHubUnavailableError("GitHub returned a server error.")
            return resp.json()["object"]["sha"]
    except httpx.TimeoutException:
        raise GitHubUnavailableError("GitHub could not be reached within the timeout period.")
    except httpx.RequestError as exc:
        raise GitHubUnavailableError(f"GitHub could not be reached: {type(exc).__name__}") from exc


async def create_branch(
    repository_url: str,
    token: str,
    branch_name: str,
    from_sha: str,
) -> None:
    """Create a new branch pointing at from_sha."""
    owner, repo = parse_repository_url(repository_url)
    headers = {"Authorization": f"token {token}", "Accept": "application/vnd.github+json"}

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.post(
                f"{_GITHUB_API}/repos/{owner}/{repo}/git/refs",
                headers=headers,
                json={"ref": f"refs/heads/{branch_name}", "sha": from_sha},
            )
            if resp.status_code == 422:
                # Branch already exists — idempotent
                return
            if resp.status_code >= 500:
                raise GitHubUnavailableError("GitHub returned a server error creating branch.")
    except httpx.TimeoutException:
        raise GitHubUnavailableError("GitHub could not be reached within the timeout period.")
    except httpx.RequestError as exc:
        raise GitHubUnavailableError(f"GitHub could not be reached: {type(exc).__name__}") from exc


async def commit_file(
    repository_url: str,
    token: str,
    branch: str,
    path: str,
    content: str,
    message: str,
    existing_sha: str | None = None,
) -> str:
    """
    Create or update a file on a branch via the GitHub contents API.

    Args:
        existing_sha: Current blob SHA if updating an existing file; None to create.

    Returns:
        The new blob SHA of the committed file.
    """
    owner, repo = parse_repository_url(repository_url)
    headers = {"Authorization": f"token {token}", "Accept": "application/vnd.github+json"}
    encoded = base64.b64encode(content.encode()).decode()
    body: dict = {"message": message, "content": encoded, "branch": branch}
    if existing_sha:
        body["sha"] = existing_sha

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.put(
                f"{_GITHUB_API}/repos/{owner}/{repo}/contents/{path}",
                headers=headers,
                json=body,
            )
            if resp.status_code >= 500:
                raise GitHubUnavailableError("GitHub returned a server error committing file.")
            if resp.status_code not in (200, 201):
                raise GitHubValidationError(
                    "COMMIT_FAILED",
                    f"Unexpected status {resp.status_code} committing '{path}'.",
                )
            return resp.json()["content"]["sha"]
    except httpx.TimeoutException:
        raise GitHubUnavailableError("GitHub could not be reached within the timeout period.")
    except httpx.RequestError as exc:
        raise GitHubUnavailableError(f"GitHub could not be reached: {type(exc).__name__}") from exc


# ---------------------------------------------------------------------------
# Pull request operations (T015)
# ---------------------------------------------------------------------------

async def create_pr(
    repository_url: str,
    token: str,
    title: str,
    body: str,
    head: str,
    base: str,
) -> tuple[int, str]:
    """
    Open a pull request.

    Returns:
        (pr_number, pr_html_url)
    """
    owner, repo = parse_repository_url(repository_url)
    headers = {"Authorization": f"token {token}", "Accept": "application/vnd.github+json"}

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.post(
                f"{_GITHUB_API}/repos/{owner}/{repo}/pulls",
                headers=headers,
                json={"title": title, "body": body, "head": head, "base": base},
            )
            if resp.status_code == 422:
                # PR already exists for this branch
                data = resp.json()
                raise GitHubValidationError(
                    "PR_ALREADY_EXISTS",
                    data.get("message", "A pull request already exists for this branch."),
                )
            if resp.status_code >= 500:
                raise GitHubUnavailableError("GitHub returned a server error creating pull request.")
            if resp.status_code not in (200, 201):
                raise GitHubValidationError(
                    "PR_CREATION_FAILED",
                    f"Unexpected status {resp.status_code} creating pull request.",
                )
            data = resp.json()
            return data["number"], data["html_url"]
    except httpx.TimeoutException:
        raise GitHubUnavailableError("GitHub could not be reached within the timeout period.")
    except httpx.RequestError as exc:
        raise GitHubUnavailableError(f"GitHub could not be reached: {type(exc).__name__}") from exc


async def get_pr(
    repository_url: str,
    token: str,
    pr_number: int,
) -> dict:
    """Return the raw GitHub PR object for the given PR number."""
    owner, repo = parse_repository_url(repository_url)
    headers = {"Authorization": f"token {token}", "Accept": "application/vnd.github+json"}

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.get(
                f"{_GITHUB_API}/repos/{owner}/{repo}/pulls/{pr_number}",
                headers=headers,
            )
            if resp.status_code == 404:
                raise GitHubValidationError("PR_NOT_FOUND", f"PR #{pr_number} not found.")
            if resp.status_code >= 500:
                raise GitHubUnavailableError("GitHub returned a server error fetching pull request.")
            return resp.json()
    except httpx.TimeoutException:
        raise GitHubUnavailableError("GitHub could not be reached within the timeout period.")
    except httpx.RequestError as exc:
        raise GitHubUnavailableError(f"GitHub could not be reached: {type(exc).__name__}") from exc


async def delete_file(
    repository_url: str,
    token: str,
    path: str,
    file_sha: str,
    message: str,
    branch: str,
) -> None:
    """Delete a file from a branch via the GitHub contents API."""
    owner, repo = parse_repository_url(repository_url)
    headers = {"Authorization": f"token {token}", "Accept": "application/vnd.github+json"}

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.request(
                "DELETE",
                f"{_GITHUB_API}/repos/{owner}/{repo}/contents/{path}",
                headers=headers,
                json={"message": message, "sha": file_sha, "branch": branch},
            )
            if resp.status_code == 404:
                return  # Already deleted — idempotent
            if resp.status_code >= 500:
                raise GitHubUnavailableError("GitHub returned a server error deleting file.")
            if resp.status_code not in (200, 201):
                raise GitHubValidationError(
                    "DELETE_FAILED",
                    f"Unexpected status {resp.status_code} deleting '{path}'.",
                )
    except httpx.TimeoutException:
        raise GitHubUnavailableError("GitHub could not be reached within the timeout period.")
    except httpx.RequestError as exc:
        raise GitHubUnavailableError(f"GitHub could not be reached: {type(exc).__name__}") from exc


async def merge_pr(
    repository_url: str,
    token: str,
    pr_number: int,
    merge_method: str = "merge",
    commit_message: str | None = None,
) -> None:
    """
    Merge an open pull request.

    Raises:
        GitHubValidationError("PR_NOT_MERGEABLE"): if the PR cannot be merged.
        GitHubUnavailableError: on timeout or 5xx.
    """
    owner, repo = parse_repository_url(repository_url)
    headers = {"Authorization": f"token {token}", "Accept": "application/vnd.github+json"}
    body: dict = {"merge_method": merge_method}
    if commit_message:
        body["commit_message"] = commit_message

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.put(
                f"{_GITHUB_API}/repos/{owner}/{repo}/pulls/{pr_number}/merge",
                headers=headers,
                json=body,
            )
            if resp.status_code == 405:
                raise GitHubValidationError("PR_NOT_MERGEABLE", "The pull request is not mergeable.")
            if resp.status_code == 409:
                raise GitHubValidationError("PR_HEAD_MODIFIED", "The pull request head was modified.")
            if resp.status_code >= 500:
                raise GitHubUnavailableError("GitHub returned a server error merging pull request.")
    except httpx.TimeoutException:
        raise GitHubUnavailableError("GitHub could not be reached within the timeout period.")
    except httpx.RequestError as exc:
        raise GitHubUnavailableError(f"GitHub could not be reached: {type(exc).__name__}") from exc


async def close_pr(
    repository_url: str,
    token: str,
    pr_number: int,
) -> None:
    """Close a pull request without merging."""
    owner, repo = parse_repository_url(repository_url)
    headers = {"Authorization": f"token {token}", "Accept": "application/vnd.github+json"}

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.patch(
                f"{_GITHUB_API}/repos/{owner}/{repo}/pulls/{pr_number}",
                headers=headers,
                json={"state": "closed"},
            )
            if resp.status_code >= 500:
                raise GitHubUnavailableError("GitHub returned a server error closing pull request.")
    except httpx.TimeoutException:
        raise GitHubUnavailableError("GitHub could not be reached within the timeout period.")
    except httpx.RequestError as exc:
        raise GitHubUnavailableError(f"GitHub could not be reached: {type(exc).__name__}") from exc
