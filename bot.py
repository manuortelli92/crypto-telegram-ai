import os
import logging
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
# Asegúrate de que esta ruta sea correcta según tu carpeta core
from core.engine import build_engine_analysis

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Procesa mensajes del usuario usando el motor de IA."""
    try:
        user_text = update.message.text
        logger.info(f"Mensaje recibido: {user_text}")
        
        # Llamada a tu motor de IA
        response = build_engine_analysis(user_text, update.effective_user.id, {})
        await update.message.reply_text(response, parse_mode='Markdown')
    except Exception as e:
        logger.error(f"Error en el motor: {e}")
        await update.message.reply_text("🤯 Hubo un problema al analizar tu consulta.")

if __name__ == '__main__':
    token = os.getenv("TELEGRAM_TOKEN")
    if not token:
        logger.error("❌ No hay TELEGRAM_TOKEN configurado.")
    else:
        app = ApplicationBuilder().token(token).build()
        app.add_handler(CommandHandler('start', lambda u, c: u.message.reply_text("¡Bot Activo!")))
        app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))
        
        logger.info("🚀 Bot iniciado correctamente...")
        app.run_polling()
