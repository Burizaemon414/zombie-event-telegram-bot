
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

# Google Sheet Setup
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
import os

# สร้างไฟล์ credentials.json จาก Environment Variable
if not os.path.exists("credentials.json"):
    with open("credentials.json", "w") as f:
        f.write(os.getenv("GOOGLE_CREDS_JSON"))
creds = ServiceAccountCredentials.from_json_keyfile_name("credentials.json", scope)
client = gspread.authorize(creds)
sheet = client.open("เครดิตฟรี กลุ่ม กิจกรรม ZOMBIE").sheet1

ASK_INFO = range(1)
GROUP_ID = -1002561643127  # กลุ่ม ZOMBIE

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    welcome_message = (
        "🎉 ยินดีต้อนรับเข้าสู่ระบบยืนยันตัวตน ZOMBIE SLOT - กิจกรรม\n\n"
        "📌 กรุณาส่งข้อมูลทั้งหมดในรูปแบบข้อความ เช่น:\n\n"
        "ชื่อ นามสกุล\nเบอร์โทร\nธนาคาร\nเลขบัญชี\nอีเมล\nชื่อเทเลแกรม\n@username"
    )
    keyboard = [[KeyboardButton("เริ่มต้นส่งข้อมูล ✅")]]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    await update.message.reply_text(welcome_message, reply_markup=reply_markup)
    return ASK_INFO

async def get_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    lines = [line.strip() for line in text.strip().splitlines() if line.strip()]

    name = phone = bank = account = email = tg_name = tg_user = ""

    if len(lines) >= 1:
        name = lines[0]

    for line in lines:
        if line.startswith("ชื่อเทเลแกรม"):
            tg_name = line.replace("ชื่อเทเลแกรม", "").strip()
        elif line.startswith("ยูสเซอร์เทเลแกรม"):
            tg_user = line.replace("ยูสเซอร์เทเลแกรม", "").strip()
        elif line.startswith("@") and not tg_user:
            tg_user = line.strip()
        elif line.isdigit() and len(line) >= 9:
            if not phone:
                phone = line
            else:
                account = line
        elif "@" in line:
            match = re.search(r"[\w.-]+@[\w.-]+\.\w+", line)
            if match:
                email = match.group()
        elif any(b in line for b in ["ไทยพาณิชย์", "กสิกร", "กรุงศรี", "กรุงไทย", "ทหารไทย", "ธนาคาร"]):
            bank = line

    # ตรวจสอบว่าครบหรือไม่
    required_fields = [name, phone, bank, account, email, tg_user]
    if any(not field for field in required_fields):
        await update.message.reply_text(
            "❗ ข้อมูลยังไม่ครบหรือรูปแบบไม่ถูกต้อง\n"
            "กรุณาตรวจสอบให้แน่ใจว่าได้กรอกครบทุกบรรทัดตามตัวอย่างที่ระบุไว้\n\n"
            "เช่น:\nชื่อ นามสกุล\nเบอร์โทร\nธนาคาร\nเลขบัญชี\nอีเมล\nชื่อเทเลแกรม\n@username"
        )
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
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Save to Google Sheet
    sheet.append_row([name, phone, bank, account, email, tg_name, tg_user, username, str(user_id), status_text, now])

    confirm_message = (
        f"✅ ขอบคุณ 🙏🏻 {name} สำหรับการยืนยันตัวตน\n"
        f"สถานะ: {status_text}\n\n"
        "👑 *ขั้นตอนถัดไป:*\n"
        "1️⃣ แคปหน้าจอข้อความนี้\n"
        "2️⃣ แอดไลน์เพื่อแจ้งแอดมิน\n"
        "⚠️ *สิทธิเครดิตฟรีจะได้รับเฉพาะผู้ที่ทำตามขั้นตอนครบเท่านั้น*"
    )

    keyboard = [
        [
            InlineKeyboardButton("💀 ZOMBIE XO", url="https://lin.ee/SgguCbJ"),
            InlineKeyboardButton("👾 ZOMBIE PG", url="https://lin.ee/ETELgrN")
        ],
        [
            InlineKeyboardButton("👑 ZOMBIE KING", url="https://lin.ee/fJilKIf"),
            InlineKeyboardButton("🧟 ZOMBIE ALL", url="https://lin.ee/9eogsb8e")
        ],
        [
            InlineKeyboardButton("🐢 GENBU88", url="https://lin.ee/JCCXt06")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(confirm_message, parse_mode="Markdown", reply_markup=reply_markup)
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ ยกเลิกการยืนยันตัวตนแล้ว")
    return ConversationHandler.END

# Build Application
app = ApplicationBuilder().token("8137922853:AAFEuJXVf_REm2tSF7kkruVVBEQaj87PU-Y").build()

conv_handler = ConversationHandler(
    entry_points=[CommandHandler("start", start)],
    states={ASK_INFO: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_info)]},
    fallbacks=[CommandHandler("cancel", cancel)],
)

app.add_handler(conv_handler)
app.run_polling()
