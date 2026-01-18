import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime, timedelta, date
import time
import math
import random
import extra_streamlit_components as stx

# --- CONFIGURATION ---
SHEET_NAME = "Khanna Family App DB"
FAMILY_GOAL_TARGET = 2000  # Points needed for Water Park

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
        # Safety cleanup for empty cells
        pts = float(row.get('Points', 0) if row.get('Points') else 0)
        xp = float(row.get('XP', 0) if row.get('XP') else 0)
        streak = int(row.get('Streak', 0) if row.get('Streak') else 0)
        last_active = row.get('Last_Active', "")
        
        users_dict[row['Name']] = {
            'role': row['Role'], 
            'pin': str(row['Pin']),
            'points': pts,
            'xp': xp,
            'streak': streak,
            'last_active': last_active
        }
    
    return {"tasks": tasks, "rewards": rewards, "history": history, "users": users_dict}

def log_history(user, action, item, points_change):
    sh = get_connection()
    worksheet = sh.worksheet("History")
    date_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    worksheet.append_row([date_str, user, action, item, points_change])

def update_user_stats(user, new_points, new_xp, new_streak, new_date):
    sh = get_connection()
    ws = sh.worksheet("Users")
    cell = ws.find(user, in_column=1)
    
    # Update Points (Col 4), XP (Col 5), Streak (Col 6), Last Active (Col 7)
    # We update the whole row range to be efficient
    ws.update_cell(cell.row, 4, new_points)
    ws.update_cell(cell.row, 5, new_xp)
    ws.update_cell(cell.row, 6, new_streak)
    ws.update_cell(cell.row, 7, new_date)

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

# --- GAME LOGIC HELPERS ---
def calculate_level(xp):
    # Formula: Level = Square Root of XP (e.g., 100 XP = Lvl 10)
    return int(math.sqrt(xp))

def get_level_progress(xp):
    current_lvl = calculate_level(xp)
    next_lvl = current_lvl + 1
    xp_current_base = current_lvl ** 2
    xp_next_goal = next_lvl ** 2
    
    progress = (xp - xp_current_base) / (xp_next_goal - xp_current_base)
    return current_lvl, progress, xp_next_goal

def check_streak(last_active_str):
    if not last_active_str:
        return 0, True # New streak
        
    today = date.today()
    try:
        last_date = datetime.strptime(last_active_str, "%Y-%m-%d").date()
    except:
        return 0, True # Error parsing, reset
    
    delta = (today - last_date).days
    
    if delta == 0:
        return 0, False # Already active today
    elif delta == 1:
        return 1, True # Increment streak!
    else:
        return -1, True # Broken streak, reset to 1

# --- LOGIN MANAGER ---
def get_login_manager():
    return stx.CookieManager()

