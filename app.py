import streamlit as st
import requests
from langchain_openai import ChatOpenAI
import os
import pandas as pd

# --- PAGE CONFIGURATION ---
st.set_page_config(page_title="NBA War Room (RapidAPI)", page_icon="🏀")
st.title("🏀 NBA War Room (RapidAPI Edition)")
st.markdown("**Source:** RapidAPI (Live Data) | **Coach:** GPT-4o")

# --- SIDEBAR: SETTINGS ---
with st.sidebar:
    st.header("⚙️ Settings")
    
    # 1. RAPID API KEY
    rapid_key_input = st.text_input("X-RapidAPI-Key", type="password")
    # Note: We use the 'free-nba' host because it has the best stat endpoints
    rapid_host = "free-nba.p.rapidapi.com"
    st.markdown("[Subscribe to 'Free NBA API'](https://rapidapi.com/theapiguy/api/free-nba)")
    
    # 2. OPENAI KEY
    openai_key_input = st.text_input("OpenAI API Key", type="password")
    
    if rapid_key_input: os.environ["RAPID_KEY"] = rapid_key_input.strip()
    if openai_key_input: os.environ["OPENAI_API_KEY"] = openai_key_input.strip()

# --- RAPID API TOOLS ---
def get_player_id(player_name):
    """Finds the Player ID on RapidAPI"""
    url = f"https://{rapid_host}/players"
    querystring = {"search": player_name, "per_page": "100"}
    headers = {
        "X-RapidAPI-Key": os.environ.get("RAPID_KEY"),
        "X-RapidAPI-Host": rapid_host
    }
    
    try:
        response = requests.get(url, headers=headers, params=querystring)
        data = response.json()
        
        # Filter for exact match or close match
        for p in data.get('data', []):
            # Simple check if the search term is in the full name
            full_name = f"{p['first_name']} {p['last_name']}"
            if player_name.lower() in full_name.lower():
                return p['id'], full_name, p['team']['full_name']
        return None, None, None
    except Exception as e:
        return None, None, str(e)

def get_last_5_games(player_id):
    """Fetches the last 5 games stats for the player"""
    url = f"https://{rapid_host}/stats"
    # We ask for the 2024 season (which covers 2024-2025)
    querystring = {
        "seasons[]": "2024", 
        "player_ids[]": str(player_id),
        "per_page": "5"  # Get last 5
    }
    headers = {
        "X-RapidAPI-Key": os.environ.get("RAPID_KEY"),
        "X-RapidAPI-Host": rapid_host
    }
    
    try:
        response = requests.get(url, headers=headers, params=querystring)
        data = response.json()
        
        games = []
        for g in data.get('data', []):
            game_info = g['game']
            matchup = f"{game_info['visitor_team']['abbreviation']} @ {game_info['home_team']['abbreviation']}"
            stats = f"PTS: {g['pts']} | REB: {g['reb']} | AST: {g['ast']}"
            date = game_info['date'].split("T")[0]
            games.append(f"Date: {date} | {matchup} | {stats}")
            
        # Join them into a string
        return "\n".join(games) if games else "No games found for 2024-25 season."
    except Exception as e:
        return f"Error fetching stats: {e}"

# --- MAIN APP ---
if rapid_key_input and openai_key_input:
    
    # FIX: Pass api_key explicitly to avoid Pydantic Validation Error
    llm_coach = ChatOpenAI(
        model="gpt-4o", 
        temperature=0.5, 
        api_key=openai_key_input
    )

    # --- UI ---
    col1, col2 = st.columns(2)
    with col1: p_name = st.text_input("Player Name", "Luka Doncic")
    with col2: p_team = st.text_input("Player Team", "Dallas Mavericks")

    if st.button("🚀 RUN RAPID ANALYSIS", type="primary"):
        
        stats_report = ""
        
        # --- PHASE 1: FETCH DATA (Direct API) ---
        with st.spinner(f"Ping {rapid_host} for stats..."):
            
            # 1. Get ID
            pid, full_name, team = get_player_id(p_name)
            
            if not pid:
                st.error(f"Player '{p_name}' not found on RapidAPI.")
                st.stop()
            
            st.success(f"Found: {full_name} ({team}) - ID: {pid}")
            
            # 2. Get Stats
            stats_report = get_last_5_games(pid)
            
            if "Error" in stats_report:
                st.error(stats_report)
                st.stop()
                
            with st.expander("📊 Read Live Stats (Raw JSON)", expanded=True):
                st.code(stats_report)

        # --- PHASE 2: GPT-4o COACHING ---
        if stats_report:
            with st.spinner("GPT-4o is analyzing the trends..."):
                try:
                    coach_prompt = f"""
                    You are an NBA Head Coach.
                    
                    PLAYER: {full_name} ({team})
                    RECENT FORM (Last 5 Games):
                    {stats_report}
                    
                    TASK:
                    1. Analyze his trend (Hot/Cold?).
                    2. Predict his stat line for the next game.
                    3. Give a betting recommendation (Over/Under on points).
                    """
                    final_prediction = llm_coach.invoke(coach_prompt).content
                    
                    st.divider()
                    st.markdown("### 🏆 Official Prediction")
                    st.write(final_prediction)
                    
                except Exception as e:
                    st.error(f"Coaching Failed: {e}")

elif not rapid_key_input or not openai_key_input:
    st.warning("⚠️ Please enter both API Keys to start.")
