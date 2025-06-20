from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardButton, InlineKeyboardMarkup, Bot
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
import asyncio
import sys

# ====== Configuration ======
ASK_INFO = range(1)
GROUP_ID = -1002561643127

# ====== Google Sheet Setup ======
def setup_google_sheets():
    """Setup Google Sheets connection"""
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    
    # ลองหา credentials จาก environment variable ก่อน
    creds_b64 = os.getenv("GOOGLE_CREDS_JSON")
    
    if creds_b64:
        print("📊 ใช้ Google credentials จาก environment variable")
        try:
            creds_json_str = base64.b64decode(creds_b64).decode("utf-8")
            credentials_info = json.loads(creds_json_str)
        except Exception as e:
            print(f"❌ Error decoding credentials: {e}")
            sys.exit(1)
    else:
        # ถ้าไม่มี environment variable ให้หาจากไฟล์
        print("📊 ใช้ Google credentials จากไฟล์")
        creds_file = "GOOGLE_CREDS_JSON.json"
        
        if not os.path.exists(creds_file):
            print(f"❌ ไม่พบไฟล์ {creds_file}")
            print("❗ กรุณาวางไฟล์ credentials หรือตั้งค่า GOOGLE_CREDS_JSON environment variable")
            sys.exit(1)
        
        with open(creds_file, 'r') as f:
            credentials_info = json.load(f)
    
    try:
        creds = ServiceAccountCredentials.from_json_keyfile_dict(credentials_info, scope)
        client = gspread.authorize(creds)
        sheet = client.open("เครดิตฟรี กลุ่ม กิจกรรม ZOMBIE").sheet1
        print("✅ เชื่อมต่อ Google Sheets สำเร็จ")
        return sheet
    except Exception as e:
        print(f"❌ ไม่สามารถเชื่อมต่อ Google Sheets: {e}")
        sys.exit(1)

# Setup Google Sheets
sheet = setup_google_sheets()

# ====== Bot Token ======
BOT_TOKEN = os.getenv("BOT_TOKEN", "8137922853:AAFEuJXVf_REm2tSF7kkruVVBEQaj87PU-Y")

# ====== Bot Handlers ======
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start command handler"""
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
    """Handle user information input"""
    text = update.message.text
    
    # ถ้ากดปุ่ม "เริ่มต้นส่งข้อมูล ✅"
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
    
    # Parse user data
    data = {}
    for line in text.strip().splitlines():
        if ':' in line:
            key, value = map(str.strip, line.split(':', 1))
            data[key.lower()] = value
    
    # ตรวจสอบข้อมูล
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
    
    # Get user info
    user = update.message.from_user
    user_id = user.id
    username = user.username or "ไม่มี"
    
    # Check group membership
    try:
        member = await context.bot.get_chat_member(chat_id=GROUP_ID, user_id=user_id)
        in_group = member.status in ['member', 'administrator', 'creator']
    except Exception as e:
        print(f"⚠️ ไม่สามารถตรวจสอบสถานะกลุ่ม: {e}")
        in_group = False
    
    status_text = "✅ อยู่ในกลุ่มแล้ว" if in_group else "❌ ยังไม่ได้เข้ากลุ่ม"
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # Save to Google Sheets
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
    
    # Send confirmation message
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
    
    await update.message.reply_text(
        confirm_message, 
        parse_mode="Markdown", 
        reply_markup=reply_markup
    )
    
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancel command handler"""
    await update.message.reply_text("❌ ยกเลิกการยืนยันตัวตนแล้ว")
    return ConversationHandler.END

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle errors"""
    print(f"❌ Error: {context.error}")
    if update and update.effective_message:
        await update.effective_message.reply_text(
            "❌ เกิดข้อผิดพลาด กรุณาลองใหม่อีกครั้ง\n"
            "หากยังมีปัญหา กรุณาติดต่อแอดมิน"
        )

async def clear_webhook():
    """Clear webhook before starting"""
    bot = Bot(token=BOT_TOKEN)
    try:
        webhook_info = await bot.get_webhook_info()
        if webhook_info.url:
            print(f"🔗 พบ Webhook เก่า: {webhook_info.url}")
            await bot.delete_webhook(drop_pending_updates=True)
            print("✅ ลบ webhook เก่าเรียบร้อย")
        else:
            print("✅ ไม่พบ webhook เก่า")
    except Exception as e:
        print(f"⚠️ Error clearing webhook: {e}")
    finally:
        await bot.close()

# ====== Main Function ======
def main():
    """Main function to run the bot"""
    print("🚀 เริ่มต้นระบบบอท...")
    print(f"🔑 Bot Token: {BOT_TOKEN[:20]}...")
    print(f"📊 Google Sheet: เครดิตฟรี กลุ่ม กิจกรรม ZOMBIE")
    print(f"🌐 Environment: {'Render' if os.getenv('RENDER') else 'Local'}")
    
    # Clear webhook first
    print("\n🔄 กำลังเคลียร์ webhook เก่า...")
    asyncio.run(clear_webhook())
    
    # Build application
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    
    # Add conversation handler
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            ASK_INFO: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_info)]
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    
    app.add_handler(conv_handler)
    app.add_error_handler(error_handler)
    
    # Check if running on Render
    if os.getenv("RENDER"):
        # Render mode - use webhook
        print("\n🌐 กำลังรันบน Render (Webhook mode)")
        PORT = int(os.environ.get("PORT", 10000))
        RENDER_EXTERNAL_URL = os.environ.get("RENDER_EXTERNAL_URL")
        
        if not RENDER_EXTERNAL_URL:
            print("❌ ไม่พบ RENDER_EXTERNAL_URL")
            sys.exit(1)
        
        webhook_url = f"{RENDER_EXTERNAL_URL}/{BOT_TOKEN}"
        print(f"🔗 Webhook URL: {webhook_url}")
        
        # Start webhook
        app.run_webhook(
            listen="0.0.0.0",
            port=PORT,
            webhook_url=webhook_url,
            drop_pending_updates=True
        )
    else:
        # Local mode - use polling
        print("\n💻 กำลังรันบน Local (Polling mode)")
        print("✅ บอทพร้อมทำงานแล้ว! กด Ctrl+C เพื่อหยุด\n")
        
        # Start polling
        app.run_polling(
            allowed_updates=Update.ALL_TYPES,
            drop_pending_updates=True
        )

if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n👋 หยุดการทำงานของบอท")
    except Exception as e:
        print(f"\n❌ เกิดข้อผิดพลาด: {e}")
        sys.exit(1)