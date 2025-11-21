import streamlit as st
import requests
from langchain_openai import ChatOpenAI
import os
from datetime import datetime, timedelta
import pytz

# --- PAGE CONFIGURATION ---
st.set_page_config(page_title="NBA War Room (Pro)", page_icon="🏀", layout="wide")
st.title("🏀 NBA War Room (Pro Edition)")
st.markdown("**Data:** BallDontLie (Live) | **Logic:** Date-Aware | **Coach:** GPT-4o")

# --- SIDEBAR: SETTINGS ---
with st.sidebar:
    st.header("⚙️ Settings")
    bdl_key = st.text_input("BallDontLie API Key", type="password")
    st.markdown("[Get Free Key](https://balldontlie.io/)")
    
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
        return (data[0]['id'], data[0]['first_name'] + " " + data[0]['last_name'], data[0]['team']) if data else (None, None, None)
    except: return None, None, None

def get_advanced_stats(player_id):
    """Fetches detailed stats: PTS, REB, AST, STL, BLK, TO, FG%"""
    try:
        url = f"{BASE_URL}/stats"
        # Get last 10 games for better sample size
        params = {"seasons[]": 2024, "player_ids[]": player_id, "per_page": 10} 
        resp = requests.get(url, headers=get_headers(), params=params)
        data = resp.json()['data']
        
        if not data: return "No games found."
        
        games_log = []
        for g in data:
            # Parse "Deep Stats"
            date = g['game']['date'].split("T")[0]
            opp = g['game']['visitor_team']['abbreviation'] if g['game']['home_team']['id'] == g['team']['id'] else g['game']['home_team']['abbreviation']
            
            # Handle shooting percentages safely
            fg_pct = f"{g['fg_pct'] * 100:.1f}%" if g['fg_pct'] else "0%"
            fg3_pct = f"{g['fg3_pct'] * 100:.1f}%" if g['fg3_pct'] else "0%"
            
            # The "Deep" Stat Line
            stat_line = (f"PTS:{g['pts']} REB:{g['reb']} AST:{g['ast']} "
                         f"STL:{g['stl']} BLK:{g['blk']} TO:{g['turnover']} "
                         f"FG:{fg_pct} 3PT:{fg3_pct}")
            
            games_log.append(f"[{date} vs {opp}] {stat_line}")
            
        return "\n".join(games_log[:5]) # Return top 5 most recent
    except Exception as e: return f"Error: {e}"

def find_exact_next_game(team_id):
    """
    Smart Scheduler:
    1. Looks at the next 7 days.
    2. Filters out games that are already 'Final'.
    3. Returns the true next matchup with date/time.
    """
    try:
        url = f"{BASE_URL}/games"
        
        # Date Logic: Range from Today to Today+7 Days
        today = datetime.now().strftime("%Y-%m-%d")
        next_week = (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d")
        
        params = {
            "team_ids[]": team_id,
            "start_date": today,
            "end_date": next_week,
            "per_page": 5
        }
        
        resp = requests.get(url, headers=get_headers(), params=params)
        games = resp.json()['data']
        
        if not games: return None, "No games scheduled for the next 7 days."
        
        # Sort by Date/Time to be sure
        games.sort(key=lambda x: x['date'])
        
        # Logic: Find first game that is NOT "Final"
        for game in games:
            status = game['status'].strip() # e.g. "Final", "8:00 PM ET", "1st Qtr"
            
            # If game is finished, skip it (it's in the past)
            if status == "Final":
                continue
                
            # We found the next active game!
            home = game['home_team']['full_name']
            visitor = game['visitor_team']['full_name']
            date_str = game['date'].split("T")[0]
            
            if game['home_team']['id'] == team_id:
                return f"vs {visitor}", f"{date_str} @ {status}"
            else:
                return f"@ {home}", f"{date_str} @ {status}"
                
        return None, "No upcoming games found (Season might be over/paused)."
        
    except Exception as e: return None, f"Error: {e}"

# --- MAIN APP LOGIC ---
if bdl_key and openai_key:
    
    llm_coach = ChatOpenAI(model="gpt-4o", temperature=0.5, api_key=openai_key)

    col1, col2 = st.columns(2)
    with col1: p_name = st.text_input("Player Name", "Luka Doncic")
    
    if st.button("🚀 RUN PRO ANALYSIS", type="primary"):
        
        with st.spinner("🔍 Scouting Player & Schedule..."):
            # 1. Find Player
            pid, full_name, team_data = get_player_data(p_name)
            if not pid:
                st.error("Player not found!")
                st.stop()
            
            team_name = team_data['full_name']
            st.success(f"Found: {full_name} ({team_name})")
            
            # 2. Smart Schedule Search
            opponent, game_time = find_exact_next_game(team_data['id'])
            
            if not opponent:
                st.warning(f"Schedule Alert: {game_time}") # prints error msg
                st.stop()
                
            st.info(f"📅 NEXT GAME: {opponent} | ⏰ {game_time}")
            
            # 3. Get Deep Stats
            stats_report = get_advanced_stats(pid)
            
            with st.expander("📊 Read Deep Stats (Steals/Blocks/FG%)", expanded=True):
                st.text(stats_report)
                
        # 4. AI Analysis
        if stats_report:
            with st.spinner("🧠 GPT-4o is calculating win probability..."):
                try:
                    prompt = f"""
                    You are an Elite NBA Scout and Betting Analyst.
                    
                    TARGET PLAYER: {full_name} ({team_name})
                    NEXT MATCHUP: {opponent} (Time: {game_time})
                    
                    DEEP STATS (Last 5 Games):
                    {stats_report}
                    
                    YOUR MISSION:
                    1. **Form Check:** Look at his FG% and Turnovers. Is he efficient or sloppy right now?
                    2. **Defensive Impact:** Is he getting Steals/Blocks?
                    3. **Prediction:** Project his stat line (PTS/REB/AST) for the upcoming game.
                    4. **Verdict:** Give a specific "Player Prop" recommendation (e.g., "Over 28.5 Points").
                    """
                    
                    prediction = llm_coach.invoke(prompt).content
                    st.divider()
                    st.markdown("### 🏆 Official Scouting Report")
                    st.write(prediction)
                    
                except Exception as e:
                    st.error(f"AI Error: {e}")

elif not bdl_key:
    st.warning("⚠️ Please enter your BallDontLie API Key to start.")
