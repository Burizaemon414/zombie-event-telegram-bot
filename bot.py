
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
creds_b64 = os.getenv("GOOGLE_CREDS_JSON")
if not creds_b64:
    raise ValueError("Environment variable GOOGLE_CREDS_JSON not found")

creds_json_str = base64.b64decode(creds_b64).decode("utf-8")
credentials_info = json.loads(creds_json_str)
creds = ServiceAccountCredentials.from_json_keyfile_dict(credentials_info, scope)
client = gspread.authorize(creds)
sheet = client.open("เครดิตฟรี กลุ่ม กิจกรรม ZOMBIE").sheet1

# ====== Bot Config ======
ASK_INFO = range(1)
GROUP_ID = -1002561643127

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
    data = {}

    for line in text.strip().splitlines():
        if ':' in line:
            key, value = map(str.strip, line.split(':', 1))
            data[key.lower()] = value

    if any(not v for v in data.values()):
        await update.message.reply_text(
            "❗ ข้อมูลยังไม่ครบหรือรูปแบบไม่ถูกต้อง\n"
            "กรุณาคัดลอกฟอร์มตัวอย่าง และเติมข้อมูลให้ครบทุกช่อง\n\n"
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

    sheet.append_row([
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
        now
    ])

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

# ====== Run Bot ======
bot_token = os.getenv("BOT_TOKEN")
if not bot_token:
    raise ValueError("Environment variable BOT_TOKEN not found")

app = ApplicationBuilder().token(bot_token).build()
conv_handler = ConversationHandler(
    entry_points=[CommandHandler("start", start)],
    states={ASK_INFO: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_info)]},
    fallbacks=[CommandHandler("cancel", cancel)],
)
app.add_handler(conv_handler)
app.run_polling()
