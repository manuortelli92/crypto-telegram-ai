import os
import google.generativeai as genai
import logging

logger = logging.getLogger(__name__)

# Intentamos configurar la key
api_key = os.getenv("GEMINI_API_KEY")

def gemini_render(system_prompt: str, user_prompt: str) -> str:
    if not api_key:
        logger.error("❌ GEMINI_API_KEY no encontrada en las variables de entorno.")
        return None
        
    try:
        genai.configure(api_key=api_key)
        # Usamos flash-8b que es el más liviano y casi nunca falla por cuotas
        model = genai.GenerativeModel(
            model_name="gemini-1.5-flash",
            system_instruction=system_prompt
        )
        
        response = model.generate_content(user_prompt)
        
        if response and response.text:
            return response.text
        else:
            logger.error("⚠️ Gemini devolvió una respuesta vacía.")
            return None

    except Exception as e:
        # ESTO ES LO QUE NECESITAMOS VER EN EL LOG
        logger.error(f"🚨 ERROR CRÍTICO EN GEMINI: {str(e)}")
        return None
