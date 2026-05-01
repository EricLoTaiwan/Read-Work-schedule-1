import streamlit as st
import pandas as pd
import re
import json
import os
import glob
import shutil 
import time
from datetime import datetime
import pytz
import requests 
import concurrent.futures
from bs4 import BeautifulSoup

# ----------------- 嘗試載入 AI 相關套件 -----------------
try:
    from PIL import Image 
    from google import genai 
    HAS_AI_MODULES = True
except ImportError:
    HAS_AI_MODULES = False
# --------------------------------------------------------

# 頁面基本設定
st.set_page_config(page_title="共用智慧班表系統", page_icon="✈️", layout="wide")

SHARED_FILE = "shared_schedule.json"
HISTORY_DIR = "schedule_history"
SAVED_TABLES_DIR = "saved_tables" 
CURRENT_ACTIVE_FILE = "current_active_schedule.txt" 
TW_TZ = pytz.timezone('Asia/Taipei')

# 確保歷史紀錄與儲存資料夾存在
os.makedirs(HISTORY_DIR, exist_ok=True)
os.makedirs(SAVED_TABLES_DIR, exist_ok=True)

# ----------------- AI 視覺辨識核心模組 -----------------
if HAS_AI_MODULES:
    def extract_schedule_with_ai(image_source, api_key, fallback_default=True):
        if not api_key:
            if fallback_default: return get_default_data()
            else: raise ValueError("未提供 API Key，無法進行辨識。")
            
        try:
            client = genai.Client(api_key=api_key)
            img = Image.open(image_source)
            
            prompt = """
            你是一個專業的長榮航空班表分析專家。請嚴格分析這張班表截圖，提取每一天的「日期 (Date)」、「星期幾 (Day)」、以及格子內的「文字內容 (Content)」。
            請嚴格以 JSON 陣列 (Array) 的格式輸出。
            **絕對不要包含任何其他問候語、解釋或是 Markdown 標記 (例如 
            ```json )**。
            只允許輸出中括號 [] 包起來的 JSON 陣列。
            
            格式範例：
            [
                {"Date": 1, "Day": "FRI", "Content": "772 (TSA)\n771\nB78N"},
                {"Date": 2, "Day": "SAT", "Content": "YJ"}
            ]
            
            嚴格規則：
            1. Date 必須是整數 (1, 2, 3...)。
            2. Day 必須是三個字母的大寫英文縮寫。
            3. Content 必須保留換行符號 (\n)。如果該天格子為空或是只有括號數字，請填寫對應的假別(如 DO, ADO) 或留空。
            4. 必須按照日期順序，從 1 號提取到該月月底。
            """
            
            models = ['gemini-2.5-flash', 'gemini-2.5-pro']
            
            for model_name in models:
                try:
                    response = client.models.generate_content(
                        model=model_name,
                        contents=[prompt, img]
                    )
                    match = re.search(r'\[.*\]', response.text, re.DOTALL)
                    
                    if match:
                        return json.loads(match.group(0))
                except Exception as model_err:
                    print(f"模型 {model_name} 失敗: {model_err}")
                    continue 
            
            raise ValueError("所有 AI 模型皆無法成功解析。")
            
        except Exception as e:
            if fallback_default:
                st.warning(f"⚠️ AI 解析發生異常，已自動切換為預設班表模式。(錯誤: {str(e)})")
                return get_default_data() 
            else:
                raise Exception(f"AI 解析失敗 (請確認 API Key 是否有效或網路狀態): {str(e)}")
# --------------------------------------------------------

def get_real_weather(lat, lon):
    try:
        url = f"[https://api.open-meteo.com/v1/forecast?latitude=](https://api.open-meteo.com/v1/forecast?latitude=){lat}&longitude={lon}&current_weather=true"
        response = requests.get(url, timeout=3)
        if response.status_code == 200:
            data = response.json()['current_weather']
            temp = data['temperature']
            code = data['weathercode']
            rain = "有雨" if code in [51,53,55,61,63,65,80,81,82,95,96,99] else "無雨"
            snow = "有雪" if code in [71,73,75,77,85,86] else "無雪"
            return {"temp": f"{temp}°C", "rain": rain, "snow": snow}
    except Exception:
        pass 
    return {"temp": "--°C", "rain": "未知", "snow": "未知"}

