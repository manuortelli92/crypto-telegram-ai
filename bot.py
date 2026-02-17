import os
import time
import logging
from collections import deque

from telegram import Update
from telegram.ext import Application, MessageHandler, ContextTypes, filters
from telegram.error import Conflict, NetworkError, TimedOut
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from core.memory import load_state, set_chat_id
from core.learning import register_user_interest
from core.engine import build_engine_analysis

logging.basicConfig(level=logging.INFO)

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
if not BOT_TOKEN:
    raise RuntimeError("Falta BOT_TOKEN")

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
        return
    try:
        text = build_engine_analysis("informe semanal")
        await application.bot.send_message(chat_id=chat_id, text=text)
    except Exception as e:
        logging.exception("weekly send failed: %s", e)


async def on_startup(app: Application):
    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        lambda: send_weekly(app),
        "cron",
        day_of_week=SCHEDULE_DOW,
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
            await update.message.reply_text("Demasiadas solicitudes. Esperá 1 minuto.")
            return

    # aprendizaje (solo ponderaciones, no “entrena” un modelo)
    if text:
        register_user_interest(text)

    # /start como texto normal
    low = text.lower()
    if text == "/start" or low in {"start", "hola", "buenas", "hey"}:
        await update.message.reply_text(
            "Escribime normal.\n"
            "Ej: 'diario', 'semanal', 'mensual', 'top 30 riesgo medio', 'BTC hoy?'\n"
            "También: 'prefiero SOL ETH' o 'evita memecoins'."
        )
        if is_owner(update):
            set_chat_id(int(chat.id))
        return

    # guardo chat_id del owner para el semanal
    if is_owner(update):
        set_chat_id(int(chat.id))

    await update.message.reply_text("Analizando...")
    try:
        reply = build_engine_analysis(text)
        await update.message.reply_text(reply)
    except Exception as e:
        logging.exception("engine error: %s", e)
        await update.message.reply_text(f"Error: {type(e).__name__}: {e}")


def build_app() -> Application:
    app = Application.builder().token(BOT_TOKEN).post_init(on_startup).build()
    app.add_handler(MessageHandler(filters.TEXT, chat_handler))
    return app


def main():
    # resiliencia: red/timeout ok; Conflict NO se arregla con código si hay 2 instancias
    while True:
        try:
            app = build_app()
            app.run_polling(drop_pending_updates=True, allowed_updates=Update.ALL_TYPES)
            return

        except Conflict as e:
            logging.error("Conflict: hay otra instancia haciendo polling. Dejá 1 sola replica. %s", e)
            time.sleep(10)

        except (TimedOut, NetworkError) as e:
            logging.error("Red/timeout. Reintento en 5s: %s", e)
            time.sleep(5)

        except Exception as e:
            logging.error("Error inesperado. Reintento en 10s: %s", e)
            time.sleep(10)


if __name__ == "__main__":
    main()