import os
import json
import base64
from datetime import datetime
from threading import Thread
from flask import Flask, request, redirect
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
sheet = client.open("เครดิตฟรี กลุ่ม กิจกรรม ZOMBIE").worksheet("ข้อมูลลูกค้า")

# ====== Bot Config ======
ASK_INFO = range(1)
GROUP_ID = -1002561643127  # เปลี่ยนเป็น group id ของคุณ

def build_redirect_url(house_key, user_id):
    return f"https://zombie-event-telegram-bot.onrender.com/go?house={house_key}&uid={user_id}"

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

    # เพิ่มแถวใหม่ทุกครั้ง (ไม่ตรวจสอบว่ามีอยู่แล้วหรือไม่)
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
        "PENDING",  # บ้านที่รับเครดิตฟรี (เริ่มต้นเป็น PENDING)
        ""  # บ้านที่เคยกดเข้าไปดู
    ])

    await update.message.reply_text(confirm_message, parse_mode="Markdown", reply_markup=reply_markup)
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ ยกเลิกการยืนยันตัวตนแล้ว")
    return ConversationHandler.END

# ====== Flask App สำหรับ log_click ======
flask_app = Flask(__name__)
CORS(flask_app)

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
        # ค้นหา user_id ทั้งหมดใน sheet
        all_cells = sheet.findall(str(uid))
        if all_cells:
            # หาแถวล่าสุด
            last_cell = all_cells[-1]
            last_row = last_cell.row
            print(f"✅ พบ user_id {uid} ที่แถว {last_row} (แถวล่าสุด)")
            
            # รวบรวมบ้านที่เคยกดจากแถวก่อนหน้า (ไม่รวมแถวปัจจุบัน)
            all_houses = []
            
            # ดึงบ้านจากแถวก่อนหน้าทั้งหมด
            for i, cell in enumerate(all_cells[:-1]):  # ไม่รวมแถวล่าสุด
                row = cell.row
                # บ้านที่รับเครดิตฟรี (คอลัมน์ 12)
                house_credit = sheet.cell(row, 12).value
                if house_credit and house_credit != "PENDING" and house_credit not in all_houses:
                    all_houses.append(house_credit)
            
            # เพิ่มบ้านที่กดครั้งนี้
            if house not in all_houses:
                all_houses.append(house)
            
            # สร้าง string ของบ้านทั้งหมด
            all_houses_str = ",".join(all_houses)
            
            # อัพเดทบ้านที่รับเครดิตฟรี (คอลัมน์ 12)
            current_house = sheet.cell(last_row, 12).value
            if current_house == "PENDING":
                sheet.update_cell(last_row, 12, house)
                print(f"🏠 อัพเดทบ้านที่รับเครดิตฟรี: {house}")
            
            # อัพเดทรายการบ้านที่เคยกดสะสม (คอลัมน์ 13)
            sheet.update_cell(last_row, 13, all_houses_str)
            print(f"📝 อัพเดทรายการบ้านสะสม: {all_houses_str}")
            
        else:
            print(f"❌ ไม่พบ user_id {uid} ในชีต")
            
    except Exception as e:
        print(f"❌ Error updating sheet: {e}")
    
    # Redirect ไป LINE
    print(f"↗️ Redirect {uid} ไปยัง {house}: {link}")
    return redirect(link, code=302)

@flask_app.route("/log_click", methods=["POST"])
def log_click():
    try:
        data = request.get_json()
        print("📥 ได้รับข้อมูลจาก Worker:", data)

        house = data.get("house", "").upper()
        user_id = str(data.get("uid"))
        time = data.get("time", datetime.utcnow().isoformat())

        if not house or not user_id:
            print("⚠️ house หรือ uid หายไป")
            return 'invalid', 400

        try:
            cell = sheet.find(user_id)
        except Exception as e:
            print(f"❌ หา user_id {user_id} ไม่เจอในชีต")
            return 'not found', 404

        row = cell.row
        print(f"✅ เจอ user_id ที่ row {row}")

        sheet.update_cell(row, 12, house)
        print(f"🏠 อัปเดตคอลัมน์ L (12): {house}")

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

# ====== Main function สำหรับ Render ======
if __name__ == "__main__":
    # Initialize bot
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

    # Start Flask in a separate thread
    flask_thread = Thread(target=lambda: flask_app.run(host="0.0.0.0", port=10000))
    flask_thread.daemon = True
    flask_thread.start()

    # Start bot
    print("🤖 Bot is starting...")
    app.run_polling(drop_pending_updates=True)