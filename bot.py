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

# ✅ CONFIG
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

cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    username TEXT,
    name TEXT
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS logs (
    user_id INTEGER,
    date TEXT,
    count INTEGER
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS streaks (
    user_id INTEGER,
    date TEXT
)
""")

conn.commit()


# ================= HELPERS =================
def get_today():
    return datetime.now(UTC).strftime("%Y-%m-%d")


# ================= USER TRACK =================
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    cursor.execute(
        "INSERT OR IGNORE INTO users VALUES (?, ?, ?)",
        (user.id, user.username, user.first_name)
    )
    conn.commit()


# ================= PHOTO =================
async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    today = get_today()

    await handle_message(update, context)

    cursor.execute("SELECT count FROM logs WHERE user_id=? AND date=?", (user.id, today))
    row = cursor.fetchone()

    if row:
        cursor.execute(
            "UPDATE logs SET count=count+1 WHERE user_id=? AND date=?",
            (user.id, today)
        )
    else:
        cursor.execute(
            "INSERT INTO logs VALUES (?, ?, ?)",
            (user.id, today, 1)
        )

    cursor.execute(
        "SELECT 1 FROM streaks WHERE user_id=? AND date=?",
        (user.id, today)
    )
    if not cursor.fetchone():
        cursor.execute("INSERT INTO streaks VALUES (?, ?)", (user.id, today))

    conn.commit()


# ================= STREAK =================
def get_streak(user_id):
    cursor.execute("SELECT date FROM streaks WHERE user_id=?", (user_id,))
    dates = set([d[0] for d in cursor.fetchall()])

    streak = 0
    today = datetime.now(UTC)

    for i in range(30):
        d = (today - timedelta(days=i)).strftime("%Y-%m-%d")
        if d in dates:
            streak += 1
        else:
            break

    return streak


# ================= TREND =================
def get_trend(user_id):
    today = get_today()
    yesterday = (datetime.now(UTC) - timedelta(days=1)).strftime("%Y-%m-%d")

    cursor.execute("SELECT count FROM logs WHERE user_id=? AND date=?", (user_id, today))
    t = cursor.fetchone()
    t = t[0] if t else 0

    cursor.execute("SELECT count FROM logs WHERE user_id=? AND date=?", (user_id, yesterday))
    y = cursor.fetchone()
    y = y[0] if y else 0

    if t > y:
        return "📈"
    elif t < y:
        return "📉"
    else:
        return "➖"


# ================= GRAPH =================
async def send_graph(app):
    days = []
    values = []

    for i in range(6, -1, -1):
        d = (datetime.now(UTC) - timedelta(days=i)).strftime("%Y-%m-%d")

        cursor.execute("SELECT SUM(count) FROM logs WHERE date=?", (d,))
        val = cursor.fetchone()[0] or 0

        days.append(d[-5:])
        values.append(val)

    plt.figure()
    plt.plot(days, values, marker='o')
    plt.title("7 Day Trend")
    plt.tight_layout()

    plt.savefig("trend.png")
    plt.close()

    with open("trend.png", "rb") as img:
        await app.bot.send_photo(GROUP_ID, img)


# ================= REPORT =================
async def send_report(app):
    today = get_today()

    cursor.execute("SELECT * FROM users")
    users = cursor.fetchall()

    cursor.execute("SELECT user_id, count FROM logs WHERE date=?", (today,))
    data = dict(cursor.fetchall())

    ranked = []
    total = 0

    for uid, username, name in users:
        count = data.get(uid, 0)
        streak = get_streak(uid)
        trend = get_trend(uid)

        display = f"@{username}" if username else name
        ranked.append((display, count, streak, trend))
        total += count

    ranked.sort(key=lambda x: x[1], reverse=True)

    text = f"📊 REPORT ({today})\n\n"

    for i, (name, count, streak, trend) in enumerate(ranked, 1):
        text += f"{i}. {name} — {count} (🔥 {streak}) {trend}\n"

    text += f"\n📸 Total: {total}"

    await app.bot.send_message(GROUP_ID, text)

    await send_graph(app)


# ================= COMMAND =================
async def report_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send_report(context.application)


# ================= MAIN =================
def main():
    threading.Thread(target=run_server, daemon=True).start()

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    global app
    app = ApplicationBuilder().token(TOKEN).build()

    # ✅ handlers
    app.add_handler(MessageHandler(filters.ALL, handle_message))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(CommandHandler("report", report_cmd))

    scheduler = BackgroundScheduler(timezone="UTC")

    def run_async(func):
        asyncio.run_coroutine_threadsafe(func(app), loop)

    # ✅ 8:30 PM IST (15:00 UTC)
    scheduler.add_job(run_async, args=[send_report], trigger='cron', hour=15, minute=0)

    scheduler.start()

    async def start_bot():
        await app.initialize()

        # ✅ FIX CONFLICT
        await app.bot.delete_webhook(drop_pending_updates=True)

        # ✅ START POLLING CORRECTLY
        await app.start()
        await app.start_polling()

        print("✅ BOT RUNNING & LISTENING")

    loop.run_until_complete(start_bot())
    loop.run_forever()


if __name__ == "__main__":
    main()
