"""
Encryption utilities for sensitive data (bot tokens).
Uses Fernet symmetric encryption from the cryptography library.
"""

from cryptography.fernet import Fernet, InvalidToken
from src.infrastructure.config.settings import settings
from src.infrastructure.logging.logger import get_logger

logger = get_logger(__name__)

_fernet = None

def _get_fernet() -> Fernet:
    """Lazily initialise and return the Fernet cipher."""
    global _fernet
    if _fernet is None:
        key = settings.TOKEN_ENCRYPTION_KEY
        if not key:
            raise RuntimeError("TOKEN_ENCRYPTION_KEY is not set")
        try:
            _fernet = Fernet(key)
        except Exception as e:
            logger.error("Failed to initialise Fernet cipher", exc_info=e)
            raise RuntimeError("Invalid TOKEN_ENCRYPTION_KEY") from e
    return _fernet

def encrypt_token(token: str) -> str:
    """
    Encrypt a bot token and return it as a base64 string.
    """
    if not token:
        return ""
    fernet = _get_fernet()
    encrypted = fernet.encrypt(token.encode("utf-8"))
    return encrypted.decode("utf-8")

def decrypt_token(encrypted: str) -> str:
    """
    Decrypt a previously encrypted token. Returns empty string if input is empty.
    Raises RuntimeError if decryption fails.
    """
    if not encrypted:
        return ""
    fernet = _get_fernet()
    try:
        decrypted = fernet.decrypt(encrypted.encode("utf-8"))
        return decrypted.decode("utf-8")
    except InvalidToken as e:
        logger.error("Failed to decrypt token – possibly wrong key or corrupted data")
        raise RuntimeError("Token decryption failed") from e
