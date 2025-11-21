import streamlit as st
from langchain.agents import initialize_agent, AgentType
from langchain.tools import Tool
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI
from langchain_community.tools import DuckDuckGoSearchRun
import os

# --- PAGE CONFIGURATION ---
st.set_page_config(page_title="NBA War Room (Web Edition)", page_icon="🏀")
st.title("🏀 Hybrid AI War Room")
st.markdown("**Mode:** Web Browsing (Unblockable) | **Scout:** Gemini 2.5 | **Coach:** GPT-4o")

# --- SIDEBAR: SETTINGS ---
with st.sidebar:
    st.header("⚙️ Settings")
    
    google_key = st.text_input("Google Gemini Key", type="password")
    if google_key: os.environ["GOOGLE_API_KEY"] = google_key.strip()
    st.markdown("[Get Free Google Key](https://aistudio.google.com/app/apikey)")
    
    openai_key = st.text_input("OpenAI API Key", type="password")
    if openai_key: os.environ["OPENAI_API_KEY"] = openai_key.strip()
    st.markdown("[Get OpenAI Key](https://platform.openai.com/account/api-keys)")
    
    st.divider()
    manual_opponent = st.text_input("Manual Opponent (Optional)", placeholder="e.g. Celtics")

# --- TOOLS (Pure Web Search) ---
search = DuckDuckGoSearchRun()

def web_search_tool(query):
    """Safe web search wrapper"""
    try:
        return search.run(query)
    except Exception as e:
        return f"Search Error: {e}"

# --- MAIN APP ---
if google_key and openai_key:
    
    # 1. Initialize Agents
    try:
        # SCOUT: Gemini 2.5 Flash (Web Browser)
        llm_scout = ChatGoogleGenerativeAI(
            model="gemini-2.5-flash", 
            temperature=0, 
            transport="rest"
        )

        # We give the agent ONE powerful tool: "Search the Web"
        tools = [
            Tool(
                name="WebSearch",
                func=web_search_tool,
                description="Useful for finding NBA stats, schedules, and injury reports."
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
        st.error(f"System Error: {e}")
        st.stop()

    # --- UI ---
    col1, col2 = st.columns(2)
    with col1: p_name = st.text_input("Player Name", "Luka Doncic")
    with col2: p_team = st.text_input("Player Team", "Dallas Mavericks")

    if st.button("🚀 RUN WEB ANALYSIS", type="primary"):
        
        scouting_report = ""
        
        # --- PHASE 1: SCOUTING (Web Browsing) ---
        with st.spinner("Step 1: Gemini is browsing the web for stats..."):
            try:
                # 1. Find Opponent
                opponent = ""
                if manual_opponent:
                    opponent = manual_opponent
                    st.info(f"Matchup (Manual): vs {opponent}")
                else:
                    opp_query = f"Who is the {p_team} playing next in the NBA? (Date: November 2025). Return ONLY the team name."
                    opponent = scout_agent.invoke({"input": opp_query})['output']
                    st.info(f"Matchup (Web Found): vs {opponent}")

                # 2. The "Mega Prompt" - Gemini does the research
                scout_prompt = f"""
                You are an NBA Scout. Use the 'WebSearch' tool to find the latest data.
                Target: {p_name} ({p_team}) vs {opponent}.
                
                TASK LIST:
                1. Search for "{p_name} last 5 games stats box score 2025". List his PTS, REB, AST for the last 5 games.
                2. Search for "{opponent} NBA defensive rating and pace 2025". Are they fast/slow? Good/bad defense?
                3. Search for "{opponent} NBA injury report today". Who is out?
                
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

elif not google_key or not openai_key:
    st.warning("⚠️ Please enter both API Keys to start.")
