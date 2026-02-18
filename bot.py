import os
import logging
import json
from telebot import TeleBot, types
from dotenv import load_dotenv

# --- IMPORTACIONES SINCRONIZADAS ---
from core.engine import build_engine_analysis
# Eliminamos add_turn de aquí porque el Engine ya se encarga de registrar los turnos
from core.brain import ensure_brain, save_brain_state
from core.learning import register_user_interest

# Configuración de Logs
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

load_dotenv()
TOKEN = os.getenv("TELEGRAM_TOKEN")

if not TOKEN:
    logger.critical("❌ No se encontró TELEGRAM_TOKEN.")
    exit(1)

bot = TeleBot(TOKEN, parse_mode="Markdown")

# --- FUNCIONES DE ESTADO (PUENTE) ---

def load_full_state():
    """Carga el estado persistente con manejo de errores robusto."""
    if os.path.exists("brain_state.json"):
        try:
            with open("brain_state.json", "r", encoding="utf-8") as f:
                data = json.load(f)
                return data if isinstance(data, dict) else {}
        except (json.JSONDecodeError, Exception) as e:
            logger.error(f"⚠️ Archivo de estado corrupto, iniciando nuevo: {e}")
            return {}
    return {}

def save_full_state(state):
    """Guarda el estado usando la persistencia de brain."""
    save_brain_state(state)

# --- MANEJADORES DE COMANDOS ---

@bot.message_handler(commands=['start'])
def cmd_start(message):
    chat_id = message.chat.id
    state = load_full_state()
    ensure_brain(state) 
    
    # Corregido: Usar una clave consistente para el administrador
    if not state.get("admin_chat_id"):
        state["admin_chat_id"] = chat_id
        save_full_state(state)
        msg = "👑 *¡Bienvenido, Administrador!* Bot configurado con éxito."
    else:
        msg = "🚀 *OrtelliCryptoAI Activo.* ¿Qué cripto analizamos hoy?"
    
    bot.send_message(chat_id, msg)

@bot.message_handler(commands=['ayuda'])
def cmd_help(message):
    help_text = (
        "📖 *Guía de Comandos:*\n\n"
        "• `/analizar` - Reporte general de mercado.\n"
        "• `/top` - Ver las monedas con mejor score.\n"
        "• Enviá un ticker (ej: `BTC`) para análisis rápido.\n"
        "• Hablá normal: el bot aprende tus preferencias de riesgo."
    )
    bot.reply_to(message, help_text)

@bot.message_handler(commands=['analizar', 'top'])
def cmd_market_report(message):
    chat_id = message.chat.id
    bot.send_chat_action(chat_id, 'typing')
    
    state = load_full_state()
    # Pasamos el texto del comando para que el engine sepa qué filtrar
    response = build_engine_analysis(message.text, chat_id, state)
    
    bot.send_message(chat_id, response)

# --- PROCESAMIENTO DE LENGUAJE NATURAL ---

@bot.message_handler(func=lambda m: True)
def handle_natural_language(message):
    chat_id = message.chat.id
    user_text = message.text
    
    # 1. Aprender de los tickers mencionados globalmente
    register_user_interest(user_text)
    
    # 2. Cargar estado fresco para esta sesión
    state = load_full_state()
    
    bot.send_chat_action(chat_id, 'typing')
    
    try:
        # 3. El Engine ahora maneja internamente el add_turn y el save_state
        # Esto evita que los mensajes se guarden doble o se crucen
        response = build_engine_analysis(user_text, chat_id, state)
        
        bot.reply_to(message, response)
        
    except Exception as e:
        logger.error(f"💥 Error en handle_natural_language: {e}")
        bot.send_message(chat_id, "⚠️ Tuve un problema al procesar tu mensaje. Probá de nuevo.")

# --- INICIO ---

if __name__ == "__main__":
    logger.info("🚀 Bot iniciado y escuchando...")
    # Agregamos skip_pending para que no procese mensajes viejos al arrancar
    bot.infinity_polling(timeout=60, long_polling_timeout=30, skip_pending=True)
