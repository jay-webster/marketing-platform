"""
Fernet symmetric encryption for GitHub personal access tokens.

Tokens are stored as "v1:<fernet_ciphertext>" to support future key rotation
without a hard cutover. On decryption the version prefix is validated before
the Fernet cipher is applied.

Security contract:
  - The encryption key is loaded exclusively from settings.GITHUB_TOKEN_ENCRYPTION_KEY.
  - The plaintext token is never logged, returned in a response, or stored in
    any exception message (callers must enforce this).
  - encrypt_token / decrypt_token are the only functions that touch plaintext.
"""

from cryptography.fernet import Fernet, InvalidToken

from src.config import settings

_VERSION = "v1"


def _get_cipher() -> Fernet:
    key = settings.GITHUB_TOKEN_ENCRYPTION_KEY
    if not key:
        raise EnvironmentError("GITHUB_TOKEN_ENCRYPTION_KEY is not configured.")
    return Fernet(key.encode())


def encrypt_token(plaintext: str) -> str:
    """Encrypt a plaintext PAT and return a versioned ciphertext string."""
    cipher = _get_cipher()
    ciphertext = cipher.encrypt(plaintext.encode()).decode()
    return f"{_VERSION}:{ciphertext}"


def decrypt_token(versioned_ciphertext: str) -> str:
    """
    Decrypt a versioned ciphertext string and return the plaintext PAT.

    Raises:
        ValueError: If the version prefix is not recognised.
        cryptography.fernet.InvalidToken: If the ciphertext has been tampered with
            or was encrypted with a different key.
    """
    try:
        version, ciphertext = versioned_ciphertext.split(":", 1)
    except ValueError:
        raise ValueError("Encrypted token has no version prefix.")

    if version != _VERSION:
        raise ValueError(f"Unsupported token version: {version!r}. Expected {_VERSION!r}.")

    cipher = _get_cipher()
    return cipher.decrypt(ciphertext.encode()).decode()
