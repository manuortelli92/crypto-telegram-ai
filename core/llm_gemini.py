import os
import logging
import google.generativeai as genai
from typing import Optional

logger = logging.getLogger(__name__)

# Configuración desde variables de entorno
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
MODEL_NAME = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")

# Inicializar la API solo si hay clave
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)
else:
    logger.error("❌ No se encontró GEMINI_API_KEY en las variables de entorno.")

def gemini_render(system_prompt: str, user_prompt: str) -> Optional[str]:
    """
    Envía la consulta a Gemini y devuelve la respuesta del analista.
    """
    if not GEMINI_API_KEY:
        return "Che, no configuraste la API Key de Gemini. Así no arranco ni a palos."

    try:
        model = genai.GenerativeModel(
            model_name=MODEL_NAME,
            system_instruction=system_prompt
        )
        
        # Configuración de generación para que no se ponga místico
        generation_config = {
            "temperature": 0.7,
            "top_p": 0.95,
            "max_output_tokens": 1024,
        }

        response = model.generate_content(
            user_prompt,
            generation_config=generation_config
        )

        if response and response.text:
            return response.text
        
        return None

    except Exception as e:
        logger.error(f"Error llamando a Gemini: {e}")
        # Si es un error de cuota (429), avisamos
        if "429" in str(e):
            return "Pará un poco que Google me está limitando por pedirle tanto. Aguantá un toque y probá de nuevo."
        return None
