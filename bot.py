import sqlite3
import threading
import hashlib
from datetime import datetime, timedelta
from http.server import HTTPServer, BaseHTTPRequestHandler

from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, CommandHandler, ContextTypes, filters
from apscheduler.schedulers.background import BackgroundScheduler

# ================= CONFIG =================
TOKEN = "8438035827:AAGfxMLEEHZ42kDGRnGI-Tp4UTNZLJWtNec"
GROUP_ID = -1004432548929   # your group id

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

cursor.execute("CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, username TEXT, name TEXT)")
cursor.execute("CREATE TABLE IF NOT EXISTS logs (user_id INTEGER, date TEXT, count INTEGER)")
cursor.execute("CREATE TABLE IF NOT EXISTS images (hash TEXT)")
conn.commit()

def today():
    return datetime.now().strftime("%Y-%m-%d")

def month():
    return datetime.now().strftime("%Y-%m")

# ================= USER =================
async def register(update):
    user = update.effective_user
    cursor.execute("INSERT OR IGNORE INTO users VALUES (?, ?, ?)",
                   (user.id, user.username, user.first_name))
    conn.commit()

# ================= DUPLICATE CHECK =================
def get_hash(file_bytes):
    return hashlib.md5(file_bytes).hexdigest()

# ================= PHOTO =================
async def photo_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await register(update)
    user = update.effective_user

    file = await update.message.photo[-1].get_file()
    data = await file.download_as_bytearray()

    img_hash = get_hash(data)

    cursor.execute("SELECT 1 FROM images WHERE hash=?", (img_hash,))
    if cursor.fetchone():
        await update.message.reply_text("⚠️ Duplicate image detected")
        return

    cursor.execute("INSERT INTO images VALUES (?)", (img_hash,))

    t = today()

    cursor.execute("SELECT count FROM logs WHERE user_id=? AND date=?", (user.id, t))
    row = cursor.fetchone()

    if row:
        cursor.execute("UPDATE logs SET count=count+1 WHERE user_id=? AND date=?", (user.id, t))
    else:
        cursor.execute("INSERT INTO logs VALUES (?, ?, ?)", (user.id, t, 1))

    conn.commit()

# ================= REPORT =================
def generate_report():
    t = today()
    m = month()

    cursor.execute("SELECT * FROM users")
    users = cursor.fetchall()

    cursor.execute("SELECT user_id, count FROM logs WHERE date=?", (t,))
    today_data = dict(cursor.fetchall())

    report = f"📊 Daily Report ({t})\n\n"
    total = 0

    low_users = []

    for uid, username, name in users:
        daily = today_data.get(uid, 0)

        cursor.execute("SELECT SUM(count) FROM logs WHERE user_id=? AND date LIKE ?", (uid, f"{m}%"))
        monthly = cursor.fetchone()[0] or 0

        tag = f"@{username}" if username else name

        report += f"{tag} — Today: {daily} | Month: {monthly}\n"

        total += daily

        if daily < 3:
            low_users.append(tag)

    report += f"\n📸 Total Today: {total}\n"

    if low_users:
        report += "\n⚠️ Low Performers:\n" + "\n".join(low_users)

    return report

# ================= REMINDER =================
async def reminder(app):
    t = today()

    cursor.execute("SELECT * FROM users")
    users = cursor.fetchall()

    cursor.execute("SELECT user_id, count FROM logs WHERE date=?", (t,))
    data = dict(cursor.fetchall())

    msg = []

    for uid, username, name in users:
        if data.get(uid, 0) == 0:
            tag = f"@{username}" if username else name
            msg.append(tag)

    if msg:
        await app.bot.send_message(GROUP_ID, "⚠️ No images uploaded:\n" + "\n".join(msg))

# ================= WEEKLY =================
async def weekly_report(app):
    cursor.execute("SELECT user_id, SUM(count) FROM logs GROUP BY user_id ORDER BY SUM(count) DESC")
    data = cursor.fetchall()

    text = "🏆 Weekly Leaderboard\n\n"

    medals = ["🥇", "🥈", "🥉"]

    for i, (uid, total) in enumerate(data[:10]):
        cursor.execute("SELECT username, name FROM users WHERE id=?", (uid,))
        u = cursor.fetchone()
        tag = f"@{u[0]}" if u[0] else u[1]

        emoji = medals[i] if i < 3 else "⭐"
        text += f"{emoji} {tag} — {total}\n"

    await app.bot.send_message(GROUP_ID, text)

# ================= COMMAND =================
async def report_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(generate_report())

# ================= MAIN =================
def main():
    threading.Thread(target=run_server, daemon=True).start()

    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(MessageHandler(filters.PHOTO, photo_handler))
    app.add_handler(CommandHandler("report", report_cmd))

    scheduler = BackgroundScheduler(timezone="Asia/Kolkata")

    # ✅ reminders
    scheduler.add_job(lambda: app.bot.send_message(GROUP_ID, "⏰ 2 PM Reminder"), 'cron', hour=14)
    scheduler.add_job(lambda: app.bot.send_message(GROUP_ID, "⏰ 4 PM Reminder"), 'cron', hour=16)

    # ✅ actual reminders tagging
    scheduler.add_job(lambda: context_runner(app, reminder), 'cron', hour=14)
    scheduler.add_job(lambda: context_runner(app, reminder), 'cron', hour=16)

    # ✅ daily report 8 PM
    scheduler.add_job(lambda: context_runner(app, send_report), 'cron', hour=20)

    # ✅ weekly Saturday 5 PM
    scheduler.add_job(lambda: context_runner(app, weekly_report), 'cron', day_of_week='sat', hour=17)

    scheduler.start()

    print("✅ BOT RUNNING ✅")

    app.run_polling(stop_signals=None)

# helper to run async in scheduler
def context_runner(app, func):
    import asyncio
    asyncio.run(func(app))

# wrapper
async def send_report(app):
    await app.bot.send_message(GROUP_ID, generate_report())


if __name__ == "__main__":
    main()
