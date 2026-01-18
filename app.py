import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime

# --- CONFIGURATION ---
SHEET_NAME = "Khanna Family App DB"

# Family Roles
FAMILY_MEMBERS = {
    "Prateek": {"role": "admin"},
    "Dipti":   {"role": "admin"},
    "Raghav":  {"role": "member"},
    "Rhea":    {"role": "member"}
}

# --- GOOGLE SHEETS CONNECTION ---
def get_connection():
    scope = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
    try:
        creds_dict = dict(st.secrets["gcp_service_account"])
        creds = Credentials.from_service_account_info(creds_dict, scopes=scope)
    except:
        creds = Credentials.from_service_account_file("credentials.json", scopes=scope)
    
    client = gspread.authorize(creds)
    return client.open(SHEET_NAME)

# --- DATA FUNCTIONS ---
def load_data():
    sh = get_connection()
    tasks = sh.worksheet("Tasks").get_all_records()
    rewards = sh.worksheet("Rewards").get_all_records()
    balances = sh.worksheet("Balances").get_all_records()
    history = sh.worksheet("History").get_all_records()
    
    balance_dict = {row['User']: row['Points'] for row in balances}
    return {"tasks": tasks, "rewards": rewards, "balances": balance_dict, "history": history}

def log_history(user, action, item, points_change):
    sh = get_connection()
    worksheet = sh.worksheet("History")
    date_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    worksheet.append_row([date_str, user, action, item, points_change])

def update_balance(user, new_amount):
    sh = get_connection()
    ws = sh.worksheet("Balances")
    cell = ws.find(user)
    ws.update_cell(cell.row, 2, new_amount)

# Helper to add rows to Sheets
def add_entry(sheet_name, data_list):
    sh = get_connection()
    ws = sh.worksheet(sheet_name)
    ws.append_row(data_list)

# Helper to update status (works for both Tasks and Rewards if ID is unique)
def update_status(sheet_name, item_id, new_status, status_col_index):
    sh = get_connection()
    ws = sh.worksheet(sheet_name)
    cell = ws.find(str(item_id), in_column=1) # Find by ID in Col 1
    ws.update_cell(cell.row, status_col_index, new_status)

