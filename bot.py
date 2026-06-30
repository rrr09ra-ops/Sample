import sqlite3
import threading
import asyncio
import hashlib
from datetime import datetime, timedelta
from http.server import HTTPServer, BaseHTTPRequestHandler

from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, CommandHandler, ContextTypes, filters
from apscheduler.schedulers.background import BackgroundScheduler

# ========= CONFIG =========
TOKEN = "8438035827:AAGfxMLEEHZ42kDGRnGI-Tp4UTNZLJWtNec"
GROUP_ID = -1004432548929

# ========= SERVER =========
class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot running")

def run_server():
    HTTPServer(("0.0.0.0", 10000), Handler).serve_forever()

# ========= DATABASE =========
conn = sqlite3.connect("bot.db", check_same_thread=False)
cursor = conn.cursor()

cursor.execute("CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, username TEXT, name TEXT)")
cursor.execute("CREATE TABLE IF NOT EXISTS logs (user_id INTEGER, date TEXT, count INTEGER)")
cursor.execute("CREATE TABLE IF NOT EXISTS images (hash TEXT)")
cursor.execute("CREATE TABLE IF NOT EXISTS streaks (user_id INTEGER, date TEXT)")
conn.commit()

def today():
    return datetime.now().strftime("%Y-%m-%d")

def month():
    return datetime.now().strftime("%Y-%m")

# ========= REGISTER =========
async def register(update):
    u = update.effective_user
    cursor.execute("INSERT OR IGNORE INTO users VALUES (?, ?, ?)", (u.id, u.username, u.first_name))
    conn.commit()

# ========= HASH =========
def get_hash(data):
    return hashlib.md5(data).hexdigest()

# ========= PHOTO =========
async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await register(update)
    user = update.effective_user
    t = today()

    file = await update.message.photo[-1].get_file()
    data = await file.download_as_bytearray()
    h = get_hash(data)

    cursor.execute("SELECT 1 FROM images WHERE hash=?", (h,))
    if cursor.fetchone():
        await update.message.reply_text("⚠️ Duplicate image")
        return

    cursor.execute("INSERT INTO images VALUES (?)", (h,))

    cursor.execute("SELECT count FROM logs WHERE user_id=? AND date=?", (user.id, t))
    if cursor.fetchone():
        cursor.execute("UPDATE logs SET count=count+1 WHERE user_id=? AND date=?", (user.id, t))
    else:
        cursor.execute("INSERT INTO logs VALUES (?, ?, ?)", (user.id, t, 1))

    # ✅ streak entry
    cursor.execute("INSERT INTO streaks VALUES (?, ?)", (user.id, t))

    conn.commit()

# ========= STREAK =========
def get_streak(uid):
    cursor.execute("SELECT date FROM streaks WHERE user_id=?", (uid,))
    dates = set(d[0] for d in cursor.fetchall())

    streak = 0
    for i in range(30):
        d = (datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d")
        if d in dates:
            streak += 1
        else:
            break
    return streak

# ========= MISSED DAYS =========
def get_missed_days(uid):
    today_date = datetime.now()
    start = today_date.replace(day=1)

    missed = []

    for i in range((today_date - start).days + 1):
        d = (start + timedelta(days=i)).strftime("%Y-%m-%d")

        cursor.execute("SELECT count FROM logs WHERE user_id=? AND date=?", (uid, d))
        if not cursor.fetchone():
            missed.append(d[-2:])  # show day only

    return missed

# ========= DAILY REPORT =========
def build_report():
    t = today()
    m = month()

    cursor.execute("SELECT * FROM users")
    users = cursor.fetchall()

    cursor.execute("SELECT user_id, count FROM logs WHERE date=?", (t,))
    today_data = dict(cursor.fetchall())

    text = f"📊 REPORT ({t})\n\n"

    low = []

    for uid, username, name in users:
        d = today_data.get(uid, 0)

        cursor.execute("SELECT SUM(count) FROM logs WHERE user_id=? AND date LIKE ?", (uid, f"{m}%"))
        monthly = cursor.fetchone()[0] or 0

        tag = f"@{username}" if username else name

        text += f"{tag} — Today: {d} | Month: {monthly}\n"

        if d < 3:
            low.append(tag)

    if low:
        text += "\n⚠️ Low performers:\n" + "\n".join(low)

    return text

# ========= WEEKLY LEADERBOARD =========
async def weekly_leaderboard(app):
    cursor.execute("SELECT user_id, SUM(count) FROM logs GROUP BY user_id ORDER BY SUM(count) DESC")
    data = cursor.fetchall()

    text = "🏆 Weekly Leaderboard\n\n"
    medals = ["🥇", "🥈", "🥉"]

    for i, (uid, total) in enumerate(data[:10]):
        cursor.execute("SELECT username, name FROM users WHERE id=?", (uid,))
        u = cursor.fetchone()
        tag = f"@{u[0]}" if u[0] else u[1]

        icon = medals[i] if i < 3 else "⭐"
        text += f"{icon} {tag} — {total}\n"

    await app.bot.send_message(GROUP_ID, text)

# ========= STREAK REPORT =========
async def weekly_streak(app):
    cursor.execute("SELECT * FROM users")
    users = cursor.fetchall()

    text = "🔥 Streak Report\n\n"

    for uid, username, name in users:
        tag = f"@{username}" if username else name
        streak = get_streak(uid)
        missed = get_missed_days(uid)

        text += f"{tag} — 🔥 {streak} days | Missed: {','.join(missed[:5])}\n"

    await app.bot.send_message(GROUP_ID, text)

# ========= COMMAND =========
async def report_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(build_report())

# ========= REMINDER =========
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
        await app.bot.send_message(GROUP_ID, "⚠️ No images:\n" + "\n".join(msg))

# ========= ASYNC HELPER =========
def run_async(app, func):
    import asyncio
    asyncio.run(func(app))

# ========= MAIN =========
def main():
    threading.Thread(target=run_server, daemon=True).start()

    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(CommandHandler("report", report_cmd))

    scheduler = BackgroundScheduler(timezone="Asia/Kolkata")

    # reminders
    scheduler.add_job(lambda: run_async(app, reminder), 'cron', hour=14)
    scheduler.add_job(lambda: run_async(app, reminder), 'cron', hour=16)

    # daily report
    scheduler.add_job(lambda: app.bot.send_message(GROUP_ID, build_report()), 'cron', hour=20)

    # weekly
    scheduler.add_job(lambda: run_async(app, weekly_leaderboard), 'cron', day_of_week='sat', hour=17)
    scheduler.add_job(lambda: run_async(app, weekly_streak), 'cron', day_of_week='sat', hour=17)

    scheduler.start()

    print("✅ BOT RUNNING ✅")

    # ✅ safe polling
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    async def polling():
        await app.initialize()
        await app.bot.delete_webhook(drop_pending_updates=True)

        offset = None

        while True:
            updates = await app.bot.get_updates(offset=offset, timeout=10)

            for u in updates:
                offset = u.update_id + 1
                await app.process_update(u)

    loop.run_until_complete(polling())

if __name__ == "__main__":
    main()
