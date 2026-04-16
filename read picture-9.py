import streamlit as st
import pandas as pd
import re
import json
import os
from datetime import datetime
import pytz
import requests 

# 頁面基本設定
st.set_page_config(page_title="共用智慧班表系統", page_icon="✈️", layout="wide")

SHARED_FILE = "shared_schedule.json"

def get_real_weather(lat, lon):
    try:
        url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current_weather=true"
        response = requests.get(url, timeout=3)
        if response.status_code == 200:
            data = response.json()['current_weather']
            temp = data['temperature']
            code = data['weathercode']
            
            rain = "有雨" if code in [51,53,55,61,63,65,80,81,82,95,96,99] else "無雨"
            snow = "有雪" if code in [71,73,75,77,85,86] else "無雪"
            
            return {"temp": f"{temp}°C", "rain": rain, "snow": snow}
    except Exception as e:
        pass 
    
    return {"temp": "--°C", "rain": "未知", "snow": "未知"}

def fetch_flight_info(flight_num):
    real_flight_db = {
        "BR9":   {"aircraft": "B77B", "route": "溫哥華 (YVR) ➔ 桃園 (TPE)", "std": "02:00", "sta": "05:25", "dur": "13h 25m", "coords": (49.1967, -123.1815)},
        "BR10":  {"aircraft": "B77B", "route": "桃園 (TPE) ➔ 溫哥華 (YVR)", "std": "23:55", "sta": "19:40", "dur": "11h 45m", "coords": (49.1967, -123.1815)}, 
        "BR867": {"aircraft": "B78P/B77M", "route": "桃園 (TPE) ➔ 香港 (HKG)", "std": "10:10", "sta": "12:10", "dur": "2h 00m", "coords": (22.3080, 113.9185)}, 
        "BR868": {"aircraft": "B78P/B77M", "route": "香港 (HKG) ➔ 桃園 (TPE)", "std": "13:10", "sta": "15:05", "dur": "1h 55m", "coords": (22.3080, 113.9185)},
        "BR158": {"aircraft": "A333", "route": "桃園 (TPE) ➔ 小松 (KMQ)", "std": "06:35", "sta": "10:25", "dur": "2h 50m", "coords": (36.3934, 136.4070)},
        "BR157": {"aircraft": "A333", "route": "小松 (KMQ) ➔ 桃園 (TPE)", "std": "11:45", "sta": "13:55", "dur": "3h 10m", "coords": (36.3934, 136.4070)},
        "BR712": {"aircraft": "B77M", "route": "桃園 (TPE) ➔ 上海浦東 (PVG)", "std": "10:10", "sta": "12:05", "dur": "1h 55m", "coords": (31.1443, 121.8083)},
        "BR711": {"aircraft": "B77M", "route": "上海浦東 (PVG) ➔ 桃園 (TPE)", "std": "13:10", "sta": "15:05", "dur": "1h 55m", "coords": (31.1443, 121.8083)},
        "BR758": {"aircraft": "B781", "route": "桃園 (TPE) ➔ 杭州 (HGH)", "std": "16:25", "sta": "18:25", "dur": "2h 00m", "coords": (30.2295, 120.4345)},
        "BR757": {"aircraft": "B781", "route": "杭州 (HGH) ➔ 桃園 (TPE)", "std": "19:35", "sta": "21:30", "dur": "1h 55m", "coords": (30.2295, 120.4345)},
        "BR265": {"aircraft": "A333", "route": "桃園 (TPE) ➔ 金邊 (PNH)", "std": "08:45", "sta": "11:10", "dur": "3h 25m", "coords": (11.5466, 104.8441)}, 
        "BR266": {"aircraft": "A333", "route": "金邊 (PNH) ➔ 桃園 (TPE)", "std": "12:10", "sta": "16:35", "dur": "3h 25m", "coords": (11.5466, 104.8441)},
        "BR211": {"aircraft": "B77M", "route": "桃園 (TPE) ➔ 曼谷 (BKK)", "std": "07:50", "sta": "10:35", "dur": "3h 45m", "coords": (13.6900, 100.7501)}, 
        "BR212": {"aircraft": "B77M", "route": "曼谷 (BKK) ➔ 桃園 (TPE)", "std": "11:50", "sta": "16:30", "dur": "3h 40m", "coords": (13.6900, 100.7501)},
        "BR277": {"aircraft": "A333", "route": "桃園 (TPE) ➔ 馬尼拉 (MNL)", "std": "15:30", "sta": "17:50", "dur": "2h 20m", "coords": (14.5090, 121.0194)}, 
        "BR278": {"aircraft": "A333", "route": "馬尼拉 (MNL) ➔ 桃園 (TPE)", "std": "18:50", "sta": "21:10", "dur": "2h 20m", "coords": (14.5090, 121.0194)},
        "BR281": {"aircraft": "B78P", "route": "桃園 (TPE) ➔ 宿霧 (CEB)", "std": "07:10", "sta": "10:05", "dur": "2h 55m", "coords": (10.3075, 123.9794)}, 
        "BR282": {"aircraft": "B78P", "route": "宿霧 (CEB) ➔ 桃園 (TPE)", "std": "11:05", "sta": "14:00", "dur": "2h 55m", "coords": (10.3075, 123.9794)},
    }
    
    if flight_num in real_flight_db:
        info = real_flight_db[flight_num]
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
            "aircraft": "依派遣而定",
            "route": "長榮航空航線 (詳細資料建檔中)",
            "std": "依班表",
            "sta": "依班表",
            "duration": "--",
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

