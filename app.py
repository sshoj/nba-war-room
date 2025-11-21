import streamlit as st
import requests
from langchain_openai import ChatOpenAI
import os
import pandas as pd
from datetime import datetime, timedelta
import difflib 

# --- PAGE CONFIGURATION ---
st.set_page_config(page_title="NBA War Room (Secure)", page_icon="🔒", layout="wide")
st.title("🏀 NBA War Room (Secure Edition)")
st.markdown("**Tier:** All-Star | **Auth:** Streamlit Secrets | **Coach:** GPT-4o")

# --- SECURE AUTHENTICATION ---
def load_keys():
    """
    Prioritizes secrets.toml, falls back to sidebar input.
    """
    keys = {}
    
    # 1. BallDontLie Key
    if "BDL_API_KEY" in st.secrets:
        keys["bdl"] = st.secrets["BDL_API_KEY"]
        st.sidebar.success("✅ BDL Key Loaded")
    else:
        keys["bdl"] = st.sidebar.text_input("BallDontLie Key", type="password")

    # 2. OpenAI Key
    if "OPENAI_API_KEY" in st.secrets:
        keys["openai"] = st.secrets["OPENAI_API_KEY"]
        st.sidebar.success("✅ OpenAI Key Loaded")
    else:
        keys["openai"] = st.sidebar.text_input("OpenAI Key", type="password")

    # Set Environment Variables for tools to use globally
    if keys["bdl"]: os.environ["BDL_API_KEY"] = keys["bdl"].strip()
    if keys["openai"]: os.environ["OPENAI_API_KEY"] = keys["openai"].strip()
    
    return keys

# --- SIDEBAR ---
with st.sidebar:
    st.header("⚙️ Settings")
    # Load keys securely
    api_keys = load_keys()
    
    st.divider()
    if st.button("New Search / Clear"):
        st.session_state.analysis_data = None
        st.session_state.messages = []
        st.rerun()

# --- SESSION STATE SETUP ---
if "messages" not in st.session_state:
    st.session_state.messages = []
if "analysis_data" not in st.session_state:
    st.session_state.analysis_data = None

# --- API CONFIG ---
BASE_URL = "https://api.balldontlie.io/v1"

def get_headers():
    return {"Authorization": os.environ.get("BDL_API_KEY")}

# --- TOOLS ---

def get_player_info_smart(user_input):
    """Smart Search V2: Handles typos (Trigram method)"""
    try:
        # 1. Split input into words
        words = user_input.split()
        candidates = {} 
        
        # 2. Broad Search
        search_terms = set(words)
        for w in words:
            if len(w) >= 3: search_terms.add(w[:3])
        
        for term in search_terms:
            r = requests.get(url=f"{BASE_URL}/players", headers=get_headers(), params={"search": term, "per_page": 10})
            if r.status_code == 200:
                for p in r.json().get('data', []):
                    candidates[p['id']] = p
        
        if not candidates: return None, f"Player '{user_input}' not found."
        
        # 3. Fuzzy Match
        candidate_list = list(candidates.values())
        candidate_names = [f"{c['first_name']} {c['last_name']}" for c in candidate_list]
        best_matches = difflib.get_close_matches(user_input, candidate_names, n=1, cutoff=0.4)
        
        if best_matches:
            target_name = best_matches[0]
            p = next(c for c in candidate_list if f"{c['first_name']} {c['last_name']}" == target_name)
            return p, f"Found: **{target_name}** (Corrected from '{user_input}')"
            
        return None, "No close matches found."

    except Exception as e: return None, f"Search Error: {e}"

def get_team_injuries(team_id):
    """Fetches official injury report with crash protection."""
    try:
        url = f"{BASE_URL}/player_injuries"
        resp = requests.get(url, headers=get_headers(), params={"team_ids[]": str(team_id)})
        data = resp.json().get('data', [])
        if not data: return "No active injuries."
        
        reports = []
        for i in data:
            p_obj = i.get('player') or {}
            p_name = f"{p_obj.get('first_name','')} {p_obj.get('last_name','')}"
            status = i.get('status', 'Unknown')
            note = i.get('note') or i.get('comment') or i.get('description') or "No details"
            reports.append(f"- **{p_name}**: {status} ({note})")
        return "\n".join(reports)
    except: return "Error fetching injuries."

