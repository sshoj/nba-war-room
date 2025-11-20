import streamlit as st
import pandas as pd
from nba_api.stats.static import players
from nba_api.stats.endpoints import playergamelog, leaguedashteamstats
from langchain.agents import initialize_agent, AgentType
from langchain.tools import Tool
from langchain_openai import ChatOpenAI
from langchain_community.tools import DuckDuckGoSearchRun
import os

# --- PAGE CONFIGURATION ---
st.set_page_config(page_title="NBA War Room", page_icon="🏀")
st.title("🏀 AI NBA War Room")

# --- SIDEBAR: SETTINGS ---
with st.sidebar:
    st.header("⚙️ Settings")
    api_key = st.text_input("Enter OpenAI API Key", type="password")
    if not api_key:
        st.warning("⚠️ Please enter your OpenAI API Key to start.")
        st.stop()
    os.environ["OPENAI_API_KEY"] = api_key

# --- TOOLS ---
def get_last_5_games_stats(player_name):
    nba_players = players.get_players()
    player = next((p for p in nba_players if p['full_name'].lower() == player_name.lower()), None)
    if not player: return "Error: Player not found."
    gamelog = playergamelog.PlayerGameLog(player_id=player['id'], season='2024-25')
    df = gamelog.get_data_frames()[0]
    if df.empty: return "No games found."
    cols = ['GAME_DATE', 'MATCHUP', 'WL', 'PTS', 'AST', 'REB', 'STL', 'FG_PCT']
    return df[cols].head(5).to_string(index=False)

def get_team_tactics(team_name):
    stats = leaguedashteamstats.LeagueDashTeamStats(measure_type='Advanced', season='2024-25')
    df = stats.get_data_frames()[0]
    team_stats = df[df['TEAM_NAME'].str.contains(team_name, case=False, na=False)]
    if team_stats.empty: return "Error: Team not found."
    cols = ['TEAM_NAME', 'PACE', 'OFF_RATING', 'DEF_RATING', 'AST_TO']
    return team_stats[cols].to_string(index=False)

search = DuckDuckGoSearchRun()

# --- AGENT ---
llm = ChatOpenAI(temperature=0, model="gpt-4o", api_key=api_key)
tools = [
    Tool(name="GetLast5Games", func=get_last_5_games_stats, description="Get recent player stats."),
    Tool(name="GetTeamTactics", func=get_team_tactics, description="Get team advanced stats."),
    Tool(name="WebSearch", func=search.run, description="Search for schedule and injuries.")
]
agent = initialize_agent(tools, llm, agent=AgentType.ZERO_SHOT_REACT_DESCRIPTION, verbose=True, handle_parsing_errors=True)

# --- UI ---
col1, col2 = st.columns(2)
with col1: p_name = st.text_input("Player Name", "Luka Doncic")
with col2: p_team = st.text_input("Player Team", "Dallas Mavericks")

if st.button("🚀 RUN WAR ROOM", type="primary"):
    with st.spinner("Analyzing..."):
        try:
            opp_query = f"Who is {p_team} playing next? Return ONLY team name."
            opponent = agent.invoke({"input": opp_query})['output']
            st.success(f"Matchup: vs {opponent}")
            
            prompt = f"Analyze {p_name} ({p_team}) vs {opponent}. Check last 5 games, team tactics, and injuries. Give a prediction."
            response = agent.invoke({"input": prompt})
            st.write(response['output'])
        except Exception as e:
            st.error(f"Error: {e}")
