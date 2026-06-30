import os
import sqlite3
import threading
import asyncio
from datetime import datetime, UTC
from http.server import HTTPServer, BaseHTTPRequestHandler

from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, ContextTypes, filters
from apscheduler.schedulers.background import BackgroundScheduler

TOKEN = 8438035827:AAGfxMLEEHZ42kDGRnGI-Tp4UTNZLJWtNec
GROUP_ID = -5314646004  # Replace this

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

def format_user(name, username):
    return f"@{username}" if username else name

# ================= PHOTO =================
async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    today = get_today()

    cursor.execute("SELECT count FROM logs WHERE user_id=? AND date=?", (user.id, today))
    row = cursor.fetchone()

    if row:
        cursor.execute("UPDATE logs SET count=count+1 WHERE user_id=? AND date=?", (user.id, today))
    else:
        cursor.execute(
            "INSERT INTO logs VALUES (?, ?, ?, ?, ?)",
            (user.id, user.username, user.first_name, today, 1)
        )

    conn.commit()

# ================= REMINDER =================
async def send_reminder(app):
    print("🔥 REMINDER TRIGGERED")

    today = get_today()

    cursor.execute("SELECT DISTINCT user_id, username, name FROM logs")
    users = cursor.fetchall()

    cursor.execute("SELECT user_id FROM logs WHERE date=?", (today,))
    submitted = {u[0] for u in cursor.fetchall()}

    missing = []

    for user_id, username, name in users:
        if user_id not in submitted:
            missing.append(format_user(name, username))

    if missing:
        msg = "⏰ Reminder\n\nSend your selfie:\n\n"
        msg += "\n".join(f"• {u}" for u in missing)

        await app.bot.send_message(chat_id=GROUP_ID, text=msg)

# ================= REPORT =================
async def send_report(app):
    print("🔥 REPORT TRIGGERED")

    today = get_today()

    cursor.execute("SELECT user_id, username, name, count FROM logs WHERE date=?", (today,))
    data = cursor.fetchall()

    if not data:
        await app.bot.send_message(
            chat_id=GROUP_ID,
            text="📊 No images shared today."
        )
        return

    report = "📊 Daily Report\n\n"
    total = 0

    for user_id, username, name, count in data:
        name_display = f"@{username}" if username else name
        report += f"• {name_display} — {count}\n"
        total += count

    report += f"\n📸 Total Images: {total}"

    await app.bot.send_message(chat_id=GROUP_ID, text=report)

# ================= MAIN =================
def main():
    # Start server
    threading.Thread(target=run_server, daemon=True).start()

    # Event loop
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    # Bot setup
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))

    print("✅ Bot running")

    # Scheduler
    scheduler = BackgroundScheduler(timezone="UTC")

    def run_async(func):
        asyncio.run_coroutine_threadsafe(func(app), loop)

    # ✅ Reminder test
    scheduler.add_job(run_async, args=[send_reminder], trigger='interval', minutes=1)

    # ✅ Report test (IMPORTANT)
    scheduler.add_job(run_async, args=[send_report], trigger='interval', minutes=2)

    scheduler.start()

    # ✅ Start bot (correct order)
    loop.run_until_complete(app.initialize())
    loop.run_until_complete(app.bot.delete_webhook(drop_pending_updates=True))
    loop.run_until_complete(app.start())
    loop.run_until_complete(app.updater.start_polling())

    loop.run_forever()
# ================= START =================
if __name__ == "__main__":
    main()