def load_shared_data():
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
        if re.match(r'^\d+$', line):
            flights.append(f"BR{line}")
    return flights

def parse_and_format_content(content, enable_parsing=True):
    lines = str(content).split('\n')
    formatted_lines = []
    red_codes = ['DO', 'ADO', 'AL', 'YH', 'YI']
    
    for line in lines:
        line = line.strip()
        if not line: continue
        if enable_parsing:
            if line == 'AL': 
                formatted_lines.append("<div style='color:#FF3B30; font-weight:700; font-size:16px; margin: 4px 0;'>🏖️ 特休 (AL)</div>")
            elif line in ['DO', 'ADO']: 
                formatted_lines.append(f"<div style='color:#FF3B30; font-weight:700; font-size:16px; margin: 4px 0;'>🏠 休假 ({line})</div>")
            elif re.match(r'^\(\d+\)$', line): 
                formatted_lines.append(f"<div style='color:#8E8E93; font-size: 13px; font-weight:600; margin-bottom: 4px;'>{line}</div>")
            elif "SCS" in line:
                prefix = line.split(" ")[0]
                formatted_lines.append(f"<div style='color:#FF9500; font-weight:800; font-size:16px; margin: 4px 0;'>🚨 待命 ({prefix})</div>")
            elif re.match(r'^\d{2}:\d{2}-\d{2}:\d{2}$', line): 
                formatted_lines.append(f"<div style='color:#AF52DE; font-weight:700; font-size:15px; margin: 4px 0;'>🕒 {line.replace('-', '~')}</div>")
            elif re.match(r'^\d+$', line): 
                flight_url = f"?flight=BR{line}"
                formatted_lines.append(f"<a href='{flight_url}' target='_self' style='display:inline-block; text-decoration:none; color:#007AFF; font-weight:800; font-size:16px; margin: 4px 0; background-color:#E5F1FF; padding:2px 6px; border-radius:6px;'>✈️ BR{line}</a>")
            elif re.match(r'^[AB]\d{2,3}[a-zA-Z0-9]?$', line): 
                formatted_lines.append(f"<div style='color:#34C759; font-weight:700; font-size:15px; margin: 4px 0;'>🛩️ 機型: {line}</div>")
            elif line in red_codes: 
                formatted_lines.append(f"<div style='color:#FF3B30; font-weight:700; font-size:16px; margin: 4px 0;'>{line}</div>")
            else: 
                formatted_lines.append(f"<div style='font-size:15px; margin: 4px 0;'>{line}</div>")
        else:
            if line in red_codes: 
                formatted_lines.append(f"<div style='color:#FF3B30; font-weight:700; font-size:16px;'>{line}</div>")
            else: 
                formatted_lines.append(f"<div style='font-size:15px;'>{line}</div>")
    return "".join(formatted_lines)

