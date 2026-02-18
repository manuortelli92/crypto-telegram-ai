import os
from typing import Optional

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-1.5-flash").strip()

_client = None

def _get_client():
    global _client
    if _client is not None:
        return _client
    if not GEMINI_API_KEY:
        return None
    try:
        from google import genai
        _client = genai.Client(api_key=GEMINI_API_KEY)
        return _client
    except Exception:
        return None


def gemini_render(system: str, user: str) -> Optional[str]:
    client = _get_client()
    if not client:
        return None
    try:
        resp = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=user,
            config={
                "system_instruction": system,
                "temperature": 0.35,
            },
        )
        text = getattr(resp, "text", None)
        return text.strip() if text else None
    except Exception:
        return None