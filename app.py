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

st.set_page_config(page_title="LutzAI 運動科學平台", layout="wide", page_icon="🏃‍♂️")

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
                knowledge_base_content += f"\n\n【PDF文獻：{file_name}】\n" + "".join([page.extract_text() for page in PyPDF2.PdfReader(f).pages if page.extract_text()])
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
    st.title("🏠 選手資料與目標賽事設定")
    
    with st.form("setup_form"):
        c1, c2 = st.columns(2)
        with c1: name = st.text_input("姓名", value=st.session_state.name)
        with c2: age = st.number_input("年齡", value=st.session_state.get('age', 30))
            
        st.markdown("### 🎯 賽事目標設定")
        goal_type = st.radio("項目", ["全程馬拉松", "半程馬拉松"])
        
        c_date, c_h, c_m = st.columns([2, 1, 1])
        with c_date: race_date = st.date_input("🗓️ 目標賽事日期 (用於推算大週期)", value=datetime.strptime(st.session_state.race_date, '%Y-%m-%d').date() if st.session_state.get('race_date') else datetime.today().date())
        with c_h: goal_hour = st.number_input("完賽時", value=2)
        with c_m: goal_minute = st.number_input("完賽分", value=48)
        
        st.markdown("### 📅 可訓練時段")
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
# 頁面 2：📈 訓練儀表板 (含預定與實際)
# ---------------------------------------------------------
elif page == "📈 訓練儀表板":
    st.title("📈 週期訓練儀表板")
    
    # 🌟 自動推算大週期 (Macrocycle)
    if st.session_state.get('race_date'):
        days_to_race = (datetime.strptime(st.session_state.race_date, '%Y-%m-%d').date() - datetime.today().date()).days
        if days_to_race < 0: macrocycle = "🏖️ 季後過渡期 (Transition)"
        elif days_to_race <= 21: macrocycle = "📉 賽前減量期 (Tapering)"
        elif days_to_race <= 84: macrocycle = "🔥 季中巔峰期 (In-Season / Peak)"
        elif days_to_race <= 168: macrocycle = "📈 季前進展期 (Pre-Season / Build)"
        else: macrocycle = "🧱 季外基礎期 (Off-Season / Base)"
        
        st.info(f"**🎯 距離目標賽事 ({st.session_state.race_date}) 還有 {days_to_race} 天！** 目前處於：**{macrocycle}**")

    # 🌟 AI 預定課表 vs 實際回報區塊
    col_plan, col_actual = st.columns(2)
    
    with col_plan:
        st.markdown("### 🤖 教練預定課表 (自動同步)")
        if st.session_state.get('training_plan'):
            df_plan = pd.DataFrame(st.session_state.training_plan)
            # 將資料表美化
            st.dataframe(df_plan.rename(columns={"date":"日期", "type":"課表類型", "distance":"距離(km)", "duration":"時間(分)", "rpe":"RPE", "details":"課表細節"}), use_container_width=True, hide_index=True)
            
            # 清除預定課表的按鈕
            if st.button("🗑️ 清空舊的預定課表"):
                conn = sqlite3.connect(DB_FILE); cursor = conn.cursor()
                cursor.execute("DELETE FROM training_plan")
                conn.commit(); conn.close()
                st.session_state.training_plan = []
                st.rerun()
        else:
            st.write("目前沒有預定課表。請至「AI 科學分析師」頁面請教練安排。")
            
    with col_actual:
        st.markdown("### 🏃‍♂️ 今日實際訓練回報")
        with st.form("daily_log"):
            train_date = st.date_input("執行日期")
            train_type = st.selectbox("類型", ["輕鬆恢復跑 (Zone 1)", "有氧耐力跑 (Zone 2)", "節奏/門檻跑 (Zone 3)", "無氧間歇跑 (Zone 4)", "其他/交叉訓練"])
            c_d, c_t = st.columns(2)
            with c_d: distance_km = st.number_input("實際距離(km)", min_value=0.0, value=8.0)
            with c_t: duration_min = st.number_input("實際時間(分)", min_value=1, value=45)
            intervals = st.text_input("備註 (可留白)")
            rpe = st.slider("實際疲勞 (RPE 0-10)", 0, 10, 6)
            
            if st.form_submit_button("📝 送出實際紀錄"):
                srpe_val = duration_min * rpe
                conn = sqlite3.connect(DB_FILE); cursor = conn.cursor()
                cursor.execute("INSERT INTO training_logs (date, type, distance, duration, rpe, srpe, details) VALUES (?, ?, ?, ?, ?, ?, ?)", (str(train_date), train_type, distance_km, duration_min, rpe, srpe_val, intervals))
                conn.commit(); conn.close()
                st.session_state.training_logs.append({"date": str(train_date), "type": train_type, "distance": distance_km, "duration": duration_min, "rpe": rpe, "srpe": srpe_val, "details": intervals})
                st.success("實際紀錄已儲存！下方圖表已更新。")
                st.rerun()

    st.markdown("---")
    if st.session_state.training_logs:
        df = pd.DataFrame(st.session_state.training_logs).sort_values('date')
        st.markdown("### 📊 累積實際訓練負荷與跑量")
        c_chart1, c_chart2 = st.columns(2)
        with c_chart1: st.line_chart(df.set_index("date")["distance"], color="#0068c9")
        with c_chart2: st.bar_chart(df.set_index("date")["srpe"], color="#ff4b4b")