# ==========================================
# 靜態常態資料庫 (作為爬蟲更新的底板)
# ==========================================
MASTER_STATIC_DB = {
    # === 東南亞區域線 ===
    "BR211": {"aircraft": "B77M", "route": "台北 (TPE) ➔ 曼谷 (BKK)", "std": "08:20", "sta": "11:10", "dur": "3h 50m", "coords": (13.6900, 100.7501)},
    "BR212": {"aircraft": "B77M", "route": "曼谷 (BKK) ➔ 台北 (TPE)", "std": "12:10", "sta": "16:45", "dur": "3h 35m", "coords": (25.0797, 121.2342)},
    "BR201": {"aircraft": "B77M", "route": "台北 (TPE) ➔ 曼谷 (BKK)", "std": "09:40", "sta": "12:25", "dur": "3h 45m", "coords": (13.6900, 100.7501)},
    "BR202": {"aircraft": "B77M", "route": "曼谷 (BKK) ➔ 台北 (TPE)", "std": "14:40", "sta": "19:15", "dur": "3h 35m", "coords": (25.0797, 121.2342)},
    "BR227": {"aircraft": "B77M", "route": "台北 (TPE) ➔ 吉隆坡 (KUL)", "std": "09:30", "sta": "14:15", "dur": "4h 45m", "coords": (2.7456, 101.7099)},
    "BR228": {"aircraft": "B77M", "route": "吉隆坡 (KUL) ➔ 台北 (TPE)", "std": "15:25", "sta": "20:15", "dur": "4h 50m", "coords": (25.0797, 121.2342)},
    "BR237": {"aircraft": "B77M", "route": "台北 (TPE) ➔ 雅加達 (CGK)", "std": "09:00", "sta": "13:20", "dur": "5h 20m", "coords": (-6.1256, 106.6558)},
    "BR238": {"aircraft": "B77M", "route": "雅加達 (CGK) ➔ 台北 (TPE)", "std": "14:20", "sta": "20:45", "dur": "5h 25m", "coords": (25.0797, 121.2342)},
    "BR391": {"aircraft": "B77M", "route": "台北 (TPE) ➔ 胡志明市 (SGN)", "std": "09:20", "sta": "11:40", "dur": "3h 20m", "coords": (10.8188, 106.6519)},
    "BR392": {"aircraft": "B77M", "route": "胡志明市 (SGN) ➔ 台北 (TPE)", "std": "12:50", "sta": "17:15", "dur": "3h 25m", "coords": (25.0797, 121.2342)},
    "BR271": {"aircraft": "A321", "route": "台北 (TPE) ➔ 馬尼拉 (MNL)", "std": "09:10", "sta": "11:30", "dur": "2h 20m", "coords": (14.5090, 121.0194)},
    "BR272": {"aircraft": "A321", "route": "馬尼拉 (MNL) ➔ 台北 (TPE)", "std": "12:40", "sta": "15:00", "dur": "2h 20m", "coords": (25.0797, 121.2342)},
    "BR265": {"aircraft": "A333", "route": "台北 (TPE) ➔ 金邊 (PNH)", "std": "08:45", "sta": "11:10", "dur": "3h 25m", "coords": (11.5466, 104.8441)},
    "BR266": {"aircraft": "A333", "route": "金邊 (PNH) ➔ 台北 (TPE)", "std": "12:10", "sta": "16:35", "dur": "3h 25m", "coords": (25.0797, 121.2342)},
    "BR281": {"aircraft": "B78P", "route": "台北 (TPE) ➔ 宿霧 (CEB)", "std": "07:10", "sta": "10:05", "dur": "2h 55m", "coords": (10.3075, 123.9794)},
    "BR282": {"aircraft": "B78P", "route": "宿霧 (CEB) ➔ 台北 (TPE)", "std": "11:05", "sta": "14:00", "dur": "2h 55m", "coords": (25.0797, 121.2342)},
    "BR257": {"aircraft": "A321", "route": "台北 (TPE) ➔ 清邁 (CNX)", "std": "07:15", "sta": "10:30", "dur": "4h 15m", "coords": (18.7668, 98.9626)},
    "BR258": {"aircraft": "A321", "route": "清邁 (CNX) ➔ 台北 (TPE)", "std": "11:35", "sta": "16:35", "dur": "4h 00m", "coords": (25.0797, 121.2342)},
    "BR397": {"aircraft": "B77M", "route": "台北 (TPE) ➔ 河內 (HAN)", "std": "09:00", "sta": "11:05", "dur": "3h 05m", "coords": (21.2212, 105.8072)},
    "BR398": {"aircraft": "B77M", "route": "河內 (HAN) ➔ 台北 (TPE)", "std": "12:05", "sta": "15:55", "dur": "2h 50m", "coords": (25.0797, 121.2342)},
    "BR383": {"aircraft": "A321", "route": "台北 (TPE) ➔ 峴港 (DAD)", "std": "09:45", "sta": "11:40", "dur": "2h 55m", "coords": (16.0439, 108.1994)},
    "BR384": {"aircraft": "A321", "route": "峴港 (DAD) ➔ 峴港 (TPE)", "std": "14:10", "sta": "18:05", "dur": "2h 55m", "coords": (25.0797, 121.2342)},
    "BR231": {"aircraft": "A333", "route": "台北 (TPE) ➔ 檳城 (PEN)", "std": "09:20", "sta": "13:50", "dur": "4h 30m", "coords": (5.2971, 100.2769)},
    "BR232": {"aircraft": "A333", "route": "檳城 (PEN) ➔ 台北 (TPE)", "std": "14:50", "sta": "19:45", "dur": "4h 55m", "coords": (25.0797, 121.2342)},
    "BR233": {"aircraft": "A321", "route": "台北 (TPE) ➔ 克拉克 (CRK)", "std": "09:00", "sta": "11:00", "dur": "2h 00m", "coords": (15.1858, 120.5599)},
    "BR234": {"aircraft": "A321", "route": "克拉克 (CRK) ➔ 台北 (TPE)", "std": "12:00", "sta": "14:00", "dur": "2h 00m", "coords": (25.0797, 121.2342)},
    "BR255": {"aircraft": "A333", "route": "台北 (TPE) ➔ 峇里島 (DPS)", "std": "10:00", "sta": "15:20", "dur": "5h 20m", "coords": (-8.7482, 115.1675)},
    "BR256": {"aircraft": "A333", "route": "峇里島 (DPS) ➔ 台北 (TPE)", "std": "16:20", "sta": "21:35", "dur": "5h 15m", "coords": (25.0797, 121.2342)},
    "BR277": {"aircraft": "A333", "route": "台北 (TPE) ➔ 馬尼拉 (MNL)", "std": "15:30", "sta": "17:50", "dur": "2h 20m", "coords": (14.5090, 121.0194)},  
    "BR278": {"aircraft": "A333", "route": "馬尼拉 (MNL) ➔ 台北 (TPE)", "std": "18:50", "sta": "21:10", "dur": "2h 20m", "coords": (25.0797, 121.2342)},  
    "BR1383": {"aircraft": "A321", "route": "台北 (TPE) ➔ 峴港 (DAD)", "std": "07:10", "sta": "09:05", "dur": "2h 55m", "coords": (16.0439, 108.1994)},
    "BR1384": {"aircraft": "A321", "route": "峴港 (DAD) ➔ 台北 (TPE)", "std": "10:20", "sta": "14:05", "dur": "2h 45m", "coords": (25.0797, 121.2342)},

    # === 東北亞與兩岸線 ===
    "BR178": {"aircraft": "B78N", "route": "台北 (TPE) ➔ 大阪 (KIX)", "std": "06:30", "sta": "10:10", "dur": "2h 40m", "coords": (34.4320, 135.2304)},
    "BR177": {"aircraft": "B78N", "route": "大阪 (KIX) ➔ 台北 (TPE)", "std": "11:10", "sta": "13:05", "dur": "2h 55m", "coords": (25.0797, 121.2342)},
    "BR130": {"aircraft": "B781", "route": "台北 (TPE) ➔ 大阪 (KIX)", "std": "13:35", "sta": "17:15", "dur": "2h 40m", "coords": (34.4320, 135.2304)},
    "BR129": {"aircraft": "B781", "route": "大阪 (KIX) ➔ 台北 (TPE)", "std": "18:30", "sta": "20:30", "dur": "3h 00m", "coords": (25.0797, 121.2342)},
    "BR198": {"aircraft": "B78P", "route": "台北 (TPE) ➔ 成田 (NRT)", "std": "08:50", "sta": "13:15", "dur": "3h 25m", "coords": (35.7647, 140.3863)},
    "BR197": {"aircraft": "B78P", "route": "成田 (NRT) ➔ 台北 (TPE)", "std": "14:15", "sta": "16:55", "dur": "3h 40m", "coords": (25.0797, 121.2342)},
    "BR189": {"aircraft": "A333", "route": "松山 (TSA) ➔ 羽田 (HND)", "std": "10:50", "sta": "13:30", "dur": "3h 40m", "coords": (35.5494, 139.7798)},
    "BR190": {"aircraft": "A333", "route": "羽田 (HND) ➔ 松山 (TSA)", "std": "14:30", "sta": "17:05", "dur": "3h 35m", "coords": (25.0697, 121.5526)},
    "BR158": {"aircraft": "A333", "route": "台北 (TPE) ➔ 小松 (KMQ)", "std": "06:35", "sta": "10:25", "dur": "2h 50m", "coords": (36.3934, 136.4070)},
    "BR157": {"aircraft": "A333", "route": "小松 (KMQ) ➔ 台北 (TPE)", "std": "11:45", "sta": "13:55", "dur": "3h 10m", "coords": (25.0797, 121.2342)},
    "BR106": {"aircraft": "A333", "route": "台北 (TPE) ➔ 福岡 (FUK)", "std": "08:10", "sta": "11:15", "dur": "2h 05m", "coords": (33.5859, 130.4507)},
    "BR105": {"aircraft": "A333", "route": "福岡 (FUK) ➔ 台北 (TPE)", "std": "12:15", "sta": "13:50", "dur": "2h 35m", "coords": (25.0797, 121.2342)},
    "BR116": {"aircraft": "A333", "route": "台北 (TPE) ➔ 札幌 (CTS)", "std": "09:30", "sta": "14:05", "dur": "3h 35m", "coords": (42.7752, 141.6923)},
    "BR115": {"aircraft": "A333", "route": "札幌 (CTS) ➔ 台北 (TPE)", "std": "15:20", "sta": "18:40", "dur": "4h 20m", "coords": (25.0797, 121.2342)},
    "BR122": {"aircraft": "A321", "route": "台北 (TPE) ➔ 青森 (AOJ)", "std": "10:00", "sta": "14:30", "dur": "3h 30m", "coords": (40.7344, 140.6900)},
    "BR121": {"aircraft": "A321", "route": "青森 (AOJ) ➔ 台北 (TPE)", "std": "15:30", "sta": "18:45", "dur": "4h 15m", "coords": (25.0797, 121.2342)},
    "BR118": {"aircraft": "A321", "route": "台北 (TPE) ➔ 仙台 (SDJ)", "std": "10:05", "sta": "14:25", "dur": "3h 20m", "coords": (38.1397, 140.9169)},
    "BR117": {"aircraft": "A321", "route": "仙台 (SDJ) ➔ 台北 (TPE)", "std": "16:05", "sta": "19:00", "dur": "3h 55m", "coords": (25.0797, 121.2342)},
    "BR160": {"aircraft": "B77M", "route": "台北 (TPE) ➔ 首爾 (ICN)", "std": "15:15", "sta": "18:45", "dur": "2h 30m", "coords": (37.4602, 126.4407)},
    "BR159": {"aircraft": "B77M", "route": "首爾 (ICN) ➔ 台北 (TPE)", "std": "19:45", "sta": "21:40", "dur": "2h 55m", "coords": (25.0797, 121.2342)},
    "BR164": {"aircraft": "B77M", "route": "台北 (TPE) ➔ 首爾 (ICN)", "std": "07:20", "sta": "10:50", "dur": "2h 30m", "coords": (37.4602, 126.4407)},  
    "BR163": {"aircraft": "B77M", "route": "首爾 (ICN) ➔ 台北 (TPE)", "std": "11:40", "sta": "13:35", "dur": "2h 55m", "coords": (25.0797, 121.2342)},  
    "BR156": {"aircraft": "A333", "route": "松山 (TSA) ➔ 首爾 (GMP)", "std": "09:20", "sta": "12:50", "dur": "2h 30m", "coords": (37.5583, 126.7906)},
    "BR155": {"aircraft": "A333", "route": "首爾 (GMP) ➔ 松山 (TSA)", "std": "13:50", "sta": "15:45", "dur": "2h 55m", "coords": (25.0697, 121.5526)},
    "BR120": {"aircraft": "A321", "route": "台北 (TPE) ➔ 釜山 (PUS)", "std": "07:55", "sta": "11:05", "dur": "2h 10m", "coords": (35.1795, 128.9382)},
    "BR119": {"aircraft": "A321", "route": "釜山 (PUS) ➔ 台北 (TPE)", "std": "12:05", "sta": "13:45", "dur": "2h 40m", "coords": (25.0797, 121.2342)},
    "BR716": {"aircraft": "B77M", "route": "台北 (TPE) ➔ 北京 (PEK)", "std": "16:20", "sta": "19:35", "dur": "3h 15m", "coords": (40.0799, 116.6031)},
    "BR715": {"aircraft": "B77M", "route": "北京 (PEK) ➔ 台北 (TPE)", "std": "20:35", "sta": "23:45", "dur": "3h 10m", "coords": (25.0797, 121.2342)},
    "BR712": {"aircraft": "B77M", "route": "台北 (TPE) ➔ 上海浦東 (PVG)", "std": "10:10", "sta": "12:05", "dur": "1h 55m", "coords": (31.1443, 121.8083)},
    "BR711": {"aircraft": "B77M", "route": "上海浦東 (PVG) ➔ 台北 (TPE)", "std": "13:10", "sta": "15:05", "dur": "1h 55m", "coords": (25.0797, 121.2342)},
    "BR772": {"aircraft": "A333", "route": "松山 (TSA) ➔ 上海虹橋 (SHA)", "std": "14:40", "sta": "16:40", "dur": "2h 00m", "coords": (31.1979, 121.3363)},
    "BR771": {"aircraft": "A333", "route": "上海虹橋 (SHA) ➔ 松山 (TSA)", "std": "19:40", "sta": "21:45", "dur": "2h 05m", "coords": (25.0697, 121.5526)},
    "BR707": {"aircraft": "B77M", "route": "台北 (TPE) ➔ 廣州 (CAN)", "std": "08:25", "sta": "10:35", "dur": "2h 10m", "coords": (23.3924, 113.2988)},
    "BR708": {"aircraft": "B77M", "route": "廣州 (CAN) ➔ 台北 (TPE)", "std": "11:55", "sta": "14:00", "dur": "2h 05m", "coords": (25.0797, 121.2342)},
    "BR891": {"aircraft": "A321", "route": "台北 (TPE) ➔ 廈門 (XMN)", "std": "09:50", "sta": "11:35", "dur": "1h 45m", "coords": (24.5440, 118.1277)},
    "BR892": {"aircraft": "A321", "route": "廈門 (XMN) ➔ 台北 (TPE)", "std": "13:00", "sta": "14:45", "dur": "1h 45m", "coords": (25.0797, 121.2342)},
    "BR765": {"aircraft": "A333", "route": "台北 (TPE) ➔ 成都 (TFU)", "std": "14:30", "sta": "18:15", "dur": "3h 45m", "coords": (30.2725, 104.4372)},
    "BR766": {"aircraft": "A333", "route": "成都 (TFU) ➔ 台北 (TPE)", "std": "19:30", "sta": "22:50", "dur": "3h 20m", "coords": (25.0797, 121.2342)},
    "BR739": {"aircraft": "A321", "route": "台北 (TPE) ➔ 重慶 (CKG)", "std": "14:35", "sta": "17:50", "dur": "3h 15m", "coords": (29.7196, 106.6416)},
    "BR740": {"aircraft": "A321", "route": "重慶 (CKG) ➔ 台北 (TPE)", "std": "18:50", "sta": "21:50", "dur": "3h 00m", "coords": (25.0797, 121.2342)},
    "BR758": {"aircraft": "A333", "route": "台北 (TPE) ➔ 杭州 (HGH)", "std": "16:25", "sta": "18:25", "dur": "2h 00m", "coords": (30.2295, 120.4345)},  
    "BR757": {"aircraft": "A333", "route": "杭州 (HGH) ➔ 台北 (TPE)", "std": "19:35", "sta": "21:30", "dur": "1h 55m", "coords": (25.0797, 121.2342)},  
    "BR851": {"aircraft": "A321", "route": "台北 (TPE) ➔ 香港 (HKG)", "std": "08:15", "sta": "10:05", "dur": "1h 50m", "coords": (22.3080, 113.9185)},
    "BR852": {"aircraft": "A321", "route": "香港 (HKG) ➔ 台北 (TPE)", "std": "11:15", "sta": "13:00", "dur": "1h 45m", "coords": (25.0797, 121.2342)},
    "BR867": {"aircraft": "B781/B77M", "route": "台北 (TPE) ➔ 香港 (HKG)", "std": "10:05", "sta": "12:05", "dur": "2h 00m", "coords": (22.3080, 113.9185)},
    "BR868": {"aircraft": "B781/B77M", "route": "香港 (HKG) ➔ 台北 (TPE)", "std": "13:30", "sta": "15:20", "dur": "1h 50m", "coords": (25.0797, 121.2342)},
    "BR871": {"aircraft": "B781", "route": "台北 (TPE) ➔ 香港 (HKG)", "std": "16:40", "sta": "18:30", "dur": "1h 50m", "coords": (22.3080, 113.9185)},
    "BR872": {"aircraft": "B781", "route": "香港 (HKG) ➔ 台北 (TPE)", "std": "19:40", "sta": "21:30", "dur": "1h 50m", "coords": (25.0797, 121.2342)},
    "BR869": {"aircraft": "B781/B77M", "route": "台北 (TPE) ➔ 香港 (HKG)", "std": "12:40", "sta": "14:45", "dur": "2h 05m", "coords": (22.3080, 113.9185)}, 
    "BR870": {"aircraft": "B781/B77M", "route": "香港 (HKG) ➔ 台北 (TPE)", "std": "15:25", "sta": "17:20", "dur": "1h 55m", "coords": (25.0797, 121.2342)}, 

    # === 美洲長程線 ===
    "BR10":  {"aircraft": "B77B", "route": "台北 (TPE) ➔ 溫哥華 (YVR)", "std": "23:55", "sta": "19:40", "dur": "11h 45m", "coords": (49.1967, -123.1815)}, 
    "BR9":   {"aircraft": "B77B", "route": "溫哥華 (YVR) ➔ 台北 (TPE)", "std": "02:00", "sta": "05:25", "dur": "13h 25m", "coords": (25.0797, 121.2342)},
    "BR18":  {"aircraft": "B77M", "route": "台北 (TPE) ➔ 舊金山 (SFO)", "std": "19:40", "sta": "16:00", "dur": "11h 20m", "coords": (37.6189, -122.3750)},
    "BR17":  {"aircraft": "B77M", "route": "舊金山 (SFO) ➔ 台北 (TPE)", "std": "01:00", "sta": "05:25", "dur": "13h 25m", "coords": (25.0797, 121.2342)},
    "BR12":  {"aircraft": "B77M", "route": "台北 (TPE) ➔ 洛杉磯 (LAX)", "std": "19:20", "sta": "16:10", "dur": "11h 50m", "coords": (33.9416, -118.4085)},
    "BR11":  {"aircraft": "B77M", "route": "洛杉磯 (LAX) ➔ 台北 (TPE)", "std": "00:05", "sta": "05:10", "dur": "14h 05m", "coords": (25.0797, 121.2342)},
    "BR32":  {"aircraft": "B77M", "route": "台北 (TPE) ➔ 紐約 (JFK)", "std": "19:10", "sta": "22:05", "dur": "14h 55m", "coords": (40.6413, -73.7781)},
    "BR31":  {"aircraft": "B77M", "route": "紐約 (JFK) ➔ 台北 (TPE)", "std": "01:25", "sta": "05:15", "dur": "15h 50m", "coords": (25.0797, 121.2342)},
    "BR26":  {"aircraft": "B77M", "route": "台北 (TPE) ➔ 西雅圖 (SEA)", "std": "23:40", "sta": "19:30", "dur": "10h 50m", "coords": (47.4502, -122.3088)},
    "BR25":  {"aircraft": "B77M", "route": "西雅圖 (SEA) ➔ 台北 (TPE)", "std": "01:50", "sta": "05:10", "dur": "12h 20m", "coords": (25.0797, 121.2342)},
    "BR56":  {"aircraft": "B77M", "route": "台北 (TPE) ➔ 芝加哥 (ORD)", "std": "20:00", "sta": "20:30", "dur": "14h 30m", "coords": (41.9742, -87.9073)},
    "BR55":  {"aircraft": "B77M", "route": "芝加哥 (ORD) ➔ 台北 (TPE)", "std": "00:30", "sta": "05:00", "dur": "15h 30m", "coords": (25.0797, 121.2342)},
    "BR52":  {"aircraft": "B77M", "route": "台北 (TPE) ➔ 休士頓 (IAH)", "std": "22:00", "sta": "22:25", "dur": "14h 25m", "coords": (29.9902, -95.3368)},
    "BR51":  {"aircraft": "B77M", "route": "休士頓 (IAH) ➔ 台北 (TPE)", "std": "00:15", "sta": "05:55", "dur": "16h 40m", "coords": (25.0797, 121.2342)},
    "BR40":  {"aircraft": "B77M", "route": "台北 (TPE) ➔ 華盛頓 (IAD 模擬)", "std": "19:30", "sta": "21:30", "dur": "14h 00m", "coords": (38.9531, -77.4565)},
    "BR39":  {"aircraft": "B77M", "route": "華盛頓 (IAD 模擬) ➔ 台北 (TPE)", "std": "23:55", "sta": "05:30", "dur": "15h 35m", "coords": (25.0797, 121.2342)},
    
    # === 歐洲長程線 ===
    "BR87":  {"aircraft": "B77M", "route": "台北 (TPE) ➔ 巴黎 (CDG)", "std": "23:50", "sta": "08:45", "dur": "14h 55m", "coords": (49.0097, 2.5479)},
    "BR88":  {"aircraft": "B77M", "route": "巴黎 (CDG) ➔ 台北 (TPE)", "std": "11:20", "sta": "06:30", "dur": "13h 10m", "coords": (25.0797, 121.2342)},
    "BR67":  {"aircraft": "B77M", "route": "台北 (TPE) ➔ 倫敦 (LHR)", "std": "08:40", "sta": "19:25", "dur": "17h 45m", "coords": (51.4700, -0.4543)},
    "BR68":  {"aircraft": "B77M", "route": "倫敦 (LHR) ➔ 台北 (TPE)", "std": "21:35", "sta": "21:15", "dur": "16h 40m", "coords": (25.0797, 121.2342)},
    "BR65":  {"aircraft": "B78P", "route": "台北 (TPE) ➔ 維也納 (VIE)", "std": "23:30", "sta": "07:15", "dur": "14h 45m", "coords": (48.1103, 16.5697)},
    "BR66":  {"aircraft": "B78P", "route": "維也納 (VIE) ➔ 台北 (TPE)", "std": "12:25", "sta": "06:30", "dur": "12h 05m", "coords": (25.0797, 121.2342)},
    "BR71":  {"aircraft": "B78P", "route": "台北 (TPE) ➔ 慕尼黑 (MUC)", "std": "23:25", "sta": "07:25", "dur": "14h 00m", "coords": (48.3537, 11.7861)},
    "BR72":  {"aircraft": "B78P", "route": "慕尼黑 (MUC) ➔ 台北 (TPE)", "std": "11:40", "sta": "06:40", "dur": "13h 00m", "coords": (25.0797, 121.2342)},
    "BR95":  {"aircraft": "B78P", "route": "台北 (TPE) ➔ 米蘭 (MXP)", "std": "23:15", "sta": "06:30", "dur": "14h 15m", "coords": (45.6301, 8.7231)},
    "BR96":  {"aircraft": "B78P", "route": "米蘭 (MXP) ➔ 台北 (TPE)", "std": "11:20", "sta": "06:20", "dur": "13h 00m", "coords": (25.0797, 121.2342)},
    "BR75":  {"aircraft": "B77M", "route": "台北 (TPE) ➔ 阿姆斯特丹 (AMS)", "std": "08:40", "sta": "19:35", "dur": "16h 55m", "coords": (52.3105, 4.7683)},
    "BR76":  {"aircraft": "B77M", "route": "阿姆斯特丹 (AMS) ➔ 台北 (TPE)", "std": "21:40", "sta": "20:05", "dur": "16h 25m", "coords": (25.0797, 121.2342)},
    
    # === 圖片中新增並已由 AI 確認的航班 ===
    "BR5":  {"aircraft": "B77M", "route": "洛杉磯 (LAX) ➔ 台北 (TPE)", "std": "11:40", "sta": "17:00", "dur": "14h 20m", "coords": (25.0797, 121.2342)},
    "BR8":  {"aircraft": "B78P", "route": "台北 (TPE) ➔ 舊金山 (SFO)", "std": "10:15", "sta": "06:45", "dur": "11h 30m", "coords": (37.6189, -122.3750)},
    "BR15": {"aircraft": "B77M", "route": "洛杉磯 (LAX) ➔ 台北 (TPE)", "std": "00:30", "sta": "05:50", "dur": "14h 20m", "coords": (25.0797, 121.2342)},
    "BR28": {"aircraft": "B77M", "route": "台北 (TPE) ➔ 舊金山 (SFO)", "std": "23:40", "sta": "20:00", "dur": "11h 20m", "coords": (37.6189, -122.3750)},
    "BR36": {"aircraft": "B77M", "route": "台北 (TPE) ➔ 多倫多 (YYZ)", "std": "19:20", "sta": "21:35", "dur": "14h 15m", "coords": (43.6777, -79.6248)},
    "BR112": {"aircraft": "A321", "route": "台北 (TPE) ➔ 沖繩 (OKA)", "std": "06:45", "sta": "09:15", "dur": "1h 30m", "coords": (26.1958, 127.6525)},
    "BR131": {"aircraft": "B781", "route": "大阪 (KIX) ➔ 台北 (TPE)", "std": "13:10", "sta": "15:05", "dur": "2h 55m", "coords": (25.0797, 121.2342)},
    "BR132": {"aircraft": "B781", "route": "台北 (TPE) ➔ 大阪 (KIX)", "std": "08:30", "sta": "12:10", "dur": "2h 40m", "coords": (34.4320, 135.2304)},
    "BR165": {"aircraft": "A321", "route": "札幌 (CTS) ➔ 台北 (TPE)", "std": "13:00", "sta": "16:20", "dur": "4h 20m", "coords": (25.0797, 121.2342)},
    "BR166": {"aircraft": "A321", "route": "台北 (TPE) ➔ 札幌 (CTS)", "std": "06:55", "sta": "11:55", "dur": "4h 00m", "coords": (42.7752, 141.6923)},
    "BR169": {"aircraft": "B78P", "route": "首爾 (ICN) ➔ 台北 (TPE)", "std": "12:00", "sta": "13:35", "dur": "2h 35m", "coords": (25.0797, 121.2342)},
    "BR170": {"aircraft": "B78P", "route": "台北 (TPE) ➔ 首爾 (ICN)", "std": "07:30", "sta": "11:00", "dur": "2h 30m", "coords": (37.4602, 126.4407)},
    "BR215": {"aircraft": "B78P", "route": "台北 (TPE) ➔ 新加坡 (SIN)", "std": "09:25", "sta": "13:55", "dur": "4h 30m", "coords": (1.3644, 103.9915)},
    "BR315": {"aircraft": "B781", "route": "台北 (TPE) ➔ 布里斯本 (BNE)", "std": "09:10", "sta": "20:00", "dur": "8h 50m", "coords": (-27.3842, 153.1175)},
    "BR385": {"aircraft": "A321", "route": "台北 (TPE) ➔ 河內 (HAN)", "std": "14:40", "sta": "16:50", "dur": "3h 10m", "coords": (21.2212, 105.8072)},
    "BR386": {"aircraft": "A321", "route": "河內 (HAN) ➔ 台北 (TPE)", "std": "18:00", "sta": "21:55", "dur": "2h 55m", "coords": (25.0797, 121.2342)},
    "BR721": {"aircraft": "A333", "route": "上海浦東 (PVG) ➔ 台北 (TPE)", "std": "20:05", "sta": "22:00", "dur": "1h 55m", "coords": (25.0797, 121.2342)},
    "BR722": {"aircraft": "A333", "route": "台北 (TPE) ➔ 上海浦東 (PVG)", "std": "16:30", "sta": "18:25", "dur": "1h 55m", "coords": (31.1443, 121.8083)},
    "BR805": {"aircraft": "A333", "route": "台北 (TPE) ➔ 澳門 (MFM)", "std": "16:40", "sta": "18:35", "dur": "1h 55m", "coords": (22.1496, 113.5915)},
    "BR806": {"aircraft": "A333", "route": "澳門 (MFM) ➔ 台北 (TPE)", "std": "20:10", "sta": "22:05", "dur": "1h 55m", "coords": (25.0797, 121.2342)},
    
    # === 系統判定為 聯營/貨機/影像辨識錯誤 (保留防呆) ===
    "BR00": {"aircraft": "N/A", "route": "未明 (Typo) ➔ TBD", "std": "--:--", "sta": "--:--", "dur": "--h --m", "coords": (25.0797, 121.2342)},
    "BR45": {"aircraft": "N/A", "route": "未明 (Typo) ➔ TBD", "std": "--:--", "sta": "--:--", "dur": "--h --m", "coords": (25.0797, 121.2342)},
    "BR47": {"aircraft": "N/A", "route": "未明 (Typo) ➔ TBD", "std": "--:--", "sta": "--:--", "dur": "--h --m", "coords": (25.0797, 121.2342)},
    "BR6535": {"aircraft": "B77F", "route": "台北 (TPE) ➔ 香港 (HKG) [貨機]", "std": "23:25", "sta": "01:20", "dur": "1h 55m", "coords": (22.3080, 113.9185)},
    "BR7187": {"aircraft": "N/A", "route": "聯營/包機 ➔ TBD", "std": "--:--", "sta": "--:--", "dur": "--h --m", "coords": (25.0797, 121.2342)},
    "BR7188": {"aircraft": "N/A", "route": "聯營/包機 ➔ TBD", "std": "--:--", "sta": "--:--", "dur": "--h --m", "coords": (25.0797, 121.2342)},
    "BR8778": {"aircraft": "N/A", "route": "聯營/包機 ➔ TBD", "std": "--:--", "sta": "--:--", "dur": "--h --m", "coords": (25.0797, 121.2342)}
}

