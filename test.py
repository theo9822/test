import streamlit as st
import pandas as pd
import sqlite3
import json
import hashlib
import io
import os
from datetime import datetime
import streamlit.components.v1 as components

# --- Configuration & Setup ---
st.set_page_config(page_title="FTC Multi-Judge App", page_icon="🤖", layout="wide")

# --- Custom CSS Styling ---
def apply_custom_css():
    st.markdown("""
        <style>
        #MainMenu {visibility: hidden;}
        footer {visibility: hidden;}
        header {visibility: hidden;}
        
        .main-title {
            background: -webkit-linear-gradient(45deg, #FF4B4B, #FF8F00);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            font-size: 3.5rem;
            font-weight: 800;
            padding-bottom: 10px;
        }

        div.stButton > button:first-child {
            border-radius: 8px;
            font-weight: bold;
            transition: all 0.3s ease;
            box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
        }
        div.stButton > button:first-child:hover {
            transform: translateY(-2px);
            box-shadow: 0 6px 12px rgba(0, 0, 0, 0.2);
            border-color: #FF4B4B;
            color: #FF4B4B;
        }
        
        [data-testid="stForm"] {
            border-radius: 15px;
            box-shadow: 0 4px 15px rgba(0, 0, 0, 0.05);
            border: 1px solid rgba(200, 200, 200, 0.2);
        }
        </style>
    """, unsafe_allow_html=True)

apply_custom_css()

# --- Database Setup ---
def get_db_connection():
    conn = sqlite3.connect('ftc_judging.db', check_same_thread=False)
    return conn

