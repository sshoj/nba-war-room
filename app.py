import streamlit as st
import requests
from langchain_openai import ChatOpenAI
import os
import pandas as pd
from datetime import datetime, timedelta

# --- PAGE CONFIGURATION ---
st.set_page_config(page_title="NBA War Room (Official)", page_icon="🏀", layout="wide")
st.title("🏀 NBA War Room (Official API)")
st.markdown("**Source:** api.balldontlie.io | **Coach:** GPT-4o")

# --- SIDEBAR: SETTINGS ---
with st.sidebar:
    st.header("⚙️ Settings")
    bdl_key = st.text_input("BallDontLie API Key", type="password")
    st.caption("Get this from balldontlie.io")
    
    openai_key = st.text_input("OpenAI API Key", type="password")
    
    if bdl_key: os.environ["BDL_API_KEY"] = bdl_key.strip()
    if openai_key: os.environ["OPENAI_API_KEY"] = openai_key.strip()

# --- API CONFIG ---
BASE_URL = "https://api.balldontlie.io/v1"

def get_headers():
    return {"Authorization": os.environ.get("BDL_API_KEY")}

# --- LOGIC TOOLS ---

def get_player_info(name):
    """Finds Player and their Team ID"""
    try:
        url = f"{BASE_URL}/players"
        params = {"search": name, "per_page": "1"}
        resp = requests.get(url, headers=get_headers(), params=params)
        data = resp.json()['data']
        if not data: return None, None, None, None
        return data[0]['id'], data[0]['first_name'], data[0]['last_name'], data[0]['team']['id']
    except: return None, None, None, None

def get_next_game(team_id):
    """Finds the FIRST game scheduled AFTER or ON today"""
    try:
        url = f"{BASE_URL}/games"
        today = datetime.now().strftime("%Y-%m-%d")
        # Look ahead 14 days to be safe
        future = (datetime.now() + timedelta(days=14)).strftime("%Y-%m-%d")
        
        params = {
            "team_ids[]": str(team_id),
            "start_date": today,
            "end_date": future,
            "per_page": "5"
        }
        resp = requests.get(url, headers=get_headers(), params=params)
        data = resp.json()['data']
        
        if not data: return None, "No upcoming games found."
        
        # Sort by Date Ascending (Soonest first)
        data.sort(key=lambda x: x['date'])
        
        # Pick the first one
        game = data[0]
        date_str = game['date'].split("T")[0]
        time_str = game['status'] # e.g., "8:00 PM ET"
        
        if game['home_team']['id'] == team_id:
            return f"vs {game['visitor_team']['full_name']}", f"{date_str} @ {time_str}"
        else:
            return f"@ {game['home_team']['full_name']}", f"{date_str} @ {time_str}"
            
    except Exception as e: return None, str(e)

def get_previous_games(team_id):
    """Fetches the 5 most recent FINAL games before today"""
    try:
        url = f"{BASE_URL}/games"
        # Look back at the whole 2024-2025 season
        params = {
            "team_ids[]": str(team_id),
            "seasons[]": "2024", 
            "per_page": "100" # Get enough to sort
        }
        resp = requests.get(url, headers=get_headers(), params=params)
        data = resp.json()['data']
        
        # Filter: Must be "Final" AND date must be before today
        # (Although 'Final' usually implies past, we sort to be sure)
        finished_games = [g for g in data if g['status'] == "Final"]
        
        # Sort Descending (Newest First)
        finished_games.sort(key=lambda x: x['date'], reverse=True)
        
        return finished_games[:5] # Return top 5
    except: return []

def get_stats_for_games(player_id, game_ids):
    """Get stats for specific game IDs"""
    if not game_ids: return []
    try:
        url = f"{BASE_URL}/stats"
        params = {
            "player_ids[]": str(player_id),
            "per_page": "10",
            "game_ids[]": game_ids
        }
        resp = requests.get(url, headers=get_headers(), params=params)
        return resp.json()['data']
    except: return []

# --- MAIN APP ---
if bdl_key and openai_key:
    
    llm = ChatOpenAI(model="gpt-4o", temperature=0.5, api_key=openai_key)
    
    col1, col2 = st.columns(2)
    with col1: p_name = st.text_input("Player Name", "Luka Doncic")
    
    # DISPLAY TODAY'S DATE
    today_display = datetime.now().strftime("%A, %B %d, %Y")
    st.caption(f"📅 Today's Date: **{today_display}**")
    
    if st.button("🚀 RUN ANALYSIS", type="primary"):
        with st.spinner("Accessing War Room Data..."):
            
            # 1. Player Info
            res = get_player_info(p_name)
            if not res or not res[0]:
                st.error("Player not found.")
                st.stop()
                
            pid, fname, lname, team_id = res
            st.success(f"Found: {fname} {lname}")
            
            # 2. Next Game
            opp_name, game_time = get_next_game(team_id)
            if opp_name:
                st.info(f"🏀 **NEXT GAME:** {opp_name} | ⏰ {game_time}")
            else:
                st.warning("No upcoming games found.")
                
            # 3. Previous 5 Games
            past_games = get_previous_games(team_id)
            if not past_games:
                st.error("No past games found.")
                st.stop()
                
            # 4. Get Stats for those games
            gids = [g['id'] for g in past_games]
            stats_data = get_stats_for_games(pid, gids)
            
            # 5. Format Log
            log_lines = []
            for game in past_games:
                gid = game['id']
                date = game['date'].split("T")[0]
                
                # Determine Opponent
                if game['home_team']['id'] == team_id:
                    opp = f"vs {game['visitor_team']['abbreviation']}"
                else:
                    opp = f"@ {game['home_team']['abbreviation']}"
                
                # Find Stat Line
                stat = next((s for s in stats_data if s['game']['id'] == gid), None)
                
                if stat and stat['min']:
                    line = f"PTS:{stat['pts']} REB:{stat['reb']} AST:{stat['ast']} (FG: {stat['fg_pct']:.0%})"
                else:
                    line = "❌ OUT (DNP)"
                    
                log_lines.append(f"[{date}] {opp} | {line}")
                
            final_log = "\n".join(log_lines)
            
            with st.expander("📊 Last 5 Games (Before Today)", expanded=True):
                st.code(final_log)
                
            # 6. GPT Analysis
            prompt = f"""
            Analyze NBA Player: {fname} {lname}
            TODAY'S DATE: {today_display}
            
            NEXT MATCHUP: {opp_name}
            
            LAST 5 GAMES (Most Recent First):
            {final_log}
            
            TASK:
            1. Is he trending UP or DOWN?
            2. Did he play the last game?
            3. Predict stats for the game against {opp_name}.
            """
            
            response = llm.invoke(prompt).content
            st.divider()
            st.write(response)

elif not bdl_key:
    st.warning("⚠️ Please enter your BallDontLie API Key.")
