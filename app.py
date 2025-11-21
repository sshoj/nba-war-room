import streamlit as st
from langchain_openai import ChatOpenAI
from duckduckgo_search import DDGS
import os
import time
import random

# --- PAGE CONFIGURATION ---
st.set_page_config(page_title="NBA War Room (Web)", page_icon="🏀", layout="wide")
st.title("🏀 NBA War Room (Web Researcher)")
st.markdown("**Source:** Web Search (StatMuse/ESPN) | **Coach:** GPT-4o")

# --- SIDEBAR ---
with st.sidebar:
    st.header("⚙️ Settings")
    openai_key_input = st.text_input("OpenAI API Key", type="password")
    if openai_key_input: os.environ["OPENAI_API_KEY"] = openai_key_input.strip()
    
    st.divider()
    st.info("This version searches the web for stats, so no RapidAPI key is needed.")
    manual_opponent = st.text_input("Manual Opponent (Optional)", placeholder="e.g. Celtics")

# --- ROBUST SEARCH TOOL ---
def search_web(query):
    """
    Searches DuckDuckGo using the 'html' backend to avoid rate limits.
    Retries 3 times if it fails.
    """
    for attempt in range(3):
        try:
            # Sleep to mimic human behavior
            time.sleep(random.uniform(1, 3))
            
            with DDGS() as ddgs:
                # backend='html' is slower but much safer from blocks
                results = list(ddgs.text(query, backend="html", max_results=3))
                
            if results:
                # Combine the top 3 search snippets into one text block
                return "\n\n".join([f"Source {i+1}: {r['body']}" for i, r in enumerate(results)])
            
        except Exception as e:
            print(f"Attempt {attempt+1} failed: {e}")
            time.sleep(2)
            
    return "Error: Could not find data on the web."

# --- MAIN APP ---
if openai_key_input:
    
    llm_coach = ChatOpenAI(model="gpt-4o", temperature=0.5, api_key=openai_key_input)

    col1, col2 = st.columns(2)
    with col1: p_name = st.text_input("Player Name", "Luka Doncic")
    with col2: p_team = st.text_input("Team", "Dallas Mavericks")

    if st.button("🚀 RUN ANALYSIS", type="primary"):
        
        # PHASE 1: SCOUTING (Web Search)
        with st.spinner("🕵️ Scanning the web for stats..."):
            
            # 1. Find Schedule
            if manual_opponent:
                opponent = manual_opponent
                st.success(f"Opponent: {opponent} (Manual)")
            else:
                schedule_query = f"Who is the {p_team} playing next in November 2025? NBA schedule."
                schedule_data = search_web(schedule_query)
                
                # Use GPT to extract the team name from the messy search results
                opp_extractor = llm_coach.invoke(f"Extract ONLY the opponent team name from this text: {schedule_data}").content
                opponent = opp_extractor.strip()
                st.info(f"Next Game: {opponent}")

            # 2. Find Player Stats (StatMuse usually ranks high)
            stats_query = f"{p_name} last 5 games stats box score November 2025 StatMuse"
            stats_data = search_web(stats_query)
            
            with st.expander("📊 Raw Search Data", expanded=True):
                st.text(stats_data)

        # PHASE 2: COACHING
        if "Error" not in stats_data:
            with st.spinner("🧠 GPT-4o is analyzing..."):
                try:
                    prompt = f"""
                    You are an Elite NBA Analyst.
                    
                    PLAYER: {p_name}
                    OPPONENT: {opponent}
                    
                    WEB SEARCH RESULTS (Recent Games):
                    {stats_data}
                    
                    TASK:
                    1. **Recent Form:** Extract his Points/Rebounds/Assists from the search text. Is he hot?
                    2. **Matchup:** How does he usually play against {opponent}?
                    3. **Prediction:** Project his stat line for the next game.
                    """
                    
                    prediction = llm_coach.invoke(prompt).content
                    st.divider()
                    st.markdown("### 🏆 Scouting Report")
                    st.write(prediction)
                    
                except Exception as e:
                    st.error(f"Coaching Error: {e}")
        else:
            st.error("Could not find stats. Try typing the opponent name manually.")

elif not openai_key_input:
    st.warning("⚠️ Please enter your OpenAI Key to start.")
