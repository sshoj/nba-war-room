import streamlit as st
from langchain.agents import initialize_agent, AgentType
from langchain.tools import Tool
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI
from langchain_community.tools import DuckDuckGoSearchRun
import os
import time

# --- PAGE CONFIGURATION ---
st.set_page_config(page_title="NBA War Room (Web Edition)", page_icon="🏀")
st.title("🏀 NBA War Room (Web Edition)")
st.markdown("**Mode:** Web Browsing (Unblockable) | **Scout:** Gemini 2.5 | **Coach:** GPT-4o")

# --- SIDEBAR: SETTINGS ---
with st.sidebar:
    st.header("⚙️ Settings")
    
    google_key_input = st.text_input("Google Gemini Key", type="password")
    if google_key_input: os.environ["GOOGLE_API_KEY"] = google_key_input.strip()
    st.markdown("[Get Free Google Key](https://aistudio.google.com/app/apikey)")
    
    openai_key_input = st.text_input("OpenAI API Key", type="password")
    if openai_key_input: os.environ["OPENAI_API_KEY"] = openai_key_input.strip()
    st.markdown("[Get OpenAI Key](https://platform.openai.com/account/api-keys)")
    
    st.divider()
    st.info("This version searches the open web, so it cannot be blocked by NBA.com.")

# --- TOOLS (Pure Web Search) ---
search = DuckDuckGoSearchRun()

def web_search_tool(query):
    """Safe web search wrapper with rate limit handling"""
    try:
        # Pause briefly to avoid hitting search rate limits
        time.sleep(1)
        return search.run(query)
    except Exception as e:
        return f"Search Error: {e}"

# --- MAIN APP ---
if google_key_input and openai_key_input:
    
    # 1. Initialize Agents
    try:
        # SCOUT: Gemini 2.5 Flash (Web Browser)
        # We use transport="rest" to avoid Streamlit crashes
        llm_scout = ChatGoogleGenerativeAI(
            model="gemini-2.5-flash", 
            temperature=0, 
            transport="rest"
        )

        # The ONLY tool available is WebSearch. 
        # It cannot try to use 'GetLast5Games' because it doesn't exist.
        tools = [
            Tool(
                name="WebSearch",
                func=web_search_tool,
                description="Useful for finding NBA stats, schedules, and injury reports. Search for specific queries like 'Luka Doncic last 5 games stats'."
            )
        ]

        scout_agent = initialize_agent(
            tools, 
            llm_scout, 
            agent=AgentType.ZERO_SHOT_REACT_DESCRIPTION, 
            verbose=True, 
            handle_parsing_errors=True
        )

        # COACH: GPT-4o
        llm_coach = ChatOpenAI(model="gpt-4o", temperature=0.5)

    except Exception as e:
        st.error(f"System Initialization Error: {e}")
        st.stop()

    # --- UI ---
    col1, col2 = st.columns(2)
    with col1: p_name = st.text_input("Player Name", "Luka Doncic")
    with col2: p_team = st.text_input("Player Team", "Dallas Mavericks")

    if st.button("🚀 RUN WEB ANALYSIS", type="primary"):
        
        scouting_report = ""
        
        # --- PHASE 1: SCOUTING (Web Browsing) ---
        with st.spinner("Step 1: Gemini is browsing the web..."):
            try:
                # 1. Find Opponent via Web
                opp_query = f"Who are the {p_team} playing next in the NBA? (Current Date: November 2025). Return ONLY the team name."
                opponent = scout_agent.invoke({"input": opp_query})['output']
                st.info(f"Matchup Found: vs {opponent}")

                # 2. The "Mega Prompt" - Gemini does the research
                scout_prompt = f"""
                You are an NBA Scout. Use the 'WebSearch' tool to find the latest data.
                Target: {p_name} ({p_team}) vs {opponent}.
                
                TASK LIST:
                1. Search for "{p_name} last 5 games stats box score November 2025". List his PTS, REB, AST.
                2. Search for "{opponent} NBA defensive rating and pace 2025".
                3. Search for "{opponent} NBA injury report today".
                
                COMPILE this into a detailed Scouting Report.
                """
                
                scouting_report = scout_agent.invoke({"input": scout_prompt})['output']
                
                with st.expander("📄 Read Web Scouting Report", expanded=True):
                    st.write(scouting_report)

            except Exception as e:
                st.error(f"Browsing Failed: {e}")
                st.stop()

        # --- PHASE 2: COACHING ---
        if scouting_report:
            with st.spinner("Step 2: GPT-4o is creating the game plan..."):
                try:
                    coach_prompt = f"""
                    You are an NBA Head Coach. Based on this scouting report, predict the game.
                    
                    REPORT:
                    {scouting_report}
                    
                    OUTPUT:
                    1. Winner Prediction.
                    2. Estimated Score.
                    3. The "X-Factor" (Why will they win?).
                    """
                    final_prediction = llm_coach.invoke(coach_prompt)
                    
                    st.divider()
                    st.markdown("### 🏆 Official Prediction")
                    st.write(final_prediction.content)
                    
                except Exception as e:
                    st.error(f"Coaching Failed: {e}")

elif not google_key_input or not openai_key_input:
    st.warning("⚠️ Please enter both API Keys to start.")
