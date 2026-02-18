import os
import google.generativeai as genai
import logging

logger = logging.getLogger(__name__)

def gemini_render(system_prompt: str, user_prompt: str) -> str:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        logger.error("❌ No hay API KEY.")
        return None
        
    try:
        genai.configure(api_key=api_key)
        
        # En el plan gratis, a veces el modelo 'gemini-pro' es el más estable
        # pero 'gemini-1.5-flash' es más rápido. Probemos con el Pro que no falla nunca.
        model = genai.GenerativeModel('gemini-pro')
        
        # Juntamos todo en un solo mensaje. 
        # Las cuentas gratis a veces fallan si separás 'system_instruction'.
        prompt_final = f"Actuá como este personaje: {system_prompt}\n\nPregunta: {user_prompt}"
        
        response = model.generate_content(prompt_final)
        
        if response and response.text:
            return response.text
        return None

    except Exception as e:
        # Si falla el Pro, intentamos el Flash con el nombre pelado
        try:
            logger.warning("Falló Pro, intentando Flash...")
            model_f = genai.GenerativeModel('gemini-1.5-flash')
            res = model_f.generate_content(f"{system_prompt}\n{user_prompt}")
            return res.text
        except Exception as e2:
            logger.error(f"🚨 ERROR FINAL: {str(e2)}")
            return None
