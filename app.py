import streamlit as st
import requests
from langchain_openai import ChatOpenAI
import os
import pandas as pd
from datetime import datetime, timedelta

# --- PAGE CONFIGURATION ---
st.set_page_config(page_title="NBA War Room (All-Star)", page_icon="⭐", layout="wide")
st.title("🏀 NBA War Room (All-Star Edition)")
st.markdown("**Tier:** All-Star (Official API) | **Features:** Live Stats + Official Injuries")

# --- SIDEBAR: SETTINGS ---
with st.sidebar:
    st.header("⚙️ Settings")
    bdl_key = st.text_input("BallDontLie API Key", type="password")
    st.caption("Must be All-Star Tier or higher")
    openai_key = st.text_input("OpenAI API Key", type="password")
    
    if bdl_key: os.environ["BDL_API_KEY"] = bdl_key.strip()
    if openai_key: os.environ["OPENAI_API_KEY"] = openai_key.strip()

# --- API CONFIG ---
BASE_URL = "https://api.balldontlie.io/v1"

def get_headers():
    return {"Authorization": os.environ.get("BDL_API_KEY")}

# --- ALL-STAR TOOLS ---

def get_team_injuries(team_id):
    """
    [ALL-STAR TIER EXCLUSIVE]
    Fetches official injury report with crash protection.
    """
    try:
        url = f"{BASE_URL}/player_injuries"
        params = {
            "team_ids[]": str(team_id)
        }
        resp = requests.get(url, headers=get_headers(), params=params)
        
        # Handle non-200 responses
        if resp.status_code != 200:
            return f"API Error {resp.status_code}"
            
        data = resp.json().get('data', [])
        
        if not data: return "No active injuries reported."
        
        reports = []
        for i in data:
            # 1. Safe Player Name Extraction
            player_data = i.get('player', {})
            player = f"{player_data.get('first_name', 'Unknown')} {player_data.get('last_name', '')}"
            
            # 2. Safe Status & Note Extraction (The Fix)
            # We use .get() so it never crashes if a field is missing
            status = i.get('status', 'Status Unknown')
            
            # Try multiple common keys for description just in case
            note = i.get('note') or i.get('comment') or i.get('description') or "No details"
            
            reports.append(f"- **{player}**: {status} ({note})")
            
        return "\n".join(reports)
        
    except Exception as e:
        return f"System Error fetching injuries: {e}"

def get_player_info(name):
    try:
        url = f"{BASE_URL}/players"
        params = {"search": name, "per_page": "1"}
        resp = requests.get(url, headers=get_headers(), params=params)
        data = resp.json()['data']
        if not data: return None, None, None, None, None
        p = data[0]
        return p['id'], p['first_name'], p['last_name'], p['team']['id'], p['team']['full_name']
    except: return None, None, None, None, None

def get_team_schedule_before_today(team_id):
    try:
        url = f"{BASE_URL}/games"
        today = datetime.now().strftime("%Y-%m-%d")
        params = {
            "team_ids[]": str(team_id),
            "seasons[]": "2025", 
            "end_date": today,
            "per_page": "20"
        }
        resp = requests.get(url, headers=get_headers(), params=params)
        data = resp.json()['data']
        finished_games = [g for g in data if g['status'] == "Final"]
        finished_games.sort(key=lambda x: x['date'], reverse=True)
        return finished_games[:5]
    except: return []

def get_next_game(team_id):
    try:
        url = f"{BASE_URL}/games"
        today = datetime.now().strftime("%Y-%m-%d")
        future = (datetime.now() + timedelta(days=14)).strftime("%Y-%m-%d")
        params = {
            "team_ids[]": str(team_id),
            "seasons[]": "2025",
            "start_date": today,
            "end_date": future,
            "per_page": "5"
        }
        resp = requests.get(url, headers=get_headers(), params=params)
        data = resp.json()['data']
        if not data: return None, "No games found.", None
        
        data.sort(key=lambda x: x['date'])
        game = data[0]
        
        # Determine Opponent ID for Injury Lookup
        if game['home_team']['id'] == team_id:
            opp_team = game['visitor_team']
            loc = "vs"
        else:
            opp_team = game['home_team']
            loc = "@"
            
        date_str = game['date'].split("T")[0]
        return f"{loc} {opp_team['full_name']}", date_str, opp_team['id'], opp_team['full_name']
    except: return None, "Error.", None, None

