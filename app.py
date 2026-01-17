import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime

# --- CONFIGURATION ---
SHEET_NAME = "Khanna Family App DB"

# Family Structure (Static Config)
FAMILY_MEMBERS = {
    "Prateek": {"role": "admin"},
    "Dipti":   {"role": "admin"},
    "Raghav":  {"role": "member"},
    "Rhea":    {"role": "member"}
}

# --- GOOGLE SHEETS CONNECTION ---
def get_connection():
    scope = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
    
    # Load credentials from Streamlit Secrets
    try:
        creds_dict = dict(st.secrets["gcp_service_account"])
        creds = Credentials.from_service_account_info(creds_dict, scopes=scope)
    except:
        st.error("Secrets not found! Please add them in Streamlit Settings.")
        st.stop()
        
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
    ws.update_cell(cell.row, 6, new_status)

# --- APP INTERFACE ---
def main():
    st.set_page_config(page_title="Khanna Family Tasks", page_icon="🏠")
    
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

    st.sidebar.title("👤 Login")
    user = st.sidebar.selectbox("User", list(FAMILY_MEMBERS.keys()))
    role = FAMILY_MEMBERS[user]["role"]
    
    st.title(f"👋 Hi, {user}!")
    
    if role == "member":
        st.metric(label="Your Points", value=data['balances'].get(user, 0))
    else:
        st.write("### 🏆 Standings")
        cols = st.columns(len(FAMILY_MEMBERS))
        for idx, member in enumerate(FAMILY_MEMBERS):
            if FAMILY_MEMBERS[member]['role'] == "member":
                cols[idx].metric(member, data['balances'].get(member, 0))

    tab1, tab2, tab3 = st.tabs(["📝 Tasks", "🎁 Rewards", "⚙️ Admin"])

    with tab1:
        st.subheader("To-Do List")
        active_tasks = [t for t in data['tasks'] if t['Status'] == "Active" and (t['Assignee'] == "Any" or t['Assignee'] == user)]
        
        if not active_tasks:
            st.info("No active tasks!")
        
        for task in active_tasks:
            with st.container(border=True):
                c1, c2 = st.columns([3, 1])
                c1.write(f"**{task['Title']}**")
                c1.caption(f"{task['Points']} pts • {task['Frequency']}")
                
                if c2.button("Done", key=f"done_{task['ID']}"):
                    current_pts = data['balances'].get(user, 0)
                    new_pts = current_pts + task['Points']
                    update_balance(user, new_pts)
                    log_history(user, "Completed Task", task['Title'], f"+{task['Points']}")
                    if task['Frequency'] == "One-time":
                        update_task_status(task['ID'], "Completed")
                    st.toast("Points Added!")
                    st.rerun()

        st.divider()
        with st.expander("➕ Suggest New Task"):
            new_title = st.text_input("Task Name")
            new_pts = st.number_input("Points", 5, 500, step=5)
            if st.button("Submit Task"):
                new_id = len(data['tasks']) + 100
                add_task({
                    "id": new_id, "title": new_title, "points": new_pts,
                    "assignee": "Any", "frequency": "One-time", "status": "Pending Approval"
                })
                st.success("Submitted for approval!")
    # --- TAB 2: REWARDS ---
    with tab2:
        st.subheader("Rewards Catalog")
        active_rewards = [r for r in data['rewards'] if r['Status'] == "Approved"]
        
        if not active_rewards:
            st.info("No rewards available yet.")
            
        for reward in active_rewards:
            with st.container(border=True):
                c1, c2 = st.columns([3, 1])
                c1.write(f"**{reward['Title']}**")
                c1.caption(f"Cost: {reward['Cost']} pts")
                
                # Check if user can afford it
                user_balance = data['balances'].get(user, 0)
                can_afford = user_balance >= reward['Cost']
                
                if c2.button("Redeem", key=f"red_{reward['ID']}", disabled=not can_afford):
                    # Deduct points
                    new_balance = user_balance - reward['Cost']
                    update_balance(user, new_balance)
                    
                    # Log it
                    log_history(user, "Redeemed Reward", reward['Title'], f"-{reward['Cost']}")
                    
                    st.balloons()
                    st.success("Redeemed! Enjoy.")
                    st.rerun()

        st.divider()
        with st.expander("➕ Wishlist (Suggest Reward)"):
             wish_item = st.text_input("I want...")
             wish_cost = st.number_input("Fair Cost?", min_value=10, step=10)
             if st.button("Add to Wishlist"):
                 # Use a simple way to generate a new ID (count existing + 200)
                 new_id = len(data['rewards']) + 200 
                 
                 # Connect to sheet and add row
                 sh = get_connection()
                 ws = sh.worksheet("Rewards")
                 ws.append_row([new_id, wish_item, wish_cost, "Pending Approval"])
                 
                 st.success("Added to wishlist for approval!")
                 
    with tab3:
        if role == "admin":
            st.write("### 🛡️ Admin Dashboard")
            pending = [t for t in data['tasks'] if t['Status'] == "Pending Approval"]
            if pending:
                st.write(f"**{len(pending)} Tasks Pending**")
                for t in pending:
                    with st.container(border=True):
                        st.write(f"{t['Title']} ({t['Points']} pts)")
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
