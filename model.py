"""
Google GenAI (Gemini / Gemma) Interaction Test Script.
"""
import os
from google import genai

# Discover API key from environment or saved database secret
api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
if not api_key:
    try:
        from web.backend.db import AppDatabase
        db = AppDatabase()
        secret = db.get_secret("llm_api_key")
        if secret and secret.get("provider") == "gemini":
            import json
            pt = secret.get("plaintext", "")
            if pt.startswith("{"):
                api_key = json.loads(pt).get("api_key")
            else:
                api_key = pt
    except Exception:
        pass

if api_key:
    client = genai.Client(api_key=api_key)
else:
    client = genai.Client()

interaction = client.interactions.create(
    model="gemma-4-31b-it",
    input="Explain how AI works in a few words"
)

print(interaction.output_text)