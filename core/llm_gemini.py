import os
import logging
import google.generativeai as genai

# Configuración de logs para Railway
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def gemini_render(system_prompt: str, user_prompt: str) -> str:
    # 1. LEER LA CLAVE DESDE RAILWAY
    api_key = os.getenv("GEMINI_API_KEY")
    
    if not api_key:
        logger.error("❌ ERROR: No se encontró la variable GEMINI_API_KEY en Railway.")
        return "Configuración incompleta: falta la API Key."

    try:
        # 2. CONFIGURAR GOOGLE AI
        genai.configure(api_key=api_key)
        
        # Usamos el modelo más estable para el plan gratuito
        model = genai.GenerativeModel(
            model_name='gemini-1.5-flash',
            system_instruction=system_prompt
        )
        
        # 3. GENERAR RESPUESTA
        # Agregamos ajustes de seguridad para evitar bloqueos por error
        response = model.generate_content(
            user_prompt,
            safety_settings=[
                {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
            ]
        )
        
        if response and response.text:
            return response.text
        return "El modelo no generó respuesta."

    except Exception as e:
        error_str = str(e)
        logger.error(f"🚨 ERROR EN GEMINI: {error_str}")
        
        if "location" in error_str.lower():
            return "Error: Tu servidor de Railway está en una región (Europa/España) no permitida por Google Gemini."
        if "API_KEY_INVALID" in error_str:
            return "Error: La clave API que pusiste en Railway es incorrecta."
            
        return f"Error técnico: {error_str}"