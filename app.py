import streamlit as st
import requests
from langchain_openai import ChatOpenAI
import os
from datetime import datetime, timedelta
import difflib 

# --- PAGE CONFIGURATION ---
st.set_page_config(page_title="NBA War Room (Ultimate)", page_icon="🏀", layout="wide")
st.title("🏀 NBA War Room (Ultimate Edition)")
st.markdown("**Stats:** BallDontLie | **Odds:** FanDuel | **Coach:** GPT-4o")

# --- SECURE AUTHENTICATION ---
def load_keys():
    """
    Loads API keys from st.secrets if available, otherwise asks user in sidebar.
    Returns a dictionary of keys.
    """
    keys = {}
    
    # Helper to get key from secrets or sidebar
    def get_key(secret_name, label):
        if secret_name in st.secrets:
            st.sidebar.success(f"✅ {label} Key Loaded")
            return st.secrets[secret_name]
        else:
            return st.sidebar.text_input(f"{label} Key", type="password")

    keys["bdl"] = get_key("BDL_API_KEY", "BallDontLie")
    keys["odds"] = get_key("ODDS_API_KEY", "The Odds API")
    keys["openai"] = get_key("OPENAI_API_KEY", "OpenAI")
    
    # Set Environment Variables for global access
    if keys["bdl"]: os.environ["BDL_API_KEY"] = keys["bdl"].strip()
    if keys["odds"]: os.environ["ODDS_API_KEY"] = keys["odds"].strip()
    if keys["openai"]: os.environ["OPENAI_API_KEY"] = keys["openai"].strip()
    
    return keys

# --- SIDEBAR ---
with st.sidebar:
    st.header("⚙️ Settings")
    api_keys = load_keys()
    
    st.divider()
    if st.button("New Search / Clear"):
        st.session_state.analysis_data = None
        st.session_state.messages = []
        st.rerun()

# --- SESSION STATE SETUP ---
if "messages" not in st.session_state:
    st.session_state.messages = []
if "analysis_data" not in st.session_state:
    st.session_state.analysis_data = None

# --- API CONFIG ---
BDL_URL = "https://api.balldontlie.io/v1"
ODDS_URL = "https://api.the-odds-api.com/v4/sports/basketball_nba"

def get_bdl_headers():
    return {"Authorization": os.environ.get("BDL_API_KEY")}

# --- TOOLS ---

def get_player_info_smart(user_input):
    """Smart Search V2: Handles typos (Trigram method)"""
    try:
        # 1. Split input into words
        words = user_input.split()
        candidates = {} 
        
        # 2. Broad Search
        search_terms = set(words)
        for w in words:
            if len(w) >= 3: search_terms.add(w[:3])
        
        for term in search_terms:
            r = requests.get(url=f"{BDL_URL}/players", headers=get_bdl_headers(), params={"search": term, "per_page": 10})
            if r.status_code == 200:
                for p in r.json().get('data', []):
                    candidates[p['id']] = p
        
        if not candidates: return None, f"Player '{user_input}' not found."
        
        # 3. Fuzzy Match
        candidate_list = list(candidates.values())
        candidate_names = [f"{c['first_name']} {c['last_name']}" for c in candidate_list]
        best_matches = difflib.get_close_matches(user_input, candidate_names, n=1, cutoff=0.4)
        
        if best_matches:
            target_name = best_matches[0]
            p = next(c for c in candidate_list if f"{c['first_name']} {c['last_name']}" == target_name)
            return p, f"Found: **{target_name}** (Corrected from '{user_input}')"
            
        return None, "No close matches found."

    except Exception as e: return None, f"Search Error: {e}"

def get_team_injuries(team_id):
    """Fetches official injury report with crash protection."""
    try:
        url = f"{BDL_URL}/player_injuries"
        resp = requests.get(url, headers=get_bdl_headers(), params={"team_ids[]": str(team_id)})
        data = resp.json().get('data', [])
        if not data: return "No active injuries."
        
        reports = []
        for i in data:
            p_obj = i.get('player') or {}
            name = f"{p_obj.get('first_name','')} {p_obj.get('last_name','')}"
            status = i.get('status', 'Unknown')
            note = i.get('note') or i.get('comment') or i.get('description') or "No details"
            reports.append(f"- **{name}**: {status} ({note})")
        return "\n".join(reports)
    except: return "Error fetching injuries."

def get_team_schedule_before_today(team_id):
    """Fetches TEAM'S last 5 finished games"""
    try:
        url = f"{BDL_URL}/games"
        today = datetime.now().strftime("%Y-%m-%d")
        params = {"team_ids[]": str(team_id), "seasons[]": "2025", "end_date": today, "per_page": "20"}
        resp = requests.get(url, headers=get_bdl_headers(), params=params)
        data = resp.json().get('data', [])
        finished = [g for g in data if g.get('status') == "Final"]
        finished.sort(key=lambda x: x['date'], reverse=True)
        return finished[:5]
    except: return []

