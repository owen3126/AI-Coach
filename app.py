import streamlit as st
import os
import numpy as np
import pandas as pd
import plotly.express as px  # 🌟 導入強大的互動式圖表套件
import requests
import urllib3
import base64
import PyPDF2
import sqlite3
from datetime import datetime

# 強制關閉 SSL 不安全警告
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

st.set_page_config(page_title="LutzAI 運動科學平台", layout="wide", page_icon="🏃‍♂️")

# ---------------------------------------------------------
# 🌟 資料庫初始化與讀取邏輯
# ---------------------------------------------------------
DB_FILE = "coach_data.db"

def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS profile (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, age INTEGER, goal_str TEXT, available_slots TEXT, cs REAL, d_prime REAL, tests_submitted INTEGER DEFAULT 0)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS training_logs (id INTEGER PRIMARY KEY AUTOINCREMENT, date TEXT, type TEXT, distance REAL, duration INTEGER, rpe INTEGER, srpe INTEGER, details TEXT)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS chat_messages (id INTEGER PRIMARY KEY AUTOINCREMENT, role TEXT, content TEXT, timestamp TEXT)''')
    # 🌟 新增：專門記錄 CS 與 D' 歷史變化的資料表
    cursor.execute('''CREATE TABLE IF NOT EXISTS physio_history (id INTEGER PRIMARY KEY AUTOINCREMENT, date TEXT, cs REAL, d_prime REAL)''')
    conn.commit()
    conn.close()

def load_data_from_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    cursor.execute("SELECT name, age, goal_str, available_slots, cs, d_prime, tests_submitted FROM profile ORDER BY id DESC LIMIT 1")
    profile = cursor.fetchone()
    if profile:
        st.session_state.name = profile[0]
        st.session_state.age = profile[1]
        st.session_state.goal_str = profile[2]
        st.session_state.available_slots = profile[3].split(",") if profile[3] else []
        st.session_state.cs = profile[4]
        st.session_state.d_prime = profile[5]
        st.session_state.tests_submitted = bool(profile[6])
        st.session_state.profile_saved = True
    else:
        st.session_state.cs = 4.0; st.session_state.d_prime = 200.0; st.session_state.available_slots = []
        st.session_state.tests_submitted = False; st.session_state.profile_saved = False
        st.session_state.name = "楊云瑢"; st.session_state.goal_str = ""
        
    cursor.execute("SELECT date, type, distance, duration, rpe, srpe, details FROM training_logs ORDER BY date ASC")
    logs = cursor.fetchall()
    st.session_state.training_logs = [{"date": l[0], "type": l[1], "distance": l[2], "duration": l[3], "rpe": l[4], "srpe": l[5], "details": l[6]} for l in logs]
        
    cursor.execute("SELECT role, content FROM chat_messages ORDER BY id ASC")
    messages = cursor.fetchall()
    st.session_state.messages = [{"role": m[0], "content": m[1]} for m in messages]
    conn.close()

init_db()
if 'db_loaded' not in st.session_state:
    load_data_from_db()
    st.session_state.db_loaded = True

# ---------------------------------------------------------
# 文獻庫讀取
# ---------------------------------------------------------
try:
    with open("personality.md", "r", encoding="utf-8") as f: agent_personality = f.read()
except FileNotFoundError:
    agent_personality = "你是一位頂尖的運動科學跑步教練，名字叫科學分析師。"

knowledge_base_content = ""
if not os.path.exists("papers"): os.makedirs("papers")
for file_name in [f for f in os.listdir("papers") if f.endswith(('.txt', '.md', '.pdf'))]:
    file_path = os.path.join("papers", file_name)
    try:
        if file_name.lower().endswith('.pdf'):
            with open(file_path, "rb") as f:
                pdf_text = "".join([page.extract_text() for page in PyPDF2.PdfReader(f).pages if page.extract_text()])
                knowledge_base_content += f"\n\n【PDF文獻：{file_name}】\n{pdf_text}"
        else:
            with open(file_path, "r", encoding="utf-8") as f: knowledge_base_content += f"\n\n【文獻：{file_name}】\n" + f.read()
    except Exception: pass

with st.sidebar:
    st.title("⚙️ 系統設定")
    with st.popover("🔑 設定 Gemini 認證密鑰"):
        api_key = st.text_input("輸入 Gemini API Key", type="password")
    
    st.markdown("---")
    st.subheader("🧭 導航選單")
    if not st.session_state.profile_saved:
        page = "🏠 首頁 (帳號設定)"
    else:
        page = st.radio("選擇頁面", ["📈 訓練儀表板", "🧬 生理參數中心", "💬 AI 科學分析師", "🏠 首頁 (帳號設定)"])

    if st.session_state.profile_saved:
        st.markdown("---")
        if st.button("🗑️ 刪除所有數據並重開帳號"):
            if os.path.exists(DB_FILE): os.remove(DB_FILE)
            st.session_state.clear()
            st.rerun()

# ---------------------------------------------------------
# 頁面 1：🏠 首頁 (帳號設定)
# ---------------------------------------------------------
if page == "🏠 首頁 (帳號設定)":
    st.title("🏠 選手資料與作息設定")
    if st.session_state.profile_saved: st.success(f"目前登入身分：{st.session_state.name} | 目標：{st.session_state.goal_str}")
    
    with st.form("setup_form"):
        c1, c2 = st.columns(2)
        with c1: name = st.text_input("姓名", value=st.session_state.name)
        with c2: age = st.number_input("年齡", value=st.session_state.get('age', 30))
            
        st.markdown("### 🎯 賽事目標")
        goal_type = st.radio("項目", ["全程馬拉松", "半程馬拉松"])
        c_h, c_m = st.columns(2)
        with c_h: goal_hour = st.number_input("時", value=2)
        with c_m: goal_minute = st.number_input("分", value=48)
        
        st.markdown("### 📅 可訓練時段")
        c_am, c_pm = st.columns(2)
        with c_am: am_days = st.multiselect("上午 (AM)", ["週一", "週二", "週三", "週四", "週五", "週六", "週日"], default=["週二", "週三", "週四", "週六", "週日"])
        with c_pm: pm_days = st.multiselect("下午 (PM)", ["週一", "週二", "週三", "週四", "週五", "週六", "週日"], default=["週一", "週二", "週三", "週四", "週五", "週六", "週日"])
        
        if st.form_submit_button("💾 儲存並進入系統"):
            selected_slots = [f"{d}_上午" for d in am_days] + [f"{d}_下午" for d in pm_days]
            goal_str = f"{goal_type} {goal_hour:02d}:{goal_minute:02d}:00"
            conn = sqlite3.connect(DB_FILE); cursor = conn.cursor()
            cursor.execute("INSERT INTO profile (name, age, goal_str, available_slots, cs, d_prime, tests_submitted) VALUES (?, ?, ?, ?, ?, ?, ?)", (name, age, goal_str, ",".join(selected_slots), 4.0, 200.0, 0))
            conn.commit(); conn.close()
            st.session_state.update({"name": name, "goal_str": goal_str, "available_slots": selected_slots, "profile_saved": True})
            st.rerun()

# ---------------------------------------------------------
# 頁面 2：📈 訓練儀表板 (Dashboard)
# ---------------------------------------------------------
elif page == "📈 訓練儀表板":
    st.title("📈 週期訓練儀表板")
    
    with st.expander("➕ 填寫今日訓練回報", expanded=False):
        c_date, c_type = st.columns(2)
        with c_date: train_date = st.date_input("日期")
        with c_type: train_type = st.selectbox("類型", ["輕鬆恢復跑 (Zone 1)", "有氧耐力跑 (Zone 2)", "節奏/門檻跑 (Zone 3)", "無氧間歇跑 (Zone 4)", "其他/交叉訓練"])
        
        c_dist, c_time = st.columns(2)
        with c_dist: distance_km = st.number_input("距離(km)", min_value=0.0, value=8.0, step=0.1)
        with c_time: duration_min = st.number_input("時間(分)", min_value=1, value=45)
            
        intervals = st.text_input("細節備註", value="") if "間歇" in train_type else ""
        rpe = st.slider("RPE (0-10)", 0, 10, 6)
        
        if st.button("📝 送出日誌"):
            srpe_val = duration_min * rpe
            conn = sqlite3.connect(DB_FILE); cursor = conn.cursor()
            cursor.execute("INSERT INTO training_logs (date, type, distance, duration, rpe, srpe, details) VALUES (?, ?, ?, ?, ?, ?, ?)", (str(train_date), train_type, distance_km, duration_min, rpe, srpe_val, intervals))
            conn.commit(); conn.close()
            st.session_state.training_logs.append({"date": str(train_date), "type": train_type, "distance": distance_km, "duration": duration_min, "rpe": rpe, "srpe": srpe_val, "details": intervals})
            st.success("紀錄已儲存！")
            st.rerun()

    if st.session_state.training_logs:
        df = pd.DataFrame(st.session_state.training_logs)
        df['date'] = pd.to_datetime(df['date']).dt.strftime('%Y-%m-%d')
        df = df.sort_values('date')
        
        st.markdown("### 🏆 數據總覽")
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("累積跑量", f"{df['distance'].sum():.1f} km")
        m2.metric("總訓練時間", f"{df['duration'].sum()} min")
        m3.metric("平均 RPE", f"{df['rpe'].mean():.1f}")
        
        acute = df.tail(7)['srpe'].sum()
        chronic = df['srpe'].mean() * 7 if not df.empty else 1
        acwl = acute / chronic
        m4.metric("ACWL 疲勞比", f"{acwl:.2f}", delta="紅區" if acwl > 1.5 else "安全", delta_color="inverse")

        st.markdown("---")
        c_chart1, c_chart2 = st.columns(2)
        with c_chart1:
            st.markdown("#### 📉 跑量趨勢")
            st.line_chart(df.set_index("date")["distance"], color="#0068c9")
        with c_chart2:
            st.markdown("#### 📊 負荷 (sRPE) 趨勢")
            st.bar_chart(df.set_index("date")["srpe"], color="#ff4b4b")
            
        st.markdown("#### 📋 完整明細表")
        st.dataframe(df.rename(columns={"date":"日期", "type":"課表類型", "distance":"距離(km)", "duration":"時間(分)", "rpe":"RPE", "srpe":"負荷(sRPE)", "details":"備註"}), use_container_width=True)
    else:
        st.info("尚無訓練紀錄，請點擊上方展開填寫。")

# ---------------------------------------------------------
# 頁面 3：🧬 生理參數中心 (🌟 包含全新動態曲線圖)
# ---------------------------------------------------------
elif page == "🧬 生理參數中心":
    st.title("🧬 生理參數追蹤與測驗")
    
    col_metrics, col_test = st.columns([1, 2])
    with col_metrics:
        st.markdown("### 📊 當前能力指標")
        st.metric("臨界速度 (CS)", f"{st.session_state.get('cs', 4.0):.2f} m/s", delta=f"{1000/st.session_state.get('cs', 4.0)/60:.2f} min/km")
        st.metric("無氧儲備 (D')", f"{st.session_state.get('d_prime', 200.0):.0f} m")
        
    with col_test:
        with st.expander("🧮 新增測驗成績解算", expanded=False):
            with st.form("test_form"):
                tc1, tc2 = st.columns(2)
                with tc1:
                    m800 = st.number_input("800m (分)", value=2); s800 = st.number_input("800m (秒)", value=28)
                    m1600 = st.number_input("1600m (分)", value=5); s1600 = st.number_input("1600m (秒)", value=10)
                with tc2:
                    m2400 = st.number_input("2400m (分)", value=8); s2400 = st.number_input("2400m (秒)", value=0)
                    m3600 = st.number_input("3600m (分)", value=12); s3600 = st.number_input("3600m (秒)", value=15)
                
                test_date = st.date_input("測驗日期", value=datetime.today())
                
                if st.form_submit_button("💾 儲存並繪製曲線"):
                    times = np.array([m800*60+s800, m1600*60+s1600, m2400*60+s2400, m3600*60+s3600])
                    distances = np.array([800, 1600, 2400, 3600])
                    slope, intercept = np.polyfit(times, distances, 1)
                    
                    conn = sqlite3.connect(DB_FILE); cursor = conn.cursor()
                    cursor.execute("UPDATE profile SET cs=?, d_prime=?, tests_submitted=1 WHERE id=(SELECT max(id) FROM profile)", (slope, intercept))
                    # 🌟 將歷史紀錄寫入專屬表單
                    cursor.execute("INSERT INTO physio_history (date, cs, d_prime) VALUES (?, ?, ?)", (str(test_date), slope, intercept))
                    conn.commit(); conn.close()
                    
                    st.session_state.update({"cs": slope, "d_prime": intercept, "tests_submitted": True})
                    st.success("生理模型已更新！")
                    st.rerun()

    st.markdown("---")
    st.markdown("### 📈 臨界速度 (CS) 與無氧儲備 (D') 成長曲線")
    
    # 🌟 從資料庫讀取並繪製 Plotly 互動圖表
    conn = sqlite3.connect(DB_FILE)
    df_physio = pd.read_sql_query("SELECT date, cs, d_prime FROM physio_history ORDER BY date ASC", conn)
    conn.close()

    if not df_physio.empty:
        # 將日期轉換為更容易閱讀的格式
        df_physio['date'] = pd.to_datetime(df_physio['date']).dt.strftime('%Y-%m-%d')
        
        fig_col1, fig_col2 = st.columns(2)
        with fig_col1:
            # CS 折線圖
            fig_cs = px.line(df_physio, x='date', y='cs', markers=True, title="臨界速度 CS (m/s) 趨勢", line_shape="spline")
            fig_cs.update_traces(line_color="#0068c9", marker=dict(size=8))
            fig_cs.update_layout(xaxis_title="測驗日期", yaxis_title="CS (m/s)")
            st.plotly_chart(fig_cs, use_container_width=True)
            
        with fig_col2:
            # D' 折線圖
            fig_dp = px.line(df_physio, x='date', y='d_prime', markers=True, title="無氧儲備 D' (m) 趨勢", line_shape="spline")
            fig_dp.update_traces(line_color="#ff4b4b", marker=dict(size=8))
            fig_dp.update_layout(xaxis_title="測驗日期", yaxis_title="D' (m)")
            st.plotly_chart(fig_dp, use_container_width=True)
            
        st.markdown("#### 📝 歷史測驗紀錄明細")
        st.dataframe(df_physio.rename(columns={"date": "日期", "cs": "臨界速度 (CS)", "d_prime": "無氧儲備 (D')"}), use_container_width=True)
    else:
        st.info("尚無歷史測驗紀錄。請在上方「新增測驗成績解算」輸入成績，系統將自動為您繪製成長曲線！")

# ---------------------------------------------------------
# 頁面 4：💬 AI 科學分析師
# ---------------------------------------------------------
elif page == "💬 AI 科學分析師":
    st.title("💬 運動科學大腦")
    st.caption(f"狀態：{'🟢 實證對話模式' if api_key else '💡 Demo 模式'}")
    
    chat_container = st.container(height=500)
    with chat_container:
        for msg in st.session_state.messages:
            with st.chat_message(msg["role"]): st.markdown(msg["content"])

    c_text, c_audio = st.columns([5, 1])
    with c_text: prompt_text = st.chat_input("詢問微週期課表或文獻...")
    with c_audio:
        with st.popover("🎤"): audio_file = st.audio_input("錄音回報")

    active_prompt = prompt_text if prompt_text else ("🎤 [語音回報]" if audio_file else "")
    
    if active_prompt:
        conn = sqlite3.connect(DB_FILE); cursor = conn.cursor()
        cursor.execute("INSERT INTO chat_messages (role, content, timestamp) VALUES (?, ?, ?)", ("user", active_prompt, str(datetime.now())))
        conn.commit(); conn.close()
        st.session_state.messages.append({"role": "user", "content": active_prompt})
        
        history = "\n".join([f"- {l['date']}: {l['type']}, {l['distance']}km, {l['duration']}min" for l in st.session_state.training_logs[-3:]])
        sys_inst = f"{agent_personality}\n\n【文獻】\n{knowledge_base_content}\n\n【生理數據】\nCS: {st.session_state.cs:.2f} m/s, D': {st.session_state.d_prime:.0f}m\n可訓練時段: {','.join(st.session_state.available_slots)}\n近期訓練:\n{history}\n\n請依此給予專業繁體中文回覆。"

        if api_key:
            with st.spinner("AI 思考中..."):
                try:
                    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3.5-flash:generateContent?key={api_key}"
                    parts = [{"inlineData": {"mimeType": audio_file.type, "data": base64.b64encode(audio_file.read()).decode("utf-8")}}, {"text": "這是語音，請聽取並指導。"}] if audio_file else [{"text": active_prompt}]
                    payload = {"systemInstruction": {"parts": [{"text": sys_inst}]}, "contents": [{"role": "user", "parts": parts}]}
                    res = requests.post(url, headers={"Content-Type": "application/json"}, json=payload, verify=False).json()
                    ai_reply = res["candidates"][0]["content"]["parts"][0]["text"] if "candidates" in res else f"❌ API 異常: {res}"
                except Exception as e: ai_reply = f"❌ 串接失敗: {e}"
        else:
            ai_reply = "💡 **【Demo 模式】** 真實模式下將結合您的生理數據給出回覆。"

        conn = sqlite3.connect(DB_FILE); cursor = conn.cursor()
        cursor.execute("INSERT INTO chat_messages (role, content, timestamp) VALUES (?, ?, ?)", ("assistant", ai_reply, str(datetime.now())))
        conn.commit(); conn.close()
        st.session_state.messages.append({"role": "assistant", "content": ai_reply})
        st.rerun()