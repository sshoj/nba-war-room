import streamlit as st
import requests
import json

st.title("🔌 'NBA API Free Data' Connection Test")

# 1. YOUR SPECIFIC CONFIGURATION
url = "https://nba-api-free-data.p.rapidapi.com/nba-atlantic-team-list"
headers = {
    "x-rapidapi-host": "nba-api-free-data.p.rapidapi.com",
    # ⚠️ REPLACE THIS WITH YOUR NEW KEY AFTER ROTATING IT
    "x-rapidapi-key": st.secrets.get("RAPID_KEY", "PASTE_YOUR_KEY_HERE")
}

if st.button("Test Connection"):
    try:
        st.write(f"Connecting to: `{url}`...")
        response = requests.get(url, headers=headers)
        
        if response.status_code == 200:
            st.success("✅ Connection Successful!")
            data = response.json()
            st.write("### Response Data:")
            st.json(data)
        elif response.status_code == 403:
            st.error("❌ 403 Forbidden: You might need to Subscribe to the API plan on RapidAPI.")
        else:
            st.error(f"❌ Error {response.status_code}: {response.text}")
            
    except Exception as e:
        st.error(f"System Error: {e}")