def init_db():
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users (username TEXT PRIMARY KEY, password TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS teams (team_number TEXT PRIMARY KEY, team_name TEXT, division TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS scores 
                 (username TEXT, team_number TEXT, award TEXT, criteria_json TEXT, field_rank INTEGER, notes TEXT, is_eligible INTEGER,
                 PRIMARY KEY(username, team_number, award))''')
    c.execute('''CREATE TABLE IF NOT EXISTS audit_logs 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP, 
                 username TEXT, team_number TEXT, award TEXT, data_dump TEXT)''')
    conn.commit()
    conn.close()

init_db()

# --- Auth Helper Functions ---
def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def create_user(username, password):
    conn = get_db_connection()
    try:
        conn.execute("INSERT INTO users (username, password) VALUES (?, ?)", (username, hash_password(password)))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()

def authenticate_user(username, password):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT password FROM users WHERE username=?", (username,))
    result = c.fetchone()
    conn.close()
    return result and result[0] == hash_password(password)

# --- Award Criteria & Logic ---
AWARDS = {
    "Design Award": {
        "Required": ["Req 1: Elegant, efficient, and practical to maintain", "Req 2: Entire machine design/process is worthy"],
        "Encouraged": ["Enc 1: Distinguishes itself by aesthetic and functional design", "Enc 2: Basis for design is well considered", "Enc 3: Effective and consistent with strategy"]
    },
    "Innovate Award": {
        "Required": ["Req 1: Engineering content illustrates how they arrived at solution", "Req 2: ROBOT or MECHANISM is creative and unique", "Req 3: Innovative element is stable, robust, and contributes positively"],
        "Encouraged": ["Enc 1: Discusses/documents how they mitigated design risks"]
    }
}

def calculate_field_points(rank):
    if rank <= 0: return 0
    elif 1 <= rank <= 5: return 3
    elif 6 <= rank <= 10: return 2
    elif 11 <= rank <= 15: return 1
    return 0

# --- App Layout & Authentication ---
if 'logged_in' not in st.session_state:
    st.session_state.update({'logged_in': False, 'username': ''})

if not st.session_state['logged_in']:
    st.markdown('<p class="main-title">🤖 FTC Judging App</p>', unsafe_allow_html=True)
    st.info("💡 **Tip:** Create an account with the username **admin** to access the Admin & Export area.")
    
    col1, col2 = st.columns([1, 1])
    with col1:
        auth_mode = st.radio("Choose Action", ["Login", "Create Account"], horizontal=True)
        username = st.text_input("Username").strip()
        password = st.text_input("Password", type="password")
        
        if st.button("Submit", use_container_width=True):
            if auth_mode == "Create Account":
                if create_user(username, password):
                    st.success("✅ Account created! You can now login.")
                else:
                    st.error("❌ Username already exists.")
            elif authenticate_user(username, password):
                st.session_state.update({'logged_in': True, 'username': username})
                st.rerun()
            else:
                st.error("❌ Invalid username or password.")
    st.stop()

# --- Main Application ---
st.markdown('<p class="main-title">🤖 FTC Judging App</p>', unsafe_allow_html=True)

col1, col2 = st.columns([8, 2])
with col1:
    st.markdown(f"**👤 Current Judge:** `{st.session_state['username']}`")
with col2:
    if st.button("🚪 Logout", use_container_width=True):
        st.session_state.update({'logged_in': False, 'username': ''})
        st.rerun()

tab1, tab2, tab3, tab4, tab5, tab6, tab7 = st.tabs(["📋 Teams", "⚖️ Judging", "👀 View All Grades", "🏆 Leaderboards", "⚙️ Admin & Export", "🌐 Live Match Data", "⏱️ Time Keeper"])

conn = get_db_connection()
try:
    teams_df = pd.read_sql_query("SELECT * FROM teams", conn)
except pd.errors.DatabaseError:
    teams_df = pd.DataFrame(columns=['team_number', 'team_name', 'division'])

# --- TAB 1: Teams ---
with tab1:
    st.header("📋 Manage Teams")
    st.info("Admins can bulk-import teams from a file in the '⚙️ Admin & Export' tab.")
    with st.form("add_team"):
        st.subheader("➕ Manual Entry")
        col_t1, col_t2, col_t3 = st.columns(3)
        with col_t1:
            t_num = st.text_input("Team Number")
        with col_t2:
            t_name = st.text_input("Team Name")
        with col_t3:
            t_div = st.selectbox("Division", ["VLAICU", "COANDA"])
            
        if st.form_submit_button("Add Team") and t_num and t_name:
            try:
                conn.execute("INSERT INTO teams (team_number, team_name, division) VALUES (?, ?, ?)", (t_num, t_name, t_div))
                conn.commit()
                st.success(f"Team {t_num} added to {t_div}!")
                st.rerun()
            except sqlite3.IntegrityError:
                st.error("Team number already exists.")
    
    st.dataframe(teams_df, use_container_width=True, hide_index=True)

# --- TAB 2: Judging ---
with tab2:
    if teams_df.empty:
        st.warning("⚠️ Add teams first!")
    else:
        st.header("⚖️ Submit Scores")
        
        selected_div = st.radio("Filter Teams by Division:", ["All Teams", "VLAICU", "COANDA"], horizontal=True)
        filtered_teams = teams_df if selected_div == "All Teams" else teams_df[teams_df['division'] == selected_div]
        
        if filtered_teams.empty:
            st.info(f"No teams found in {selected_div}.")
        else:
            col_s1, col_s2 = st.columns(2)
            with col_s1:
                team_options = filtered_teams['team_number'] + " - " + filtered_teams['team_name'] + " (" + filtered_teams['division'] + ")"
                selected_team_str = st.selectbox("Select Team", sorted(team_options.tolist()))
                selected_team_num = selected_team_str.split(" - ")[0]
            with col_s2:
                award_choice = st.selectbox("Select Award", ["Design Award", "Innovate Award"])
            
            req_criteria = AWARDS[award_choice]["Required"]
            enc_criteria = AWARDS[award_choice]["Encouraged"]
            all_criteria = req_criteria + enc_criteria
            
            c = conn.cursor()
            c.execute("SELECT criteria_json, field_rank, notes, is_eligible FROM scores WHERE username=? AND team_number=? AND award=?", 
                      (st.session_state['username'], selected_team_num, award_choice))
            existing_data = c.fetchone()
            
            current_scores = json.loads(existing_data[0]) if existing_data else {crit: 0.0 for crit in all_criteria}
            current_rank = existing_data[1] if existing_data else 0
            current_notes = existing_data[2] if existing_data else ""

            with st.form("grade_form"):
                st.markdown("### 🔴 Required Criteria")
                new_scores, req_checks = {}, {}
                
                # CHANGED: Swapped st.slider for st.number_input
                for req in req_criteria:
                    prev_checked = current_scores.get(req, 0.0) > 0 or existing_data is None
                    req_checks[req] = st.checkbox(req, value=prev_checked)
                    if req_checks[req]:
                        new_scores[req] = st.number_input(f"{req} (0-10)", min_value=0.0, max_value=10.0, step=0.5, value=float(current_scores.get(req, 0.0)))
                    else:
                        new_scores[req] = 0.0

                st.markdown("### 🟢 Encouraged Criteria")
                # CHANGED: Swapped st.slider for st.number_input
                for enc in enc_criteria:
                    new_scores[enc] = st.number_input(f"{enc} (0-10)", min_value=0.0, max_value=10.0, step=0.5, value=float(current_scores.get(enc, 0.0)))
                
                st.markdown("---")
                col_f1, col_f2 = st.columns([1, 2])
                with col_f1:
                    field_rank = st.number_input("Field Rank Position (e.g., 1)", min_value=0, step=1, value=int(current_rank))
                with col_f2:
                    notes = st.text_area("Notes", value=current_notes, height=68)
                
                confirm_ineligible = st.checkbox("⚠️ I confirm this team does NOT meet all requirements and is INELIGIBLE.")

                if st.form_submit_button("💾 Save Scores", use_container_width=True):
                    all_req_met = all(req_checks.values())
                    if not all_req_met and not confirm_ineligible:
                        st.error("🛑 Wait! You left a required criteria unchecked. Confirm they are ineligible using the checkbox to save.")
                    else:
                        is_eligible = 1 if all_req_met else 0
                        json_dump = json.dumps(new_scores)
                        
                        conn.execute('''INSERT OR REPLACE INTO scores (username, team_number, award, criteria_json, field_rank, notes, is_eligible)
                                        VALUES (?, ?, ?, ?, ?, ?, ?)''', 
                                     (st.session_state['username'], selected_team_num, award_choice, json_dump, field_rank, notes, is_eligible))
                        
                        log_data = json.dumps({"scores": new_scores, "rank": field_rank, "notes": notes, "eligible": is_eligible})
                        conn.execute('''INSERT INTO audit_logs (username, team_number, award, data_dump) VALUES (?, ?, ?, ?)''',
                                     (st.session_state['username'], selected_team_num, award_choice, log_data))
                        
                        conn.commit()
                        st.success("✨ Scores saved securely!")

# --- TAB 3: View All Grades ---
try:
    all_scores_df = pd.read_sql_query("SELECT * FROM scores", conn)
except pd.errors.DatabaseError:
    all_scores_df = pd.DataFrame()

with tab3:
    st.header("👀 Individual Judge Submissions")
    if not all_scores_df.empty and not teams_df.empty:
        df_view = all_scores_df.copy()
        df_view = df_view.merge(teams_df[['team_number', 'division']], on='team_number', how='left')
        df_view['Criteria Sum'] = df_view['criteria_json'].apply(lambda x: sum(json.loads(x).values()))
        df_view['Field Points'] = df_view['field_rank'].apply(calculate_field_points)
        df_view['Judge Total'] = df_view['Criteria Sum'] + df_view['Field Points']
        df_view['Status'] = df_view['is_eligible'].apply(lambda x: "✅ Eligible" if x == 1 else "❌ Ineligible")
        st.dataframe(df_view[['username', 'division', 'team_number', 'award', 'Status', 'Judge Total', 'notes']], use_container_width=True, hide_index=True)
    else:
        st.info("No grades submitted yet.")

# --- TAB 4: Final Leaderboard ---
with tab4:
    st.header("🏆 Final Aggregated Leaderboard")
    if not all_scores_df.empty and not teams_df.empty:
        df_calc = all_scores_df.copy()
        df_calc['Judge Total'] = df_calc['criteria_json'].apply(lambda x: sum(json.loads(x).values())) + df_calc['field_rank'].apply(calculate_field_points)
        
        ineligible_flags = df_calc.groupby(['team_number', 'award'])['is_eligible'].min().reset_index()
        final_totals = df_calc.groupby(['team_number', 'award'])['Judge Total'].sum().reset_index()
        final_totals = final_totals.merge(ineligible_flags, on=['team_number', 'award']).merge(teams_df, on='team_number', how='left')
        
        eligible_teams = final_totals[final_totals['is_eligible'] == 1]
        
        div_tab1, div_tab2 = st.tabs(["🔵 VLAICU Division", "🟠 COANDA Division"])
        
        for idx, div_name in enumerate(["VLAICU", "COANDA"]):
            current_tab = div_tab1 if idx == 0 else div_tab2
            with current_tab:
                div_teams = eligible_teams[eligible_teams['division'] == div_name]
                if div_teams.empty:
                    st.info(f"No eligible scores for {div_name} yet.")
                else:
                    colA, colB = st.columns(2)
                    with colA:
                        st.subheader("📐 Design Award")
                        design_df = div_teams[div_teams['award'] == 'Design Award'].sort_values(by='Judge Total', ascending=False)
                        st.dataframe(design_df[['team_number', 'team_name', 'Judge Total']], hide_index=True, use_container_width=True)
                    with colB:
                        st.subheader("💡 Innovate Award")
                        innovate_df = div_teams[div_teams['award'] == 'Innovate Award'].sort_values(by='Judge Total', ascending=False)
                        st.dataframe(innovate_df[['team_number', 'team_name', 'Judge Total']], hide_index=True, use_container_width=True)
    else:
        st.info("No judging data yet.")

# --- TAB 5: Admin & Export ---
with tab5:
    if st.session_state['username'].lower() != 'admin':
        st.error("🚫 Access Restricted. You must be logged in as 'admin' to view this area.")
    else:
        st.header("⚙️ Admin Dashboard")
        
        st.subheader("📈 Live Competition Stats")
        m1, m2, m3 = st.columns(3)
        total_teams = len(teams_df)
        try:
            total_judges = pd.read_sql_query("SELECT COUNT(username) FROM users", conn).iloc[0,0]
        except:
            total_judges = 0
        total_scores = len(all_scores_df) if not all_scores_df.empty else 0
        
        m1.metric("Total Teams", total_teams)
        m2.metric("Registered Judges", total_judges)
        m3.metric("Grades Submitted", total_scores)
        st.markdown("---")
        
        st.subheader("📥 Bulk Import Teams")
        st.write("Upload an excel or csv with 3 columns: **Team Number**, **Team Name**, and **Division** (must be VLAICU or COANDA).")
        uploaded_file = st.file_uploader("Upload File", type=['csv', 'xlsx'])
        if uploaded_file is not None:
            if st.button("Import Teams"):
                try:
                    if uploaded_file.name.endswith('.csv'):
                        df_import = pd.read_csv(uploaded_file, dtype=str)
                    else:
                        df_import = pd.read_excel(uploaded_file, dtype=str)
                    
                    required_cols = ['Team Number', 'Team Name', 'Division']
                    if all(col in df_import.columns for col in required_cols):
                        success_count = 0
                        for _, row in df_import.iterrows():
                            t_num = str(row['Team Number']).strip()
                            t_name = str(row['Team Name']).strip()
                            t_div = str(row['Division']).strip().upper()
                            
                            if t_div not in ["VLAICU", "COANDA"]:
                                t_div = "VLAICU"
                                
                            try:
                                conn.execute("INSERT INTO teams (team_number, team_name, division) VALUES (?, ?, ?)", (t_num, t_name, t_div))
                                success_count += 1
                            except sqlite3.IntegrityError:
                                pass 
                        conn.commit()
                        st.success(f"Successfully imported {success_count} new teams!")
                        st.rerun()
                    else:
                        st.error(f"❌ Error: Your file must contain columns named exactly: {', '.join(required_cols)}")
                except Exception as e:
                    st.error(f"Error reading file: {e}")

        st.markdown("---")

        st.subheader("📊 Export Complete Judging Data")
        if not all_scores_df.empty:
            df_export = all_scores_df.copy()
            df_export = df_export.merge(teams_df, on='team_number', how='left')
            def generate_excel():
                output = io.BytesIO()
                with pd.ExcelWriter(output, engine='openpyxl') as writer:
                    if 'final_totals' in locals():
                        summary_df = final_totals.rename(columns={'Judge Total': 'Combined Score', 'is_eligible': 'Eligibility (1=Yes, 0=No)'})
                        summary_df.to_excel(writer, sheet_name="Final Leaderboards", index=False)
                    
                    unique_judges = df_export['username'].unique()
                    for judge in unique_judges:
                        judge_df = df_export[df_export['username'] == judge].copy()
                        criteria_unpacked = pd.json_normalize(judge_df['criteria_json'].apply(json.loads))
                        criteria_unpacked.index = judge_df.index
                        judge_df['Criteria Sum'] = judge_df['criteria_json'].apply(lambda x: sum(json.loads(x).values()))
                        judge_df['Field Pts'] = judge_df['field_rank'].apply(calculate_field_points)
                        judge_df['Final Points'] = judge_df['Criteria Sum'] + judge_df['Field Pts']
                        judge_clean = judge_df.drop(columns=['criteria_json']).join(criteria_unpacked)
                        cols = ['division', 'team_number', 'team_name', 'award', 'is_eligible', 'field_rank', 'Field Pts', 'Criteria Sum', 'Final Points', 'notes']
                        cols += [c for c in criteria_unpacked.columns]
                        judge_clean[cols].to_excel(writer, sheet_name=f"Judge_{judge}", index=False)
                return output.getvalue()

            st.download_button(
                label="📥 Download Complete Excel Report (.xlsx)",
                data=generate_excel(),
                file_name=f"FTC_Judging_Export_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                type="primary"
            )
        else:
            st.info("No data available to export yet.")

        st.markdown("---")
        
        st.subheader("💾 Database Management")
        col_db1, col_db2 = st.columns(2)
        
        with col_db1:
            st.markdown("**1. Download Backup**")
            with open("ftc_judging.db", "rb") as f:
                st.download_button("⬇️ Download ftc_judging.db", data=f, file_name=f"ftc_backup_{datetime.now().strftime('%Y%m%d_%H%M')}.db", mime="application/octet-stream")
        
        with col_db2:
            st.markdown("**2. Restore Database**")
            uploaded_db = st.file_uploader("Upload a backup .db file", type=['db'], label_visibility="collapsed")
            if uploaded_db is not None:
                if st.button("🚨 Confirm Restore"):
                    conn.close() 
                    with open("ftc_judging.db", "wb") as f:
                        f.write(uploaded_db.getvalue())
                    st.session_state.update({'logged_in': False, 'username': ''}) 
                    st.rerun()

        st.markdown("**3. Danger Zone: Factory Reset**")
        if st.checkbox("I understand this permanently deletes ALL data."):
            if st.button("🧨 Wipe Database"):
                conn.close()
                if os.path.exists("ftc_judging.db"):
                    os.remove("ftc_judging.db")
                st.session_state.update({'logged_in': False, 'username': ''})
                st.rerun()

        st.markdown("---")
        st.subheader("📜 System Audit Logs")
        try:
            logs_df = pd.read_sql_query("SELECT * FROM audit_logs ORDER BY timestamp DESC", conn)
            st.dataframe(logs_df, use_container_width=True, hide_index=True, height=200)
        except pd.errors.DatabaseError:
            st.info("No logs available.")

# --- TAB 6: Live Event Data (FTC Events) ---
with tab6:
    st.header("🌐 Live Event Rankings & Matches")
    st.write("Live data pulled directly from the official FTC Events page.")
    
    event_div = st.radio("Select Division to View:", ["🔵 VLAICU", "🟠 COANDA"], horizontal=True)
    
    urls = {
        "🔵 VLAICU": "https://ftc-events.firstinspires.org/2025/ROCMPVLC",
        "🟠 COANDA": "https://ftc-events.firstinspires.org/2025/ROCMPCND"
    }
    
    selected_url = urls[event_div]
    
    data_tab1, data_tab2 = st.tabs(["🏅 Qualification Rankings", "⏱️ Match Results"])
    
    with data_tab1:
        st.markdown(f"**Viewing Rankings for {event_div}**")
        components.iframe(f"{selected_url}/rankings", height=600, scrolling=True)
        
    with data_tab2:
        st.markdown(f"**Viewing Match Schedule & Results for {event_div}**")
        components.iframe(f"{selected_url}/qualifications", height=600, scrolling=True)
        
    st.caption(f"If the embedded page doesn't load, you can [click here to open the official FIRST page]({selected_url}) in a new tab.")

# --- TAB 7: TIME KEEPER ---
with tab7:
    st.header("⏱️ Judging Time Keeper")
    st.write("Use this timer to keep pit interviews running on schedule. A loud alarm will sound when time is up!")
    
    # Custom HTML/JS with ONINPUT triggers and 5 loud beeps
    timer_html = """
    <div style="font-family: Arial, sans-serif; text-align: center; padding: 30px; background: #262730; border-radius: 15px; border: 2px solid #FF4B4B; color: white;">
        <h1 style="font-size: 5rem; margin: 10px; font-variant-numeric: tabular-nums;" id="display">05:00</h1>
        
        <div style="margin: 20px 0;">
            <label style="font-size: 1.2rem; margin-right: 10px;">
                <input type="number" id="mins" value="5" min="0" oninput="updateFromInputs()" style="width: 70px; font-size: 1.2rem; padding: 5px; text-align: center; border-radius: 5px; border: none; color: black;"> Minutes
            </label>
            <label style="font-size: 1.2rem;">
                <input type="number" id="secs" value="0" min="0" max="59" oninput="updateFromInputs()" style="width: 70px; font-size: 1.2rem; padding: 5px; text-align: center; border-radius: 5px; border: none; color: black;"> Seconds
            </label>
        </div>
        
        <div style="margin-top: 25px;">
            <button onclick="startTimer()" style="font-size: 1.5rem; font-weight: bold; padding: 10px 25px; margin: 5px; cursor: pointer; border-radius: 8px; background: #4CAF50; color: white; border: none; box-shadow: 0 4px 6px rgba(0,0,0,0.3);">▶ Start</button>
            <button onclick="pauseTimer()" style="font-size: 1.5rem; font-weight: bold; padding: 10px 25px; margin: 5px; cursor: pointer; border-radius: 8px; background: #FF9800; color: white; border: none; box-shadow: 0 4px 6px rgba(0,0,0,0.3);">⏸ Pause</button>
            <button onclick="resetTimer()" style="font-size: 1.5rem; font-weight: bold; padding: 10px 25px; margin: 5px; cursor: pointer; border-radius: 8px; background: #F44336; color: white; border: none; box-shadow: 0 4px 6px rgba(0,0,0,0.3);">🔄 Reset</button>
        </div>
    </div>

    <script>
    let timerInterval;
    let timeRemaining = 300; 
    let isRunning = false;
    
    function playBeep() {
        const AudioContext = window.AudioContext || window.webkitAudioContext;
        const ctx = new AudioContext();
        
        // Loop to create 5 distinct, annoying beeps
        for (let i = 0; i < 5; i++) {
            const osc = ctx.createOscillator();
            const gain = ctx.createGain();
            
            osc.connect(gain);
            gain.connect(ctx.destination);
            
            // "Square" wave is much harsher and louder than a smooth "sine" wave
            osc.type = "square"; 
            osc.frequency.value = 1000; // High pitch to cut through pit noise
            
            // Schedule the beep: starts at current time + spacing (0.4 seconds apart)
            let startTime = ctx.currentTime + (i * 0.4);
            let stopTime = startTime + 0.2; // Each beep lasts 0.2 seconds
            
            // Fast attack and release so it sounds sharp
            gain.gain.setValueAtTime(0, startTime);
            gain.gain.linearRampToValueAtTime(1, startTime + 0.01);
            gain.gain.setValueAtTime(1, stopTime - 0.01);
            gain.gain.linearRampToValueAtTime(0, stopTime);
            
            osc.start(startTime);
            osc.stop(stopTime);
        }
    }

    function updateDisplay() {
        let m = Math.floor(timeRemaining / 60);
        let s = timeRemaining % 60;
        document.getElementById("display").innerText = 
            (m < 10 ? "0" + m : m) + ":" + (s < 10 ? "0" + s : s);
    }

    function updateFromInputs() {
        if (!isRunning) {
            let m = parseInt(document.getElementById("mins").value) || 0;
            let s = parseInt(document.getElementById("secs").value) || 0;
            timeRemaining = m * 60 + s;
            document.getElementById("display").style.color = "white";
            updateDisplay();
        }
    }

    function startTimer() {
        if (isRunning) return;
        
        if (timeRemaining <= 0) {
            updateFromInputs();
        }

        if (timeRemaining > 0) {
            isRunning = true;
            document.getElementById("display").style.color = "white";
            timerInterval = setInterval(() => {
                timeRemaining--;
                updateDisplay();
                if (timeRemaining <= 0) {
                    clearInterval(timerInterval);
                    isRunning = false;
                    playBeep(); // Fires off the 5 annoying beeps
                    
                    // Flash the screen red matching the duration of the beeps
                    document.getElementById("display").style.color = "#FF0000";
                    setTimeout(() => document.getElementById("display").style.color = "white", 400);
                    setTimeout(() => document.getElementById("display").style.color = "#FF0000", 800);
                    setTimeout(() => document.getElementById("display").style.color = "white", 1200);
                    setTimeout(() => document.getElementById("display").style.color = "#FF0000", 1600);
                    setTimeout(() => document.getElementById("display").style.color = "white", 2000);
                }
            }, 1000);
        }
    }

    function pauseTimer() {
        clearInterval(timerInterval);
        isRunning = false;
    }

    function resetTimer() {
        pauseTimer();
        updateFromInputs();
    }
    
    updateFromInputs();
    </script>
    """
    
    components.html(timer_html, height=450)

try:
    conn.close()
except:
    pass
