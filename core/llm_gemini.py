import os
import logging
import google.generativeai as genai

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def gemini_render(system_prompt: str, user_prompt: str) -> str:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return "❌ Error: No hay clave API en Railway."

    try:
        genai.configure(api_key=api_key)
        
        # --- DIAGNÓSTICO: LISTAR MODELOS REALES ---
        modelos_disponibles = []
        try:
            for m in genai.list_models():
                if 'generateContent' in m.supported_generation_methods:
                    modelos_disponibles.append(m.name.replace('models/', ''))
            logger.info(f"✅ Modelos que tu clave SI puede usar: {modelos_disponibles}")
        except Exception as e:
            logger.error(f"❌ No pude listar los modelos: {e}")

        # --- SELECCIÓN AUTOMÁTICA ---
        # Si 'gemini-1.5-flash' está en la lista, lo usamos. Si no, usamos el primero que aparezca.
        if not modelos_disponibles:
            # Si la lista está vacía, intentamos los nombres estándar por desesperación
            modelos_disponibles = ['gemini-1.5-flash', 'gemini-1.5-pro', 'gemini-pro']
        
        target_model = 'gemini-1.5-flash' if 'gemini-1.5-flash' in modelos_disponibles else modelos_disponibles[0]
        
        logger.info(f"🤖 Intentando usar el modelo: {target_model}")

        # Configuración del modelo
        model = genai.GenerativeModel(model_name=target_model)
        
        # Respuesta simple (unimos prompts para máxima compatibilidad)
        prompt_final = f"{system_prompt}\n\nPregunta: {user_prompt}"
        response = model.generate_content(prompt_final)
        
        if response and response.text:
            return response.text
        return "⚠️ Google devolvió una respuesta vacía."

    except Exception as e:
        error_msg = str(e)
        logger.error(f"💥 Error final: {error_msg}")
        
        if "403" in error_msg:
            return "❌ Error 403: Tu clave API no tiene permisos. ¿Aceptaste los términos en Google AI Studio?"
        if "404" in error_msg:
            return "❌ Error 404: Google sigue diciendo que el modelo no existe. Intenta crear una CLAVE NUEVA."
            
        return f"❌ Error técnico: {error_msg}"