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

cursor.execute("""CREATE TABLE IF NOT EXISTS logs (user_id INTEGER, username TEXT, name TEXT, date TEXT, count INTEGER)""")
cursor.execute("""CREATE TABLE IF NOT EXISTS users (user_id INTEGER, username TEXT, name TEXT)""")
cursor.execute("""CREATE TABLE IF NOT EXISTS streaks (user_id INTEGER, date TEXT)""")

conn.commit()

def get_today():
    return datetime.now(UTC).strftime("%Y-%m-%d")

# ================= USER TRACK =================
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    cursor.execute("SELECT 1 FROM users WHERE user_id=?", (user.id,))
    if not cursor.fetchone():
        cursor.execute("INSERT INTO users VALUES (?, ?, ?)", (user.id, user.username, user.first_name))
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
        cursor.execute("INSERT INTO logs VALUES (?, ?, ?, ?, ?)",
                       (user.id, user.username, user.first_name, today, 1))

    cursor.execute("INSERT INTO streaks VALUES (?, ?)", (user.id, today))
    conn.commit()

# ================= STREAK =================
def calculate_streak(user_id):
    cursor.execute("SELECT date FROM streaks WHERE user_id=? ORDER BY date DESC", (user_id,))
    dates = [r[0] for r in cursor.fetchall()]

    streak, today = 0, datetime.now(UTC)

    for i in range(len(dates)):
        d = (today - timedelta(days=i)).strftime("%Y-%m-%d")
        if d in dates:
            streak += 1
        else:
            break

    return streak

# ================= TREND =================
def get_user_trend(user_id):
    today = get_today()
    yesterday = (datetime.now(UTC) - timedelta(days=1)).strftime("%Y-%m-%d")

    cursor.execute("SELECT count FROM logs WHERE user_id=? AND date=?", (user_id, today))
    t = cursor.fetchone()
    t = t[0] if t else 0

    cursor.execute("SELECT count FROM logs WHERE user_id=? AND date=?", (user_id, yesterday))
    y = cursor.fetchone()
    y = y[0] if y else 0

    if t > y: return "📈"
    elif t < y: return "📉"
    else: return "➖"

# ================= IMPROVED =================
def get_most_improved_user():
    today = get_today()
    yesterday = (datetime.now(UTC) - timedelta(days=1)).strftime("%Y-%m-%d")

    cursor.execute("SELECT user_id, count FROM logs WHERE date=?", (today,))
    today_data = dict(cursor.fetchall())

    cursor.execute("SELECT user_id, count FROM logs WHERE date=?", (yesterday,))
    y_data = dict(cursor.fetchall())

    best, score = None, -999

    for uid, val in today_data.items():
        diff = val - y_data.get(uid, 0)
        if diff > score:
            best, score = uid, diff

    if not best:
        return None

    cursor.execute("SELECT username, name FROM users WHERE user_id=?", (best,))
    u = cursor.fetchone()

    name = f"@{u[0]}" if u[0] else u[1]
    return name, score

# ================= TREND GRAPH =================
async def send_trend_graph(app):
    days, values = [], []

    for i in range(6, -1, -1):
        d = (datetime.now(UTC) - timedelta(days=i)).strftime("%Y-%m-%d")
        cursor.execute("SELECT SUM(count) FROM logs WHERE date=?", (d,))
        val = cursor.fetchone()[0] or 0

        days.append(d[-5:])
        values.append(val)

    plt.plot(days, values, marker='o')
    plt.title("7-Day Trend")
    plt.savefig("trend.png")
    plt.close()

    await app.bot.send_photo(chat_id=GROUP_ID, photo=open("trend.png", "rb"))

# ================= MISSED =================
async def missed_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    today = get_today()

    cursor.execute("SELECT user_id, username, name FROM users")
    users = cursor.fetchall()

    cursor.execute("SELECT user_id FROM logs WHERE date=?", (today,))
    sent = {u[0] for u in cursor.fetchall()}

    out = []

    for uid, username, name in users:
        if uid not in sent:
            disp = f"@{username}" if username else name
            out.append(f"{disp} — 0")

    await update.message.reply_text("\n".join(out) if out else "✅ All active")

# ================= YESTERDAY =================
async def missed_yesterday_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    yesterday = (datetime.now(UTC) - timedelta(days=1)).strftime("%Y-%m-%d")

    cursor.execute("SELECT user_id, username, name FROM users")
    users = cursor.fetchall()

    cursor.execute("SELECT user_id FROM logs WHERE date=?", (yesterday,))
    sent = {u[0] for u in cursor.fetchall()}

    out = []

    for uid, username, name in users:
        if uid not in sent:
            disp = f"@{username}" if username else name
            out.append(f"{disp} — 0")

    await update.message.reply_text("\n".join(out) if out else "✅ No misses")

