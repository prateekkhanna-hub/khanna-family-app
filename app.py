import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime, timedelta
import time
import random
import extra_streamlit_components as stx
import re

# --- CONFIGURATION ---
SHEET_NAME = "Khanna Family App DB"
GLOBAL_GOAL_TARGET_DEFAULT = 2000 
GLOBAL_GOAL_TITLE_DEFAULT = "Water Park Trip"

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
def clean_header(header):
    header = re.sub(r'\s*\([A-Z]\)', '', header) # Removes (A), (B) etc
    return header.strip()

def load_data():
    sh = get_connection()
    ranges = ['Tasks!A:Z', 'Rewards!A:Z', 'History!A:Z', 'Users!A:Z', 'Settings!A:Z']
    results = sh.values_batch_get(ranges)
    
    def get_df(index):
        rows = results['valueRanges'][index].get('values', [])
        if not rows: return []
        headers = rows[0]
        cleaned_headers = [clean_header(h) for h in headers]
        return [dict(zip(cleaned_headers, row)) for row in rows[1:]]

    tasks = get_df(0)
    rewards = get_df(1)
    history = get_df(2)
    users_list = get_df(3)
    settings_list = get_df(4)
    
    users_dict = {}
    for row in users_list:
        if not row.get('Name'): continue
        role_raw = row.get('Role', 'Kid')
        role = role_raw.strip().lower()
        pin = str(row.get('Pin', '0000'))
        
        try: pts = float(row.get('Points', 0))
        except: pts = 0.0
        try: xp = float(row.get('XP', 0))
        except: xp = 0.0
        try: streak = int(row.get('Streak', 0))
        except: streak = 0
        
        users_dict[row['Name']] = {
            'role': role,
            'pin': pin,
            'points': pts,
            'xp': xp,
            'streak': streak,
            'last_active': row.get('Last_Active', ""),
            'badges': row.get('Badges', "")
        }

    settings_dict = {}
    for row in settings_list:
        if 'Setting' in row and 'Value' in row:
            try: settings_dict[row['Setting']] = float(row['Value'])
            except: settings_dict[row['Setting']] = row['Value']
            
    return {"tasks": tasks, "rewards": rewards, "history": history, "users": users_dict, "settings": settings_dict}

# --- LOGIC & UPDATES ---
def update_setting(key, value):
    sh = get_connection()
    try: ws = sh.worksheet("Settings")
    except: ws = sh.add_worksheet(title="Settings", rows=10, cols=2); ws.append_row(["Setting", "Value"])
    try: cell = ws.find(key, in_column=1); ws.update_cell(cell.row, 2, value)
    except: ws.append_row([key, value])

def calculate_level(xp):
    if xp <= 0: return 1, "Rookie 🌱"
    level = int((xp ** 0.5) / 2) + 1
    titles = {
        1: "Rookie 🌱", 2: "Scout 🔭", 3: "Adventurer 🎒", 
        4: "Warrior ⚔️", 5: "Knight 🛡️", 6: "Ninja 🥷", 
        7: "Master 🧘", 8: "Champion 🏆", 9: "Legend 👑", 10: "Mythic 🐉"
    }
    title = titles.get(level, "Cosmic Being 🌌")
    return level, title

def recalculate_all_xp():
    """Scans History to calculate total lifetime XP for all users."""
    data = load_data()
    history = data['history']
    
    # dictionary to hold totals: {'Prateek': 105.5, 'Rhea': 50.0}
    user_xp_totals = {}

    for row in history:
        # Expected row keys: Date, User, Action, Item, Points_Change
        # Adjust keys based on your actual history header names
        user = row.get('User') or row.get('user') # Handle case sensitivity
        points_str = row.get('Points_Change') or row.get('Points Change') or row.get('points_change')
        
        if user and points_str:
            try:
                val = float(points_str)
                # XP only counts positive gains (Tasks/Bonuses), not Spending
                if val > 0:
                    user_xp_totals[user] = user_xp_totals.get(user, 0) + val
            except:
                continue

    # Now update the Users Sheet
    sh = get_connection()
    ws = sh.worksheet("Users")
    
    # Iterate through users in sheet to find their row
    all_values = ws.get_all_values()
    headers = all_values[0]
    
    # Find column index for 'Name' and 'XP'
    # Headers might be "Name" or "Name (A)" depending on cleanup
    name_col_idx = -1
    xp_col_idx = -1
    
    for i, h in enumerate(headers):
        clean_h = clean_header(h).lower()
        if clean_h == 'name': name_col_idx = i
        if clean_h == 'xp': xp_col_idx = i
        
    if name_col_idx == -1 or xp_col_idx == -1:
        return False, "Could not find 'Name' or 'XP' columns in Users sheet."

    updates_made = 0
    for i, row in enumerate(all_values):
        if i == 0: continue # Skip header
        
        name = row[name_col_idx]
        if name in user_xp_totals:
            new_xp = user_xp_totals[name]
            # +1 because spreadsheet rows are 1-based
            ws.update_cell(i + 1, xp_col_idx + 1, new_xp)
            updates_made += 1
            
    return True, f"Updated XP for {updates_made} users."

