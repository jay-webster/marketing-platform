"""
GitHub repository sync client.

Token safety (CONSTITUTION §Administrative Security — Exposure Prevention):
  - The token lives only in the _token attribute (memory).
  - It is injected into git operations at call time via an authenticated URL
    that is constructed in _auth_url() and NEVER passed to any logger.* call.
  - clone: auth URL is used once, then .git/config is immediately reset to the
    clean URL so the token is never persisted to disk.
  - update (fetch+merge): auth URL is passed directly to `git fetch` as a
    positional argument — it is never written to .git/config at all.
  - All subprocess calls use capture_output=True so git output never reaches
    the console or any upstream log handler.
  - _sanitize() scrubs the token from captured stderr before it reaches a log
    call, guarding against git unexpectedly echoing the URL in error messages.
  - GIT_TERMINAL_PROMPT=0 prevents git from hanging on interactive auth prompts
    in headless/container environments.

CONSTITUTION compliance:
  - TENANT_SAFE  : Clone path is scoped to data/tenants/{tenant_name}/ —
                   one directory per tenant, no cross-tenant access possible.
  - DRY          : Standalone client; no overlap with postgres_manager.
  - NON_BLOCKING : Stateless. No session or in-process cache. The clone
                   directory should be a GCP Cloud Storage FUSE mount in prod.
"""

import logging
import os
import re
import subprocess
from pathlib import Path
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Compiled constants
# ---------------------------------------------------------------------------

# Matches: https://github.com/owner/repo  or  https://github.com/owner/repo.git
_GITHUB_URL_RE = re.compile(
    r"^https://github\.com"
    r"/(?P<owner>[A-Za-z0-9_][A-Za-z0-9_.-]*)"
    r"/(?P<repo>[A-Za-z0-9_][A-Za-z0-9_.-]*?)"
    r"(?:\.git)?$"
)

# Allowlist for tenant_name — prevents path traversal and shell metacharacters.
_SAFE_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")

# Base directory for all tenant clones.  Override via TENANT_DATA_DIR env var.
_BASE_CLONE_DIR = Path(os.environ.get("TENANT_DATA_DIR", "data/tenants"))


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class GitHubSyncError(RuntimeError):
    """
    Raised when a git operation fails.

    The message is always token-free — _sanitize() is applied to stderr
    before it is embedded in any exception message or log line.
    """


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------

