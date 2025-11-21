import streamlit as st
import requests
from langchain_openai import ChatOpenAI
import os
import pandas as pd
from datetime import datetime, timedelta
import difflib # Standard library for fuzzy matching

# --- PAGE CONFIGURATION ---
st.set_page_config(page_title="NBA War Room (All-Star)", page_icon="⭐", layout="wide")
st.title("🏀 NBA War Room (All-Star Edition)")
st.markdown("**Tier:** All-Star (Official API) | **Features:** Smart Search + Deep Stats + Chat")

# --- SIDEBAR: SETTINGS ---
with st.sidebar:
    st.header("⚙️ Settings")
    bdl_key = st.text_input("BallDontLie API Key", type="password")
    openai_key = st.text_input("OpenAI API Key", type="password")
    
    if bdl_key: os.environ["BDL_API_KEY"] = bdl_key.strip()
    if openai_key: os.environ["OPENAI_API_KEY"] = openai_key.strip()
    
    st.divider()
    if st.button("New Search / Clear"):
        st.session_state.analysis_data = None
        st.session_state.messages = []
        st.rerun()

# --- SESSION STATE ---
if "messages" not in st.session_state:
    st.session_state.messages = []
if "analysis_data" not in st.session_state:
    st.session_state.analysis_data = None

# --- API CONFIG ---
BASE_URL = "https://api.balldontlie.io/v1"

def get_headers():
    return {"Authorization": os.environ.get("BDL_API_KEY")}

# --- SMART TOOLS ---

def get_player_info_smart(user_input):
    """
    Smart Search: Handles typos (e.g. 'Luca Donicic' -> 'Luka Doncic')
    """
    try:
        # 1. Try Exact Search
        url = f"{BASE_URL}/players"
        resp = requests.get(url, headers=get_headers(), params={"search": user_input, "per_page": 5})
        data = resp.json()['data']
        
        # 2. If empty, try "Fuzzy Search"
        if not data:
            # Split "Luca Donicic" -> ["Luca", "Donicic"]
            words = user_input.split()
            candidates = []
            
            # Search API for each word individually
            for word in words:
                if len(word) > 2: # Skip short words
                    r = requests.get(url, headers=get_headers(), params={"search": word, "per_page": 5})
                    candidates.extend(r.json()['data'])
            
            if not candidates: return None, f"Player '{user_input}' not found."
            
            # Use Python's difflib to find best string match
            # We compare full names
            candidate_names = [f"{c['first_name']} {c['last_name']}" for c in candidates]
            best_match_name = difflib.get_close_matches(user_input, candidate_names, n=1, cutoff=0.4)
            
            if best_match_name:
                # Find the object belonging to that name
                target_name = best_match_name[0]
                data = [c for c in candidates if f"{c['first_name']} {c['last_name']}" == target_name]
            else:
                return None, f"Player '{user_input}' not found. Did you mean {candidate_names[0]}?"

        # Return the best match
        p = data[0]
        full_name = f"{p['first_name']} {p['last_name']}"
        return p, f"Found: **{full_name}** ({p['team']['full_name']})"
        
    except Exception as e: return None, f"Search Error: {e}"

