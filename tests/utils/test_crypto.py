"""Unit tests for utils/crypto.py."""
import pytest
from cryptography.fernet import Fernet, InvalidToken
from unittest.mock import patch

from utils.crypto import encrypt_token, decrypt_token


@pytest.fixture
def test_key():
    return Fernet.generate_key().decode()


def test_roundtrip(test_key):
    with patch("utils.crypto.settings") as mock_settings:
        mock_settings.GITHUB_TOKEN_ENCRYPTION_KEY = test_key
        plaintext = "github_pat_testtoken123"
        encrypted = encrypt_token(plaintext)
        assert decrypt_token(encrypted) == plaintext


def test_version_prefix_present(test_key):
    with patch("utils.crypto.settings") as mock_settings:
        mock_settings.GITHUB_TOKEN_ENCRYPTION_KEY = test_key
        encrypted = encrypt_token("some_token")
        assert encrypted.startswith("v1:")


def test_wrong_key_raises(test_key):
    with patch("utils.crypto.settings") as mock_settings:
        mock_settings.GITHUB_TOKEN_ENCRYPTION_KEY = test_key
        encrypted = encrypt_token("some_token")

    wrong_key = Fernet.generate_key().decode()
    with patch("utils.crypto.settings") as mock_settings:
        mock_settings.GITHUB_TOKEN_ENCRYPTION_KEY = wrong_key
        with pytest.raises(InvalidToken):
            decrypt_token(encrypted)


def test_missing_version_prefix_raises(test_key):
    with patch("utils.crypto.settings") as mock_settings:
        mock_settings.GITHUB_TOKEN_ENCRYPTION_KEY = test_key
        with pytest.raises(ValueError, match="no version prefix"):
            decrypt_token("notversioned")


def test_unsupported_version_raises(test_key):
    with patch("utils.crypto.settings") as mock_settings:
        mock_settings.GITHUB_TOKEN_ENCRYPTION_KEY = test_key
        with pytest.raises(ValueError, match="Unsupported token version"):
            decrypt_token("v99:someciphertext")


def test_tampered_ciphertext_raises(test_key):
    with patch("utils.crypto.settings") as mock_settings:
        mock_settings.GITHUB_TOKEN_ENCRYPTION_KEY = test_key
        encrypted = encrypt_token("real_token")
        tampered = encrypted[:-4] + "XXXX"
        with pytest.raises(InvalidToken):
            decrypt_token(tampered)
