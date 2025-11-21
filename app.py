import streamlit as st
import requests
from langchain_openai import ChatOpenAI
import os
import pandas as pd
from datetime import datetime, timedelta

# --- PAGE CONFIGURATION ---
st.set_page_config(page_title="NBA War Room (All-Star)", page_icon="⭐", layout="wide")
st.title("🏀 NBA War Room (All-Star Edition)")

# --- SIDEBAR ---
with st.sidebar:
    st.header("⚙️ Settings")
    bdl_key = st.text_input("BallDontLie API Key", type="password")
    openai_key = st.text_input("OpenAI API Key", type="password")
    
    if bdl_key: os.environ["BDL_API_KEY"] = bdl_key.strip()
    if openai_key: os.environ["OPENAI_API_KEY"] = openai_key.strip()
    
    st.divider()
    st.header("🔎 Analysis Mode")
    # THE NEW FEATURE: Switch between "Recent" and "Head-to-Head"
    analysis_mode = st.radio("Select Data Focus:", ["Recent Form (Last 5)", "Head-to-Head (Vs Opponent)"])

# --- API CONFIG ---
BASE_URL = "https://api.balldontlie.io/v1"

def get_headers():
    return {"Authorization": os.environ.get("BDL_API_KEY")}

# --- TOOLS ---
def get_player_info(name):
    try:
        url = f"{BASE_URL}/players"
        params = {"search": name, "per_page": "1"}
        resp = requests.get(url, headers=get_headers(), params=params)
        data = resp.json()['data']
        if not data: return None
        return data[0] # Returns full player object
    except: return None

def get_next_game(team_id):
    """Finds next game and opponent ID"""
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
        if not data: return None, None, None
        
        data.sort(key=lambda x: x['date'])
        game = data[0]
        
        if game['home_team']['id'] == team_id:
            return game['visitor_team']['full_name'], game['visitor_team']['id'], game['date']
        else:
            return game['home_team']['full_name'], game['home_team']['id'], game['date']
    except: return None, None, None

def get_stats(player_id, team_id, opponent_id=None, mode="Recent Form (Last 5)"):
    """
    SMART FETCH:
    - If Mode is 'Recent': Gets last 5 games regardless of opponent.
    - If Mode is 'Head-to-Head': Gets last 5 games VS THAT OPPONENT (spanning seasons).
    """
    try:
        url = f"{BASE_URL}/stats"
        params = {
            "player_ids[]": str(player_id),
            "per_page": "100" # Get a large batch to filter
        }
        
        # If H2H, we might need to look back further, so we grab 2023-2025
        if mode == "Head-to-Head (Vs Opponent)":
            params["seasons[]"] = ["2023", "2024", "2025"]
        else:
            params["seasons[]"] = ["2025"] # Recent form only cares about now

        resp = requests.get(url, headers=get_headers(), params=params)
        data = resp.json()['data']
        
        # Sort newest first
        data.sort(key=lambda x: x['game']['date'], reverse=True)
        
        filtered_games = []
        for g in data:
            # FILTER: Head to Head
            if mode == "Head-to-Head (Vs Opponent)" and opponent_id:
                # Check if this game involved the opponent
                home_id = g['game']['home_team_id']
                visit_id = g['game']['visitor_team_id']
                if home_id != opponent_id and visit_id != opponent_id:
                    continue # Skip irrelevant games
            
            # Format Date
            date = g['game']['date'].split("T")[0]
            
            # Determine Opponent Label
            is_home = g['game']['home_team_id'] == team_id
            if is_home:
                opp_name = g['game']['visitor_team']['abbreviation']
                loc = "vs"
            else:
                opp_name = g['game']['home_team']['abbreviation']
                loc = "@"
                
            # Stats
            if g['min']:
                fg_pct = f"{g['fg_pct']*100:.1f}%" if g['fg_pct'] else "0%"
                line = f"MIN:{g['min']} PTS:{g['pts']} REB:{g['reb']} AST:{g['ast']} FG:{fg_pct}"
            else:
                line = "DNP (Did Not Play)"
                
            filtered_games.append(f"[{date}] {loc} {opp_name} | {line}")
            
            if len(filtered_games) >= 5: break # Only keep top 5 matches
            
        return "\n".join(filtered_games)
    except Exception as e: return f"Error: {e}"

# --- MAIN APP ---
if bdl_key and openai_key:
    
    llm = ChatOpenAI(model="gpt-4o", temperature=0.5, api_key=openai_key)
    
    col1, col2 = st.columns(2)
    with col1: p_name = st.text_input("Player Name", "Luka Doncic")
    
    # Initialize Chat History
    if "messages" not in st.session_state:
        st.session_state.messages = []

    if st.button("🚀 RUN ANALYSIS", type="primary"):
        # Clear previous chat on new run
        st.session_state.messages = []
        
        with st.spinner("Connecting to War Room..."):
            
            # 1. Get Player
            player = get_player_info(p_name)
            if not player:
                st.error("Player not found.")
                st.stop()
            
            pid = player['id']
            tid = player['team']['id']
            p_full = f"{player['first_name']} {player['last_name']}"
            
            st.success(f"Found: **{p_full}**")
            
            # 2. Get Next Matchup
            opp_name, opp_id, date_str = get_next_game(tid)
            if not opp_name:
                st.warning("No upcoming schedule found.")
                opp_name = "Unknown"
                opp_id = None
            else:
                st.info(f"Matchup: vs {opp_name}")

            # 3. Get Stats (The Smart Part)
            # We pass the mode (Recent vs H2H) and the Opponent ID
            stats_log = get_stats(pid, tid, opp_id, analysis_mode)
            
            with st.expander(f"📊 Stats Mode: {analysis_mode}", expanded=True):
                if not stats_log:
                    st.warning("No games found matching criteria.")
                else:
                    st.code(stats_log)
                    
            # 4. GPT Analysis
            if stats_log:
                sys_prompt = f"""
                You are an NBA Analyst.
                PLAYER: {p_full}
                MODE: {analysis_mode}
                DATA:
                {stats_log}
                
                Write a concise prediction for the game against {opp_name}.
                """
                report = llm.invoke(sys_prompt).content
                st.write("### 📝 Analyst Report")
                st.write(report)
                
                # Save context for chat
                st.session_state['context'] = f"Player: {p_full}. Mode: {analysis_mode}. Stats: {stats_log}"

    # --- CHAT INTERFACE ---
    st.divider()
    st.subheader("💬 Chat with the Analyst")
    
    # Display chat history
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    # User Input
    if prompt := st.chat_input("Ask about the stats (e.g., 'Is he consistent?'):"):
        # 1. Show User Message
        st.chat_message("user").markdown(prompt)
        st.session_state.messages.append({"role": "user", "content": prompt})
        
        # 2. Generate Response
        if 'context' in st.session_state:
            full_prompt = f"Context: {st.session_state['context']}\n\nUser Question: {prompt}"
            response = llm.invoke(full_prompt).content
        else:
            response = "Please run the analysis first to load data."
            
        # 3. Show Bot Message
        st.chat_message("assistant").markdown(response)
        st.session_state.messages.append({"role": "assistant", "content": response})

elif not bdl_key:
    st.warning("⚠️ Enter Keys to start.")
