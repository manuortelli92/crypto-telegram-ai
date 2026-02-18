import os
import logging
import google.generativeai as genai
from typing import Optional

# Configuración de Logging para Diagnóstico
logger = logging.getLogger(__name__)

# Configuración Global
API_KEY = os.getenv("GEMINI_API_KEY")

def setup_gemini():
    """Configura la API de forma segura al inicio."""
    if not API_KEY:
        logger.error("❌ GEMINI_API_KEY no detectada en las variables de entorno.")
        return False
    try:
        genai.configure(api_key=API_KEY)
        return True
    except Exception as e:
        logger.error(f"❌ Error configurando Google AI: {e}")
        return False

# Inicializamos una vez
GEMINI_READY = setup_gemini()

def gemini_render(system_prompt: str, user_prompt: str) -> str:
    """
    Motor de análisis de lenguaje natural.
    Diseñado para máxima estabilidad en el Tier Gratuito de Google.
    """
    if not GEMINI_READY:
        return "⚠️ Error: La IA no está configurada correctamente en Railway."

    try:
        # Usamos 1.5-flash: es el más rápido y tiene la cuota más alta para gratis
        model = genai.GenerativeModel('gemini-1.5-flash')

        # UNIFICACIÓN ESTRATÉGICA: 
        # Combinamos todo en un solo bloque con separadores claros.
        full_input = (
            f"### INSTRUCCIONES OPERATIVAS ###\n{system_prompt}\n\n"
            f"### CONTEXTO Y DATOS ###\n{user_prompt}\n\n"
            f"### RESPUESTA ###"
        )

        # AJUSTES DE SEGURIDAD: 
        # Importante para que no bloquee análisis de mercado por 'riesgo'
        safety = [
            {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_ONLY_HIGH"},
            {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_ONLY_HIGH"},
            {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_ONLY_HIGH"},
            {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_ONLY_HIGH"},
        ]

        # Configuración de generación: temperatura baja para menos 'delirio'
        generation_config = {
            "temperature": 0.4,
            "top_p": 0.9,
            "max_output_tokens": 1000,
        }

        response = model.generate_content(
            full_input,
            safety_settings=safety,
            generation_config=generation_config
        )

        # VALIDACIÓN DE RESPUESTA
        if not response or not response.text:
            logger.warning("⚠️ Gemini devolvió una respuesta vacía o fue bloqueada por filtros.")
            return "⚠️ La IA no pudo procesar esta consulta (posible filtro de seguridad)."

        # Limpieza básica de la respuesta para Telegram
        clean_res = response.text.strip()
        
        # Si la respuesta es demasiado corta, podría ser un error silencioso
        if len(clean_res) < 2:
            return "⚠️ La IA tuvo un problema al generar el texto."

        return clean_res

    except Exception as e:
        error_msg = str(e)
        logger.error(f"💥 Fallo en el motor Gemini: {error_msg}")

        # DIAGNÓSTICO ESPECÍFICO
        if "429" in error_msg:
            return "⏳ Cuota agotada (15 req/min). Por favor, esperá un minuto."
        if "403" in error_msg:
            return "🚫 Error 403: Acceso denegado (¿API Key activa?)."
        if "location" in error_msg.lower():
            return "📍 Error de Región: Railway te asignó una zona donde el Plan Gratis de Google no opera."
        
        return f"🤯 Error técnico en la IA: {error_msg[:100]}"
