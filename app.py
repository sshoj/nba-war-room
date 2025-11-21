import streamlit as st
import requests
from langchain_openai import ChatOpenAI
import os
import pandas as pd
from datetime import datetime, timedelta
import difflib 

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
    Smart Search V2: Uses 'Trigram' searching to find players even with bad typos.
    Example: 'Luca Donicic' -> Searches 'Don' -> Finds 'Luka Doncic'
    """
    try:
        # 1. Split input into words
        words = user_input.split()
        candidates = {} # Use a dict to keep unique players (ID as key)
        
        # 2. Broad Search Strategy
        # We search for the full word AND the first 3 letters of each word
        search_terms = set(words) # Add original words
        for w in words:
            if len(w) >= 3:
                search_terms.add(w[:3]) # Add "Luc", "Don", etc.
        
        # Run API searches
        for term in search_terms:
            r = requests.get(url=f"{BASE_URL}/players", headers=get_headers(), params={"search": term, "per_page": 10})
            if r.status_code == 200:
                for p in r.json().get('data', []):
                    candidates[p['id']] = p
        
        if not candidates: return None, f"Player '{user_input}' not found."
        
        # 3. Python Fuzzy Match
        # Now that we have a pool of ~20 candidates (including the right one), we match the full name
        candidate_list = list(candidates.values())
        # Create formatted names for matching: "Luka Doncic"
        candidate_names = [f"{c['first_name']} {c['last_name']}" for c in candidate_list]
        
        # Use difflib to find which candidate is closest to "Luca Donicic"
        best_matches = difflib.get_close_matches(user_input, candidate_names, n=1, cutoff=0.4)
        
        if best_matches:
            target_name = best_matches[0]
            # Find the player object that matches the name
            p = next(c for c in candidate_list if f"{c['first_name']} {c['last_name']}" == target_name)
            return p, f"Found: **{target_name}** (Corrected from '{user_input}')"
            
        return None, "No close matches found."

    except Exception as e: return None, f"Search Error: {e}"

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
        params = {"team_ids[]": str(team_id), "seasons[]": "2025", "end_date": today, "per_page": "20"}
        resp = requests.get(url, headers=get_headers(), params=params)
        data = resp.json().get('data', [])
        finished = [g for g in data if g.get('status') == "Final"]
        finished.sort(key=lambda x: x['date'], reverse=True)
        return finished[:5]
    except: return []

def get_next_game(team_id):
    try:
        url = f"{BASE_URL}/games"
        today = datetime.now().strftime("%Y-%m-%d")
        future = (datetime.now() + timedelta(days=14)).strftime("%Y-%m-%d")
        params = {"team_ids[]": str(team_id), "seasons[]": "2025", "start_date": today, "end_date": future, "per_page": "10"}
        resp = requests.get(url, headers=get_headers(), params=params)
        data = resp.json().get('data', [])
        if not data: return None, "No games found.", None, None
        
        data.sort(key=lambda x: x['date'])
        # Find first non-final game
        game = next((g for g in data if
