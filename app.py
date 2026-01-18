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
GLOBAL_GOAL_TARGET = 1000  # Default if sheet is empty

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
    # Now fetching Settings as well
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
    
    # Process Users
    users_dict = {}
    for row in users_list:
        pts = float(row.get('Points', 0)) if row.get('Points') else 0
        xp = float(row.get('XP', 0)) if row.get('XP') else 0
        streak = int(row.get('Streak', 0)) if row.get('Streak') else 0
        
        users_dict[row['Name']] = {
            'role': row['Role'], 
            'pin': str(row['Pin']),
            'points': pts,
            'streak': streak,
            'last_active': row.get('Last_Active', ""),
            'badges': row.get('Badges', ""),
            'xp': xp,
            'row_id': row.get('Name') # Storing name to find row easily later if needed
        }

    # Process Global Settings
    settings_dict = {}
    for row in settings_list:
        if 'Setting' in row and 'Value' in row:
            settings_dict[row['Setting']] = float(row['Value'])
            
    return {"tasks": tasks, "rewards": rewards, "history": history, "users": users_dict, "settings": settings_dict}

# --- GAMIFICATION LOGIC ---

def calculate_level(xp):
    # Level = Square root of XP divided by a constant
    # Level 1 = 0 XP, Level 5 = 625 XP approx with constant 5
    if xp == 0: return 1, "Rookie"
    level = int((xp ** 0.5) / 2.5) + 1
    
    titles = {
        1: "Rookie 🌱", 2: "Novice 🔨", 3: "Apprentice 📘", 
        4: "Specialist ⚡", 5: "Expert 🔥", 6: "Master ⚔️", 
        7: "Grandmaster 🧙‍♂️", 8: "Legend 👑", 9: "Mythic 🐉", 10: "Godlike ⚡"
    }
    title = titles.get(level, "Cosmic Being 🌌")
    return level, title

def check_streak(user, last_active_str, current_streak):
    today = datetime.now().date()
    if not last_active_str:
        return 1, today  # First time active
        
    try:
        last_date = datetime.strptime(last_active_str, "%Y-%m-%d").date()
    except:
        return 1, today # Error parsing, reset

    delta = (today - last_date).days
    
    if delta == 0:
        return current_streak, today # Already active today
    elif delta == 1:
        return current_streak + 1, today # Streak continues!
    else:
        return 1, today # Streak broken, reset to 1

