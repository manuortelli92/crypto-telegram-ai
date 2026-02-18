import os
import logging
import google.generativeai as genai

# Configuración Global de Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Cargar y Validar API Key Globalmente
API_KEY = os.getenv("GEMINI_API_KEY")
if not API_KEY:
    raise ValueError("❌ Error: No hay clave API configurada. Configura GEMINI_API_KEY en tu entorno.")

# Configurar la Clase para Manejar el Modelo Centralizadamente
class GeminiAI:
    def __init__(self, model_name: str = 'gemini-1.5-flash'):
        """Inicializa la configuración de la API y el modelo."""
        self.model_name = model_name
        self.model = None
        self.safety_settings = self._configure_safety_settings()
        self._initialize_model()

    def _initialize_model(self):
        """Configura el modelo generativo una sola vez."""
        genai.configure(api_key=API_KEY)
        self.model = genai.GenerativeModel(
            model_name=self.model_name,
            system_instruction=""
        )
        logger.info(f"Modelo {self.model_name} inicializado con éxito.")

    def _configure_safety_settings(self):
        """Define los ajustes de seguridad del modelo."""
        return [
            {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
        ]

    def generate_response(self, system_prompt: str, user_prompt: str) -> str:
        """Genera contenido basado en las instrucciones proporcionadas."""
        try:
            self.model.system_instruction = system_prompt
            response = self.model.generate_content(
                user_prompt,
                safety_settings=self.safety_settings
            )

            # Manejo de Respuestas de Google AI
            if response.candidates and response.candidates[0].finish_reason == 3:
                return "⚠️ Google bloqueó esta respuesta por sus políticas de seguridad."
            if response and response.text:
                return response.text
            return "⚠️ Google devolvió una respuesta vacía. Intenta reformular tu pregunta."

        except Exception as e:
            return self._handle_error(e)

    def _handle_error(self, error: Exception) -> str:
        """Gestión y registro de excepciones."""
        error_msg = str(error)
        logger.error(f"💥 Error: {error_msg}")

        if "429" in error_msg:
            return "🚀 ¡Calma! Mandaste demasiados mensajes seguidos. Espera un momento."
        if "location" in error_msg.lower():
            return "📍 Error de ubicación. Asegúrate de que Railway esté configurado en us-east-1."
        return f"🤯 Explotó algo internamente: {error_msg}"


# Uso Ejemplo - Entrada
def gemini_render(system_prompt: str, user_prompt: str) -> str:
    """Interfaz simplificada para interactuar con GeminiAI."""
    gemini = GeminiAI()
    return gemini.generate_response(system_prompt, user_prompt)