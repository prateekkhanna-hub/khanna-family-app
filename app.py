import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime, timedelta
import time
import extra_streamlit_components as stx
import re
import random

# --- CONFIG ---
SHEET_NAME = "Khanna Family App DB"
SCOPE = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']

# --- BACKEND ---
@st.cache_resource
def get_sh():
    try: creds = Credentials.from_service_account_info(dict(st.secrets["gcp_service_account"]), scopes=SCOPE)
    except: creds = Credentials.from_service_account_file("credentials.json", scopes=SCOPE)
    return gspread.authorize(creds).open(SHEET_NAME)

def load_data():
    sh = get_sh()
    # Fetch all data in one go
    res = sh.values_batch_get(['Tasks!A:Z', 'Rewards!A:Z', 'History!A:Z', 'Users!A:Z', 'Settings!A:Z'])
    
    def to_df(idx):
        vals = res['valueRanges'][idx].get('values', [])
        if not vals: return pd.DataFrame()
        
        # 1. Clean Headers
        cols = [re.sub(r'\s*\([A-Z]\)', '', str(h)).strip().title() for h in vals[0]]
        cols = ['XP' if c == 'Xp' else c for c in cols]
        
        # 2. Robust Row Loading
        header_len = len(cols)
        data = []
        for row in vals[1:]:
            clean_row = row[:header_len] + [None] * (max(0, header_len - len(row)))
            data.append(clean_row)
            
        return pd.DataFrame(data, columns=cols)

    dfs = {k: to_df(i) for i, k in enumerate(['tasks', 'rewards', 'history', 'users', 'settings'])}
    
    # Process Users Data
    if not dfs['users'].empty:
        for req_col in ['Points', 'XP', 'Streak', 'Pin']: 
            if req_col not in dfs['users'].columns: dfs['users'][req_col] = 0
        
        num_cols = ['Points', 'XP', 'Streak']
        dfs['users'][num_cols] = dfs['users'][num_cols].apply(pd.to_numeric, errors='coerce').fillna(0)
        dfs['users']['_row_idx'] = range(2, len(dfs['users']) + 2)
        dfs['users'].set_index('Name', inplace=True, drop=False)
    
    settings = dict(zip(dfs['settings']['Setting'], dfs['settings']['Value'])) if not dfs['settings'].empty else {}
    return dfs, settings

def get_level(xp):
    lvl = int((xp ** 0.5) / 2) + 1 if xp > 0 else 1
    titles = {1:"Rookie 🌱", 2:"Scout 🔭", 3:"Adventurer 🎒", 4:"Warrior ⚔️", 5:"Knight 🛡️", 6:"Ninja 🥷", 7:"Master 🧘", 8:"Champion 🏆", 9:"Legend 👑"}
    return lvl, titles.get(lvl, "Cosmic 🌌")

def update_history(user, action_type, item, points_change):
    ws = get_sh().worksheet("History")
    row_data = [datetime.now().strftime("%Y-%m-%d %H:%M"), user, action_type, item, points_change]
    ws.append_row(row_data)

def complete_task(user, t, u_dat, done_today_count, settings):
    try:
        # 1. Calculate Rewards
        mult = 1.5 if u_dat['Streak'] >= 7 else (1.2 if u_dat['Streak'] >= 3 else 1.0)
        pts = float(t['Points']) * mult
        
        today = datetime.now().strftime("%Y-%m-%d")
        new_strk = int(u_dat['Streak'])
        last_active = str(u_dat.get('Last_Active', ''))
        
        # Streak Logic
        if last_active != today:
            yesterday = (datetime.now()-timedelta(days=1)).strftime("%Y-%m-%d")
            new_strk = new_strk + 1 if last_active == yesterday else 1
        
        # 2. Batch Update User Stats
        ws_u = get_sh().worksheet("Users")
        row_idx = u_dat['_row_idx']
        
        ws_u.update(range_name=f"D{row_idx}:F{row_idx}", values=[[u_dat['Points'] + pts, new_strk, today]])
        ws_u.update_cell(row_idx, 8, u_dat['XP'] + pts)
        
        # 3. Update Global Goal
        current_global = float(settings.get('Family_Goal_Current', 0))
        ws_s = get_sh().worksheet("Settings")
        try:
            cell = ws_s.find("Family_Goal_Current", in_column=1)
            ws_s.update_cell(cell.row, 2, current_global + pts)
        except: pass

        # 4. Update History
        update_history(user, "Quest", t['Title'], pts)
        
        # 5. Update Task Status
        if t.get('Frequency') == "One-time":
            ws_t = get_sh().worksheet("Tasks")
            ws_t.update_cell(int(t.name) + 2, 6, "Completed")

        st.toast(f"✅ Nice! Earned {pts:g} Gold!")
        time.sleep(1)
    except Exception as e:
        st.error(f"Error: {e}")

