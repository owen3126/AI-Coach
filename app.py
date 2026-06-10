import streamlit as st
import os
import numpy as np
import requests
import urllib3
import base64
import PyPDF2  # 載入 PDF 閱讀套件

# 強制關閉 SSL 不安全警告 (確保穿透學校/公司防火牆)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# 頁面基本設定
st.set_page_config(page_title="AI 語音/文字訓練輔助平台", layout="wide")

# ---------------------------------------------------------
# 系統初始化與資料夾建立
# ---------------------------------------------------------
if not os.path.exists("papers"):
    os.makedirs("papers")

# 1. 讀取教練個性檔 (personality.md)
try:
    with open("personality.md", "r", encoding="utf-8") as f:
        agent_personality = f.read()
except FileNotFoundError:
    agent_personality = "你是一位頂尖的運動科學跑步教練，名字叫科學分析師。"

# 2. 自動讀取 papers/ 內所有的文獻內容 (支援 txt, md, pdf)
knowledge_base_content = ""
paper_files = [f for f in os.listdir("papers") if f.endswith(('.txt', '.md', '.pdf'))]

for file_name in paper_files:
    file_path = os.path.join("papers", file_name)
    try:
        if file_name.lower().endswith('.pdf'):
            # PDF 檔案的專屬萃取邏輯
            with open(file_path, "rb") as f:
                reader = PyPDF2.PdfReader(f)
                pdf_text = ""
                for page in reader.pages:
                    extracted = page.extract_text()
                    if extracted:
                        pdf_text += extracted + "\n"
                knowledge_base_content += f"\n\n【PDF文獻檔案：{file_name}】\n{pdf_text}"
        else:
            # 一般文字檔的讀取邏輯
            with open(file_path, "r", encoding="utf-8") as f:
                knowledge_base_content += f"\n\n【文獻檔案：{file_name}】\n" + f.read()
    except Exception:
        # 遇到加密或損毀檔案自動跳過
        pass

# 初始化 Session State 狀態記憶
if 'profile_saved' not in st.session_state:
    st.session_state.profile_saved = False
if 'tests_submitted' not in st.session_state:
    st.session_state.tests_submitted = False
if "messages" not in st.session_state:
    st.session_state.messages = []
if "training_logs" not in st.session_state:
    # 預載歷史精細訓練數據以利初始 ACWL 計算
    st.session_state.training_logs = [
        {"date": "2026-06-01", "type": "有氧耐力跑 (Zone 2)", "distance": 10.0, "duration": 50, "rpe": 5, "srpe": 250, "details": ""},
        {"date": "2026-06-03", "type": "節奏/門檻跑 (Zone 3)", "distance": 12.0, "duration": 60, "rpe": 6, "srpe": 360, "details": ""},
        {"date": "2026-06-05", "type": "輕鬆恢復跑 (Zone 1)", "distance": 6.0, "duration": 40, "rpe": 4, "srpe": 160, "details": ""},
        {"date": "2026-06-07", "type": "無氧間歇跑 (Zone 4)", "distance": 14.0, "duration": 90, "rpe": 7, "srpe": 630, "details": "1000m x 5"},
    ]
if "cs" not in st.session_state: st.session_state.cs = 4.0
if "d_prime" not in st.session_state: st.session_state.d_prime = 200.0
if "available_slots" not in st.session_state: st.session_state.available_slots = []

