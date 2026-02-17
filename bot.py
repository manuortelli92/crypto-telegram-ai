import os
import time
import logging
from collections import deque

from telegram import Update
from telegram.ext import Application, MessageHandler, ContextTypes, filters
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from core.memory import load_state, set_chat_id
from core.learning import register_user_interest
from core.engine import build_engine_analysis

logging.basicConfig(level=logging.INFO)

BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("Falta BOT_TOKEN")

OWNER_ID = os.getenv("OWNER_ID", "").strip()
RATE_LIMIT_PER_MIN = int(os.getenv("RATE_LIMIT_PER_MIN", "12"))

SCHEDULE_HOUR = int(os.getenv("SCHEDULE_HOUR", "9"))
SCHEDULE_MINUTE = int(os.getenv("SCHEDULE_MINUTE", "0"))

_user_hits = {}

def is_owner(update: Update) -> bool:
    uid = update.effective_user.id if update.effective_user else None
    return str(uid) == str(OWNER_ID)

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
        return
    try:
        text = build_engine_analysis("informe semanal")
        await application.bot.send_message(chat_id=chat_id, text=text)
    except Exception as e:
        logging.error("weekly send failed: %s", e)

async def on_startup(app: Application):
    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        lambda: send_weekly(app),
        "cron",
        day_of_week="mon",
        hour=SCHEDULE_HOUR,
        minute=SCHEDULE_MINUTE,
        id="weekly_report",
        replace_existing=True,
    )
    scheduler.start()

async def chat_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat = update.effective_chat
    if not user or not chat or not update.message:
        return

    uid = user.id
    text = (update.message.text or "").strip()

    # Rate limit solo usuarios normales
    if not is_owner(update):
        if not rate_limit_ok(uid):
            await update.message.reply_text("Demasiadas solicitudes. Espera 1 minuto.")
            return

    # Aprende de lo que escriben (solo suma pesos, no responde)
    register_user_interest(text)

    # /start como texto normal
    if text == "/start" or text.lower() in ["start", "hola", "buenas", "hey"]:
        await update.message.reply_text(
            "Escribi por ejemplo:\n"
            "informe diario\n"
            "informe semanal\n"
            "informe mensual\n"
            "o preguntame por una moneda puntual."
        )
        # Guardamos chat_id solo del owner para informes automáticos
        if is_owner(update):
            set_chat_id(int(chat.id))
        return

    # Guardamos chat_id del owner si escribe (para el semanal)
    if is_owner(update):
        set_chat_id(int(chat.id))

    await update.message.reply_text("Analizando...")
    try:
        reply = build_engine_analysis(text)
        await update.message.reply_text(reply)
    except Exception as e:
        await update.message.reply_text(f"Error: {type(e).__name__}: {e}")

def main():
    app = Application.builder().token(BOT_TOKEN).post_init(on_startup).build()
    app.add_handler(MessageHandler(filters.TEXT, chat_handler))
    app.run_polling()

if __name__ == "__main__":
    main()