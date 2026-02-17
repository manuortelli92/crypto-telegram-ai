import os
import time
import logging
from collections import deque
from typing import Any, Dict, Optional

from telegram import Update
from telegram.ext import Application, MessageHandler, ContextTypes, filters
from telegram.error import Conflict, NetworkError, TimedOut
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from core.memory import load_state, set_chat_id
from core.learning import register_user_interest
from core.engine import build_engine_analysis

# Brain conversacional
from core.brain import add_turn, recent_context_text, apply_patch_to_session

logging.basicConfig(level=logging.INFO)

BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("Falta BOT_TOKEN")

OWNER_ID = os.getenv("OWNER_ID", "").strip()
RATE_LIMIT_PER_MIN = int(os.getenv("RATE_LIMIT_PER_MIN", "12"))

SCHEDULE_HOUR = int(os.getenv("SCHEDULE_HOUR", "9"))
SCHEDULE_MINUTE = int(os.getenv("SCHEDULE_MINUTE", "0"))
SCHEDULE_DOW = os.getenv("SCHEDULE_DOW", "mon")

_user_hits = {}

# Intentamos traer save_state si existe
try:
    from core.memory import save_state  # type: ignore
except Exception:
    save_state = None  # fallback


def _persist_state(state: Dict[str, Any]) -> None:
    if save_state is None:
        # No crasheamos: solo no persistimos brain
        logging.warning("core.memory.save_state() no existe. Brain NO persistente (solo RAM).")
        return
    try:
        save_state(state)  # type: ignore
    except Exception as e:
        logging.error("save_state falló: %s", e)


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


def _enrich_text_with_context(state: Dict[str, Any], chat_id: int, user_text: str) -> str:
    # Actualiza preferencias del brain en base al mensaje actual
    brain_prefs = apply_patch_to_session(state, chat_id, user_text)

    ctx = recent_context_text(state, chat_id, max_turns=6)

    enriched = (
        f"CONTEXTO RECIENTE:\n{ctx}\n\n"
        f"PEDIDO ACTUAL:\n{user_text}\n\n"
        f"PARAMETROS:\n"
        f"mode={brain_prefs.get('mode')} top_n={brain_prefs.get('top_n')} "
        f"risk_pref={brain_prefs.get('risk_pref')} "
        f"focus={brain_prefs.get('focus')} avoid={brain_prefs.get('avoid')}"
    )
    return enriched


async def send_weekly(application: Application):
    state = load_state()
    chat_id = state.get("chat_id")
    if not chat_id:
        return
    try:
        # Usamos brain (si existe) para que el semanal sea coherente
        enriched = _enrich_text_with_context(state, int(chat_id), "informe semanal")
        text = build_engine_analysis(enriched)
        await application.bot.send_message(chat_id=chat_id, text=text)

        add_turn(state, int(chat_id), "bot", text)
        _persist_state(state)

    except Exception as e:
        logging.error("weekly send failed: %s", e)


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
    chat_id = int(chat.id)
    text = (update.message.text or "").strip()

    # Rate limit solo usuarios normales
    if not is_owner(update):
        if not rate_limit_ok(uid):
            await update.message.reply_text("Demasiadas solicitudes. Espera 1 minuto.")
            return

    # Aprende de lo que escriben (learning ligero)
    register_user_interest(text)

    # Cargamos estado una vez por mensaje
    state = load_state()

    # /start como texto normal
    if text == "/start" or text.lower() in ["start", "hola", "buenas", "hey"]:
        await update.message.reply_text(
            "Escribime normal.\n"
            "Ej: 'diario', 'semanal', 'mensual', 'top 30 riesgo medio', 'BTC hoy?'\n"
            "También podés decir: 'prefiero SOL ETH' o 'evita memecoins'.\n"
        )
        if is_owner(update):
            set_chat_id(chat_id)
        return

    # Guardamos chat_id del owner para informes automáticos
    if is_owner(update):
        set_chat_id(chat_id)

    # Brain: guardamos turno user + persistimos
    add_turn(state, chat_id, "user", text)
    _persist_state(state)

    # Respuesta
    await update.message.reply_text("Analizando...")
    try:
        enriched_text = _enrich_text_with_context(state, chat_id, text)
        reply = build_engine_analysis(enriched_text)
        await update.message.reply_text(reply)

        # Brain: guardamos turno bot + persistimos
        add_turn(state, chat_id, "bot", reply)
        _persist_state(state)

    except Exception as e:
        await update.message.reply_text(f"Error: {type(e).__name__}: {e}")


def build_app() -> Application:
    app = Application.builder().token(BOT_TOKEN).post_init(on_startup).build()
    app.add_handler(MessageHandler(filters.TEXT, chat_handler))
    return app


def main():
    # Loop de resiliencia: si Telegram corta por Conflict o red, reintenta
    while True:
        try:
            app = build_app()
            # drop_pending_updates evita cola vieja si se reinicia
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