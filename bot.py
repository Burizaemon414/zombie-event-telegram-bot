import os
import json
import base64
from datetime import datetime
from threading import Thread
from flask import Flask, request, redirect
import time
import logging
import signal
import sys
import pytz

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

# ====== Logging Setup ======
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Reduce telegram library logs
logging.getLogger("telegram").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)

# ====== Graceful Shutdown Handler ======
class GracefulShutdown:
    shutdown = False
    
    @classmethod
    def signal_handler(cls, sig, frame):
        logger.info('🛑 Graceful shutdown initiated...')
        cls.shutdown = True
        sys.exit(0)

# Register signal handlers
signal.signal(signal.SIGINT, GracefulShutdown.signal_handler)
signal.signal(signal.SIGTERM, GracefulShutdown.signal_handler)

# ====== Bot Config ======
ASK_INFO = range(1)
BOT_TOKEN = os.getenv("BOT_TOKEN")
TELEGRAM_GROUP_ID = os.getenv("TELEGRAM_GROUP_ID")

if not BOT_TOKEN:
    raise ValueError("No BOT_TOKEN in environment")

if not TELEGRAM_GROUP_ID:
    logger.warning("⚠️ No TELEGRAM_GROUP_ID in environment - group checking disabled")

# Global storage for pending saves
pending_saves = []
failed_saves = []

# ====== Google Sheet Setup ======
def get_google_sheet():
    """สร้าง connection ใหม่ทุกครั้ง - เสถียรกว่า"""
    try:
        scope = [
            "https://spreadsheets.google.com/feeds",
            "https://www.googleapis.com/auth/drive"
        ]
        creds_b64 = os.getenv("GOOGLE_CREDS_JSON")
        if not creds_b64:
            raise ValueError("Environment variable GOOGLE_CREDS_JSON not found")

        creds_json_str = base64.b64decode(creds_b64).decode("utf-8")
        credentials_info = json.loads(creds_json_str)
        creds = ServiceAccountCredentials.from_json_keyfile_dict(credentials_info, scope)
        client = gspread.authorize(creds)
        sheet = client.open("เครดิตฟรี กลุ่ม กิจกรรม ZOMBIE").worksheet("ข้อมูลลูกค้า")
        return sheet
    except Exception as e:
        logger.error(f"❌ Google Sheets connection error: {e}")
        return None

def safe_append_row(data, max_retries=3):
    """บันทึกข้อมูลพร้อม retry และ backup ถ้าเกิด error"""
    for attempt in range(max_retries):
        try:
            sheet = get_google_sheet()
            if sheet:
                sheet.append_row(data)
                logger.info(f"✅ บันทึกข้อมูลสำเร็จ (attempt {attempt + 1})")
                return True
        except Exception as e:
            if hasattr(e, 'resp') and e.resp.status == 429:
                wait_time = (attempt + 1) * 5
                logger.warning(f"⏳ Rate limit! รอ {wait_time} วินาที...")
                time.sleep(wait_time)
            else:
                logger.error(f"❌ Error attempt {attempt + 1}: {e}")
                if attempt == max_retries - 1:
                    # บันทึก backup
                    backup_data = {
                        "timestamp": datetime.now().isoformat(),
                        "data": data,
                        "error": str(e)
                    }
                    failed_saves.append(backup_data)
                    
                    # บันทึกลงไฟล์
                    try:
                        with open("backup_failed_saves.json", "a", encoding='utf-8') as f:
                            json.dump(backup_data, f, ensure_ascii=False)
                            f.write("\n")
                        logger.info("💾 บันทึกไว้ใน backup file")
                    except:
                        pass
        
        time.sleep(1)
    
    return False

