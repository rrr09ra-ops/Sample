import os
import sqlite3
import threading
import asyncio
from datetime import datetime, UTC
from http.server import HTTPServer, BaseHTTPRequestHandler

from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    MessageHandler,
    ContextTypes,
    filters
)

from apscheduler.schedulers.background import BackgroundScheduler

# ✅ PUT YOUR TOKEN HERE (WITH QUOTES)
TOKEN = "8438035827:AAGfxMLEEHZ42kDGRnGI-Tp4UTNZLJWtNec"

# ❌ TEMP — this will be replaced after getting correct ID
GROUP_ID = 0

print("✅ Bot starting...")

# ================= SERVER =================
class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot running")

def run_server():
    server = HTTPServer(("0.0.0.0", 10000), Handler)
    server.serve_forever()

# ================= DATABASE =================
conn = sqlite3.connect("bot.db", check_same_thread=False)
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS logs (
    user_id INTEGER,
    username TEXT,
    name TEXT,
    date TEXT,
    count INTEGER
)
""")
conn.commit()

def get_today():
    return datetime.now(UTC).strftime("%Y-%m-%d")

# ================= PHOTO HANDLER =================
async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    today = get_today()

    print("✅ PHOTO RECEIVED FROM:", user.id)

# ================= GET CHAT ID =================
async def get_chat_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print("✅ CHAT ID:", update.effective_chat.id)

# ================= REMINDER =================
async def send_reminder(app):
    print("🔥 REMINDER TRIGGERED")

    if GROUP_ID != 0:
        await app.bot.send_message(
            chat_id=GROUP_ID,
            text="⏰ Reminder: Please send your photo!"
        )

# ================= REPORT =================
async def send_report(app):
    print("🔥 REPORT TRIGGERED")

    if GROUP_ID != 0:
        await app.bot.send_message(
            chat_id=GROUP_ID,
            text="📊 Report test working!"
        )

# ================= MAIN =================
def main():
    threading.Thread(target=run_server, daemon=True).start()

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    app = ApplicationBuilder().token(TOKEN).build()

    # ✅ HANDLERS
    app.add_handler(MessageHandler(filters.ALL, get_chat_id))  # get chat id
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))

    print("✅ Bot running")

    scheduler = BackgroundScheduler(timezone="UTC")

    def run_async(func):
        asyncio.run_coroutine_threadsafe(func(app), loop)

    # ✅ TEST SCHEDULE
    scheduler.add_job(run_async, args=[send_reminder], trigger='interval', minutes=1)
    scheduler.add_job(run_async, args=[send_report], trigger='interval', minutes=2)

    scheduler.start()

    loop.run_until_complete(app.initialize())
    loop.run_until_complete(app.bot.delete_webhook(drop_pending_updates=True))
    loop.run_until_complete(app.start())
    loop.run_until_complete(app.updater.start_polling())

    print("✅ Send any message in group to get CHAT ID")

    loop.run_forever()

# ================= START =================
if __name__ == "__main__":
    main()
``
