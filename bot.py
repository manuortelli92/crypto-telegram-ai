import os
import logging

from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from core.memory import load_state, set_chat_id, update_prefs
from core.engine import build_ai_brief

logging.basicConfig(level=logging.INFO)

BOT_TOKEN = os.getenv("BOT_TOKEN")

if not BOT_TOKEN:
    raise RuntimeError("Falta BOT_TOKEN en Railway")

SCHEDULE_DOW = os.getenv("SCHEDULE_DOW", "mon")
SCHEDULE_HOUR = int(os.getenv("SCHEDULE_HOUR", "9"))
SCHEDULE_MINUTE = int(os.getenv("SCHEDULE_MINUTE", "0"))

# -------------------- COMANDOS --------------------

async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = int(update.effective_chat.id)
    set_chat_id(chat_id)

    await update.message.reply_text(
        "Listo. Ya registre tu chat.\n\n"
        "Podes hablarme normal y te respondo con analisis crypto.\n"
        "Ejemplos:\n"
        "- Esta semana tengo 500 AUD que ves mejor?\n"
        "- Evita ADA prefiero BTC ETH\n"
        "- Quiero menos riesgo\n"
    )

async def prefs_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    state = load_state()
    await update.message.reply_text(f"Preferencias actuales:\n{state.get('prefs')}")

async def weekly_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    state = load_state()
    prefs = state.get("prefs", {})

    await update.message.reply_text("Analizando mercado...")

    text = build_ai_brief(prefs, user_message="weekly brief")
    await update.message.reply_text(text)

async def setrisk_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Uso: /setrisk low|medium|high")
        return

    risk = context.args[0].lower()

    if risk not in ["low", "medium", "high"]:
        await update.message.reply_text("Valor invalido.")
        return

    update_prefs({"risk": risk})

    await update.message.reply_text(f"Risk actualizado a {risk}")

# -------------------- INTERPRETACION TEXTO --------------------

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

# -------------------- CHAT LIBRE --------------------

async def chat_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):

    chat_id = int(update.effective_chat.id)
    set_chat_id(chat_id)

    user_text = (update.message.text or "").strip()

    if not user_text:
        return

    patch = _extraer_preferencias(user_text)

    state = load_state()
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

# -------------------- ENVIO AUTOMATICO --------------------

async def enviar_weekly(application: Application):
    state = load_state()
    chat_id = state.get("chat_id")

    if not chat_id:
        return

    prefs = state.get("prefs", {})

    texto = build_ai_brief(prefs, user_message="weekly automatico")

    await application.bot.send_message(chat_id=chat_id, text=texto)

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

# -------------------- MAIN --------------------

def main():
    app = Application.builder().token(BOT_TOKEN).post_init(on_startup).build()

    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("prefs", prefs_cmd))
    app.add_handler(CommandHandler("weekly", weekly_cmd))
    app.add_handler(CommandHandler("setrisk", setrisk_cmd))

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, chat_handler))

    app.run_polling()

if __name__ == "__main__":
    main()