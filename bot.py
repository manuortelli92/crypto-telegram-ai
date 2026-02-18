import os
import logging
import asyncio
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler, filters

# Importación de la lógica central
from core.engine import build_engine_analysis

# Configuración de Logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Respuesta al comando /start - Formato corregido."""
    user_name = update.effective_user.first_name
    # Triple comilla para evitar el SyntaxError anterior
    welcome_text = f"""
¡Hola {user_name}! 👋 Soy **OrtelliCryptoAI**.

Estoy listo para analizar el mercado cripto por vos. 
🚀 Escribí el nombre de una moneda (ej: `BTC`) o preguntame algo general.

_Usá /top para ver el ranking actual._
    """
    await update.message.reply_text(welcome_text, parse_mode='Markdown')

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Maneja las consultas de texto."""
    user_text = update.message.text
    chat_id = update.effective_user.id
    
    await update.message.reply_chat_action("typing")
    
    try:
        # Procesamiento
        response = build_engine_analysis(user_text, chat_id, {})
        await update.message.reply_text(response, parse_mode='Markdown')
    except Exception as e:
        logger.error(f"Error en bot.py: {e}")
        await update.message.reply_text("⚠️ Se me recalentaron los circuitos. Reintentá en un toque.")

if __name__ == '__main__':
    TOKEN = os.getenv("TELEGRAM_TOKEN")
    
    if not TOKEN:
        logger.critical("❌ Falta TELEGRAM_TOKEN en Railway.")
    else:
        app = ApplicationBuilder().token(TOKEN).build()
        app.add_handler(CommandHandler('start', start))
        app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))
        
        logger.info("🚀 Bot iniciado correctamente.")
        app.run_polling()