# ==========================================
# 每日自動抓取並更新常態資料庫 (一天僅執行一次)
# ==========================================
@st.cache_data(ttl=86400, show_spinner="🔄 每日例行更新常態航班資料庫 (一天僅執行一次，約需 30-60 秒)...")
def get_daily_updated_db():
    updated_db = {}
    for k, v in MASTER_STATIC_DB.items():
        updated_db[k] = v.copy()

    def fetch_flight_times(flight_no, info):
        if info.get("route") and ("Typo" in info["route"] or "聯營" in info["route"]):
            return flight_no, info
            
        fa_flight_id = flight_no.upper().replace("BR", "EVA")
        fa_url = f"[https://zh-tw.flightaware.com/live/flight/](https://zh-tw.flightaware.com/live/flight/){fa_flight_id}"
        payload = {
            'api_key': "c84488b98c1d6af5b8b94b306c2e6001",
            'url': fa_url
        }
        try:
            res = requests.get('[http://api.scraperapi.com](http://api.scraperapi.com)', params=payload, timeout=25)
            if res.status_code == 200:
                soup = BeautifulSoup(res.text, "html.parser")
                scripts = soup.find_all("script")
                for s in scripts:
                    if s.string and "__APOLLO_STATE__" in s.string:
                        match = re.search(r'__APOLLO_STATE__\s*=\s*({.*?});', s.string, re.DOTALL)
                        if match:
                            apollo_data = json.loads(match.group(1))
                            today_str = datetime.now(TW_TZ).strftime("%Y-%m-%d")
                            
                            for key, val in apollo_data.items():
                                if isinstance(val, dict) and "gateDepartureTimes" in val and "gateArrivalTimes" in val:
                                    s_ts = val.get("gateDepartureTimes", {}).get("scheduled") or val.get("takeoffTimes", {}).get("scheduled")
                                    a_ts = val.get("gateArrivalTimes", {}).get("scheduled") or val.get("landingTimes", {}).get("scheduled")
                                    
                                    if s_ts:
                                        dt_str = datetime.fromtimestamp(s_ts, TW_TZ).strftime("%Y-%m-%d")
                                        if dt_str == today_str:
                                            info["std"] = datetime.fromtimestamp(s_ts, TW_TZ).strftime("%H:%M")
                                            if a_ts: 
                                                info["sta"] = datetime.fromtimestamp(a_ts, TW_TZ).strftime("%H:%M")
                                                if a_ts > s_ts:
                                                    total_mins = int((a_ts - s_ts) / 60)
                                                    h = total_mins // 60
                                                    m = total_mins % 60
                                                    info["dur"] = f"{h}h {m:02d}m"
                                            return flight_no, info
        except Exception:
            pass
        return flight_no, info

    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        future_to_flight = {executor.submit(fetch_flight_times, f, info): f for f, info in updated_db.items()}
        for future in concurrent.futures.as_completed(future_to_flight):
            try:
                f_no, updated_info = future.result()
                updated_db[f_no] = updated_info
            except:
                pass

    return updated_db

