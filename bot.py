import os
import time
import logging
import asyncio
from collections import deque

from telegram import Update
from telegram.ext import Application, MessageHandler, ContextTypes, filters
from telegram.error import Conflict, NetworkError, TimedOut
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from core.memory import load_state, set_chat_id
from core.learning import register_user_interest
from core.engine import build_engine_analysis

# Configuración de Logging más detallada
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Carga de variables de entorno
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
if not BOT_TOKEN:
    raise RuntimeError("ERROR: La variable de entorno BOT_TOKEN no está configurada.")

OWNER_ID = os.getenv("OWNER_ID", "").strip()
RATE_LIMIT_PER_MIN = int(os.getenv("RATE_LIMIT_PER_MIN", "12"))

SCHEDULE_DOW = os.getenv("SCHEDULE_DOW", "mon")
SCHEDULE_HOUR = int(os.getenv("SCHEDULE_HOUR", "9"))
SCHEDULE_MINUTE = int(os.getenv("SCHEDULE_MINUTE", "0"))

_user_hits = {}

def is_owner(update: Update) -> bool:
    uid = update.effective_user.id if update.effective_user else None
    return bool(OWNER_ID) and str(uid) == str(OWNER_ID)

def rate_limit_ok(user_id: int) -> bool:
    now = time.time()
    q = _user_hits.get(user_id)
    if q is None:
        q = deque()
        _user_hits[user_id] = q
    while q and (now - q[0]) > 60:
        q.popleft()
    if len(q) >= RATE_LIMIT_PER_MIN:
        return False
    q.append(now)
    return True

async def send_weekly(application: Application):
    state = load_state()
    chat_id = state.get("chat_id")
    if not chat_id:
        logger.warning("No se pudo enviar el informe semanal: chat_id no guardado.")
        return
    try:
        text = build_engine_analysis("informe semanal")
        await application.bot.send_message(chat_id=chat_id, text=text)
    except Exception as e:
        logger.exception(f"Fallo en el envío semanal: {e}")

async def on_startup(app: Application):
    """Configuración inicial al arrancar el bot."""
    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        send_weekly,
        "cron",
        day_of_week=SCHEDULE_DOW,
        hour=SCHEDULE_HOUR,
        minute=SCHEDULE_MINUTE,
        args=[app],
        id="weekly_report",
        replace_existing=True,
    )
    scheduler.start()
    logger.info("Scheduler iniciado. Tarea semanal programada.")

async def chat_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat = update.effective_chat
    if not user or not chat or not update.message:
        return

    uid = user.id
    text = (update.message.text or "").strip()

    # Rate limit solo para usuarios que no son el dueño
    if not is_owner(update):
        if not rate_limit_ok(uid):
            await update.message.reply_text("⏳ Demasiadas solicitudes. Esperá un minuto.")
            return

    # Registrar interés (aprendizaje básico)
    if text:
        register_user_interest(text)

    # Lógica de comandos básicos
    low = text.lower()
    if text == "/start" or low in {"start", "hola", "buenas", "hey"}:
        await update.message.reply_text(
            "🤖 **¡Hola! Soy tu asistente cripto.**\n\n"
            "Podés pedirme análisis así:\n"
            "• '¿Cómo viene BTC hoy?'\n"
            "• 'Informe mensual'\n"
            "• 'Top 30 riesgo medio'\n"
            "• 'Prefiero SOL y ETH'"
        )
        if is_owner(update):
            set_chat_id(int(chat.id))
            logger.info(f"Chat ID del dueño guardado: {chat.id}")
        return

    # Si es el owner, nos aseguramos de tener el chat_id actualizado
    if is_owner(update):
        set_chat_id(int(chat.id))

    # Procesamiento con el Engine de IA
    msg_espera = await update.message.reply_text("🔍 Analizando el mercado...")
    try:
        reply = build_engine_analysis(text)
        await update.message.reply_text(reply)
    except Exception as e:
        logger.exception(f"Error en el engine: {e}")
        await update.message.reply_text("❌ Lo siento, tuve un problema procesando tu consulta.")
    finally:
        # Opcional: borrar el mensaje de "Analizando..."
        try:
            await context.bot.delete_message(chat_id=chat.id, message_id=msg_espera.message_id)
        except:
            pass

def build_app() -> Application:
    return Application.builder().token(BOT_TOKEN).post_init(on_startup).build()

def main():
    """Función principal corregida para Railway."""
    app = build_app()
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, chat_handler))
    
    logger.info("Iniciando bot...")
    
    # drop_pending_updates=True evita que el bot responda mensajes acumulados al reiniciar
    # run_polling maneja automáticamente reintentos de red
    app.run_polling(drop_pending_updates=True, allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