def get_stats_for_specific_games(player_id, game_ids):
    if not game_ids: return []
    try:
        url = f"{BASE_URL}/stats"
        params = {
            "player_ids[]": str(player_id),
            "per_page": "10",
            "game_ids[]": [str(g) for g in game_ids]
        }
        resp = requests.get(url, headers=get_headers(), params=params)
        return resp.json()['data']
    except: return []

# --- MAIN APP ---
if bdl_key and openai_key:
    
    llm = ChatOpenAI(model="gpt-4o", temperature=0.5, api_key=openai_key)
    
    col1, col2 = st.columns(2)
    with col1: p_name = st.text_input("Player Name", "Luka Doncic")
    
    today_display = datetime.now().strftime("%A, %B %d, %Y")
    st.caption(f"📅 Today: **{today_display}**")
    
    if st.button("🚀 RUN ALL-STAR ANALYSIS", type="primary"):
        with st.spinner("Accessing Official NBA Database..."):
            
            # 1. Player Info
            res = get_player_info(p_name)
            if not res or not res[0]:
                st.error("Player not found.")
                st.stop()
                
            pid, fname, lname, team_id, team_name = res
            st.success(f"Found: **{fname} {lname}** ({team_name})")
            
            # 2. Next Game (And Opponent ID)
            opp_str, date_next, opp_id, opp_real_name = get_next_game(team_id)
            
            if opp_str:
                st.info(f"🏀 **NEXT GAME:** {opp_str} | 📅 {date_next}")
            else:
                st.warning("No upcoming games found.")
                opp_real_name = "Unknown"

            # 3. OFFICIAL INJURY REPORT (All-Star Exclusive)
            st.write("---")
            col_a, col_b = st.columns(2)
            
            with col_a:
                st.subheader(f"🏥 {team_name}")
                if team_id:
                    injuries_home = get_team_injuries(team_id)
                    st.info(injuries_home)
                else:
                    st.write("No data.")

            with col_b:
                st.subheader(f"🏥 {opp_real_name}")
                if opp_id:
                    injuries_opp = get_team_injuries(opp_id)
                    st.error(injuries_opp)
                else:
                    st.write("No opponent data.")

            # 4. Past Games
            past_games = get_team_schedule_before_today(team_id)
            if not past_games:
                st.error("No recent games found.")
                st.stop()
                
            game_ids = [g['id'] for g in past_games]
            player_stats = get_stats_for_specific_games(pid, game_ids)
            
            # 5. Build Log
            log_lines = []
            for game in past_games:
                gid = game['id']
                date = game['date'].split("T")[0]
                
                if game['home_team']['id'] == team_id:
                    opp_team = game['visitor_team']
                    loc = "vs"
                else:
                    opp_team = game['home_team']
                    loc = "@"
                
                stat = next((s for s in player_stats if s['game']['id'] == gid), None)
                
                if stat and stat['min']:
                    fg_pct = f"{stat['fg_pct']*100:.1f}%" if stat['fg_pct'] else "0%"
                    line = (f"MIN:{stat['min']} | PTS:{stat['pts']} REB:{stat['reb']} AST:{stat['ast']} | "
                            f"FG:{fg_pct}")
                else:
                    line = "❌ OUT (DNP)"
                    
                log_lines.append(f"[{date}] {loc} {opp_team['abbreviation']} | {line}")
                
            final_log = "\n".join(log_lines)
            
            with st.expander("📊 Game Log (Season 2025-26)", expanded=True):
                st.code(final_log)
                
            # 6. GPT Analysis
            prompt = f"""
            You are an Expert NBA Analyst.
            
            TARGET: {fname} {lname} ({team_name})
            OPPONENT: {opp_real_name}
            
            OFFICIAL INJURY REPORT:
            - {team_name}: {injuries_home}
            - {opp_real_name}: {injuries_opp}
            
            GAME LOG (Last 5):
            {final_log}
            
            TASK:
            1. **Injury Impact:** How do the specific injuries on BOTH teams affect {lname}'s role?
            2. **Matchup:** Given the opponent's injuries, does he have an advantage?
            3. **Prediction:** Project stats (PTS/REB/AST).
            """
            
            response = llm.invoke(prompt).content
            st.divider()
            st.markdown("### 🧠 Coach's Verdict")
            st.write(response)

elif not bdl_key:
    st.warning("⚠️ Enter your All-Star API Key.")