# ---------------------------------------------------------
# 側邊欄控制台
# ---------------------------------------------------------
with st.sidebar:
    st.title("📊 運動科學指標控制台")
    
    # API Key 彈出式視窗
    with st.popover("🔑 設定 Gemini 認證密鑰"):
        st.markdown("### API 金鑰配置")
        api_key = st.text_input("請輸入你的 Gemini API Key", type="password", help="輸入後將啟用真實 AI 對話大腦")
        st.caption("填寫完畢後點擊外部空白處即可自動鎖定")
    
    if st.session_state.profile_saved:
        st.markdown(f"**👤 選手姓名**：{st.session_state.get('name', '')}")
        st.markdown(f"**🎯 目標賽事**：{st.session_state.get('goal_str', '')}")
        
        with st.expander("📅 檢視我的可訓練時段"):
            if st.session_state.available_slots:
                st.write(", ".join(st.session_state.available_slots))
            else:
                st.info("未勾選特定時段")
                
        st.markdown("---")
        st.subheader("🧬 生理模型基準線")
        if st.session_state.tests_submitted:
            st.metric(label="臨界速度 Critical Speed (CS)", value=f"{st.session_state.cs:.2f} m/s", delta=f"{1000/st.session_state.cs/60:.2f} min/km")
            st.metric(label="無氧儲備距離 (D')", value=f"{st.session_state.d_prime:.0f} m")
        else:
            st.warning("請在右側工作台執行基準測驗解算")
            
        st.markdown("---")
        st.subheader("📈 疲勞負荷監控")
        srpe_list = [log["srpe"] for log in st.session_state.training_logs]
        if srpe_list:
            acute_load = sum(srpe_list[-7:])
            chronic_load = np.mean(srpe_list) * 7 if len(srpe_list) > 0 else 1.0
            acwl = acute_load / chronic_load
            st.metric(label="今日 ACWL 比值", value=f"{acwl:.2f}")
            if 0.8 <= acwl <= 1.3: st.success("🟢 處於安全適應區間")
            elif acwl > 1.5: st.error("🚨 進入過度訓練紅區")
            else: st.info("🟡 處於恢復或減量期")

    st.markdown("---")
    st.subheader("📚 運動科學文獻庫")
    st.info("請將運動科學文獻的 .txt 或 .pdf 檔案直接拖曳進專案的 papers/ 資料夾中，系統將於背景自動判讀。")

# ---------------------------------------------------------
# 主畫面邏輯
# ---------------------------------------------------------
if not st.session_state.profile_saved:
    st.title("🏃‍♂️ 建立專屬 AI 跑步模型")
    
    with st.form("setup_form"):
        col_info1, col_info2 = st.columns(2)
        with col_info1: name = st.text_input("姓名", value="楊云瑢")
        with col_info2: age = st.number_input("年齡", value=30)
            
        st.markdown("### 🎯 賽事目標設定")
        goal_type = st.radio("賽事項目", ["全程馬拉松", "半程馬拉松"])
        col_h, col_m = st.columns(2)
        with col_h: goal_hour = st.number_input("目標完賽：小時", value=2)
        with col_m: goal_minute = st.number_input("目標完賽：分鐘", value=48)
        
        st.markdown("---")
        st.markdown("### 📅 每週可訓練時段調查")
        
        col_am, col_pm = st.columns(2)
        with col_am:
            st.markdown("**🌅 上午 (AM) 可訓練日**")
            am_days = st.multiselect("選擇上午時段", ["週一", "週二", "週三", "週四", "週五", "週六", "週日"], default=["週二", "週三", "週四", "週六", "週日"])
        with col_pm:
            st.markdown("**🌇 下午/晚上 (PM) 可訓練日**")
            pm_days = st.multiselect("選擇下午/晚上時段", ["週一", "週二", "週三", "週四", "週五", "週六", "週日"], default=["週一", "週二", "週三", "週四", "週五", "週六", "週日"])
        
        st.markdown("---")
        submitted = st.form_submit_button("💾 儲存資料並喚醒 AI 教練")
        
        if submitted:
            selected_slots = [f"{d}_上午" for d in am_days] + [f"{d}_下午" for d in pm_days]
            st.session_state.name = name
            st.session_state.goal_str = f"{goal_type} {goal_hour:02d}:{goal_minute:02d}:00"
            st.session_state.available_slots = selected_slots
            st.session_state.profile_saved = True
            
            st.session_state.messages.append({
                "role": "assistant", 
                "content": f"你好 {name}！教練已成功上線。目標：**{st.session_state.goal_str}**。\n\n我已將你提交的每週 **{len(selected_slots)} 個可訓練時段** 寫入背景。**現在，你可以選擇下方打字跟我對話，或者展開「🎤 語音輸入工作台」用講的跟我報告！**"
            })
            st.rerun()

