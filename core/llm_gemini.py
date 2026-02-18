import os
import google.generativeai as genai
import logging

logger = logging.getLogger(__name__)

def gemini_render(system_prompt: str, user_prompt: str) -> str:
    api_key = os.getenv("GEMINI_API_KEY")
    
    if not api_key:
        logger.error("❌ GEMINI_API_KEY no configurada.")
        return None
        
    try:
        genai.configure(api_key=api_key)
        
        # CAMBIO CLAVE: Usamos el nombre técnico completo que la API v1beta espera
        model = genai.GenerativeModel(
            model_name="gemini-1.5-flash-latest" 
        )
        
        # Combinamos todo en un solo string para evitar problemas de estructura
        prompt_final = f"INSTRUCCIONES: {system_prompt}\n\nDATOS Y PREGUNTA: {user_prompt}"
        
        response = model.generate_content(prompt_final)
        
        if response and response.text:
            return response.text
        
        return None

    except Exception as e:
        # Si falla el flash-latest, intentamos con el pro por las dudas
        try:
            logger.warning("Reintentando con modelo alternativo...")
            model_alt = genai.GenerativeModel("gemini-pro")
            response = model_alt.generate_content(f"{system_prompt}\n\n{user_prompt}")
            return response.text
        except:
            logger.error(f"🚨 FALLO TOTAL EN GEMINI: {str(e)}")
            return None