def get_stats_for_games(player_id, game_ids):
    if not game_ids: return []
    try:
        url = f"{BDL_URL}/stats"
        params = {"player_ids[]": str(player_id), "per_page": "10", "game_ids[]": [str(g) for g in game_ids]}
        resp = requests.get(url, headers=get_bdl_headers(), params=params)
        return resp.json().get('data', [])
    except: return []

def get_next_game(team_id):
    """Finds next scheduled game"""
    try:
        url = f"{BDL_URL}/games"
        today = datetime.now().strftime("%Y-%m-%d")
        future = (datetime.now() + timedelta(days=14)).strftime("%Y-%m-%d")
        params = {"team_ids[]": str(team_id), "seasons[]": "2025", "start_date": today, "end_date": future, "per_page": "10"}
        resp = requests.get(url, headers=get_bdl_headers(), params=params)
        data = resp.json().get('data', [])
        if not data: return None, "No games found.", None, None
        
        data.sort(key=lambda x: x['date'])
        game = next((g for g in data if g['status'] != "Final"), None)
        if not game: return None, "No upcoming games.", None, None
        
        if game['home_team']['id'] == team_id:
            opp = game['visitor_team']
            loc = "vs"
        else:
            opp = game['home_team']
            loc = "@"
        return f"{loc} {opp.get('full_name', 'Unknown')}", game['date'].split("T")[0], opp.get('id'), opp.get('full_name')
    except: return None, "Error", None, None

def get_fanduel_props(player_name, team_name):
    """Fetches FanDuel Player Props via The Odds API"""
    api_key = os.environ.get("ODDS_API_KEY")
    if not api_key: return "Odds API Key missing."

    try:
        # 1. Get Today's Games
        games_resp = requests.get(f"{ODDS_URL}/events", params={"apiKey": api_key, "regions": "us"})
        games = games_resp.json()
        
        if not games or isinstance(games, dict) and "message" in games: 
            return "No betting lines available right now."

        game_id = None
        for g in games:
            if team_name in g['home_team'] or team_name in g['away_team']:
                game_id = g['id']
                break
        
        if not game_id: return f"No active betting lines found for {team_name}."

        # 2. Fetch Props
        props_resp = requests.get(
            f"{ODDS_URL}/events/{game_id}/odds",
            params={
                "apiKey": api_key,
                "regions": "us",
                "markets": "player_points,player_rebounds,player_assists",
                "bookmakers": "fanduel"
            }
        )
        data = props_resp.json()
        
        lines = []
        bookmakers = data.get('bookmakers', [])
        if not bookmakers: return "No FanDuel lines released yet."
        
        for market in bookmakers[0].get('markets', []):
            market_name = market['key'].replace("player_", "").title()
            for outcome in market['outcomes']:
                p_last = player_name.split()[-1]
                if p_last in outcome['description']:
                    line = outcome.get('point', 'N/A')
                    price = outcome.get('price', 'N/A')
                    lines.append(f"**{market_name}**: {line} ({price})")
        
        return " | ".join(lines) if lines else f"No specific props found for {player_name}."

    except Exception as e: return f"Error fetching odds: {e}"

