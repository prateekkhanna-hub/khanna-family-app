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
        creds = Credentials.from_service_account_file("credentials.json", scopes=scope)
    return gspread.authorize(creds).open(SHEET_NAME)

# --- DATA FUNCTIONS ---
def load_data():
    sh = get_connection()
    # Fetch all necessary sheets
    ranges = ['Tasks!A:Z', 'Rewards!A:Z', 'History!A:Z', 'Users!A:Z', 'Settings!A:Z']
    results = sh.values_batch_get(ranges)
    
    def get_df(index):
        rows = results['valueRanges'][index].get('values', [])
        if not rows: return []
        headers = rows[0]
        # Clean headers: remove spaces
        headers = [h.strip() for h in headers]
        return [dict(zip(headers, row)) for row in rows[1:]]

    tasks = get_df(0)
    rewards = get_df(1)
    history = get_df(2)
    users_list = get_df(3)
    settings_list = get_df(4)
    
    users_dict = {}
    for row in users_list:
        # SAFETY CHECK: If Name or Role is missing, skip this row
        if not row.get('Name'): continue
        
        # Safe Getters (prevents crashing if column is missing)
        role = row.get('Role', 'Kid') # Default to Kid if missing
        pin = str(row.get('Pin', '0000'))
        
        # Number conversion safety
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

# --- GAMIFICATION LOGIC ---
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

def update_user_stats(user, points_change, xp_change):
    sh = get_connection()
    ws = sh.worksheet("Users")
    cell = ws.find(user, in_column=1)
    
    current_values = ws.row_values(cell.row)
    
    # Safe parsing of current values
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

    # Update columns D(4), E(5), H(8)
    ws.update_cell(cell.row, 4, new_points)
    ws.update_cell(cell.row, 5, new_streak)
    ws.update_cell(cell.row, 8, new_xp)
    
    if points_change > 0:
        try:
            ws_set = sh.worksheet("Settings")
            g_cell = ws_set.find("Family_Goal_Current", in_column=1)
            cur_global = float(ws_set.cell(g_cell.row, 2).value)
            ws_set.update_cell(g_cell.row, 2, cur_global + points_change)
        except:
            pass 

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
    
    st.markdown("""
        <style>
        div.stButton > button[kind="primary"] {
            background-color: #28a745; color: white; font-weight: bold; height: 3em; width: 100%; border-radius: 12px;
        }
        div.stButton > button[kind="secondary"] { height: 3em; width: 100%; border-radius: 12px; }
        .stat-card {
            background-color: #262730; border: 1px solid #464b59; border-radius: 10px; padding: 15px; text-align: center; margin-bottom: 10px;
        }
        .active-card { border: 2px solid #ff4b4b; background-color: #362022; }
        .stat-value { font-size: 1.5rem; font-weight: bold; margin: 0; }
        .stat-label { font-size: 0.9rem; color: #ccc; margin: 0; }
        .stProgress > div > div > div > div { background-color: #00d4ff; }
        </style>
        """, unsafe_allow_html=True)

    try:
        data = load_data()
    except Exception as e:
        st.error(f"⚠️ Database Error: {e}")
        st.stop()

    cookie_manager = get_login_manager()
    if 'authenticated' not in st.session_state:
        st.session_state['authenticated'] = False
        st.session_state['user'] = None

    if not st.session_state['authenticated']:
        time.sleep(0.1)
        cookie_user = cookie_manager.get("active_user")
        if cookie_user and cookie_user in data['users']:
            st.session_state['authenticated'] = True
            st.session_state['user'] = cookie_user
            st.rerun()

    if not st.session_state['authenticated']:
        st.title("🛡️ Family Quest Login")
        valid_users = list(data['users'].keys())
        if not valid_users: st.error("No users found."); return
        user_select = st.selectbox("Select Your Hero", valid_users)
        pin_input = st.text_input("Secret Code", type="password")
        if st.button("Enter Realm", type="primary"):
            # Check if Pin exists
            correct_pin = str(data['users'][user_select]['pin'])
            if pin_input == correct_pin:
                st.session_state['authenticated'] = True
                st.session_state['user'] = user_select
                expires = datetime.now() + timedelta(days=30)
                cookie_manager.set("active_user", user_select, expires_at=expires)
                st.balloons()
                st.rerun()
            else:
                st.error("Wrong PIN!")
        return

    user = st.session_state['user']
    user_data = data['users'][user]
    role = user_data['role']
    
    level, title = calculate_level(user_data['xp'])
    prev_threshold = ((level - 1) * 2) ** 2 if level > 1 else 0
    next_threshold = (level * 2) ** 2
    if next_threshold <= prev_threshold: next_threshold = prev_threshold + 10
    xp_progress = max(0.0, min(1.0, (user_data['xp'] - prev_threshold) / (next_threshold - prev_threshold)))

    c1, c2 = st.columns([3, 1])
    c1.title(f"{user}")
    c1.caption(f"**{title}** (Lvl {level})")
    if c2.button("Logout"):
        cookie_manager.delete("active_user")
        st.session_state['authenticated'] = False
        st.session_state['user'] = None
        st.rerun()
    
    st.write(f"**XP Progress:** {int(user_data['xp'])} / {int(next_threshold)}")
    st.progress(xp_progress)
    k1, k2 = st.columns(2)
    k1.metric("💰 Gold", f"{user_data['points']:g}")
    k2.metric("🔥 Streak", f"{user_data['streak']} Days")
    
    st.divider()
    g_current = data['settings'].get('Family_Goal_Current', 0)
    g_target = data['settings'].get('Family_Goal_Target', GLOBAL_GOAL_TARGET_DEFAULT)
    st.write(f"### 🌍 Family Goal: Water Park Trip!")
    st.progress(min(g_current / g_target, 1.0))
    st.caption(f"{int(g_current)} / {int(g_target)} pts")

    st.divider()
    tab1, tab2, tab3, tab4 = st.tabs(["⚔️ Quests", "🎁 Loot", "🏆 Hall of Fame", "⚙️ Admin"])

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
                    st.balloons()
                    st.toast(f"Completed! +{final_points:g} Gold & XP")
                    time.sleep(1.5)
                    st.rerun()

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
            st.write("### 🛡️ Admin")
            for t in [t for t in data['tasks'] if t['Status'] == "Pending Approval"]:
                c1, c2, c3 = st.columns([2, 1, 1])
                c1.write(f"{t['Title']} ({t['Points']} pts)")
                if c2.button("✅", key=f"at_{t['ID']}"): update_status("Tasks", t['ID'], "Active", 6); st.rerun()
                if c3.button("❌", key=f"rt_{t['ID']}"): update_status("Tasks", t['ID'], "Rejected", 6); st.rerun()
            st.divider()
            with st.expander("➕ Create Task"):
                tt = st.text_input("Title"); tp = st.number_input("Points", min_value=1.0)
                ta = st.text_input("Assignee", value="Any")
                if st.button("Create"):
                    add_entry("Tasks", [int(datetime.now().timestamp()), tt, tp, ta, "One-time", "Active"])
                    st.success("Created!"); time.sleep(1); st.rerun()
            st.divider(); st.write("History"); st.dataframe(pd.DataFrame(data['history']).tail(10).iloc[::-1], use_container_width=True, hide_index=True)
        else: st.warning("Restricted")

if __name__ == "__main__":
    main()
