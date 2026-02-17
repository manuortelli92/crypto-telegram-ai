import os
import time
import logging
from collections import deque
from typing import Dict

from telegram import Update
from telegram.ext import Application, MessageHandler, ContextTypes, filters
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from core.memory import load_state, set_chat_id, update_prefs
from core.market import get_ranked_market, fmt_pct

logging.basicConfig(level=logging.INFO)

BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("Falta BOT_TOKEN en Railway")

OWNER_ID = os.getenv("OWNER_ID", "").strip()
ROOT_PHRASE = os.getenv("ROOT_PHRASE", "").strip()
RATE_LIMIT_PER_MIN = int(os.getenv("RATE_LIMIT_PER_MIN", "12"))

SCHEDULE_HOUR = int(os.getenv("SCHEDULE_HOUR", "9"))
SCHEDULE_MINUTE = int(os.getenv("SCHEDULE_MINUTE", "0"))

_user_hits = {}

MAJORS = {"BTC", "ETH", "SOL", "BNB", "XRP"}

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
    if not is_owner(update):
        return False
    if not ROOT_PHRASE:
        return True
    return ROOT_PHRASE.lower() in (text or "").lower()

def parse_report_mode(text: str) -> str:
    t = (text or "").lower()
    if "mensual" in t:
        return "mensual"
    if "diario" in t:
        return "diario"
    return "semanal"

def build_report(prefs: Dict, user_text: str) -> str:
    mode = parse_report_mode(user_text)

    tmp_prefs = dict(prefs)
    tmp_prefs["max_picks"] = 20

    mkt = get_ranked_market(tmp_prefs)
    rows = mkt.get("rows", [])

    majors_rows = [r for r in rows if r["symbol"] in MAJORS]
    alts_rows = [r for r in rows if r["symbol"] not in MAJORS]

    lines = []
    lines.append(f"Panorama {mode.upper()}")

    def add_section(title, items):
        if not items:
            return
        lines.append("")
        lines.append(title)
        for i, r in enumerate(items, 1):
            lines.append(
                f"{i}) {r['symbol']} | score {r['score']:.1f} | riesgo {r['risk']} | 7d {fmt_pct(r['mom_7d'])}"
            )

    add_section("NO-ALTS:", majors_rows)
    add_section("ALTS:", alts_rows)

    return "\n".join(lines)

async def send_scheduled(application: Application):
    state = load_state()
    chat_id = state.get("chat_id")
    if not chat_id:
        return
    prefs = state.get("prefs", {})
    text = build_report(prefs, "semanal")
    await application.bot.send_message(chat_id=chat_id, text=text)

async def on_startup(app: Application):
    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        lambda: send_scheduled(app),
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

    if text == "/start" or text.lower() in ["start", "hola", "buenas", "hey"]:
        await update.message.reply_text(
            "Escribi: informe diario, informe semanal o informe mensual"
        )
        if is_owner(update):
            set_chat_id(int(chat.id))
        return

    state = load_state()
    prefs = state.get("prefs", {})

    await update.message.reply_text("Analizando...")
    try:
        reply = build_report(prefs, text)
        await update.message.reply_text(reply)
    except Exception as e:
        await update.message.reply_text(f"Error: {type(e).__name__}: {e}")

def main():
    app = Application.builder().token(BOT_TOKEN).post_init(on_startup).build()
    app.add_handler(MessageHandler(filters.TEXT, chat_handler))
    app.run_polling()

if __name__ == "__main__":
    main()