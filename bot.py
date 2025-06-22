import os
import json
import base64
from datetime import datetime
from threading import Thread
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
from googleapiclient.errors import HttpError

# ====== Logging Setup ======
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ====== Graceful Shutdown Handler ======
class GracefulShutdown:
    shutdown = False
    
    @classmethod
    def signal_handler(cls, sig, frame):
        logger.info('Graceful shutdown initiated...')
        cls.shutdown = True
        sys.exit(0)

# Register signal handlers
signal.signal(signal.SIGINT, GracefulShutdown.signal_handler)
signal.signal(signal.SIGTERM, GracefulShutdown.signal_handler)

# ====== Google Sheet Setup ======
def get_google_sheet():
    """สร้าง connection ใหม่ทุกครั้ง"""
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
        logger.error(f"Google Sheets connection error: {e}")
        return None

# ====== Bot Config ======
ASK_INFO = range(1)
GROUP_ID = -1002561643127

# Global storage for pending saves
pending_saves = []
failed_saves = []

def build_redirect_url(house_key, user_id):
    return f"https://zombie-event-telegram-bot.onrender.com/go?house={house_key}&uid={user_id}"

def safe_append_row(data, max_retries=3):
    """บันทึกข้อมูลพร้อม retry ถ้าเกิด error"""
    for attempt in range(max_retries):
        try:
            sheet = get_google_sheet()
            if sheet:
                sheet.append_row(data)
                logger.info(f"✅ บันทึกข้อมูลสำเร็จ")
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

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
    
    try:
        await update.message.reply_text(welcome_message, reply_markup=reply_markup)
    except Exception as e:
        logger.error(f"Error in start: {e}")
    
    return ASK_INFO

