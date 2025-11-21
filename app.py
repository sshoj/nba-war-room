import streamlit as st
from nba_api.stats.static import players
from nba_api.stats.endpoints import playergamelog
import pandas as pd

st.title("🔌 Source Data Connection Test")

# 1. Setup Anti-Blocking Headers (Crucial)
custom_headers = {
    'Host': 'stats.nba.com',
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:126.0) Gecko/20100101 Firefox/126.0',
    'Accept': 'application/json, text/plain, */*',
    'Referer': 'https://stats.nba.com/',
    'Connection': 'keep-alive',
}

if st.button("Test Connection to NBA.com"):
    with st.spinner("Pinging NBA Database..."):
        try:
            # 1. Find Player ID (Static Data)
            st.write("Step 1: Looking up player ID locally...")
            nba_players = players.get_players()
            lebron = next((p for p in nba_players if "LeBron James" in p['full_name']), None)
            st.success(f"✅ Found ID: {lebron['id']}")
            
            # 2. Fetch Live Stats (The Real Test)
            st.write("Step 2: Requesting live game logs (2024-25)...")
            gamelog = playergamelog.PlayerGameLog(
                player_id=lebron['id'], 
                season='2024-25', 
                headers=custom_headers,
                timeout=15
            )
            
            # 3. Show Raw Data
            df = gamelog.get_data_frames()[0]
            
            if not df.empty:
                st.success("✅ SUCCESS: Data received from NBA Source!")
                st.write("### Raw Data from Source:")
                st.dataframe(df[['GAME_DATE', 'MATCHUP', 'PTS', 'AST', 'REB']].head())
            else:
                st.warning("⚠️ Connection successful, but no games found (Season might not have started or filter is wrong).")
                
        except Exception as e:
            st.error(f"❌ BLOCKED: The source refused the connection.\nError: {e}")