# --- APP INTERFACE ---
def main():
    st.set_page_config(page_title="Khanna Family Tasks", page_icon="🏠")
    
    # CSS for Mobile Usability
    st.markdown("""
        <style>
        .stButton>button {width: 100%; border-radius: 12px; height: 3.5em;}
        div[data-testid="stMetricValue"] {font-size: 1.8rem;}
        </style>
        """, unsafe_allow_html=True)

    try:
        data = load_data()
    except Exception as e:
        st.error(f"Connection Error: {e}")
        st.stop()

    # Login
    st.sidebar.title("👤 Login")
    user = st.sidebar.selectbox("User", list(FAMILY_MEMBERS.keys()))
    role = FAMILY_MEMBERS[user]["role"]
    
    st.title(f"👋 Hi, {user}!")
    
    # --- DASHBOARD (Family Standings) ---
    st.write("### 🏆 Family Leaderboard")
    cols = st.columns(len(FAMILY_MEMBERS))
    for idx, (member_name, details) in enumerate(FAMILY_MEMBERS.items()):
        score = float(data['balances'].get(member_name, 0))
        label = f"⭐ {member_name}" if member_name == user else member_name
        cols[idx].metric(label, f"{score:g}")

    st.divider()

    tab1, tab2, tab3 = st.tabs(["📝 Tasks", "🎁 Rewards", "⚙️ Admin"])

    # --- TAB 1: TASKS ---
    with tab1:
        st.subheader("To-Do List")
        active_tasks = [t for t in data['tasks'] if t['Status'] == "Active" and (t['Assignee'] == "Any" or t['Assignee'] == user)]
        
        for task in active_tasks:
            with st.container(border=True):
                c1, c2 = st.columns([3, 1])
                c1.write(f"**{task['Title']}**")
                c1.caption(f"{float(task['Points']):g} pts • {task['Frequency']}")
                
                if c2.button("Done", key=f"done_{task['ID']}"):
                    current_pts = float(data['balances'].get(user, 0))
                    task_pts = float(task['Points'])
                    new_pts = current_pts + task_pts
                    
                    update_balance(user, new_pts)
                    log_history(user, "Completed Task", task['Title'], f"+{task_pts:g}")
                    
                    if task['Frequency'] == "One-time":
                        update_status("Tasks", task['ID'], "Completed", 6)
                    
                    st.toast(f"Good job! +{task_pts:g} Points")
                    st.rerun()

        st.divider()
        with st.expander("➕ Suggest New Task"):
            t_title = st.text_input("Task Name")
            t_pts = st.number_input("Points", min_value=1.0, value=5.0, step=0.25, format="%.2f")
            if st.button("Submit Task"):
                new_id = len(data['tasks']) + 101
                # ID, Title, Points, Assignee, Frequency, Status
                add_entry("Tasks", [new_id, t_title, t_pts, "Any", "One-time", "Pending Approval"])
                st.success("Task sent for approval!")

    # --- TAB 2: REWARDS ---
    with tab2:
        st.subheader("Rewards Catalog")
        active_rewards = [r for r in data['rewards'] if r['Status'] == "Approved"]
        
        for reward in active_rewards:
            with st.container(border=True):
                c1, c2 = st.columns([3, 1])
                c1.write(f"**{reward['Title']}**")
                c1.caption(f"Cost: {float(reward['Cost']):g} pts")
                
                user_balance = float(data['balances'].get(user, 0))
                cost = float(reward['Cost'])
                
                if c2.button("Redeem", key=f"redeem_{reward['ID']}", disabled=user_balance < cost):
                    new_pts = user_balance - cost
                    update_balance(user, new_pts)
                    log_history(user, "Redeemed Reward", reward['Title'], f"-{cost:g}")
                    st.balloons()
                    st.toast("Reward Redeemed!")
                    st.rerun()
        
        # --- NEW FEATURE: Suggest Rewards ---
        st.divider()
        with st.expander("➕ Suggest New Reward"):
            r_title = st.text_input("Reward Name")
            r_cost = st.number_input("Cost", min_value=1.0, value=50.0, step=0.25, format="%.2f")
            if st.button("Submit Reward Request"):
                new_id = len(data['rewards']) + 201
                # ID, Title, Cost, Status
                add_entry("Rewards", [new_id, r_title, r_cost, "Pending Approval"])
                st.success("Reward sent for approval!")

    # --- TAB 3: ADMIN ---
    with tab3:
        if role == "admin":
            st.write("### 🛡️ Admin Dashboard")
            
            # 1. Pending Tasks
            pending_tasks = [t for t in data['tasks'] if t['Status'] == "Pending Approval"]
            if pending_tasks:
                st.write(f"**Tasks Pending ({len(pending_tasks)})**")
                for t in pending_tasks:
                    with st.container(border=True):
                        st.write(f"Task: {t['Title']} ({float(t['Points']):g} pts)")
                        c1, c2 = st.columns(2)
                        if c1.button("Approve", key=f"app_t_{t['ID']}"):
                            update_status("Tasks", t['ID'], "Active", 6)
                            st.rerun()
                        if c2.button("Reject", key=f"rej_t_{t['ID']}"):
                            update_status("Tasks", t['ID'], "Rejected", 6)
                            st.rerun()
            
            # 2. Pending Rewards (NEW FEATURE)
            pending_rewards = [r for r in data['rewards'] if r['Status'] == "Pending Approval"]
            if pending_rewards:
                st.divider()
                st.write(f"**Rewards Pending ({len(pending_rewards)})**")
                for r in pending_rewards:
                    with st.container(border=True):
                        st.write(f"Reward: {r['Title']} ({float(r['Cost']):g} pts)")
                        c1, c2 = st.columns(2)
                        if c1.button("Approve", key=f"app_r_{r['ID']}"):
                            update_status("Rewards", r['ID'], "Approved", 4)
                            st.rerun()
                        if c2.button("Reject", key=f"rej_r_{r['ID']}"):
                            update_status("Rewards", r['ID'], "Rejected", 4)
                            st.rerun()

            if not pending_tasks and not pending_rewards:
                st.info("All caught up! No pending approvals.")

            st.divider()
            st.write("### 📜 Activity Log")
            df = pd.DataFrame(data['history'])
            if not df.empty:
                st.dataframe(df.tail(15).iloc[::-1], use_container_width=True, hide_index=True)
        else:
            st.info("Ask Mom or Dad to see this tab!")

if __name__ == "__main__":
    main()
