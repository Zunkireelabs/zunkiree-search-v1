"""
Per-tenant backend credential encryption.

Strict + lazy:
- Strict: no fallback to CHATBOT_ENCRYPTION_KEY. If
  BACKEND_CREDENTIALS_ENCRYPTION_KEY isn't set, encrypt/decrypt raise.
  Module import never touches the env.
- Lazy: Fernet instance is constructed on first encrypt() / decrypt() call.
  Apps boot cleanly even before the env var is configured. Legacy-fallback
  tenants (no per-tenant credential row) never touch this module.
"""
from cryptography.fernet import Fernet


class BackendCredentialsEncryptionError(RuntimeError):
    pass


def _build_fernet() -> Fernet:
    # Imported here so config is evaluated at first call, not module load.
    from app.config import get_settings

    key = (get_settings().backend_credentials_encryption_key or "").strip()
    if not key:
        raise BackendCredentialsEncryptionError(
            "BACKEND_CREDENTIALS_ENCRYPTION_KEY is not configured. "
            "Generate one with: "
            "python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'"
        )
    try:
        return Fernet(key.encode("utf-8"))
    except Exception as e:
        raise BackendCredentialsEncryptionError(
            f"BACKEND_CREDENTIALS_ENCRYPTION_KEY is not a valid Fernet key: {e}"
        ) from e


def encrypt(plaintext: str) -> str:
    return _build_fernet().encrypt(plaintext.encode("utf-8")).decode("utf-8")


def decrypt(ciphertext: str) -> str:
    return _build_fernet().decrypt(ciphertext.encode("utf-8")).decode("utf-8")
