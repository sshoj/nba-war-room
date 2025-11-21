import streamlit as st
import pandas as pd
from nba_api.stats.static import players
from nba_api.stats.endpoints import playergamelog, leaguedashteamstats
from langchain.agents import initialize_agent, AgentType
from langchain.tools import Tool
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI
from langchain_community.tools import DuckDuckGoSearchRun
import os

# --- PAGE CONFIGURATION ---
st.set_page_config(page_title="NBA War Room (Hybrid)", page_icon="🏀")
st.title("🏀 Hybrid AI War Room")
st.markdown("**Scout:** Gemini 1.5 Flash (Free) | **Coach:** GPT-4o (Paid)")

# --- SIDEBAR: SETTINGS ---
with st.sidebar:
    st.header("⚙️ Settings")
    
    # 1. Google Key (Scout) - Cleaned input
    google_key_input = st.text_input("Google Gemini Key", type="password")
    google_key = google_key_input.strip() if google_key_input else None
    st.markdown("[Get Free Google Key](https://aistudio.google.com/app/apikey)")
    
    # 2. OpenAI Key (Coach) - Cleaned input
    openai_key_input = st.text_input("OpenAI API Key", type="password")
    openai_key = openai_key_input.strip() if openai_key_input else None
    st.markdown("[Get OpenAI Key](https://platform.openai.com/account/api-keys)")
    
    if google_key: os.environ["GOOGLE_API_KEY"] = google_key
    if openai_key: os.environ["OPENAI_API_KEY"] = openai_key

# --- CONFIG: NBA API HEADERS (Crucial for Cloud) ---
# This disguises the app as a real browser to avoid being blocked by NBA.com
custom_headers = {
    'Host': 'stats.nba.com',
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:126.0) Gecko/20100101 Firefox/126.0',
    'Accept': 'application/json, text/plain, */*',
    'Referer': 'https://stats.nba.com/',
    'Connection': 'keep-alive',
}

# --- TOOLS ---
def get_last_5_games_stats(player_name):
    try:
        nba_players = players.get_players()
        # FUZZY MATCH: "Luka" will find "Luka Doncic"
        player = next((p for p in nba_players if player_name.lower() in p['full_name'].lower()), None)
        
        if not player: 
            return f"Error: Player '{player_name}' not found. Try the full name."
        
        # SEASON UPDATE: Changed to '2025-26' for Nov 2025
        gamelog = playergamelog.PlayerGameLog(
            player_id=player['id'], 
            season='2025-26', 
            headers=custom_headers
        )
        df = gamelog.get_data_frames()[0]
        
        if df.empty:
            return f"No games found for {player['full_name']} in 2025-26 season yet."

        cols = ['GAME_DATE', 'MATCHUP', 'WL', 'PTS', 'AST', 'REB', 'STL', 'FG_PCT']
        return df[cols].head(5).to_string(index=False)
        
    except Exception as e:
        return f"Error retrieving stats: {str(e)}"

def get_team_tactics(team_name):
    try:
        # SEASON UPDATE: Changed to '2025-26'
        stats = leaguedashteamstats.LeagueDashTeamStats(
            measure_type='Advanced', 
            season='2025-26', 
            headers=custom_headers
        )
        df = stats.get_data_frames()[0]
        
        team_stats = df[df['TEAM_NAME'].str.contains(team_name, case=False, na=False)]
        
        if team_stats.empty:
            return f"Error: Team '{team_name}' not found."
            
        cols = ['TEAM_NAME', 'PACE', 'OFF_RATING', 'DEF_RATING', 'AST_TO']
        return team_stats[cols].to_string(index=False)
        
    except Exception as e:
        return f"Error retrieving tactics: {str(e)}"

search = DuckDuckGoSearchRun()

# --- MAIN APP LOGIC ---
if google_key and openai_key:
    # 1. THE SCOUT (Gemini 1.5 Flash)
    llm_scout = ChatGoogleGenerativeAI(
        model="gemini-1.5-flash",  # Standard Stable Model
        temperature=0, 
        google_api_key=google_key,
        transport="rest"
    )

    tools = [
        Tool(name="GetLast5Games", func=get_last_5_games_stats, description="Get recent player stats."),
        Tool(name="GetTeamTactics", func=get_team_tactics, description="Get team advanced stats."),
        Tool(name="WebSearch", func=search.run, description="Search for schedule and injuries.")
    ]

    scout_agent = initialize_agent(
        tools, 
        llm_scout, 
        agent=AgentType.ZERO_SHOT_REACT_DESCRIPTION, 
        verbose=True, 
        handle_parsing_errors=True
    )

    # 2. THE COACH (GPT-4o)
    llm_coach = ChatOpenAI(model="gpt-4o", temperature=0.5, api_key=openai_key)

    # --- UI ---
    col1, col2 = st.columns(2)
    with col1: p_name = st.text_input("Player Name", "Luka Doncic")
    with col2: p_team = st.text_input("Player Team", "Dallas Mavericks")

    if st.button("🚀 RUN HYBRID ANALYSIS", type="primary"):
        
        scouting_report = ""
        with st.spinner("Step 1: Gemini (Scout) is gathering data..."):
            try:
                # 1. Find Opponent
                opp_query = f"Who is the {p_team} playing next in Nov 2025? Return ONLY the team name."
                opponent_raw = scout_agent.invoke({"input": opp_query})['output']
                st.info(f"Matchup: vs {opponent_raw}")
                
                # 2. Gather Stats
                scout_prompt = f"""
                Gather intelligence for {p_name} ({p_team}) vs {opponent_raw}.
                1. Use 'GetLast5Games' to get {p_name}'s stats.
                2. Use 'GetTeamTactics' to get {opponent_raw}'s tactics.
                3. Use 'WebSearch' to find {opponent_raw}'s injury report.
                
                Output a detailed "Scouting Report".
                """
                scouting_report = scout_agent.invoke({"input": scout_prompt})['output']
                
                with st.expander("📄 Read Scouting Report"):
                    st.write(scouting_report)

            except Exception as e:
                st.error(f"Scouting Error: {e}")
                st.stop()

        if scouting_report:
            with st.spinner("Step 2: GPT-4o (Coach) is making the game plan..."):
                try:
                    coach_prompt = f"""
                    You are an expert NBA Head Coach. Read this scouting report and make a final game prediction.
                    
                    SCOUTING REPORT:
                    {scouting_report}
                    
                    YOUR TASK:
                    1. Predict the Winner.
                    2. Estimate the Score.
                    3. Give one "Key to the Game".
                    """
                    final_prediction = llm_coach.invoke(coach_prompt)
                    
                    st.divider()
                    st.markdown("### 🏆 GPT-4o Final Verdict")
                    st.write(final_prediction.content)
                    
                except Exception as e:
                    st.error(f"Coaching Error: {e}")

elif not google_key or not openai_key:
    st.info("👈 Please enter both API Keys in the sidebar to start.")