# ----------------- 獲取單一航班資訊 (結合爬蟲與即時天氣) -----------------
def fetch_flight_info(flight_num):
    dynamic_db = get_daily_updated_db()
    
    if flight_num in dynamic_db:
        info = dynamic_db[flight_num]
        weather_data = get_real_weather(info['coords'][0], info['coords'][1])
        return {
            "aircraft": info['aircraft'],
            "route": info['route'],
            "std": info['std'],
            "sta": info['sta'],
            "duration": info['dur'],
            "weather": weather_data
        }
    else:
        return {
            "aircraft": "N/A",
            "route": "N/A ➔ N/A",
            "std": "N/A",
            "sta": "N/A",
            "duration": "N/A",
            "weather": {"temp": "--°C", "rain": "未知", "snow": "未知"}
        }

def get_default_data():
    return [
        {"Date": 1, "Day": "WED", "Content": "758\n757\nB781"},
        {"Date": 2, "Day": "THU", "Content": "DO"},
        {"Date": 3, "Day": "FRI", "Content": "867\n868\nB78P"},
        {"Date": 4, "Day": "SAT", "Content": "(4)\nQ06 SCS\n06:45-09:45\nA330"},
        {"Date": 5, "Day": "SUN", "Content": "(5)\nS05 SCS\n05:00-08:00"},
        {"Date": 6, "Day": "MON", "Content": "ADO"},
        {"Date": 7, "Day": "TUE", "Content": "265\n266\nA333"},
        {"Date": 8, "Day": "WED", "Content": "AL"},
        {"Date": 9, "Day": "THU", "Content": "AL"},
        {"Date": 10, "Day": "FRI", "Content": "AL"},
        {"Date": 11, "Day": "SAT", "Content": "YH"},
        {"Date": 12, "Day": "SUN", "Content": "YI"},
        {"Date": 13, "Day": "MON", "Content": "ADO"},
        {"Date": 14, "Day": "TUE", "Content": "10\nB77B"},
        {"Date": 15, "Day": "WED", "Content": "LO"},
        {"Date": 16, "Day": "THU", "Content": "9\nB77B"}, 
        {"Date": 17, "Day": "FRI", "Content": "9\nB77B"},
        {"Date": 18, "Day": "SAT", "Content": "ADO"},
        {"Date": 19, "Day": "SUN", "Content": "DO"},
        {"Date": 20, "Day": "MON", "Content": "S05 SCS\n05:00-08:00"},
        {"Date": 21, "Day": "TUE", "Content": "ADO"},
        {"Date": 22, "Day": "WED", "Content": "867\n868\nB77M"},
        {"Date": 23, "Day": "THU", "Content": "DO"},
        {"Date": 24, "Day": "FRI", "Content": "158\n157\nA333"},
        {"Date": 25, "Day": "SAT", "Content": "211\n212 PNC\nB77M"},
        {"Date": 26, "Day": "SUN", "Content": "277\n278\nA333"},
        {"Date": 27, "Day": "MON", "Content": "DO"},
        {"Date": 28, "Day": "TUE", "Content": "712\n711\nB77M"},
        {"Date": 29, "Day": "WED", "Content": "281\n282\nB78P"},
        {"Date": 30, "Day": "THU", "Content": "712\n711\nB77M"}
    ]

