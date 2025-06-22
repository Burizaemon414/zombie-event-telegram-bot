import os
import json
import base64
from datetime import datetime
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import logging

logger = logging.getLogger(__name__)

class SheetManager:
    """จัดการ Google Sheets หลายๆ sheet อัตโนมัติ"""
    
    def __init__(self):
        self.client = None
        self.spreadsheet = None
        self.current_sheet = None
        self.sheet_index = 1
        self.max_rows_per_sheet = 50000  # จำกัดที่ 50k เพื่อ performance
        self._connect()
    
    def _connect(self):
        """เชื่อมต่อ Google Sheets"""
        try:
            scope = [
                "https://spreadsheets.google.com/feeds",
                "https://www.googleapis.com/auth/drive"
            ]
            creds_b64 = os.getenv("GOOGLE_CREDS_JSON")
            creds_json_str = base64.b64decode(creds_b64).decode("utf-8")
            credentials_info = json.loads(creds_json_str)
            creds = ServiceAccountCredentials.from_json_keyfile_dict(credentials_info, scope)
            
            self.client = gspread.authorize(creds)
            self.spreadsheet = self.client.open("เครดิตฟรี กลุ่ม กิจกรรม ZOMBIE")
            self._check_current_sheet()
            
        except Exception as e:
            logger.error(f"Connection error: {e}")
            raise
    
    def _check_current_sheet(self):
        """ตรวจสอบ sheet ปัจจุบัน"""
        # ดึงรายการ sheets ทั้งหมด
        worksheets = self.spreadsheet.worksheets()
        
        # หา sheet ล่าสุด
        data_sheets = [ws for ws in worksheets if ws.title.startswith("ข้อมูลลูกค้า")]
        
        if data_sheets:
            # เรียงตาม index และเลือกตัวล่าสุด
            latest_sheet = sorted(data_sheets, key=lambda x: self._extract_sheet_number(x.title))[-1]
            self.current_sheet = latest_sheet
            self.sheet_index = self._extract_sheet_number(latest_sheet.title)
            
            # ตรวจสอบว่าเต็มหรือยัง
            row_count = len(self.current_sheet.get_all_values())
            if row_count >= self.max_rows_per_sheet:
                self._create_new_sheet()
        else:
            # สร้าง sheet แรก
            self.current_sheet = self.spreadsheet.worksheet("ข้อมูลลูกค้า")
            self.sheet_index = 1
    
    def _extract_sheet_number(self, sheet_name):
        """ดึงหมายเลข sheet จากชื่อ"""
        if sheet_name == "ข้อมูลลูกค้า":
            return 1
        try:
            # Format: "ข้อมูลลูกค้า_2", "ข้อมูลลูกค้า_3"
            return int(sheet_name.split("_")[-1])
        except:
            return 1
    
    def _create_new_sheet(self):
        """สร้าง sheet ใหม่เมื่อเต็ม"""
        try:
            self.sheet_index += 1
            new_sheet_name = f"ข้อมูลลูกค้า_{self.sheet_index}"
            
            # สร้าง sheet ใหม่
            new_sheet = self.spreadsheet.add_worksheet(
                title=new_sheet_name,
                rows=self.max_rows_per_sheet + 1000,  # เผื่อ buffer
                cols=20
            )
            
            # คัดลอก header จาก sheet เดิม
            headers = self.current_sheet.row_values(1)
            new_sheet.update('A1:T1', [headers])
            
            # Format header
            new_sheet.format('A1:T1', {
                "backgroundColor": {"red": 0.2, "green": 0.6, "blue": 0.9},
                "textFormat": {"bold": True, "foregroundColor": {"red": 1, "green": 1, "blue": 1}}
            })
            
            self.current_sheet = new_sheet
            logger.info(f"✅ Created new sheet: {new_sheet_name}")
            
            # แจ้งเตือน admin
            self._notify_admin_new_sheet(new_sheet_name)
            
        except Exception as e:
            logger.error(f"Error creating new sheet: {e}")
            raise
    
    def _notify_admin_new_sheet(self, sheet_name):
        """แจ้งเตือน admin เมื่อสร้าง sheet ใหม่"""
        # TODO: ส่งข้อความแจ้งเตือนผ่าน Telegram
        logger.info(f"📢 Notification: New sheet created - {sheet_name}")
    
    def append_row(self, data):
        """เพิ่มข้อมูลพร้อมตรวจสอบ sheet เต็ม"""
        try:
            # ตรวจสอบจำนวนแถวปัจจุบัน
            current_rows = len(self.current_sheet.get_all_values())
            
            if current_rows >= self.max_rows_per_sheet:
                logger.info(f"⚠️ Sheet {self.current_sheet.title} is full ({current_rows} rows)")
                self._create_new_sheet()
            
            # เพิ่มข้อมูล
            self.current_sheet.append_row(data)
            logger.info(f"✅ Added data to {self.current_sheet.title} (row {current_rows + 1})")
            
            return True
            
        except Exception as e:
            logger.error(f"Error appending row: {e}")
            return False
    
    def search_user(self, user_id):
        """ค้นหา user จากทุก sheets"""
        try:
            worksheets = self.spreadsheet.worksheets()
            data_sheets = [ws for ws in worksheets if ws.title.startswith("ข้อมูลลูกค้า")]
            
            results = []
            
            for sheet in data_sheets:
                try:
                    # ค้นหาใน column I (user_id)
                    cell_list = sheet.findall(str(user_id))
                    for cell in cell_list:
                        row_data = sheet.row_values(cell.row)
                        results.append({
                            'sheet': sheet.title,
                            'row': cell.row,
                            'data': row_data
                        })
                except Exception as e:
                    logger.error(f"Error searching in {sheet.title}: {e}")
            
            return results
            
        except Exception as e:
            logger.error(f"Error searching user: {e}")
            return []
    
    def get_statistics(self):
        """ดึงสถิติการใช้งาน"""
        try:
            worksheets = self.spreadsheet.worksheets()
            data_sheets = [ws for ws in worksheets if ws.title.startswith("ข้อมูลลูกค้า")]
            
            stats = {
                'total_sheets': len(data_sheets),
                'sheets': []
            }
            
            total_users = 0
            
            for sheet in data_sheets:
                row_count = len(sheet.get_all_values()) - 1  # ไม่นับ header
                total_users += row_count
                
                stats['sheets'].append({
                    'name': sheet.title,
                    'users': row_count,
                    'capacity': f"{(row_count/self.max_rows_per_sheet)*100:.1f}%"
                })
            
            stats['total_users'] = total_users
            stats['current_sheet'] = self.current_sheet.title
            
            return stats
            
        except Exception as e:
            logger.error(f"Error getting statistics: {e}")
            return None