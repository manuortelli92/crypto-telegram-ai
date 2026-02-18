import os
import google.generativeai as genai
import logging

logger = logging.getLogger(__name__)

def gemini_render(system_prompt: str, user_prompt: str) -> str:
    # 1. Recuperamos la Key dentro de la función para asegurar que lea el cambio de Railway
    api_key = os.getenv("GEMINI_API_KEY")
    
    if not api_key:
        logger.error("❌ ERROR: La variable GEMINI_API_KEY está vacía en Railway.")
        return None
        
    try:
        # 2. Configuración
        genai.configure(api_key=api_key)
        
        # 3. Inicializar modelo (usamos 1.5-flash que es el más estable para tiers gratuitos)
        model = genai.GenerativeModel(
            model_name="gemini-1.5-flash",
            generation_config={"temperature": 0.7}
        )
        
        # 4. Enviar mensaje (Combinamos system y user para evitar errores de soporte de roles)
        full_prompt = f"{system_prompt}\n\nPregunta del usuario: {user_prompt}"
        response = model.generate_content(full_prompt)
        
        if response and response.text:
            return response.text
        
        logger.warning("⚠️ Gemini devolvió una respuesta vacía o bloqueada por seguridad.")
        return None

    except Exception as e:
        # ESTO VA A APARECER EN TUS LOGS DE RAILWAY
        logger.error(f"🚨 FALLO TOTAL EN GEMINI: {str(e)}")
        return None