def update_house_selection(user_id, house):
    """อัพเดทการเลือกบ้านใน Google Sheet"""
    try:
        sheet = get_google_sheet()
        if not sheet:
            return False
        
        # หา user_id ใน sheet
        all_cells = sheet.findall(str(user_id))
        if not all_cells:
            logger.warning(f"⚠️ User {user_id} not found in sheet")
            return False
        
        # หาแถวล่าสุดของ user นี้
        user_rows = []
        for cell in all_cells:
            # เช็คว่าเป็น column User ID (column I = 9)
            if cell.col == 9:
                user_rows.append(cell.row)
        
        if not user_rows:
            logger.warning(f"⚠️ No valid user rows found for {user_id}")
            return False
        
        # เอาแถวล่าสุด
        last_row = max(user_rows)
        logger.info(f"📋 Found user {user_id} at row {last_row}")
        
        # เช็คสถานะปัจจุบัน
        current_status = sheet.cell(last_row, 12).value  # Column L - บ้านที่รับเครดิตฟรี
        current_history = sheet.cell(last_row, 13).value or ""  # Column M - บ้านที่รับไปแล้ว
        
        bangkok_tz = pytz.timezone('Asia/Bangkok')
        now = datetime.now(bangkok_tz).strftime("%Y-%m-%d %H:%M:%S")
        
        if current_status == "PENDING":
            # ครั้งแรก - อัพเดท status และไม่เปลี่ยน timestamp
            sheet.update_cell(last_row, 12, house)  # บ้านที่รับเครดิตฟรี
            sheet.update_cell(last_row, 13, house)  # บ้านที่รับไปแล้ว
            logger.info(f"✅ Updated PENDING to {house} for user {user_id}")
            
        else:
            # ไม่ใช่ครั้งแรก - สร้าง row ใหม่
            # ดึงข้อมูลเดิม
            row_data = sheet.row_values(last_row)
            
            # สร้างประวัติบ้านที่เคยไป
            existing_houses = current_history.split(',') if current_history else []
            if current_status and current_status != 'PENDING':
                if current_status not in existing_houses:
                    existing_houses.append(current_status)
            existing_houses.append(house)
            
            # สร้าง row ใหม่
            new_row = row_data[:11]  # เอาข้อมูลถึง column K (วันที่)
            new_row[10] = now  # อัพเดทเวลาใหม่
            new_row.append(house)  # บ้านที่รับเครดิตฟรี (column L)
            new_row.append(','.join(existing_houses))  # บ้านที่รับไปแล้ว (column M)
            
            sheet.append_row(new_row)
            logger.info(f"✅ Created new row for user {user_id}: {house}")
            logger.info(f"📊 House history: {','.join(existing_houses)}")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Error updating house selection: {e}")
        return False

# ====== Group Membership Checking ======
async def check_user_in_telegram_group(user_id: int) -> str:
    """Check if user is in Telegram group"""
    try:
        if not TELEGRAM_GROUP_ID:
            return "ไม่ทราบ"
        
        # Create a temporary bot instance for checking
        from telegram import Bot
        bot = Bot(token=BOT_TOKEN)
        
        # Get chat member status
        chat_member = await bot.get_chat_member(chat_id=TELEGRAM_GROUP_ID, user_id=user_id)
        
        if chat_member.status in ['member', 'administrator', 'creator']:
            logger.info(f"✅ User {user_id} is in group: {chat_member.status}")
            return "เข้าแล้ว"
        elif chat_member.status in ['left', 'kicked']:
            logger.info(f"❌ User {user_id} not in group: {chat_member.status}")
            return "ยังไม่เข้า"
        else:
            logger.info(f"❓ User {user_id} unknown status: {chat_member.status}")
            return "ไม่ทราบ"
            
    except Exception as e:
        if "user not found" in str(e).lower():
            logger.info(f"❌ User {user_id} not found in group")
            return "ยังไม่เข้า"
        else:
            logger.error(f"❌ Error checking group membership: {e}")
            return "ไม่ทราบ"

def check_user_in_group_sync(user_id: int) -> str:
    """Synchronous wrapper for group checking"""
    try:
        import asyncio
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        result = loop.run_until_complete(check_user_in_telegram_group(user_id))
        loop.close()
        return result
    except Exception as e:
        logger.error(f"❌ Error in sync group check: {e}")
        return "ไม่ทราบ"

