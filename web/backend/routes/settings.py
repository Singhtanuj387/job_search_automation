"""
Settings and Encrypted API Key Management API Routes.
"""
import os
import time
from typing import Dict, Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from web.backend.db import AppDatabase
from web.backend.llm_service import LLMService
from web.backend.session import get_client_id

router = APIRouter(prefix="/api/settings", tags=["Settings"])
db = AppDatabase()


class SaveSecretRequest(BaseModel):
    provider: str
    api_key: str
    extra_config: Optional[Dict[str, str]] = None


class TestGeminiRequest(BaseModel):
    api_key: Optional[str] = None
    model_id: Optional[str] = "gemma-4-31b-it"
    input_text: Optional[str] = "Explain how AI works in a few words"


@router.get("/secret")
def get_secret(client_id: str = Depends(get_client_id)):
    secret = db.get_secret("llm_api_key", session_id=client_id)
    if not secret:
        return {"has_key": False, "provider": None, "masked_key": None}
    return {
        "has_key": True,
        "provider": secret["provider"],
        "masked_key": secret["masked_key"],
        "last_validated_at": secret["last_validated_at"],
    }


@router.post("/secret")
def save_secret(req: SaveSecretRequest, client_id: str = Depends(get_client_id)):
    if not req.api_key or not req.api_key.strip():
        raise HTTPException(status_code=400, detail="API key cannot be empty.")

    # 1. Validate key with minimal test probe
    valid, message = LLMService.validate_api_key(
        provider=req.provider,
        api_key=req.api_key,
        extra_config=req.extra_config,
    )

    if not valid:
        raise HTTPException(status_code=400, detail=f"Key validation failed: {message}")

    # 2. Save encrypted at rest isolated by session_id
    if req.provider.lower() == "gemini":
        import json
        raw_model = (req.extra_config or {}).get("model_id")
        model_id = LLMService.normalize_gemini_model(raw_model)
        payload = {
            "api_key": req.api_key.strip(),
            "model_id": model_id.strip(),
        }
        plaintext_to_save = json.dumps(payload)
    else:
        plaintext_to_save = req.api_key.strip()

    saved = db.save_secret(
        key_name="llm_api_key",
        plaintext_value=plaintext_to_save,
        provider=req.provider,
        session_id=client_id,
    )

    return {
        "status": "ok",
        "message": message,
        "provider": saved["provider"],
        "masked_key": saved["masked_key"],
        "last_validated_at": saved["last_validated_at"],
    }


@router.delete("/secret")
def delete_secret(client_id: str = Depends(get_client_id)):
    success = db.delete_secret("llm_api_key", session_id=client_id)
    return {"status": "ok" if success else "not_found", "deleted": success}


@router.get("/providers")
def list_providers():
    return {
        "providers": [
            {
                "id": "gemini",
                "name": "Google Gemini & Gemma",
                "placeholder": "AIzaSy...",
                "description": "Native google-genai integration supporting gemma-4-31b-it and Gemini models.",
                "default_model": "gemma-4-31b-it",
            },
            {
                "id": "openai",
                "name": "OpenAI",
                "placeholder": "sk-...",
                "description": "Industry-standard models (GPT-4o, GPT-4o-mini).",
                "default_model": "gpt-4o-mini",
            },
            {
                "id": "anthropic",
                "name": "Anthropic Claude",
                "placeholder": "sk-ant-api03-...",
                "description": "Recommended for high-fidelity resume and cover letter synthesis.",
                "default_model": "claude-3-5-sonnet-20241022",
            },
        ]
    }


@router.post("/test-gemini")
def test_gemini(req: TestGeminiRequest, client_id: str = Depends(get_client_id)):
    """
    Tests Google GenAI / Gemma model invocation directly as specified by the user:
        client = genai.Client()
        interaction = client.interactions.create(
            model=model,
            input=input
        )
    """
    key = req.api_key.strip() if req.api_key else None
    if not key:
        secret = db.get_secret("llm_api_key", session_id=client_id)
        if secret and secret.get("provider") == "gemini":
            import json
            pt = secret.get("plaintext", "")
            if pt.startswith("{"):
                key = json.loads(pt).get("api_key")
            else:
                key = pt

    if not key:
        key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")

    if not key:
        raise HTTPException(
            status_code=400,
            detail="No Gemini API key provided in request or found in saved dashboard settings.",
        )

    model_id = LLMService.normalize_gemini_model(req.model_id)
    input_text = req.input_text.strip() if req.input_text else "Explain how AI works in a few words"

    start_t = time.time()
    try:
        from google import genai
        client = genai.Client(api_key=key)

        try:
            interaction = client.interactions.create(
                model=model_id,
                input=input_text,
            )
            output = getattr(interaction, "output_text", None) or str(interaction)
            method = "client.interactions.create"
        except Exception as inter_err:
            if model_id != "gemma-4-31b-it":
                # Attempt gemma-4-31b-it fallback
                fallback_inter = client.interactions.create(
                    model="gemma-4-31b-it",
                    input=input_text,
                )
                output = getattr(fallback_inter, "output_text", None) or str(fallback_inter)
                method = f"client.interactions.create (fallback to gemma-4-31b-it from: {inter_err})"
                model_id = "gemma-4-31b-it"
            else:
                raise inter_err

        duration = round(time.time() - start_t, 2)
        return {
            "status": "ok",
            "model": model_id,
            "method": method,
            "output_text": output,
            "latency_seconds": duration,
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Gemini execution failed: {str(e)}")