# ---------------------------------------------------------
# 頁面 3：🧬 生理參數中心
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
                    cursor.execute("INSERT INTO physio_history (date, cs, d_prime) VALUES (?, ?, ?)", (str(test_date), slope, intercept))
                    conn.commit(); conn.close()
                    
                    st.session_state.update({"cs": slope, "d_prime": intercept, "tests_submitted": True})
                    st.success("生理模型已更新！")
                    st.rerun()

    st.markdown("---")
    st.markdown("### 📈 臨界速度 (CS) 與無氧儲備 (D') 成長曲線")
    
    conn = sqlite3.connect(DB_FILE)
    df_physio = pd.read_sql_query("SELECT date, cs, d_prime FROM physio_history ORDER BY date ASC", conn)
    conn.close()

    if not df_physio.empty:
        df_physio['date'] = pd.to_datetime(df_physio['date']).dt.strftime('%Y-%m-%d')
        fig_col1, fig_col2 = st.columns(2)
        with fig_col1:
            fig_cs = px.line(df_physio, x='date', y='cs', markers=True, title="臨界速度 CS (m/s) 趨勢")
            fig_cs.update_traces(line_color="#0068c9", marker=dict(size=8))
            st.plotly_chart(fig_cs, use_container_width=True)
            
        with fig_col2:
            fig_dp = px.line(df_physio, x='date', y='d_prime', markers=True, title="無氧儲備 D' (m) 趨勢")
            fig_dp.update_traces(line_color="#ff4b4b", marker=dict(size=8))
            st.plotly_chart(fig_dp, use_container_width=True)
    else:
        st.info("尚無歷史測驗紀錄。請在上方「新增測驗成績解算」輸入成績，系統將自動為您繪製成長曲線！")

# ---------------------------------------------------------
# 頁面 4：💬 AI 科學分析師 (自動抓取課表引擎)
# ---------------------------------------------------------
elif page == "💬 AI 科學分析師":
    st.title("💬 運動科學大腦")
    st.caption("請教練安排課表後，系統會自動辨識並同步至「訓練儀表板」。")
    
    chat_container = st.container(height=500)
    with chat_container:
        for msg in st.session_state.messages:
            with st.chat_message(msg["role"]): st.markdown(msg["content"])

    c_text, c_audio = st.columns([5, 1])
    with c_text: prompt_text = st.chat_input("請幫我安排下週的微週期課表...")
    with c_audio:
        with st.popover("🎤"): audio_file = st.audio_input("錄音回報")

    active_prompt = prompt_text if prompt_text else ("🎤 [語音回報]" if audio_file else "")
    
    if active_prompt:
        # 存入資料庫
        conn = sqlite3.connect(DB_FILE); cursor = conn.cursor()
        cursor.execute("INSERT INTO chat_messages (role, content, timestamp) VALUES (?, ?, ?)", ("user", active_prompt, str(datetime.now())))
        conn.commit(); conn.close()
        st.session_state.messages.append({"role": "user", "content": active_prompt})
        
        history = "\n".join([f"- {l['date']}: {l['type']}, {l['distance']}km, {l['duration']}min" for l in st.session_state.training_logs[-3:]])
        
        # 🌟 賦予 AI 結構化輸出的嚴格指令
        sys_inst = f"{agent_personality}\n\n【文獻知識】\n{knowledge_base_content}\n\n" \
                   f"【生理與目標數據】\nCS: {st.session_state.cs:.2f} m/s, D': {st.session_state.d_prime:.0f}m\n" \
                   f"可訓練時段: {','.join(st.session_state.available_slots)}\n" \
                   f"目標賽事日: {st.session_state.get('race_date')}\n" \
                   f"近期訓練:\n{history}\n\n" \
                   f"【重要開發指令】：當你為選手「安排」或「修改」未來課表時，除了提供專業的文字解說，請務必在回覆的最下方，附帶一段 JSON 格式的數據。必須以 ```json 開頭並以 
