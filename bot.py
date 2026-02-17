import os
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

logging.basicConfig(level=logging.INFO)

BOT_TOKEN = os.getenv("BOT_TOKEN")

if not BOT_TOKEN:
    raise RuntimeError("Falta BOT_TOKEN en Railway")

# -------------------- START DEBUG --------------------

async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    username = update.effective_user.username

    await update.message.reply_text(
        f"DEBUG INFO:\n\n"
        f"USER_ID: {user_id}\n"
        f"CHAT_ID: {chat_id}\n"
        f"USERNAME: @{username}"
    )

# -------------------- MAIN --------------------

def main():

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start_cmd))

    app.run_polling()

if __name__ == "__main__":
    main()