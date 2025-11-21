import streamlit as st
import requests
from langchain_openai import ChatOpenAI
import os
import pandas as pd
from datetime import datetime, timedelta

# --- PAGE CONFIGURATION ---
st.set_page_config(page_title="NBA War Room (Official)", page_icon="🏀", layout="wide")
st.title("🏀 NBA War Room (Official API)")
st.markdown("**Source:** api.balldontlie.io (Direct) | **Coach:** GPT-4o")

# --- SIDEBAR: SETTINGS ---
with st.sidebar:
    st.header("⚙️ Settings")
    
    # 1. OFFICIAL KEY (Not RapidAPI)
    bdl_key = st.text_input("BallDontLie API Key", type="password")
    st.caption("Get this from balldontlie.io (NOT RapidAPI)")
    
    openai_key = st.text_input("OpenAI API Key", type="password")
    
    if bdl_key: os.environ["BDL_API_KEY"] = bdl_key.strip()
    if openai_key: os.environ["OPENAI_API_KEY"] = openai_key.strip()

# --- API CONFIG (DIRECT) ---
BASE_URL = "https://api.balldontlie.io/v1"

def get_headers():
    # The official API uses 'Authorization' header
    return {"Authorization": os.environ.get("BDL_API_KEY")}

# --- ADVANCED TOOLS ---

@st.cache_data(ttl=3600)
def get_conference_rankings():
    """Fetches standings to map Team ID -> Rank"""
    try:
        url = f"{BASE_URL}/standings"
        params = {"season": "2025"} 
        resp = requests.get(url, headers=get_headers(), params=params)
        data = resp.json()['data']
        
        rank_map = {}
        for team in data:
            t_id = team['team']['id']
            conf = team['conference'].get('name', 'UNK')
            rank = team['conference'].get('rank', 'N/A')
            rank_map[t_id] = f"{conf} #{rank}"
            
        return rank_map
    except Exception:
        return {}

def get_player_info(name):
    """Finds Player and their Team ID"""
    try:
        url = f"{BASE_URL}/players"
        params = {"search": name, "per_page": "1"}
        resp = requests.get(url, headers=get_headers(), params=params)
        data = resp.json()['data']
        
        if not data: 
            return None, None, None, None
            
        p = data[0]
        return p['id'], p['first_name'], p['last_name'], p['team']['id']
    except Exception:
        return None, None, None, None

def get_team_schedule(team_id):
    """Fetches the TEAM'S last 5 finished games"""
    try:
        url = f"{BASE_URL}/games"
        # '2024' covers the 2024-2025 season in this API
        params = {
            "team_ids[]": str(team_id),
            "seasons[]": "2024", 
            "per_page": "10"
        }
        resp = requests.get(url, headers=get_headers(), params=params)
        data = resp.json()['data']
        
        # Filter only 'Final' games and sort by date (newest first)
        finished_games = [g for g in data if g['status'] == "Final"]
        finished_games.sort(key=lambda x: x['date'], reverse=True)
        
        return finished_games[:5]
    except Exception:
        return []

def get_game_stats(player_id, game_ids):
    """Fetches stats for specific games to see if player played"""
    if not game_ids: 
        return []
        
    try:
        url = f"{BASE_URL}/stats"
        # We pass the list of Game IDs to filter specifically for them
        params = {
            "player_ids[]": str(player_id),
            "per_page": "10",
            "game_ids[]": [str(gid) for gid in game_ids] 
        }
        resp = requests.get(url, headers=get_headers(), params=params)
        return resp.json()['data']
    except Exception:
        return []

# --- MAIN APP ---
if bdl_key and openai_key:
    
    llm = ChatOpenAI(model="gpt-4o", temperature=0.5, api_key=openai_key)
    
    col1, col2 = st.columns(2)
    with col1: p_name = st.text_input("Player Name", "Luka Doncic")
    
    if st.button("🚀 RUN ANALYSIS", type="primary"):
        with st.spinner("Connecting to BallDontLie.io..."):
            
            # 1. Get Player & Team
            res = get_player_info(p_name)
            if not res or not res[0]:
