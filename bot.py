import os
import time
import logging
from collections import deque

from telegram import Update
from telegram.ext import Application, MessageHandler, ContextTypes, filters
from telegram.error import Conflict, NetworkError, TimedOut
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from core.memory import load_state, set_chat_id, update_prefs
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


def extract_prefs_patch(text: str) -> dict:
    """
    Parseo simple en español:
      - "evita memecoins" / "sin memecoins"
      - "prefiero SOL ETH"
      - "evita ADA XRP"
      - "riesgo bajo/medio/alto"
    """
    t = (text or "").lower().strip()
    patch = {}

    if any(k in t for k in ["evita memecoins", "sin memecoins", "no memecoins", "no memecoin", "sin memecoin"]):
        patch["avoid_memecoins"] = True
    if any(k in t for k in ["permiti memecoins", "permití memecoins", "con memecoins", "habilita memecoins"]):
        patch["avoid_memecoins"] = False

    if any(k in t for k in ["riesgo bajo", "conservador", "risk low", "low"]):
        patch["risk"] = "LOW"
    if any(k in t for k in ["riesgo medio", "medium"]):
        patch["risk"] = "MEDIUM"
    if any(k in t for k in ["riesgo alto", "agresivo", "risk high", "high"]):
        patch["risk"] = "HIGH"

    if "prefiero " in t:
        part = t.split("prefiero ", 1)[1]
        coins = part.replace(",", " ").upper().split()
        patch["focus"] = [c for c in coins if c.isalpha() and 2 <= len(c) <= 6]

    if "evita " in t:
        part = t.split("evita ", 1)[1]
        coins = part.replace(",", " ").upper().split()
        # ojo: si dice "evita memecoins" no lo tratamos como tickers
        coins = [c for c in coins if c not in {"MEMECOINS", "MEMECOIN"}]
        patch["avoid"] = [c for c in coins if c.isalpha() and 2 <= len(c) <= 6]

    return patch


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

    if not is_owner(update):
        if not rate_limit_ok(uid):
            await update.message.reply_text("Demasiadas solicitudes. Espera 1 minuto.")
            return

    register_user_interest(text)

    if text == "/start" or text.lower() in ["start", "hola", "buenas", "hey"]:
        await update.message.reply_text(
            "Hablame normal.\n"
            "Ej: 'diario', 'semanal', 'mensual', 'top 30 riesgo medio', 'BTC hoy?'\n"
            "Si sos el owner, también podés fijar preferencias:\n"
            "- 'evita memecoins'\n"
            "- 'prefiero SOL ETH'\n"
            "- 'evita ADA XRP'\n"
            "- 'riesgo bajo/medio/alto'\n"
        )
        if is_owner(update):
            set_chat_id(int(chat.id))
        return

    if is_owner(update):
        set_chat_id(int(chat.id))
        patch = extract_prefs_patch(text)
        if patch:
            prefs = update_prefs(patch)
            await update.message.reply_text(f"OK. Preferencias guardadas: {prefs}")
            return

    await update.message.reply_text("Analizando...")
    try:
        reply = build_engine_analysis(text)
        await update.message.reply_text(reply)
    except Exception as e:
        await update.message.reply_text(f"Error: {type(e).__name__}: {e}")


def build_app() -> Application:
    app = Application.builder().token(BOT_TOKEN).post_init(on_startup).build()
    app.add_handler(MessageHandler(filters.TEXT, chat_handler))
    return app


def main():
    while True:
        try:
            app = build_app()
            app.run_polling(drop_pending_updates=True, allowed_updates=Update.ALL_TYPES)
            return

        except Conflict as e:
            logging.error("Telegram Conflict (otra instancia usando getUpdates). %s", e)
            time.sleep(10)

        except (TimedOut, NetworkError) as e:
            logging.error("Error de red/timeout. Reintentando en 5s: %s", e)
            time.sleep(5)

        except Exception as e:
            logging.error("Error inesperado. Reintentando en 10s: %s", e)
            time.sleep(10)


if __name__ == "__main__":
    main()