import os
import gc
import json
import base64
from datetime import datetime
from threading import Thread, Lock
from flask import Flask, request, redirect
from flask_cors import CORS
import time
import asyncio
import logging
import signal
import sys

from dotenv import load_dotenv
load_dotenv()

from telegram import (
    Update,
    ReplyKeyboardMarkup,
    KeyboardButton,
    InlineKeyboardButton,
    InlineKeyboardMarkup
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
    ConversationHandler
)
from telegram.error import Conflict, NetworkError, TelegramError

import gspread
from oauth2client.service_account import ServiceAccountCredentials

# ====== Logging ======
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

# ====== Memory Monitoring ======
def log_memory_usage(context=""):
    """Log current memory usage"""
    import resource
    usage = resource.getrusage(resource.RUSAGE_SELF)
    memory_mb = usage.ru_maxrss / 1024  # Linux KB to MB
    logger.info(f"💾 Memory {context}: {memory_mb:.1f} MB")
    return memory_mb

# ====== Google Sheet Manager ======
class LightweightSheetManager:
    def __init__(self):
        self.sheet = None
        self.last_connect = None
        self.connect_interval = 300  # reconnect every 5 mins
        self._lock = Lock()
    
    def get_sheet(self):
        """Get sheet with connection pooling"""
        with self._lock:
            now = time.time()
            if self.sheet and self.last_connect and (now - self.last_connect < self.connect_interval):
                return self.sheet
            
            try:
                if self.sheet:
                    del self.sheet
                    gc.collect()
                
                scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
                creds_b64 = os.getenv("GOOGLE_CREDS_JSON")
                creds_json_str = base64.b64decode(creds_b64).decode("utf-8")
                credentials_info = json.loads(creds_json_str)
                creds = ServiceAccountCredentials.from_json_keyfile_dict(credentials_info, scope)
                
                client = gspread.authorize(creds)
                self.sheet = client.open("เครดิตฟรี กลุ่ม กิจกรรม ZOMBIE").worksheet("ข้อมูลลูกค้า")
                self.last_connect = now
                
                logger.info("✅ Google Sheets connected")
                return self.sheet
                
            except Exception as e:
                logger.error(f"❌ Sheet connection error: {e}")
                return None

# Initialize
sheet_manager = LightweightSheetManager()

# Bot Config
ASK_INFO = range(1)
GROUP_ID = -1002561643127

from collections import deque
pending_saves = deque(maxlen=100)
failed_saves = deque(maxlen=50)

# ====== Bot Handlers ======
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    log_memory_usage("at start command")
    
    welcome_message = (
        "🎉 ยินดีต้อนรับเข้าสู่ระบบยืนยันตัวตน ZOMBIE SLOT - กิจกรรม \n\n"
        "📌 กรุณาก๊อปข้อความด้านล่างนี้แล้วเติมข้อมูลให้ครบทุกช่อง \n\n"
        "ชื่อ - นามสกุล : \n"
        "เบอร์โทร : \n"
        "ธนาคาร : \n"
        "เลขบัญชี : \n"
        "อีเมล : \n"
        "ชื่อเทเลแกรม : \n"
        "@username Telegram :"
    )
    keyboard = [[KeyboardButton("เริ่มต้นส่งข้อมูล ✅")]]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    
    await update.message.reply_text(welcome_message, reply_markup=reply_markup)
    return ASK_INFO