def buy_reward(user, r, u_dat):
    try:
        ws = get_sh().worksheet("Users")
        row_idx = u_dat['_row_idx']
        ws.update_cell(row_idx, 4, u_dat['Points'] - float(r['Cost']))
        update_history(user, "Reward", r['Title'], -float(r['Cost']))
        st.toast(f"🎁 Redeemed: {r['Title']}")
        time.sleep(1)
    except Exception as e:
        st.error(f"Error: {e}")

# --- UPDATED POP-UP MODAL (Min Points 0.5) ---
@st.dialog("💡 Propose New Quest")
def propose_quest_modal(user, user_list):
    with st.form("new_q_modal"):
        st.write("Suggest a task to the Admins.")
        new_t = st.text_input("Quest Title")
        # CHANGED: min_value=0.5, step=0.5
        pts = st.number_input("Suggested Points", min_value=0.5, value=10.0, step=0.5)
        
        c1, c2 = st.columns(2)
        with c1:
            options = ["Any"] + user_list
            assignee = st.selectbox("Assign To", options)
        with c2:
            freq = st.selectbox("Frequency", ["One-time", "Daily", "Weekly", "Twice Daily"])
        
        if st.form_submit_button("Submit Proposal"):
            ws_t = get_sh().worksheet("Tasks")
            ws_t.append_row([int(time.time()), new_t, pts, assignee, freq, "Pending Approval"])
            st.success("Sent for approval!")
            time.sleep(1)
            st.rerun()

