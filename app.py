import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime, timedelta
import time
import random
import extra_streamlit_components as stx

# --- CONFIGURATION ---
SHEET_NAME = "Khanna Family App DB"
GLOBAL_GOAL_TARGET_DEFAULT = 2000 

# --- GOOGLE SHEETS CONNECTION ---
@st.cache_resource
def get_connection():
    scope = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
    try:
        creds_dict = dict(st.secrets["gcp_service_account"])
        creds = Credentials.from_service_account_info(creds_dict, scopes=scope)
    except:
        # Local fallback
        creds = Credentials.from_service_account_file("credentials.json", scopes=scope)
    
    return gspread.authorize(creds).open(SHEET_NAME)

# --- DATA FUNCTIONS ---
def load_data():
    sh = get_connection()
    # Fetch all necessary sheets including the new 'Settings' tab
    ranges = ['Tasks!A:Z', 'Rewards!A:Z', 'History!A:Z', 'Users!A:Z', 'Settings!A:Z']
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
    settings_list = get_df(4)
    
    # Process Users Dictionary with new Gamification columns
    users_dict = {}
    for row in users_list:
        # Safely convert strings to numbers, defaulting to 0 if empty
        pts = float(row.get('Points', 0)) if row.get('Points') else 0.0
        xp = float(row.get('XP', 0)) if row.get('XP') else 0.0
        streak = int(row.get('Streak', 0)) if row.get('Streak') else 0
        
        users_dict[row['Name']] = {
            'role': row['Role'], 
            'pin': str(row['Pin']),
            'points': pts,
            'xp': xp,
            'streak': streak,
            'last_active': row.get('Last_Active', ""),
            'badges': row.get('Badges', "")
        }

    # Process Settings for Global Goal
    settings_dict = {}
    for row in settings_list:
        if 'Setting' in row and 'Value' in row:
            try:
                settings_dict[row['Setting']] = float(row['Value'])
            except:
                settings_dict[row['Setting']] = row['Value']
            
    return {"tasks": tasks, "rewards": rewards, "history": history, "users": users_dict, "settings": settings_dict}

# --- GAMIFICATION LOGIC ---

def calculate_level(xp):
    # Level = Square root of XP divided by a constant factor
    # Example: 100 XP = Lvl 5.
    if xp <= 0: return 1, "Rookie 🌱"
    
    level = int((xp ** 0.5) / 2) + 1
    
    titles = {
        1: "Rookie 🌱", 2: "Scout 🔭", 3: "Adventurer 🎒", 
        4: "Warrior ⚔️", 5: "Knight 🛡️", 6: "Ninja 🥷", 
        7: "Master 🧘", 8: "Champion 🏆", 9: "Legend 👑", 10: "Mythic 🐉"
    }
    # Fallback for high levels
    title = titles.get(level, "Cosmic Being 🌌")
    return level, title

