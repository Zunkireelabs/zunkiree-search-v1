"""Argon2id hashing for per-tenant admin token secrets (Z6).

Mirrors the shape of connectors/encryption.py — single-purpose helper, lazy
initialisation, no env-var dependency at import time. The secret plaintext
(`zka_sec_<48>`) is never persisted; only the Argon2id hash lands in
tenant_admin_tokens.secret_hash.

Default argon2-cffi parameters are appropriate for server-side admin tokens
(small caller volume, not user-facing latency-critical). Don't override
without a reason.
"""
from __future__ import annotations

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, InvalidHash

_hasher: PasswordHasher | None = None


def _get_hasher() -> PasswordHasher:
    global _hasher
    if _hasher is None:
        _hasher = PasswordHasher()
    return _hasher


def hash_token(plaintext: str) -> str:
    """Return an Argon2id hash for the given token plaintext."""
    return _get_hasher().hash(plaintext)


def verify_token(plaintext: str, stored_hash: str) -> bool:
    """Constant-time-ish verify. Returns True only on exact match.

    Argon2id's verify raises on mismatch / malformed-hash; both map to False
    so callers can branch on a single boolean.
    """
    try:
        return _get_hasher().verify(stored_hash, plaintext)
    except (VerifyMismatchError, InvalidHash, Exception):
        return False
