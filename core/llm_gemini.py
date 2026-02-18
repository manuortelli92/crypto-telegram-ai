import os
import logging
import google.generativeai as genai

# Configuración de logs
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def gemini_render(system_prompt: str, user_prompt: str) -> str:
    # 1. Obtener clave y modelo de las variables de Railway
    api_key = os.getenv("GEMINI_API_KEY")
    # Si no hay variable, usamos el flash por defecto
    model_id = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")
    
    if not api_key:
        logger.error("❌ No se encontró la variable GEMINI_API_KEY")
        return "Error: Falta la configuración de la clave API."

    try:
        # 2. Configurar la API
        genai.configure(api_key=api_key)
        
        # 3. Limpiar el nombre del modelo (por si pusiste 'models/')
        model_name = model_id.split('/')[-1] 
        
        # 4. Configurar el modelo
        model = genai.GenerativeModel(
            model_name=model_name,
            system_instruction=system_prompt
        )
        
        # 5. Ajustes de seguridad (para evitar bloqueos por error)
        safety_settings = [
            {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
        ]

        # 6. Generar respuesta
        response = model.generate_content(
            user_prompt,
            safety_settings=safety_settings
        )
        
        if response and response.text:
            return response.text
        else:
            return "El modelo no generó respuesta (posible bloqueo de seguridad)."

    except Exception as e:
        error_str = str(e)
        logger.error(f"🚨 Error en Gemini: {error_str}")
        
        # Manejo de errores específicos
        if "404" in error_str:
            return "Error 404: El modelo no existe. Asegúrate de que el 'requirements.txt' esté corregido."
        if "location" in error_str.lower():
            return "Error de Región: Google bloquea esta IP. Cambia la región de Railway a US-East-1."
            
        # Si el error es por 'system_instruction' (en modelos viejos), intentar modo simple
        try:
            model_basic = genai.GenerativeModel(model_name='gemini-pro')
            res = model_basic.generate_content(f"{system_prompt}\n\n{user_prompt}")
            return res.text
        except:
            return f"Error técnico detallado: {error_str}"