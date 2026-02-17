import os
import time
import logging
from collections import deque

from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from core.memory import load_state, set_chat_id, update_prefs
from core.engine import build_ai_brief

logging.basicConfig(level=logging.INFO)

BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("Falta BOT_TOKEN en Railway")

OWNER_ID = os.getenv("OWNER_ID", "").strip()          # REQUIRED (tu USER_ID)
BOT_PIN = os.getenv("BOT_PIN", "").strip()            # OPTIONAL
RATE_LIMIT_PER_MIN = int(os.getenv("RATE_LIMIT_PER_MIN", "12"))

SCHEDULE_DOW = os.getenv("SCHEDULE_DOW", "mon")
SCHEDULE_HOUR = int(os.getenv("SCHEDULE_HOUR", "9"))
SCHEDULE_MINUTE = int(os.getenv("SCHEDULE_MINUTE", "0"))

_user_hits = {}

def _is_owner(update: Update) -> bool:
    if not OWNER_ID:
        return False
    uid = update.effective_user.id if update.effective_user else None
    return str(uid) == str(OWNER_ID)

def _rate_limit_ok(user_id: int) -> bool:
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

def _pin_ok(state: dict) -> bool:
    if not BOT_PIN:
        return True
    return state.get("pin_ok") is True

def _set_pin_ok() -> None:
    # Guardamos un flag persistente en state.json (via core.memory)
    state = load_state()
    state["pin_ok"] = True
    from core.memory import save_state
    save_state(state)

def _extraer_preferencias(texto: str):
    t = texto.lower()
    patch = {}

    if "menos riesgo" in t or "conservador" in t:
        patch["risk"] = "low"
    if "mas riesgo" in t or "agresivo" in t:
        patch["risk"] = "high"

    if "evita " in t:
        parte = t.split("evita ", 1)[1]
        coins = parte.replace(",", " ").upper().split()
        patch["avoid"] = list({c for c in coins if len(c) <= 6})

    if "prefiero " in t:
        parte = t.split("prefiero ", 1)[1]
        coins = parte.replace(",", " ").upper().split()
        patch["focus"] = list({c for c in coins if len(c) <= 6})

    return patch if patch else None

async def _deny(update: Update, reason: str = "Acceso denegado.") -> None:
    uid = update.effective_user.id if update.effective_user else None
    uname = update.effective_user.username if (update.effective_user and update.effective_user.username) else None
    await update.message.reply_text(
        f"{reason}\n"
        f"ID detectado: {uid}\n"
        f"Usuario: @{uname}" if uname else f"{reason}\nID detectado: {uid}"
    )

# -------------------- COMANDOS --------------------

async def whoami_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id if update.effective_user else None
    chat_id = update.effective_chat.id if update.effective_chat else None
    username = update.effective_user.username if (update.effective_user and update.effective_user.username) else "(sin username)"
    await update.message.reply_text(
        "DEBUG INFO\n"
        f"USER_ID: {user_id}\n"
        f"CHAT_ID: {chat_id}\n"
        f"USERNAME: {username}"
    )

async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_owner(update):
        await _deny(update, "Acceso denegado (solo owner).")
        return

    chat_id = int(update.effective_chat.id)
    set_chat_id(chat_id)

    msg = (
        "OK. Acceso habilitado.\n"
        "Podes escribirme normal y te respondo.\n"
    )
    if BOT_PIN:
        msg += "PIN activo: manda /pin TU_PIN para desbloquear.\n"
    await update.message.reply_text(msg)

async def pin_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_owner(update):
        await _deny(update, "Acceso denegado (solo owner).")
        return

    if not BOT_PIN:
        await update.message.reply_text("PIN no configurado (BOT_PIN vacio).")
        return

    if not context.args:
        await update.message.reply_text("Uso: /pin 1234")
        return

    if context.args[0].strip() == BOT_PIN:
        _set_pin_ok()
        await update.message.reply_text("PIN OK. Bot desbloqueado.")
    else:
        await update.message.reply_text("PIN incorrecto.")

async def prefs_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_owner(update):
        await _deny(update, "Acceso denegado (solo owner).")
        return

    state = load_state()
    await update.message.reply_text(f"Preferencias:\n{state.get('prefs')}")

async def weekly_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_owner(update):
        await _deny(update, "Acceso denegado (solo owner).")
        return

    state = load_state()
    if not _pin_ok(state):
        await update.message.reply_text("Falta PIN. Usa /pin ####")
        return

    uid = update.effective_user.id
    if not _rate_limit_ok(uid):
        await update.message.reply_text("Rate limit. Espera un minuto.")
        return

    prefs = state.get("prefs", {})
    await update.message.reply_text("Analizando mercado...")

    try:
        text = build_ai_brief(prefs, user_message="weekly brief")
        await update.message.reply_text(text)
    except Exception as e:
        await update.message.reply_text(f"Error: {type(e).__name__}: {e}")

# -------------------- CHAT LIBRE --------------------

async def chat_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_owner(update):
        await _deny(update, "Acceso denegado (solo owner).")
        return

    state = load_state()
    if not _pin_ok(state):
        await update.message.reply_text("Falta PIN. Usa /pin ####")
        return

    uid = update.effective_user.id
    if not _rate_limit_ok(uid):
        await update.message.reply_text("Rate limit. Espera un minuto.")
        return

    chat_id = int(update.effective_chat.id)
    set_chat_id(chat_id)

    user_text = (update.message.text or "").strip()
    if not user_text:
        return

    patch = _extraer_preferencias(user_text)
    prefs = state.get("prefs", {})

    if patch:
        state = update_prefs(patch)
        prefs = state.get("prefs", {})

    await update.message.reply_text("Analizando...")

    try:
        respuesta = build_ai_brief(prefs, user_message=user_text)
        await update.message.reply_text(respuesta)
    except Exception as e:
        await update.message.reply_text(f"Error: {type(e).__name__}: {e}")

# -------------------- ENVIO AUTOMATICO SEMANAL --------------------

async def enviar_weekly(application: Application):
    state = load_state()
    chat_id = state.get("chat_id")
    if not chat_id:
        return
    if not _pin_ok(state):
        return

    prefs = state.get("prefs", {})
    try:
        texto = build_ai_brief(prefs, user_message="weekly automatico")
        await application.bot.send_message(chat_id=chat_id, text=texto)
    except Exception as e:
        logging.error("weekly send failed: %s", e)

async def on_startup(app: Application):
    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        lambda: enviar_weekly(app),
        "cron",
        day_of_week=SCHEDULE_DOW,
        hour=SCHEDULE_HOUR,
        minute=SCHEDULE_MINUTE,
        id="weekly_brief",
        replace_existing=True,
    )
    scheduler.start()

def main():
    app = Application.builder().token(BOT_TOKEN).post_init(on_startup).build()

    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("pin", pin_cmd))
    app.add_handler(CommandHandler("prefs", prefs_cmd))
    app.add_handler(CommandHandler("weekly", weekly_cmd))
    app.add_handler(CommandHandler("whoami", whoami_cmd))

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, chat_handler))

    app.run_polling()

if __name__ == "__main__":
    main()