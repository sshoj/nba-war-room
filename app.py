import streamlit as st
import pandas as pd
from nba_api.stats.endpoints import teaminfocommon

st.title("🏀 NBA API Connection Test")

# 1. Setup Anti-Blocking Headers
custom_headers = {
    'Host': 'stats.nba.com',
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:126.0) Gecko/20100101 Firefox/126.0',
    'Accept': 'application/json, text/plain, */*',
    'Referer': 'https://stats.nba.com/',
    'Connection': 'keep-alive',
}

# 2. Dallas Mavericks ID
mavs_id = 1610612742

if st.button("Run Connection Test"):
    with st.spinner("Pinging NBA.com (Max 10 seconds)..."):
        try:
            # 3. Call API with Timeout
            mavs_info = teaminfocommon.TeamInfoCommon(
                team_id=mavs_id, 
                headers=custom_headers,
                timeout=10  # <--- CRITICAL: Prevents infinite hanging
            )
            
            # 4. Get Data
            df = mavs_info.get_data_frames()[0]
            
            # 5. Show Success
            st.success("✅ Connection Successful!")
            st.write("### Data Received:")
            st.dataframe(df) # Shows the interactive table
            
        except Exception as e:
            st.error("❌ Connection Failed")
            st.warning(f"Error Details: {e}")
            
            # Context for the user
            if "Read timed out" in str(e) or "403" in str(e):
                st.info("💡 NOTE: This error confirms that NBA.com is blocking Streamlit Cloud's IP address. You should stick to the RapidAPI or Web-Search method.")
