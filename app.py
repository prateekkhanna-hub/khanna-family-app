import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime, timedelta
import time, random, re
import extra_streamlit_components as stx

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
    # Batch get all data at once
    res = sh.values_batch_get(['Tasks!A:Z', 'Rewards!A:Z', 'History!A:Z', 'Users!A:Z', 'Settings!A:Z'])
    
    def to_df(idx):
        vals = res['valueRanges'][idx].get('values', [])
        if not vals: return pd.DataFrame()
        cols = [re.sub(r'\s*\([A-Z]\)', '', str(h)).strip() for h in vals[0]]
        return pd.DataFrame(vals[1:], columns=cols)

    dfs = {k: to_df(i) for i, k in enumerate(['tasks', 'rewards', 'history', 'users', 'settings'])}
    
    # Type conversion for easier math later
    if not dfs['users'].empty:
        dfs['users'][['Points', 'XP', 'Streak']] = dfs['users'][['Points', 'XP', 'Streak']].apply(pd.to_numeric, errors='coerce').fillna(0)
        dfs['users'].set_index('Name', inplace=True, drop=False)
    
    settings = dict(zip(dfs['settings']['Setting'], dfs['settings']['Value'])) if not dfs['settings'].empty else {}
    return dfs, settings

def update_entry(sheet, search_val, col_idx, new_val, append_data=None):
    ws = get_sh().worksheet(sheet)
    if append_data: ws.append_row(append_data)
    else:
        try: 
            cell = ws.find(str(search_val), in_column=1)
            ws.update_cell(cell.row, col_idx, new_val)
        except: pass

def get_level(xp):
    lvl = int((xp ** 0.5) / 2) + 1 if xp > 0 else 1
    titles = {1:"Rookie 🌱", 2:"Scout 🔭", 3:"Adventurer 🎒", 4:"Warrior ⚔️", 5:"Knight 🛡️", 6:"Ninja 🥷", 7:"Master 🧘", 8:"Champion 🏆", 9:"Legend 👑"}
    return lvl, titles.get(lvl, "Cosmic 🌌")

