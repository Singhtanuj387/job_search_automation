"""Unit tests for security, encryption, and key masking."""
from web.backend.security import SecurityManager


def test_encryption_roundtrip():
    secret = "sk-ant-api03-super-secret-key-123456789"
    encrypted = SecurityManager.encrypt(secret)
    assert encrypted != secret
    decrypted = SecurityManager.decrypt(encrypted)
    assert decrypted == secret


def test_key_masking():
    anthropic_key = "sk-ant-api03-1234567890abcdef1234"
    masked = SecurityManager.mask_key(anthropic_key)
    assert masked.startswith("sk-ant-api03-")
    assert masked.endswith("1234")
    assert "•" in masked
    assert "abcdef" not in masked

    gemini_key = "AIzaSyABCDEF1234567890GHIJKL"
    masked_gemini = SecurityManager.mask_key(gemini_key)
    assert masked_gemini.startswith("AIzaSy")
    assert masked_gemini.endswith("IJKL")
    assert "•" in masked_gemini

    # Gemini JSON configuration masking
    gemini_json = '{"api_key": "AIzaSyABCDEF1234567890GHIJKL", "model_id": "Gemma-4-31B"}'
    masked_json = SecurityManager.mask_key(gemini_json)
    assert masked_json.startswith("AIzaSy")
    assert "IJKL" in masked_json
    assert "Gemma-4-31B" in masked_json