def display_flight_info_panel(flight_num):
    info = fetch_flight_info(flight_num)
    
    st.markdown(f"### 🛫 航班詳細資訊: {flight_num}")
    
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
    
    st.markdown("<br>", unsafe_allow_html=True)
    
    try:
        flight_digits = re.search(r'\d+', flight_num).group()
        flightaware_url = f"https://www.flightaware.com/live/flight/EVA{flight_digits}"
    except AttributeError:
        flightaware_url = "https://www.flightaware.com/"

    st.link_button("✈️ 航班雷達動態", url=flightaware_url, type="primary", use_container_width=True)

def main():
    tw_now = datetime.now(pytz.timezone('Asia/Taipei'))
    current_day_number = tw_now.day

    if 'initialized' not in st.session_state:
        st.session_state.selected_date = current_day_number
        st.session_state.selected_flight = None
        st.session_state.initialized = True

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
        st.subheader("🖼️ 上傳班表圖片")
        st.info("💡 支援常見的圖片格式 (PNG, JPG)。上傳後可於此處預覽與對照。")
        uploaded_image = st.file_uploader("請選擇班表圖片", type=['png', 'jpg', 'jpeg'])
        if uploaded_image is not None:
            st.image(uploaded_image, caption="已上傳的班表圖片", use_container_width=True)
            st.success("✅ 圖片上傳成功！")

    st.title("✈️ 共享智慧班表系統")
    df = load_shared_data()
    
    col1, col2 = st.columns([1, 1])
    with col1:
        enable_parsing = st.toggle("✨ 啟動智慧解讀模式", value=True)
    with col2:
        st.markdown(f"<div style='text-align: right; color: #8E8E93; font-weight: 600;'>🇹🇼 台灣現在時間: {tw_now.strftime('%m/%d %H:%M')}</div>", unsafe_allow_html=True)
    
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
                if st.button(f"查看今日 {flight} 資訊", use_container_width=True):
                    st.session_state.selected_flight = flight
                    st.session_state.selected_date = None

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

    # 整合者修正：去除前導空白，防止觸發 Markdown 程式碼區塊
    grid_html = "<div style='width: 100%; overflow-x: auto; padding-bottom: 15px;'>\n<div style='display: grid; grid-template-columns: repeat(7, minmax(130px, 1fr)); gap: 12px; min-width: 900px;'>"

    for day in days_of_week:
        color = "#FF3B30" if day in ["SUN", "SAT"] else "#1C1C1E"
        grid_html += f"\n<div style='text-align: center; color: {color}; font-weight:800; font-size:16px; padding-bottom: 8px; border-bottom: 2px solid #E5E5EA;'>{day}</div>"

    current_day = 1
    total_days = len(df) 

    for week in range(6):
        if current_day > total_days: break
        for day_idx in range(7):
            if week == 0 and day_idx < start_day_index:
                grid_html += "\n<div style='height: 180px; background-color: #F2F2F7; border-radius: 12px;'></div>"
            elif current_day <= total_days:
                day_data = df[df['Date'] == current_day].iloc[0]
                raw_content = day_data['Content']
                parsed_html = parse_and_format_content(raw_content, enable_parsing)
                
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
                date_link_html = f"<a href='?date={current_day}' target='_self' style='text-decoration:none; color:{date_color}; cursor:pointer;'>{current_day}</a>"

                # 整合者修正：緊湊寫法，避免空白縮排被解析為 Code Block
                grid_html += f"\n<div style='height: 180px; padding: 12px; background-color: {bg_color}; border: {border_style}; border-radius: 12px; box-shadow: {box_shadow}; overflow-y: auto; line-height: 1.6;'><div style='font-size: 18px; font-weight: 800; border-bottom: 1px solid #E5E5EA; padding-bottom: 4px; margin-bottom: 8px;'>{date_link_html} {today_badge}</div><div>{parsed_html}</div></div>"
                current_day += 1
            else:
                grid_html += "\n<div style='height: 180px; background-color: #F2F2F7; border-radius: 12px;'></div>"

    grid_html += "\n</div>\n</div>" 
    
    st.markdown(grid_html, unsafe_allow_html=True)

if __name__ == "__main__":
    main()
