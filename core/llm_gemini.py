import os
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Configuración desde variables de entorno
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-1.5-flash").strip()

_client = None

def _get_client():
    """Inicializa el cliente de Google GenAI de forma segura (Singleton)."""
    global _client
    if _client is not None:
        return _client
    
    if not GEMINI_API_KEY:
        logger.error("CRÍTICO: GEMINI_API_KEY no encontrada en las variables de entorno.")
        return None
        
    try:
        from google import genai
        _client = genai.Client(api_key=GEMINI_API_KEY)
        return _client
    except ImportError:
        logger.error("ERROR: La librería 'google-genai' no está instalada. Ejecutá: pip install google-genai")
        return None
    except Exception as e:
        logger.error(f"Error inesperado al inicializar Gemini Client: {e}")
        return None

def gemini_render(system: str, user: str) -> Optional[str]:
    """
    Envía el prompt al modelo de Google y devuelve la respuesta limpia.
    """
    client = _get_client()
    if not client:
        return None
        
    try:
        # Usamos la configuración de generación para mayor precisión
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=user,
            config={
                "system_instruction": system,
                "temperature": 0.4, # Un poco más de creatividad, pero manteniendo coherencia
                "max_output_tokens": 1000,
            },
        )
        
        if not response or not hasattr(response, "text"):
            logger.warning("Gemini devolvió una respuesta vacía o sin texto.")
            return None
            
        return response.text.strip()
        
    except Exception as e:
        logger.error(f"Error en la llamada a Gemini API: {e}")
        return None
