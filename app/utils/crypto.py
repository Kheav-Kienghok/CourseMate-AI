from __future__ import annotations

import base64
import hashlib
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken

from utils.config import get_encryption_secret


def _build_key_from_secret() -> bytes:
    """Derive a Fernet-compatible key from the app secret.

    We allow COURSEMATE_ENCRYPTION_SECRET to be any string and
    stretch it into a 32-byte key, then base64-url encode it
    as required by Fernet.
    """

    secret = get_encryption_secret().encode("utf-8")
    digest = hashlib.sha256(secret).digest()
    return base64.urlsafe_b64encode(digest)


def _get_fernet() -> Fernet:
    key = _build_key_from_secret()
    return Fernet(key)


def encrypt_text(plaintext: str) -> str:
    """Encrypt a UTF-8 string and return ciphertext as UTF-8 string."""

    f = _get_fernet()
    token = f.encrypt(plaintext.encode("utf-8"))
    return token.decode("utf-8")


def decrypt_text(ciphertext: str | None) -> Optional[str]:
    """Decrypt ciphertext back to a string.

    Returns None if ciphertext is empty or cannot be decrypted
    (e.g. key changed or data corrupted).
    """

    if not ciphertext:
        return None

    f = _get_fernet()
    try:
        data = f.decrypt(ciphertext.encode("utf-8"))
        return data.decode("utf-8")
    except InvalidToken:
        return None


if __name__ == "__main__":
    # Simple manual test helper: encrypt and decrypt a sample value
    sample = input("Enter text to encrypt and decrypt: ")

    encrypted = encrypt_text(sample)
    print(f"Encrypted: {encrypted}")

    decrypted = decrypt_text(encrypted)
    print(f"Decrypted: {decrypted}")

    a1 = decrypt_text("gAAAAABpt_PgNWvPnzM_T2IE5_az6zuvwCjuKq6ezfoR2RQ2JtuOGUAutLfSGI9X5bSxnuyfL8MpNvJ60u1XeHOVvMMfvePO83U3fEtTpFziBHgFDXcexHuYP2OJtEaGaUsKWi5JWVyj")
    print(f"Decrypted known token: {a1}")