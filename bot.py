import os
import time
import logging
from collections import deque

from telegram import Update
from telegram.ext import Application, MessageHandler, ContextTypes, filters
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from core.memory import load_state, set_chat_id, update_prefs
from core.engine import build_ai_brief

logging.basicConfig(level=logging.INFO)

BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("Falta BOT_TOKEN en Railway")

OWNER_ID = os.getenv("OWNER_ID", "").strip()  # tu USER_ID
ROOT_PHRASE = os.getenv("ROOT_PHRASE", "").strip()  # opcional, 2da capa tipo "mate amargo 7"
RATE_LIMIT_PER_MIN = int(os.getenv("RATE_LIMIT_PER_MIN", "12"))

SCHEDULE_DOW = os.getenv("SCHEDULE_DOW", "mon")
SCHEDULE_HOUR = int(os.getenv("SCHEDULE_HOUR", "9"))
SCHEDULE_MINUTE = int(os.getenv("SCHEDULE_MINUTE", "0"))

_user_hits = {}

def is_owner(update: Update) -> bool:
    if not OWNER_ID:
        return False
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

def root_ok(update: Update, text: str) -> bool:
    # Root solo para owner. Si además seteás ROOT_PHRASE, pide esa frase.
    if not is_owner(update):
        return False
    if not ROOT_PHRASE:
        return True
    return ROOT_PHRASE.lower() in (text or "").lower()

def extract_prefs_patch(text: str):
    t = (text or "").lower()
    patch = {}

    if "menos riesgo" in t or "conservador" in t:
        patch["risk"] = "low"
    if "mas riesgo" in t or "agresivo" in t:
        patch["risk"] = "high"
    if "riesgo medio" in t:
        patch["risk"] = "medium"

    if "evita " in t:
        part = t.split("evita ", 1)[1]
        coins = part.replace(",", " ").upper().split()
        patch["avoid"] = list({c for c in coins if len(c) <= 6})

    if "prefiero " in t:
        part = t.split("prefiero ", 1)[1]
        coins = part.replace(",", " ").upper().split()
        patch["focus"] = list({c for c in coins if len(c) <= 6})

    if "top " in t:
        # ejemplo: "top 5"
        try:
            n = int(t.split("top ", 1)[1].split()[0])
            patch["max_picks"] = max(1, min(10, n))
        except Exception:
            pass

    return patch if patch else None

async def send_weekly(application: Application):
    state = load_state()
    chat_id = state.get("chat_id")
    if not chat_id:
        return
    prefs = state.get("prefs", {})
    try:
        text = build_ai_brief(prefs, user_message="weekly automatico")
        await application.bot.send_message(chat_id=chat_id, text=text)
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
        id="weekly_brief",
        replace_existing=True,
    )
    scheduler.start()

def root_help_text() -> str:
    return (
        "ROOT (solo owner)\n"
        "- Decí: 'root activar semanal'\n"
        "- Decí: 'root desactivar semanal'\n"
        "- Decí: 'root ver prefs'\n"
        "- Decí: 'root riesgo low|medium|high'\n"
        "- Decí: 'root evita ADA' / 'root prefiero BTC ETH'\n"
        "Si seteaste ROOT_PHRASE, incluí esa frase en el mensaje."
    )

def parse_root_intent(text: str) -> str:
    t = (text or "").lower()
    if "root" not in t:
        return ""
    if "activar semanal" in t:
        return "weekly_on"
    if "desactivar semanal" in t:
        return "weekly_off"
    if "ver prefs" in t or "ver preferencias" in t:
        return "show_prefs"
    if "ayuda" in t or "help" in t:
        return "root_help"
    return "root_other"

async def chat_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat = update.effective_chat
    if not user or not chat or not update.message:
        return

    uid = user.id
    if not rate_limit_ok(uid):
        await update.message.reply_text("Rate limit: esperá un minuto y probá de nuevo.")
        return

    text = (update.message.text or "").strip()

    # Respuesta “start” como texto normal (no comando)
    if text == "/start" or text.lower() in ["start", "hola", "buenas", "hey"]:
        await update.message.reply_text(
            "Escribime normal y te paso un brief del mercado.\n"
            "Ej: 'que ves esta semana con riesgo medio?'"
        )
        # Si sos owner, guardamos chat_id para el semanal (root)
        if is_owner(update):
            set_chat_id(int(chat.id))
        return

    # ROOT: solo owner (y opcional frase secreta)
    root_intent = parse_root_intent(text)
    if root_intent:
        if not root_ok(update, text):
            await update.message.reply_text("Root denegado.")
            return

        state = load_state()

        if root_intent == "root_help":
            await update.message.reply_text(root_help_text())
            return

        if root_intent == "show_prefs":
            await update.message.reply_text(f"Prefs:\n{state.get('prefs')}")
            return

        if root_intent in ["weekly_on", "weekly_off"]:
            # Guardamos chat_id cuando activás semanal
            if root_intent == "weekly_on":
                set_chat_id(int(chat.id))
                await update.message.reply_text("OK. Weekly activado (se manda al chat actual).")
            else:
                # desactivar = borrar chat_id
                state["chat_id"] = None
                from core.memory import save_state
                save_state(state)
                await update.message.reply_text("OK. Weekly desactivado.")
            return

        # Root: actualizar preferencias por texto
        patch = extract_prefs_patch(text.replace("root", "", 1))
        if patch:
            update_prefs(patch)
            await update.message.reply_text(f"OK. Actualizado: {patch}")
        else:
            await update.message.reply_text("Root OK, pero no entendí qué cambiar. Decí 'root ayuda'.")
        return

    # Usuario normal (cualquiera): brief sin tocar prefs globales
    # (Si querés que también use prefs globales, lo cambiamos.)
    state = load_state()
    prefs = state.get("prefs", {})

    await update.message.reply_text("Analizando... (10-30s)")
    try:
        reply = build_ai_brief(prefs, user_message=text)
        await update.message.reply_text(reply)
    except Exception as e:
        await update.message.reply_text(f"Error: {type(e).__name__}: {e}")

def main():
    app = Application.builder().token(BOT_TOKEN).post_init(on_startup).build()
    # Captura todo texto (incluye /start como texto si el user lo manda)
    app.add_handler(MessageHandler(filters.TEXT, chat_handler))
    app.run_polling()

if __name__ == "__main__":
    main()