# --- UI ---
def main():
    st.set_page_config(page_title="Khanna Family Quest", page_icon="🛡️", layout="centered")
    st.markdown("""<style>
        div.stButton > button { width: 100%; border-radius: 8px; font-weight: bold; height: 2.5em !important; }
        .stat-box { background: #262730; border: 1px solid #464b59; border-radius: 10px; padding: 10px; text-align: center; color: white; }
        .stat-val { font-size: 1.2rem; font-weight: bold; margin: 0; }
        .stat-lbl { font-size: 0.8rem; color: #aaa; margin: 0; }
        </style>""", unsafe_allow_html=True)

    try: dfs, settings = load_data()
    except Exception as e: st.error(f"DB Error: {e}"); st.stop()

    # Auth
    mgr = stx.CookieManager()
    if 'user' not in st.session_state:
        c_user = mgr.get("active_user")
        st.session_state['user'] = c_user if c_user in dfs['users'].index else None

    if not st.session_state['user']:
        st.title("🛡️ Login")
        u = st.selectbox("Hero", dfs['users'].index.tolist())
        if st.button("Enter", type="primary") and st.text_input("PIN", type="password") == str(dfs['users'].loc[u, 'Pin']):
            st.session_state['user'] = u
            mgr.set("active_user", u, expires_at=datetime.now() + timedelta(days=30))
            st.rerun()
        return

    # User Context
    user = st.session_state['user']
    u_dat = dfs['users'].loc[user]
    lvl, title = get_level(u_dat['XP'])
    
    # Header
    c1, c2 = st.columns([3, 1])
    c1.markdown(f"### {user} <small>({title})</small>", unsafe_allow_html=True)
    if c2.button("Log out"): mgr.delete("active_user"); st.session_state['user'] = None; st.rerun()

    # Stats Strip
    cols = st.columns(3)
    for c, icon, val, lbl in zip(cols, ["💰","🔥","⚔️"], [u_dat['Points'], int(u_dat['Streak']), lvl], ["Gold", "Streak", "Level"]):
        c.markdown(f"<div class='stat-box'><div class='stat-val'>{icon} {val:g}</div><div class='stat-lbl'>{lbl}</div></div>", unsafe_allow_html=True)

    # Global Goal
    cur, tgt = float(settings.get('Family_Goal_Current', 0)), float(settings.get('Family_Goal_Target', 2000))
    st.progress(min(cur/tgt, 1.0), text=f"🌍 {settings.get('Family_Goal_Title', 'Goal')} ({cur:g}/{tgt:g})")

    t1, t2, t3, t4 = st.tabs(["⚔️ Quests", "🎁 Loot", "🏆 Fame", "⚙️ Admin"])

    with t1: # Quests
        # Filter Logic: Using Pandas Vectorization (Much faster than loops)
        h_df = dfs['history']
        today = datetime.now().strftime("%Y-%m-%d")
        # Get list of tasks completed today by this user
        done_today = h_df[(h_df['User'] == user) & (h_df['Date'].str.contains(today))]['Item'].tolist()
        
        for _, t in dfs['tasks'].iterrows():
            if t['Status'] == 'Active' and (user in t['Assignee'] or "Any" in t['Assignee']):
                is_done = t['Title'] in done_today
                if t['Frequency'] == "Twice Daily": # PM check logic
                    is_done = (done_today.count(t['Title']) >= 2) or (datetime.now().hour < 16 and done_today.count(t['Title']) >= 1)

                if not is_done:
                    with st.container(border=True):
                        c_txt, c_btn = st.columns([3, 1])
                        c_txt.write(f"**{t['Title']}** ({t['Points']} pts)")
                        if c_btn.button("Done", key=t['ID']):
                            mult = 1.5 if u_dat['Streak'] >= 7 else (1.2 if u_dat['Streak'] >= 3 else 1.0)
                            pts = float(t['Points']) * mult
                            
                            # Streak Update Logic
                            ws_u = get_sh().worksheet("Users")
                            u_row = ws_u.find(user, in_column=1).row
                            new_strk = int(u_dat['Streak'])
                            if u_dat['Last_Active'] != today:
                                new_strk = new_strk + 1 if u_dat['Last_Active'] == (datetime.now()-timedelta(days=1)).strftime("%Y-%m-%d") else 1
                                ws_u.update_cell(u_row, 6, today) # Update Date
                            
                            ws_u.update_cell(u_row, 4, u_dat['Points'] + pts) # Points
                            ws_u.update_cell(u_row, 5, new_strk) # Streak
                            ws_u.update_cell(u_row, 8, u_dat['XP'] + pts) # XP
                            
                            update_entry("History", "", 0, "", [datetime.now().strftime("%Y-%m-%d %H:%M"), user, "Quest", t['Title'], pts])
                            update_entry("Settings", "Family_Goal_Current", 2, cur + pts)
                            if t['Frequency'] == "One-time": update_entry("Tasks", t['ID'], 6, "Completed")
                            
                            st.toast(f"+{pts:g} Gold!"); time.sleep(1); st.rerun()

        with st.expander("💡 Propose Quest"):
            with st.form("new_q"):
                if st.form_submit_button("Submit") and (title := st.text_input("Title")):
                    update_entry("Tasks", "", 0, "", [int(time.time()), title, st.number_input("Pts", 1.0), user, "One-time", "Pending Approval"])
                    st.success("Sent!"); st.rerun()

    with t2: # Loot
        st.markdown("### ❓ Mystery Box (15g)")
        if st.button("Open Box", disabled=u_dat['Points'] < 15):
            prize = random.choice([5, 10, 15, 20, 50])
            ws = get_sh().worksheet("Users"); row = ws.find(user, in_column=1).row
            ws.update_cell(row, 4, u_dat['Points'] - 15 + prize)
            update_entry("History", "", 0, "", [datetime.now().strftime("%Y-%m-%d %H:%M"), user, "Mystery Box", f"Won {prize}", prize-15])
            st.balloons() if prize > 15 else st.info(f"Won {prize}"); time.sleep(2); st.rerun()

        for _, r in dfs['rewards'].iterrows():
            if r['Status'] == 'Approved':
                with st.container(border=True):
                    c1, c2 = st.columns([3,1])
                    c1.write(f"**{r['Title']}** ({r['Cost']} pts)")
                    if c2.button("Buy", key=r['ID'], disabled=u_dat['Points'] < float(r['Cost'])):
                        ws = get_sh().worksheet("Users"); row = ws.find(user, in_column=1).row
                        ws.update_cell(row, 4, u_dat['Points'] - float(r['Cost']))
                        update_entry("History", "", 0, "", [datetime.now().strftime("%Y-%m-%d %H:%M"), user, "Reward", r['Title'], -float(r['Cost'])])
                        st.snow(); st.rerun()

    with t3: # Fame
        for n, row in dfs['users'].sort_values('XP', ascending=False).iterrows():
            lv, ti = get_level(row['XP'])
            st.info(f"**{n}** ({ti} Lvl {lv}) - {row['Points']:g} pts | 🔥 {int(row['Streak'])}")

    with t4: # Admin
        if u_dat['role'] == 'admin':
            if st.button("🔄 Sync XP"):
                # One-liner to sum points from history using Pandas groupby
                xp_map = dfs['history'].copy(); xp_map['Points'] = pd.to_numeric(xp_map['Points_Change'], errors='coerce')
                totals = xp_map.groupby('User')['Points'].sum().to_dict()
                ws = get_sh().worksheet("Users"); rows = ws.get_all_values()
                for i, r in enumerate(rows[1:], 2):
                    if r[0] in totals: ws.update_cell(i, 8, max(0, totals[r[0]]))
                st.success("Synced!"); time.sleep(1); st.rerun()
                
            st.write("#### Approvals")
            pend_t = dfs['tasks'][dfs['tasks']['Status'] == "Pending Approval"]
            for _, t in pend_t.iterrows():
                c1, c2, c3 = st.columns([2,1,1])
                c1.write(f"{t['Title']} ({t['Points']})")
                if c2.button("✅", key=f"ok_{t['ID']}"): update_entry("Tasks", t['ID'], 6, "Active"); st.rerun()
                if c3.button("❌", key=f"no_{t['ID']}"): update_entry("Tasks", t['ID'], 6, "Rejected"); st.rerun()

if __name__ == "__main__": main()
