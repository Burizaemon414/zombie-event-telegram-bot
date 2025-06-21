from flask import Flask, request, redirect
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import os
import json
import base64
from datetime import datetime

app = Flask(__name__)

# ====== Google Sheet Setup ======
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds_b64 = os.getenv("GOOGLE_CREDS_JSON")

if not creds_b64:
    raise ValueError("Environment variable GOOGLE_CREDS_JSON not found")

creds_json = base64.b64decode(creds_b64).decode("utf-8")
credentials_info = json.loads(creds_json)
creds = ServiceAccountCredentials.from_json_keyfile_dict(credentials_info, scope)
client = gspread.authorize(creds)
sheet = client.open("เครดิตฟรี กลุ่ม กิจกรรม ZOMBIE").sheet1

# ====== Redirect Map ======
LINE_HOUSE_LINKS = {
    "ZOMBIE_XO": "https://lin.ee/SgguCbJ",
    "ZOMBIE_PG": "https://lin.ee/ETELgrN",
    "ZOMBIE_KING": "https://lin.ee/fJilKIf",
    "ZOMBIE_ALL": "https://lin.ee/9eogsb8e",
    "GENBU88": "https://lin.ee/JCCXt06"
}

@app.route("/go")
def go():
    house = request.args.get("house")
    uid = request.args.get("uid")

    if not house or not uid:
        return "Missing parameters", 400

    link = LINE_HOUSE_LINKS.get(house.upper())
    if not link:
        return "Unknown house", 400

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # ค้นหา row ของ user_id แล้วอัปเดต "บ้านที่กด" + เวลา
    cell = sheet.find(uid)
    if cell:
        sheet.update_cell(cell.row, sheet.col_count, f"{house} @ {now}")
    else:
        sheet.append_row(["-", "-", "-", "-", "-", "-", "-", "-", uid, "-", now, house])

    return redirect(link, code=302)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)
