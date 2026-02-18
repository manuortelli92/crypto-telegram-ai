import os
import logging
import google.generativeai as genai

# Configuración de logs para ver errores en el panel de Railway
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def gemini_render(system_prompt: str, user_prompt: str) -> str:
    # 1. Obtener la clave desde las variables de entorno de Railway
    api_key = os.getenv("GEMINI_API_KEY")
    
    if not api_key:
        logger.error("❌ ERROR: No se encontró GEMINI_API_KEY en las variables de Railway.")
        return "Error: Configuración de API Key faltante."

    try:
        # 2. Configuración de la API
        genai.configure(api_key=api_key)
        
        # 3. Configurar el modelo con el nombre técnico exacto
        # Usamos 'models/gemini-1.5-flash' para evitar el error 404
        model = genai.GenerativeModel(
            model_name='models/gemini-1.5-flash',
            system_instruction=system_prompt
        )
        
        # 4. Ajustes de seguridad relajados para evitar bloqueos innecesarios
        safety_settings = [
            {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
        ]

        # 5. Intentar generar la respuesta
        response = model.generate_content(
            user_prompt,
            safety_settings=safety_settings
        )
        
        if response and response.text:
            return response.text
        else:
            return "El modelo no devolvió texto. Revisa los filtros de seguridad."

    except Exception as e:
        error_msg = str(e)
        logger.error(f"🚨 ERROR EN GEMINI: {error_msg}")
        
        # Si falla el modelo 1.5, intentamos el Pro (por si la librería es vieja)
        try:
            logger.info("Intentando con modelo gemini-pro como respaldo...")
            model_alt = genai.GenerativeModel('gemini-pro')
            # El modelo antiguo no usa system_instruction, así que sumamos los textos
            full_prompt = f"{system_prompt}\n\n{user_prompt}"
            res = model_alt.generate_content(full_prompt)
            return res.text
        except:
            if "location" in error_msg.lower():
                return "Error: Región no admitida por Google (IP de Railway bloqueada)."
            return f"Error técnico: {error_msg}"