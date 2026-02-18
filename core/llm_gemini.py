import os
import logging
import google.generativeai as genai

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def gemini_render(system_prompt: str, user_prompt: str) -> str:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return "❌ Error: No hay clave API configurada."

    try:
        genai.configure(api_key=api_key)
        
        # Usamos el modelo Flash con un nombre que fuerza la versión más estable
        model = genai.GenerativeModel(
            model_name='gemini-1.5-flash',
            system_instruction=system_prompt
        )
        
        # CONFIGURACIÓN DE SEGURIDAD AL MÍNIMO
        # Google a veces bloquea respuestas inofensivas. Con esto lo evitamos.
        safety_settings = [
            {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
        ]

        # Intentar generar contenido
        response = model.generate_content(
            user_prompt,
            safety_settings=safety_settings
        )
        
        # Verificar si Google bloqueó la respuesta por seguridad
        if response.candidates and response.candidates[0].finish_reason == 3:
            return "⚠️ Google bloqueó esta respuesta por sus políticas de seguridad."

        if response and response.text:
            return response.text
        
        return "⚠️ Google devolvió una respuesta vacía. Probá con otra pregunta."

    except Exception as e:
        error_msg = str(e)
        logger.error(f"💥 Error: {error_msg}")
        
        # Si el error es de cuota (demasiados mensajes)
        if "429" in error_msg:
            return "🚀 ¡Calma! Mandaste demasiados mensajes seguidos. Esperá un minuto."
        
        # Si el error es de la región (aunque estés en USA, a veces falla)
        if "location" in error_msg.lower():
            return "📍 Error de ubicación. Revisá que Railway esté en US-East-1."

        return f"🤯 Explotó algo internamente: {error_msg}"