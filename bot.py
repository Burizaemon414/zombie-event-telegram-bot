from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
    ConversationHandler
)
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import re
from datetime import datetime
import os
import json
import base64

# ====== Google Sheet Setup ======
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]

# ตรวจสอบว่าใช้ environment variable หรือไฟล์
creds_b64 = os.getenv("GOOGLE_CREDS_JSON")
if creds_b64:
    # ถ้ามี environment variable (สำหรับ Render)
    creds_json_str = base64.b64decode(creds_b64).decode("utf-8")
    credentials_info = json.loads(creds_json_str)
else:
    # ถ้าไม่มี ให้อ่านจากไฟล์ (สำหรับ local testing)
    try:
        with open('GOOGLE_CREDS_JSON.json', 'r') as f:
            credentials_info = json.load(f)
    except FileNotFoundError:
        raise ValueError("ไม่พบ GOOGLE_CREDS_JSON ทั้งใน environment variable และไฟล์")

creds = ServiceAccountCredentials.from_json_keyfile_dict(credentials_info, scope)
client = gspread.authorize(creds)
sheet = client.open("เครดิตฟรี กลุ่ม กิจกรรม ZOMBIE").sheet1

# ====== Bot Config ======
ASK_INFO = range(1)
GROUP_ID = -1002561643127

# ดึง BOT_TOKEN จาก environment variable หรือใช้ค่า default
BOT_TOKEN = os.getenv("BOT_TOKEN", "8137922853:AAFEuJXVf_REm2tSF7kkruVVBEQaj87PU-Y")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    welcome_message = (
        "🎉 ยินดีต้อนรับเข้าสู่ระบบยืนยันตัวตน ZOMBIE SLOT - กิจกรรม\n\n"
        "📌 กรุณาก๊อปข้อความด้านล่างนี้แล้วเติมข้อมูลให้ครบทุกช่อง:\n\n"
        "ชื่อ - นามสกุล : \n"
        "เบอร์โทร : \n"
        "ธนาคาร : \n"
        "เลขบัญชี : \n"
        "อีเมล : \n"
        "ชื่อเทเลแกรม : \n"
        "@username Telegram : "
    )
    keyboard = [[KeyboardButton("เริ่มต้นส่งข้อมูล ✅")]]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    await update.message.reply_text(welcome_message, reply_markup=reply_markup)
    return ASK_INFO

