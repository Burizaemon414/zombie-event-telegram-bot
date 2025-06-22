import os
import gc
import json
import base64
from datetime import datetime
from flask import Flask, request, jsonify
from flask_cors import CORS
import logging
import asyncio
from threading import Lock

from dotenv import load_dotenv
load_dotenv()

import telegram
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup

import gspread
from oauth2client.service_account import ServiceAccountCredentials

# ====== Logging ======
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ====== Bot Setup ======
BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("No BOT_TOKEN in environment")

bot = telegram.Bot(token=BOT_TOKEN)
WEBHOOK_URL = "https://zombie-event-telegram-bot.onrender.com/webhook"

# ====== Memory Monitor ======
def log_memory():
    import resource
    usage = resource.getrusage(resource.RUSAGE_SELF)
    memory_mb = usage.ru_maxrss / 1024
    logger.info(f"💾 Memory: {memory_mb:.1f} MB")
    return memory_mb

# ====== Google Sheets ======
class SheetManager:
    def __init__(self):
        self.sheet = None
        self._lock = Lock()
        self._connect()
    
    def _connect(self):
        try:
            scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
            creds_b64 = os.getenv("GOOGLE_CREDS_JSON")
            creds_json_str = base64.b64decode(creds_b64).decode("utf-8")
            credentials_info = json.loads(creds_json_str)
            creds = ServiceAccountCredentials.from_json_keyfile_dict(credentials_info, scope)
            
            client = gspread.authorize(creds)
            self.sheet = client.open("เครดิตฟรี กลุ่ม กิจกรรม ZOMBIE").worksheet("ข้อมูลลูกค้า")
            logger.info("✅ Google Sheets connected")
        except Exception as e:
            logger.error(f"Sheet error: {e}")
    
    def append_row(self, data):
        with self._lock:
            try:
                if not self.sheet:
                    self._connect()
                self.sheet.append_row(data)
                return True
            except Exception as e:
                logger.error(f"Append error: {e}")
                return False

sheet_manager = SheetManager()

# ====== Flask App ======
app = Flask(__name__)
CORS(app)

# User states
user_states = {}

@app.route("/")
def home():
    return "Bot is running! ✅"

@app.route("/health")
def health():
    memory = log_memory()
    return {
        "status": "healthy" if memory < 500 else "warning",
        "memory_mb": round(memory, 2),
        "webhook": WEBHOOK_URL
    }

@app.route("/webhook", methods=["POST"])
def webhook():
    """Handle Telegram updates via webhook"""
    try:
        update = Update.de_json(request.get_json(force=True), bot)
        
        # Handle different update types
        if update.message:
            handle_message(update)
        elif update.callback_query:
            handle_callback(update)
        
        return "OK"
    except Exception as e:
        logger.error(f"Webhook error: {e}")
        return "Error", 500

