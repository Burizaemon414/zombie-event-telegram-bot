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
import hashlib
from collections import deque, defaultdict

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

# ====== CRITICAL: Disable all sensitive logging ======
class NoSensitiveFilter(logging.Filter):
    """Filter out any sensitive data from logs completely"""
    
    SENSITIVE_PATTERNS = [
        r'\d{3,4}-?\d{3,4}-?\d{4}',  # Phone numbers
        r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}',  # Emails
        r'\b\d{6,}\b',  # Account numbers
        r'Col\d+\s+[^:]+:\s+[^\']+',  # Column data
    ]
    
    def filter(self, record):
        import re
        message = record.getMessage()
        
        # Block any message containing sensitive patterns
        for pattern in self.SENSITIVE_PATTERNS:
            if re.search(pattern, message):
                return False
        
        # Block specific sensitive keywords
        sensitive_keywords = ['เบอร์', 'อีเมล', 'บัญชี', 'Col1', 'Col2', 'Col3', 'Col4', 'Col5']
        if any(keyword in message for keyword in sensitive_keywords):
            return False
            
        return True

# Configure completely secure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)

# Add the filter to ALL handlers
secure_filter = NoSensitiveFilter()
for handler in logging.root.handlers:
    handler.addFilter(secure_filter)

logger = logging.getLogger(__name__)

# ====== Rate Limiting ======
class RateLimiter:
    def __init__(self, max_requests=3, time_window=60):
        self.max_requests = max_requests
        self.time_window = time_window
        self.requests = defaultdict(deque)
        self.lock = Lock()
    
    def is_allowed(self, user_id):
        with self.lock:
            now = time.time()
            user_requests = self.requests[user_id]
            
            # Clean old requests
            while user_requests and user_requests[0] < now - self.time_window:
                user_requests.popleft()
            
            # Check if under limit
            if len(user_requests) < self.max_requests:
                user_requests.append(now)
                return True
            
            return False

# Initialize rate limiter (stricter limits)
rate_limiter = RateLimiter(max_requests=3, time_window=60)

# ====== Memory Monitoring ======
def log_memory_usage(context=""):
    """Log current memory usage"""
    import resource
    usage = resource.getrusage(resource.RUSAGE_SELF)
    memory_mb = usage.ru_maxrss / 1024
    logger.info(f"Memory {context}: {memory_mb:.1f} MB")
    return memory_mb

# ====== Google Sheet Manager ======
class LightweightSheetManager:
    def __init__(self):
        self.sheet = None
        self.last_connect = None
        self.connect_interval = 300
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
                
                logger.info("Google Sheets connected successfully")
                return self.sheet
                
            except Exception as e:
                logger.error(f"Sheet connection failed: {type(e).__name__}")
                return None

# Initialize
sheet_manager = LightweightSheetManager()

# Bot Config
ASK_INFO = range(1)
GROUP_ID = -1002561643127

pending_saves = deque(maxlen=100)
failed_saves = deque(maxlen=50)

# ====== Helper Functions ======
def create_user_hash(user_id):
    """Create hash for user logging (privacy)"""
    return hashlib.md5(str(user_id).encode()).hexdigest()[:8]

async def check_group_membership_fixed(context, user_id):
    """FIXED group membership check - exact code from working bot"""
    try:
        # This is the EXACT working code from bot_fixed_final.py
        member = await context.bot.get_chat_member(chat_id=GROUP_ID, user_id=user_id)
        in_group = member.status in ['member', 'administrator', 'creator']
        
        user_hash = create_user_hash(user_id)
        logger.info(f"Group check result for user {user_hash}: {'IN_GROUP' if in_group else 'NOT_IN_GROUP'}")
        return in_group
        
    except Exception as e:
        user_hash = create_user_hash(user_id)
        logger.error(f"Group check failed for user {user_hash}: {type(e).__name__}")
        return False