# ================= LOW ALERT =================
async def send_low_performance_alert(app):
    today = get_today()

    cursor.execute("SELECT user_id, username, name FROM users")
    users = cursor.fetchall()

    cursor.execute("SELECT user_id, count FROM logs WHERE date=?", (today,))
    data = dict(cursor.fetchall())

    msg = []

    for uid, u, n in users:
        c = data.get(uid, 0)
        name = f"@{u}" if u else n

        if c == 0:
            msg.append(f"🚨 {name} — 0")
        elif c == 1:
            msg.append(f"⚠️ {name} — 1")

    if msg:
        await app.bot.send_message(chat_id=GROUP_ID, text="Low Performance:\n\n" + "\n".join(msg))

# ================= PRIVATE ALERT =================
async def send_private_alerts(app):
    today = get_today()

    cursor.execute("SELECT user_id FROM users")
    users = cursor.fetchall()

    cursor.execute("SELECT user_id, count FROM logs WHERE date=?", (today,))
    data = dict(cursor.fetchall())

    for (uid,) in users:
        c = data.get(uid, 0)
        if c <= 1:
            try:
                await app.bot.send_message(uid, "⚠️ Please improve today's performance")
            except:
                pass

# ================= REPORT =================
async def send_report(app):
    today = get_today()

    cursor.execute("SELECT user_id, username, name FROM users")
    users = cursor.fetchall()

    cursor.execute("SELECT user_id, count FROM logs WHERE date=?", (today,))
    data = dict(cursor.fetchall())

    ranked = []
    total = 0

    for uid, u, n in users:
        c = data.get(uid, 0)
        s = calculate_streak(uid)
        t = get_user_trend(uid)
        name = f"@{u}" if u else n

        ranked.append((name, c, s, t))
        total += c

    ranked.sort(key=lambda x: x[1], reverse=True)

    report = f"📊 REPORT ({today})\n\n"

    for i, (n, c, s, t) in enumerate(ranked, 1):
        report += f"{i}. {n} — {c} (🔥 {s}) {t}\n"

    improved = get_most_improved_user()
    if improved:
        report += f"\n🏆 Most Improved: {improved[0]} (+{improved[1]})"

    report += f"\n📸 Total: {total}"

    await app.bot.send_message(chat_id=GROUP_ID, text=report)
    await send_trend_graph(app)

# ================= WEEKLY =================
async def send_weekly_report(app):
    today = datetime.now(UTC)

    data = {}

    for i in range(7):
        d = (today - timedelta(days=i)).strftime("%Y-%m-%d")
        cursor.execute("SELECT user_id, count FROM logs WHERE date=?", (d,))
        for uid, c in cursor.fetchall():
            data[uid] = data.get(uid, 0) + c

    cursor.execute("SELECT user_id, username, name FROM users")
    users = cursor.fetchall()

    ranked = []
    for uid, u, n in users:
        name = f"@{u}" if u else n
        ranked.append((name, data.get(uid, 0)))

    ranked.sort(key=lambda x: x[1], reverse=True)

    text = "📊 Weekly:\n\n"
    for i, (n, c) in enumerate(ranked, 1):
        text += f"{i}. {n} — {c}\n"

    await app.bot.send_message(chat_id=GROUP_ID, text=text)

# ================= MAIN =================
def main():
    threading.Thread(target=run_server, daemon=True).start()

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(MessageHandler(filters.ALL, handle_message))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))

    app.add_handler(CommandHandler("missed", missed_cmd))
    app.add_handler(CommandHandler("missed_yesterday", missed_yesterday_cmd))
    app.add_handler(CommandHandler("weekly", lambda u, c: send_weekly_report(c.application)))

    scheduler = BackgroundScheduler(timezone="UTC")

    def run_async(func):
        asyncio.run_coroutine_threadsafe(func(app), loop)

    scheduler.add_job(run_async, args=[send_low_performance_alert], trigger='cron', hour=12, minute=30)  # 6 PM IST
    scheduler.add_job(run_async, args=[send_private_alerts], trigger='cron', hour=13, minute=0)  # 6:30 PM IST
    scheduler.add_job(run_async, args=[send_report], trigger='cron', hour=15, minute=0)  # 8:30 PM IST

    scheduler.start()

    loop.run_until_complete(app.initialize())
    loop.run_until_complete(app.start())
    loop.run_until_complete(app.updater.start_polling())

    print("🔥 ULTIMATE BOT RUNNING")

    loop.run_forever()

if __name__ == "__main__":
    main()