# ====== Bot Handlers ======
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command"""
    welcome_message = (
        "🎉 ยินดีต้อนรับเข้าสู่ระบบยืนยันตัวตน ZOMBIE SLOT - กิจกรรม\n\n"
        "📌 กรุณาก๊อปข้อความด้านล่างแล้วกรอกข้อมูล:\n\n"
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
    
    try:
        await update.message.reply_text(welcome_message, reply_markup=reply_markup)
        logger.info(f"🚀 /start command from user {update.effective_user.id}")
    except Exception as e:
        logger.error(f"❌ Error in start: {e}")
    
    return ASK_INFO

async def get_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle user information input"""
    text = update.message.text
    user = update.message.from_user
    
    logger.info(f"📝 Processing info from user {user.id}")
    
    # Skip if it's just the button text
    if text == "เริ่มต้นส่งข้อมูล ✅":
        await update.message.reply_text(
            "กรุณากรอกข้อมูลตามรูปแบบที่กำหนด:\n\n"
            "ชื่อ - นามสกุล : ชื่อของคุณ\n"
            "เบอร์โทร : เบอร์ของคุณ\n"
            "ธนาคาร : ธนาคารของคุณ\n"
            "เลขบัญชี : เลขบัญชีของคุณ\n"
            "อีเมล : อีเมลของคุณ\n"
            "ชื่อเทเลแกรม : ชื่อเทเลแกรมของคุณ\n"
            "@username Telegram : @username ของคุณ"
        )
        return ASK_INFO
    
    # Validate format
    if text.count(":") < 5:
        await update.message.reply_text("❗ ข้อมูลไม่ครบหรือไม่ถูกต้อง กรุณากรอกให้ครับทุกช่องตามตัวอย่าง")
        return ASK_INFO

    # Parse data with flexible field names
    data = {}
    for line in text.strip().splitlines():
        if ':' in line:
            key, value = map(str.strip, line.split(':', 1))
            
            # Normalize field names
            key_lower = key.lower().replace(" ", "").replace("-", "")
            
            if "ชื่อ" in key and ("นามสกุล" in key or "surname" in key.lower()):
                data["ชื่อ - นามสกุล"] = value
            elif "เบอร์" in key or "phone" in key.lower() or "tel" in key.lower():
                data["เบอร์โทร"] = value
            elif "ธนาคาร" in key or "bank" in key.lower():
                data["ธนาคาร"] = value
            elif "เลข" in key and "บัญชี" in key:
                data["เลขบัญชี"] = value
            elif "อีเมล" in key or "email" in key.lower():
                data["อีเมล"] = value
            elif "ชื่อ" in key and ("เทเลแกรม" in key or "telegram" in key.lower()) and "@" not in key:
                data["ชื่อเทเลแกรม"] = value
            elif "@" in key and ("username" in key.lower() or "telegram" in key):
                data["@username telegram"] = value

    logger.info(f"📊 Parsed data from user {user.id}:")
    for k, v in data.items():
        logger.info(f"  {k}: '{v}'")

    # Check for required fields
    required_fields = ["ชื่อ - นามสกุล", "เบอร์โทร", "ธนาคาร", "เลขบัญชี", "อีเมล", "ชื่อเทเลแกรม", "@username telegram"]
    missing_fields = [field for field in required_fields if not data.get(field)]
    
    if missing_fields:
        await update.message.reply_text(
            f"❗ ข้อมูลไม่ครบ กรุณากรอกให้ครบทุกช่อง\nข้อมูลที่ขาด: {', '.join(missing_fields)}"
        )
        logger.info(f"⚠️ Missing fields from user {user.id}: {missing_fields}")
        return ASK_INFO

    # Check group membership
    group_status = check_user_in_group_sync(user.id)
    logger.info(f"👥 Group status for user {user.id}: {group_status}")
    
    # Prepare data for Google Sheets
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
        group_status,
        now,
        "PENDING",
        ""
    ]
    
    # Add to pending list
    pending_saves.append(user_data)
    
    # Try to save
    success = safe_append_row(user_data)
    
    # Remove from pending if successful
    if success and user_data in pending_saves:
        pending_saves.remove(user_data)
    
    # Create house selection buttons
    house_keys = [
        ("💀 ZOMBIE XO", "ZOMBIE_XO"),
        ("👾 ZOMBIE PG", "ZOMBIE_PG"),
        ("👑 ZOMBIE KING", "ZOMBIE_KING"),
        ("🧟 ZOMBIE ALL", "ZOMBIE_ALL"),
        ("🐢 GENBU88", "GENBU88")
    ]
    
    confirm_message = (
        f"✅ ขอบคุณ 🙏🏻 {data.get('ชื่อ - นามสกุล', 'คุณ')} สำหรับการยืนยันตัวตน\n\n"
        f"สถานะ: {group_status}\n"
        "👑 ขั้นตอนถัดไป:\n"
        "1️⃣ แคปหน้าจอข้อความนี้\n"
        "2️⃣ แอดไลน์เพื่อแจ้งแอดมิน ติดต่อรับเครดิตฟรี\n\n"
        "⚠️ สิทธิเครดิตฟรีจะได้รับเฉพาะผู้ที่ทำตามขั้นตอนครบเท่านั้น"
    )
    
    # Create keyboard
    keyboard = []
    for i in range(0, len(house_keys), 2):
        row = []
        for text, house_key in house_keys[i:i+2]:
            url = f"https://zombie-event-telegram-bot.onrender.com/go?house={house_key}&uid={user.id}"
            row.append(InlineKeyboardButton(text, url=url))
        keyboard.append(row)
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    try:
        await update.message.reply_text(confirm_message, reply_markup=reply_markup)
        logger.info(f"✅ Confirmation sent to user {user.id}")
    except Exception as e:
        logger.error(f"❌ Error sending confirmation: {e}")
    
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle cancel command"""
    await update.message.reply_text("❌ ยกเลิกการยืนยันตัวตนแล้ว")
    return ConversationHandler.END

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle errors"""
    logger.error(f"❌ Exception while handling an update: {context.error}")

