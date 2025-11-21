import streamlit as st
import requests
from langchain_openai import ChatOpenAI
import os
from datetime import datetime, timedelta
import time

# --- PAGE CONFIGURATION ---
st.set_page_config(page_title="NBA War Room (RapidAPI)", page_icon="🏀", layout="wide")
st.title("🏀 NBA War Room (RapidAPI Pro)")
st.markdown("**Data:** RapidAPI (Unblockable) | **Logic:** Deep Stats | **Coach:** GPT-4o")

# --- SIDEBAR: SETTINGS ---
with st.sidebar:
    st.header("⚙️ Settings")
    
    # 1. RAPID API KEY
    rapid_key_input = st.text_input("X-RapidAPI-Key", type="password")
    st.caption("Use your RapidAPI key (starts with 'fc...')")
    st.markdown("[Get Free Key](https://rapidapi.com/theapiguy/api/free-nba)")
    
    # 2. OPENAI KEY
    openai_key_input = st.text_input("OpenAI API Key", type="password")
    
    if rapid_key_input: os.environ["RAPID_KEY"] = rapid_key_input.strip()
    if openai_key_input: os.environ["OPENAI_API_KEY"] = openai_key_input.strip()

# --- RAPID API CONFIG ---
RAPID_HOST = "free-nba.p.rapidapi.com"

def get_headers():
    return {
        "X-RapidAPI-Key": os.environ.get("RAPID_KEY"),
        "X-RapidAPI-Host": RAPID_HOST
    }

# --- TOOLS ---
def get_player_data(player_name):
    """Finds Player ID and Team ID"""
    try:
        url = f"https://{RAPID_HOST}/players"
        params = {"search": player_name, "per_page": "1"}
        resp = requests.get(url, headers=get_headers(), params=params, timeout=10)
        data = resp.json()['data']
        
        if not data: return None, None, None
        
        p = data[0]
        return p['id'], f"{p['first_name']} {p['last_name']}", p['team']
    except Exception as e:
        return None, None, str(e)

def find_next_game(team_id):
    """Finds the exact next scheduled game (ignoring past games)"""
    try:
        url = f"https://{RAPID_HOST}/games"
        # Search 7-day window
        today = datetime.now().strftime("%Y-%m-%d")
        next_week = (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d")
        
        params = {
            "team_ids[]": str(team_id),
            "start_date": today,
            "end_date": next_week,
            "per_page": "10"
        }
        resp = requests.get(url, headers=get_headers(), params=params, timeout=10)
        games = resp.json()['data']
        
        if not games: return "No games scheduled soon.", "TBD"
        
        # Sort by date to get the soonest
        games.sort(key=lambda x: x['date'])
        
        # Find first non-final game
        for g in games:
            if g['status'] != "Final":
                # Found it!
                home = g['home_team']['full_name']
                visitor = g['visitor_team']['full_name']
                
                # Clean Time format
                try:
                    # API often returns ISO format like '2025-11-22T00:00:00.000Z'
                    dt = datetime.strptime(g['date'], "%Y-%m-%dT%H:%M:%S.%fZ")
                    clean_time = dt.strftime("%a, %b %d")
                except:
                    clean_time = g['date'].split("T")[0]

                if g['home_team']['id'] == team_id:
                    return f"vs {visitor}", clean_time
                else:
                    return f"@ {home}", clean_time
                    
        return "No upcoming games (Season Paused/Ended)", "N/A"
    except Exception as e:
        return f"Error: {e}", "Error"

def get_deep_stats(player_id):
    """Fetches advanced stats (STL, BLK, FG%)"""
    try:
        url = f"https://{RAPID_HOST}/stats"
        # Fetch last 10 games to ensure we catch recent activity
        params = {
            "seasons[]": "2024", # Try 2024 first (covers 24-25 season)
            "player_ids[]": str(player_id),
            "per_page": "10"
        }
        
        resp = requests.get(url, headers=get_headers(), params=params, timeout=10)
        
        if resp.status_code == 401:
            return "API Error 401: Invalid Key. Please check your RapidAPI key."
            
        data = resp.json()['data']
        
        if not data:
            # Fallback: Try 2025 if 2024 yields nothing
            params["seasons[]"] = "2025"
            resp = requests.get(url, headers=get_headers(), params=params, timeout=10)
            data = resp.json()['data']
            if not data: return "No stats found for current season."

        games_log = []
        for g in data:
            date = g['game']['date'].split("T")[0]
            
            # Determine opponent
            if g['game']['home_team']['id'] == g['team']['id']:
                opp = f"vs {g['game']['visitor_team']['abbreviation']}"
            else:
                opp = f"@ {g['game']['home_team']['abbreviation']}"
            
            # Format Stats
            fg = f"{g['fg_pct']*100:.1f}%" if g['fg_pct'] else "0%"
            line = (f"PTS:{g['pts']} REB:{g['reb']} AST:{g['ast']} "
                    f"STL:{g['stl']} BLK:{g['blk']} TO:{g['turnover']} FG:{fg}")
            
            games_log.append(f"[{date} {opp}] {line}")
            
        # Sort descending (newest first) and take top 5
        games_log.sort(reverse=True)
        return "\n".join(games_log[:5])
        
    except Exception as e:
        return f"System Error: {e}"

# --- MAIN APP ---
if rapid_key_input and openai_key_input:
    
    llm_coach = ChatOpenAI(model="gpt-4o", temperature=0.5, api_key=openai_key_input)

    col1, col2 = st.columns(2)
    with col1: p_name = st.text_input("Player Name", "Devin Booker")
    
    if st.button("🚀 RUN ANALYSIS", type="primary"):
        
        with st.spinner("Connecting to RapidAPI..."):
            # 1. Get Player
            pid, full_name, team_data = get_player_data(p_name)
            if not pid:
                st.error(f"Player '{p_name}' not found.")
                st.stop()
            
            team_name = team_data['full_name']
            st.success(f"Found: {full_name} ({team_name})")
            
            # 2. Get Schedule
            opponent, game_time = find_next_game(team_data['id'])
            st.info(f"📅 NEXT GAME: {opponent} | ⏰ {game_time}")
            
            # 3. Get Deep Stats
            stats_report = get_deep_stats(pid)
            
            if "Error" in stats_report:
                st.error(stats_report)
                st.stop()
                
            with st.expander("📊 Raw Deep Stats", expanded=True):
                st.text(stats_report)

        # 4. AI Prediction
        with st.spinner("GPT-4o is generating the game plan..."):
            try:
                prompt = f"""
                You are an Expert NBA Betting Analyst.
                
                TARGET: {full_name}
                OPPONENT: {opponent}
                
                RECENT FORM (Last 5 Games):
                {stats_report}
                
                TASK:
                1. **Trend Analysis:** Is he hot or cold? (Look at FG% and PTS).
                2. **Defensive Stocks:** Is he getting Steals/Blocks?
                3. **Projection:** Predict his exact stat line (PTS/REB/AST) vs {opponent}.
                4. **Betting Pick:** Recommend one specific prop bet (e.g. "Over 26.5 Points").
                """
                
                prediction = llm_coach.invoke(prompt).content
                st.divider()
                st.markdown("### 🏆 Coach's Verdict")
                st.write(prediction)
                
            except Exception as e:
                st.error(f"AI Error: {e}")

elif not rapid_key_input:
    st.warning("⚠️ Please enter your RapidAPI Key to start.")
