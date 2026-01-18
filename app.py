import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime, timedelta
import time
import extra_streamlit_components as stx

# --- CONFIGURATION ---
SHEET_NAME = "Khanna Family App DB"

# --- GOOGLE SHEETS CONNECTION ---
@st.cache_resource
def get_connection():
    scope = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
    try:
        creds_dict = dict(st.secrets["gcp_service_account"])
        creds = Credentials.from_service_account_info(creds_dict, scopes=scope)
    except:
        creds = Credentials.from_service_account_file("credentials.json", scopes=scope)
    
    return gspread.authorize(creds).open(SHEET_NAME)

# --- DATA FUNCTIONS ---
def load_data():
    sh = get_connection()
    ranges = ['Tasks!A:Z', 'Rewards!A:Z', 'History!A:Z', 'Users!A:Z']
    results = sh.values_batch_get(ranges)
    
    def get_df(index):
        rows = results['valueRanges'][index].get('values', [])
        if not rows: return []
        headers = rows[0]
        return [dict(zip(headers, row)) for row in rows[1:]]

    tasks = get_df(0)
    rewards = get_df(1)
    history = get_df(2)
    users_list = get_df(3)
    
    users_dict = {}
    for row in users_list:
        pts = row.get('Points', 0)
        if pts == "": pts = 0
        users_dict[row['Name']] = {
            'role': row['Role'], 
            'pin': str(row['Pin']),
            'points': float(pts)
        }
    
    return {"tasks": tasks, "rewards": rewards, "history": history, "users": users_dict}

def log_history(user, action, item, points_change):
    sh = get_connection()
    worksheet = sh.worksheet("History")
    date_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    worksheet.append_row([date_str, user, action, item, points_change])

def update_points(user, new_amount):
    sh = get_connection()
    ws = sh.worksheet("Users")
    cell = ws.find(user, in_column=1)
    ws.update_cell(cell.row, 4, new_amount)

def add_entry(sheet_name, data_list):
    sh = get_connection()
    ws = sh.worksheet(sheet_name)
    ws.append_row(data_list)

def update_status(sheet_name, item_id, new_status, status_col_index):
    sh = get_connection()
    ws = sh.worksheet(sheet_name)
    cell = ws.find(str(item_id), in_column=1)
    ws.update_cell(cell.row, status_col_index, new_status)

# --- LOGIN MANAGER ---
def get_login_manager():
    return stx.CookieManager()

