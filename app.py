import streamlit as st
import requests
from langchain_openai import ChatOpenAI
import os
import pandas as pd
from datetime import datetime, timedelta
import difflib 

# --- PAGE CONFIGURATION ---
st.set_page_config(page_title="NBA War Room (Ultimate)", page_icon="🏀", layout="wide")
st.title("🏀 NBA War Room (Ultimate Edition)")
st.markdown("**Stats:** BallDontLie (All-Star) | **Odds:** FanDuel | **Coach:** GPT-4o")

# --- SIDEBAR: SETTINGS ---
with st.sidebar:
    st.header("⚙️ Settings")
    
    # 1. BallDontLie Key
    bdl_key = st.text_input("BallDontLie API Key", type="password")
    st.caption("Must be All-Star Tier")
    
    # 2. The Odds API Key
    odds_key = st.text_input("The Odds API Key", type="password")
    
    # 3. OpenAI Key
    openai_key = st.text_input("OpenAI API Key", type="password")
    
    if bdl_key: os.environ["BDL_API_KEY"] = bdl_key.strip()
    if odds_key: os.environ["ODDS_API_KEY"] = odds_key.strip()
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
BDL_URL = "https://api.balldontlie.io/v1"
ODDS_URL = "https://api.the-odds-api.com/v4/sports/basketball_nba"

def get_headers():
    return {"Authorization": os.environ.get("BDL_API_KEY")}

# --- TOOLS ---

def get_fanduel_props(player_name, team_name):
    """Fetches FanDuel Player Props"""
    api_key = os.environ.get("ODDS_API_KEY")
    if not api_key: return "Odds API Key missing."

    try:
        # 1. Get Today's Games
        games_resp = requests.get(f"{ODDS_URL}/events", params={"apiKey": api_key, "regions": "us"})
        games = games_resp.json()
        
        if not games or "message" in games: return "No betting lines available right now."

        game_id = None
        for g in games:
            if team_name in g['home_team'] or team_name in g['away_team']:
                game_id = g['id']
                break
        
        if not game_id: return f"No lines found for {team_name}."

        # 2. Fetch Props
        props_resp = requests.get(
            f"{ODDS_URL}/events/{game_id}/odds",
            params={
                "apiKey": api_key,
                "regions": "us",
                "markets": "player_points,player_rebounds,player_assists",
                "bookmakers": "fanduel"
            }
        )
        data = props_resp.json()
        
        lines = []
        bookmakers = data.get('bookmakers', [])
        if not bookmakers: return "No FanDuel lines released yet."
        
        for market in bookmakers[0].get('markets', []):
            market_name = market['key'].replace("player_", "").title()
            for outcome in market['outcomes']:
                p_last = player_name.split()[-1]
                if p_last in outcome['description']:
                    line = outcome.get('point', 'N/A')
                    price = outcome.get('price', 'N/A')
                    lines.append(f"**{market_name}**: {line} ({price})")
        
        return " | ".join(lines) if lines else f"No specific props found for {player_name}."

    except Exception as e: return f"Error fetching odds: {e}"

def get_player_info_smart(user_input):
    try:
        url = f"{BDL_URL}/players"
        resp = requests.get(url, headers=get_headers(), params={"search": user_input, "per_page": 10})
        candidates = resp.json().get('data', [])
        
        if not candidates:
            # Fallback: Search by separate words
            for word in user_input.split():
                if len(word) > 2:
                    r = requests.get(url
