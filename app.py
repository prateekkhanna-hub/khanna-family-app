import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime

# --- CONFIGURATION ---
SHEET_NAME = "Khanna Family App DB"

# Family Structure
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
        # Load from Streamlit Secrets (Cloud)
        creds_dict = dict(st.secrets["gcp_service_account"])
        creds = Credentials.from_service_account_info(creds_dict, scopes=scope)
    except:
        # Fallback for local testing (credentials.json)
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
    
    # Map users to their points
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
    # Update Column 2 (Points)
    ws.update_cell(cell.row, 2, new_amount)

def add_task(task_data):
    sh = get_connection()
    ws = sh.worksheet("Tasks")
    ws.append_row([
        task_data['id'], task_data['title'], task_data['points'], 
        task_data['assignee'], task_data['frequency'], task_data['status']
    ])

def update_task_status(task_id, new_status):
    sh = get_connection()
    ws = sh.worksheet("Tasks")
    cell = ws.find(str(task_id), in_column=1)
    # Status is Column 6
    ws.update_cell(cell.row, 6, new_status)

# --- APP INTERFACE ---
def main():
    st.set_page_config(page_title="Khanna Family Tasks", page_icon="🏠")
    
    # CSS to make buttons easier to tap on mobile
    st.markdown("""
        <style>
        .stButton>button {width: 100%; border-radius: 12px; height: 3.5em;}
        </style>
        """, unsafe_allow_html=True)

    try:
        data = load_data()
    except Exception as e:
        st.error(f"Connection Error: {e}")
        st.stop()

    # Login Sidebar
    st.sidebar.title("👤 Login")
    user = st.sidebar.selectbox("User", list(FAMILY_MEMBERS.keys()))
    role = FAMILY_MEMBERS[user]["role"]
    
    st.title(f"👋 Hi, {user}!")
    
    # Points Dashboard
    if role == "member":
        # Format as float to show decimals (e.g. 10.25)
        st.metric(label="Your Points", value=f"{data['balances'].get(user, 0):.2f}")
    else:
        st.write("### 🏆 Standings")
        cols = st.columns(len(FAMILY_MEMBERS))
        for idx, member in enumerate(FAMILY_MEMBERS):
            if FAMILY_MEMBERS[member]['role'] == "member":
                # Show decimals in standings
                cols[idx].metric(member, f"{data['balances'].get(member, 0):.2f}")

    tab1, tab2, tab3 = st.tabs(["📝 Tasks", "🎁 Rewards", "⚙️ Admin"])

    # --- TAB 1: TASKS ---
    with tab1:
        st.subheader("To-Do List")
        active_tasks = [t for t in data['tasks'] if t['Status'] == "Active" and (t['Assignee'] == "Any" or t['Assignee'] == user)]
        
        if not active_tasks:
            st.info("No active tasks!")
        
        for task in active_tasks:
            with st.container(border=True):
                c1, c2 = st.columns([3, 1])
                c1.write(f"**{task['Title']}**")
                # Show points with decimals if needed
                c1.caption(f"{float(task['Points']):g} pts • {task['Frequency']}")
                
                if c2.button("Done", key=f"done_{task['ID']}"):
                    current_pts = float(data['balances'].get(user, 0))
                    task_pts = float(task['Points'])
                    new_pts = current_pts + task_pts
                    
                    update_balance(user, new_pts)
                    log_history(user, "Completed Task", task['Title'], f"+{task_pts:g}")
                    
                    if task['Frequency'] == "One-time":
                        update_task_status(task['ID'], "Completed")
                    
                    st.toast(f"+{task_pts:g} Points Added!")
                    st.rerun()

        st.divider()
        with st.expander("➕ Suggest New Task"):
            new_title = st.text_input("Task Name")
            
            # --- UPDATED: Min 1.0, Step 0.25 ---
            # using 1.0 ensures Python treats it as a float (decimal)
            new_pts = st.number_input("Points", min_value=1.0, value=5.0, step=0.25, format="%.2f")
            
            if st.button("Submit Task"):
                new_id = len(data['tasks']) + 100
                add_task({
                    "id": new_id, "title": new_title, "points": new_pts,
                    "assignee": "Any", "frequency": "One-time", "status": "Pending Approval"
                })
                st.success(f"Submitted task for {new_pts} points!")

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

    # --- TAB 3: ADMIN ---
    with tab3:
        if role == "admin":
            st.write("### 🛡️ Admin Dashboard")
            
            # Pending Tasks
            pending = [t for t in data['tasks'] if t['Status'] == "Pending Approval"]
            if pending:
                st.write(f"**{len(pending)} Tasks Pending**")
                for t in pending:
                    with st.container(border=True):
                        st.write(f"{t['Title']} ({float(t['Points']):g} pts)")
                        c1, c2 = st.columns(2)
                        if c1.button("Approve", key=f"app_{t['ID']}"):
                            update_task_status(t['ID'], "Active")
                            st.rerun()
                        if c2.button("Reject", key=f"rej_{t['ID']}"):
                            update_task_status(t['ID'], "Rejected")
                            st.rerun()
            else:
                st.info("No pending approvals.")
            
            st.divider()
            st.write("### 📜 Recent History")
            df = pd.DataFrame(data['history'])
            if not df.empty:
                st.dataframe(df.tail(10), use_container_width=True, hide_index=True)

if __name__ == "__main__":
    main()
