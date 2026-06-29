import os
import sqlite3
import threading
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler

from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, ContextTypes, filters
from apscheduler.schedulers.background import BackgroundScheduler

# ================= CONFIG =================
TOKEN = os.environ.get("TOKEN")
GROUP_ID = -5314646004   # ⚠️ PUT YOUR GROUP ID

print("DEBUG TOKEN:", TOKEN)

if not TOKEN:
    raise ValueError("❌ TOKEN missing!")

# ================= DUMMY SERVER (RENDER FIX) =================
class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot Running")

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

# ================= HELPERS =================
def get_today():
    return datetime.now().strftime("%Y-%m-%d")

def get_month():
    return datetime.now().strftime("%Y-%m")

def format_user(name, username):
    return f"@{username}" if username else name

def get_monthly_count(user_id):
    month = get_month()
    cursor.execute("""
    SELECT SUM(count) FROM logs
    WHERE user_id=? AND date LIKE ?
    """, (user_id, f"{month}%"))

    result = cursor.fetchone()[0]
    return result if result else 0

# ================= PHOTO HANDLER =================
async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    today = get_today()

    username = user.username
    name = user.first_name

    cursor.execute("SELECT count FROM logs WHERE user_id=? AND date=?",
                   (user.id, today))
    row = cursor.fetchone()

    if row:
        cursor.execute("UPDATE logs SET count=count+1 WHERE user_id=? AND date=?",
                       (user.id, today))
    else:
        cursor.execute("""
        INSERT INTO logs VALUES (?,?,?,?,?)
        """, (user.id, username, name, today, 1))

    conn.commit()

# ================= REMINDER (1 PM) =================
def reminder_job(app):
    async def send():
        today = get_today()

        cursor.execute("SELECT DISTINCT user_id, username, name FROM logs")
        users = cursor.fetchall()

        cursor.execute("SELECT user_id FROM logs WHERE date=?", (today,))
        submitted = {u[0] for u in cursor.fetchall()}

        reminder_list = []

        for user_id, username, name in users:
            if user_id not in submitted:
                reminder_list.append(format_user(name, username))

        if reminder_list:
            msg = "⏰ Reminder\n\nPlease send your selfie:\n\n"
            msg += "\n".join([f"• {u}" for u in reminder_list])

            await app.bot.send_message(chat_id=GROUP_ID, text=msg)

    app.create_task(send())

# ================= DAILY REPORT (10:30 PM) =================
def report_job(app):
    async def send():
        today = get_today()

        cursor.execute("SELECT DISTINCT user_id, username, name FROM logs")
        all_users = cursor.fetchall()

        cursor.execute("""
        SELECT user_id, username, name, count 
        FROM logs WHERE date=?
        """, (today,))
        today_data = cursor.fetchall()

        data_dict = {u[0]: u for u in today_data}

        report = f"📊 Daily Report ({today})\n\n"

        shared = "✅ Shared:\n"
        missed = "❌ Missed:\n"
        total = 0

        for user_id, username, name in all_users:
            display = format_user(name, username)

            if user_id in data_dict:
                count = data_dict[user_id][3]
                monthly = get_monthly_count(user_id)

                shared += f"• {display} — {count} today | {monthly} month\n"
                total += count
            else:
                missed += f"• {display}\n"

        report += shared + "\n" + missed
        report += f"\n📸 Total Images Today: {total}"

        await app.bot.send_message(chat_id=GROUP_ID, text=report)

    app.create_task(send())

# ================= MAIN =================
import asyncio

def main():
    # ✅ Start dummy server (Render fix)
    threading.Thread(target=run_server).start()

    # ✅ Create event loop manually (Python 3.14 fix)
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))

    print("✅ Bot started successfully")

    # ✅ Scheduler
    scheduler = BackgroundScheduler(timezone="UTC")

# IST → UTC
scheduler.add_job(lambda: reminder_job(app), trigger='cron', hour=7, minute=45)
scheduler.add_job(lambda: report_job(app), trigger='cron', hour=15, minute=0)

scheduler.start()

    # ✅ Run bot inside loop
    loop.run_until_complete(app.initialize())
    loop.run_until_complete(app.start())
    loop.run_until_complete(app.updater.start_polling())

    # ✅ Keep running
    loop.run_forever()


if __name__ == "__main__":
    main()
# ================= START =================
if __name__ == "__main__":
    main()
