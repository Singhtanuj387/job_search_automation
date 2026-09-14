"""
Cryptographic Security Layer for API keys and sensitive tokens.
Encrypts secrets at rest using Fernet symmetric encryption and enforces key masking.
"""
from typing import Optional
from cryptography.fernet import Fernet
from web.backend.config import get_master_key


class SecurityManager:
    """
    Encrypts and decrypts sensitive values at rest using server-side master key.
    """

    @classmethod
    def _get_fernet(cls) -> Fernet:
        return Fernet(get_master_key())

    @classmethod
    def encrypt(cls, plaintext: str) -> str:
        """Encrypts plaintext string and returns URL-safe base64 string."""
        if not plaintext:
            return ""
        f = cls._get_fernet()
        return f.encrypt(plaintext.encode("utf-8")).decode("utf-8")

    @classmethod
    def decrypt(cls, ciphertext: str) -> str:
        """Decrypts ciphertext string and returns plaintext."""
        if not ciphertext:
            return ""
        f = cls._get_fernet()
        return f.decrypt(ciphertext.encode("utf-8")).decode("utf-8")

    @classmethod
    def mask_key(cls, key: str) -> str:
        """
        Masks an API key to reveal only prefix and last 4 characters.
        e.g. 'sk-ant-api03-abcdef1234567890' -> 'sk-ant-••••••••••••7890'
        """
        if not key:
            return ""
        cleaned = key.strip()
        if len(cleaned) <= 8:
            return "••••" + cleaned[-2:]

        import json

        # Check if key is a JSON string containing provider config (e.g. Gemini with model_id)
        if cleaned.startswith("{"):
            try:
                data = json.loads(cleaned)
                if "api_key" in data:
                    k = data.get("api_key", "")
                    m = data.get("model_id", "Gemma-4-31B")
                    prefix = "AIzaSy" if k.startswith("AIzaSy") else k[:4]
                    return f"{prefix}••••••••{k[-4:]} ({m})"
            except Exception:
                pass

        # Check for common prefixes
        prefix = ""
        for p in ["sk-ant-api03-", "sk-ant-", "sk-proj-", "sk-", "AIzaSy"]:
            if cleaned.startswith(p):
                prefix = p
                break

        if not prefix:
            prefix = cleaned[:4]

        suffix = cleaned[-4:]
        mask_len = max(len(cleaned) - len(prefix) - len(suffix), 6)
        return f"{prefix}{'•' * min(mask_len, 14)}{suffix}"

