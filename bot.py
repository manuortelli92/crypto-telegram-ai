import os
import logging
import asyncio
from telegram import Update, constants
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

# Importamos tu artillería pesada del core
from core.engine import build_engine_analysis
from core.memory import load_state, save_state, set_chat_id
from core.learning import register_user_interest

# Configuración de Logs
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Variables de Entorno (Asegurate de ponerlas en Railway)
TOKEN = os.getenv("BOT_TOKEN")
OWNER_ID = os.getenv("OWNER_ID") # Opcional: para restringir uso

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /start: Registra al usuario y da la bienvenida."""
    chat_id = update.effective_chat.id
    set_chat_id(chat_id) # Guardamos el ID en state.json
    
    welcome_msg = (
        "¡Hola, che! 👋 Soy **OrtelliCryptoAI**.\n\n"
        "Analizo el mercado en tiempo real, verifico precios en varios exchanges y te tiro la posta.\n\n"
        "👉 **¿Qué podés hacer?**\n"
        "• Preguntame por una moneda: `¿Cómo ves SOL?` o `BTC`\n"
        "• Pedime un análisis general: `¿Qué compro hoy?` o `Top 10 agresivo`\n"
        "• Enterate de noticias: `¿Qué está pasando?`"
    )
    await update.message.reply_text(welcome_msg, parse_mode=constants.ParseMode.MARKDOWN)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /ayuda."""
    help_text = (
        "🇦🇷 **Guía rápida:**\n"
        "1. **Análisis:** Escribí cualquier duda sobre cripto.\n"
        "2. **Precisión:** Cruzo datos de CoinGecko, Binance y Kraken.\n"
        "3. **Memoria:** Aprendo qué monedas te interesan más.\n\n"
        "Si el bot no responde, esperá 10 segundos (puede ser el rate-limit de la API)."
    )
    await update.message.reply_text(help_text, parse_mode=constants.ParseMode.MARKDOWN)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Maneja todos los mensajes de texto."""
    user_text = update.message.text
    chat_id = update.effective_chat.id
    
    if not user_text:
        return

    # 1. Aprender de lo que el usuario escribe
    register_user_interest(user_text)

    # 2. Feedback visual: "Escribiendo..."
    await context.bot.send_chat_action(chat_id=chat_id, action=constants.ChatAction.TYPING)

    # 3. Procesar con el Engine
    try:
        # Cargamos el estado (preferencias, memoria, etc)
        state = load_state()
        
        # El engine hace toda la magia (verificación, noticias, Gemini)
        response = build_engine_analysis(user_text, chat_id, state)
        
        # 4. Enviar respuesta
        await update.message.reply_text(response, parse_mode=constants.ParseMode.MARKDOWN)
        
    except Exception as e:
        logger.error(f"Error procesando mensaje: {e}", exc_info=True)
        error_msg = "⚠️ *Hubo un bardo técnico.*\nNo pude terminar el análisis, probá de nuevo en un minuto que seguro se enfrió la API."
        await update.message.reply_text(error_msg, parse_mode=constants.ParseMode.MARKDOWN)

if __name__ == '__main__':
    if not TOKEN:
        print("❌ ERROR: No se encontró el BOT_TOKEN en las variables de entorno.")
        exit(1)

    # Construcción de la App de Telegram
    # Usamos connect_timeout y read_timeout más largos para Railway
    app = ApplicationBuilder().token(TOKEN).connect_timeout(30).read_timeout(30).build()

    # Handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("ayuda", help_command))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))

    print("🚀 Bot encendido y patrullando el mercado...")
    app.run_polling(drop_pending_updates=True)