# --- MAIN APP ---
def main():
    st.set_page_config(page_title="Khanna Family Tasks", page_icon="🏠")
    st.markdown("""<style>.stButton>button {width: 100%; border-radius: 12px; height: 3.5em;} div[data-testid="stMetricValue"] {font-size: 1.8rem;}</style>""", unsafe_allow_html=True)

    try:
        data = load_data()
    except Exception as e:
        st.warning("Syncing...")
        time.sleep(1)
        st.rerun()

    # --- COOKIE LOGIC ---
    cookie_manager = get_login_manager()
    time.sleep(0.1)
    
    cookie_user = cookie_manager.get("active_user")

    # If NO cookie, show Login Screen
    if not cookie_user or cookie_user not in data['users']:
        st.title("🔒 Login")
        valid_users = list(data['users'].keys())
        if not valid_users:
            st.error("No users found in Database!")
            return

        user_select = st.selectbox("Who are you?", valid_users)
        pin_input = st.text_input("Enter PIN", type="password")
        
        if st.button("Login"):
            correct_pin = str(data['users'][user_select]['pin'])
            if pin_input == correct_pin:
                # FIX: Use datetime object instead of timestamp float
                expire_date = datetime.now() + timedelta(days=30)
                cookie_manager.set("active_user", user_select, expires_at=expire_date)
                st.success("Logged in!")
                time.sleep(0.5)
                st.rerun()
            else:
                st.error("Wrong PIN!")
        return

    # If cookie exists, load user
    user = cookie_user
    role = data['users'][user]['role']

    # Sidebar Logout
    st.sidebar.divider()
    st.sidebar.write(f"Logged in as: **{user}**")
    if st.sidebar.button("Logout"):
        cookie_manager.delete("active_user")
        st.rerun()
    
    st.title(f"👋 Hi, {user}!")
    
    # --- DASHBOARD ---
    st.write("### 🏆 Family Leaderboard")
    family_members = sorted(list(data['users'].keys()))
    cols = st.columns(len(family_members))
    for idx, member_name in enumerate(family_members):
        score = data['users'][member_name]['points']
        label = f"⭐ {member_name}" if member_name == user else member_name
        cols[idx].metric(label, f"{score:g}")

    st.divider()
    tab1, tab2, tab3 = st.tabs(["📝 Tasks", "🎁 Rewards", "⚙️ Admin"])

    with tab1:
        st.subheader("To-Do List")
        active_tasks = [t for t in data['tasks'] if t['Status'] == "Active" and (t['Assignee'] == "Any" or t['Assignee'] == user)]
        for task in active_tasks:
            with st.container(border=True):
                c1, c2 = st.columns([3, 1])
                c1.write(f"**{task['Title']}**")
                c1.caption(f"{float(task['Points']):g} pts • {task['Frequency']}")
                if c2.button("Done", key=f"done_{task['ID']}"):
                    current_pts = data['users'][user]['points']
                    task_pts = float(task['Points'])
                    new_pts = current_pts + task_pts
                    update_points(user, new_pts)
                    log_history(user, "Completed Task", task['Title'], f"+{task_pts:g}")
                    if task['Frequency'] == "One-time":
                        update_status("Tasks", task['ID'], "Completed", 6)
                    st.toast(f"Good job! +{task_pts:g} Points")
                    st.rerun()

        st.divider()
        with st.expander("➕ Suggest New Task"):
            with st.form("new_task_form"):
                t_title = st.text_input("Task Name")
                t_pts = st.number_input("Points", min_value=1.0, value=5.0, step=0.25, format="%.2f")
                if st.form_submit_button("Submit Task"):
                    new_id = len(data['tasks']) + 101
                    add_entry("Tasks", [new_id, t_title, t_pts, "Any", "One-time", "Pending Approval"])
                    st.success("Task sent for approval!")

    with tab2:
        st.subheader("Rewards Catalog")
        active_rewards = [r for r in data['rewards'] if r['Status'] == "Approved"]
        for reward in active_rewards:
            with st.container(border=True):
                c1, c2 = st.columns([3, 1])
                c1.write(f"**{reward['Title']}**")
                c1.caption(f"Cost: {float(reward['Cost']):g} pts")
                user_balance = data['users'][user]['points']
                cost = float(reward['Cost'])
                if c2.button("Redeem", key=f"redeem_{reward['ID']}", disabled=user_balance < cost):
                    new_pts = user_balance - cost
                    update_points(user, new_pts)
                    log_history(user, "Redeemed Reward", reward['Title'], f"-{cost:g}")
                    st.balloons()
                    st.toast("Reward Redeemed!")
                    st.rerun()
        st.divider()
        with st.expander("➕ Suggest New Reward"):
            with st.form("new_reward_form"):
                r_title = st.text_input("Reward Name")
                r_cost = st.number_input("Cost", min_value=1.0, value=50.0, step=0.25, format="%.2f")
                if st.form_submit_button("Submit Reward Request"):
                    new_id = len(data['rewards']) + 201
                    add_entry("Rewards", [new_id, r_title, r_cost, "Pending Approval"])
                    st.success(f"Reward '{r_title}' sent for approval!")

    with tab3:
        if role == "admin":
            st.write("### 🛡️ Admin Dashboard")
            p_tasks = [t for t in data['tasks'] if t['Status'] == "Pending Approval"]
            p_rewards = [r for r in data['rewards'] if r['Status'] == "Pending Approval"]
            if p_tasks:
                st.write(f"**Tasks Pending ({len(p_tasks)})**")
                for t in p_tasks:
                    with st.container(border=True):
                        st.write(f"Task: {t['Title']} ({float(t['Points']):g} pts)")
                        c1, c2 = st.columns(2)
                        if c1.button("Approve", key=f"app_t_{t['ID']}"):
                            update_status("Tasks", t['ID'], "Active", 6)
                            st.rerun()
                        if c2.button("Reject", key=f"rej_t_{t['ID']}"):
                            update_status("Tasks", t['ID'], "Rejected", 6)
                            st.rerun()
            if p_rewards:
                st.divider()
                st.write(f"**Rewards Pending ({len(p_rewards)})**")
                for r in p_rewards:
                    with st.container(border=True):
                        st.write(f"Reward: {r['Title']} ({float(r['Cost']):g} pts)")
                        c1, c2 = st.columns(2)
                        if c1.button("Approve", key=f"app_r_{r['ID']}"):
                            update_status("Rewards", r['ID'], "Approved", 4)
                            st.rerun()
                        if c2.button("Reject", key=f"rej_r_{r['ID']}"):
                            update_status("Rewards", r['ID'], "Rejected", 4)
                            st.rerun()
            if not p_tasks and not p_rewards:
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
