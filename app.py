import streamlit as st
import requests
from langchain_openai import ChatOpenAI
import os
import pandas as pd
from datetime import datetime, timedelta
import difflib 

# --- PAGE CONFIGURATION ---
st.set_page_config(page_title="NBA War Room (Secure)", page_icon="🔒", layout="wide")
st.title("🏀 NBA War Room (Secure Edition)")
st.markdown("**Tier:** All-Star | **Auth:** Streamlit Secrets | **Coach:** GPT-4o")

# --- SECURE AUTHENTICATION ---
def load_keys():
    """
    Prioritizes secrets.toml, falls back to sidebar input.
    """
    keys = {}
    
    # 1. BallDontLie Key
    if "BDL_API_KEY" in st.secrets:
        keys["bdl"] = st.secrets["BDL_API_KEY"]
        st.sidebar.success("✅ BDL Key Loaded")
    else:
        keys["bdl"] = st.sidebar.text_input("BallDontLie Key", type="password")

    # 2. OpenAI Key
    if "OPENAI_API_KEY" in st.secrets:
        keys["openai"] = st.secrets["OPENAI_API_KEY"]
        st.sidebar.success("✅ OpenAI Key Loaded")
    else:
        keys["openai"] = st.sidebar.text_input("OpenAI Key", type="password")

    # Set Environment Variables for tools to use globally
    if keys["bdl"]: os.environ["BDL_API_KEY"] = keys["bdl"].strip()
    if keys["openai"]: os.environ["OPENAI_API_KEY"] = keys["openai"].strip()
    
    return keys

# --- SIDEBAR ---
with st.sidebar:
    st.header("⚙️ Settings")
    # Load keys securely
    api_keys = load_keys()
    
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
    """Smart Search V2: Handles typos (Trigram method)"""
    try:
        # 1. Split input into words
        words = user_input.split()
        candidates = {} 
        
        # 2. Broad Search
        search_terms = set(words)
        for w in words:
            if len(w) >= 3: search_terms.add(w[:3])
        
        for term in search_terms:
            r = requests.get(url=f"{BASE_URL}/players", headers=get_headers(), params={"search": term, "per_page": 10})
            if r.status_code == 200:
                for p in r.json().get('data', []):
                    candidates[p['id']] = p
        
        if not candidates: return None, f"Player '{user_input}' not found."
        
        # 3. Fuzzy Match
        candidate_list = list(candidates.values())
        candidate_names = [f"{c['first_name']} {c['last_name']}" for c in candidate_list]
        best_matches = difflib.get_close_matches(user_input, candidate_names, n=1, cutoff=0.4)
        
        if best_matches:
            target_name = best_matches[0]
            p = next(c for c in candidate_list if f"{c['first_name']} {c['last_name']}" == target_name)
            return p, f"Found: **{target_name}** (Corrected from '{user_input}')"
            
        return None, "No close matches found."

    except Exception as e: return None, f"Search Error: {e}"

def get_team_injuries(team_id):
    """Fetches official injury report with crash protection."""
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
    """Fetches TEAM'S last 5 finished games"""
    try:
        url = f"{BASE_URL}/games"
        today = datetime.now().strftime("%Y-%m-%d")
        params = {"team_ids[]": str(team_id), "seasons[]": "2025", "end_date": today, "per_page": "20"}
        resp = requests.get(url, headers=get_headers(), params=params)
        data = resp.json().get('data
