import os
import time
import logging
import asyncio
from collections import deque

from telegram import Update
from telegram.ext import Application, MessageHandler, ContextTypes, filters
from telegram.error import Conflict

# Importaciones de tu estructura core
from core.memory import load_state, save_state, set_chat_id
from core.brain import add_turn, apply_patch_to_session
from core.engine import build_engine_analysis

# Configuración de Logs
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Variables de Entorno
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
OWNER_ID = os.getenv("OWNER_ID", "").strip()
RATE_LIMIT_PER_MIN = int(os.getenv("RATE_LIMIT_PER_MIN", "12"))

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

async def chat_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat = update.effective_chat
    if not user or not chat or not update.message:
        return

    uid = user.id
    text = (update.message.text or "").strip()

    # 1. Control de flujo y Rate Limit
    if not is_owner(update) and not rate_limit_ok(uid):
        await update.message.reply_text("⏳ Pará un poco, che. Muchas consultas seguidas. Esperá un minuto.")
        return

    # 2. Cargar estado y Procesar Memoria (Brain)
    state = load_state()
    
    # Registramos lo que dijo el usuario en su "cerebro"
    add_turn(state, chat.id, role="user", text=text)
    
    # Aplicamos parches (si dijo "prefiero BTC" o "riesgo bajo", se guarda acá)
    brain_prefs = apply_patch_to_session(state, chat.id, text)

    # 3. Comandos básicos / Start
    low = text.lower()
    if text == "/start" or low in {"start", "hola", "buenas"}:
        reply = (
            "🤖 **¡Buenas! Soy tu analista cripto.**\n\n"
            "Podés pedirme cosas como:\n"
            "• '¿Cómo ves BTC?'\n"
            "• 'Pasame el top 20 mensual'\n"
            "• 'Prefiero ETH y SOL' (lo voy a recordar)\n"
            "• 'Cambiá a riesgo bajo'"
        )
        await update.message.reply_text(reply)
        if is_owner(update):
            set_chat_id(int(chat.id))
        add_turn(state, chat.id, role="bot", text=reply)
        save_state(state)
        return

    if is_owner(update):
        set_chat_id(int(chat.id))

    # 4. Ejecución del Análisis
    msg_espera = await update.message.reply_text("🔍 Analizando datos del mercado...")
    
    try:
        # Le pasamos el texto y las preferencias que el "brain" procesó
        # Nota: Si tu engine.py acepta brain_prefs, usalo así. 
        # Si no, build_engine_analysis(text) sigue funcionando.
        reply = build_engine_analysis(text)
        
        await update.message.reply_text(reply)
        
        # Guardamos la respuesta del bot en la memoria
        add_turn(state, chat.id, role="bot", text=reply)
        
    except Exception as e:
        logger.exception(f"Error en engine: {e}")
        await update.message.reply_text("❌ Hubo un error analizando el mercado. Reintentá en un toque.")
    finally:
        save_state(state) # Guardamos todo el progreso (memoria + chat_id)
        try:
            await context.bot.delete_message(chat_id=chat.id, message_id=msg_espera.message_id)
        except:
            pass

def main():
    if not BOT_TOKEN:
        logger.error("Falta BOT_TOKEN en las variables de entorno.")
        return

    app = Application.builder().token(BOT_TOKEN).build()
    
    # Handler para mensajes de texto (excluyendo comandos de sistema)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, chat_handler))
    
    logger.info("Bot iniciado y listo para recibir mensajes...")
    
    # Railway: drop_pending_updates evita colapsos por mensajes viejos
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
