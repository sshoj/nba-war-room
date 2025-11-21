import streamlit as st
import requests
import os

st.title("🩺 API Connection Doctor")

# 1. Enter Key
api_key = st.text_input("Enter BallDontLie API Key", type="password")

if st.button("Run Diagnosis"):
    if not api_key:
        st.error("Please enter a key.")
        st.stop()

    headers = {"Authorization": api_key}

    # --- TEST 1: AUTHENTICATION (The "Hello World" of this API) ---
    st.subheader("Test 1: Authentication Check (/players)")
    try:
        # We ask for just 1 player to keep it light
        url_1 = "https://api.balldontlie.io/v1/players"
        resp_1 = requests.get(url_1, headers=headers, params={"per_page": 1})
        
        if resp_1.status_code == 200:
            st.success(f"✅ Success! (Status: {resp_1.status_code})")
            st.json(resp_1.json())
        else:
            st.error(f"❌ Failed (Status: {resp_1.status_code})")
            st.write("Response:", resp_1.text)
            st.warning("Diagnostic: If this failed, your API KEY is invalid or formatted wrong.")
            st.stop() # Stop here if auth fails
            
    except Exception as e:
        st.error(f"System Error: {e}")

    st.divider()

    # --- TEST 2: PERMISSIONS CHECK (/stats) ---
    st.subheader("Test 2: Plan Permissions Check (/stats)")
    try:
        # We ask for stats for a specific season
        url_2 = "https://api.balldontlie.io/v1/stats"
        params_2 = {"seasons[]": 2024, "per_page": 1}
        resp_2 = requests.get(url_2, headers=headers, params=params_2)
        
        if resp_2.status_code == 200:
            st.success(f"✅ Success! (Status: {resp_2.status_code})")
            st.write("Good news! Your key has access to Player Stats.")
            st.json(resp_2.json())
        else:
            st.error(f"❌ Failed (Status: {resp_2.status_code})")
            st.write("Response:", resp_2.text)
            st.warning("Diagnostic: Your Key is valid, BUT your Plan does not allow access to Stats.")
            
    except Exception as e:
        st.error(f"System Error: {e}")
