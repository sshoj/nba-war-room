{\rtf1\ansi\ansicpg1252\cocoartf2867
\cocoatextscaling0\cocoaplatform0{\fonttbl\f0\fmodern\fcharset0 Courier;}
{\colortbl;\red255\green255\blue255;\red0\green0\blue0;}
{\*\expandedcolortbl;;\cssrgb\c0\c0\c0;}
\margl1440\margr1440\vieww11520\viewh8400\viewkind0
\deftab720
\pard\pardeftab720\partightenfactor0

\f0\fs26 \cf0 \expnd0\expndtw0\kerning0
\outl0\strokewidth0 \strokec2 import streamlit as st\
import pandas as pd\
from nba_api.stats.static import players\
from nba_api.stats.endpoints import playergamelog, leaguedashteamstats\
from langchain.agents import initialize_agent, AgentType, Tool\
from langchain_openai import ChatOpenAI\
from langchain_community.tools import DuckDuckGoSearchRun\
import os\
\
# --- PAGE CONFIGURATION ---\
st.set_page_config(page_title="NBA War Room", page_icon="\uc0\u55356 \u57280 ")\
\
st.title("\uc0\u55356 \u57280  AI NBA War Room")\
st.write("The ultimate pre-game analysis tool for your iPhone.")\
\
# --- SIDEBAR: SETTINGS ---\
with st.sidebar:\
    st.header("\uc0\u9881 \u65039  Settings")\
    api_key = st.text_input("Enter OpenAI API Key", type="password")\
    st.markdown("[Get an API Key](https://platform.openai.com/account/api-keys)")\
    \
    if not api_key:\
        st.warning("\uc0\u9888 \u65039  Please enter your OpenAI API Key to start.")\
        st.stop()\
\
    os.environ["OPENAI_API_KEY"] = api_key\
\
# --- DEFINE PYTHON TOOLS ---\
\
def get_last_5_games_stats(player_name):\
    """Fetches last 5 games stats for a player."""\
    nba_players = players.get_players()\
    player = next((p for p in nba_players if p['full_name'].lower() == player_name.lower()), None)\
    if not player: return "Error: Player not found."\
    \
    # Fetch Log (Season 2024-25) - Update season string if needed\
    gamelog = playergamelog.PlayerGameLog(player_id=player['id'], season='2024-25')\
    df = gamelog.get_data_frames()[0]\
    cols = ['GAME_DATE', 'MATCHUP', 'WL', 'PTS', 'AST', 'REB', 'STL', 'FG_PCT']\
    return df[cols].head(5).to_string(index=False)\
\
def get_team_tactics(team_name):\
    """Fetches team advanced stats (Pace, Ratings)."""\
    stats = leaguedashteamstats.LeagueDashTeamStats(measure_type='Advanced', season='2024-25')\
    df = stats.get_data_frames()[0]\
    team_stats = df[df['TEAM_NAME'].str.contains(team_name, case=False, na=False)]\
    if team_stats.empty: return "Error: Team not found."\
    cols = ['TEAM_NAME', 'PACE', 'OFF_RATING', 'DEF_RATING', 'AST_TO']\
    return team_stats[cols].to_string(index=False)\
\
search = DuckDuckGoSearchRun()\
\
# --- INITIALIZE AGENTS ---\
llm = ChatOpenAI(temperature=0, model="gpt-4-turbo")\
\
tools = [\
    Tool(name="GetLast5Games", func=get_last_5_games_stats, description="Get recent player stats."),\
    Tool(name="GetTeamTactics", func=get_team_tactics, description="Get team advanced stats (Pace, Ratings)."),\
    Tool(name="WebSearch", func=search.run, description="Search for schedule and injuries.")\
]\
\
agent = initialize_agent(\
    tools, llm, agent=AgentType.ZERO_SHOT_REACT_DESCRIPTION, verbose=True, handle_parsing_errors=True\
)\
\
# --- THE APP INTERFACE ---\
\
# 1. User Inputs\
col1, col2 = st.columns(2)\
with col1:\
    player_name = st.text_input("Player Name", "Luka Doncic")\
with col2:\
    player_team = st.text_input("Player Team", "Dallas Mavericks")\
\
if st.button("\uc0\u55357 \u56960  RUN WAR ROOM ANALYSIS", type="primary"):\
    with st.spinner("Consulting the Analysts, Scouts, and Coaches..."):\
        \
        # Step 1: Find Opponent\
        st.info(f"\uc0\u55357 \u56589  Finding next opponent for \{player_team\}...")\
        opp_query = f"Who is the \{player_team\} playing next in the NBA? Return ONLY the team name."\
        opponent = agent.invoke(\{"input": opp_query\})['output']\
        st.success(f"Matchup Identified: vs \{opponent\}")\
        \
        # Step 2: Run Full Analysis\
        prompt = f"""\
        Perform a full pre-game analysis for \{player_name\} (\{player_team\}) vs \{opponent\}.\
        \
        1. Use 'GetLast5Games' to check \{player_name\}'s recent form.\
        2. Use 'GetTeamTactics' to check \{opponent\}'s system (Pace, Def Rating).\
        3. Use 'WebSearch' to check \{opponent\}'s injury report today.\
        \
        Synthesize this into a final prediction report.\
        Format the output clearly with:\
        - **Player Form:** (Hot/Cold)\
        - **Tactical Matchup:** (Fast/Slow, Defensive gaps)\
        - **Injury Intel:** (Who is out)\
        - **PREDICTION:** (Winner and estimated score)\
        """\
        \
        response = agent.invoke(\{"input": prompt\})\
        \
        # Step 3: Display Result\
        st.divider()\
        st.markdown("### \uc0\u55357 \u56541  Official Scouting Report")\
        st.write(response['output'])}