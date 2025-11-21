import streamlit as st
import requests
from langchain_openai import ChatOpenAI
import os
import pandas as pd
from datetime import datetime, timedelta

# --- PAGE CONFIGURATION ---
st.set_page_config(page_title="NBA War Room (All-Star)", page_icon="⭐", layout="wide")
st.title("🏀 NBA War Room (All-Star Edition)")
st.markdown("**Tier:** All-Star (Official API) | **Features:** Injuries + Deep Stats + Persistent Chat")

# --- SIDEBAR: SETTINGS ---
with st.sidebar:
    st.header("⚙️ Settings")
    bdl_key = st.text_input("BallDontLie API Key", type="password")
    openai_key = st.text_input("OpenAI API Key", type="password")
    
    if bdl_key: os.environ["BDL_API_KEY"] = bdl_key.strip()
    if openai_key: os.environ["OPENAI_API_KEY"] = openai_key.strip()
    
    st.divider()
    st.info("Stats will stay visible while you chat.")

# --- INITIALIZE SESSION STATE ---
# This creates the "Memory" for the app
if "messages" not in st.session_state:
    st.session_state.messages = []
if "analysis_data" not in st.session_state:
    st.session_state.analysis_data = None # Stores the stats/report

# --- API CONFIG ---
BASE_URL = "https://api.balldontlie.io/v1"

def get_headers():
    return {"Authorization": os.environ.get("BDL_API_KEY")}

# --- ALL-STAR TOOLS ---

def get_team_injuries(team_id):
    """Fetches official injury report with crash protection."""
    try:
        url = f"{BASE_URL}/player_injuries"
        params = {"team_ids[]": str(team_id)}
        resp = requests.get(url, headers=get_headers(), params=params)
        
        if resp.status_code != 200: return f"API Error {resp.status_code}"
        data = resp.json().get('data', [])
        
        if not data: return "No active injuries reported."
        
        reports = []
        for i in data:
            player = i.get('player', {}).get('first_name', '') + " " + i.get('player', {}).get('last_name', '')
            status = i.get('status', 'Unknown')
            note = i.get('note') or i.get('comment') or i.get('description') or "No details"
            reports.append(f"- **{player}**: {status} ({note})")
            
        return "\n".join(reports)
    except Exception as e: return f"Error: {e}"

def get_player_info(name):
    try:
        url = f"{BASE_URL}/players"
        params = {"search": name, "per_page": "1"}
        resp = requests.get(url, headers=get_headers(), params=params)
        data = resp.json()['data']
        if not data: return None
        p = data[0]
        return p['id'], p['first_name'], p['last_name'], p['team']['id'], p['team']['full_name']
    except: return None

def get_team_schedule_before_today(team_id):
    """Fetches TEAM'S last 5 finished games (2025 Season)"""
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
        if not data: return None, "No games found.", None, None
        
        data.sort(key=lambda x: x['date'])
        game = data[0]
        
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

# --- MAIN APP LOGIC ---
if bdl_key and openai_key:
    
    llm = ChatOpenAI(model="gpt-4o", temperature=0.5, api_key=openai_key)
    
    col1, col2 = st.columns(2)
    with col1: p_name = st.text_input("Player Name", "Luka Doncic")
    
    # --- BUTTON LOGIC (Saves to Session State) ---
    if st.button("🚀 RUN ALL-STAR ANALYSIS", type="primary"):
        with st.spinner("Fetching Official Data..."):
            
            # 1. Player Info
            res = get_player_info(p_name)
            if not res:
                st.error("Player not found.")
                st.stop()
            
            pid, fname, lname, team_id, team_name = res
            
            # 2. Next Game & Opponent ID
            opp_str, date_next, opp_id, opp_real_name = get_next_game(team_id)
            if not opp_str: opp_real_name = "Unknown"

            # 3. Injuries
            injuries_home = get_team_injuries(team_id) if team_id else "N/A"
            injuries_opp = get_team_injuries(opp_id) if opp_id else "N/A"

            # 4. Stats
            past_games = get_team_schedule_before_today(team_id)
            game_ids = [g['id'] for g in past_games]
            player_stats = get_stats_for_specific_games(pid, game_ids)
            
            # Build Log
            log_lines = []
            for game in past_games:
                gid = game['id']
                date = game['date'].split("T")[0]
                if game['home_team']['id'] == team_id:
                    opp = game['visitor_team']['abbreviation']
                    loc = "vs"
                else:
                    opp = game['home_team']['abbreviation']
                    loc = "@"
                
                stat = next((s for s in player_stats if s['game']['id'] == gid), None)
                if stat and stat['min']:
                    fg_pct = f"{stat['fg_pct']*100:.1f}%" if stat['fg_pct'] else "0%"
                    line = f"MIN:{stat['min']} PTS:{stat['pts']} REB:{stat['reb']} AST:{stat['ast']} FG:{fg_pct}"
                else:
                    line = "❌ OUT (DNP)"
                log_lines.append(f"[{date}] {loc} {opp} | {line}")
            
            final_log = "\n".join(log_lines)
            
            # 5. Generate
