import os
import logging
import google.generativeai as genai

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def gemini_render(system_prompt: str, user_prompt: str) -> str:
    api_key = os.getenv("GEMINI_API_KEY")
    # Intentamos leer el modelo de la variable, si no, usamos el flash
    model_id = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")
    
    if not api_key:
        return "Falta GEMINI_API_KEY en Railway."

    try:
        genai.configure(api_key=api_key)
        
        # --- INTENTO 1: Usar el modelo configurado (Gemini 1.5) ---
        try:
            # Limpiamos el nombre por si tiene "models/" de más
            clean_model = model_id.replace("models/", "")
            model = genai.GenerativeModel(
                model_name=clean_model,
                system_instruction=system_prompt
            )
            response = model.generate_content(user_prompt)
            return response.text
            
        except Exception as e:
            # --- INTENTO 2: Fallback al modelo Pro (Más compatible) ---
            logger.warning(f"Fallo el modelo {model_id}, intentando gemini-pro...")
            model_alt = genai.GenerativeModel(model_name='gemini-pro')
            # El modelo pro antiguo no acepta system_instruction separado
            prompt_final = f"{system_prompt}\n\nUsuario: {user_prompt}"
            response = model_alt.generate_content(prompt_final)
            return response.text

    except Exception as e:
        error_str = str(e)
        logger.error(f"Error definitivo: {error_str}")
        
        if "404" in error_str:
            return "Error 404: Google no reconoce el modelo. Revisa el requirements.txt."
        if "location" in error_str.lower():
            return "Error de Región: Cambia la región de Railway a US-East."
            
        return f"Error: {error_str}"