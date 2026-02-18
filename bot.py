import os
import logging
import json
from telebot import TeleBot, types
from dotenv import load_dotenv

# --- IMPORTACIONES SINCRONIZADAS ---
from core.engine import build_engine_analysis
# Importamos desde BRAIN que es donde vive el estado ahora
from core.brain import add_turn, ensure_brain, save_brain_state
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
    """Carga el estado persistente desde el archivo JSON."""
    if os.path.exists("brain_state.json"):
        try:
            with open("brain_state.json", "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error cargando estado: {e}")
    return {}

def save_full_state(state):
    """Guarda el estado usando la función de brain.py."""
    save_brain_state(state)

# --- MANEJADORES DE COMANDOS ---

@bot.message_handler(commands=['start'])
def cmd_start(message):
    chat_id = message.chat.id
    state = load_full_state()
    ensure_brain(state) # Inicializa si está vacío
    
    # Lógica de Admin simple
    if not state.get("admin_chat_id"):
        state["admin_chat_id"] = chat_id
        save_full_state(state)
        msg = "👑 *¡Bienvenido, Administrador!* Bot configurado."
    else:
        msg = "🚀 *OrtelliCryptoAI Activo.* ¿Qué cripto analizamos?"
    
    bot.send_message(chat_id, msg)

@bot.message_handler(commands=['ayuda'])
def cmd_help(message):
    help_text = (
        "📖 *Guía de Comandos:*\n\n"
        "• `/analizar` - Reporte general.\n"
        "• `/top 10` - Ver las mejores monedas.\n"
        "• Enviar `BTC` o `ETH` para análisis rápido.\n"
        "• Hablar normal para que el bot aprenda tus gustos."
    )
    bot.reply_to(message, help_text)

@bot.message_handler(commands=['analizar', 'top'])
def cmd_market_report(message):
    chat_id = message.chat.id
    bot.send_chat_action(chat_id, 'typing')
    
    state = load_full_state()
    response = build_engine_analysis(message.text, chat_id, state)
    
    bot.send_message(chat_id, response)

# --- PROCESAMIENTO DE LENGUAJE NATURAL ---

@bot.message_handler(func=lambda m: True)
def handle_natural_language(message):
    chat_id = message.chat.id
    user_text = message.text
    
    # 1. Registrar interés global (Learning)
    register_user_interest(user_text)
    
    # 2. Cargar estado y registrar turno (Brain)
    state = load_full_state()
    
    # 3. Chat Action
    bot.send_chat_action(chat_id, 'typing')
    
    try:
        # 4. Generar respuesta con el Engine
        response = build_engine_analysis(user_text, chat_id, state)
        
        # El guardado de 'add_turn' y 'save_brain_state' ya ocurre 
        # dentro de build_engine_analysis para evitar duplicados.
        
        bot.reply_to(message, response)
    except Exception as e:
        logger.error(f"Error en el flujo principal: {e}")
        bot.send_message(chat_id, "⚠️ Error técnico. Reintentá en un momento.")

# --- INICIO ---

if __name__ == "__main__":
    logger.info("🚀 Bot iniciado correctamente.")
    bot.infinity_polling(timeout=60, long_polling_timeout=30)
