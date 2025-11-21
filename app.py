import streamlit as st
import requests
from langchain_openai import ChatOpenAI
import os
import pandas as pd
from datetime import datetime, timedelta
import difflib  # Built-in library for fuzzy matching

# --- PAGE CONFIGURATION ---
st.set_page_config(page_title="NBA War Room (All-Star)", page_icon="⭐", layout="wide")
st.title("🏀 NBA War Room (All-Star Edition)")
st.markdown("**Tier:** All-Star (Official API) | **Features:** Smart Search + Deep Stats + Chat")

# --- SIDEBAR: SETTINGS ---
with st.sidebar:
    st.header("⚙️ Settings")
    bdl_key = st.text_input("BallDontLie API Key", type="password")
    st.caption("Must be All-Star Tier (starts with 'fc...')")
    openai_key = st.text_input("OpenAI API Key", type="password")
    
    if bdl_key: os.environ["BDL_API_KEY"] = bdl_key.strip()
    if openai_key: os.environ["OPENAI_API_KEY"] = openai_key.strip()
    
    st.divider()
    # Clear Button to reset the view
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
    """
    Smart Search: Handles typos (e.g. 'Luca Donicic' -> 'Luka Doncic')
    Returns: (id, first_name, last_name, team_id, team_name)
    """
    try:
        # 1. Try Exact Search first
        url = f"{BASE_URL}/players"
        resp = requests.get(url, headers=get_headers(), params={"search": user_input, "per_page": 5})
        data = resp.json().get('data', [])
        
        # 2. If empty, try "Fuzzy Search"
        if not data:
            # Split input into words (e.g. "Luca", "Donicic")
            words = user_input.split()
            candidates = []
            
            # Search API for each word individually
            for word in words:
                if len(word) > 2: # Skip short words
                    r = requests.get(url, headers=get_headers(), params={"search": word, "per_page": 5})
                    candidates.extend(r.json().get('data', []))
            
            if not candidates: return None
            
            # Use Python's difflib to find best string match
            candidate_names = [f"{c['first_name']} {c['last_name']}" for c in candidates]
            best_match_name = difflib.get_close_matches(user_input, candidate_names, n=1, cutoff=0.4)
            
            if best_match_name:
                # Retrieve the object belonging to that name
                target_name = best_match_name[0]
                data = [c for c in candidates if f"{c['first_name']} {c['last_name']}" == target_name]
            else:
                return None

        # Return the best match data
        p = data[0]
        return p['id'], p['first_name'], p['last_name'], p['team']['id'], p['team']['full_name']
        
    except Exception: return None

def get_team_injuries(team_id):
    """
    [ALL-STAR EXCLUSIVE] Fetches official injury report with crash protection.
    """
    try:
        url = f"{BASE_URL}/player_injuries"
        params = {"team_ids[]": str(team_id)}
        resp = requests.get(url, headers=get_headers(), params=params)
        
        if resp.status_code != 200: return f"API Error {resp.status_code}"
        data = resp.json().get('data', [])
        
        if not data: return "No active injuries reported."
        
        reports = []
        for i in data:
            # Safe extraction to prevent crashes
            p_obj = i.get('player') or {}
            p_name = f"{p_obj.get('first_name','')} {p_obj.get('last_name','')}"
            status = i.get('status', 'Unknown')
            # Check multiple fields for the injury details
            note = i.get('note') or i.get('comment') or i.get('description') or "No details"
            reports.append(f"- **{p_name}**: {status} ({note})")
            
        return "\n".join(reports)
    except Exception as e:
        return f"Error fetching injuries: {e}"

def get_team_schedule_before_today(team_id):
    """Fetches TEAM'S last 5 finished games (2025 Season)"""
    try:
        url = f"{BASE_URL}/games"
        today = datetime.now().strftime("%Y-%m-%d")
        # We use '2025' for the 2025-26 season
        params = {"team_ids[]": str(team_id), "seasons[]": "2025", "end_date": today, "per_page": "20"}
        resp = requests.get(url, headers=get_headers(), params=params)
        data = resp.json().get('data', [])
        
        # Filter for Final games only
        finished = [g for g in data if g.get('status') == "Final"]
        # Sort newest first
        finished.sort(key=lambda x: x['date'], reverse=True)
        return finished[:5]
    except: return []

def get_next_game(team_id):
    """Finds the next scheduled game and opponent"""
    try:
        url = f"{BASE_URL}/games"
        today = datetime.now().strftime("%Y-%m-%d")
        future = (datetime.now() + timedelta(days=14)).strftime("%Y-%m-%d")
        params = {"team_ids[]": str(team_id), "seasons[]": "2025", "start_date": today, "end_date": future, "per_page": "5"}
        resp = requests.get(url, headers=get_headers(), params=params)
        data = resp.json().get('data', [])
        if not data: return None, "No games found.", None, None
        
        data.sort(key=lambda x: x['date'])
        game = data[0]
        
        home = game.get('home_team', {})
        visitor = game.get('visitor_team', {})
        
        # Determine opponent
        if home.get('id') == team_id:
            opp = visitor
            loc = "vs"
        else:
            opp = home
            loc = "@"
            
        return f"{loc} {opp.get('full_name', 'Unknown')}", game['date'].split("T")[0], opp.get('id'), opp.get('full_name')
    except: return None, "Error", None, None

