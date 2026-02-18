import os
import logging
from telegram import Update, constants
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
from core.engine import build_engine_analysis
from core.memory import load_state, save_state, set_chat_id
from core.learning import register_user_interest

# Configuración Global
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

TOKEN = os.getenv("BOT_TOKEN")
OWNER_ID = os.getenv("OWNER_ID")  # Opcional
CONNECT_TIMEOUT = int(os.getenv("CONNECT_TIMEOUT", 30))

if not TOKEN or not OWNER_ID:
    print("❌ ERROR: Faltan variables de entorno necesarias.")
    exit(1)

MESSAGES = {
    "start": (
        "¡Hola, che! 👋 Soy **OrtelliCryptoAI**.

"
        "Analizo el mercado cripto y más:

"
        "• `¿Cómo ves SOL?`
"
        "• `¿Qué compro hoy?`
"
        "• Noticias importantes: `¿Novedades importantes?`"
    ),
    "help": (
        "🇦🇷 Guía rápida:
"
        "1. Preguntá algo sobre cripto.
"
        "2. Usa `/start` para empezar.
"
        "3. API: CoinGecko, Binance."
    ),
    "error_generic": "⚠️ Hubo un bardo técnico, intentá más tarde."
}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    set_chat_id(update.effective_chat.id)
    await update.message.reply_text(MESSAGES["start"], parse_mode=constants.ParseMode.MARKDOWN)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        state = load_state()
        user_text = update.message.text
        register_user_interest(user_text)

        # Respuesta
        response = build_engine_analysis(user_text, update.effective_chat.id, state)
        await update.message.reply_text(response, parse_mode=constants.ParseMode.MARKDOWN)
    except Exception as e:
        logger.error(f"Error: {e}")
        await update.message.reply_text(MESSAGES["error_generic"], parse_mode=constants.ParseMode.MARKDOWN)

if __name__ == "__main__":
    app = ApplicationBuilder().token(TOKEN).connect_timeout(CONNECT_TIMEOUT).read_timeout(CONNECT_TIMEOUT).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))
    print("🚀 Bot encendido.")
    app.run_polling(drop_pending_updates=True)