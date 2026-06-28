import os
import sqlite3
import threading
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
from telegram.ext import ApplicationBuilder, MessageHandler, filters

# ================= CONFIG =================
TOKEN = os.environ.get("TOKEN")
GROUP_ID = -5314646004   # ⚠️ REPLACE with your group ID

print("DEBUG TOKEN:", TOKEN)

if not TOKEN:
    raise ValueError("❌ TOKEN missing!")

# ================= DUMMY SERVER (RENDER FIX) =================
class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot is running")

def run_server():
    server = HTTPServer(("0.0.0.0", 10000), Handler)
    server.serve_forever()

# ================= DATABASE =================
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

# ================= HELPERS =================
def get_today():
    return datetime.now().strftime("%Y-%m-%d")

# ================= PHOTO HANDLER =================
async def handle_photo(update, context):
    user = update.effective_user
    today = get_today()

    cursor.execute("SELECT count FROM logs WHERE user_id=? AND date=?",
                   (user.id, today))
    row = cursor.fetchone()

    if row:
        cursor.execute("UPDATE logs SET count=count+1 WHERE user_id=? AND date=?",
                       (user.id, today))
    else:
        cursor.execute("INSERT INTO logs VALUES (?,?,?,?)",
                       (user.id, user.first_name, today, 1))

    conn.commit()

# ================= MAIN =================
def main():
    # Start dummy server (fix Render timeout)
    threading.Thread(target=run_server).start()

    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))

    print("✅ Bot started successfully")

    app.run_polling()

# ================= START =================
if __name__ == "__main__":
    main()