def get_team_schedule_before_today(team_id):
    """Fetches TEAM'S last 5 finished games"""
    try:
        url = f"{BASE_URL}/games"
        today = datetime.now().strftime("%Y-%m-%d")
        params = {"team_ids[]": str(team_id), "seasons[]": "2025", "end_date": today, "per_page": "20"}
        resp = requests.get(url, headers=get_headers(), params=params)
        data = resp.json().get('data', [])
        finished = [g for g in data if g.get('status') == "Final"]
        finished.sort(key=lambda x: x['date'], reverse=True)
        return finished[:5]
    except: return []

def get_next_game(team_id):
    """Finds next scheduled game"""
    try:
        url = f"{BASE_URL}/games"
        today = datetime.now().strftime("%Y-%m-%d")
        future = (datetime.now() + timedelta(days=14)).strftime("%Y-%m-%d")
        params = {"team_ids[]": str(team_id), "seasons[]": "2025", "start_date": today, "end_date": future, "per_page": "10"}
        resp = requests.get(url, headers=get_headers(), params=params)
        data = resp.json().get('data', [])
        if not data: return None, "No games found.", None, None
        
        data.sort(key=lambda x: x['date'])
        game = next((g for g in data if g['status'] != "Final"), None)
        if not game: return None, "No upcoming games.", None, None
        
        home = game.get('home_team', {})
        visitor = game.get('visitor_team', {})
        
        if home.get('id') == team_id:
            opp = visitor
            loc = "vs"
        else:
            opp = home
            loc = "@"
            
        return f"{loc} {opp.get('full_name', 'Unknown')}", game['date'].split("T")[0], opp.get('id'), opp.get('full_name')
    except: return None, "Error", None, None

def get_stats_for_specific_games(player_id, game_ids):
    if not game_ids: return []
    try:
        url = f"{BASE_URL}/stats"
        params = {"player_ids[]": str(player_id), "per_page": "10", "game_ids[]": [str(g) for g in game_ids]}
        resp = requests.get(url, headers=get_headers(), params=params)
        return resp.json().get('data', [])
    except: return []