def handle_message(update):
    """Handle text messages"""
    chat_id = update.message.chat_id
    text = update.message.text
    user = update.message.from_user
    
    if text == "/start":
        # Send welcome message
        welcome = (
            "🎉 ยินดีต้อนรับเข้าสู่ระบบยืนยันตัวตน ZOMBIE SLOT\n\n"
            "📌 กรุณาก๊อปข้อความด้านล่างแล้วกรอกข้อมูล:\n\n"
            "ชื่อ - นามสกุล : \n"
            "เบอร์โทร : \n"
            "ธนาคาร : \n"
            "เลขบัญชี : \n"
            "อีเมล : \n"
            "ชื่อเทเลแกรม : \n"
            "@username Telegram :"
        )
        bot.send_message(chat_id, welcome)
        user_states[chat_id] = "waiting_info"
        
    elif user_states.get(chat_id) == "waiting_info":
        # Process user info
        if text.count(":") < 5:
            bot.send_message(chat_id, "❗ ข้อมูลไม่ครบ กรุณากรอกใหม่")
            return
        
        # Parse data
        data = {}
        for line in text.strip().splitlines():
            if ':' in line:
                key, value = map(str.strip, line.split(':', 1))
                data[key.lower()] = value
        
        # Save to sheet
        import pytz
        bangkok_tz = pytz.timezone('Asia/Bangkok')
        now = datetime.now(bangkok_tz).strftime("%Y-%m-%d %H:%M:%S")
        
        user_data = [
            data.get("ชื่อ - นามสกุล", ""),
            data.get("เบอร์โทร", ""),
            data.get("ธนาคาร", ""),
            data.get("เลขบัญชี", ""),
            data.get("อีเมล", ""),
            data.get("ชื่อเทเลแกรม", ""),
            data.get("@username telegram", ""),
            user.username or "ไม่มี",
            str(user.id),
            "ไม่ทราบ",
            now,
            "PENDING",
            ""
        ]
        
        if sheet_manager.append_row(user_data):
            # Send confirmation with buttons
            houses = [
                ("💀 ZOMBIE XO", "ZOMBIE_XO"),
                ("👾 ZOMBIE PG", "ZOMBIE_PG"),
                ("👑 ZOMBIE KING", "ZOMBIE_KING"),
                ("🧟 ZOMBIE ALL", "ZOMBIE_ALL"),
                ("🐢 GENBU88", "GENBU88")
            ]
            
            keyboard = []
            for i in range(0, len(houses), 2):
                row = []
                for text, code in houses[i:i+2]:
                    url = f"https://zombie-event-telegram-bot.onrender.com/go?house={code}&uid={user.id}"
                    row.append(InlineKeyboardButton(text, url=url))
                keyboard.append(row)
            
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            msg = (
                f"✅ ขอบคุณ {data.get('ชื่อ - นามสกุล', 'คุณ')} สำหรับการลงทะเบียน\n\n"
                "📋 ขั้นตอนต่อไป:\n"
                "1️⃣ แคปหน้าจอนี้\n"
                "2️⃣ เลือกบ้านที่ต้องการ\n"
                "3️⃣ แอดไลน์ติดต่อแอดมิน"
            )
            
            bot.send_message(chat_id, msg, reply_markup=reply_markup)
            user_states.pop(chat_id, None)
        else:
            bot.send_message(chat_id, "❌ เกิดข้อผิดพลาด กรุณาลองใหม่")

def handle_callback(update):
    """Handle button callbacks"""
    query = update.callback_query
    query.answer()

@app.route("/go")
def go():
    """Redirect to LINE"""
    from flask import redirect
    
    LINKS = {
        "ZOMBIE_XO": "https://lin.ee/SgguCbJ",
        "ZOMBIE_PG": "https://lin.ee/ETELgrN",
        "ZOMBIE_KING": "https://lin.ee/fJilKIf",
        "ZOMBIE_ALL": "https://lin.ee/9eogsb8e",
        "GENBU88": "https://lin.ee/JCCXt06"
    }
    
    house = request.args.get("house", "").upper()
    uid = request.args.get("uid")
    
    if house in LINKS:
        logger.info(f"Redirect: {uid} -> {house}")
        return redirect(LINKS[house])
    
    return "Invalid request", 400

@app.route("/setup_webhook", methods=["GET", "POST"])
def setup_webhook():
    """Setup webhook endpoint"""
    try:
        # Delete old webhook
        bot.delete_webhook()
        
        # Set new webhook
        success = bot.set_webhook(url=WEBHOOK_URL)
        
        if success:
            info = bot.get_webhook_info()
            return {
                "status": "success",
                "webhook_url": info.url,
                "pending_updates": info.pending_update_count
            }
        else:
            return {"status": "failed"}, 500
            
    except Exception as e:
        return {"status": "error", "message": str(e)}, 500

# ====== Main ======
if __name__ == "__main__":
    # Log startup
    logger.info("🤖 Starting Webhook Bot...")
    log_memory()
    
    # Setup webhook on startup
    try:
        bot.delete_webhook()
        bot.set_webhook(url=WEBHOOK_URL)
        logger.info(f"✅ Webhook set: {WEBHOOK_URL}")
    except Exception as e:
        logger.error(f"Webhook setup error: {e}")
    
    # Run Flask
    app.run(host="0.0.0.0", port=10000, debug=False)