async def get_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    data = {}

    if text.count(":") < 5:
        await update.message.reply_text("❗ ข้อมูลไม่ครบหรือไม่ถูกต้อง กรุณากรอกให้ครบทุกช่องตามตัวอย่าง")
        return ASK_INFO

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
    
    # ใช้เวลา Bangkok timezone
    import pytz
    bangkok_tz = pytz.timezone('Asia/Bangkok')
    now = datetime.now(bangkok_tz).strftime("%Y-%m-%d %H:%M:%S")

    house_keys = [
        ("💀 ZOMBIE XO", "ZOMBIE_XO"),
        ("👾 ZOMBIE PG", "ZOMBIE_PG"),
        ("👑 ZOMBIE KING", "ZOMBIE_KING"),
        ("🧟 ZOMBIE ALL", "ZOMBIE_ALL"),
        ("🐢 GENBU88", "GENBU88")
    ]

    confirm_message = (
        f"✅ ขอบคุณ 🙏🏻 {data.get('ชื่อ - นามสกุล', 'ผู้ใช้')} สำหรับการยืนยันตัวตน \n\n"
        f"สถานะ: {status_text}\n"
        "👑 *ขั้นตอนถัดไป:* \n"
        "1️⃣ แคปหน้าจอข้อความนี้ \n"
        "2️⃣ แอดไลน์เพื่อแจ้งแอดมิน ติดต่อรับเครดิตฟรี \n\n"
        "⚠️ *สิทธิเครดิตฟรีจะได้รับเฉพาะผู้ที่ทำตามขั้นตอนครบเท่านั้น*"
    )

    keyboard = [
        [InlineKeyboardButton(text, url=build_redirect_url(house_key, user_id))
         for text, house_key in house_keys[:2]],
        [InlineKeyboardButton(text, url=build_redirect_url(house_key, user_id))
         for text, house_key in house_keys[2:4]],
        [InlineKeyboardButton(house_keys[4][0], url=build_redirect_url(house_keys[4][1], user_id))]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    # เตรียมข้อมูลสำหรับบันทึก
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
    
    # เพิ่มใน pending list ก่อน
    pending_saves.append(user_data)
    
    # พยายามบันทึก
    success = safe_append_row(user_data)
    
    # ถ้าสำเร็จ ลบออกจาก pending
    if success and user_data in pending_saves:
        pending_saves.remove(user_data)
    
    # แจ้งเตือนถ้ามีข้อมูลค้าง
    if len(pending_saves) > 0:
        logger.info(f"⚠️ มีข้อมูลรอบันทึก {len(pending_saves)} รายการ")

    try:
        await update.message.reply_text(confirm_message, parse_mode="Markdown", reply_markup=reply_markup)
    except Exception as e:
        logger.error(f"Error sending confirm message: {e}")
    
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ ยกเลิกการยืนยันตัวตนแล้ว")
    return ConversationHandler.END

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle errors"""
    logger.error(f"Exception while handling an update: {context.error}")

# ====== Flask App ======
flask_app = Flask(__name__)
CORS(flask_app)

@flask_app.route("/")
def home():
    return "🤖 Zombie Event Bot is running! ✅"

@flask_app.route("/health")
def health_check():
    """Health check endpoint"""
    import pytz
    import psutil
    
    bangkok_tz = pytz.timezone('Asia/Bangkok')
    current_time = datetime.now(bangkok_tz).strftime("%Y-%m-%d %H:%M:%S")
    
    # Memory check
    process = psutil.Process()
    memory_mb = process.memory_info().rss / 1024 / 1024
    
    health_status = "healthy"
    if len(pending_saves) > 10:
        health_status = "warning"
    if len(failed_saves) > 5:
        health_status = "critical"
    
    return {
        "status": health_status,
        "bot": "zombie-event-telegram-bot",
        "time": current_time,
        "memory_mb": round(memory_mb, 2),
        "pending_saves": len(pending_saves),
        "failed_saves": len(failed_saves),
        "message": f"Bot is running! Pending: {len(pending_saves)}, Failed: {len(failed_saves)}"
    }

@flask_app.route("/go")
def go():
    """Route สำหรับ redirect และเก็บ log การคลิก"""
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
    
    # บันทึกข้อมูลการคลิกลง Google Sheet
    import pytz
    bangkok_tz = pytz.timezone('Asia/Bangkok')
    now = datetime.now(bangkok_tz).strftime("%Y-%m-%d %H:%M:%S")
    
    try:
        sheet = get_google_sheet()
        if sheet:
            # ค้นหา user_id ทั้งหมดใน sheet
            all_cells = sheet.findall(str(uid))
            if all_cells:
                # หาแถวล่าสุด
                last_cell = all_cells[-1]
                last_row = last_cell.row
                logger.info(f"✅ พบ user_id {uid} ที่แถว {last_row}")
                
                # อัพเดทข้อมูล
                try:
                    current_house = sheet.cell(last_row, 12).value
                    if current_house == "PENDING":
                        sheet.update_cell(last_row, 12, house)
                        logger.info(f"🏠 อัพเดทบ้านที่รับเครดิตฟรี: {house}")
                except Exception as e:
                    logger.error(f"Error updating: {e}")
    except Exception as e:
        logger.error(f"❌ Error in go route: {e}")
    
    logger.info(f"↗️ Redirect {uid} ไปยัง {house}: {link}")
    return redirect(link, code=302)

# ====== Main function ======
if __name__ == "__main__":
    # Initialize bot
    bot_token = os.getenv("BOT_TOKEN")
    if not bot_token:
        raise ValueError("Environment variable BOT_TOKEN not found")

    # Create application with conflict handling
    app = ApplicationBuilder().token(bot_token).build()
    
    # Add error handler
    app.add_error_handler(error_handler)

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={ASK_INFO: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_info)]},
        fallbacks=[CommandHandler("cancel", cancel)]
    )
    app.add_handler(conv_handler)

    # Start Flask in a separate thread
    flask_thread = Thread(target=lambda: flask_app.run(host="0.0.0.0", port=10000))
    flask_thread.daemon = True
    flask_thread.start()

    # Start bot with proper error handling
    logger.info("🤖 Bot is starting...")
    logger.info("🌐 Health check available at: /health")
    logger.info("🔗 Redirect handler available at: /go")
    
    try:
        # Use drop_pending_updates to clear old updates
        app.run_polling(
            drop_pending_updates=True,
            allowed_updates=Update.ALL_TYPES,
            close_loop=False
        )
    except Conflict:
        logger.error("❌ Another instance is already running!")
        logger.info("💡 Please stop other instances or wait a moment")
    except Exception as e:
        logger.error(f"❌ Bot error: {e}")
    finally:
        logger.info("Bot stopped")