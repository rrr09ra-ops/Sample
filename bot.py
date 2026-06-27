import sqlite3
from datetime import datetime
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, ContextTypes, filters
import sqlite3
from datetime import datetime
import os

TOKEN = os.environ.get("TOKEN")   # ✅ use this

print("DEBUG TOKEN:", TOKEN)      # ✅ add this line

if TOKEN is None or TOKEN == "":
    raise ValueError("❌ TOKEN missing!")

conn = sqlite3.connect("bot.db", check_same_thread=False)
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS logs (
    user_id INTEGER,
    name TEXT,
    date TEXT,
    count INTEGER
)
""")
conn.commit()

# ================= FUNCTIONS =================

def get_today():
    return datetime.now().strftime("%Y-%m-%d")

def get_month():
    return datetime.now().strftime("%Y-%m")

def format_user(name, username):
    return f"@{username}" if username else name

def get_all_users():
    cursor.execute("SELECT DISTINCT user_id, username, name FROM logs")
    return cursor.fetchall()

def get_today_users():
    today = get_today()
    cursor.execute("SELECT user_id, username, name, count FROM logs WHERE date=?", (today,))
    return cursor.fetchall()

def get_monthly_count(user_id):
    month = get_month()
    cursor.execute("""
    SELECT SUM(count) FROM logs
    WHERE user_id=? AND date LIKE ?
    """, (user_id, f"{month}%"))
    result = cursor.fetchone()[0]
    return result if result else 0

# ================= HANDLER =================

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    today = get_today()

    username = user.username
    name = user.first_name

    cursor.execute("""
    SELECT count FROM logs WHERE user_id=? AND date=?
    """, (user.id, today))

    row = cursor.fetchone()

    if row:
        cursor.execute("""
        UPDATE logs SET count = count + 1 WHERE user_id=? AND date=?
        """, (user.id, today))
    else:
        cursor.execute("""
        INSERT INTO logs (user_id, username, name, date, count)
        VALUES (?,?,?,?,?)
        """, (user.id, username, name, today, 1))

    conn.commit()

# ================= DAILY REPORT =================

async def daily_report(context: ContextTypes.DEFAULT_TYPE):
    today = get_today()

    all_users = get_all_users()
    today_data = get_today_users()

    data_dict = {u[0]: u for u in today_data}

    report = f"📊 *Daily Report* ({today})\n\n"

    shared_text = "✅ *Shared Selfies*\n"
    missed_text = "❌ *Missed*\n"
    total_images = 0

    for user_id, username, name in all_users:
        display = format_user(name, username)

        if user_id in data_dict:
            count = data_dict[user_id][3]
            monthly = get_monthly_count(user_id)

            shared_text += f"• {display} — {count} today | {monthly} month\n"
            total_images += count
        else:
            missed_text += f"• {display}\n"

    report += shared_text + "\n" + missed_text
    report += f"\n📸 *Total Images Today:* {total_images}"

    await context.bot.send_message(
        chat_id=GROUP_ID,
        text=report,
        parse_mode="Markdown"
    )

# ================= REMINDER =================

async def reminder(context: ContextTypes.DEFAULT_TYPE):
    today = get_today()

    all_users = get_all_users()

    cursor.execute("SELECT user_id FROM logs WHERE date=?", (today,))
    submitted = {u[0] for u in cursor.fetchall()}

    reminder_list = []

    for user_id, username, name in all_users:
        if user_id not in submitted:
            display = format_user(name, username)
            reminder_list.append(display)

    if reminder_list:
        message = "⏰ *Reminder*\n\nFollowing members have not shared selfie yet:\n\n"
        message += "\n".join([f"• {user}" for user in reminder_list])

        await context.bot.send_message(
            chat_id=GROUP_ID,
       text=message,
            parse_mode="Markdown"
        )

# ================= MAIN =================

import asyncio
from telegram.ext import ApplicationBuilder, MessageHandler, filters

def main():
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))

    print("✅ Bot started successfully")

    app.run_polling()

if __name__ == "__main__":
    # ✅ create event loop manually (fix for Python 3.14)
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    main()
