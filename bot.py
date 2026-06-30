import sqlite3
import threading
import asyncio
from datetime import datetime, timedelta, UTC
from http.server import HTTPServer, BaseHTTPRequestHandler

from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    MessageHandler,
    CommandHandler,
    ContextTypes,
    filters
)

from apscheduler.schedulers.background import BackgroundScheduler

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt


TOKEN = "8438035827:AAGfxMLEEHZ42kDGRnGI-Tp4UTNZLJWtNec"
GROUP_ID = -1004432548929


# ================= SERVER =================
class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot running")

def run_server():
    HTTPServer(("0.0.0.0", 10000), Handler).serve_forever()


# ================= DATABASE =================
conn = sqlite3.connect("bot.db", check_same_thread=False)
cursor = conn.cursor()

cursor.execute("CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, username TEXT, name TEXT)")
cursor.execute("CREATE TABLE IF NOT EXISTS logs (user_id INTEGER, date TEXT, count INTEGER)")
cursor.execute("CREATE TABLE IF NOT EXISTS streaks (user_id INTEGER, date TEXT)")
conn.commit()


def get_today():
    return datetime.now(UTC).strftime("%Y-%m-%d")


# ================= USER =================
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    cursor.execute("INSERT OR IGNORE INTO users VALUES (?, ?, ?)",
                   (user.id, user.username, user.first_name))
    conn.commit()


# ================= PHOTO =================
async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    today = get_today()

    await handle_message(update, context)

    cursor.execute("SELECT count FROM logs WHERE user_id=? AND date=?", (user.id, today))
    row = cursor.fetchone()

    if row:
        cursor.execute("UPDATE logs SET count=count+1 WHERE user_id=? AND date=?", (user.id, today))
    else:
        cursor.execute("INSERT INTO logs VALUES (?, ?, ?)", (user.id, today, 1))

    cursor.execute("SELECT 1 FROM streaks WHERE user_id=? AND date=?", (user.id, today))
    if not cursor.fetchone():
        cursor.execute("INSERT INTO streaks VALUES (?, ?)", (user.id, today))

    conn.commit()


# ================= REPORT =================
async def send_report(app):
    today = get_today()

    cursor.execute("SELECT * FROM users")
    users = cursor.fetchall()

    cursor.execute("SELECT user_id, count FROM logs WHERE date=?", (today,))
    data = dict(cursor.fetchall())

    text = f"📊 REPORT ({today})\n\n"
    total = 0

    for uid, username, name in users:
        count = data.get(uid, 0)
        display = f"@{username}" if username else name
        text += f"{display} — {count}\n"
        total += count

    text += f"\n📸 Total: {total}"

    await app.bot.send_message(GROUP_ID, text)


# ================= COMMAND =================
async def report_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send_report(context.application)


# ================= MAIN =================
def main():
    threading.Thread(target=run_server, daemon=True).start()

    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(MessageHandler(filters.ALL, handle_message))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(CommandHandler("report", report_cmd))

    scheduler = BackgroundScheduler(timezone="UTC")

    def scheduled_job():
        asyncio.run(send_report(app))

    scheduler.add_job(scheduled_job, trigger='cron', hour=15, minute=0)
    scheduler.start()

    print("✅ BOT RUNNING ✅")

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    async def polling_loop():
        await app.initialize()
        await app.bot.delete_webhook(drop_pending_updates=True)

        offset = None

        while True:
            updates = await app.bot.get_updates(offset=offset, timeout=10)

            for update in updates:
                offset = update.update_id + 1
                await app.process_update(update)

    loop.run_until_complete(polling_loop())


if __name__ == "__main__":
    main()