def load_shared_data(active_path=None):
    if active_path and os.path.exists(active_path):
        json_path = os.path.splitext(active_path)[0] + ".json"
        
        if os.path.exists(json_path):
            try:
                with open(json_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                return pd.DataFrame(data)
            except Exception:
                pass
                
    if os.path.exists(SHARED_FILE):
        try:
            with open(SHARED_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
            return pd.DataFrame(data)
        except Exception:
            pass
            
    return pd.DataFrame(get_default_data())

def extract_flights_from_content(content):
    lines = str(content).split('\n')
    flights = []
    for line in lines:
        line = line.strip()
        if re.match(r'^(?:BR)?\d+(?:\s*PNC)?(?:\s*\(?TSA\)?)?$', line, flags=re.IGNORECASE):
            num = re.search(r'\d+', line).group()
            flights.append(f"BR{num}")
    return flights

def generate_detailed_table(df):
    table_rows = []
    for index, row in df.iterrows():
        date_str = str(row['Date'])
        raw_content = str(row['Content']) if pd.notna(row['Content']) else ""
        flights = extract_flights_from_content(raw_content)
        
        if not flights:
            display_text = raw_content.replace('\n', ' / ').strip()
            table_rows.append({
                "Date": date_str,
                "Bound": "--", 
                "Flight": display_text if display_text else "無紀錄",
                "FROM": "--",
                "To": "--",
                "AIRCRAFT": "--",
                "STD": "--",
                "STA": "--",
                "Total Time": "--"
            })
        else:
            for f in flights:
                info = fetch_flight_info(f)
                route_parts = info['route'].split('➔')
                from_loc = route_parts[0].strip() if len(route_parts) > 0 else "N/A"
                to_loc = route_parts[1].strip() if len(route_parts) > 1 else "N/A"
                
                if "TPE" in from_loc or "桃園" in from_loc or "台北" in from_loc or "松山" in from_loc or "TSA" in from_loc:
                    bound_status = "去程"
                elif "TPE" in to_loc or "桃園" in to_loc or "台北" in to_loc or "松山" in to_loc or "TSA" in to_loc:
                    bound_status = "回程"
                else:
                    bound_status = "--"
                
                table_rows.append({
                    "Date": date_str,
                    "Bound": bound_status,
                    "Flight": f,
                    "FROM": from_loc,
                    "To": to_loc,
                    "AIRCRAFT": info['aircraft'],
                    "STD": info['std'],
                    "STA": info['sta'],
                    "Total Time": info['duration']
                })
            
    if not table_rows:
        return pd.DataFrame()
    return pd.DataFrame(table_rows)

def parse_and_format_content(content, enable_parsing=True, active_schedule_name=""):
    if not enable_parsing:
        return f"<div style='font-size:15px;'>{str(content).replace(chr(10), '<br>')}</div>"

    lines = str(content).split('\n')
    formatted_lines = []
    red_codes = ['DO', 'ADO', 'AL']
    active_sched_param = f"&schedule={active_schedule_name}" if active_schedule_name else ""
    
    for line in lines:
        line = line.strip()
        if not line: continue
        
        if line in ['AL']: 
            formatted_lines.append("<div style='color:#FF3B30; font-weight:700; font-size:16px; margin: 4px 0;'>🏖️ 特休 (AL)</div>")
        elif line in ['DO', 'ADO']: 
            formatted_lines.append(f"<div style='color:#FF3B30; font-weight:700; font-size:16px; margin: 4px 0;'>🏠 休假 ({line})</div>")
        
        elif re.match(r'^Y[A-Z]$', line): 
            formatted_lines.append(f"<div style='color:#FF3B30; font-weight:700; font-size:16px; margin: 4px 0;'>🏖️ 年度休假 ({line})</div>")
        
        elif re.match(r'^\(\d+\)$', line): 
            formatted_lines.append(f"<div style='color:#8E8E93; font-size: 13px; font-weight:600; margin-bottom: 4px;'>{line}</div>")
        elif "SCS" in line: 
            formatted_lines.append(f"<div style='color:#FF9500; font-weight:800; font-size:16px; margin: 4px 0;'>🚨 待命 ({line.split()[0]})</div>")
        elif re.match(r'^\d{2}:\d{2}-\d{2}:\d{2}$', line): 
            formatted_lines.append(f"<div style='color:#AF52DE; font-weight:700; font-size:15px; margin: 4px 0;'>🕒 {line.replace('-', '~')}</div>")
        
        elif "PNC" in line.upper() and re.search(r'\d+', line):
            f_num = re.search(r'\d+', line).group()
            flight_url = f"?flight=BR{f_num}{active_sched_param}"
            formatted_lines.append(f"<a href='{flight_url}' target='_self' style='display:inline-block; text-decoration:none; color:#007AFF; font-weight:800; font-size:16px; margin: 4px 0; background-color:#E5F1FF; padding:2px 6px; border-radius:6px; border: 1px dashed #007AFF;'>💺 BR{f_num} (乘客返回)</a>")
        
        elif "TSA" in line.upper() and re.search(r'\d+', line):
            f_num = re.search(r'\d+', line).group()
            flight_url = f"?flight=BR{f_num}{active_sched_param}"
            formatted_lines.append(f"<a href='{flight_url}' target='_self' style='display:inline-block; text-decoration:none; color:#10B981; font-weight:800; font-size:16px; margin: 4px 0; background-color:#D1FAE5; padding:2px 6px; border-radius:6px; border: 1px dashed #10B981;'>✈️ BR{f_num} (松山)</a>")
            
        elif re.match(r'^\d+$', line): 
            flight_url = f"?flight=BR{line}{active_sched_param}"
            formatted_lines.append(f"<a href='{flight_url}' target='_self' style='display:inline-block; text-decoration:none; color:#007AFF; font-weight:800; font-size:16px; margin: 4px 0; background-color:#E5F1FF; padding:2px 6px; border-radius:6px;'>✈️ BR{line}</a>")
        
        elif re.match(r'^[AB]\d{2,3}[a-zA-Z0-9]?$', line): 
            formatted_lines.append(f"<div style='color:#34C759; font-weight:700; font-size:15px; margin: 4px 0;'>🛩️ 機型: {line}</div>")
        elif line in red_codes: 
            formatted_lines.append(f"<div style='color:#FF3B30; font-weight:700; font-size:16px; margin: 4px 0;'>{line}</div>")
        else: 
            formatted_lines.append(f"<div style='font-size:15px; margin: 4px 0;'>{line}</div>")
            
    return "".join(formatted_lines)


def display_flight_info_panel(flight_num):
    info = fetch_flight_info(flight_num)
    
    # 【整合者修改】：修正被 Markdown 語法污染的網址，確保 href 內是純淨的 https:// 開頭
    google_search_url = f"https://www.google.com/search?q={flight_num}"
    
    title_html = f"### 🛫 航班詳細資訊: <a href='{google_search_url}' target='_blank' style='color: #007AFF; text-decoration: none; border-bottom: 2px dashed #007AFF; padding-bottom: 2px;' title='點擊查看 Google 即時航班動態'>{flight_num} 🔍</a>"
    st.markdown(title_html, unsafe_allow_html=True)
    
    st.markdown(f"<span style='font-size:18px;'>**🛬 回程航班:** {flight_num}</span>", unsafe_allow_html=True)
    st.markdown(f"<span style='font-size:18px;'>**✈️ 機型:** {info['aircraft']}</span>", unsafe_allow_html=True)
    st.markdown(f"<span style='font-size:18px;'>**🏢 航線:** {info['route']}</span>", unsafe_allow_html=True)
    
    weather_html = f"""
    <div style="background-color: #007AFF; padding: 18px; border-radius: 12px; color: white; margin-top: 15px; margin-bottom: 15px; box-shadow: 0 4px 10px rgba(0,122,255,0.2);">
        <div style="font-size: 15px; margin-bottom: 8px; font-weight: 600; opacity: 0.9;">☁️ 目的地/外站 出發天氣</div>
        <div style="font-size: 20px; font-weight: 800; letter-spacing: 1px;">
            🌡️ {info['weather']['temp']} &nbsp;|&nbsp; ☁️ {info['weather']['rain']} &nbsp;|&nbsp; ❌ {info['weather']['snow']}
        </div>
    </div>
    """
    st.markdown(weather_html, unsafe_allow_html=True)
    
    st.markdown(f"<span style='font-size:16px;'>**⏱️ STD:**</span> <span style='float:right; font-weight:bold; font-size:18px;'>{info['std']}</span>", unsafe_allow_html=True)
    st.markdown("<hr style='margin: 12px 0px; border-top: 1px solid #E5E5EA;'>", unsafe_allow_html=True)
    st.markdown(f"<span style='font-size:16px;'>**🛬 STA:**</span> <span style='float:right; font-weight:bold; font-size:18px;'>{info['sta']}</span>", unsafe_allow_html=True)
    st.markdown("<hr style='margin: 12px 0px; border-top: 1px solid #E5E5EA;'>", unsafe_allow_html=True)
    st.markdown(f"<span style='font-size:16px;'>**⏱️ 總時間:**</span> <span style='float:right; font-weight:900; color:#007AFF; font-size:18px;'>{info['duration']}</span>", unsafe_allow_html=True)

def get_history_files():
    try:
        files = glob.glob(os.path.join(HISTORY_DIR, "*.*"))
        img_files = [f for f in files if f.lower().endswith(('.png', '.jpg', '.jpeg'))]
        img_files.sort(key=os.path.getmtime, reverse=True)
        return img_files
    except Exception:
        return []

def get_saved_tables():
    try:
        files = glob.glob(os.path.join(SAVED_TABLES_DIR, "*.json"))
        files.sort(key=os.path.getmtime, reverse=True)
        return files
    except Exception:
        return []

def main():
    tw_now = datetime.now(TW_TZ)
    current_day_number = tw_now.day

    if 'initialized' not in st.session_state:
        st.session_state.selected_date = current_day_number
        st.session_state.selected_flight = None
        
        recovered_path = None
        if os.path.exists(CURRENT_ACTIVE_FILE):
            try:
                with open(CURRENT_ACTIVE_FILE, "r", encoding="utf-8") as f:
                    saved_path = f.read().strip()
                    if saved_path and os.path.exists(saved_path):
                        recovered_path = saved_path
            except Exception:
                pass
                
        st.session_state.active_schedule = recovered_path
        st.session_state.api_key = "AIzaSyA4L4bGHxOmKdcaZxh9qLLtdtAKb5ZvmPY" 
        st.session_state.initialized = True

    if "schedule" in st.query_params:
        sched = st.query_params["schedule"]
        if sched and os.path.exists(sched):
            st.session_state.active_schedule = sched
            try:
                with open(CURRENT_ACTIVE_FILE, "w", encoding="utf-8") as f:
                    f.write(sched)
            except Exception:
                pass

    if "date" in st.query_params:
        st.session_state.selected_date = int(st.query_params["date"])
        st.session_state.selected_flight = None
        st.query_params.clear()
        
    if "flight" in st.query_params:
        st.session_state.selected_flight = st.query_params["flight"]
        st.session_state.selected_date = None
        st.query_params.clear()

    with st.sidebar:
        st.header("⚙️ 班表管理設定")
        
        st.subheader("💾 讀取已儲存的班表 (免 API)")
        saved_tables = get_saved_tables()
        if saved_tables:
            table_options = {"None": "--- 尚未選擇 ---"}
            for f in saved_tables:
                table_options[f] = f"📊 {os.path.basename(f).replace('.json', '')}"
                
            selected_table = st.selectbox(
                "選擇並直接載入：", 
                options=["None"] + saved_tables,
                format_func=lambda x: table_options[x]
            )
            
            if selected_table != "None":
                if st.button("📥 載入此班表", type="primary", use_container_width=True):
                    base_path = os.path.splitext(selected_table)[0]
                    img_found = None
                    for ext in ['.png', '.jpg', '.jpeg']:
                        if os.path.exists(base_path + ext):
                            img_found = base_path + ext
                            break
                    
                    final_path = img_found if img_found else selected_table
                    st.session_state.active_schedule = final_path
                    
                    try:
                        with open(CURRENT_ACTIVE_FILE, "w", encoding="utf-8") as f:
                            f.write(final_path)
                    except Exception:
                        pass
                        
                    st.success(f"已成功載入: {os.path.basename(selected_table).replace('.json', '')}")
                    st.rerun()

                with st.expander("✏️ 重新命名此班表"):
                    old_base_name = os.path.basename(selected_table).replace('.json', '')
                    new_name = st.text_input("輸入新名稱", value=old_base_name)
                    if st.button("💾 確認重命名", type="primary", use_container_width=True):
                        if new_name.strip() and new_name != old_base_name:
                            new_json_path = os.path.join(SAVED_TABLES_DIR, f"{new_name}.json")
                            if os.path.exists(new_json_path):
                                st.error("名稱已存在，請換一個名稱！")
                            else:
                                try:
                                    os.rename(selected_table, new_json_path)
                                    old_base_path = os.path.splitext(selected_table)[0]
                                    for ext in ['.png', '.jpg', '.jpeg']:
                                        if os.path.exists(old_base_path + ext):
                                            os.rename(old_base_path + ext, os.path.join(SAVED_TABLES_DIR, f"{new_name}{ext}"))
                                            break
                                    
                                    if st.session_state.active_schedule and old_base_name in st.session_state.active_schedule:
                                        img_ext = os.path.splitext(st.session_state.active_schedule)[1]
                                        new_active = os.path.join(SAVED_TABLES_DIR, f"{new_name}{img_ext}")
                                        st.session_state.active_schedule = new_active
                                        try:
                                            with open(CURRENT_ACTIVE_FILE, "w", encoding="utf-8") as f:
                                                f.write(new_active)
                                        except Exception:
                                            pass
                                        
                                    st.success("重命名成功！")
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"重命名失敗: {e}")
        else:
            st.info("目前沒有已儲存的班表。")
            
        st.markdown("---")
        
        if HAS_AI_MODULES:
            with st.expander("🔑 系統進階設定 (AI 辨識)", expanded=False):
                st.session_state.api_key = st.text_input("請輸入 Google Gemini API Key", value=st.session_state.api_key, type="password")
                st.caption("申請網址: [https://aistudio.google.com/app/apikey](https://aistudio.google.com/app/apikey)")
                if not st.session_state.api_key:
                    st.warning("未輸入 API Key，上傳圖片將使用預設資料範本。")
        else:
            st.error("⚠️ 缺少 AI 辨識套件！\n請在終端機執行：\n`pip install google-genai pillow`\n\n目前將以無 AI 模式運行。")
        
        st.markdown("---")
        st.subheader("🖼️ 上傳新班表圖片")
        st.info("💡 支援 PNG, JPG。若有安裝套件並設定 API Key，系統將自動辨識圖片內容。")
        
        uploaded_image = st.file_uploader("請選擇班表圖片", type=['png', 'jpg', 'jpeg'])
        if uploaded_image is not None:
            save_path = os.path.join(HISTORY_DIR, uploaded_image.name)
            base_name = os.path.splitext(uploaded_image.name)[0]
            json_path = os.path.join(HISTORY_DIR, f"{base_name}.json")
            
            try:
                with open(save_path, "wb") as f:
                    f.write(uploaded_image.getbuffer())
                
                if not os.path.exists(json_path):
                    if HAS_AI_MODULES and st.session_state.api_key:
                        with st.spinner('🤖 AI 視覺模組正在努力解讀班表中，請稍候...'):
                            ai_data = extract_schedule_with_ai(save_path, st.session_state.api_key)
                            if ai_data:
                                with open(json_path, 'w', encoding='utf-8') as f:
                                    json.dump(ai_data, f, ensure_ascii=False, indent=4)
                                st.success("✨ 解析完成！已建立專屬資料檔。")
                    else:
                        current_df = pd.DataFrame(get_default_data())
                        current_df.to_json(json_path, orient='records', force_ascii=False)
                        st.success("✅ 圖片上傳成功！已套用預設資料範本。")

            except Exception as e:
                st.error(f"儲存失敗: {e}")
            
            history_files = get_history_files()
            if len(history_files) > 3:
                for old_file in history_files[3:]:
                    try:
                        os.remove(old_file)
                        old_base = os.path.splitext(old_file)[0]
                        if os.path.exists(f"{old_base}.json"):
                            os.remove(f"{old_base}.json")
                    except Exception:
                        pass
                        
        st.markdown("---")
        st.subheader("🔄 選擇並套用歷史班表圖片")
        
        history_files = get_history_files()
        
        if not history_files:
            st.warning("目前沒有班表紀錄，請先上傳圖片。")
        else:
            options_dict = {f: f"📅 {os.path.basename(f)}" for f in history_files}
            
            default_index = 0
            if st.session_state.active_schedule in history_files:
                default_index = history_files.index(st.session_state.active_schedule)
                
            selected_file = st.selectbox(
                "從最近 3 次的紀錄中選擇：", 
                options=history_files, 
                format_func=lambda x: options_dict[x],
                index=default_index
            )
            
            if st.button("✅ 確定套用此班表", type="primary", use_container_width=True):
                st.session_state.active_schedule = selected_file
                
                try:
                    with open(CURRENT_ACTIVE_FILE, "w", encoding="utf-8") as f:
                        f.write(selected_file)
                except Exception:
                    pass
                    
                st.success("切換成功！日曆資料與圖片已同步綁定。")
                st.rerun()

            st.markdown("<br>", unsafe_allow_html=True)
            with st.expander("🛠️ 圖片解析失敗？進階修復選項", expanded=True):
                st.info("若畫面顯示舊版或預設班表，可能是上傳同名檔案導致未觸發 AI，或前次解析中斷。請使用下方按鈕強制破解覆寫。")
                if st.button("🔥 強制重新辨識此圖片 (消耗 API)", type="primary", use_container_width=True):
                    if not HAS_AI_MODULES or not st.session_state.api_key:
                        st.error("請先確保上方已輸入有效的 API Key 且支援 AI 模組！")
                    elif not st.session_state.active_schedule or not os.path.exists(st.session_state.active_schedule):
                        st.warning("找不到目前套用的圖片檔案，請先在上方選擇套用的圖片。")
                    else:
                        target_img = st.session_state.active_schedule
                        target_json = os.path.splitext(target_img)[0] + ".json"
                        
                        with st.spinner("🤖 正在強制重新解讀該班表圖片，請稍候..."):
                            try:
                                new_data = extract_schedule_with_ai(target_img, st.session_state.api_key, fallback_default=False)
                                if new_data:
                                    with open(target_json, 'w', encoding='utf-8') as f:
                                        json.dump(new_data, f, ensure_ascii=False, indent=4)
                                    st.success("✨ 強制辨識且覆寫成功！即將重新載入...")
                                    time.sleep(1)  
                                    st.rerun()
                            except Exception as parse_error:
                                st.error(f"❌ {str(parse_error)}")

    st.title("✈️ 共享智慧班表系統")
    
    df = load_shared_data(st.session_state.active_schedule)
    
    col1, col2 = st.columns([1, 1])
    with col1:
        enable_parsing = st.toggle("✨ 啟動智慧解讀模式", value=True)
    with col2:
        st.markdown(f"<div style='text-align: right; color: #8E8E93; font-weight: 600;'>🇹🇼 台灣現在時間: {tw_now.strftime('%m/%d %H:%M')}</div>", unsafe_allow_html=True)
    
    st.markdown("---")
    
    st.subheader("📋 本月航班詳細列表")
    detailed_table = generate_detailed_table(df)
        
    if not detailed_table.empty:
        st.dataframe(detailed_table, hide_index=True, use_container_width=True)
        
        with st.expander("📥 儲存此表格到左側選單 (免耗費 API)", expanded=False):
            save_name = st.text_input("請輸入您要儲存的名稱 (例如: 2026_05_Justin)")
            if st.button("確定儲存"):
                if save_name.strip() == "":
                    st.warning("名稱不能為空！")
                else:
                    target_json = os.path.join(SAVED_TABLES_DIR, f"{save_name}.json")
                    if os.path.exists(target_json):
                        st.error("此名稱已存在，請更換名稱或先重新命名舊檔！")
                    elif st.session_state.active_schedule and os.path.exists(st.session_state.active_schedule):
                        try:
                            src_img = st.session_state.active_schedule
                            img_ext = os.path.splitext(src_img)[1]
                            dest_img = os.path.join(SAVED_TABLES_DIR, f"{save_name}{img_ext}")
                            shutil.copy(src_img, dest_img)
                            
                            src_json = os.path.splitext(src_img)[0] + ".json"
                            if os.path.exists(src_json):
                                shutil.copy(src_json, target_json)
                                st.success(f"🎉 成功！已將班表儲存為 `{save_name}`，包含圖片對照，未來可從左側直接讀取！")
                            else:
                                st.warning("只儲存了圖片，找不到對應的 JSON 資料。")
                        except Exception as e:
                            st.error(f"儲存過程發生錯誤: {e}")
                    else:
                        st.warning("目前沒有綁定原始圖片，無法儲存。請先上傳或選擇一個班表！")
    else:
        st.info("此班表中未偵測到詳細航班資訊。")
    
    st.markdown("---")

    today_flights = []
    day_data = df[df['Date'] == current_day_number]
    if not day_data.empty:
        today_flights = extract_flights_from_content(day_data.iloc[0]['Content'])

    col_sel, col_info = st.columns([1, 2])
    
    with col_sel:
        st.subheader("🔍 航班快速查詢")
        st.info("💡 **提示：**\n1. 點擊下方日曆的 **藍色航班號碼** 查單班。\n2. 點擊日曆左上角的 **日期數字** 顯示當日全部航班！", icon="👆")
        
        if today_flights:
            st.success(f"今日 ({current_day_number} 號) 快速捷徑：")
            for flight in today_flights:
                if st.button(f"查看今日 {flight} 資訊", type="primary", use_container_width=True):
                    st.session_state.selected_flight = flight
                    st.session_state.selected_date = None

        if st.session_state.selected_flight:
            st.markdown("---")
            st.subheader("🌐 即時航班動態")
            current_f = st.session_state.selected_flight
            
            # 【整合者修改】：已經將疊影、錯位的代碼刪除，保留唯一乾淨的 google_card_html 宣告
            google_card_html = f"""
            <div style="border: 1px solid #dfe1e5; border-radius: 8px; padding: 16px; margin-top: 10px; background-color: #ffffff; box-shadow: 0 1px 6px rgba(32,33,36,.15); transition: box-shadow 0.3s ease-in-out;">
                <div style="display: flex; align-items: center; margin-bottom: 12px;">
                    <span style="background-color: #4285F4; color: white; border-radius: 50%; width: 24px; height: 24px; display: inline-flex; justify-content: center; align-items: center; font-weight: bold; font-family: Arial, sans-serif; font-size: 14px; margin-right: 10px;">G</span>
                    <span style="font-family: Arial, sans-serif; font-size: 14px; color: #5f6368;">Google 航班直接搜尋</span>
                </div>
                <div style="font-size: 18px; font-weight: 500; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; color: #1a0dab; margin-bottom: 12px; letter-spacing: 0.5px;">長榮航空 {current_f}</div>
                <a href="https://www.google.com/search?q={current_f}" target="_blank" style="display: block; width: 100%; background-color: #f8f9fa; border: 1px solid #dadce0; border-radius: 6px; color: #3c4043; cursor: pointer; font-family: Arial, sans-serif; font-weight: bold; font-size: 14px; padding: 10px 0; text-align: center; text-decoration: none; box-sizing: border-box;">🔍 點擊查看起降與登機門資訊</a>
            </div>
            """
            st.markdown(google_card_html, unsafe_allow_html=True)

    with col_info:
        if st.session_state.selected_flight:
            with st.container():
                display_flight_info_panel(st.session_state.selected_flight)
                
        elif st.session_state.selected_date:
            date_val = st.session_state.selected_date
            selected_day_data = df[df['Date'] == date_val]
            
            if not selected_day_data.empty:
                raw_content = selected_day_data.iloc[0]['Content']
                flights_on_date = extract_flights_from_content(raw_content)
                
                if flights_on_date:
                    st.markdown(f"#### 📅 {date_val} 號 執勤航班總覽")
                    for idx, f in enumerate(flights_on_date):
                        with st.container():
                            display_flight_info_panel(f)
                        if idx < len(flights_on_date) - 1:
                            st.markdown("<hr style='border: 2px dashed #AF52DE; margin: 30px 0;'>", unsafe_allow_html=True)
                else:
                    st.info(f"📅 您選擇的日期 ({date_val} 號) 無排定航班，或為休假/待命。好好休息！☕")
        else:
            st.warning("👈 尚未選擇航班或日期。請點擊下方日曆。")

    st.markdown("---")
    st.subheader("🗓️ 班表總覽")
    
    days_of_week = ["SUN", "MON", "TUE", "WED", "THU", "FRI", "SAT"]
    first_day_str = str(df.iloc[0]['Day']).upper()
    start_day_index = days_of_week.index(first_day_str) if first_day_str in days_of_week else 0

    grid_html = "<div style='width: 100%; overflow-x: auto; padding-bottom: 15px;'>\n<div style='display: grid; grid-template-columns: repeat(7, minmax(130px, 1fr)); gap: 12px; min-width: 900px;'>"

    for day in days_of_week:
        color = "#FF3B30" if day in ["SUN", "SAT"] else "#1C1C1E"
        grid_html += f"\n<div style='text-align: center; color: {color}; font-weight:800; font-size:16px; padding-bottom: 8px; border-bottom: 2px solid #E5E5EA;'>{day}</div>"

    current_day = 1
    total_days = len(df) 
    
    current_active = st.session_state.active_schedule if st.session_state.active_schedule else ""

    for week in range(6):
        if current_day > total_days: break
        for day_idx in range(7):
            if week == 0 and day_idx < start_day_index:
                grid_html += "\n<div style='height: 180px; background-color: #F2F2F7; border-radius: 12px;'></div>"
            elif current_day <= total_days:
                day_data = df[df['Date'] == current_day].iloc[0]
                raw_content = day_data['Content']
                
                parsed_html = parse_and_format_content(raw_content, enable_parsing, current_active)
                
                is_today = (current_day == current_day_number)
                if is_today:
                    bg_color = "#FFFFE5" 
                    border_style = "2px solid #007AFF" 
                    box_shadow = "0 4px 12px rgba(0, 122, 255, 0.15)"
                    today_badge = "<span style='float: right; background-color: #007AFF; color: white; padding: 2px 8px; border-radius: 12px; font-size: 11px; font-weight:800;'>TODAY</span>"
                else:
                    bg_color = "#FFFAFA" if day_idx in [0, 6] else "#FFFFFF"
                    border_style = "1px solid #E5E5EA"
                    box_shadow = "0 2px 8px rgba(0, 0, 0, 0.04)"
                    today_badge = ""
                
                date_color = "#FF3B30" if day_idx in [0, 6] else "#1C1C1E"
                
                active_sched_param = f"&schedule={current_active}" if current_active else ""
                date_link_html = f"<a href='?date={current_day}{active_sched_param}' target='_self' style='text-decoration:none; color:{date_color}; cursor:pointer;'>{current_day}</a>"

                grid_html += f"\n<div style='height: 180px; padding: 12px; background-color: {bg_color}; border: {border_style}; border-radius: 12px; box-shadow: {box_shadow}; overflow-y: auto; line-height: 1.6;'><div style='font-size: 18px; font-weight: 800; border-bottom: 1px solid #E5E5EA; padding-bottom: 4px; margin-bottom: 8px;'>{date_link_html} {today_badge}</div><div>{parsed_html}</div></div>"
                current_day += 1
            else:
                grid_html += "\n<div style='height: 180px; background-color: #F2F2F7; border-radius: 12px;'></div>"

    grid_html += "\n</div>\n</div>" 
    st.markdown(grid_html, unsafe_allow_html=True)

    st.markdown("---")
    st.subheader("🖼️ 原始班表對照")
    
    if st.session_state.active_schedule and os.path.exists(st.session_state.active_schedule):
        if st.session_state.active_schedule.lower().endswith(('.png', '.jpg', '.jpeg')):
            st.image(st.session_state.active_schedule, caption=f"目前套用的原始班表: {os.path.basename(st.session_state.active_schedule)}", use_container_width=True)
        else:
            st.info("💡 雖然已套用資料，但目前沒有綁定支援的圖片格式供顯示。")
    else:
        st.info("💡 尚未套用任何班表圖片，或找不到該圖片檔案。請由左側邊欄上傳或選擇套用。")

if __name__ == "__main__":
    main()
