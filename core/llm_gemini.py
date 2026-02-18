import os
import logging
import google.generativeai as genai

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def gemini_render(system_prompt: str, user_prompt: str) -> str:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return "Falta la clave API."

    try:
        genai.configure(api_key=api_key)
        
        # Probamos con el nombre de modelo más específico y actualizado
        # 'gemini-1.5-flash-latest' suele evitar el error 404 en Railway
        model = genai.GenerativeModel(
            model_name='gemini-1.5-flash-latest', 
            system_instruction=system_prompt
        )

        response = model.generate_content(user_prompt)
        
        if response and response.text:
            return response.text
        return "El modelo no generó texto."

    except Exception as e:
        error_msg = str(e)
        logger.error(f"Error: {error_msg}")
        
        # SI VUELVE A DAR 404, PROBAMOS EL MODELO PRO QUE SIEMPRE ESTÁ DISPONIBLE
        if "404" in error_msg or "not found" in error_msg.lower():
            try:
                logger.info("Intentando con gemini-pro (fallback)...")
                model_alt = genai.GenerativeModel('gemini-pro')
                res = model_alt.generate_content(f"{system_prompt}\n\n{user_prompt}")
                return res.text
            except:
                return "Error 404 persistente: Google no reconoce el modelo en esta cuenta."
        
        return f"Error: {error_msg}"