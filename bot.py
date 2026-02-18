import os
import logging
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler, filters

# Importamos la lógica del motor y la IA
from core.engine import build_engine_analysis

# Configuración de Logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- COMANDOS ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Responde al comando /start."""
    user_name = update.effective_user.first_name
    # Usamos triple comilla para evitar el SyntaxError de las comillas
    welcome_text = f"""
¡Hola {user_name}! 👋 Acá OrtelliCryptoAI.

Soy tu analista de la city pero en Telegram. 
📈 Te tiro la posta sobre el mercado, precios verificados y análisis con IA.

**¿Qué podés hacer?**
• Escribí el nombre de una moneda (ej: `BTC` o `SOL`).
• Consultame algo general (ej: `¿Cómo ves el mercado hoy?`).
• Usá `/top` para ver lo más caliente del momento.

_No es consejo financiero, es timba con data._ 🚀
    """
    await update.message.reply_text(welcome_text, parse_mode='Markdown')

async def top_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Muestra el top de monedas analizadas."""
    await update.message.reply_chat_action("typing")
    # Llamamos al engine con un texto genérico para que devuelva el top
    response = build_engine_analysis("Dame el top 10", update.effective_user.id, {})
    await update.message.reply_text(response, parse_mode='Markdown')

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Maneja cualquier mensaje de texto del usuario."""
    user_text = update.message.text
    chat_id = update.effective_user.id
    
    # Animación de "escribiendo..." para que el usuario no se impaciente
    await update.message.reply_chat_action("typing")
    
    try:
        # Procesamos la consulta a través del engine
        response = build_engine_analysis(user_text, chat_id, {})
        await update.message.reply_text(response, parse_mode='Markdown')
    except Exception as e:
        logger.error(f"Error handling message: {e}")
        await update.message.reply_text("⚠️ Se me cruzaron los cables. Probá de nuevo en un toque.")

# --- MAIN ---

if __name__ == '__main__':
    # Token de Telegram desde Railway
    TOKEN = os.getenv("TELEGRAM_TOKEN")
    
    if not TOKEN:
        print("❌ ERROR: No se encontró TELEGRAM_TOKEN en las variables de entorno.")
    else:
        # Construcción de la aplicación
        application = ApplicationBuilder().token(TOKEN).build()
        
        # Handlers
        application.add_handler(CommandHandler('start', start))
        application.add_handler(CommandHandler('top', top_command))
        application.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))
        
        print("🚀 OrtelliCryptoAI está vivo. Esperando mensajes...")
        application.run_polling()
