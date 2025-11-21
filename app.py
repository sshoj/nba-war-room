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
st.markdown("**Scout:** Gemini Pro (Data) | **Coach:** GPT-4o (Prediction)")

# --- SIDEBAR: DUAL KEYS ---
with st.sidebar:
    st.header("⚙️ Settings")
    
    # 1. Google Key (For the heavy lifting)
    google_key = st.text_input("Google Gemini Key (The Scout)", type="password")
    st.markdown("[Get Free Google Key](https://aistudio.google.com/app/apikey)")
    
    # 2. OpenAI Key (For the final verdict)
    openai_key = st.text_input("OpenAI API Key (The Coach)", type="password")
    st.markdown("[Get OpenAI Key](https://platform.openai.com/account/api-keys)")
    
    if not google_key or not openai_key:
        st.warning("⚠️ You need BOTH keys for Hybrid Mode.")
        st.stop()

    os.environ["GOOGLE_API_KEY"] = google_key
    os.environ["OPENAI_API_KEY"] = openai_key

# --- TOOLS (Gemini uses these) ---
def get_last_5_games_stats(player_name):
    try:
        nba_players = players.get_players()
        player = next((p for p in nba_players if p['full_name'].lower() == player_name.lower()), None)
        if not player: return "Error: Player not found."
        gamelog = playergamelog.PlayerGameLog(player_id=player['id'], season='2024-25')
        df = gamelog.get_data_frames()[0]
        cols = ['GAME_DATE', 'MATCHUP', 'WL', 'PTS', 'AST', 'REB', 'STL', 'FG_PCT']
        return df[cols].head(5).to_string(index=False)
    except: return "No data found."

def get_team_tactics(team_name):
    try:
        stats = leaguedashteamstats.LeagueDashTeamStats(measure_type='Advanced', season='2024-25')
        df = stats.get_data_frames()[0]
        team_stats = df[df['TEAM_NAME'].str.contains(team_name, case=False, na=False)]
        cols = ['TEAM_NAME', 'PACE', 'OFF_RATING', 'DEF_RATING', 'AST_TO']
        return team_stats[cols].to_string(index=False)
    except: return "Team not found."

search = DuckDuckGoSearchRun()

# --- INITIALIZE MODELS ---

# 1. THE SCOUT (Gemini) - Handles Tools, Data, and Web Search
llm_scout = ChatGoogleGenerativeAI(model="gemini-1.5-pro", temperature=0, google_api_key=google_key)

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

# 2. THE COACH (GPT-4o) - Pure reasoning, no tools (Cheap)
llm_coach = ChatOpenAI(model="gpt-4o", temperature=0.5, api_key=openai_key)

# --- UI ---
col1, col2 = st.columns(2)
with col1: p_name = st.text_input("Player Name", "Luka Doncic")
with col2: p_team = st.text_input("Player Team", "Dallas Mavericks")

if st.button("🚀 RUN HYBRID ANALYSIS", type="primary"):
    with st.spinner("Step 1: Gemini is scouting the data..."):
        try:
            # --- STEP 1: GEMINI GATHERS INTEL ---
            opp_query = f"Who is {p_team} playing next? Return ONLY team name."
            opponent = scout_agent.invoke({"input": opp_query})['output']
            st.info(f"Matchup: vs {opponent}")
            
            scout_prompt = f"""
            Gather intelligence for {p_name} ({p_team}) vs {opponent}.
            1. Get {p_name}'s last 5 games stats.
            2. Get {opponent}'s tactics (Pace/Defense).
            3. Search for {opponent}'s injury report.
            
            Output a detailed "Scouting Report" summarizing the data. 
            Do not make a prediction yet, just list the facts.
            """
            
            # Gemini does the hard work here
            scouting_report = scout_agent.invoke({"input": scout_prompt})['output']
            
            with st.expander("📄 Read Gemini's Scouting Report"):
                st.write(scouting_report)

    except Exception as e:
        st.error(f"Scouting Error: {e}")
        st.stop()

    with st.spinner("Step 2: GPT-4o is making the game plan..."):
        try:
            # --- STEP 2: GPT-4o MAKES THE DECISION ---
            # We feed the text summary to GPT (Low token usage)
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
