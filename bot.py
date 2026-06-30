import sqlite3
import threading
from datetime import datetime, UTC
from http.server import HTTPServer, BaseHTTPRequestHandler

from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, CommandHandler, ContextTypes, filters

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

# ================= CONFIG =================
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
conn.commit()

def get_today():
    return datetime.now(UTC).strftime("%Y-%m-%d")

# ================= HANDLERS =================
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    cursor.execute("INSERT OR IGNORE INTO users VALUES (?, ?, ?)",
                   (user.id, user.username, user.first_name))
    conn.commit()

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

    conn.commit()

# ================= REPORT =================
async def send_report(update: Update, context: ContextTypes.DEFAULT_TYPE):
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

    await update.message.reply_text(text)

# ================= MAIN =================
def main():
    threading.Thread(target=run_server, daemon=True).start()

    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(MessageHandler(filters.ALL, handle_message))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))

    # ✅ IMPORTANT: command handler
    app.add_handler(CommandHandler("report", send_report))

    print("✅ BOT RUNNING ✅")

    # ✅ FINAL FIX — THIS WORKS ON RENDER + PYTHON 3.14
    app.run_polling(stop_signals=None)

if __name__ == "__main__":
    main()