# --- MAIN APP LOGIC ---
# Check if keys exist (either from secrets OR input)
if api_keys["bdl"] and api_keys["openai"]:
    
    llm = ChatOpenAI(model="gpt-4o", temperature=0.5, api_key=api_keys["openai"])
    
    col1, col2 = st.columns([3, 1])
    with col1:
        p_name = st.text_input("Player Name", "Luka Doncic")
    with col2:
        st.write("") 
        st.write("")
        run_btn = st.button("🚀 Run Analysis", type="primary", use_container_width=True)

    # --- PROCESS DATA ---
    if run_btn:
        status_box = st.status("🔍 Scouting in progress...", expanded=True)
        
        try:
            # 1. Smart Player Search
            status_box.write("Finding player (Auto-Correcting)...")
            res_obj, msg = get_player_info_smart(p_name)
            
            if not res_obj:
                status_box.update(label="Search Failed", state="error")
                st.error(msg)
                st.stop()
            
            st.success(msg)
            pid = res_obj['id']
            fname = res_obj['first_name']
            lname = res_obj['last_name']
            tid = res_obj['team']['id']
            tname = res_obj['team']['full_name']
            
            # 2. Schedule
            status_box.write("Checking schedule...")
            opp_str, date, opp_id, opp_name = get_next_game(tid)
            if not opp_str: opp_name = "Unknown"
            
            # 3. Injuries
            status_box.write("Fetching injuries...")
            inj_home = get_team_injuries(tid) if tid else "N/A"
            inj_opp = get_team_injuries(opp_id) if opp_id else "N/A"
            
            # 4. Stats
            status_box.write("Crunching stats...")
            past_games = get_team_schedule_before_today(tid)
            gids = [g['id'] for g in past_games]
            p_stats = get_stats_for_specific_games(pid, gids)
            
            log_lines = []
            for g in past_games:
                gid = g['id']
                d = g['date'].split("T")[0]
                
                home = g.get('home_team', {})
                visitor = g.get('visitor_team', {})
                
                if home.get('id') == tid:
                    opp_abbr = visitor.get('abbreviation', 'UNK')
                    loc = "vs"
                else:
                    opp_abbr = home.get('abbreviation', 'UNK')
                    loc = "@"
                
                stat = next((s for s in p_stats if s['game']['id'] == gid), None)
                if stat and stat.get('min'):
                    fg = f"{stat['fg_pct']*100:.0f}%" if stat.get('fg_pct') else "0%"
                    fg3 = f"{stat.get('fg3m', 0)}/{stat.get('fg3a', 0)}"
                    line = f"MIN:{stat.get('min')} | PTS:{stat.get('pts',0)} REB:{stat.get('reb',0)} AST:{stat.get('ast',0)} | FG:{fg} 3PT:{fg3}"
                else:
                    line = "❌ OUT (DNP)"
                log_lines.append(f"[{d}] {loc} {opp_abbr} | {line}")
            
            final_log = "\n".join(log_lines)
            
            # 5. AI Analysis
            status_box.write("Consulting GPT-4o...")
            prompt = f"""
            Role: NBA Expert.
            Player: {fname} {lname} ({tname})
            Matchup: {opp_str} ({date})
            
            OFFICIAL INJURY REPORT:
            - {tname}: {inj_home}
            - {opp_name}: {inj_opp}
            
            RECENT GAMES (2025 Season):
            {final_log}
            
            Tasks:
            1. **Health/Load:** Analyze minutes & DNPs. Is he fresh?
            2. **Performance:** Check FG% and 3PT volume.
            3. **Impact:** How do injuries (on both teams) affect him?
            4. **Prediction:** Project PTS/REB/AST.
            """
            analysis = llm.invoke(prompt).content
            
            # 6. Save & Refresh
            st.session_state.analysis_data = {
                "player": f"{fname} {lname}",
                "team": tname,
                "matchup": opp_str,
                "date": date,
                "inj_home": inj_home,
                "inj_opp": inj_opp,
                "log": final_log,
                "analysis": analysis,
                "context": prompt + "\n\nPrediction:\n" + analysis
            }
            
            st.session_state.messages = [{"role": "assistant", "content": analysis}]
            status_box.update(label="Analysis Complete!", state="complete", expanded=False)
            st.rerun()
            
        except Exception as e:
            status_box.update(label="System Error", state="error")
            st.error(f"Error: {e}")

    # --- DISPLAY ---
    data = st.session_state.analysis_data
    
    if data:
        st.divider()
        st.markdown(f"### 📊 Report: {data['player']} {data['matchup']}")
        st.caption(f"Date: {data['date']}")
        
        c1, c2 = st.columns(2)
        with c1:
            st.info(f"**{data['team']} Injuries:**\n\n{data['inj_home']}")
        with c2:
            st.error(f"**Opponent Injuries:**\n\n{data['inj_opp']}")
            
        with st.expander("View Verified Game Log", expanded=True):
            st.code(data['log'])
            
        st.write("### 🧠 Coach's Prediction")
        st.write(data['analysis'])
        
        st.divider()
        st.subheader("💬 Chat with the Scout")
        
        for msg in st.session_state.messages:
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])
                
        if user_input := st.chat_input("Ask follow-up..."):
            with st.chat_message("user"):
                st.markdown(user_input)
            st.session_state.messages.append({"role": "user", "content": user_input})
            
            with st.chat_message("assistant"):
                with st.spinner("Thinking..."):
                    full_context = f"CONTEXT:\n{data['context']}\n\nUSER ASKED: {user_input}"
                    response = llm.invoke(full_context).content
                    st.markdown(response)
            st.session_state.messages.append({"role": "assistant", "content": response})

else:
    st.warning("⚠️ Keys missing! Check your secrets.toml or enter them in the sidebar.")
