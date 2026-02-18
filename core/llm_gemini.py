import os
import google.generativeai as genai
import logging

logger = logging.getLogger(__name__)

def gemini_render(system_prompt: str, user_prompt: str) -> str:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        logger.error("❌ No hay GEMINI_API_KEY")
        return None
        
    try:
        # 1. Configuración básica
        genai.configure(api_key=api_key)
        
        # 2. En el plan GRATIS, el modelo más compatible es este nombre exacto:
        # Sin prefijos de 'models/' ni sufijos de '-latest'
        model = genai.GenerativeModel('gemini-1.5-flash')
        
        # 3. Formato ultra-simple (sin instrucciones de sistema separadas)
        # Esto es lo que mejor funciona en el plan gratuito
        mensaje_completo = f"{system_prompt}\n\nPregunta del usuario: {user_prompt}"
        
        # 4. Llamada con parámetros de seguridad relajados
        # (A veces el plan gratis bloquea por 'falso positivo' de seguridad)
        response = model.generate_content(
            mensaje_completo,
            safety_settings=[
                {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
            ]
        )
        
        if response and response.text:
            return response.text
        return None

    except Exception as e:
        # SI ESTO FALLA, EL PROBLEMA ES LA REGIÓN O LA KEY
        logger.error(f"🚨 ERROR DEFINITIVO: {str(e)}")
        
        # Intento desesperado con el modelo Pro antiguo
        try:
            model_alt = genai.GenerativeModel('gemini-pro')
            res = model_alt.generate_content(mensaje_completo)
            return res.text
        except:
            return None
