import os
import logging
import google.generativeai as genai

# Configuración de Logging
logger = logging.getLogger(__name__)

# La configuración de la API se hace una sola vez al cargar el módulo
API_KEY = os.getenv("GEMINI_API_KEY")
if API_KEY:
    genai.configure(api_key=API_KEY)

def gemini_render(system_prompt: str, user_prompt: str) -> str:
    """
    Versión ultra-compatible para Tier Gratuito.
    Evita el Error 404 al no usar system_instruction como parámetro separado.
    """
    if not API_KEY:
        logger.error("❌ GEMINI_API_KEY no encontrada.")
        return "⚠️ Error: Configura la API KEY en Railway."

    try:
        # 1. Instanciamos el modelo sin system_instruction fija
        model = genai.GenerativeModel('gemini-1.5-flash')

        # 2. UNIFICACIÓN DE PROMPT (Clave para el Plan Gratis)
        # En lugar de separar los roles, los enviamos en un solo bloque.
        # Esto es lo más compatible con todas las versiones de la API.
        prompt_final = f"INSTRUCCIONES DE SISTEMA:\n{system_prompt}\n\nCONSULTA DEL USUARIO:\n{user_prompt}"

        # 3. Ajustes de seguridad (para evitar bloqueos por data financiera)
        safety = [
            {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
        ]

        # 4. Generación de contenido
        response = model.generate_content(
            prompt_final,
            safety_settings=safety
        )

        if response and response.text:
            return response.text
        
        return "⚠️ Google devolvió una respuesta vacía o bloqueada."

    except Exception as e:
        error_msg = str(e)
        logger.error(f"💥 Error en Gemini: {error_msg}")

        if "429" in error_msg:
            return "🚀 Cuota agotada por este minuto. Esperá un momento."
        if "404" in error_msg:
            return "📍 Error 404: Nombre de modelo no reconocido o no disponible en esta región."
        if "location" in error_msg.lower():
            return "📍 Tu servidor de Railway está en una región no soportada por el Plan Gratis."
            
        return f"🤯 Error técnico: {error_msg}"