def update_user_stats(user, points_change, xp_change):
    sh = get_connection()
    ws = sh.worksheet("Users")
    cell = ws.find(user, in_column=1)
    
    # Get current row data to ensure we don't overwrite with stale data
    # Columns: A=Name, B=Role, C=Pin, D=Points, E=Streak, F=Last_Active, G=Badges, H=XP
    current_values = ws.row_values(cell.row)
    
    # Parse existing values safely
    try:
        old_points = float(current_values[3])
    except: old_points = 0.0
    
    try:
        old_streak = int(current_values[4])
    except: old_streak = 0
    
    last_active_str = current_values[5] if len(current_values) > 5 else ""
    
    try:
        old_xp = float(current_values[7])
    except: old_xp = 0.0

    # Calculate New Values
    new_points = old_points + points_change
    new_xp = old_xp + xp_change
    
    # Streak Logic (Only update if gaining positive XP/Points)
    new_streak = old_streak
    today_str = datetime.now().strftime("%Y-%m-%d")
    
    if xp_change > 0:
        if last_active_str == today_str:
            new_streak = old_streak # Already active today
        elif last_active_str == (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d"):
            new_streak = old_streak + 1 # Consecutive day
        else:
            new_streak = 1 # Streak broken or new
        
        # Update Last Active Date only on activity
        ws.update_cell(cell.row, 6, today_str)

    # Batch update Points (Col 4), Streak (Col 5), XP (Col 8)
    ws.update_cell(cell.row, 4, new_points)
    ws.update_cell(cell.row, 5, new_streak)
    ws.update_cell(cell.row, 8, new_xp)
    
    # Update Global Goal if points gained
    if points_change > 0:
        try:
            ws_set = sh.worksheet("Settings")
            g_cell = ws_set.find("Family_Goal_Current", in_column=1)
            # Fetch current explicitly to be safe
            cur_global = float(ws_set.cell(g_cell.row, 2).value)
            ws_set.update_cell(g_cell.row, 2, cur_global + points_change)
        except:
            pass # Fail silently if settings sheet is missing row

def add_entry(sheet_name, data_list):
    sh = get_connection()
    ws = sh.worksheet(sheet_name)
    ws.append_row(data_list)

def update_status(sheet_name, item_id, new_status, status_col_index):
    sh = get_connection()
    ws = sh.worksheet(sheet_name)
    cell = ws.find(str(item_id), in_column=1)
    ws.update_cell(cell.row, status_col_index, new_status)

def delete_entry(sheet_name, item_id):
    sh = get_connection()
    ws = sh.worksheet(sheet_name)
    cell = ws.find(str(item_id), in_column=1)
    ws.delete_rows(cell.row)

def log_history(user, action, item, points_change):
    sh = get_connection()
    ws = sh.worksheet("History")
    date_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    ws.append_row([date_str, user, action, item, points_change])

# --- LOGIN MANAGER ---
def get_login_manager():
    return stx.CookieManager()

# --- MAIN APP ---
def main():
    st.set_page_config(page_title="Khanna Family Quest", page_icon="🛡️", layout="centered")
    
    # -------------------------------------------------------------------------
    # CUSTOM CSS
    # -------------------------------------------------------------------------
    st.markdown("""
        <style>
        /* BUTTONS */
        div.stButton > button[kind="primary"] {
            background-color: #28a745;
            color: white;
            font-weight: bold;
            height: 3em;
            width: 100%;
            border-radius: 12px;
        }
        div.stButton > button[kind="secondary"] {
            height: 3em;
            width: 100%;
            border-radius: 12px;
        }

        /* CARDS */
        .stat-card {
            background-color: #262730;
            border: 1px solid #464b59;
            border-radius: 10px;
            padding: 15px;
            text-align: center;
            margin-bottom: 10px;
        }
        .active-card {
            border: 2px solid #ff4b4b;
            background-color: #362022;
        }
        .stat-value { font-size: 1.5rem; font-weight: bold; margin: 0; }
        .stat-label { font-size: 0.9rem; color: #ccc; margin: 0; }
        .crown { font-size: 1.2rem; }
        
        /* PROGRESS BAR CUSTOMIZATION */
        .stProgress > div > div > div > div {
            background-color: #00d4ff;
        }
        </style>
        """, unsafe_allow_html=True)

    # --- ERROR HANDLING LOAD ---
    try:
        data = load_data()
    except Exception as e:
        st.error(f"⚠️ Database Error: {e}")
        st.stop() # Stops execution so it doesn't loop infinitely

    # --- SESSION & COOKIE LOGIC (FIXED) ---
    cookie_manager = get_login_manager()
    
    # Initialize session state if missing
    if 'authenticated' not in st.session_state:
        st.session_state['authenticated'] = False
        st.session_state['user'] = None

    # Check cookie ONLY if not already authenticated in this session
    if not st.session_state['authenticated']:
        time.sleep(0.1)
        cookie_user = cookie_manager.get("active_user")
        if cookie_user and cookie_user in data['users']:
            st.session_state['authenticated'] = True
            st.session_state['user'] = cookie_user
            st.rerun()

    # --- LOGIN SCREEN ---
    if not st.session_state['authenticated']:
        st.title("🛡️ Family Quest Login")
        valid_users = list(data['users'].keys())
        
        if not valid_users:
            st.error("No users found in DB.")
            return

        user_select = st.selectbox("Select Your Hero", valid_users)
        pin_input = st.text_input("Secret Code", type="password")
        
        if st.button("Enter Realm", type="primary"):
            correct_pin = str(data['users'][user_select]['pin'])
            if pin_input == correct_pin:
                st.session_state['authenticated'] = True
                st.session_state['user'] = user_select
                
                # Set cookie for 30 days
                expires = datetime.now() + timedelta(days=30)
                cookie_manager.set("active_user", user_select, expires_at=expires)
                
                st.balloons()
                st.rerun()
            else:
                st.error("Wrong PIN!")
        return

    # --- MAIN DASHBOARD ---
    user = st.session_state['user']
    user_data = data['users'][user]
    role = user_data['role']
    
    # Calculate Gamification Stats
    level, title = calculate_level(user_data['xp'])
    
    # XP Progress to next level
    # Simple Formula: Next level requires (Level * 2)^2 XP
    # This is purely visual for the progress bar
    prev_threshold = ((level - 1) * 2) ** 2 if level > 1 else 0
    next_threshold = (level * 2) ** 2
    if next_threshold <= prev_threshold: next_threshold = prev_threshold + 10 # Safety
    
    xp_progress = (user_data['xp'] - prev_threshold) / (next_threshold - prev_threshold)
    xp_progress = max(0.0, min(1.0, xp_progress)) # Clamp between 0 and 1

    # 1. HEADER & LOGOUT
    c1, c2 = st.columns([3, 1])
    c1.title(f"{user}")
    c1.caption(f"**{title}** (Lvl {level})")
    
    if c2.button("Logout"):
        cookie_manager.delete("active_user")
        st.session_state['authenticated'] = False
        st.session_state['user'] = None
        st.rerun()
    
    # 2. STATUS BARS
    st.write(f"**XP Progress:** {int(user_data['xp'])} / {int(next_threshold)}")
    st.progress(xp_progress)
    
    k1, k2 = st.columns(2)
    k1.metric("💰 Gold (Points)", f"{user_data['points']:g}")
    k2.metric("🔥 Daily Streak", f"{user_data['streak']} Days")
    
    # 3. GLOBAL GOAL
    st.divider()
    g_current = data['settings'].get('Family_Goal_Current', 0)
    g_target = data['settings'].get('Family_Goal_Target', GLOBAL_GOAL_TARGET_DEFAULT)
    
    st.write(f"### 🌍 Family Goal: Water Park Trip!")
    st.progress(min(g_current / g_target, 1.0))
    st.caption(f"Total Family Points: {int(g_current)} / {int(g_target)}")

    st.divider()
    
    # --- TABS ---
    tab1, tab2, tab3, tab4 = st.tabs(["⚔️ Quests", "🎁 Loot", "🏆 Hall of Fame", "⚙️ Admin"])

    # --- TAB 1: QUESTS (TASKS) ---
    with tab1:
        st.subheader("Active Quests")
        
        my_tasks = []
        for t in data['tasks']:
            assignees = str(t['Assignee'])
            if t['Status'] == "Active":
                if "Any" in assignees or user in assignees:
                    my_tasks.append(t)
        
        if not my_tasks:
            st.info("No active quests! Go play outside. 🌞")

        for task in my_tasks:
            with st.container(border=True):
                c_text, c_btn = st.columns([3, 1])
                
                # Streak Multiplier Logic
                base_points = float(task['Points'])
                multiplier = 1.0
                if user_data['streak'] >= 7: multiplier = 1.5
                elif user_data['streak'] >= 3: multiplier = 1.2
                
                final_points = base_points * multiplier
                
                c_text.write(f"**{task['Title']}**")
                
                # Visual Flair for multiplier
                if multiplier > 1.0:
                    c_text.markdown(f"Points: ~~{base_points}~~ **{final_points:.1f}** (🔥 x{multiplier} Streak Bonus!)")
                else:
                    c_text.caption(f"Points: {base_points} • {task['Frequency']}")

                if c_btn.button("Complete", key=f"btn_{task['ID']}", type="primary"):
                    # Add Points AND XP
                    update_user_stats(user, final_points, final_points)
                    log_history(user, "Quest Complete", task['Title'], f"+{final_points:g}")
                    
                    if task['Frequency'] == "One-time":
                        update_status("Tasks", task['ID'], "Completed", 6)
                    
                    st.balloons()
                    st.toast(f"Quest Complete! +{final_points:g} Gold & XP")
                    time.sleep(1.5)
                    st.rerun()

    # --- TAB 2: LOOT (REWARDS) ---
    with tab2:
        st.subheader("Marketplace")
        
        # MYSTERY BOX
        with st.container(border=True):
            st.markdown("### ❓ Mystery Box (Cost: 15)")
            st.caption("Win between 5 and 50 points!")
            
            if st.button("Open Mystery Box", disabled=user_data['points'] < 15):
                cost = 15
                prize = random.choice([5, 10, 10, 15, 20, 25, 50])
                
                # Deduct cost, add prize (XP does NOT change)
                net_change = prize - cost
                update_user_stats(user, net_change, 0) 
                log_history(user, "Mystery Box", f"Won {prize}", f"{net_change}")
                
                if prize > 15:
                    st.balloons()
                    st.success(f"JACKPOT! You spent 15 and won {prize}!")
                else:
                    st.info(f"You spent 15 and got {prize}.")
                
                time.sleep(2)
                st.rerun()

        st.divider()
        
        # STANDARD REWARDS
        active_rewards = [r for r in data['rewards'] if r['Status'] == "Approved"]
        for reward in active_rewards:
            with st.container(border=True):
                c1, c2 = st.columns([3, 1])
                cost = float(reward['Cost'])
                
                c1.write(f"**{reward['Title']}**")
                c1.caption(f"Cost: {cost:g}")
                
                if c2.button("Buy", key=f"buy_{reward['ID']}", disabled=user_data['points'] < cost):
                    update_user_stats(user, -cost, 0) # Reduce points, XP stays same
                    log_history(user, "Reward Redeemed", reward['Title'], f"-{cost:g}")
                    st.snow()
                    st.toast("Item Redeemed!")
                    time.sleep(1)
                    st.rerun()
                    
        # Suggest Reward
        with st.expander("Request New Reward"):
            with st.form("new_reward"):
                rt = st.text_input("Reward Name")
                rc = st.number_input("Cost", min_value=1.0)
                if st.form_submit_button("Submit"):
                    nid = int(datetime.now().timestamp())
                    add_entry("Rewards", [nid, rt, rc, "Pending Approval"])
                    st.success("Sent for approval!")

    # --- TAB 3: LEADERBOARD ---
    with tab3:
        st.subheader("🏆 Hall of Fame")
        
        # Sort by XP (Lifetime Score)
        sorted_users = sorted(data['users'].items(), key=lambda x: x[1]['xp'], reverse=True)
        
        for name, stats in sorted_users:
            lvl, title = calculate_level(stats['xp'])
            is_me = (name == user)
            
            card_style = "stat-card active-card" if is_me else "stat-card"
            
            st.markdown(f"""
            <div class="{card_style}">
                <div style="display:flex; justify-content:space-between; align-items:center;">
                    <div style="text-align:left;">
                        <span style="font-size:1.2rem; font-weight:bold;">{name}</span><br>
                        <span style="color:#bbb;">{title} (Lvl {lvl})</span>
                    </div>
                    <div style="text-align:right;">
                        <span style="font-size:1.4rem; font-weight:bold;">{stats['points']:g} pts</span><br>
                        <span style="color:#ff4b4b;">🔥 {stats['streak']} day streak</span>
                    </div>
                </div>
            </div>
            """, unsafe_allow_html=True)

    # --- TAB 4: ADMIN ---
    with tab4:
        if role == "admin":
            st.write("### 🛡️ Admin Controls")
            
            # PENDING APPROVALS
            p_tasks = [t for t in data['tasks'] if t['Status'] == "Pending Approval"]
            p_rewards = [r for r in data['rewards'] if r['Status'] == "Pending Approval"]
            
            if p_tasks or p_rewards:
                st.write("#### ⏳ Pending Approvals")
                for t in p_tasks:
                    c1, c2, c3 = st.columns([2, 1, 1])
                    c1.write(f"Task: {t['Title']} ({t['Points']} pts)")
                    if c2.button("Approve", key=f"apt_{t['ID']}"):
                        update_status("Tasks", t['ID'], "Active", 6)
                        st.rerun()
                    if c3.button("Reject", key=f"rjt_{t['ID']}"):
                        update_status("Tasks", t['ID'], "Rejected", 6)
                        st.rerun()
                
                for r in p_rewards:
                    c1, c2, c3 = st.columns([2, 1, 1])
                    c1.write(f"Reward: {r['Title']} ({r['Cost']} pts)")
                    if c2.button("Approve", key=f"apr_{r['ID']}"):
                        update_status("Rewards", r['ID'], "Approved", 4)
                        st.rerun()
                    if c3.button("Reject", key=f"rjr_{r['ID']}"):
                        update_status("Rewards", r['ID'], "Rejected", 4)
                        st.rerun()
            else:
                st.info("No pending items.")
            
            # CREATE TASK
            st.divider()
            with st.expander("➕ Create New Task"):
                t_title = st.text_input("Task Title")
                t_pts = st.number_input("Points", min_value=1.0)
                t_assignee = st.text_input("Assignee (Name or 'Any')", value="Any")
                if st.button("Create Task"):
                    nid = int(datetime.now().timestamp())
                    add_entry("Tasks", [nid, t_title, t_pts, t_assignee, "One-time", "Active"])
                    st.success("Task Created!")
                    time.sleep(1)
                    st.rerun()
            
            # LOGS
            st.divider()
            st.write("#### 📜 Activity Log")
            df = pd.DataFrame(data['history'])
            if not df.empty:
                st.dataframe(df.tail(20).iloc[::-1], use_container_width=True, hide_index=True)

        else:
            st.warning("🔒 Admin Access Only")

if __name__ == "__main__":
    main()