def update_user_stats(user, points_change, xp_change):
    sh = get_connection()
    ws = sh.worksheet("Users")
    cell = ws.find(user, in_column=1)
    current_values = ws.row_values(cell.row)
    
    try: old_points = float(current_values[3])
    except: old_points = 0.0
    try: old_streak = int(current_values[4])
    except: old_streak = 0
    last_active_str = current_values[5] if len(current_values) > 5 else ""
    try: old_xp = float(current_values[7])
    except: old_xp = 0.0

    new_points = old_points + points_change
    new_xp = old_xp + xp_change
    new_streak = old_streak
    
    today_str = datetime.now().strftime("%Y-%m-%d")
    
    if xp_change > 0:
        if last_active_str == today_str:
            new_streak = old_streak
        elif last_active_str == (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d"):
            new_streak = old_streak + 1
        else:
            new_streak = 1
        ws.update_cell(cell.row, 6, today_str)

    ws.update_cell(cell.row, 4, new_points)
    ws.update_cell(cell.row, 5, new_streak)
    ws.update_cell(cell.row, 8, new_xp)
    
    if points_change > 0:
        update_setting("Family_Goal_Current", 
                       load_data()['settings'].get('Family_Goal_Current', 0) + points_change)

def add_entry(sheet_name, data_list):
    sh = get_connection()
    ws = sh.worksheet(sheet_name)
    ws.append_row(data_list)

def update_status(sheet_name, item_id, new_status, status_col_index):
    sh = get_connection()
    ws = sh.worksheet(sheet_name)
    cell = ws.find(str(item_id), in_column=1)
    ws.update_cell(cell.row, status_col_index, new_status)

def log_history(user, action, item, points_change):
    sh = get_connection()
    ws = sh.worksheet("History")
    date_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    ws.append_row([date_str, user, action, item, points_change])

def get_login_manager():
    return stx.CookieManager()

# --- MAIN APP ---
def main():
    st.set_page_config(page_title="Khanna Family Quest", page_icon="🛡️", layout="centered")
    
    st.markdown("""
        <style>
        div.stButton > button { width: 100%; border-radius: 8px; font-weight: bold; height: 2.5em !important; padding: 0px 10px; }
        div.stButton > button[kind="primary"] { background-color: #28a745; color: white; }
        .stat-strip { display: flex; justify-content: space-between; background-color: #262730; border: 1px solid #464b59; border-radius: 10px; padding: 10px 15px; margin-bottom: 15px; align-items: center; }
        .stat-item { text-align: center; flex: 1; }
        .stat-icon { font-size: 1.2rem; margin-bottom: 2px; display: block; }
        .stat-value { font-weight: bold; font-size: 1.1rem; margin: 0; color: white; }
        .stat-label { font-size: 0.75rem; color: #aaa; margin: 0; }
        .stat-card { background-color: #262730; border: 1px solid #464b59; border-radius: 10px; padding: 10px; margin-bottom: 8px; }
        .active-card { border: 2px solid #ff4b4b; background-color: #362022; }
        h3 { margin-top: -20px !important; padding-top: 0px !important; margin-bottom: 5px !important; }
        .stProgress > div > div > div > div { background-color: #00d4ff; }
        .block-container { padding-top: 2rem !important; padding-bottom: 5rem !important; }
        </style>
        """, unsafe_allow_html=True)

    try:
        data = load_data()
    except Exception as e:
        st.error(f"⚠️ Database Error: {e}"); st.stop()

    cookie_manager = get_login_manager()
    if 'authenticated' not in st.session_state: st.session_state['authenticated'] = False; st.session_state['user'] = None

    if not st.session_state['authenticated']:
        time.sleep(0.1)
        cookie_user = cookie_manager.get("active_user")
        if cookie_user and cookie_user in data['users']:
            st.session_state['authenticated'] = True; st.session_state['user'] = cookie_user; st.rerun()

    if not st.session_state['authenticated']:
        st.title("🛡️ Family Quest Login")
        valid_users = list(data['users'].keys())
        if not valid_users: st.error("No users found."); return
        user_select = st.selectbox("Select Your Hero", valid_users)
        pin_input = st.text_input("Secret Code", type="password")
        if st.button("Enter Realm", type="primary"):
            correct_pin = str(data['users'][user_select]['pin'])
            if pin_input == correct_pin:
                st.session_state['authenticated'] = True; st.session_state['user'] = user_select
                cookie_manager.set("active_user", user_select, expires_at=datetime.now() + timedelta(days=30))
                st.balloons(); st.rerun()
            else: st.error("Wrong PIN!")
        return

    user = st.session_state['user']
    user_data = data['users'][user]
    role = user_data['role']
    level, title = calculate_level(user_data['xp'])
    
    prev_threshold = ((level - 1) * 2) ** 2 if level > 1 else 0
    next_threshold = (level * 2) ** 2
    if next_threshold <= prev_threshold: next_threshold = prev_threshold + 10
    xp_percent = max(0.0, min(1.0, (user_data['xp'] - prev_threshold) / (next_threshold - prev_threshold)))

    top_c1, top_c2 = st.columns([3, 1])
    with top_c1: st.markdown(f"### {user} <span style='font-size:0.9rem; color:#aaa; font-weight:normal'>({title})</span>", unsafe_allow_html=True)
    with top_c2:
        if st.button("🚪 Logout"): cookie_manager.delete("active_user"); st.session_state['authenticated'] = False; st.session_state['user'] = None; st.rerun()
            
    st.markdown(f"""
    <div class="stat-strip">
        <div class="stat-item" style="border-right: 1px solid #444;"><span class="stat-icon">💰</span><p class="stat-value">{user_data['points']:g}</p><p class="stat-label">Gold</p></div>
        <div class="stat-item" style="border-right: 1px solid #444;"><span class="stat-icon">🔥</span><p class="stat-value">{user_data['streak']}</p><p class="stat-label">Days</p></div>
        <div class="stat-item"><span class="stat-icon">⚔️</span><p class="stat-value">{level}</p><p class="stat-label">Level</p></div>
    </div>
    """, unsafe_allow_html=True)
    
    g_current = data['settings'].get('Family_Goal_Current', 0)
    g_target = data['settings'].get('Family_Goal_Target', GLOBAL_GOAL_TARGET_DEFAULT)
    g_title = data['settings'].get('Family_Goal_Title', GLOBAL_GOAL_TITLE_DEFAULT)
    g_percent = min(g_current / g_target, 1.0)

    with st.expander(f"🌍 Goal: {g_title} ({int(g_percent*100)}%)", expanded=False):
        st.write(f"**Family Progress:** {int(g_current)} / {int(g_target)}")
        st.progress(g_percent)
        st.divider()
        st.write(f"**Your XP Progress:** {int(user_data['xp'])} / {int(next_threshold)}")
        st.progress(xp_percent)

    tab1, tab2, tab3, tab4 = st.tabs(["⚔️ Quests", "🎁 Loot", "🏆 Fame", "⚙️ Admin"])

    with tab1:
        st.subheader("Active Quests")
        my_tasks = [t for t in data['tasks'] if t['Status'] == "Active" and ("Any" in str(t['Assignee']) or user in str(t['Assignee']))]
        if not my_tasks: st.info("No active quests!")
        for task in my_tasks:
            with st.container(border=True):
                c_text, c_btn = st.columns([3, 1])
                base_points = float(task['Points'])
                multiplier = 1.0
                if user_data['streak'] >= 7: multiplier = 1.5
                elif user_data['streak'] >= 3: multiplier = 1.2
                final_points = base_points * multiplier
                c_text.write(f"**{task['Title']}**")
                if multiplier > 1.0: c_text.markdown(f"Points: ~~{base_points}~~ **{final_points:.1f}** (🔥 x{multiplier} Bonus!)")
                else: c_text.caption(f"Points: {base_points} • {task['Frequency']}")
                if c_btn.button("Complete", key=f"btn_{task['ID']}", type="primary"):
                    update_user_stats(user, final_points, final_points)
                    log_history(user, "Quest Complete", task['Title'], f"+{final_points:g}")
                    if task['Frequency'] == "One-time": update_status("Tasks", task['ID'], "Completed", 6)
                    st.balloons(); st.toast(f"Completed! +{final_points:g} Gold & XP"); time.sleep(1.5); st.rerun()

    with tab2:
        st.subheader("Marketplace")
        with st.container(border=True):
            st.markdown("### ❓ Mystery Box (Cost: 15)")
            if st.button("Open", disabled=user_data['points'] < 15):
                prize = random.choice([5, 10, 10, 15, 20, 25, 50])
                update_user_stats(user, prize - 15, 0)
                log_history(user, "Mystery Box", f"Won {prize}", f"{prize - 15}")
                if prize > 15: st.balloons(); st.success(f"JACKPOT! Won {prize}!")
                else: st.info(f"Won {prize}.")
                time.sleep(2); st.rerun()
        st.divider()
        for reward in [r for r in data['rewards'] if r['Status'] == "Approved"]:
            with st.container(border=True):
                c1, c2 = st.columns([3, 1])
                cost = float(reward['Cost'])
                c1.write(f"**{reward['Title']}** ({cost:g} pts)")
                if c2.button("Buy", key=f"buy_{reward['ID']}", disabled=user_data['points'] < cost):
                    update_user_stats(user, -cost, 0)
                    log_history(user, "Reward", reward['Title'], f"-{cost:g}")
                    st.snow(); st.toast("Redeemed!"); time.sleep(1); st.rerun()
        with st.expander("Request New Reward"):
            with st.form("new_reward"):
                rt = st.text_input("Name"); rc = st.number_input("Cost", min_value=1.0)
                if st.form_submit_button("Submit"):
                    add_entry("Rewards", [int(datetime.now().timestamp()), rt, rc, "Pending Approval"])
                    st.success("Sent!"); st.rerun()

    with tab3:
        st.subheader("🏆 Hall of Fame")
        for name, stats in sorted(data['users'].items(), key=lambda x: x[1]['xp'], reverse=True):
            lvl, title = calculate_level(stats['xp'])
            style = "stat-card active-card" if name == user else "stat-card"
            st.markdown(f"""<div class="{style}"><div style="display:flex; justify-content:space-between;">
            <div style="text-align:left;"><b>{name}</b><br><span style="color:#bbb;">{title} (Lvl {lvl})</span></div>
            <div style="text-align:right;"><b>{stats['points']:g} pts</b><br><span style="color:#ff4b4b;">🔥 {stats['streak']} day streak</span></div>
            </div></div>""", unsafe_allow_html=True)

    with tab4:
        if role == "admin": 
            st.write("### 🛡️ Admin Controls")
            
            # --- XP SYNC BUTTON ---
            with st.container(border=True):
                st.write("#### 🔧 Maintenance")
                st.info("Click this if XP looks wrong. It will look at History and recalculate total XP.")
                if st.button("🔄 Sync XP from History"):
                    with st.spinner("Crunching numbers..."):
                        success, msg = recalculate_all_xp()
                        if success: st.success(msg)
                        else: st.error(msg)
                    time.sleep(2); st.rerun()

            st.divider()
            with st.container(border=True):
                st.write("#### 🌍 Family Goal Settings")
                c_goal, c_target, c_save = st.columns([2, 1, 1])
                current_title = data['settings'].get('Family_Goal_Title', GLOBAL_GOAL_TITLE_DEFAULT)
                current_target = data['settings'].get('Family_Goal_Target', GLOBAL_GOAL_TARGET_DEFAULT)
                new_title = c_goal.text_input("Goal Reward Name", value=current_title)
                new_target = c_target.number_input("Target Points", value=float(current_target))
                if c_save.button("Update Goal"):
                    update_setting("Family_Goal_Title", new_title)
                    update_setting("Family_Goal_Target", new_target)
                    st.success("Goal Updated!"); time.sleep(1); st.rerun()

            st.divider()
            p_tasks = [t for t in data['tasks'] if t['Status'] == "Pending Approval"]
            p_rewards = [r for r in data['rewards'] if r['Status'] == "Pending Approval"]
            if p_tasks or p_rewards:
                st.write("#### ⏳ Pending Approvals")
                for t in p_tasks:
                    c1, c2, c3 = st.columns([2, 1, 1])
                    c1.write(f"Task: {t['Title']} ({t['Points']} pts)")
                    if c2.button("✅", key=f"at_{t['ID']}"): update_status("Tasks", t['ID'], "Active", 6); st.rerun()
                    if c3.button("❌", key=f"rt_{t['ID']}"): update_status("Tasks", t['ID'], "Rejected", 6); st.rerun()
                for r in p_rewards:
                    c1, c2, c3 = st.columns([2, 1, 1])
                    c1.write(f"Reward: {r['Title']} ({r['Cost']} pts)")
                    if c2.button("✅", key=f"apr_{r['ID']}"): update_status("Rewards", r['ID'], "Approved", 4); st.rerun()
                    if c3.button("❌", key=f"rjr_{r['ID']}"): update_status("Rewards", r['ID'], "Rejected", 4); st.rerun()
            else: st.info("No pending items.")
            
            st.divider()
            with st.expander("➕ Create Task"):
                tt = st.text_input("Title"); tp = st.number_input("Points", min_value=1.0)
                ta = st.text_input("Assignee", value="Any")
                if st.button("Create"):
                    add_entry("Tasks", [int(datetime.now().timestamp()), tt, tp, ta, "One-time", "Active"])
                    st.success("Created!"); time.sleep(1); st.rerun()
        else:
            st.warning(f"Restricted Area. You are logged in as role: '{role}'")

if __name__ == "__main__":
    main()