# --- MAIN APP ---
def main():
    st.set_page_config(page_title="Khanna Family RPG", page_icon="⚔️")
    
    # CSS: Progress Bars & Cards
    st.markdown("""
        <style>
        div.stButton > button[kind="primary"] {
            background-color: #28a745; color: white; border-radius: 12px; height: 3em; width: 100%;
        }
        div.stButton > button[kind="secondary"] {
            border-radius: 12px; height: 3em; width: 100%;
        }
        .stat-card {
            background-color: #262730; border: 1px solid #464b59; border-radius: 10px; padding: 10px; text-align: center;
        }
        .stat-card.active { border: 2px solid #ff4b4b; background-color: #362022; }
        .lvl-badge { background-color: #FFD700; color: black; padding: 2px 6px; border-radius: 4px; font-weight: bold; font-size: 0.8em; }
        </style>
        """, unsafe_allow_html=True)

    try:
        data = load_data()
    except Exception as e:
        st.warning("Syncing DB...")
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
        st.title("🔒 Login")
        valid_users = list(data['users'].keys())
        if not valid_users: st.error("No users found!"); return
        user_select = st.selectbox("Who are you?", valid_users)
        pin_input = st.text_input("Enter PIN", type="password")
        if st.button("Login", type="primary"):
            if pin_input == str(data['users'][user_select]['pin']):
                st.session_state['authenticated'] = True
                st.session_state['user'] = user_select
                cookie_manager.set("active_user", user_select, expires_at=datetime.now() + timedelta(days=30))
                st.rerun()
            else:
                st.error("Wrong PIN!")
        return

    # LOAD USER DATA
    u_data = data['users'][user]
    role = u_data['role']
    cur_pts = u_data['points']
    cur_xp = u_data['xp']
    cur_streak = u_data['streak']
    
    # LEVEL CALCULATIONS
    level, progress_pct, next_xp = get_level_progress(cur_xp)
    
    # Header
    c1, c2 = st.columns([3, 1])
    c1.title(f"👋 Hi, Lvl {level} {user}!")
    if c2.button("Logout"):
        cookie_manager.delete("active_user")
        st.session_state['authenticated'] = False
        st.rerun()

    # --- 1. GLOBAL FAMILY GOAL ---
    total_family_points = sum(u['points'] for u in data['users'].values())
    goal_pct = min(total_family_points / FAMILY_GOAL_TARGET, 1.0)
    
    st.write(f"### 🏖️ Family Goal: Water Park Trip ({int(total_family_points)}/{FAMILY_GOAL_TARGET})")
    st.progress(goal_pct)
    if goal_pct >= 1.0:
        st.success("🎉 GOAL REACHED! PACK YOUR BAGS! 🎉")
    
    st.divider()

    # --- 2. LEADERBOARD (SORTED BY XP/LEVEL) ---
    st.write("### 🏆 Hall of Fame (Lifetime XP)")
    # Sort by XP descending
    sorted_members = sorted(data['users'].keys(), key=lambda x: data['users'][x]['xp'], reverse=True)
    
    cols = st.columns(len(sorted_members))
    for idx, member in enumerate(sorted_members):
        m_data = data['users'][member]
        m_lvl = calculate_level(m_data['xp'])
        m_streak = m_data['streak']
        
        # Badge Logic
        badge = "🌱 Rookie"
        if m_lvl >= 5: badge = "🔥 Pro"
        if m_lvl >= 10: badge = "👑 Legend"
        
        # Flame for streak
        streak_icon = f"🔥{m_streak}" if m_streak > 0 else "❄️"
        
        border_cls = "stat-card active" if member == user else "stat-card"
        
        cols[idx].markdown(f"""
            <div class="{border_cls}">
                <div class="lvl-badge">{badge}</div>
                <h3 style="margin:0">Lvl {m_lvl}</h3>
                <p style="font-size:0.8em">{member}</p>
                <p style="font-size:0.8em; color:#aaa;">{streak_icon} Streak</p>
            </div>
        """, unsafe_allow_html=True)
        
    st.divider()

    # --- TABS ---
    tab1, tab2, tab3 = st.tabs(["⚔️ Tasks", "🎁 Rewards", "⚙️ Admin"])

    # --- TAB 1: TASKS ---
    with tab1:
        # Multiplier Logic Display
        multiplier = 1.0
        if cur_streak >= 7: multiplier = 1.5
        elif cur_streak >= 3: multiplier = 1.2
        
        if multiplier > 1.0:
            st.info(f"⚡ **Streak Bonus Active!** You are earning **{multiplier}x** points today!")

        st.subheader("Your Missions")
        
        my_tasks = []
        for t in data['tasks']:
            assignees = str(t['Assignee']) 
            if t['Status'] == "Active":
                if "Any" in assignees or user in assignees:
                    my_tasks.append(t)
        
        if not my_tasks:
            st.info("No active missions. Rest up, hero! 🛌")

        for task in my_tasks:
            with st.container(border=True):
                c_text, c_btn = st.columns([3, 1])
                
                base_pts = float(task['Points'])
                final_pts = base_pts * multiplier
                
                assignee_display = "Shared" if "," in task['Assignee'] else "You"
                if task['Assignee'] == "Any": assignee_display = "Anyone"
                
                c_text.write(f"**{task['Title']}**")
                c_text.caption(f"💰 {final_pts:g} pts (Base: {base_pts}) • {assignee_display}")
                
                if c_btn.button("✅ Done", key=f"btn_{task['ID']}", type="primary"):
                    # --- CORE LOGIC: XP + POINTS + STREAKS ---
                    
                    # 1. Calculate new totals
                    new_pts_total = cur_pts + final_pts
                    new_xp_total = cur_xp + final_pts # XP grows same as points earned
                    
                    # 2. Check Streak
                    streak_change, should_update = check_streak(u_data['last_active'])
                    new_streak = cur_streak
                    if should_update:
                        if streak_change == 1: new_streak += 1 # Increment
                        elif streak_change == -1: new_streak = 1 # Reset to 1
                        # If 0, streak stays same (already active today)
                    
                    today_str = datetime.now().strftime("%Y-%m-%d")
                    
                    # 3. Commit to DB
                    update_user_stats(user, new_pts_total, new_xp_total, new_streak, today_str)
                    
                    # 4. Log History
                    log_history(user, "Completed Task", task['Title'], f"+{final_pts:g}")
                    
                    if task['Frequency'] == "One-time":
                        update_status("Tasks", task['ID'], "Completed", 6)
                    
                    st.balloons()
                    st.toast(f"Heroic! +{final_pts:g} pts | Streak: {new_streak}")
                    time.sleep(1.5)
                    st.rerun()

        st.divider()
        with st.expander("➕ Propose New Mission"):
            with st.form("new_task"):
                assignee_str = user
                if role == "admin":
                    sel = st.multiselect("Assign to:", ["Any"] + sorted(list(data['users'].keys())), default=["Any"])
                    assignee_str = ", ".join(sel) if sel else "Any"
                
                t_title = st.text_input("Mission Title")
                t_pts = st.number_input("Base Points", min_value=0.0, step=0.5)
                
                if st.form_submit_button("Submit"):
                    if t_pts > 0:
                        nid = int(datetime.now().timestamp())
                        add_entry("Tasks", [nid, t_title, t_pts, assignee_str, "One-time", "Pending Approval"])
                        st.success("Mission sent to High Command!")
                    else:
                        st.error("Points must be > 0")

    # --- TAB 2: REWARDS ---
    with tab2:
        # --- MYSTERY BOX (GACHA) ---
        st.subheader("🎲 Mystery Box")
        with st.container(border=True):
            c1, c2 = st.columns([2, 1])
            c1.write("**Try your luck!** Cost: 15 pts")
            c1.caption("Win between 5 and 50 points!")
            
            if c2.button("Open Box 🎁", disabled=cur_pts < 15, type="primary"):
                # Gacha Logic
                cost = 15
                prize = random.randint(5, 50)
                net_change = prize - cost # e.g., -15 + 50 = +35
                
                new_pts_total = cur_pts + net_change
                # XP does NOT go down on cost, but DOES go up on prize? 
                # Usually gambling doesn't give XP. Let's strictly adjust Wallet Points.
                
                update_user_stats(user, new_pts_total, cur_xp, cur_streak, u_data['last_active'])
                log_history(user, "Mystery Box", f"Won {prize} pts", f"{net_change:+g}")
                
                if prize > 25:
                    st.balloons()
                    st.success(f"JACKPOT! You won {prize} points!")
                else:
                    st.toast(f"You won {prize} points.")
                
                time.sleep(2)
                st.rerun()

        st.divider()
        st.subheader("Rewards Catalog")
        active_rewards = [r for r in data['rewards'] if r['Status'] == "Approved"]
        for reward in active_rewards:
            with st.container(border=True):
                c1, c2 = st.columns([3, 1])
                c1.write(f"**{reward['Title']}**")
                c1.caption(f"Cost: {float(reward['Cost']):g} pts")
                
                cost = float(reward['Cost'])
                if c2.button("Redeem", key=f"r_{reward['ID']}", disabled=cur_pts < cost):
                    # Only subtract Points, NOT XP
                    new_pts = cur_pts - cost
                    update_user_stats(user, new_pts, cur_xp, cur_streak, u_data['last_active'])
                    log_history(user, "Redeemed Reward", reward['Title'], f"-{cost:g}")
                    st.balloons()
                    st.toast("Item Acquired!")
                    time.sleep(1.5)
                    st.rerun()
        
        st.divider()
        with st.expander("➕ Request New Reward"):
            with st.form("new_reward"):
                r_title = st.text_input("Reward Name")
                r_cost = st.number_input("Cost", min_value=0.0, step=1.0)
                if st.form_submit_button("Submit"):
                    if r_cost > 0:
                        nid = int(datetime.now().timestamp())
                        add_entry("Rewards", [nid, r_title, r_cost, "Pending Approval"])
                        st.success("Request sent!")

    # --- TAB 3: ADMIN ---
    with tab3:
        if role == "admin":
            st.write("### 🛡️ High Command")
            
            # Tasks Pending
            p_tasks = [t for t in data['tasks'] if t['Status'] == "Pending Approval"]
            if p_tasks:
                st.write(f"**Mission Requests ({len(p_tasks)})**")
                for t in p_tasks:
                    with st.container(border=True):
                        st.write(f"{t['Title']} ({t['Points']} pts) -> {t['Assignee']}")
                        c1, c2, c3 = st.columns(3)
                        if c1.button("✅", key=f"at_{t['ID']}"):
                            update_status("Tasks", t['ID'], "Active", 6)
                            st.rerun()
                        if c2.button("❌", key=f"rt_{t['ID']}"):
                            update_status("Tasks", t['ID'], "Rejected", 6)
                            st.rerun()
                        if c3.button("🗑️", key=f"dt_{t['ID']}"):
                            delete_entry("Tasks", t['ID'])
                            st.rerun()

            # Rewards Pending
            p_rewards = [r for r in data['rewards'] if r['Status'] == "Pending Approval"]
            if p_rewards:
                st.divider()
                st.write(f"**Reward Requests ({len(p_rewards)})**")
                for r in p_rewards:
                    with st.container(border=True):
                        st.write(f"{r['Title']} ({r['Cost']} pts)")
                        c1, c2, c3 = st.columns(3)
                        if c1.button("✅", key=f"ar_{r['ID']}"):
                            update_status("Rewards", r['ID'], "Approved", 4)
                            st.rerun()
                        if c2.button("❌", key=f"rr_{r['ID']}"):
                            update_status("Rewards", r['ID'], "Rejected", 4)
                            st.rerun()
                        if c3.button("🗑️", key=f"dr_{r['ID']}"):
                            delete_entry("Rewards", r['ID'])
                            st.rerun()

            # Log
            st.divider()
            st.write("### 📜 Chronicle")
            df = pd.DataFrame(data['history'])
            if not df.empty:
                st.dataframe(df.tail(15).iloc[::-1], use_container_width=True, hide_index=True)
        else:
            st.info("Restricted Area. Clearance Level: ADMIN")

if __name__ == "__main__":
    main()