class GitHubClient:
    """
    Clone and update GitHub repositories on behalf of a tenant.

    Args:
        github_token: A GitHub personal access token or fine-grained token
                      with at least ``contents:read`` scope.
                      Prefer constructing via ``GitHubClient.from_env()``.
    """

    def __init__(self, github_token: str) -> None:
        if not github_token:
            raise ValueError("github_token must not be empty.")
        self._token = github_token

    @classmethod
    def from_env(cls) -> "GitHubClient":
        """Construct from the GITHUB_TOKEN environment variable."""
        token = os.environ.get("GITHUB_TOKEN", "")
        if not token:
            raise EnvironmentError("GITHUB_TOKEN environment variable is not set.")
        return cls(token)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def sync_repository(self, github_url: str, tenant_name: str) -> list[str]:
        """
        Clone or update a GitHub repository for a tenant, then return all
        Markdown file paths for downstream indexing.

        Behaviour:
          - If ``data/tenants/{tenant_name}/`` does not contain a ``.git``
            directory, performs a fresh clone.
          - If it already exists, fetches the latest changes and
            fast-forward merges (equivalent to ``git pull --ff-only``).

        The GitHub token is injected at the network layer only and is never
        written to ``.git/config`` or any log line.

        Args:
            github_url:  HTTPS GitHub repo URL.
                         E.g. ``"https://github.com/acme/marketing-content"``
            tenant_name: Scopes the local clone directory.  Must match
                         ``[A-Za-z0-9][A-Za-z0-9_-]{0,63}`` to prevent
                         path traversal.

        Returns:
            Sorted list of absolute path strings for every ``.md`` file
            found in the cloned repository.

        Raises:
            ValueError:       Invalid URL format or unsafe ``tenant_name``.
            GitHubSyncError:  git command failure (message is always token-free).
        """
        clean_url = self._validate_github_url(github_url)
        clone_dir = self._resolve_clone_dir(tenant_name)

        logger.info("Syncing repo %s for tenant '%s' → %s", clean_url, tenant_name, clone_dir)

        clone_dir.mkdir(parents=True, exist_ok=True)

        if (clone_dir / ".git").is_dir():
            self._update(clone_dir, clean_url)
        else:
            self._clone(clone_dir, clean_url)

        md_files = self._collect_md_files(clone_dir)
        logger.info(
            "Sync complete for tenant '%s'. Found %d Markdown file(s).",
            tenant_name,
            len(md_files),
        )
        return md_files

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    @staticmethod
    def _validate_github_url(github_url: str) -> str:
        """
        Return the canonical clean URL (scheme + host + path, no ``.git`` suffix,
        no embedded credentials).

        Raises:
            ValueError: If the URL fails any of the validation checks.
        """
        url = github_url.strip()
        parsed = urlparse(url)

        if parsed.scheme != "https":
            raise ValueError(
                f"URL must use the HTTPS scheme, got {parsed.scheme!r}. "
                "SSH URLs are not supported — use HTTPS with a token."
            )

        if parsed.netloc not in ("github.com", "www.github.com"):
            raise ValueError(
                f"URL must point to github.com, got {parsed.netloc!r}."
            )

        # Reject credentials embedded directly in the URL.
        if parsed.username or parsed.password:
            raise ValueError(
                "URL must not contain embedded credentials. "
                "Pass the token to GitHubClient separately."
            )

        match = _GITHUB_URL_RE.match(url.rstrip("/"))
        if not match:
            raise ValueError(
                f"URL does not match the expected GitHub repo format "
                f"(https://github.com/owner/repo). Got: {url!r}"
            )

        owner = match.group("owner")
        repo = match.group("repo")
        return f"https://github.com/{owner}/{repo}"

    @staticmethod
    def _resolve_clone_dir(tenant_name: str) -> Path:
        """Return the tenant-scoped clone Path after validating ``tenant_name``."""
        if not _SAFE_NAME_RE.match(tenant_name):
            raise ValueError(
                f"tenant_name must start with an alphanumeric character and contain "
                f"only letters, digits, hyphens, and underscores (max 64 chars). "
                f"Got: {tenant_name!r}"
            )
        return _BASE_CLONE_DIR / tenant_name

    # ------------------------------------------------------------------
    # Git operations
    # ------------------------------------------------------------------

    def _auth_url(self, clean_url: str) -> str:
        """
        Build an authenticated HTTPS URL by injecting the token as the password.

        ``x-access-token`` is the conventional GitHub username for PAT auth.

        !! This return value must NEVER be passed to any logger.* call. !!
        """
        return clean_url.replace("https://", f"https://x-access-token:{self._token}@", 1)

    def _run(
        self,
        cmd: list[str],
        *,
        cwd: Path | None = None,
        context: str = "",
    ) -> subprocess.CompletedProcess:
        """
        Run a git command with full output capture.

        - ``capture_output=True``  — stdout/stderr never reach the console.
        - ``shell=False``          — no shell-injection risk; args are a list.
        - ``GIT_TERMINAL_PROMPT=0``— prevents interactive auth hang in containers.
        - On failure, stderr is sanitised before being logged or embedded in
          the raised ``GitHubSyncError``.
        """
        env = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}
        try:
            return subprocess.run(
                cmd,
                capture_output=True,
                check=True,
                cwd=cwd,
                env=env,
                timeout=120,
                text=True,
            )
        except subprocess.CalledProcessError as exc:
            safe_stderr = self._sanitize(exc.stderr or "")
            safe_cmd = self._sanitize(" ".join(exc.cmd))
            logger.error(
                "git command failed [%s]: exit=%d stderr=%r",
                context or safe_cmd,
                exc.returncode,
                safe_stderr,
            )
            raise GitHubSyncError(
                f"git {context or 'operation'} failed (exit {exc.returncode}): {safe_stderr}"
            ) from exc
        except subprocess.TimeoutExpired as exc:
            logger.error("git command timed out [%s].", context)
            raise GitHubSyncError(
                f"git {context or 'operation'} timed out after {exc.timeout}s."
            ) from exc

    def _clone(self, clone_dir: Path, clean_url: str) -> None:
        """
        Fresh clone into ``clone_dir``.

        The auth URL is used only for the network call. Immediately after
        cloning, the remote URL in ``.git/config`` is reset to ``clean_url``
        so the token is never persisted to disk — even if the reset step
        fails, the ``finally`` block ensures the attempt is always made.
        """
        logger.info("Cloning %s ...", clean_url)
        auth_url = self._auth_url(clean_url)
        try:
            self._run(
                ["git", "clone", "--", auth_url, str(clone_dir)],
                context="clone",
            )
        finally:
            # Reset remote URL regardless of clone success/failure.
            # A partial clone may have written .git/config before failing.
            if (clone_dir / ".git").is_dir():
                self._reset_remote_url(clone_dir, clean_url)

    def _update(self, clone_dir: Path, clean_url: str) -> None:
        """
        Update an existing clone via fetch + fast-forward merge.

        Credentials are passed directly to ``git fetch`` as a positional
        argument — they are never written to ``.git/config`` because we
        bypass the stored remote and supply the URL inline.
        """
        logger.info("Updating existing clone at %s ...", clone_dir)
        auth_url = self._auth_url(clean_url)

        # Fetch from the auth URL without touching .git/config.
        self._run(
            ["git", "fetch", "--", auth_url],
            cwd=clone_dir,
            context="fetch",
        )
        # Fast-forward the local branch to FETCH_HEAD.
        self._run(
            ["git", "merge", "--ff-only", "FETCH_HEAD"],
            cwd=clone_dir,
            context="merge",
        )

    def _reset_remote_url(self, clone_dir: Path, clean_url: str) -> None:
        """Overwrite origin's stored URL with the unauthenticated ``clean_url``."""
        try:
            self._run(
                ["git", "remote", "set-url", "origin", clean_url],
                cwd=clone_dir,
                context="reset-remote-url",
            )
        except GitHubSyncError:
            # Non-fatal: log a warning but don't mask the primary error.
            logger.warning(
                "Could not reset remote URL for %s. "
                "The token may remain in .git/config — rotate it promptly.",
                clone_dir,
            )

    # ------------------------------------------------------------------
    # File discovery
    # ------------------------------------------------------------------

    @staticmethod
    def _collect_md_files(clone_dir: Path) -> list[str]:
        """Return sorted absolute path strings for all ``.md`` files under ``clone_dir``."""
        return sorted(
            str(p.resolve()) for p in clone_dir.rglob("*.md") if p.is_file()
        )

    # ------------------------------------------------------------------
    # Safety
    # ------------------------------------------------------------------

    def _sanitize(self, text: str) -> str:
        """Replace any accidental token occurrence in ``text`` with ``'***'``."""
        if self._token and self._token in text:
            return text.replace(self._token, "***")
        return text
