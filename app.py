import streamlit as st
import requests
from langchain_openai import ChatOpenAI
import os
import pandas as pd
from datetime import datetime, timedelta

# --- PAGE CONFIGURATION ---
st.set_page_config(page_title="NBA War Room (Official)", page_icon="🏀", layout="wide")
st.title("🏀 NBA War Room (Official API)")
st.markdown("**Logic:** Team Schedule First | **Season:** 2025-26 | **Coach:** GPT-4o")

# --- SIDEBAR ---
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

# --- TOOLS ---

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
        
        if not data: 
            return None, None, None, None
            
        p = data[0]
        # Return ID, First, Last, Team ID, Team Name
        return p['id'], p['first_name'], p['last_name'], p['team']['id'], p['team']['full_name']
    except:
        return None, None, None, None, None

def get_team_schedule_before_today(team_id):
    """
    CRITICAL FIX:
    1. Searches games for THIS Team (Season 2025).
    2. Filters for dates BEFORE today.
    3. Sorts by newest first.
    """
    try:
        url = f"{BASE_URL}/games"
        today = datetime.now().strftime("%Y-%m-%d")
        
        params = {
            "team_ids[]": str(team_id),
            "seasons[]": "2025", 
            "end_date": today, # STRICTLY before or on today
            "per_page": "20"   # Get enough to filter
        }
        resp = requests.get(url, headers=get_headers(), params=params)
        data = resp.json()['data']
        
        # Filter: Must be "Final" to have stats
        finished_games = [g for g in data if g['status'] == "Final"]
        
        # Sort Descending (Newest First)
        finished_games.sort(key=lambda x: x['date'], reverse=True)
        
        return finished_games[:5] # Return exactly 5
    except:
        return []

def get_next_game(team_id):
    """Finds the NEXT game (Today or Future)"""
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
        
        if not data: return None, "No games found in next 14 days."
        
        # Sort Ascending (Soonest First)
        data.sort(key=lambda x: x['date'])
        
        game = data[0]
        
        # Determine Opponent
        if game['home_team']['id'] == team_id:
            opp_name = game['visitor_team']['full_name']
            loc = "vs"
        else:
            opp_name = game['home_team']['full_name']
            loc = "@"
            
        date_str = game['date'].split("T")[0]
        return f"{loc} {opp_name}", date_str
        
    except: return None, "Error finding schedule."

def get_stats_for_specific_games(player_id, game_ids):
    """Fetches stats ONLY for the Game IDs found in the schedule"""
    if not game_ids: return []
    try:
        url = f"{BASE_URL}/stats"
        params = {
            "player_ids[]": str(player_id),
            "per_page": "10",
            # This forces the API to only look at the specific team games we found
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
    
    # Show Today's Date
    today_display = datetime.now().strftime("%A, %B %d, %Y")
    st.caption(f"📅 Today's Date: **{today_display}**")
    
    if st.button("🚀 RUN PRO ANALYSIS", type="primary"):
        with st.spinner("Analyzing Schedule & Stats..."):
            
            # 1. Get Player
            res = get_player_info(p_name)
            if not res or not res[0]:
                st.error("Player not found.")
                st.stop()
                
            pid, fname, lname, team_id, team_name = res
            st.success(f"Found: **{fname} {lname}** (Team: {team_name})")
            
            # 2. Get Next Game
            opp_next, date_next = get_next_game(team_id)
            if opp_next:
                st.info(f"🏀 **NEXT GAME:** {opp_next} | 📅 {date_next}")
            else:
                st.warning("No upcoming games found.")
            
            # 3. Get Past 5 Games (The Team's Schedule)
            past_games = get_team_schedule_before_today(team_id)
            if not past_games:
                st.error("No recent games found for this team in 2025.")
                st.stop()
                
            # 4. Get Stats for those specific games
            game_ids = [g['id'] for g in past_games]
            player_stats = get_stats_for_specific_games(pid, game_ids)
            
            # 5. Get Rankings
            rank_map = get_conference_rankings()
            
            # 6. Build the Log
            log_lines = []
            for game in past_games:
                gid = game['id']
                date = game['date'].split("T")[0]
                
                # Determine Opponent
                if game['home_team']['id'] == team_id:
                    opp_team = game['visitor_team']
                    loc = "vs"
                else:
                    opp_team = game['home_team']
                    loc = "@"
                
                opp_abbr = opp_team['abbreviation']
                opp_rank = rank_map.get(opp_team['id'], "")
                
                # Find the stat line for this specific game
                stat = next((s for s in player_stats if s['game']['id'] == gid), None)
                
                if stat and stat['min']:
                    # Calculate FG%
                    fg_pct = f"{stat['fg_pct']*100:.1f}%" if stat['fg_pct'] else "0%"
                    
                    # Extract 3PT
                    fg3m = stat['fg3m']
                    fg3a = stat['fg3a']
                    fg3_str = f"{fg3m}/{fg3a}"
                    
                    line = (f"MIN:{stat['min']} | PTS:{stat['pts']} REB:{stat['reb']} AST:{stat['ast']} | "
                            f"FG:{fg_pct} 3PT:{fg3_str}")
                else:
                    line = "❌ OUT (DNP)"
                    
                log_lines.append(f"[{date}] {loc} {opp_abbr} {opp_rank} | {line}")
                
            final_log = "\n".join(log_lines)
            
            with st.expander("📊 Verified Game Log (Season 2025-26)", expanded=True):
                st.code(final_log)
                
            # 7. GPT Analysis
            prompt = f"""
            Analyze NBA Player: {fname} {lname} ({team_name})
            TODAY: {today_display}
            NEXT MATCHUP: {opp_next}
            
            OFFICIAL GAME LOG (Last 5 Team Games):
            {final_log}
            
            TASK:
            1. **Availability:** Is he missing games? (Look for "OUT" tags).
            2. **Performance:** If playing, is he hitting his averages? Check FG% and 3PT volume.
            3. **Prediction:** Project stats (PTS/REB/AST) vs {opp_next}.
            """
            
            response = llm.invoke(prompt).content
            st.divider()
            st.write(response)

elif not bdl_key:
    st.warning("⚠️ Please enter your BallDontLie API Key.")
