import os
import json
import base64
from datetime import datetime
from threading import Thread
from flask import Flask, request
from flask_cors import CORS

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

import gspread
from oauth2client.service_account import ServiceAccountCredentials

# ====== Google Sheet Setup ======
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
sheet = client.open("เครดิตฟรี กลุ่ม กิจกรรม ZOMBIE").sheet1

# ====== Bot Config ======
ASK_INFO = range(1)
GROUP_ID = -1002561643127  # เปลี่ยนเป็น group id ของคุณ

def build_redirect_url(house_key, user_id):
    return f"https://activate-creditfree.slotzombies.net/?house={house_key}&uid={user_id}"

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
    await update.message.reply_text(welcome_message, reply_markup=reply_markup)
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
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

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
        now,
        "PENDING"
    ])

    await update.message.reply_text(confirm_message, parse_mode="Markdown", reply_markup=reply_markup)
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ ยกเลิกการยืนยันตัวตนแล้ว")
    return ConversationHandler.END

# ====== Telegram Bot Setup ======
bot_token = os.getenv("BOT_TOKEN")
if not bot_token:
    raise ValueError("Environment variable BOT_TOKEN not found")

app = ApplicationBuilder().token(bot_token).build()

conv_handler = ConversationHandler(
    entry_points=[CommandHandler("start", start)],
    states={ASK_INFO: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_info)]},
    fallbacks=[CommandHandler("cancel", cancel)]
)
app.add_handler(conv_handler)

# ====== Flask App สำหรับ log_click ======
flask_app = Flask(__name__)
CORS(flask_app)

@flask_app.route("/log_click", methods=["POST"])
def log_click():
    try:
        data = request.get_json()
        print("📥 ได้รับข้อมูลจาก Worker:", data)

        house = data.get("house", "").upper()
        user_id = str(data.get("uid"))
        time = data.get("time", datetime.utcnow().isoformat())

        # ตรวจสอบข้อมูลที่จำเป็น
        if not house or not user_id:
            print("⚠️ house หรือ uid หายไป")
            return 'invalid', 400

        # 🔍 หาแถวของ user_id
        try:
            cell = sheet.find(user_id)
        except Exception as e:
            print(f"❌ หา user_id {user_id} ไม่เจอในชีต")
            return 'not found', 404

        row = cell.row
        print(f"✅ เจอ user_id ที่ row {row}")

        # ✅ คอลัมน์ L (12) → บ้านล่าสุดที่กด
        sheet.update_cell(row, 12, house)
        print(f"🏠 อัปเดตคอลัมน์ L (12): {house}")

        # ✅ คอลัมน์ M (13) → บ้านที่เคยกดทั้งหมด (สะสม)
        current = sheet.cell(row, 13).value or ""
        if house not in current:
            updated = f"{current},{house}" if current else house
            sheet.update_cell(row, 13, updated)
            print(f"🧩 เพิ่มบ้าน {house} ในคอลัมน์ M (13): {updated}")
        else:
            print(f"🔁 บ้าน {house} เคยกดแล้ว ไม่อัปเดตซ้ำ")

        return '', 204

    except Exception as e:
        print("❌ ERROR ใน log_click:", e)
        return 'error', 500

# ====== Run Telegram + Flask ======
def run_telegram():
    app.run_polling()

def run_flask():
    flask_app.run(host="0.0.0.0", port=10000)

if __name__ == "__main__":
    Thread(target=run_flask).start()
    app.run_polling()
