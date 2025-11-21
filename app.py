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
    # The official API uses 'Authorization' header, not 'X-RapidAPI-Key'
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
    except:
        return {}

def get_player_info(name):
    """Finds Player and their Team ID"""
    try:
        url = f"{BASE_URL}/players"
        params = {"search": name, "per_page": "1"}
        resp = requests.get(url, headers=get_headers(), params=params)
        data = resp.json()['data']
        if not data: return None, None, None, None
        return data[0]['id'], data[0]['first_name'], data[0]['last_name'], data[0]['team']['id']
    except:
