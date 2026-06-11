import streamlit as st
import os
import numpy as np
import pandas as pd
import plotly.express as px
import requests
import urllib3
import base64
import PyPDF2
import sqlite3
import json
import re
from datetime import datetime

# 強制關閉 SSL 不安全警告
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ---------------------------------------------------------
# 🌟 UI 溫和修復與 LINE 氣泡對話框 (安全版 CSS)
# ---------------------------------------------------------
st.set_page_config(page_title="LutzAI 運動科學平台", layout="wide", page_icon="📓")

st.markdown("""
<style>
/* 移除強制全域覆蓋，讓 Streamlit 內建引擎接管字體大小，避免按鈕與圖示重疊 */

/* =========================================
   💬 LINE 風格對話氣泡設計 (動態適應深淺色)
   ========================================= */
/* 隱藏預設頭像背景色 */
[data-testid="stChatMessageAvatar"] {
    background-color: transparent !important;
}

/* User 氣泡：仿 LINE 右側 (使用半透明灰底，深淺色皆適用) */
[data-testid="stChatMessage"]:has([data-testid="chatAvatarIcon-user"]) [data-testid="stChatMessageContent"] {
    background-color: rgba(135, 131, 120, 0.15) !important;
    border-radius: 18px 18px 2px 18px !important;
    padding: 12px 18px !important;
}

/* AI 教練氣泡：仿 LINE 左側 (透明底加細邊框) */
[data-testid="stChatMessage"]:has([data-testid="chatAvatarIcon-assistant"]) [data-testid="stChatMessageContent"] {
    background-color: transparent !important;
    border: 1px solid rgba(135, 131, 120, 0.2) !important;
    border-radius: 18px 18px 18px 2px !important;
    padding: 12px 18px !important;
}
</style>
""", unsafe_allow_html=True)

# ---------------------------------------------------------
# 🌟 Plotly 圖表專屬主題設定函數
# ---------------------------------------------------------
def apply_notion_theme(fig):
    """移除強制黑字，讓系統自動適應深淺色，保留極簡格線"""
    fig.update_layout(
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=20, r=20, t=40, b=20)
    )
    fig.update_yaxes(showgrid=True, gridwidth=1, gridcolor='rgba(135, 131, 120, 0.2)', zerolinecolor='rgba(135, 131, 120, 0.2)')
    fig.update_xaxes(showgrid=False, zerolinecolor='rgba(135, 131, 120, 0.2)')
    return fig

# ---------------------------------------------------------
# 🌟 資料庫初始化與讀取邏輯
# ---------------------------------------------------------
DB_FILE = "coach_data.db"

def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS profile (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, age INTEGER, goal_str TEXT, race_date TEXT, available_slots TEXT, cs REAL, d_prime REAL, tests_submitted INTEGER DEFAULT 0)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS training_logs (id INTEGER PRIMARY KEY AUTOINCREMENT, date TEXT, type TEXT, distance REAL, duration INTEGER, rpe INTEGER, srpe INTEGER, details TEXT)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS training_plan (id INTEGER PRIMARY KEY AUTOINCREMENT, date TEXT, type TEXT, distance REAL, duration INTEGER, rpe INTEGER, details TEXT)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS chat_messages (id INTEGER PRIMARY KEY AUTOINCREMENT, role TEXT, content TEXT, timestamp TEXT)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS physio_history (id INTEGER PRIMARY KEY AUTOINCREMENT, date TEXT, cs REAL, d_prime REAL)''')
    conn.commit()
    conn.close()

def load_data_from_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    cursor.execute("SELECT name, age, goal_str, race_date, available_slots, cs, d_prime, tests_submitted FROM profile ORDER BY id DESC LIMIT 1")
    profile = cursor.fetchone()
    if profile:
        st.session_state.name = profile[0]
        st.session_state.age = profile[1]
        st.session_state.goal_str = profile[2]
        st.session_state.race_date = profile[3] if profile[3] else str(datetime.today().date())
        st.session_state.available_slots = profile[4].split(",") if profile[4] else []
        st.session_state.cs = profile[5]
        st.session_state.d_prime = profile[6]
        st.session_state.tests_submitted = bool(profile[7])
        st.session_state.profile_saved = True
    else:
        st.session_state.cs = 4.0; st.session_state.d_prime = 200.0; st.session_state.available_slots = []
        st.session_state.tests_submitted = False; st.session_state.profile_saved = False
        st.session_state.name = "楊云瑢"; st.session_state.goal_str = ""; st.session_state.race_date = str(datetime.today().date())
        
    cursor.execute("SELECT date, type, distance, duration, rpe, srpe, details FROM training_logs ORDER BY date ASC")
    st.session_state.training_logs = [{"date": l[0], "type": l[1], "distance": l[2], "duration": l[3], "rpe": l[4], "srpe": l[5], "details": l[6]} for l in cursor.fetchall()]
    
    cursor.execute("SELECT date, type, distance, duration, rpe, details FROM training_plan ORDER BY date ASC")
    st.session_state.training_plan = [{"date": p[0], "type": p[1], "distance": p[2], "duration": p[3], "rpe": p[4], "details": p[5]} for p in cursor.fetchall()]

    cursor.execute("SELECT role, content FROM chat_messages ORDER BY id ASC")
    st.session_state.messages = [{"role": m[0], "content": m[1]} for m in cursor.fetchall()]
    conn.close()

init_db()
if 'db_loaded' not in st.session_state:
    try:
        load_data_from_db()
    except sqlite3.OperationalError:
        if os.path.exists(DB_FILE): os.remove(DB_FILE)
        init_db(); load_data_from_db()
    st.session_state.db_loaded = True

# ---------------------------------------------------------
# 🚀 效能殺手修復：文獻庫快取讀取 (Cache Data)
# ---------------------------------------------------------
try:
    with open("personality.md", "r", encoding="utf-8") as f: agent_personality = f.read()
except FileNotFoundError:
    agent_personality = "你是一位頂尖的運動科學跑步教練，名字叫科學分析師。"

@st.cache_data
def load_knowledge_base():
    """快取文獻讀取，避免每次點擊按鈕都重新掃描 PDF 導致系統卡頓"""
    kb_content = ""
    if not os.path.exists("papers"): os.makedirs("papers")
    for file_name in [f for f in os.listdir("papers") if f.endswith(('.txt', '.md', '.pdf'))]:
        file_path = os.path.join("papers", file_name)
        try:
            if file_name.lower().endswith('.pdf'):
                with open(file_path, "rb") as f: 
                    kb_content += f"\n\n【PDF文獻：{file_name}】\n" + "".join([page.extract_text() for page in PyPDF2.PdfReader(f).pages if page.extract_text()])
            else:
                with open(file_path, "r", encoding="utf-8") as f: kb_content += f"\n\n【文獻：{file_name}】\n" + f.read()
        except Exception: pass
    return kb_content

knowledge_base_content = load_knowledge_base()

with st.sidebar:
    st.markdown("### ⚙️ Workspace")
    with st.popover("🔑 API 金鑰"):
        api_key = st.text_input("輸入 Gemini API Key", type="password")
    
    st.markdown("---")
    if not st.session_state.profile_saved:
        page = "🏠 首頁 (Profile)"
    else:
        page = st.radio("導覽目錄", ["📈 訓練儀表板", "🧬 生理參數庫", "💬 AI 對話教練", "🏠 首頁 (Profile)"])

    if st.session_state.profile_saved:
        st.markdown("---")
        if st.button("🗑️ 清空所有數據庫"):
            if os.path.exists(DB_FILE): os.remove(DB_FILE)
            st.session_state.clear()
            st.rerun()

# ---------------------------------------------------------
# 頁面 1：🏠 首頁 (Profile)
# ---------------------------------------------------------
if page == "🏠 首頁 (Profile)":
    st.markdown("## 🏠 選手檔案 (Profile)")
    
    with st.form("setup_form"):
        c1, c2 = st.columns(2)
        with c1: name = st.text_input("姓名", value=st.session_state.name)
        with c2: age = st.number_input("年齡", value=st.session_state.get('age', 30))
            
        st.markdown("#### 🎯 賽事目標設定")
        goal_type = st.radio("項目", ["全程馬拉松", "半程馬拉松"], horizontal=True)
        
        c_date, c_h, c_m = st.columns([2, 1, 1])
        with c_date: race_date = st.date_input("🗓️ 目標賽事日期", value=datetime.strptime(st.session_state.race_date, '%Y-%m-%d').date() if st.session_state.get('race_date') else datetime.today().date())
        with c_h: goal_hour = st.number_input("時", value=2)
        with c_m: goal_minute = st.number_input("分", value=48)
        
        st.markdown("#### 📅 每週可訓練空檔")
        c_am, c_pm = st.columns(2)
        with c_am: am_days = st.multiselect("上午 (AM)", ["週一", "週二", "週三", "週四", "週五", "週六", "週日"], default=["週二", "週三", "週四", "週六", "週日"])
        with c_pm: pm_days = st.multiselect("下午 (PM)", ["週一", "週二", "週三", "週四", "週五", "週六", "週日"], default=["週一", "週二", "週三", "週四", "週五", "週六", "週日"])
        
        if st.form_submit_button("💾 儲存並進入系統"):
            selected_slots = [f"{d}_上午" for d in am_days] + [f"{d}_下午" for d in pm_days]
            goal_str = f"{goal_type} {goal_hour:02d}:{goal_minute:02d}:00"
            conn = sqlite3.connect(DB_FILE); cursor = conn.cursor()
            cursor.execute("INSERT INTO profile (name, age, goal_str, race_date, available_slots, cs, d_prime, tests_submitted) VALUES (?, ?, ?, ?, ?, ?, ?, ?)", (name, age, goal_str, str(race_date), ",".join(selected_slots), 4.0, 200.0, 0))
            conn.commit(); conn.close()
            st.session_state.update({"name": name, "goal_str": goal_str, "race_date": str(race_date), "available_slots": selected_slots, "profile_saved": True})
            st.rerun()

# ---------------------------------------------------------
# 頁面 2：📈 訓練儀表板
# ---------------------------------------------------------
elif page == "📈 訓練儀表板":
    st.markdown("## 📈 訓練儀表板")
    
    if st.session_state.get('race_date'):
        days_to_race = (datetime.strptime(st.session_state.race_date, '%Y-%m-%d').date() - datetime.today().date()).days
        if days_to_race < 0: macrocycle = "Transition (季後過渡期)"
        elif days_to_race <= 21: macrocycle = "Tapering (賽前減量期)"
        elif days_to_race <= 84: macrocycle = "Peak (季中巔峰期)"
        elif days_to_race <= 168: macrocycle = "Build (季前進展期)"
        else: macrocycle = "Base (季外基礎期)"
        
        st.markdown(f"**🎯 距目標賽事還剩 {days_to_race} 天** ｜ 當前週期：`{macrocycle}`")

    st.markdown("---")
    col_plan, col_actual = st.columns(2)
    
    with col_plan:
        st.markdown("#### 🤖 預定課表 (Planned)")
        if st.session_state.get('training_plan'):
            df_plan = pd.DataFrame(st.session_state.training_plan)
            st.dataframe(df_plan.rename(columns={"date":"Date", "type":"Type", "distance":"Dist (km)", "duration":"Time (min)", "rpe":"RPE", "details":"Details"}), use_container_width=True, hide_index=True)
            if st.button("🗑️ 清除課表"):
                conn = sqlite3.connect(DB_FILE); cursor = conn.cursor()
                cursor.execute("DELETE FROM training_plan")
                conn.commit(); conn.close()
                st.session_state.training_plan = []
                st.rerun()
        else:
            st.caption("尚未建立課表。請至「AI 對話教練」頁面請教練安排。")
            
    with col_actual:
        st.markdown("#### 🏃‍♂️ 實際回報 (Actual)")
        with st.form("daily_log"):
            train_date = st.date_input("Date")
            train_type = st.selectbox("Type", ["輕鬆恢復跑 (Zone 1)", "有氧耐力跑 (Zone 2)", "節奏/門檻跑 (Zone 3)", "無氧間歇跑 (Zone 4)", "其他/交叉訓練"])
            c_d, c_t = st.columns(2)
            with c_d: distance_km = st.number_input("Dist (km)", min_value=0.0, value=8.0)
            with c_t: duration_min = st.number_input("Time (min)", min_value=1, value=45)
            intervals = st.text_input("Details")
            rpe = st.slider("RPE", 0, 10, 6)
            
            if st.form_submit_button("📝 記錄儲存"):
                srpe_val = duration_min * rpe
                conn = sqlite3.connect(DB_FILE); cursor = conn.cursor()
                cursor.execute("INSERT INTO training_logs (date, type, distance, duration, rpe, srpe, details) VALUES (?, ?, ?, ?, ?, ?, ?)", (str(train_date), train_type, distance_km, duration_min, rpe, srpe_val, intervals))
                conn.commit(); conn.close()
                st.session_state.training_logs.append({"date": str(train_date), "type": train_type, "distance": distance_km, "duration": duration_min, "rpe": rpe, "srpe": srpe_val, "details": intervals})
                st.rerun()

    st.markdown("---")
    if st.session_state.training_logs:
        df = pd.DataFrame(st.session_state.training_logs).sort_values('date')
        st.markdown("#### 📊 Volume & Load Trends")
        c_chart1, c_chart2 = st.columns(2)
        
        fig_dist = px.bar(df, x="date", y="distance", title="Distance (km)", color_discrete_sequence=["#2EA3F2"])
        fig_dist = apply_notion_theme(fig_dist)
        c_chart1.plotly_chart(fig_dist, use_container_width=True)
        
        fig_load = px.area(df, x="date", y="srpe", title="Training Load (sRPE)", color_discrete_sequence=["#E03E3E"])
        fig_load = apply_notion_theme(fig_load)
        c_chart2.plotly_chart(fig_load, use_container_width=True)

# ---------------------------------------------------------
# 頁面 3：🧬 生理參數庫
# ---------------------------------------------------------
elif page == "🧬 生理參數庫":
    st.markdown("## 🧬 Physiology Data")
    
    col_metrics, col_test = st.columns([1, 2])
    with col_metrics:
        st.markdown("#### 📊 Current Metrics")
        st.metric("CS (Critical Speed)", f"{st.session_state.get('cs', 4.0):.2f} m/s", delta=f"{1000/st.session_state.get('cs', 4.0)/60:.2f} min/km")
        st.metric("D' (Anaerobic Reserve)", f"{st.session_state.get('d_prime', 200.0):.0f} m")
        
    with col_test:
        with st.expander("➕ Update Benchmark Test", expanded=False):
            with st.form("test_form"):
                tc1, tc2 = st.columns(2)
                with tc1:
                    m800 = st.number_input("800m (min)", value=2); s800 = st.number_input("800m (sec)", value=28)
                    m1600 = st.number_input("1600m (min)", value=5); s1600 = st.number_input("1600m (sec)", value=10)
                with tc2:
                    m2400 = st.number_input("2400m (min)", value=8); s2400 = st.number_input("2400m (sec)", value=0)
                    m3600 = st.number_input("3600m (min)", value=12); s3600 = st.number_input("3600m (sec)", value=15)
                
                test_date = st.date_input("Date", value=datetime.today())
                
                if st.form_submit_button("Calculate & Save"):
                    times = np.array([m800*60+s800, m1600*60+s1600, m2400*60+s2400, m3600*60+s3600])
                    distances = np.array([800, 1600, 2400, 3600])
                    slope, intercept = np.polyfit(times, distances, 1)
                    
                    conn = sqlite3.connect(DB_FILE); cursor = conn.cursor()
                    cursor.execute("UPDATE profile SET cs=?, d_prime=?, tests_submitted=1 WHERE id=(SELECT max(id) FROM profile)", (slope, intercept))
                    cursor.execute("INSERT INTO physio_history (date, cs, d_prime) VALUES (?, ?, ?)", (str(test_date), slope, intercept))
                    conn.commit(); conn.close()
                    
                    st.session_state.update({"cs": slope, "d_prime": intercept, "tests_submitted": True})
                    st.rerun()

    st.markdown("---")
    conn = sqlite3.connect(DB_FILE)
    df_physio = pd.read_sql_query("SELECT date, cs, d_prime FROM physio_history ORDER BY date ASC", conn)
    conn.close()

    if not df_physio.empty:
        df_physio['date'] = pd.to_datetime(df_physio['date']).dt.strftime('%Y-%m-%d')
        fig_col1, fig_col2 = st.columns(2)
        with fig_col1:
            fig_cs = px.line(df_physio, x='date', y='cs', markers=True, title="CS Trend", color_discrete_sequence=["#0F7B6C"]) 
            fig_cs = apply_notion_theme(fig_cs)
            st.plotly_chart(fig_cs, use_container_width=True)
        with fig_col2:
            fig_dp = px.line(df_physio, x='date', y='d_prime', markers=True, title="D' Trend", color_discrete_sequence=["#5A5A9A"]) 
            fig_dp = apply_notion_theme(fig_dp)
            st.plotly_chart(fig_dp, use_container_width=True)

# ---------------------------------------------------------
# 頁面 4：💬 AI 氣泡對話教練
# ---------------------------------------------------------
elif page == "💬 AI 對話教練":
    st.markdown("## 💬 Coaching Room")
    st.caption("討論課表調整。確認課表後，系統將自動同步並覆寫儀表板上的日程。")
    
    chat_container = st.container(height=500)
    with chat_container:
        for msg in st.session_state.messages:
            with st.chat_message(msg["role"]): st.markdown(msg["content"])

    c_text, c_audio = st.columns([5, 1])
    with c_text: prompt_text = st.chat_input("Ex: 教練，幫我排今天到週日的課表...")
    with c_audio:
        with st.popover("🎤"): audio_file = st.audio_input("Audio")

    active_prompt = prompt_text if prompt_text else ("🎤 [語音回報]" if audio_file else "")
    
    if active_prompt:
        conn = sqlite3.connect(DB_FILE); cursor = conn.cursor()
        cursor.execute("INSERT INTO chat_messages (role, content, timestamp) VALUES (?, ?, ?)", ("user", active_prompt, str(datetime.now())))
        conn.commit(); conn.close()
        st.session_state.messages.append({"role": "user", "content": active_prompt})
        
        history = "\n".join([f"- {l['date']}: {l['type']}, {l['distance']}km, {l['duration']}min" for l in st.session_state.training_logs[-3:]])
        
        now = datetime.today()
        current_date_str = now.strftime('%Y-%m-%d')
        weekday_map = {0:"一", 1:"二", 2:"三", 3:"四", 4:"五", 5:"六", 6:"日"}
        current_weekday = f"星期{weekday_map[now.weekday()]}"
        backticks = chr(96) * 3
        
        prompt_parts = [
            f"{agent_personality}",
            "",
            "【現實時間認知】",
            f"今天是真實世界的：{current_date_str} ({current_weekday})",
            f"- 當選手要求「安排本週課表」時，請務必從「{current_date_str} 開始，排到本週日為止」。",
            "- 當選手在週日要求「安排下週課表」時，再給完整的下週一到下週日課表。",
            f"- 若選手提出回饋修改課表，請從「{current_date_str} 起」向後調整未來的課表。",
            "",
            "【生理與目標數據】",
            f"CS: {st.session_state.cs:.2f} m/s, D': {st.session_state.d_prime:.0f}m",
            f"可訓練時段: {','.join(st.session_state.available_slots)}",
            f"目標賽事日: {st.session_state.get('race_date')}",
            "近期訓練歷史:",
            f"{history}",
            "",
            "【專屬偏好設定】",
            "- 課表呈現請勿使用粗體字。",
            "- 針對「輕鬆恢復跑 (Zone 1)」等恢復性質訓練，請務必提供具體的「配速區間 (Pace Range)」。",
            "",
            "【重要操作指令：兩階段確認法】",
            "1. 當你提出新的課表或調整草案時，【必須只使用一般文字或表格】，並詢問選手：「確認沒問題的話，我就幫你同步到系統裡囉？」",
            "2. 【極度重要】：絕不能在第一次提案就輸出 JSON！",
            "3. 只有當選手回答「好」、「OK」、「沒問題」、「確認」這類同意詞時，你才可以在回覆的最下方，輸出 JSON 結構數據。",
            "4. 輸出的 JSON 中，只要日期相同的項目，系統會自動覆蓋(Update)掉舊的課表。",
            "",
            f"JSON 格式範例 (必須被 {backticks}json 包含)：",
            f"{backticks}json",
            "[",
            '  {"date": "2026-06-15", "type": "輕鬆恢復跑 (Zone 1)", "distance": 6.0, "duration": 40, "rpe": 3, "details": "心率維持在130以下"}',
            "]",
            f"{backticks}",
            "注意：type 必須嚴格等於這五種之一：[輕鬆恢復跑 (Zone 1), 有氧耐力跑 (Zone 2), 節奏/門檻跑 (Zone 3), 無氧間歇跑 (Zone 4), 其他/交叉訓練]。"
        ]
        
        sys_inst = "\n".join(prompt_parts)

        if api_key:
            with st.spinner("AI 正在深度思考與演算中..."):
                try:
                    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3.5-flash:generateContent?key={api_key}"
                    parts = [{"inlineData": {"mimeType": audio_file.type, "data": base64.b64encode(audio_file.read()).decode("utf-8")}}, {"text": "這是語音，請聽取並指導。"}] if audio_file else [{"text": active_prompt}]
                    payload = {"systemInstruction": {"parts": [{"text": sys_inst}]}, "contents": [{"role": "user", "parts": parts}]}
                    res = requests.post(url, headers={"Content-Type": "application/json"}, json=payload, verify=False).json()
                    
                    if "candidates" in res:
                        ai_reply = res["candidates"][0]["content"]["parts"][0]["text"]
                        
                        regex_pattern = rf'{backticks}json\n(.*?)\n{backticks}'
                        json_match = re.search(regex_pattern, ai_reply, re.DOTALL)
                        
                        if json_match:
                            try:
                                plan_data = json.loads(json_match.group(1))
                                conn = sqlite3.connect(DB_FILE); cursor = conn.cursor()
                                for day_plan in plan_data:
                                    cursor.execute("DELETE FROM training_plan WHERE date = ?", (day_plan['date'],))
                                    cursor.execute("INSERT INTO training_plan (date, type, distance, duration, rpe, details) VALUES (?, ?, ?, ?, ?, ?)", 
                                        (day_plan['date'], day_plan['type'], float(day_plan['distance']), int(day_plan['duration']), int(day_plan['rpe']), day_plan.get('details', '')))
                                conn.commit()
                                
                                cursor.execute("SELECT date, type, distance, duration, rpe, details FROM training_plan ORDER BY date ASC")
                                st.session_state.training_plan = [{"date": p[0], "type": p[1], "distance": p[2], "duration": p[3], "rpe": p[4], "details": p[5]} for p in cursor.fetchall()]
                                conn.close()
                                
                                ai_reply += "\n\n✅ **[系統提示：收到確認指令！最新課表已覆寫並同步至「訓練儀表板」。]**"
                            except Exception as e:
                                ai_reply += f"\n\n⚠️ **[系統提示：課表同步失敗]** {e}"
                                
                    else:
                        ai_reply = f"❌ API Error: {res}"
                except Exception as e: ai_reply = f"❌ Connection Failed: {e}"
        else:
            ai_reply = "💡 **[Demo Mode]** 真實模式下，AI 回覆後系統會自動進行資料庫寫入。"

        conn = sqlite3.connect(DB_FILE); cursor = conn.cursor()
        cursor.execute("INSERT INTO chat_messages (role, content, timestamp) VALUES (?, ?, ?)", ("assistant", ai_reply, str(datetime.now())))
        conn.commit(); conn.close()
        st.session_state.messages.append({"role": "assistant", "content": ai_reply})
        st.rerun()