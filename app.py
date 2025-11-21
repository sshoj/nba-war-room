import streamlit as st
import requests
from langchain_openai import ChatOpenAI
import os
from datetime import datetime

# --- PAGE CONFIGURATION ---
st.set_page_config(page_title="NBA War Room (BallDontLie)", page_icon="🏀")
st.title("🏀 NBA War Room (BallDontLie Edition)")
st.markdown("**Data Source:** BallDontLie API (Official) | **Coach:** GPT-4o")

# --- SIDEBAR: SETTINGS ---
with st.sidebar:
    st.header("⚙️ Settings")
    
    # 1. BALLDONTLIE KEY
    bdl_key = st.text_input("BallDontLie API Key", type="password")
    st.markdown("[Get Free Key](https://balldontlie.io/)")
    
    # 2. OPENAI KEY
    openai_key = st.text_input("OpenAI API Key", type="password")
    
    if bdl_key: os.environ["BDL_API_KEY"] = bdl_key.strip()
    if openai_key: os.environ["OPENAI_API_KEY"] = openai_key.strip()

# --- API TOOLS ---
BASE_URL = "https://api.balldontlie.io/v1"

def get_headers():
    return {"Authorization": os.environ.get("BDL_API_KEY")}

def get_player_data(player_name):
    """Finds Player ID and Team ID"""
    try:
        url = f"{BASE_URL}/players"
        params = {"search": player_name}
        resp = requests.get(url, headers=get_headers(), params=params)
        data = resp.json()['data']
        
        if not data:
            return None, None, None
            
        # Return first match
        p = data[0]
        return p['id'], p['first_name'] + " " + p['last_name'], p['team']
    except Exception as e:
        return None, None, str(e)

def get_last_5_games(player_id):
    """Fetches last 5 games stats"""
    try:
        url = f"{BASE_URL}/stats"
        # Season 2024 = 2024-2025 Season
        params = {
            "seasons[]": 2024,
            "player_ids[]": player_id,
            "per_page": 5
        }
        resp = requests.get(url, headers=get_headers(), params=params)
        data = resp.json()['data']
        
        if not data:
            return "No games found for 2024-25 season."
            
        # Format data for GPT
        games_log = []
        for g in data:
            matchup = f"{g['game']['visitor_team']['abbreviation']} @ {g['game']['home_team']['abbreviation']}"
            date = g['game']['date'].split("T")[0]
            stat_line = f"PTS: {g['pts']}, REB: {g['reb']}, AST: {g['ast']}"
            games_log.append(f"{date} | {matchup} | {stat_line}")
            
        return "\n".join(games_log)
    except Exception as e:
        return f"Error: {e}"

def get_next_game(team_id):
    """Finds the next scheduled game for the team"""
    try:
        url = f"{BASE_URL}/games"
        today = datetime.now().strftime("%Y-%m-%d")
        params = {
            "team_ids[]": team_id,
            "start_date": today,
            "per_page": 1  # Get next 1 game
        }
        resp = requests.get(url, headers=get_headers(), params=params)
        data = resp.json()['data']
        
        if not data:
            return "Unknown Opponent (Schedule not found)"
            
        game = data[0]
        home_team = game['home_team']['full_name']
        visitor_team = game['visitor_team']['full_name']
        
        # Determine opponent
        if game['home_team']['id'] == team_id:
            return f"vs {visitor_team}"
        else:
            return f"@ {home_team}"
            
    except Exception as e:
        return f"Error finding schedule: {e}"

# --- MAIN APP ---
if bdl_key and openai_key:
    
    llm_coach = ChatOpenAI(model="gpt-4o", temperature=0.5, api_key=openai_key)

    col1, col2 = st.columns(2)
    with col1: p_name = st.text_input("Player Name", "Luka Doncic")
    
    if st.button("🚀 RUN ANALYSIS", type="primary"):
        
        with st.spinner("Fetching Data from BallDontLie..."):
            # 1. Find Player & Team
            pid, full_name, team_data = get_player_data(p_name)
            
            if not pid:
                st.error("Player not found!")
                st.stop()
                
            team_name = team_data['full_name']
            team_id = team_data['id']
            
            st.success(f"Found: {full_name} ({team_name})")
            
            # 2. Get Schedule (Next Opponent)
            next_opponent = get_next_game(team_id)
            st.info(f"Next Game: {next_opponent}")
            
            # 3. Get Stats
            stats_report = get_last_5_games(pid)
            with st.expander("📊 Raw Game Logs", expanded=True):
                st.code(stats_report)
                
        # --- GPT ANALYSIS ---
        if stats_report:
            with st.spinner("GPT-4o is generating the game plan..."):
                try:
                    prompt = f"""
                    You are an Expert NBA Analyst.
                    
                    TARGET: {full_name} ({team_name})
                    NEXT OPPONENT: {next_opponent}
                    RECENT FORM (Last 5 Games):
                    {stats_report}
                    
                    TASK:
                    1. Analyze the player's trend (Hot/Cold?).
                    2. Predict his stat line for the next game against {next_opponent}.
                    3. Provide a betting recommendation (Over/Under on Points).
                    """
                    
                    prediction = llm_coach.invoke(prompt).content
                    st.divider()
                    st.markdown("### 🏆 Official Prediction")
                    st.write(prediction)
                    
                except Exception as e:
                    st.error(f"AI Error: {e}")

elif not bdl_key:
    st.warning("⚠️ Please enter your BallDontLie API Key to start.")
