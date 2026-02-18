import os
import logging
from telebot import TeleBot, types
from dotenv import load_dotenv

# Importamos nuestro motor reparado
from core.engine import build_engine_analysis
from core.state import load_state, set_chat_id, save_state
from core.learning import add_turn, register_user_interest

# Configuración de Logs profesional
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Cargar variables de entorno
load_dotenv()
TOKEN = os.getenv("TELEGRAM_TOKEN")

if not TOKEN:
    logger.critical("❌ No se encontró TELEGRAM_TOKEN en las variables de entorno.")
    exit(1)

bot = TeleBot(TOKEN, parse_mode="Markdown")

# --- MIDDLEWARE & SEGURIDAD ---

@bot.message_handler(commands=['start'])
def cmd_start(message):
    chat_id = message.chat.id
    # Registramos al usuario como admin si es el primero en usarlo
    st = load_state()
    if not st.get("chat_id"):
        set_chat_id(chat_id)
        msg = "👑 *¡Bienvenido, Administrador!* Configurado con éxito."
    else:
        msg = "🚀 *OrtelliCryptoAI Activo.* ¿En qué cripto nos enfocamos hoy?"
    
    bot.send_message(chat_id, msg)

@bot.message_handler(commands=['ayuda'])
def cmd_help(message):
    help_text = (
        "📖 *Guía de Comandos:*\n\n"
        "• `/analizar` - Reporte general del mercado.\n"
        "• `/top 10` - Ver las 10 mejores monedas.\n"
        "• `BTC`, `SOL`, `ETH` - Análisis específico de una moneda.\n"
        "• 'Evitá las memecoins' - El bot aprende tus gustos."
    )
    bot.reply_to(message, help_text)

@bot.message_handler(commands=['analizar', 'top'])
def cmd_market_report(message):
    chat_id = message.chat.id
    text = message.text
    
    # Animación de "escribiendo" para mejorar la experiencia de usuario
    bot.send_chat_action(chat_id, 'typing')
    
    state = load_state()
    response = build_engine_analysis(text, chat_id, state)
    
    bot.send_message(chat_id, response)

# --- PROCESAMIENTO DE MENSAJES NATURALES ---

@bot.message_handler(func=lambda m: True)
def handle_natural_language(message):
    chat_id = message.chat.id
    user_text = message.text
    
    # 1. Registrar interés (Aprender de lo que el usuario habla)
    register_user_interest(user_text)
    
    # 2. Guardar en memoria de corto plazo (Contexto)
    state = load_state()
    add_turn(state, chat_id, role="user", text=user_text)
    save_state(state) # Persistir el turno
    
    # 3. Mostrar que el bot está procesando
    bot.send_chat_action(chat_id, 'typing')
    
    # 4. Generar respuesta con el Engine
    try:
        response = build_engine_analysis(user_text, chat_id, state)
        
        # Guardar respuesta del bot en el historial
        add_turn(state, chat_id, role="bot", text=response)
        save_state(state)
        
        bot.reply_to(message, response)
    except Exception as e:
        logger.error(f"Error procesando mensaje: {e}")
        bot.send_message(chat_id, "⚠️ Tuve un pequeño problema técnico. Reintentá en un momento.")

# --- INICIO DEL WORKER ---

if __name__ == "__main__":
    logger.info("🚀 Bot iniciado y escuchando en Telegram...")
    # polling infinito con reconexión automática
    bot.infinity_polling(timeout=60, long_polling_timeout=30)
