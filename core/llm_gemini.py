import os
import google.generativeai as genai
import logging

logger = logging.getLogger(__name__)

# Configuramos la KEY
api_key = os.getenv("GEMINI_API_KEY")
genai.configure(api_key=api_key)

def gemini_render(system_prompt: str, user_prompt: str) -> str:
    if not api_key:
        logger.error("No hay GEMINI_API_KEY configurada")
        return None
        
    try:
        # Usamos el modelo flash que es rápido y barato (gratis en nivel demo)
        model = genai.GenerativeModel(
            model_name="gemini-1.5-flash",
            system_instruction=system_prompt
        )
        
        response = model.generate_content(user_prompt)
        return response.text
    except Exception as e:
        logger.error(f"Error en Gemini: {e}")
        return None
