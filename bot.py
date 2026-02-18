import os
import logging
import asyncio
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler, filters

# Importamos tu motor corregido
from core.engine import build_engine_analysis

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Usamos f-string con comillas triples para que no haya SyntaxError
    await update.message.reply_text(
        f"¡Hola {update.effective_user.first_name}! 👋\nSoy **OrtelliCryptoAI**. Pasame una moneda o haceme una pregunta.",
        parse_mode='Markdown'
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_text = update.message.text
    chat_id = update.effective_user.id
    await update.message.reply_chat_action("typing")
    
    # Aquí llamamos a tu función build_engine_analysis que ya tiene el try/except
    response = build_engine_analysis(user_text, chat_id, {})
    await update.message.reply_text(response, parse_mode='Markdown')

if __name__ == '__main__':
    TOKEN = os.getenv("TELEGRAM_TOKEN")
    if not TOKEN:
        logger.error("❌ Falta TELEGRAM_TOKEN")
    else:
        app = ApplicationBuilder().token(TOKEN).build()
        app.add_handler(CommandHandler('start', start))
        app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))
        logger.info("🚀 Bot encendido")
        app.run_polling()
