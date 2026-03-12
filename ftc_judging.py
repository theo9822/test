import streamlit as st
import pandas as pd
import sqlite3
import json
import hashlib
import io
import os
from datetime import datetime

# --- Configuration & Setup ---
st.set_page_config(page_title="FTC Multi-Judge App", layout="wide")

# --- Database Setup ---
def get_db_connection():
    conn = sqlite3.connect('ftc_judging.db', check_same_thread=False)
    return conn

def init_db():
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users (username TEXT PRIMARY KEY, password TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS teams (team_number TEXT PRIMARY KEY, team_name TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS scores 
                 (username TEXT, team_number TEXT, award TEXT, criteria_json TEXT, field_rank INTEGER, notes TEXT, is_eligible INTEGER,
                 PRIMARY KEY(username, team_number, award))''')
    c.execute('''CREATE TABLE IF NOT EXISTS audit_logs 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP, 
                 username TEXT, team_number TEXT, award TEXT, data_dump TEXT)''')
    conn.commit()
    conn.close()

# Initialize DB on startup
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
    st.title("🔐 Login / Sign Up")
    st.info("💡 Tip: Create an account with the username **admin** to access the Admin & Export area.")
    auth_mode = st.radio("Choose Action", ["Login", "Create Account"])
    username = st.text_input("Username").strip()
    password = st.text_input("Password", type="password")
    
    if st.button("Submit"):
        if auth_mode == "Create Account":
            if create_user(username, password):
                st.success("Account created! You can now login.")
            else:
                st.error("Username already exists.")
        elif authenticate_user(username, password):
            st.session_state.update({'logged_in': True, 'username': username})
            st.rerun()
        else:
            st.error("Invalid username or password.")
    st.stop()

# --- Main Application ---
st.title(f"🤖 FTC Judging App")
col1, col2 = st.columns([8, 2])
with col1:
    st.markdown(f"**Current Judge:** `{st.session_state['username']}`")
with col2:
    if st.button("Logout", use_container_width=True):
        st.session_state.update({'logged_in': False, 'username': ''})
        st.rerun()

tab1, tab2, tab3, tab4, tab5 = st.tabs(["📋 Teams", "⚖️ Judging", "👀 View All Grades", "🏆 Leaderboards", "⚙️ Admin & Export"])

# Open the main connection for the app session
conn = get_db_connection()
try:
    teams_df = pd.read_sql_query("SELECT * FROM teams", conn)
except pd.errors.DatabaseError:
    # Failsafe if the DB was just wiped
    teams_df = pd.DataFrame(columns=['team_number', 'team_name'])

# --- TAB 1: Teams ---
with tab1:
    st.header("Manage Teams")
    st.info("Admins can bulk-import teams from a file in the '⚙️ Admin & Export' tab.")
    with st.form("add_team"):
        st.subheader("Manual Entry")
        t_num = st.text_input("Team Number")
        t_name = st.text_input("Team Name")
        if st.form_submit_button("Add Team") and t_num and t_name:
            try:
                conn.execute("INSERT INTO teams (team_number, team_name) VALUES (?, ?)", (t_num, t_name))
                conn.commit()
                st.success(f"Team {t_num} added!")
                st.rerun()
            except sqlite3.IntegrityError:
                st.error("Team number already exists.")
    
    st.dataframe(teams_df, use_container_width=True, hide_index=True)

# --- TAB 2: Judging ---
with tab2:
    if teams_df.empty:
        st.warning("Add teams first!")
    else:
        team_options = teams_df['team_number'] + " - " + teams_df['team_name']
        selected_team_str = st.selectbox("Select Team", sorted(team_options.tolist()))
        selected_team_num = selected_team_str.split(" - ")[0]
        award_choice = st.radio("Select Award", ["Design Award", "Innovate Award"], horizontal=True)
        
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
            
            for req in req_criteria:
                prev_checked = current_scores.get(req, 0.0) > 0 or existing_data is None
                req_checks[req] = st.checkbox(req, value=prev_checked)
                if req_checks[req]:
                    new_scores[req] = st.number_input(f"Score for {req[:15]}...", min_value=0.0, max_value=10.0, step=0.1, value=float(current_scores.get(req, 0.0)))
                else:
                    new_scores[req] = 0.0

            st.markdown("### 🟢 Encouraged Criteria")
            for enc in enc_criteria:
                new_scores[enc] = st.number_input(enc, min_value=0.0, max_value=10.0, step=0.1, value=float(current_scores.get(enc, 0.0)))
            
            st.markdown("---")
            field_rank = st.number_input("Field Rank Position (e.g., 1)", min_value=0, step=1, value=int(current_rank))
            notes = st.text_area("Notes", value=current_notes)
            confirm_ineligible = st.checkbox("I confirm this team does NOT meet all requirements and is INELIGIBLE.")

            if st.form_submit_button("Save Scores"):
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
                    st.success("Scores saved securely!")

# --- TAB 3: View All Grades ---
try:
    all_scores_df = pd.read_sql_query("SELECT * FROM scores", conn)
except pd.errors.DatabaseError:
    all_scores_df = pd.DataFrame()

with tab3:
    st.header("Individual Judge Submissions")
    if not all_scores_df.empty:
        df_view = all_scores_df.copy()
        df_view['Criteria Sum'] = df_view['criteria_json'].apply(lambda x: sum(json.loads(x).values()))
        df_view['Field Points'] = df_view['field_rank'].apply(calculate_field_points)
        df_view['Judge Total'] = df_view['Criteria Sum'] + df_view['Field Points']
        df_view['Status'] = df_view['is_eligible'].apply(lambda x: "✅ Eligible" if x == 1 else "❌ Ineligible")
        st.dataframe(df_view[['username', 'team_number', 'award', 'Status', 'Judge Total', 'notes']], use_container_width=True, hide_index=True)
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
        
        colA, colB = st.columns(2)
        with colA:
            st.subheader("Design Award")
            st.dataframe(eligible_teams[eligible_teams['award'] == 'Design Award'].sort_values(by='Judge Total', ascending=False)[['team_number', 'team_name', 'Judge Total']], hide_index=True)
        with colB:
            st.subheader("Innovate Award")
            st.dataframe(eligible_teams[eligible_teams['award'] == 'Innovate Award'].sort_values(by='Judge Total', ascending=False)[['team_number', 'team_name', 'Judge Total']], hide_index=True)
    else:
        st.info("No judging data yet.")

# --- TAB 5: Admin & Export ---
with tab5:
    if st.session_state['username'].lower() != 'admin':
        st.error("🚫 Access Restricted. You must be logged in as 'admin' to view this area.")
    else:
        st.header("⚙️ Admin Dashboard")
        
        # --- BULK IMPORT TEAMS ---
        st.subheader("📥 Bulk Import Teams")
        st.write("Upload a `.csv` or `.xlsx` file containing two columns exactly named: **Team Number** and **Team Name**.")
        uploaded_file = st.file_uploader("Choose File", type=['csv', 'xlsx'])
        if uploaded_file is not None:
            if st.button("Import Teams"):
                try:
                    if uploaded_file.name.endswith('.csv'):
                        df_import = pd.read_csv(uploaded_file, dtype=str)
                    else:
                        df_import = pd.read_excel(uploaded_file, dtype=str)
                    
                    if 'Team Number' in df_import.columns and 'Team Name' in df_import.columns:
                        success_count = 0
                        for _, row in df_import.iterrows():
                            t_num = str(row['Team Number']).strip()
                            t_name = str(row['Team Name']).strip()
                            try:
                                conn.execute("INSERT INTO teams (team_number, team_name) VALUES (?, ?)", (t_num, t_name))
                                success_count += 1
                            except sqlite3.IntegrityError:
                                pass 
                        conn.commit()
                        st.success(f"Successfully imported {success_count} new teams! Duplicate team numbers were ignored.")
                        st.rerun()
                    else:
                        st.error("❌ Error: Your file must contain columns named exactly 'Team Number' and 'Team Name'.")
                except Exception as e:
                    st.error(f"Error reading file: {e}")

        st.markdown("---")

        # --- EXCEL EXPORT ---
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
                        cols = ['team_number', 'team_name', 'award', 'is_eligible', 'field_rank', 'Field Pts', 'Criteria Sum', 'Final Points', 'notes']
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
        
        # --- DATABASE MANAGEMENT (BACKUP, RESTORE, WIPE) ---
        st.subheader("💾 Database Management")
        st.write("Safely backup your database file, restore an old one, or factory-reset the application.")
        
        col_db1, col_db2 = st.columns(2)
        
        # 1. DOWNLOAD DB
        with col_db1:
            st.markdown("**1. Download Backup**")
            with open("ftc_judging.db", "rb") as f:
                st.download_button(
                    label="⬇️ Download ftc_judging.db",
                    data=f,
                    file_name=f"ftc_backup_{datetime.now().strftime('%Y%m%d_%H%M')}.db",
                    mime="application/octet-stream"
                )
        
        # 2. RESTORE DB
        with col_db2:
            st.markdown("**2. Restore Database**")
            st.warning("Uploading a `.db` file will instantly overwrite all current data.")
            uploaded_db = st.file_uploader("Upload a backup .db file", type=['db'])
            if uploaded_db is not None:
                if st.button("🚨 Confirm Restore Database"):
                    conn.close() # Close connection before overwriting file
                    with open("ftc_judging.db", "wb") as f:
                        f.write(uploaded_db.getvalue())
                    st.session_state.update({'logged_in': False, 'username': ''}) # Force logout to re-initialize
                    st.rerun()

        # 3. WIPE DB
        st.markdown("**3. Danger Zone: Factory Reset**")
        confirm_wipe = st.checkbox("I understand this will permanently delete ALL users (including this admin account), teams, scores, and logs.")
        if confirm_wipe:
            if st.button("🧨 Wipe Database"):
                conn.close()
                if os.path.exists("ftc_judging.db"):
                    os.remove("ftc_judging.db")
                st.session_state.update({'logged_in': False, 'username': ''})
                st.rerun()

        st.markdown("---")

        # --- AUDIT LOGS ---
        st.subheader("📜 System Audit Logs")
        try:
            logs_df = pd.read_sql_query("SELECT * FROM audit_logs ORDER BY timestamp DESC", conn)
            st.dataframe(logs_df, use_container_width=True, hide_index=True, height=200)
        except pd.errors.DatabaseError:
            st.info("No logs available.")

# Close connection at the very end of the script
try:
    conn.close()
except:
    pass