def get_stats_for_specific_games(player_id, game_ids):
    """Fetches stats for specific Game IDs"""
    if not game_ids: return []
    try:
        url = f"{BASE_URL}/stats"
        # We request specific game IDs to match the schedule
        params = {"player_ids[]": str(player_id), "per_page": "10", "game_ids[]": [str(g) for g in game_ids]}
        resp = requests.get(url, headers=get_headers(), params=params)
        return resp.json().get('data', [])
    except: return []

# --- MAIN APP LOGIC ---
if bdl_key and openai_key:
    
    llm = ChatOpenAI(model="gpt-4o", temperature=0.5, api_key=openai_key)
    
    col1, col2 = st.columns([3, 1])
    with col1:
        p_name = st.text_input("Player Name", "Luca Donicic") # Default with typo to test
    with col2:
        st.write("") 
        st.write("")
        run_btn = st.button("🚀 Run Analysis", type="primary", use_container_width=True)

    # --- PROCESS DATA (On Click) ---
    if run_btn:
        status_box = st.status("🔍 Scouting in progress...", expanded=True)
        
        try:
            # 1. Player Info (Smart Search)
            status_box.write("Finding player (Auto-Correcting)...")
            res = get_player_info_smart(p_name)
            if not res:
                status_box.update(label="Player not found!", state="error")
                st.stop()
            pid, fname, lname, tid, tname = res
            
            # 2. Schedule & Opponent
            status_box.write("Checking schedule...")
            opp_str, date, opp_id, opp_name = get_next_game(tid)
            if not opp_str: opp_name = "Unknown"
            
            # 3. Injuries (Official API)
            status_box.write("Fetching Official Injury Reports...")
            inj_home = get_team_injuries(tid) if tid else "N/A"
            inj_opp = get_team_injuries(opp_id) if opp_id else "N/A"
            
            # 4. Deep Stats & DNPs
            status_box.write("Crunching Deep Stats...")
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
                
                # Match Player Stat to Game
                stat = next((s for s in p_stats if s['game']['id'] == gid), None)
                
                if stat and stat.get('min'):
                    # Deep Stats Formatting
                    fg_pct = f"{stat['fg_pct']*100:.0f}%" if stat.get('fg_pct') else "0%"
                    fg3_str = f"{stat.get('fg3m', 0)}/{stat.get('fg3a', 0)}"
                    min_ply = stat.get('min')
                    
                    line = (f"MIN:{min_ply} | PTS:{stat.get('pts',0)} REB:{stat.get('reb',0)} AST:{stat.get('ast',0)} | "
                            f"FG:{fg_pct} 3PT:{fg3_str}")
                else:
                    line = "❌ OUT (DNP)"
                    
                log_lines.append(f"[{d}] {loc} {opp_abbr} | {line}")
            
            final_log = "\n".join(log_lines)
            
            # 5. GPT Analysis
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
            
            # 6. SAVE TO STATE & REFRESH
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
            
            # Initialize chat with the report
            st.session_state.messages = [{"role": "assistant", "content": analysis}]
            
            status_box.update(label="Analysis Complete!", state="complete", expanded=False)
            st.rerun() # Forces the UI to update immediately
            
        except Exception as e:
            status_box.update(label="System Error", state="error")
            st.error(f"Error details: {e}")

    # --- DISPLAY RESULTS (Persistent) ---
    data = st.session_state.analysis_data
    
    if data:
        st.divider()
        st.markdown(f"### 📊 Report: {data['player']} {data['matchup']}")
        st.caption(f"Date: {data['date']}")
        
        c1, c2 = st.columns(2)
        with c1:
            st.info(f"**🏥 {data['team']} Injuries:**\n\n{data['inj_home']}")
        with c2:
            st.error(f"**🏥 Opponent Injuries:**\n\n{data['inj_opp']}")
            
        with st.expander("View Verified Game Log (Min/3PT/FG%)", expanded=True):
            st.code(data['log'])
            
        st.write("### 🧠 Coach's Prediction")
        st.write(data['analysis'])
        
        # --- CHAT SECTION ---
        st.divider()
        st.subheader("💬 Chat with the Scout")
        
        for msg in st.session_state.messages:
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])
                
        if user_input := st.chat_input("Ask follow-up (e.g. 'Is he a risky bet?')"):
            with st.chat_message("user"):
                st.markdown(user_input)
            st.session_state.messages.append({"role": "user", "content": user_input})
            
            with st.chat_message("assistant"):
                with st.spinner("Thinking..."):
                    full_context = f"CONTEXT:\n{data['context']}\n\nUSER ASKED: {user_input}"
                    response = llm.invoke(full_context).content
                    st.markdown(response)
            st.session_state.messages.append({"role": "assistant", "content": response})

elif not bdl_key:
    st.warning("⚠️ Please enter API Keys.")
