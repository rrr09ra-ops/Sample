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

# ✅ CONFIG
TOKEN = "8438035827:AAGfxMLEEHZ42kDGRnGI-Tp4UTNZLJWtNec"
GROUP_ID = -1004432548929
ADMIN_ID = 123456789

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

cursor.execute("""
CREATE TABLE IF NOT EXISTS logs (
    user_id INTEGER,
    username TEXT,
    name TEXT,
    date TEXT,
    count INTEGER
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER,
    username TEXT,
    name TEXT
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS streaks (
    user_id INTEGER,
    date TEXT
)
""")

conn.commit()

def get_today():
    return datetime.now(UTC).strftime("%Y-%m-%d")

# ================= PHOTO =================
async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    today = get_today()

    # save user
    cursor.execute("SELECT 1 FROM users WHERE user_id=?", (user.id,))
    if not cursor.fetchone():
        cursor.execute(
            "INSERT INTO users VALUES (?, ?, ?)",
            (user.id, user.username, user.first_name)
        )

    # update count
    cursor.execute("SELECT count FROM logs WHERE user_id=? AND date=?", (user.id, today))
    row = cursor.fetchone()

    if row:
        cursor.execute(
            "UPDATE logs SET count=count+1 WHERE user_id=? AND date=?",
            (user.id, today)
        )
    else:
        cursor.execute(
            "INSERT INTO logs VALUES (?, ?, ?, ?, ?)",
            (user.id, user.username, user.first_name, today, 1)
        )

    # update streak log
    cursor.execute("INSERT INTO streaks VALUES (?, ?)", (user.id, today))

    conn.commit()

# ================= STREAK =================
def calculate_streak(user_id):
    cursor.execute(
        "SELECT date FROM streaks WHERE user_id=? ORDER BY date DESC",
        (user_id,)
    )
    dates = [row[0] for row in cursor.fetchall()]

    streak = 0
    today = datetime.now(UTC)

    for i in range(len(dates)):
        check_day = (today - timedelta(days=i)).strftime("%Y-%m-%d")
        if check_day in dates:
            streak += 1
        else:
            break

    return streak

# ================= MISSED =================
async def missed_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    today_dt = datetime.now(UTC)
    today = get_today()

    cursor.execute("SELECT user_id, username, name FROM users")
    users = cursor.fetchall()

    cursor.execute("SELECT user_id FROM logs WHERE date=?", (today,))
    sent_users = {u[0] for u in cursor.fetchall()}

    missed_list = []

    for user_id, username, name in users:
        if user_id not in sent_users:
            missing_days = 0

            for i in range(0, 5):
                check_day = (today_dt - timedelta(days=i)).strftime("%Y-%m-%d")

                cursor.execute(
                    "SELECT 1 FROM logs WHERE user_id=? AND date=?",
                    (user_id, check_day)
                )

                if not cursor.fetchone():
                    missing_days += 1
                else:
                    break

            display = f"@{username}" if username else name

            if missing_days >= 2:
                missed_list.append(f"🚨 {display} — 0 (missed {missing_days} days)")
            else:
                missed_list.append(f"⚠️ {display} — 0")

    if not missed_list:
        await update.message.reply_text("✅ No one missed today!")
        return

    text = "⚠️ Missed Users:\n\n" + "\n".join(missed_list)

    await update.message.reply_text(text)

# ================= MISSED YESTERDAY =================
async def missed_yesterday_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    yesterday = (datetime.now(UTC) - timedelta(days=1)).strftime("%Y-%m-%d")

    cursor.execute("SELECT user_id, username, name FROM users")
    users = cursor.fetchall()

    cursor.execute("SELECT user_id FROM logs WHERE date=?", (yesterday,))
    sent_users = {u[0] for u in cursor.fetchall()}

    missed = []

    for user_id, username, name in users:
        if user_id not in sent_users:
            display = f"@{username}" if username else name
            missed.append(f"{display} — 0")

    if not missed:
        await update.message.reply_text("✅ No one missed yesterday!")
        return

    text = f"📅 Missed Yesterday ({yesterday}):\n\n" + "\n".join(missed)

    await update.message.reply_text(text)

# ================= AUTO MISSED =================
async def send_missed_alert(app):
    today = get_today()

    cursor.execute("SELECT user_id, username, name FROM users")
    users = cursor.fetchall()

    cursor.execute("SELECT user_id FROM logs WHERE date=?", (today,))
    sent_users = {u[0] for u in cursor.fetchall()}

    missed = []

    for user_id, username, name in users:
        if user_id not in sent_users:
            display = f"@{username}" if username else name
            missed.append(f"{display} — 0")

    if not missed:
        return

    text = "⚠️ Missed Users:\n\n" + "\n".join(missed)

    await app.bot.send_message(chat_id=GROUP_ID, text=text)

# ================= REPORT =================
async def send_report(app):
    today = get_today()

    cursor.execute("SELECT user_id, username, name FROM users")
    users = cursor.fetchall()

    cursor.execute("SELECT user_id, count FROM logs WHERE date=?", (today,))
    data_dict = dict(cursor.fetchall())

    ranked = []
    total = 0

    for uid, username, name in users:
        count = data_dict.get(uid, 0)
        streak = calculate_streak(uid)
        display = f"@{username}" if username else name

        ranked.append((display, count, streak))
        total += count

    ranked.sort(key=lambda x: x[1], reverse=True)

    report = f"📊 Daily Report ({today})\n\n🏆 Leaderboard:\n\n"

    for i, (display, count, streak) in enumerate(ranked, 1):
        report += f"{i}. {display} — {count} (🔥 {streak}d)\n"

    report += f"\n📸 Total Today: {total}"

    await app.bot.send_message(chat_id=GROUP_ID, text=report)

# ================= MAIN =================
def main():
    threading.Thread(target=run_server, daemon=True).start()

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(CommandHandler("missed", missed_cmd))
    app.add_handler(CommandHandler("missed_yesterday", missed_yesterday_cmd))
    app.add_handler(CommandHandler("report", lambda u, c: send_report(c.application)))

    scheduler = BackgroundScheduler(timezone="UTC")

    def run_async(func):
        asyncio.run_coroutine_threadsafe(func(app), loop)

    # ✅ 2 PM IST
    scheduler.add_job(run_async, args=[send_missed_alert], trigger='cron', hour=8, minute=30)

    # ✅ 8:30 PM IST
    scheduler.add_job(run_async, args=[send_report], trigger='cron', hour=15, minute=0)

    scheduler.start()

    loop.run_until_complete(app.initialize())
    loop.run_until_complete(app.start())
    loop.run_until_complete(app.updater.start_polling())

    print("✅ CLEAN FINAL BOT RUNNING")

    loop.run_forever()

if __name__ == "__main__":
    main()