else:
    st.title("🎙️ AI 教練動態訓練主控台")
    st.caption(f"目前運行狀態：{'🟢 真正實證對話模式' if api_key else '💡 系統展示(Demo)模式'}")
    
    col_test, col_daily = st.columns(2)
    with col_test:
        with st.expander("📋 填寫/更新 4 項基準測驗成績", expanded=not st.session_state.tests_submitted):
            c1, c2 = st.columns(2)
            with c1:
                m800 = st.number_input("800m (分)", value=2); s800 = st.number_input("800m (秒)", value=28)
                m1600 = st.number_input("1600m (分)", value=5); s1600 = st.number_input("1600m (秒)", value=10)
            with c2:
                m2400 = st.number_input("2400m (分)", value=8); s2400 = st.number_input("2400m (秒)", value=0)
                m3600 = st.number_input("3600m (分)", value=12); s3600 = st.number_input("3600m (秒)", value=15)
            if st.button("🧮 執行運動科學線性迴歸解算"):
                times = np.array([m800*60+s800, m1600*60+s1600, m2400*60+s2400, m3600*60+s3600])
                distances = np.array([800, 1600, 2400, 3600])
                slope, intercept = np.polyfit(times, distances, 1)
                st.session_state.cs = slope
                st.session_state.d_prime = intercept
                st.session_state.tests_submitted = True
                st.session_state.messages.append({"role": "assistant", "content": f"【生理模型更新成功】CS: **{slope:.2f} m/s**, D': **{intercept:.0f} m**。"})
                st.rerun()

    with col_daily:
        with st.expander("🏃‍♂️ 填寫今日訓練回報 (精細日誌功能)", expanded=st.session_state.tests_submitted):
            train_date = st.date_input("訓練日期")
            train_type = st.selectbox("課表類型", ["輕鬆恢復跑 (Zone 1)", "有氧耐力跑 (Zone 2)", "節奏/門檻跑 (Zone 3)", "無氧間歇跑 (Zone 4)", "其他/交叉訓練"])
            
            c_dist, c_time = st.columns(2)
            with c_dist: distance_km = st.number_input("總距離 (公里)", min_value=0.0, value=8.0, step=0.1)
            with c_time: duration_min = st.number_input("總時間 (分鐘)", min_value=1, value=45)
                
            intervals = st.text_input("細節備註 (如間歇組數：400m x 10趟)", value="") if "間歇" in train_type else ""
            rpe = st.slider("自覺疲勞量表 (RPE, 0-10分)", 0, 10, 6)
            
            # 自動推算配速與強度比
            if distance_km > 0 and duration_min > 0:
                avg_pace_sec = (duration_min * 60) / distance_km
                avg_pace_str = f"{int(avg_pace_sec // 60)}:{int(avg_pace_sec % 60):02d} /km"
                avg_speed_ms = (distance_km * 1000) / (duration_min * 60)
                intensity_pct = (avg_speed_ms / st.session_state.cs) * 100 if st.session_state.cs > 0 else 0.0
                st.info(f"⚡ 系統試算：平均配速 **{avg_pace_str}** (約為臨界速度 CS 的 **{intensity_pct:.1f}%**)")

            if st.button("📝 送出今日精細日誌"):
                srpe_val = duration_min * rpe
                st.session_state.training_logs.append({
                    "date": str(train_date), "type": train_type, "distance": distance_km,
                    "duration": duration_min, "rpe": rpe, "srpe": srpe_val, "details": intervals
                })
                st.session_state.messages.append({"role": "assistant", "content": f"【日誌建檔】已記錄 {train_date} 的 {train_type}。單次負荷：{srpe_val} sRPE。"})
                st.rerun()

    st.markdown("---")
    
    # 語音輸入模組
    with st.expander("🎤 語音輸入工作台 (跑步完手抖、有汗時專用)", expanded=False):
        st.info("點擊下方麥克風允許網頁錄音，錄製完畢後系統會自動編碼並送給 Gemini 大腦！")
        audio_file = st.audio_input("錄製您的訓練回報或提問")

    # 顯示對話歷史
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    # 處理輸入
    prompt_text = st.chat_input("打字詢問下週微週期課表、檢視疲勞狀態...")
    
    is_voice = False
    active_prompt = ""
    base64_audio = ""
    audio_mime = ""
    
    if prompt_text:
        active_prompt = prompt_text
    elif audio_file:
        is_voice = True
        active_prompt = "🎤 [發送了一段語音回報，請聽取音訊]"
        audio_bytes = audio_file.read()
        base64_audio = base64.b64encode(audio_bytes).decode("utf-8")
        audio_mime = audio_file.type

    if active_prompt:
        st.session_state.messages.append({"role": "user", "content": active_prompt})
        
        # 建立結構化 System Prompt 記憶體
        history_summary = ""
        for log in st.session_state.training_logs[-3:]:
            history_summary += f"- {log.get('date')}: {log.get('type')}, {log.get('distance')}km, {log.get('duration')}min, RPE {log.get('rpe')}\n"

        system_instruction = f"{agent_personality}\n\n" \
                             f"【實證運動科學文獻知識庫如下】\n{knowledge_base_content}\n\n" \
                             f"【當前選手真實生理與作息數據】\n" \
                             f"- 選手姓名: {st.session_state.name}\n" \
                             f"- 目標: {st.session_state.goal_str}\n" \
                             f"- 臨界速度 (CS): {st.session_state.cs:.2f} m/s\n" \
                             f"- 無氧儲備距離 (D'): {st.session_state.d_prime:.0f} 米\n" \
                             f"- 選手可訓練時段: {', '.join(st.session_state.available_slots)}\n" \
                             f"- 最近三筆訓練歷史紀錄:\n{history_summary}\n\n" \
                             f"請依據上述設定、生理數據、歷史紀錄與作息空檔給予專業回覆。在安排微週期課表時，絕對不能把課表塞在選手沒有勾選的時間段。請務必使用繁體中文。"

        if api_key:
            with st.spinner("Gemini 教練正在調閱文獻並聽取訊息中..."):
                try:
                    # 使用穩定支援多模態的 Pro 1.5 級別大腦網址
                    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-pro:generateContent?key={api_key}"
                    headers = {"Content-Type": "application/json"}
                    
                    parts_list = []
                    if is_voice:
                        parts_list.append({"inlineData": {"mimeType": audio_mime, "data": base64_audio}})
                        parts_list.append({"text": "這是選手親自錄製的聲音，請直接聽取並給予科學指導。"})
                    else:
                        parts_list.append({"text": active_prompt})
                        
                    payload = {
                        "systemInstruction": {
                            "parts": [{"text": system_instruction}]
                        },
                        "contents": [
                            {
                                "role": "user",
                                "parts": parts_list
                            }
                        ]
                    }
                    response = requests.post(url, headers=headers, json=payload, verify=False)
                    res_json = response.json()
                    
                    if "candidates" in res_json:
                        ai_reply = res_json["candidates"][0]["content"]["parts"][0]["text"]
                    else:
                        ai_reply = f"❌ API 回應異常，伺服器可能過載或密鑰錯誤。詳細資訊：{res_json}"
                except Exception as e:
                    ai_reply = f"❌ 串接失敗。錯誤訊息: {str(e)}"
        else:
            if is_voice:
                ai_reply = "💡 **【系統 Demo 模式 - 語音辨識成功】**\n偵測到語音輸入！真實模式下，Gemini 將直接解讀音訊。"
            else:
                ai_reply = "💡 **【系統 Demo 模式提示】**\n目前為純展示狀態。System Prompt 已自動封裝您的生理與作息數據。"

        st.session_state.messages.append({"role": "assistant", "content": ai_reply})
        st.rerun()