def get_next_game(team_id):
    """Finds the NEXT scheduled game (ignoring finished ones)"""
    try:
        url = f"{BASE_URL}/games"
        today = datetime.now().strftime("%Y-%m-%d")
        
        # Look ahead 30 days to be safe
        future = (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d")
        
        params = {
            "team_ids[]": str(team_id),
            "seasons[]": "2025",
            "start_date": today,
            "end_date": future,
            "per_page": "20"
        }
        resp = requests.get(url, headers=get_headers(), params=params)
        data = resp.json()['data']
        
        if not data: return None, "No games scheduled soon.", None, None
        
        # Sort by Date (Ascending)
        data.sort(key=lambda x: x['date'])
        
        # Logic: Return the first game that is NOT "Final"
        # This catches games happening TODAY that haven't finished yet
        for game in data:
            status = game['status'].strip()
            if status != "Final":
                # Found it!
                date_str = game['date'].split("T")[0]
                if game['home_team']['id'] == team_id:
                    opp = game['visitor_team']
                    loc = "vs"
                else:
                    opp = game['home_team']
                    loc = "@"
                
                return f"{loc} {opp['full_name']}", f"{date_str} ({status})", opp['id'], opp['full_name']
        
        return None, "No upcoming games found (Season ended?)", None, None
    except: return None, "Error finding schedule", None, None

def get_team_injuries(team_id):
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
    try:
        url = f"{BASE_URL}/games"
        today = datetime.now().strftime("%Y-%m-%d")
        # Get last 20 games to ensure we have enough 'Final' ones
        params = {"team_ids[]": str(team_id), "seasons[]": "2025", "end_date": today, "per_page": "20"}
        resp = requests.get(url, headers=get_headers(), params=params)
        data = resp.json()['data']
        finished = [g for g in data if g['status'] == "Final"]
        finished.sort(key=lambda x: x['date'], reverse=True)
        return finished[:5]
    except: return []

def get_stats_for_specific_games(player_id, game_ids):
    if not game_ids: return []
    try:
        url = f"{BASE_URL}/stats"
        params = {"player_ids[]": str(player_id), "per_page": "10", "game_ids[]": [str(g) for g in game_ids]}
        resp = requests.get(url, headers=get_headers(), params=params)
        return resp.json()['data']
    except: return []

# --- MAIN APP LOGIC ---
if bdl_key and openai_key:
    
    llm = ChatOpenAI(model="gpt-4o", temperature=0.5, api_key=openai_key)
    
    col1, col2 = st.columns([3, 1])
    with col1:
        p_name = st.text_input("Player Name", "Luca Donicic") # Example typo
    with col2:
        st.write("") 
        st.write("")
        run_btn = st.button("🚀 Run Analysis", type="primary", use_container_width=True)

    if run_btn:
        status_box = st.status("🔍 Smart Search Active...", expanded=True)
        
        try:
            # 1. Smart Player Search
            status_box.write("Finding player (Auto-Correcting)...")
            player_obj, msg = get_player_info_smart(p_name)
            
            if not player_obj:
                status_box.update(label="Search Failed", state="error")
                st.error(msg)
                st.stop()
            
            st.success(msg) # Show "Found: Luka Doncic"
            pid = player_obj['id']
            fname = player_obj['first_name']
            lname = player_obj['last_name']
            tid = player_obj['team']['id']
            tname = player_obj['team']['full_name']
            
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
                loc = "vs" if g['home_team']['id'] == tid else "@"
                opp = g['visitor_team']['abbreviation'] if loc == "vs" else g['home_team']['abbreviation']
                
                stat = next((s for s in p_stats if s['game']['id'] == gid), None)
                if stat and stat['min']:
                    fg = f"{stat['fg_pct']*100:.0f}%" if stat['fg_pct'] else "0%"
                    # Add 3PT
                    fg3 = f"{stat['fg3m']}/{stat['fg3a']}"
                    line = f"MIN:{stat['min']} | PTS:{stat['pts']} REB:{stat['reb']} AST:{stat['ast']} | FG:{fg} 3PT:{fg3}"
                else:
                    line = "❌ OUT (DNP)"
                log_lines.append(f"[{d}] {loc} {opp} | {line}")
            
            final_log = "\n".join(log_lines)
            
            # 5. AI Analysis
            status_box.write("Consulting GPT-4o...")
            prompt = f"""
            Role: NBA Expert.
            Player: {fname} {lname} ({tname})
            Matchup: {opp_str} ({date})
            
            Injuries:
            {tname}: {inj_home}
            {opp_name}: {inj_opp}
            
            Recent Games:
            {final_log}
            
            Tasks:
            1. Analyze form (FG%, 3PT shooting).
            2. Impact of injuries on this specific game.
            3. Predict stat line (PTS/REB/AST).
            """
            analysis = llm.invoke(prompt).content
            
            # 6. Save & Refresh
            st.session_state.analysis_data = {
                "player": f"{fname} {lname}",
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
            st.info(f"**{data['player'].split()[-1]}'s Team Injuries:**\n\n{data['inj_home']}")
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

elif not bdl_key:
    st.warning("⚠️ Please enter API Keys.")
