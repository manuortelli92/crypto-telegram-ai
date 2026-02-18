import os
import google.generativeai as genai
import logging

logger = logging.getLogger(__name__)

def gemini_render(system_prompt: str, user_prompt: str) -> str:
    # 1. Traemos la Key
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        logger.error("❌ GEMINI_API_KEY no configurada en Railway.")
        return None
        
    try:
        # 2. Configuración explícita
        genai.configure(api_key=api_key)
        
        # 3. Probamos con el nombre de modelo más compatible de todos
        # 'gemini-1.5-flash' a veces da 404, 'models/gemini-1.5-flash' es la ruta completa
        model = genai.GenerativeModel('models/gemini-1.5-flash')
        
        # 4. Construimos el mensaje de forma simple
        # Combinamos todo para que Gemini entienda su rol y la data
        prompt_final = f"INSTRUCCIONES: {system_prompt}\n\nDATOS Y PREGUNTA: {user_prompt}"
        
        response = model.generate_content(prompt_final)
        
        if response and response.text:
            return response.text
        
        return None

    except Exception as e:
        # Si el 1.5-flash sigue dando error 404, intentamos con el 1.0 Pro como último recurso
        try:
            logger.warning(f"Fallo con Flash, intentando Pro... Error: {e}")
            model_alt = genai.GenerativeModel('models/gemini-1.0-pro')
            response = model_alt.generate_content(f"{system_prompt}\n\n{user_prompt}")
            return response.text
        except Exception as e2:
            logger.error(f"🚨 FALLO TOTAL EN GEMINI: {str(e2)}")
            return None