async def get_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    
    if text.count(":") < 5:
        await update.message.reply_text("❗ ข้อมูลไม่ครบ กรุณากรอกให้ครบทุกช่อง")
        return ASK_INFO
    
    data = {}
    for line in text.strip().splitlines():
        if ':' in line:
            key, value = map(str.strip, line.split(':', 1))
            data[key.lower()] = value
    
    if any(not v for v in data.values()):
        await update.message.reply_text("❗ บางช่องเว้นว่าง กรุณากรอกให้ครบทุกช่อง")
        return ASK_INFO
    
    user = update.message.from_user
    user_id = user.id
    username = user.username or "ไม่มี"
    
    try:
        member = await context.bot.get_chat_member(chat_id=GROUP_ID, user_id=user_id)
        in_group = member.status in ['member', 'administrator', 'creator']
    except:
        in_group = False
    
    status_text = "✅ อยู่ในกลุ่มแล้ว" if in_group else "❌ ยังไม่ได้เข้ากลุ่ม"
    
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
        username,
        str(user_id),
        status_text,
        now,
        "PENDING",
        ""
    ]
    
    saved = False
    sheet = sheet_manager.get_sheet()
    if sheet:
        try:
            sheet.append_row(user_data)
            saved = True
            logger.info(f"✅ Saved user {user_id}")
        except Exception as e:
            logger.error(f"Save error: {e}")
    
    if not saved:
        pending_saves.append(user_data)
        logger.warning(f"⏳ Added to pending queue: {user_id}")
    
    house_keys = [
        ("💀 ZOMBIE XO", "ZOMBIE_XO"),
        ("👾 ZOMBIE PG", "ZOMBIE_PG"),
        ("👑 ZOMBIE KING", "ZOMBIE_KING"),
        ("🧟 ZOMBIE ALL", "ZOMBIE_ALL"),
        ("🐢 GENBU88", "GENBU88")
    ]
    
    def build_url(house, uid):
        return f"https://zombie-event-telegram-bot.onrender.com/go?house={house}&uid={uid}"
    
    keyboard = [
        [InlineKeyboardButton(text, url=build_url(house, user_id)) 
         for text, house in house_keys[:2]],
        [InlineKeyboardButton(text, url=build_url(house, user_id)) 
         for text, house in house_keys[2:4]],
        [InlineKeyboardButton(house_keys[4][0], url=build_url(house_keys[4][1], user_id))]
    ]
    
    confirm_message = (
        f"✅ ขอบคุณ {data.get('ชื่อ - นามสกุล', 'ผู้ใช้')} สำหรับการยืนยันตัวตน\n\n"
        f"สถานะ: {status_text}\n"
        "📋 ขั้นตอนต่อไป:\n"
        "1️⃣ แคปหน้าจอข้อความนี้\n"
        "2️⃣ เลือกบ้านที่ต้องการ\n"
        "3️⃣ แอดไลน์ติดต่อแอดมิน"
    )
    
    await update.message.reply_text(
        confirm_message, 
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    
    gc.collect()
    log_memory_usage("after save")
    
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ ยกเลิกการลงทะเบียน")
    return ConversationHandler.END

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Exception: {context.error}")

# ====== Flask App ======
flask_app = Flask(__name__)
CORS(flask_app)

@flask_app.route("/")
def home():
    return "Bot is running! ✅"

@flask_app.route("/health")
def health_check():
    memory_mb = log_memory_usage("health check")
    return {
        "status": "healthy" if memory_mb < 1500 else "warning",
        "memory_mb": round(memory_mb, 2),
        "pending": len(pending_saves),
        "failed": len(failed_saves)
    }

@flask_app.route("/go")
def go():
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
        logger.info(f"Click: {uid} -> {house}")
        return redirect(LINKS[house], 302)
    
    return "Invalid request", 400

# ====== Main ======
def main():
    # Start Flask FIRST (for port detection)
    logger.info("🌐 Starting Flask server on port 10000...")
    flask_thread = Thread(
        target=lambda: flask_app.run(
            host="0.0.0.0", 
            port=10000,
            debug=False,
            use_reloader=False
        ),
        daemon=True
    )
    flask_thread.start()
    
    # Wait for Flask to start
    time.sleep(2)
    
    # Initialize bot
    token = os.getenv("BOT_TOKEN")
    if not token:
        raise ValueError("No BOT_TOKEN in environment")
    
    try:
        app = (
            ApplicationBuilder()
            .token(token)
            .connection_pool_size(4)
            .pool_timeout(20.0)
            .read_timeout(10.0)
            .write_timeout(10.0)
            .build()
        )
        
        app.add_error_handler(error_handler)
        
        conv_handler = ConversationHandler(
            entry_points=[CommandHandler("start", start)],
            states={ASK_INFO: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_info)]},
            fallbacks=[CommandHandler("cancel", cancel)]
        )
        app.add_handler(conv_handler)
        
        log_memory_usage("at startup")
        
        logger.info("🤖 Optimized bot starting...")
        logger.info("📊 Memory limit: 2GB")
        logger.info("🌐 Health: http://0.0.0.0:10000/health")
        
        # Run bot (blocking)
        app.run_polling(
            drop_pending_updates=True,
            allowed_updates=Update.ALL_TYPES
        )
        
    except Conflict as e:
        logger.error(f"Conflict: {str(e)}")
        time.sleep(30)
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Fatal error: {str(e)}")
        import traceback
        traceback.print_exc()
    finally:
        logger.info("Bot stopped")

if __name__ == "__main__":
    main()