``` 結尾。\n" \
                   f"JSON 格式範例：\n" \
                   f"[\n" \
                   f'  {{"date": "2026-06-15", "type": "輕鬆恢復跑 (Zone 1)", "distance": 6.0, "duration": 40, "rpe": 3, "details": "心率維持在130以下"}}\n' \
                   f"]\n" \
                   f"注意：type 必須嚴格等於這五種之一：[輕鬆恢復跑 (Zone 1), 有氧耐力跑 (Zone 2), 節奏/門檻跑 (Zone 3), 無氧間歇跑 (Zone 4), 其他/交叉訓練]。"

        if api_key:
            with st.spinner("AI 思考中並編寫課表..."):
                try:
                    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3.5-flash:generateContent?key={api_key}"
                    parts = [{"inlineData": {"mimeType": audio_file.type, "data": base64.b64encode(audio_file.read()).decode("utf-8")}}, {"text": "這是語音，請聽取並指導。"}] if audio_file else [{"text": active_prompt}]
                    payload = {"systemInstruction": {"parts": [{"text": sys_inst}]}, "contents": [{"role": "user", "parts": parts}]}
                    res = requests.post(url, headers={"Content-Type": "application/json"}, json=payload, verify=False).json()
                    
                    if "candidates" in res:
                        ai_reply = res["candidates"][0]["content"]["parts"][0]["text"]
                        
                        # 🌟 攔截 JSON 並存入訓練計畫資料庫
                        json_match = re.search(r'```json\n(.*?)\n```', ai_reply, re.DOTALL)
                        if json_match:
                            try:
                                plan_data = json.loads(json_match.group(1))
                                conn = sqlite3.connect(DB_FILE); cursor = conn.cursor()
                                for day_plan in plan_data:
                                    cursor.execute("INSERT INTO training_plan (date, type, distance, duration, rpe, details) VALUES (?, ?, ?, ?, ?, ?)", 
                                        (day_plan['date'], day_plan['type'], float(day_plan['distance']), int(day_plan['duration']), int(day_plan['rpe']), day_plan.get('details', '')))
                                conn.commit(); conn.close()
                                
                                st.session_state.training_plan.extend(plan_data)
                                ai_reply += "\n\n✅ **[系統提示：已偵測到結構化課表，並成功同步至「訓練儀表板」！]**"
                            except Exception as e:
                                ai_reply += f"\n\n⚠️ **[系統提示：課表同步失敗，格式有誤]** {e}"
                                
                    else:
                        ai_reply = f"❌ API 異常: {res}"
                except Exception as e: ai_reply = f"❌ 串接失敗: {e}"
        else:
            ai_reply = "💡 **【Demo 模式】** 真實模式下，若對話中包含課表，系統將自動解析並寫入左側儀表板。"

        conn = sqlite3.connect(DB_FILE); cursor = conn.cursor()
        cursor.execute("INSERT INTO chat_messages (role, content, timestamp) VALUES (?, ?, ?)", ("assistant", ai_reply, str(datetime.now())))
        conn.commit(); conn.close()
        st.session_state.messages.append({"role": "assistant", "content": ai_reply})
        st.rerun()