# --- UI ---
def main():
    st.set_page_config(page_title="Khanna Family Quest", page_icon="🛡️", layout="wide")
    
    st.markdown("""<style>
        div.stButton > button { width: 100%; border-radius: 8px; font-weight: bold; height: 2.5em !important; }
        .stat-box { background: #262730; border: 1px solid #464b59; border-radius: 10px; padding: 10px; text-align: center; color: white; margin-bottom: 10px;}
        .stat-val { font-size: 1.2rem; font-weight: bold; margin: 0; }
        .stat-lbl { font-size: 0.8rem; color: #aaa; margin: 0; }
        </style>""", unsafe_allow_html=True)

    try: dfs, settings = load_data()
    except Exception as e: st.error(f"DB Error: {e}"); st.stop()

    # --- AUTHENTICATION ---
    mgr = stx.CookieManager(key="auth_manager")
    auth_user = mgr.get("active_user")

    if 'user' not in st.session_state: st.session_state['user'] = None

    if st.session_state['user'] is None and auth_user:
        if auth_user in dfs['users'].index: st.session_state['user'] = auth_user
        else: mgr.delete("active_user")

    if not st.session_state['user']:
        st.title("🛡️ Login")
        valid_users = dfs['users'].index.tolist() if not dfs['users'].empty else []
        with st.form("login_form"):
            u = st.selectbox("Hero", valid_users) if valid_users else None
            pin = st.text_input("PIN", type="password")
            if st.form_submit_button("Enter", type="primary") and u:
                if str(pin).strip() == str(dfs['users'].loc[u].get('Pin', '0000')).strip():
                    st.session_state['user'] = u
                    mgr.set("active_user", u, expires_at=datetime.now() + timedelta(days=30))
                    st.success("Welcome!"); time.sleep(0.5); st.rerun()
                else: st.error("Wrong PIN")
        return

    # --- SIDEBAR ---
    user = st.session_state['user']
    u_dat = dfs['users'].loc[user]
    lvl, title = get_level(u_dat['XP'])
    
    is_admin = str(u_dat.get('Role', '')).strip().lower() == 'admin'

    with st.sidebar:
        st.markdown(f"## 🛡️ {user}")
        st.markdown(f"**{title}** (Lvl {lvl})")
        
        c1, c2 = st.columns(2)
        c1.markdown(f"<div class='stat-box'><div class='stat-val'>💰 {u_dat['Points']:g}</div><div class='stat-lbl'>Gold</div></div>", unsafe_allow_html=True)
        c2.markdown(f"<div class='stat-box'><div class='stat-val'>🔥 {int(u_dat['Streak'])}</div><div class='stat-lbl'>Streak</div></div>", unsafe_allow_html=True)
        
        st.divider()
        cur, tgt = float(settings.get('Family_Goal_Current', 0)), float(settings.get('Family_Goal_Target', 2000))
        prog = cur/tgt if tgt > 0 else 0
        st.write(f"🌍 **{settings.get('Family_Goal_Title', 'Goal')}**")
        st.progress(min(max(prog, 0.0), 1.0))
        st.caption(f"{cur:g} / {tgt:g} Gold collected")
        
        st.divider()
        if st.button("🚪 Log out"): 
            mgr.delete("active_user")
            st.session_state['user'] = None
            st.rerun()

    # --- MAIN CONTENT ---
    t1, t2, t3, t4 = st.tabs(["⚔️ Quests", "🎁 Loot", "🏆 Fame", "⚙️ Admin"])

    with t1: # Quests
        c_search, c_add = st.columns([4, 1])
        search_q = c_search.text_input("Search Quests...", placeholder="e.g. Dishwasher", label_visibility="collapsed")
        
        if c_add.button("➕ Propose"):
            all_users = dfs['users'].index.tolist()
            propose_quest_modal(user, all_users)

        h_df = dfs['history']
        today = datetime.now().strftime("%Y-%m-%d")
        done_today_list = []
        if not h_df.empty and 'User' in h_df.columns and 'Date' in h_df.columns:
            done_today_list = h_df[(h_df['User'] == user) & (h_df['Date'].str.contains(today, na=False))]['Item'].tolist()
        
        tasks = dfs['tasks']
        if search_q: tasks = tasks[tasks['Title'].str.contains(search_q, case=False, na=False)]
        
        categories = {
            "🌅 Daily Routines": ["Daily"],
            "🔄 Weekly & Recurring": ["Twice Daily", "Weekly"],
            "⚔️ Challenges & One-Time": ["One-time"]
        }
        
        for cat_name, freq_list in categories.items():
            cat_tasks = tasks[tasks['Frequency'].isin(freq_list)]
            if cat_tasks.empty: continue
            
            with st.expander(cat_name, expanded=True):
                for idx, t in cat_tasks.iterrows():
                    # VISIBILITY LOGIC
                    assignee_raw = t.get('Assignee', 'Any')
                    is_assigned_to_me = user in assignee_raw or "Any" in assignee_raw
                    
                    if t.get('Status') == 'Active' and (is_assigned_to_me or is_admin):
                        count = done_today_list.count(t['Title'])
                        is_done = False
                        if t.get('Frequency') == "Twice Daily":
                            is_done = (count >= 2) or (datetime.now().hour < 16 and count >= 1)
                        else: is_done = count >= 1

                        if not is_done:
                            with st.container(border=True):
                                c_txt, c_btn = st.columns([3, 1])
                                if is_admin and not is_assigned_to_me:
                                    c_txt.write(f"**{t['Title']}** ({t['Points']} pts)")
                                    c_txt.caption(f"👤 Assigned to: {assignee_raw} | {t['Frequency']}")
                                else:
                                    c_txt.write(f"**{t['Title']}** ({t['Points']} pts)")
                                
                                st.button("Done", key=f"btn_task_{idx}", 
                                          on_click=complete_task, 
                                          args=(user, t, u_dat, count, settings))

    with t2: # Loot
        st.markdown("### ❓ Mystery Box (15g)")
        if st.button("Open Box", disabled=u_dat['Points'] < 15):
            prize = random.choice([5, 10, 15, 20, 50])
            ws = get_sh().worksheet("Users"); row_idx = u_dat['_row_idx']
            ws.update_cell(row_idx, 4, u_dat['Points'] - 15 + prize)
            update_history(user, "Mystery Box", f"Won {prize}", prize-15)
            st.balloons() if prize > 15 else st.info(f"Won {prize}")
            time.sleep(1); st.rerun()

        st.divider()
        search_r = st.text_input("Search Rewards...", placeholder="e.g. Robux", label_visibility="collapsed")
        rewards = dfs['rewards']
        if search_r: rewards = rewards[rewards['Title'].str.contains(search_r, case=False, na=False)]

        for idx, r in rewards.iterrows():
            if r.get('Status') == 'Approved':
                with st.container(border=True):
                    c1, c2 = st.columns([3,1])
                    c1.write(f"**{r['Title']}** ({r['Cost']} pts)")
                    st.button("Buy", key=f"btn_rew_{idx}", 
                              disabled=u_dat['Points'] < float(r['Cost']),
                              on_click=buy_reward,
                              args=(user, r, u_dat))

    with t3: # Fame
        for n, row in dfs['users'].sort_values('XP', ascending=False).iterrows():
            lv, ti = get_level(row['XP'])
            st.info(f"**{n}** ({ti} Lvl {lv}) - {row['Points']:g} pts | 🔥 {int(row['Streak'])}")

    with t4: # Admin
        if is_admin:
            if st.button("🔄 Sync XP"):
                xp_map = dfs['history'].copy()
                if not xp_map.empty:
                    xp_map['Points'] = pd.to_numeric(xp_map['Points_Change'], errors='coerce')
                    totals = xp_map.groupby('User')['Points'].sum().to_dict()
                    ws = get_sh().worksheet("Users")
                    rows = ws.get_all_values()
                    for i, r in enumerate(rows[1:], 2):
                        if r[0] in totals: ws.update_cell(i, 8, max(0, totals[r[0]]))
                    st.success("Synced!"); time.sleep(1); st.rerun()
            
            st.write("#### Approvals")
            pend_t = dfs['tasks'][dfs['tasks']['Status'] == "Pending Approval"]
            for idx, t in pend_t.iterrows():
                c1, c2, c3 = st.columns([2,1,1])
                c1.write(f"{t['Title']} ({t['Points']})")
                ws_t = get_sh().worksheet("Tasks")
                if c2.button("✅", key=f"ok_{idx}"): ws_t.update_cell(idx + 2, 6, "Active"); st.rerun()
                if c3.button("❌", key=f"no_{idx}"): ws_t.update_cell(idx + 2, 6, "Rejected"); st.rerun()

if __name__ == "__main__": main()
