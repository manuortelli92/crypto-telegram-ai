import os
import time
import logging
from collections import deque
from typing import Dict, Tuple, Optional, List

from telegram import Update
from telegram.ext import Application, MessageHandler, ContextTypes, filters
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from core.memory import load_state, set_chat_id, update_prefs
from core.market import get_ranked_market, fmt_pct
from core.news import get_news

logging.basicConfig(level=logging.INFO)

BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("Falta BOT_TOKEN en Railway")

OWNER_ID = os.getenv("OWNER_ID", "").strip()          # tu USER_ID
ROOT_PHRASE = os.getenv("ROOT_PHRASE", "").strip()    # opcional 2da capa
RATE_LIMIT_PER_MIN = int(os.getenv("RATE_LIMIT_PER_MIN", "12"))

# Hora de envío (para los informes automáticos)
SCHEDULE_HOUR = int(os.getenv("SCHEDULE_HOUR", "9"))
SCHEDULE_MINUTE = int(os.getenv("SCHEDULE_MINUTE", "0"))

_user_hits = {}

# Definición simple de "NO-ALTS" (majors). Ajustalo si querés.
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

def clamp_int(x: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, x))

def parse_report_mode(text: str) -> str:
    t = (text or "").lower()
    if "mensual" in t or "mes" in t:
        return "mensual"
    if "semanal" in t or "semana" in t:
        return "semanal"
    if "diario" in t or "hoy" in t:
        return "diario"
    return "semanal"

def parse_top_n(text: str, default_n: int = 8) -> int:
    t = (text or "").lower()
    if "top " in t:
        try:
            n = int(t.split("top ", 1)[1].split()[0])
            return clamp_int(n, 3, 20)
        except Exception:
            return default_n
    return default_n

def build_report(prefs: Dict, user_text: str) -> str:
    mode = parse_report_mode(user_text)
    top_n = parse_top_n(user_text, default_n=int(prefs.get("max_picks") or 8))

    # No tocamos prefs globales acá; solo ajustamos para este reporte
    tmp_prefs = dict(prefs)
    tmp_prefs["max_picks"] = top_n

    mkt = get_ranked_market(tmp_prefs)
    rows = mkt.get("rows", [])

    majors_rows = [r for r in rows if r["symbol"] in MAJORS]
    alts_rows = [r for r in rows if r["symbol"] not in MAJORS]

    # Armamos el mensaje
    lines: List[str] = []
    lines.append(f"INFORME {mode.upper()} (multi-source)")
    lines.append(f"UTC {mkt['generated_utc']} | timeframe {mkt['timeframe']} | tol {int(mkt['tol']*100)}%")
    lines.append("")

    def add_section(title: str, items: List[Dict], take: int):
        if not items:
            return
        lines.append(title)
        for i, r in enumerate(items[:take], 1):
            lines.append(
                f"{i}) {r['name']} ({r['symbol']}) | score {r['score']:.1f} | conf {r['confidence']} | risk {r['risk']} | src_ok {r['sources_ok']}"
            )
            lines.append(f"   mom: 7d {fmt_pct(r['mom_7d'])} | 30d {fmt_pct(r['mom_30d'])}")
            used = ", ".join(r["sources_used"]) if r.get("sources_used") else "n/a"
            lines.append(f"   fuentes: {used}")
        lines.append("")

    # Distribución: intentamos 3 majors + el resto alts, pero respeta top_n total.
    take_maj = min(3, top_n)
    take_alts = max(0, top_n - take_maj)

    add_section("NO-ALTS (Majors):", majors_rows, take_maj)
    add_section("ALTS:", alts_rows, take_alts)

    # Noticias (ligeras, para no alargar demasiado)
    news = get_news(max_total=6)
    if news:
        lines.append("Titulares (RSS):")
        for n in news[:5]:
            lines.append(f"- [{n.get('source')}] {n.get('title')}")
        lines.append("")

    # Cierre según modo
    if mode == "diario":
        lines.append("Nota: enfoque corto. Evita sobreoperar. Entrada escalonada si compras.")
    elif mode == "mensual":
        lines.append("Nota: enfoque largo. Prioriza calidad + DCA y gestion de riesgo.")
    else:
        lines.append("Nota: enfoque semanal. Defini monto, riesgo y entrada en 2-3 compras.")

    lines.append("Info only, no asesoramiento financiero.")
    return "\n".join(lines)

def root_help_text() -> str:
    base = (
        "ROOT (solo owner) por texto:\n"
        "- root activar diario | root desactivar diario\n"
        "- root activar semanal | root desactivar semanal\n"
        "- root activar mensual | root desactivar mensual\n"
        "- root ver prefs\n"
        "- root riesgo low|medium|high\n"
        "- root evita ADA\n"
        "- root prefiero BTC ETH\n"
        "- root top 10\n"
    )
    if ROOT_PHRASE:
        base += "\n(Como tenes ROOT_PHRASE, incluila en el mensaje root.)"
    return base

