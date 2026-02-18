import os
import logging
import google.generativeai as genai

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def gemini_render(system_prompt: str, user_prompt: str) -> str:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return "❌ Error: Configura GEMINI_API_KEY en Railway."

    try:
        genai.configure(api_key=api_key)
        
        # --- LISTAR MODELOS DISPONIBLES (Para depuración) ---
        # Esto nos dirá en los logs de Railway qué modelos ve tu bot
        try:
            available_models = [m.name for m in genai.list_models()]
            logger.info(f"Modelos detectados: {available_models}")
        except Exception as e:
            logger.warning(f"No se pudieron listar modelos: {e}")

        # --- SELECCIÓN INTELIGENTE DEL MODELO ---
        # Intentamos en este orden de preferencia:
        modelos_a_probar = ['gemini-1.5-flash', 'gemini-1.5-pro', 'gemini-pro']
        
        selected_model = 'gemini-pro' # Por defecto
        for m in modelos_a_probar:
            # Buscamos si el modelo está en la lista de Google (o lo intentamos directamente)
            selected_model = m
            break

        logger.info(f"Usando modelo: {selected_model}")
        
        # Configurar el modelo seleccionado
        # Nota: Solo los modelos 1.5 soportan 'system_instruction'
        if '1.5' in selected_model:
            model = genai.GenerativeModel(
                model_name=selected_model,
                system_instruction=system_prompt
            )
            prompt = user_prompt
        else:
            # Para gemini-pro (viejo), unimos los prompts
            model = genai.GenerativeModel(model_name=selected_model)
            prompt = f"{system_prompt}\n\nUsuario: {user_prompt}"

        # Ajustes de seguridad
        safety = [
            {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
        ]

        response = model.generate_content(prompt, safety_settings=safety)
        
        if response and response.text:
            return response.text
        return "El modelo respondió vacío."

    except Exception as e:
        error_msg = str(e)
        logger.error(f"Error crítico: {error_msg}")
        
        if "404" in error_msg:
            return "Error 404: El modelo no se encuentra. Cambia la región de Railway a USA."
        if "location" in error_msg.lower():
            return "Error de Región: Google bloquea tu IP actual. Cambia la región en Railway Settings a US-East-1."
            
        return f"Error técnico: {error_msg}"