# --- MAIN APP LOGIC ---
if api_keys["bdl"] and api_keys["openai"] and api_keys["odds"]:
    
    llm = ChatOpenAI(model="gpt-4o", temperature=0.5, api_key=api_keys["openai"])
    
    col1, col2 = st.columns([3, 1])
    with col1:
        p_name = st.text_input("Player Name", "Luka Doncic")
    with col2:
        st.write("")
        st.write("")
        run_btn = st.button("🚀 Run Analysis", type="primary", use_container_width=True)

    # --- PROCESS DATA (On Click) ---
    if run_btn:
        status_box = st.status("🔍 Scouting in progress...", expanded=True)
        
        try:
            # 1. Player Info
            status_box.write("Finding player...")
            player_obj, msg = get_player_info_smart(p_name)
            if not player_obj:
                status_box.update(label="Player Not Found", state="error")
                st.error(msg)
                st.stop()
            
            pid = player_obj['id']
            fname = player_obj['first_name']
            lname = player_obj['last_name']
            tid = player_obj['team']['id']
            tname = player_obj['team']['full_name']
            st.success(msg)

            # 2. Schedule
            status_box.write("Checking schedule...")
            opp_str, date, opp_id, opp_name = get_next_game(tid)
            if not opp_str: opp_name = "Unknown"

            # 3. Betting Odds
            status_box.write("Fetching FanDuel Lines...")
            betting_lines = get_fanduel_props(f"{fname} {lname}", tname)

            # 4. Injuries
            status_box.write("Checking injuries...")
            inj_home = get_team_injuries(tid) if tid else "N/A"
            inj_opp = get_team_injuries(opp_id) if opp_id else "N/A"

            # 5. Stats (Team Schedule First)
            status_box.write("Crunching stats...")
            past_games = get_team_schedule_before_today(tid)
            gids = [g['id'] for g in past_games]
            p_stats = get_stats_for_games(pid, gids)
            
            log_lines = []
            for g in past_games:
                gid = g['id']
                d = g['date'].split("T")[0]
                
                # Opponent & Location
                if g['home_team']['id'] == tid:
                    opp_abbr = g['visitor_team']['abbreviation']
                    loc = "vs"
                else:
                    opp_abbr = g['home_team']['abbreviation']
                    loc = "@"
                
                # Find Stat Line
                stat = next((s for s in p_stats if s['game']['id'] == gid), None)
                
                if stat and stat.get('min') and stat['min'] != "00:00" and stat['min'] != "0":
                    fg = f"{stat['fg_pct']*100:.0f}%" if stat.get('fg_pct') else "0%"
                    fg3 = f"{stat.get('fg3m',0)}/{stat.get('fg3a',0)}"
                    line = f"MIN:{stat.get('min')} | PTS:{stat.get('pts')} REB:{stat.get('reb')} AST:{stat.get('ast')} | FG:{fg} 3PT:{fg3}"
                else:
                    line = "⛔ DNP (Did Not Play)"
                    
                log_lines.append(f"[{d}] {loc} {opp_abbr} | {line}")
            
            final_log = "\n".join(log_lines)

            # 6. GPT Analysis
            status_box.write("Consulting Coach...")
            prompt = f"""
            Role: Expert Sports Bettor.
            Target: {fname} {lname} ({tname})
            Matchup: {opp_str}
            
            VEGAS LINES (FanDuel):
            {betting_lines}
            
            INJURIES:
            {tname}: {inj_home}
            {opp_name}: {inj_opp}
            
            RECENT FORM (Last 5):
            {final_log}
            
            Tasks:
            1. **Line Value:** Compare his recent stats to the FanDuel lines.
            2. **Prediction:** Do you recommend OVER or UNDER for Points?
            3. **Reasoning:** Cite specific stats or injuries.
            """
            analysis = llm.invoke(prompt).content
            
            # Save & Refresh
            st.session_state.analysis_data = {
                "player": f"{fname} {lname}",
                "matchup": opp_str,
                "date": date,
                "odds": betting_lines,
                "log": final_log,
                "analysis": analysis,
                "inj_home": inj_home,
                "inj_opp": inj_opp,
                "context": prompt + "\n\nAnalysis:\n" + analysis
            }
            st.session_state.messages = [{"role": "assistant", "content": analysis}]
            status_box.update(label="Ready!", state="complete", expanded=False)
            st.rerun()
            
        except Exception as e:
            status_box.update(label="System Error", state="error")
            st.error(f"Error: {e}")

    # --- DISPLAY RESULTS ---
    data = st.session_state.analysis_data
    
    if data:
        st.divider()
        
        # Safe Access to avoid KeyErrors
        p_label = data.get('player', 'Unknown')
        m_label = data.get('matchup', 'Unknown')
        d_label = data.get('date', '')
        
        st.markdown(f"### 📊 Report: {p_label} {m_label}")
        st.caption(f"Date: {d_label}")
        
        st.info(f"🎰 **FanDuel Lines:**\n\n{data.get('odds', 'No odds data')}")
        
        with st.expander("View Stats & Injuries", expanded=False):
            c1, c2 = st.columns(2)
            c1.warning(f"Home Injuries:\n{data.get('inj_home', 'N/A')}")
            c2.error(f"Away Injuries:\n{data.get('inj_opp', 'N/A')}")
            st.code(data.get('log', 'No logs'))
            
        st.write("### 🧠 Betting Advice")
        st.write(data.get('analysis', 'No analysis'))
        
        st.divider()
        # Chat
        for msg in st.session_state.messages:
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])
        
        if val := st.chat_input("Ask follow-up..."):
            st.session_state.messages.append({"role": "user", "content": val})
            with st.chat_message("user"): st.markdown(val)
            with st.chat_message("assistant"):
                with st.spinner("Thinking..."):
                    ctx = data.get('context', '')
                    res = llm.invoke(f"CTX:\n{ctx}\nQ: {val}").content
                    st.markdown(res)
            st.session_state.messages.append({"role": "assistant", "content": res})

else:
    st.warning("⚠️ Keys missing! Check your secrets.toml or enter them in the sidebar.")