# ====== Flask App ======
flask_app = Flask(__name__)

@flask_app.route("/")
def home():
    return "🤖 Zombie Event Bot is running! ✅ (Improved Polling Mode)"

@flask_app.route("/health")
def health_check():
    """Health check endpoint"""
    bangkok_tz = pytz.timezone('Asia/Bangkok')
    current_time = datetime.now(bangkok_tz).strftime("%Y-%m-%d %H:%M:%S")
    
    # Memory check with fallback
    memory_mb = 0
    try:
        import psutil
        process = psutil.Process()
        memory_mb = process.memory_info().rss / 1024 / 1024
    except ImportError:
        logger.warning("⚠️ psutil not available - memory monitoring disabled")
        memory_mb = 0
    except Exception as e:
        logger.error(f"❌ Memory check error: {e}")
        memory_mb = 0
    
    health_status = "healthy"
    if len(pending_saves) > 10:
        health_status = "warning"
    if len(failed_saves) > 5:
        health_status = "critical"
    
    return {
        "status": health_status,
        "bot": "zombie-event-telegram-bot",
        "mode": "polling_improved",
        "time": current_time,
        "memory_mb": round(memory_mb, 2),
        "pending_saves": len(pending_saves),
        "failed_saves": len(failed_saves),
        "group_checking": bool(TELEGRAM_GROUP_ID),
        "message": f"Bot running! Pending: {len(pending_saves)}, Failed: {len(failed_saves)}"
    }

@flask_app.route("/go")
def go():
    """Route สำหรับ redirect และอัพเดท Google Sheet"""
    LINE_HOUSE_LINKS = {
        "ZOMBIE_XO": "https://lin.ee/SgguCbJ",
        "ZOMBIE_PG": "https://lin.ee/ETELgrN",
        "ZOMBIE_KING": "https://lin.ee/fJilKIf",
        "ZOMBIE_ALL": "https://lin.ee/9eogsb8e",
        "GENBU88": "https://lin.ee/JCCXt06"
    }
    
    house = request.args.get("house", "").upper()
    uid = request.args.get("uid")
    
    if not house or not uid:
        return "Missing parameters", 400
    
    link = LINE_HOUSE_LINKS.get(house)
    if not link:
        return f"Unknown house: {house}", 400
    
    # อัพเดทการเลือกบ้าน
    update_house_selection(uid, house)
    
    logger.info(f"🔗 Redirect user {uid} to {house}: {link}")
    return redirect(link, code=302)

# ====== Main Function ======
if __name__ == "__main__":
    # Create application
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    
    # Add error handler
    app.add_error_handler(error_handler)

    # Create conversation handler
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={ASK_INFO: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_info)]},
        fallbacks=[CommandHandler("cancel", cancel)]
    )
    app.add_handler(conv_handler)

    # Start Flask in a separate thread
    flask_thread = Thread(target=lambda: flask_app.run(host="0.0.0.0", port=10000, debug=False))
    flask_thread.daemon = True
    flask_thread.start()
    
    logger.info("🤖 Starting Zombie Event Telegram Bot (Improved Polling Mode)...")
    logger.info("🌐 Health check: /health")
    logger.info("🔗 Redirect handler: /go")
    logger.info(f"👥 Group checking: {'Enabled' if TELEGRAM_GROUP_ID else 'Disabled'}")
    
    try:
        # Start polling with proper error handling
        app.run_polling(
            drop_pending_updates=True,
            allowed_updates=Update.ALL_TYPES,
            close_loop=False,
            poll_interval=1.0,
            timeout=10
        )
    except Conflict:
        logger.error("❌ Another instance is already running!")
        logger.info("💡 Please stop other instances or wait a moment")
    except Exception as e:
        logger.error(f"❌ Bot error: {e}")
    finally:
        logger.info("🛑 Bot stopped")