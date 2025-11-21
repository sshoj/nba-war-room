import streamlit as st
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI
from ddgs import DDGS
import os
import time
import random

# --- PAGE CONFIGURATION ---
st.set_page_config(page_title="NBA War Room (Unblockable)", page_icon="🏀")
st.title("🏀 NBA War Room (Unblockable)")
st.markdown("**Mode:** Anti-Blocking | **Scout:** Gemini 2.5 | **Coach:** GPT-4o")

# --- SIDEBAR: SETTINGS ---
with st.sidebar:
    st.header("⚙️ Settings")
    
    google_key_input = st.text_input("Google Gemini Key", type="password")
    if google_key_input: os.environ["GOOGLE_API_KEY"] = google_key_input.strip()
    
    openai_key_input = st.text_input("OpenAI API Key", type="password")
    if openai_key_input: os.environ["OPENAI_API_KEY"] = openai_key_input.strip()
    
    st.divider()
    manual_opponent = st.text_input("Manual Opponent (Optional)", placeholder="e.g. Celtics")

# --- ROBUST SEARCH TOOL (Bypasses 202 Ratelimit) ---
def safe_search(query):
    """
    Uses the 'html' backend to bypass API rate limits.
    Retries with exponential backoff if blocked.
    """
    max_retries = 3
    for attempt in range(max_retries):
        try:
            # Sleep random amount to look human (2-4 seconds)
            time.sleep(random.uniform(2, 4))
            
            # Use 'html' backend which is slower but rarely blocked
            with DDGS() as ddgs:
                results = list(ddgs.text(query, backend="html", max_results=1))
                
            if results:
                return results[0]['body']
            else:
                return "No results found."
                
        except Exception as e:
            if "Ratelimit" in str(e) and attempt < max_retries - 1:
                st.toast(f"Rate limited... retrying in 5s (Attempt {attempt+1})")
                time.sleep(5) # Wait longer before retry
                continue
            return f"Search Error: {e}"

# --- MAIN APP ---
if google_key_input and openai_key_input:
    
    # Initialize Models
    # We use transport="rest" to avoid Streamlit crashes
    llm_scout = ChatGoogleGenerativeAI(
        model="gemini-2.5-flash", 
        temperature=0, 
        transport="rest"
    )
    llm_coach = ChatOpenAI(model="gpt-4o", temperature=0.5)

    # --- UI ---
    col1, col2 = st.columns(2)
    with col1: p_name = st.text_input("Player Name", "Luka Doncic")
    with col2: p_team = st.text_input("Player Team", "Dallas Mavericks")

    if st.button("🚀 RUN ROBUST ANALYSIS", type="primary"):
        
        scouting_report = ""
        
        # --- PHASE 1: PYTHON GATHERS DATA (Stealth Mode) ---
        with st.spinner("Step 1: Python is searching (Stealth Mode)..."):
            
            # 1. Determine Opponent
            if manual_opponent:
                opponent = manual_opponent
                st.success(f"Targeting Matchup: {p_team} vs {opponent}")
            else:
                # Search for schedule
                schedule_query = f"Who are the {p_team} playing next in November 2025? Return team name."
                opponent_raw = safe_search(schedule_query)
                opponent = opponent_raw[:50] # Keep it short
                st.info(f"Found Matchup Data: {opponent}")
            
            # 2. Run Key Searches (One by one to be safe)
            
            # Player Stats
            st.write(f"🔎 Searching for {p_name}'s recent stats...")
            raw_p_stats = safe_search(f"{p_name} last 5 games stats box score November 2025")
            
            # Team Tactics
            st.write(f"🔎 Searching for {opponent} defensive ratings...")
            raw_t_stats = safe_search(f"{opponent} NBA defensive rating pace stats 2025")
            
            # Injuries
            st.write(f"🔎 Searching for {opponent} injury report...")
            raw_injuries = safe_search(f"{opponent} NBA injury report today November 2025")

        # --- PHASE 2: GEMINI SUMMARIZES ---
        with st.spinner("Step 2: Gemini is analyzing the data..."):
            try:
                scout_prompt = f"""
                You are an NBA Scout. I have gathered raw search data for you.
                Target: {p_name} vs {opponent}.
                
                RAW DATA:
                1. PLAYER STATS: {raw_p_stats}
                2. OPPONENT STATS: {raw_t_stats}
                3. INJURIES: {raw_injuries}
                
                TASK:
                Write a concise "Scouting Report".
                - If the data says "Rate limit", admit you couldn't find it.
                - Otherwise, summarize the Points/Rebounds/Assists and Team Defense.
                """
                
                scouting_report = llm_scout.invoke(scout_prompt).content
                
                with st.expander("📄 Read Scout's Report", expanded=True):
                    st.write(scouting_report)

            except Exception as e:
                st.error(f"Gemini Error: {e}")
                st.stop()

        # --- PHASE 3: GPT-4o PREDICTS ---
        if scouting_report:
            with st.spinner("Step 3: GPT-4o is predicting the game..."):
                try:
                    coach_prompt = f"""
                    You are an NBA Head Coach. 
                    Based on this scouting report, predict the winner and score.
                    
                    REPORT:
                    {scouting_report}
                    """
                    final_prediction = llm_coach.invoke(coach_prompt).content
                    
                    st.divider()
                    st.markdown("### 🏆 Official Prediction")
                    st.write(final_prediction)
                    
                except Exception as e:
                    st.error(f"Coaching Failed: {e}")

elif not google_key_input or not openai_key_input:
    st.warning("⚠️ Please enter both API Keys to start.")