def parse_root_intent(text: str) -> str:
    t = (text or "").lower()
    if "root" not in t:
        return ""

    if "ayuda" in t or "help" in t:
        return "root_help"
    if "ver prefs" in t or "ver preferencias" in t:
        return "show_prefs"

    # Activar/desactivar schedulers
    if "activar diario" in t:
        return "daily_on"
    if "desactivar diario" in t:
        return "daily_off"
    if "activar semanal" in t:
        return "weekly_on"
    if "desactivar semanal" in t:
        return "weekly_off"
    if "activar mensual" in t:
        return "monthly_on"
    if "desactivar mensual" in t:
        return "monthly_off"

    return "root_other"

def extract_prefs_patch(text: str) -> Optional[Dict]:
    t = (text or "").lower()
    patch: Dict = {}

    if "riesgo low" in t or "riesgo bajo" in t or "menos riesgo" in t or "conservador" in t:
        patch["risk"] = "low"
    if "riesgo high" in t or "riesgo alto" in t or "mas riesgo" in t or "agresivo" in t:
        patch["risk"] = "high"
    if "riesgo medium" in t or "riesgo medio" in t:
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
        try:
            n = int(t.split("top ", 1)[1].split()[0])
            patch["max_picks"] = clamp_int(n, 3, 20)
        except Exception:
            pass

    return patch if patch else None

def set_flag(state: Dict, key: str, value: bool) -> None:
    state[key] = bool(value)
    from core.memory import save_state
    save_state(state)

async def send_scheduled(application: Application, mode: str):
    state = load_state()

    # Solo manda si el owner lo activó y hay chat registrado
    chat_id = state.get("chat_id")
    if not chat_id:
        return

    flag = {
        "diario": "daily_on",
        "semanal": "weekly_on",
        "mensual": "monthly_on"
    }.get(mode)

    if flag and not state.get(flag, False):
        return

    prefs = state.get("prefs", {})
    # Forzamos el modo en el texto para que arme ese informe
    text = build_report(prefs, f"informe {mode}")
    await application.bot.send_message(chat_id=chat_id, text=text)

async def on_startup(app: Application):
    scheduler = AsyncIOScheduler()

    # Diario: todos los días
    scheduler.add_job(
        lambda: send_scheduled(app, "diario"),
        "cron",
        hour=SCHEDULE_HOUR,
        minute=SCHEDULE_MINUTE,
        id="daily_report",
        replace_existing=True,
    )

    # Semanal: lunes
    scheduler.add_job(
        lambda: send_scheduled(app, "semanal"),
        "cron",
        day_of_week="mon",
        hour=SCHEDULE_HOUR,
        minute=SCHEDULE_MINUTE,
        id="weekly_report",
        replace_existing=True,
    )

    # Mensual: día 1
    scheduler.add_job(
        lambda: send_scheduled(app, "mensual"),
        "cron",
        day=1,
        hour=SCHEDULE_HOUR,
        minute=SCHEDULE_MINUTE,
        id="monthly_report",
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

    # Rate limit solo para usuarios normales (root sin limites)
    if not is_owner(update):
        if not rate_limit_ok(uid):
            await update.message.reply_text("Demasiadas solicitudes. Espera 1 minuto y proba de nuevo.")
            return

    # /start como texto normal
    if text == "/start" or text.lower() in ["start", "hola", "buenas", "hey"]:
        await update.message.reply_text(
            "Escribime normal y te paso un informe del mercado.\n"
            "Ej: 'informe diario top 8'\n"
            "Ej: 'informe semanal'\n"
            "Ej: 'informe mensual top 12'\n"
        )
        # Si sos owner, guardo chat para envíos programados (cuando actives)
        if is_owner(update):
            set_chat_id(int(chat.id))
        return

    # Root path (solo owner)
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

        if root_intent in ["daily_on", "daily_off", "weekly_on", "weekly_off", "monthly_on", "monthly_off"]:
            # registramos chat actual para los envíos
            set_chat_id(int(chat.id))

            if root_intent == "daily_on":
                set_flag(state, "daily_on", True)
                await update.message.reply_text("OK. Informe diario ACTIVADO (se manda a este chat).")
                return
            if root_intent == "daily_off":
                set_flag(state, "daily_on", False)
                await update.message.reply_text("OK. Informe diario DESACTIVADO.")
                return

            if root_intent == "weekly_on":
                set_flag(state, "weekly_on", True)
                await update.message.reply_text("OK. Informe semanal ACTIVADO (lunes).")
                return
            if root_intent == "weekly_off":
                set_flag(state, "weekly_on", False)
                await update.message.reply_text("OK. Informe semanal DESACTIVADO.")
                return

            if root_intent == "monthly_on":
                set_flag(state, "monthly_on", True)
                await update.message.reply_text("OK. Informe mensual ACTIVADO (día 1).")
                return
            if root_intent == "monthly_off":
                set_flag(state, "monthly_on", False)
                await update.message.reply_text("OK. Informe mensual DESACTIVADO.")
                return

        # Root: cambiar preferencias
        patch = extract_prefs_patch(text.replace("root", "", 1))
        if patch:
            update_prefs(patch)
            await update.message.reply_text(f"OK. Actualizado: {patch}")
        else:
            await update.message.reply_text("Root OK, pero no entendi. Deci 'root ayuda'.")
        return

    # Normal user path (libre): genera informe según lo pedido
    state = load_state()
    prefs = state.get("prefs", {})

    await update.message.reply_text("Analizando... (10-30s)")
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