async def get_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    
    # ถ้ากดปุ่ม "เริ่มต้นส่งข้อมูล ✅" ให้แสดงฟอร์มอีกครั้ง
    if text == "เริ่มต้นส่งข้อมูล ✅":
        await update.message.reply_text(
            "📝 กรุณาคัดลอกฟอร์มด้านล่างและเติมข้อมูลให้ครบ:\n\n"
            "ชื่อ - นามสกุล : \n"
            "เบอร์โทร : \n"
            "ธนาคาร : \n"
            "เลขบัญชี : \n"
            "อีเมล : \n"
            "ชื่อเทเลแกรม : \n"
            "@username Telegram : "
        )
        return ASK_INFO
    
    data = {}
    for line in text.strip().splitlines():
        if ':' in line:
            key, value = map(str.strip, line.split(':', 1))
            data[key.lower()] = value

    # ตรวจสอบว่าข้อมูลครบหรือไม่
    required_fields = [
        "ชื่อ - นามสกุล",
        "เบอร์โทร",
        "ธนาคาร",
        "เลขบัญชี",
        "อีเมล",
        "ชื่อเทเลแกรม",
        "@username telegram"
    ]
    
    missing_fields = []
    for field in required_fields:
        if not data.get(field.lower(), "").strip():
            missing_fields.append(field)
    
    if missing_fields:
        await update.message.reply_text(
            f"❗ ข้อมูลยังไม่ครบ กรุณาเติมข้อมูลในช่องต่อไปนี้:\n"
            f"{', '.join(missing_fields)}\n\n"
            "กรุณาคัดลอกฟอร์มตัวอย่างและเติมข้อมูลให้ครบทุกช่อง"
        )
        return ASK_INFO

    user = update.message.from_user
    user_id = user.id
    username = user.username or "ไม่มี"

    # ตรวจสอบสถานะการเข้ากลุ่ม
    try:
        member = await context.bot.get_chat_member(chat_id=GROUP_ID, user_id=user_id)
        in_group = member.status in ['member', 'administrator', 'creator']
    except Exception as e:
        print(f"Error checking group membership: {e}")
        in_group = False

    status_text = "✅ อยู่ในกลุ่มแล้ว" if in_group else "❌ ยังไม่ได้เข้ากลุ่ม"
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # บันทึกข้อมูลลง Google Sheets
    try:
        sheet.append_row([
            data.get("ชื่อ - นามสกุล", ""),
            data.get("เบอร์โทร", ""),
            data.get("ธนาคาร", ""),
            data.get("เลขบัญชี", ""),
            data.get("อีเมล", ""),
            data.get("ชื่อเทเลแกรม", ""),
            data.get("@username telegram", ""),
            f"@{username}" if username != "ไม่มี" else "ไม่มี",
            str(user_id),
            status_text,
            now
        ])
        print(f"✅ บันทึกข้อมูลของ {user_id} สำเร็จ")
    except Exception as e:
        print(f"❌ Error saving to Google Sheets: {e}")
        await update.message.reply_text(
            "❌ เกิดข้อผิดพลาดในการบันทึกข้อมูล\n"
            "กรุณาลองใหม่อีกครั้งหรือติดต่อแอดมิน"
        )
        return ConversationHandler.END

    confirm_message = (
        f"✅ ขอบคุณ 🙏🏻 {data.get('ชื่อ - นามสกุล', 'ผู้ใช้')} สำหรับการยืนยันตัวตน \n"
        f"สถานะ: {status_text}\n\n"
        "👑 *ขั้นตอนถัดไป:*\n"
        "1️⃣ แคปหน้าจอข้อความนี้\n"
        "2️⃣ แอดไลน์เพื่อแจ้งแอดมิน\n"
        "⚠️ *สิทธิเครดิตฟรีจะได้รับเฉพาะผู้ที่ทำตามขั้นตอนครบเท่านั้น*"
    )

    keyboard = [
        [InlineKeyboardButton("💀 ZOMBIE XO", url="https://lin.ee/SgguCbJ"),
         InlineKeyboardButton("👾 ZOMBIE PG", url="https://lin.ee/ETELgrN")],
        [InlineKeyboardButton("👑 ZOMBIE KING", url="https://lin.ee/fJilKIf"),
         InlineKeyboardButton("🧟 ZOMBIE ALL", url="https://lin.ee/9eogsb8e")],
        [InlineKeyboardButton("🐢 GENBU88", url="https://lin.ee/JCCXt06")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(confirm_message, parse_mode="Markdown", reply_markup=reply_markup)
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ ยกเลิกการยืนยันตัวตนแล้ว")
    return ConversationHandler.END

# ====== Error Handler ======
async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print(f"❌ Error: {context.error}")
    if update and update.effective_message:
        await update.effective_message.reply_text(
            "❌ เกิดข้อผิดพลาด กรุณาลองใหม่อีกครั้ง\n"
            "หากยังมีปัญหา กรุณาติดต่อแอดมิน"
        )

# ====== Run Bot ======
if __name__ == '__main__':
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            ASK_INFO: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_info)]
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    
    app.add_handler(conv_handler)
    app.add_error_handler(error_handler)
    
    print("🤖 บอทเริ่มทำงานแล้ว...")
    print(f"📱 Bot Token: {BOT_TOKEN[:10]}...")
    print(f"📊 Google Sheet: เครดิตฟรี กลุ่ม กิจกรรม ZOMBIE")
    
    # ตรวจสอบการเชื่อมต่อ Google Sheets
    try:
        test = sheet.get('A1')
        print("✅ เชื่อมต่อ Google Sheets สำเร็จ")
    except Exception as e:
        print(f"❌ ไม่สามารถเชื่อมต่อ Google Sheets: {e}")
    
    app.run_polling()