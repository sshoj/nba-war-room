import streamlit as st
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI
from langchain_community.tools import DuckDuckGoSearchRun
import os
import time

# --- PAGE CONFIGURATION ---
st.set_page_config(page_title="NBA War Room (Pipeline)", page_icon="🏀")
st.title("🏀 NBA War Room (Pipeline Mode)")
st.markdown("**Mode:** Rate-Limit Proof | **Scout:** Python + Gemini | **Coach:** GPT-4o")

# --- SIDEBAR: SETTINGS ---
with st.sidebar:
    st.header("⚙️ Settings")
    
    google_key_input = st.text_input("Google Gemini Key", type="password")
    if google_key_input: os.environ["GOOGLE_API_KEY"] = google_key_input.strip()
    
    openai_key_input = st.text_input("OpenAI API Key", type="password")
    if openai_key_input: os.environ["OPENAI_API_KEY"] = openai_key_input.strip()
    
    st.markdown("---")
    manual_opponent = st.text_input("Manual Opponent (Optional)", placeholder="e.g. Celtics")

# --- TOOLS (No Agents, Just Functions) ---
search = DuckDuckGoSearchRun()

def safe_search(query):
    """Runs a search with a tiny pause to be safe."""
    try:
        time.sleep(1) # Sleep 1s to be nice to DuckDuckGo
        results = search.run(query)
        return results
    except Exception as e:
        return f"Search Failed: {e}"

# --- MAIN APP ---
if google_key_input and openai_key_input:
    
    # Initialize Models (Simple Chat Models, No Agents)
    llm_scout = ChatGoogleGenerativeAI(model="gemini-2.5-flash", temperature=0, transport="rest")
    llm_coach = ChatOpenAI(model="gpt-4o", temperature=0.5)

    # --- UI ---
    col1, col2 = st.columns(2)
    with col1: p_name = st.text_input("Player Name", "Luka Doncic")
    with col2: p_team = st.text_input("Player Team", "Dallas Mavericks")

    if st.button("🚀 RUN PIPELINE ANALYSIS", type="primary"):
        
        # --- PHASE 1: PYTHON GATHERS DATA (0 API Calls) ---
        with st.spinner("Step 1: Python is surfing the web (Saving API Credits)..."):
            
            # 1. Determine Opponent
            if manual_opponent:
                opponent = manual_opponent
            else:
                # We do one quick search to find the opponent
                schedule_query = f"Who are the {p_team} playing next in the NBA? (Date: November 2025). Return team name."
                opponent_raw = safe_search(schedule_query)
                # Simple cleaning: assume the search result contains the name
                opponent = opponent_raw[:100] # Keep it short for the prompt
            
            st.info(f"Targeting Matchup: {p_team} vs {opponent}...")

            # 2. Run the 3 Key Searches Manually
            # We fetch the raw text FIRST, so the AI doesn't have to "think" about doing it.
            raw_p_stats = safe_search(f"{p_name} last 5 games stats box score November 2025 points rebounds assists")
            raw_t_stats = safe_search(f"{opponent} NBA team defensive rating pace stats 2025")
            raw_injuries = safe_search(f"{opponent} NBA injury report today November 2025")

        # --- PHASE 2: GEMINI SUMMARIZES (1 API Call) ---
        scouting_report = ""
        with st.spinner("Step 2: Gemini is reading the search results..."):
            try:
                scout_prompt = f"""
                You are an NBA Scout. I have already gathered the search results for you.
                
                RAW DATA FOUND:
                1. PLAYER STATS: {raw_p_stats}
                2. OPPONENT STATS: {raw_t_stats}
                3. INJURIES: {raw_injuries}
                
                TASK:
                Clean this mess up into a professional "Scouting Report". 
                - List {p_name}'s recent form (Points/Rebs/Ast).
                - Describe {opponent}'s defense (Good/Bad?).
                - List key injuries.
                """
                
                # This is the ONLY call to Gemini
                scouting_report = llm_scout.invoke(scout_prompt).content
                
                with st.expander("📄 Read Gemini's Report", expanded=True):
                    st.write(scouting_report)

            except Exception as e:
                st.error(f"Gemini Overloaded: {e}")
                st.stop()

        # --- PHASE 3: GPT-4o PREDICTS (1 API Call) ---
        if scouting_report:
            with st.spinner("Step 3: GPT-4o is making the game plan..."):
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
