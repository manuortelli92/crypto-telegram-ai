import os
import logging
import asyncio
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler, filters

# Importamos la lógica del motor de análisis
from core.engine import build_engine_analysis

# Configuración de Logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Responde al comando /start con triple comilla para evitar errores de sintaxis."""
    user_name = update.effective_user.first_name
    welcome_text = f"""
¡Hola {user_name}! 👋 Soy **OrtelliCryptoAI**.

Estoy listo para analizar el mercado por vos. 
🚀 Escribí el nombre de una moneda (ej: `BTC`) o haceme una pregunta general sobre el mercado.

_Usá /top para ver lo mejor del momento._
    """
    await update.message.reply_text(welcome_text, parse_mode='Markdown')

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Maneja los mensajes de texto del usuario."""
    user_text = update.message.text
    chat_id = update.effective_user.id
    
    # Animación de "escribiendo..."
    await update.message.reply_chat_action("typing")
    
    try:
        # Llamada al motor de análisis
        response = build_engine_analysis(user_text, chat_id, {})
        await update.message.reply_text(response, parse_mode='Markdown')
    except Exception as e:
        logger.error(f"Error en handle_message: {e}")
        await update.message.reply_text("⚠️ Hubo un bardo técnico. Probá de nuevo en un ratito.")

if __name__ == '__main__':
    TOKEN = os.getenv("TELEGRAM_TOKEN")
    
    if not TOKEN:
        logger.error("❌ ERROR: No se encontró TELEGRAM_TOKEN en Railway.")
    else:
        app = ApplicationBuilder().token(TOKEN).build()
        
        # Handlers
        app.add_handler(CommandHandler('start', start))
        app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))
        
        logger.info("🚀 Bot iniciado con éxito")
        app.run_polling()