# ====== Bot Handlers ======
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    user_hash = create_user_hash(user_id)
    
    # Rate limiting check
    if not rate_limiter.is_allowed(user_id):
        await update.message.reply_text("⏱️ กรุณารอสักครู่ก่อนส่งคำสั่งใหม่")
        logger.warning(f"Rate limit exceeded for user {user_hash}")
        return ConversationHandler.END
    
    log_memory_usage("start")
    logger.info(f"Start command from user {user_hash}")
    
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
    user_id = update.message.from_user.id
    user_hash = create_user_hash(user_id)
    text = update.message.text
    
    # Rate limiting check
    if not rate_limiter.is_allowed(user_id):
        await update.message.reply_text("⏱️ กรุณารอสักครู่ก่อนส่งข้อมูลใหม่")
        return ASK_INFO
    
    logger.info(f"Processing registration from user {user_hash}")
    
    if text.count(":") < 5:
        await update.message.reply_text("❗ ข้อมูลไม่ครบ กรุณากรอกให้ครบทุกช่อง")
        return ASK_INFO
    
    # Parse data WITHOUT logging any sensitive information
    data = {}
    for line in text.strip().splitlines():
        if ':' in line:
            key, value = map(str.strip, line.split(':', 1))
            data[key.lower()] = value
    
    if any(not v for v in data.values()):
        await update.message.reply_text("❗ บางช่องเว้นว่าง กรุณากรอกให้ครบทุกช่อง")
        return ASK_INFO
    
    user = update.message.from_user
    username = user.username or "ไม่มี"
    
    # CRITICAL FIX: Use the exact working group check code
    logger.info(f"Starting group membership check for user {user_hash}")
    
    try:
        # This is the EXACT code from bot_fixed_final.py that works
        member = await context.bot.get_chat_member(chat_id=GROUP_ID, user_id=user_id)
        in_group = member.status in ['member', 'administrator', 'creator']
        
        logger.info(f"Group check SUCCESS for user {user_hash}: {'MEMBER' if in_group else 'NOT_MEMBER'}")
        
    except Exception as e:
        logger.error(f"Group check FAILED for user {user_hash}: {type(e).__name__}")
        in_group = False
    
    status_text = "✅ อยู่ในกลุ่มแล้ว" if in_group else "❌ ยังไม่ได้เข้ากลุ่ม"
    logger.info(f"Final status for user {user_hash}: {status_text}")
    
    import pytz
    bangkok_tz = pytz.timezone('Asia/Bangkok')
    now = datetime.now(bangkok_tz).strftime("%Y-%m-%d %H:%M:%S")
    
    # Prepare data for sheet (NO LOGGING OF ACTUAL DATA)
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
    
    # Save to sheet (NO sensitive data in logs)
    saved = False
    sheet = sheet_manager.get_sheet()
    if sheet:
        try:
            sheet.append_row(user_data)
            saved = True
            logger.info(f"Data saved successfully for user {user_hash}")
        except Exception as e:
            logger.error(f"Save failed for user {user_hash}: {type(e).__name__}")
    
    if not saved:
        pending_saves.append(user_data)
        logger.warning(f"Added to pending queue: user {user_hash}")
    
    # House selection buttons
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
    
    # Get first name only (safe)
    first_name = data.get('ชื่อ - นามสกุล', 'ผู้ใช้').split()[0] if data.get('ชื่อ - นามสกุล') else 'ผู้ใช้'
    
    confirm_message = (
        f"✅ ขอบคุณ {first_name} สำหรับการยืนยันตัวตน\n\n"
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
    
    # Clean up memory
    gc.collect()
    log_memory_usage("after_save")
    logger.info(f"Registration completed for user {user_hash}")
    
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_hash = create_user_hash(update.message.from_user.id)
    logger.info(f"Registration cancelled by user {user_hash}")
    await update.message.reply_text("❌ ยกเลิกการลงทะเบียน")
    return ConversationHandler.END

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    # Only log error type, never details
    error_type = type(context.error).__name__
    logger.error(f"Bot error occurred: {error_type}")

# ====== Flask App ======
flask_app = Flask(__name__)
CORS(flask_app)

@flask_app.route("/")
def home():
    return "ZOMBIE Bot v2.0 - Privacy Protected ✅"

@flask_app.route("/health")
def health_check():
    memory_mb = log_memory_usage("health")
    return {
        "status": "healthy" if memory_mb < 1500 else "warning",
        "memory_mb": round(memory_mb, 2),
        "pending": len(pending_saves),
        "failed": len(failed_saves),
        "timestamp": datetime.now().isoformat()
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
        user_hash = create_user_hash(uid) if uid else "unknown"
        logger.info(f"House selection: {user_hash} chose {house}")
        return redirect(LINKS[house], 302)
    
    logger.warning(f"Invalid house request: {house}")
    return "Invalid request", 400

# ====== Background Tasks ======
def retry_failed_saves():
    """Background task to retry failed saves"""
    while True:
        try:
            if pending_saves:
                sheet = sheet_manager.get_sheet()
                if sheet:
                    retry_count = min(3, len(pending_saves))
                    for _ in range(retry_count):
                        if pending_saves:
                            user_data = pending_saves.popleft()
                            try:
                                sheet.append_row(user_data)
                                logger.info("Retry save successful")
                            except Exception as e:
                                failed_saves.append(user_data)
                                logger.error(f"Retry save failed: {type(e).__name__}")
            
            time.sleep(30)
            
        except Exception as e:
            logger.error(f"Background task error: {type(e).__name__}")
            time.sleep(60)

# ====== Main ======
def main():
    # Start background task
    retry_thread = Thread(target=retry_failed_saves, daemon=True)
    retry_thread.start()
    
    # Start Flask
    logger.info("Starting Flask server on port 10000...")
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
    
    time.sleep(2)
    
    # Initialize bot
    token = os.getenv("BOT_TOKEN")
    if not token:
        raise ValueError("No BOT_TOKEN in environment")
    
    try:
        app = (
            ApplicationBuilder()
            .token(token)
            .connection_pool_size(8)
            .pool_timeout(30.0)
            .read_timeout(15.0)
            .write_timeout(15.0)
            .concurrent_updates(100)
            .build()
        )
        
        app.add_error_handler(error_handler)
        
        conv_handler = ConversationHandler(
            entry_points=[CommandHandler("start", start)],
            states={ASK_INFO: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_info)]},
            fallbacks=[CommandHandler("cancel", cancel)]
        )
        app.add_handler(conv_handler)
        
        log_memory_usage("startup")
        
        logger.info("=== ZOMBIE Bot v2.0 Starting ===")
        logger.info("PRIVACY: Maximum protection enabled")
        logger.info("GROUP_CHECK: Fixed with working code")
        logger.info("RATE_LIMIT: 3 requests/minute per user")
        logger.info("PERFORMANCE: Optimized for 400+ users")
        logger.info("Health check: /health")
        
        # Run bot with drop_pending_updates to clear webhook conflicts
        logger.info("🤖 Starting bot with polling...")
        app.run_polling(
            drop_pending_updates=True,  # This will clear webhook automatically
            allowed_updates=Update.ALL_TYPES
        )
        
    except Conflict as e:
        logger.error(f"Bot conflict detected: {type(e).__name__}")
        time.sleep(30)
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Fatal error: {type(e).__name__}")
    finally:
        logger.info("Bot shutdown complete")

if __name__ == "__main__":
    main()