import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime

# --- CONFIGURATION ---
SHEET_NAME = "Khanna Family App DB"

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
    
    # Load all worksheets
    tasks = sh.worksheet("Tasks").get_all_records()
    rewards = sh.worksheet("Rewards").get_all_records()
    balances = sh.worksheet("Balances").get_all_records()
    history = sh.worksheet("History").get_all_records()
    users = sh.worksheet("Users").get_all_records() # NEW: Load Users from Sheet
    
    # Helper dicts
    balance_dict = {row['User']: row['Points'] for row in balances}
    user_dict = {row['Name']: {'role': row['Role'], 'pin': str(row['Pin'])} for row in users}
    
    return {
        "tasks": tasks, 
        "rewards": rewards, 
        "balances": balance_dict, 
        "history": history,
        "users": user_dict
    }

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

def add_entry(sheet_name, data_list):
    sh = get_connection()
    ws = sh.worksheet(sheet_name)
    ws.append_row(data_list)

def update_status(sheet_name, item_id, new_status, status_col_index):
    sh = get_connection()
    ws = sh.worksheet(sheet_name)
    cell = ws.find(str(item_id), in_column=1)
    ws.update_cell(cell.row, status_col_index, new_status)

# --- AUTHENTICATION LOGIC ---
def check_password(user_data):
    """Returns True if the user is logged in successfully"""
    if st.session_state.get('authenticated', False):
        return True
        
    st.sidebar.title("🔒 Login")
    
    # Get user names from the loaded sheet data
    valid_users = list(user_data.keys())
    user_select = st.sidebar.selectbox("Who are you?", valid_users)
    pin_input = st.sidebar.text_input("Enter PIN", type="password")
    
    if st.sidebar.button("Login"):
        # Check against Sheet Data
        correct_pin = str(user_data[user_select]['pin'])
        
        if pin_input == correct_pin:
            st.session_state['authenticated'] = True
            st.session_state['user'] = user_select
            st.session_state['role'] = user_data[user_select]['role']
            st.rerun()
        else:
            st.sidebar.error("Wrong PIN!")
            
    return False

def logout():
    st.session_state['authenticated'] = False
    st.session_state['user'] = None
    st.rerun()

# --- MAIN APP ---
def main():
    st.set_page_config(page_title="Khanna Family Tasks", page_icon="🏠")
    
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

    # 1. CHECK LOGIN (Pass the data from Sheet)
    if not check_password(data['users']):
        st.title("🏠 Khanna Family Tasks")
        st.info("Please log in from the sidebar.")
        return

    # 2. LOAD APP
    user = st.session_state['user']
    role = st.session_state['role']
    
    st.sidebar.divider()
    st.sidebar.write(f"Logged in as: **{user}**")
    if st.sidebar.button("Logout"):
        logout()
    
    st.title(f"👋 Hi, {user}!")
    
    # --- DASHBOARD ---
    st.write("### 🏆 Family Leaderboard")
    
    # Dynamic Columns based on Users in Sheet
    # Filter only family members who have a balance entry
    family_members = [u for u in data['users'].keys() if u in data['balances']]
    cols = st.columns(len(family_members))
    
    for idx, member_name in enumerate(family_members):
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
        
        st.divider()
        with st.expander("➕ Suggest New Reward"):
            r_title = st.text_input("Reward Name")
            r_cost = st.number_input("Cost", min_value=1.0, value=50.0, step=0.25, format="%.2f")
            if st.button("Submit Reward Request"):
                new_id = len(data['rewards']) + 201
                add_entry("Rewards", [new_id, r_title, r_cost, "Pending Approval"])
                st.success("Reward sent for approval!")

    # --- TAB 3: ADMIN ---
    with tab3:
        if role == "admin":
            st.write("### 🛡️ Admin Dashboard")
            
            # Pending Items
            pending_tasks = [t for t in data['tasks'] if t['Status'] == "Pending Approval"]
            pending_rewards = [r for r in data['rewards'] if r['Status'] == "Pending Approval"]
            
            if pending_tasks or pending_rewards:
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
            else:
                st.info("No pending approvals.")

            st.divider()
            st.write("### 📜 Activity Log")
            df = pd.DataFrame(data['history'])
            if not df.empty:
                st.dataframe(df.tail(15).iloc[::-1], use_container_width=True, hide_index=True)
        else:
            st.warning("🔒 You need Admin permissions to see this area.")

if __name__ == "__main__":
    main()