def update_user_stats(user, points_add, xp_add):
    sh = get_connection()
    ws = sh.worksheet("Users")
    cell = ws.find(user, in_column=1)
    
    # Get current data to calculate streak
    current_data = ws.row_values(cell.row)
    # Map columns: A=Name, B=Role, C=Pin, D=Points, E=Streak, F=Last_Active, G=Badges, H=XP
    
    old_points = float(current_data[3]) if len(current_data) > 3 else 0
    old_streak = int(current_data[4]) if len(current_data) > 4 and current_data[4] else 0
    last_date = current_data[5] if len(current_data) > 5 else ""
    old_xp = float(current_data[7]) if len(current_data) > 7 and current_data[7] else 0
    
    new_points = old_points + points_add
    new_xp = old_xp + xp_add
    
    # Calculate Streak
    if points_add > 0: # Only update streak on positive actions (completing tasks)
        new_streak, new_date_obj = check_streak(user, last_date, old_streak)
        new_date_str = new_date_obj.strftime("%Y-%m-%d")
    else:
        new_streak = old_streak
        new_date_str = last_date

    # Batch update for speed
    # Col D=4, E=5, F=6, H=8
    ws.update_cell(cell.row, 4, new_points)
    ws.update_cell(cell.row, 5, new_streak)
    ws.update_cell(cell.row, 6, new_date_str)
    ws.update_cell(cell.row, 8, new_xp)
    
    # Global Goal Update
    if points_add > 0:
        ws_set = sh.worksheet("Settings")
        try:
            g_cell = ws_set.find("Family_Goal_Current", in_column=1)
            cur_global = float(ws_set.cell(g_cell.row, 2).value)
            ws_set.update_cell(g_cell.row, 2, cur_global + points_add)
        except:
            pass # Handle case where setting doesn't exist yet

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
    
    # ---------------- CSS ----------------
    st.markdown("""
        <style>
        div.stButton > button[kind="primary"] {
            background-color: #28a745; color: white; border-radius: 12px; height: 3em; font-weight: bold;
        }
        div.stButton > button[kind="secondary"] { border-radius: 12px; height: 3em; }
        
        /* LEVEL PROGRESS BAR */
        .xp-bar-bg { width: 100%; background-color: #444; border-radius: 10px; height: 10px; margin-top:5px;}
        .xp-bar-fill { background-color: #00d4ff; height: 100%; border-radius: 10px; }
        
        /* CARDS */
        .stat-card {
            background-color: #262730; border: 1px solid #464b59; border-radius: 10px;
            padding: 10px; text-align: center; margin-bottom: 10px;
        }
        .stat-value { font-size: 1.5rem; font-weight: bold; margin:0; }
        .stat-label { font-size: 0.8rem; color: #aaa; margin:0; }
        .badge-container { font-size: 1.2rem; margin-top: 5px; }
        </style>
    """, unsafe_allow_html=True)

    try:
        data = load_data()
    except:
        st.warning("Syncing Database...")
        time.sleep(1)
        st.rerun()

    # --- AUTHENTICATION ---
    cookie_manager = get_login_manager()
    time.sleep(0.1)
    cookie_user = cookie_manager.get("active_user")

    is_authenticated = False
    if cookie_user and cookie_user in data['users']:
        is_authenticated = True
        user = cookie_user
    elif st.session_state.get('authenticated'):
        is_authenticated = True
        user = st.session_state.get('user')

    if not is_authenticated:
        st.title("🛡️ Family Quest Login")
        valid_users = list(data['users'].keys())
        if not valid_users: st.error("No users found."); return
        
        user_select = st.selectbox("Select Hero", valid_users)
        pin_input = st.text_input("Secret Code", type="password")
        
        if st.button("Enter Realm", type="primary"):
            correct_pin = str(data['users'][user_select]['pin'])
            if pin_input == correct_pin:
                st.session_state['authenticated'] = True
                st.session_state['user'] = user_select
                cookie_manager.set("active_user", user_select, expires_at=datetime.now() + timedelta(days=30))
                st.balloons()
                st.rerun()
            else:
                st.error("Incorrect Code!")
        return

    # --- LOGGED IN DASHBOARD ---
    
    # 1. CALCULATE USER STATS
    role = data['users'][user]['role']
    user_pts = data['users'][user]['points']
    user_xp = data['users'][user]['xp']
    user_streak = data['users'][user]['streak']
    level, title = calculate_level(user_xp)
    
    # XP Progress Math
    # Approx logic: next level XP is (level * 2.5)^2
    next_level_xp = ((level) * 2.5) ** 2
    prev_level_xp = ((level - 1) * 2.5) ** 2
    if level == 1: prev_level_xp = 0
    
    xp_needed = next_level_xp - prev_level_xp
    xp_current = user_xp - prev_level_xp
    if xp_needed <= 0: xp_needed = 1 # avoid div by 0
    progress_percent = min(max(xp_current / xp_needed, 0), 1)

    # 2. HEADER AREA
    c1, c2 = st.columns([3, 1])
    c1.title(f"{user}")
    c1.caption(f"**{title}** (Lvl {level})")
    if c2.button("Logout"):
        cookie_manager.delete("active_user")
        st.session_state['authenticated'] = False
        st.rerun()

    # 3. LEVEL & STREAK BAR
    st.write(f"XP: {int(user_xp)} / {int(next_level_xp)}")
    st.progress(progress_percent)
    
    cols = st.columns(3)
    cols[0].metric("💰 Gold (Points)", f"{user_pts:g}")
    cols[1].metric("🔥 Streak", f"{user_streak} Days")
    
    # 4. GLOBAL FAMILY GOAL
    st.divider()
    g_target = data['settings'].get('Family_Goal_Target', GLOBAL_GOAL_TARGET)
    g_current = data['settings'].get('Family_Goal_Current', 0)
    g_percent = min(g_current / g_target, 1.0)
    
    st.write(f"### 🌍 Family Goal: Water Park Trip!")
    st.progress(g_percent)
    st.caption(f"{int(g_current)} / {int(g_target)} points gathered by the family!")

    # --- TABS ---
    tab1, tab2, tab3, tab4 = st.tabs(["⚔️ Quests", "🎁 Loot", "🏆 Leaderboard", "⚙️ Admin"])

    # TAB 1: QUESTS (TASKS)
    with tab1:
        st.subheader("Available Quests")
        my_tasks = []
        for t in data['tasks']:
            assignees = str(t['Assignee']) 
            if t['Status'] == "Active":
                if "Any" in assignees or user in assignees:
                    my_tasks.append(t)
        
        if not my_tasks: st.info("No active quests. You are free... for now.")

        for task in my_tasks:
            with st.container(border=True):
                c_text, c_btn = st.columns([3, 1])
                c_text.write(f"**{task['Title']}**")
                
                # Streak Bonus Calculation
                base_pts = float(task['Points'])
                bonus_mult = 1.0
                if user_streak >= 3: bonus_mult = 1.2
                if user_streak >= 7: bonus_mult = 1.5
                final_pts = base_pts * bonus_mult
                
                bonus_text = f" (🔥 x{bonus_mult})" if bonus_mult > 1 else ""
                c_text.caption(f"{base_pts:g} pts{bonus_text} • {task['Frequency']}")
                
                if c_btn.button("Complete", key=f"btn_{task['ID']}", type="primary"):
                    # Update User (Points + XP)
                    # XP is usually same as points earned, but permanent
                    update_user_stats(user, final_pts, final_pts)
                    log_history(user, "Completed Quest", task['Title'], f"+{final_pts:g}")
                    
                    if task['Frequency'] == "One-time":
                        update_status("Tasks", task['ID'], "Completed", 6)
                    
                    st.balloons()
                    st.toast(f"Quest Complete! +{final_pts:g} Gold")
                    time.sleep(1.5)
                    st.rerun()

    # TAB 2: LOOT (REWARDS + MYSTERY BOX)
    with tab2:
        st.subheader("🛒 Market")
        
        # MYSTERY BOX
        with st.container(border=True):
            st.write("### ❓ Mystery Box (Cost: 15 pts)")
            st.write("Contains random points between 5 and 50!")
            if st.button("Open Mystery Box", disabled=user_pts < 15):
                cost = 15
                prize = random.choice([5, 10, 10, 20, 20, 50])
                
                # Deduct cost, add prize
                update_user_stats(user, prize - cost, 0) # Net change
                log_history(user, "Opened Mystery Box", f"Won {prize}", f"{prize - cost}")
                
                if prize > 15:
                    st.balloons()
                    st.success(f"JACKPOT! You spent 15 and won {prize} pts!")
                else:
                    st.info(f"You spent 15 and got {prize} pts.")
                time.sleep(2)
                st.rerun()

        st.divider()
        st.write("### Standard Rewards")
        active_rewards = [r for r in data['rewards'] if r['Status'] == "Approved"]
        for reward in active_rewards:
            with st.container(border=True):
                c1, c2 = st.columns([3, 1])
                c1.write(f"**{reward['Title']}**")
                c1.caption(f"Cost: {float(reward['Cost']):g} pts")
                
                if c2.button("Buy", key=f"redeem_{reward['ID']}", disabled=user_pts < float(reward['Cost'])):
                    cost = float(reward['Cost'])
                    update_user_stats(user, -cost, 0) # XP doesn't go down
                    log_history(user, "Redeemed Reward", reward['Title'], f"-{cost:g}")
                    st.snow()
                    st.toast("Reward Redeemed!")
                    time.sleep(1)
                    st.rerun()

    # TAB 3: LEADERBOARD
    with tab3:
        st.subheader("🏆 Hall of Fame")
        
        # Sort by XP (Total Lifetime Score) instead of current points
        sorted_users = sorted(data['users'].items(), key=lambda x: x[1]['xp'], reverse=True)
        
        for name, stats in sorted_users:
            u_lvl, u_title = calculate_level(stats['xp'])
            is_me = (name == user)
            bg_color = "#362022" if is_me else "#262730"
            border = "2px solid #ff4b4b" if is_me else "1px solid #464b59"
            
            st.markdown(f"""
            <div style="background-color: {bg_color}; border: {border}; border-radius: 10px; padding: 15px; margin-bottom: 10px; display: flex; align-items: center;">
                <div style="flex: 1;">
                    <span style="font-size: 1.2rem; font-weight: bold;">{name}</span> <br>
                    <span style="color: #ccc; font-size: 0.9rem;">{u_title} (Lvl {u_lvl})</span>
                </div>
                <div style="text-align: right;">
                    <span style="font-size: 1.5rem; font-weight: bold;">{stats['points']:g} pts</span> <br>
                    <span style="color: #ff4b4b;">🔥 {stats['streak']} day streak</span>
                </div>
            </div>
            """, unsafe_allow_html=True)

    # TAB 4: ADMIN
    with tab4:
        if role == "admin":
            st.write("### 🛡️ Admin Dashboard")
            
            # Form to add Task/Reward (simplified for brevity)
            with st.expander("➕ Add Task / Reward"):
                new_type = st.radio("Type", ["Task", "Reward"])
                n_title = st.text_input("Title")
                n_val = st.number_input("Value", min_value=1.0)
                if st.button("Create"):
                    nid = int(datetime.now().timestamp())
                    if new_type == "Task":
                        add_entry("Tasks", [nid, n_title, n_val, "Any", "One-time", "Active"])
                    else:
                        add_entry("Rewards", [nid, n_title, n_val, "Approved"])
                    st.success("Created!")
                    time.sleep(1)
                    st.rerun()
            
            st.divider()
            st.write("**Pending Items**")
            # Reuse logic for pending items from previous code, or keep clean
            p_tasks = [t for t in data['tasks'] if t['Status'] == "Pending Approval"]
            for t in p_tasks:
                c1, c2 = st.columns([3, 1])
                c1.write(f"{t['Title']} ({t['Assignee']})")
                if c2.button("Approve", key=f"a_{t['ID']}"):
                    update_status("Tasks", t['ID'], "Active", 6)
                    st.rerun()

            st.write("### 📜 Activity Log")
            df = pd.DataFrame(data['history'])
            if not df.empty:
                st.dataframe(df.tail(15).iloc[::-1], use_container_width=True, hide_index=True)
        else:
            st.warning("Restricted Area")

if __name__ == "__main__":
    main()
