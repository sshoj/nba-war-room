import streamlit as st
import requests
from langchain_openai import ChatOpenAI
import os
import pandas as pd
from datetime import datetime, timedelta
import difflib 

# --- PAGE CONFIGURATION ---
st.set_page_config(page_title="NBA War Room (Ultimate)", page_icon="🏀", layout="wide")
st.title("🏀 NBA War Room (Ultimate Edition)")
st.markdown("**Stats:** BallDontLie | **Odds:** FanDuel (Props or Moneyline) | **Coach:** GPT-4o")

# --- SECURE AUTHENTICATION ---
def load_keys():
    keys = {}
    def get_key(secret_name, label):
        if secret_name in st.secrets:
            st.sidebar.success(f"✅ {label} Key Loaded")
            return st.secrets[secret_name]
        else:
            return st.sidebar.text_input(f"{label} Key", type="password")

    keys["bdl"] = get_key("BDL_API_KEY", "BallDontLie")
    keys["odds"] = get_key("ODDS_API_KEY", "The Odds API")
    keys["openai"] = get_key("OPENAI_API_KEY", "OpenAI")
    
    if keys["bdl"]:
        os.environ["BDL_API_KEY"] = keys["bdl"].strip()
    if keys["odds"]:
        os.environ["ODDS_API_KEY"] = keys["odds"].strip()
    if keys["openai"]:
        os.environ["OPENAI_API_KEY"] = keys["openai"].strip()
    
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
    """Return headers for BallDontLie requests with Bearer auth."""
    key = os.environ.get("BDL_API_KEY")
    if not key:
        return {}
    return {"Authorization": f"Bearer {key}"}

def get_current_season() -> int:
    """
    Compute current NBA season year.
    If month >= October, season is this year, else previous year.
    """
    today = datetime.today()
    return today.year if today.month >= 10 else today.year - 1

REQUEST_TIMEOUT = 10  # seconds

# --- TOOLS ---

def get_player_info_smart(user_input):
    """Smart Search V2: Handles typos (Trigram method) with basic error handling."""
    try:
        words = user_input.split()
        candidates = {} 
        search_terms = set(words)
        for w in words:
            if len(w) >= 3:
                search_terms.add(w[:3])
        
        for term in search_terms:
            try:
                r = requests.get(
                    url=f"{BDL_URL}/players",
                    headers=get_bdl_headers(),
                    params={"search": term, "per_page": 10},
                    timeout=REQUEST_TIMEOUT,
                )
            except Exception as e:
                return None, f"Network error searching for player: {e}"
            
            if r.status_code != 200:
                return None, f"BallDontLie error ({r.status_code}) while searching players."
            
            data = r.json().get("data", [])
            for p in data:
                candidates[p["id"]] = p
        
        if not candidates:
            return None, f"Player '{user_input}' not found."
        
        candidate_list = list(candidates.values())
        candidate_names = [f"{c['first_name']} {c['last_name']}" for c in candidate_list]
        best_matches = difflib.get_close_matches(user_input, candidate_names, n=1, cutoff=0.4)
        
        if best_matches:
            target_name = best_matches[0]
            p = next(c for c in candidate_list if f"{c['first_name']} {c['last_name']}" == target_name)
            return p, f"Found: **{target_name}** (Corrected from '{user_input}')"
            
        return None, "No close matches found."

    except Exception as e:
        return None, f"Search Error: {e}"

def get_team_injuries(team_id):
    """Fetches official injury report with error handling."""
    try:
        url = f"{BDL_URL}/player_injuries"
        resp = requests.get(
            url,
            headers=get_bdl_headers(),
            params={"team_ids[]": str(team_id)},
            timeout=REQUEST_TIMEOUT,
        )
        if resp.status_code != 200:
            return f"Error fetching injuries (status {resp.status_code})."
        data = resp.json().get("data", [])
        if not data:
            return "No active injuries."
        
        reports = []
        for i in data:
            p_obj = i.get("player") or {}
            name = f"{p_obj.get('first_name','')} {p_obj.get('last_name','')}"
            status = i.get("status", "Unknown")
            note = i.get("note") or i.get("comment") or i.get("description") or "No details"
            reports.append(f"- **{name}**: {status} ({note})")
        return "\n".join(reports)
    except Exception as e:
        return f"Error fetching injuries: {e}"

def get_team_schedule_before_today(team_id, n_games: int = 7):
    """Fetches TEAM'S last n finished games (EXTENDED HISTORY) with error handling."""
    try:
        url = f"{BDL_URL}/games"
        today = datetime.now().strftime("%Y-%m-%d")
        season = get_current_season()
        params = {
            "team_ids[]": str(team_id),
            "seasons[]": str(season),
            "end_date": today,
            "per_page": "50",
        }
        resp = requests.get(
            url,
            headers=get_bdl_headers(),
            params=params,
            timeout=REQUEST_TIMEOUT,
        )
        if resp.status_code != 200:
            return []
        data = resp.json().get("data", [])
        finished = [g for g in data if g.get("status") == "Final"]
        finished.sort(key=lambda x: x["date"], reverse=True)
        return finished[:n_games]
    except Exception:
        return []

def get_stats_for_games(player_id, game_ids):
    """Fetch stats for a player across a list of game IDs with error handling."""
    if not game_ids:
        return []
    try:
        url = f"{BDL_URL}/stats"
        params = {
            "player_ids[]": str(player_id),
            "per_page": "50",
            "game_ids[]": [str(g) for g in game_ids],
        }
        resp = requests.get(
            url,
            headers=get_bdl_headers(),
            params=params,
            timeout=REQUEST_TIMEOUT,
        )
        if resp.status_code != 200:
            return []
        return resp.json().get("data", [])
    except Exception:
        return []

def get_next_game(team_id):
    """Get next scheduled (non-final) game for a team with error handling."""
    try:
        url = f"{BDL_URL}/games"
        today = datetime.now().strftime("%Y-%m-%d")
        future = (datetime.now() + timedelta(days=14)).strftime("%Y-%m-%d")
        season = get_current_season()
        params = {
            "team_ids[]": str(team_id),
            "seasons[]": str(season),
            "start_date": today,
            "end_date": future,
            "per_page": "25",
        }
        resp = requests.get(
            url,
            headers=get_bdl_headers(),
            params=params,
            timeout=REQUEST_TIMEOUT,
        )
        if resp.status_code != 200:
            return None, "Error fetching next game.", None, None
        data = resp.json().get("data", [])
        if not data:
            return None, "No games found.", None, None
        
        data.sort(key=lambda x: x["date"])
        game = next((g for g in data if g["status"] != "Final"), None)
        if not game:
            return None, "No upcoming games.", None, None
        
        if game["home_team"]["id"] == team_id:
            opp = game["visitor_team"]
            loc = "vs"
        else:
            opp = game["home_team"]
            loc = "@"
        return f"{loc} {opp.get('full_name', 'Unknown')}", game["date"].split("T")[0], opp.get("id"), opp.get("full_name")
    except Exception:
        return None, "Error fetching next game.", None, None

def get_betting_odds(player_name, team_name):
    """
    Fetches Betting Lines with error handling.
    STRATEGY:
    1. Try Player Props (Points, etc.) first.
    2. If no props found, FALLBACK to Game Moneyline (H2H).
    """
    api_key = os.environ.get("ODDS_API_KEY")
    if not api_key:
        return "Odds API Key missing."

    try:
        # 1. Get Games list (events) – NOTE: /events only needs apiKey
        games_resp = requests.get(
            f"{ODDS_URL}/events",
            params={"apiKey": api_key},
            timeout=REQUEST_TIMEOUT,
        )

        if games_resp.status_code != 200:
            # Show response text too, so you see WHY it's 401
            try:
                msg = games_resp.json().get("message", games_resp.text)
            except Exception:
                msg = games_resp.text
            return f"Error fetching games from Odds API (status {games_resp.status_code}): {msg}"

        games = games_resp.json()

        if not isinstance(games, list) or not games:
            return "No betting lines available."

        team_name_lower = team_name.lower()
        game_id = None
        home_team = None
        away_team = None

        for g in games:
            ht = g.get("home_team", "")
            at = g.get("away_team", "")
            if team_name_lower in ht.lower() or team_name_lower in at.lower():
                game_id = g.get("id")
                home_team = ht
                away_team = at
                break
        
        if not game_id:
            return f"No active betting lines found for {team_name}."

        # 2. Try Player Props First ...
        # (keep the rest of your function the same)
        props_resp = requests.get(
            f"{ODDS_URL}/events/{game_id}/odds",
            params={
                "apiKey": api_key,
                "regions": "us",
                "markets": "player_points,player_rebounds,player_assists",
                "bookmakers": "fanduel",
            },
            timeout=REQUEST_TIMEOUT,
        )
        if props_resp.status_code == 200:
            data = props_resp.json()
            bookmakers = data.get("bookmakers", [])
            
            lines = []
            if bookmakers:
                for market in bookmakers[0].get("markets", []):
                    market_name = market["key"].replace("player_", "").title()
                    for outcome in market.get("outcomes", []):
                        p_last = player_name.split()[-1]
                        if p_last.lower() in outcome.get("description", "").lower():
                            line = outcome.get("point", "N/A")
                            price = outcome.get("price", "N/A")
                            lines.append(f"**{market_name}**: {line} ({price})")
            
            if lines:
                return " | ".join(lines)
        
        # 3. Fallback to Moneyline (H2H) if no props found
        h2h_resp = requests.get(
            f"{ODDS_URL}/events/{game_id}/odds",
            params={
                "apiKey": api_key,
                "regions": "us",
                "markets": "h2h",
                "bookmakers": "fanduel",
            },
            timeout=REQUEST_TIMEOUT,
        )
        if h2h_resp.status_code != 200:
            return "Props not ready. Error fetching moneyline odds."
        h2h_data = h2h_resp.json()
        bm_h2h = h2h_data.get("bookmakers", [])
        
        if bm_h2h:
            markets = bm_h2h[0].get("markets", [])
            if markets:
                outcomes = markets[0].get("outcomes", [])
                odds_str = " vs ".join([f"{o['name']} ({o['price']})" for o in outcomes])
                return f"Props not ready. **Game Odds:** {odds_str}"
            
        return "No odds available."

    except Exception as e:
        return f"Error fetching odds: {e}"

# --- MAIN LOGIC ---
if api_keys["bdl"] and api_keys["openai"] and api_keys["odds"]:
    
    llm = ChatOpenAI(model="gpt-4o", temperature=0.5, api_key=api_keys["openai"])
    
    col1, col2 = st.columns([3, 1])
    with col1:
        p_name = st.text_input("Player Name", "Luka Doncic")
    with col2:
        st.write("") 
        st.write("")
        run_btn = st.button("🚀 Run Analysis", type="primary", use_container_width=True)

    # --- PROCESS DATA ---
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
            
            pid = player_obj["id"]
            fname = player_obj["first_name"]
            lname = player_obj["last_name"]
            tid = player_obj["team"]["id"]
            tname = player_obj["team"]["full_name"]
            st.success(msg)

            # 2. Schedule
            status_box.write("Checking schedule...")
            opp_str, date, opp_id, opp_name = get_next_game(tid)
            if not opp_str:
                opp_name = "Unknown"

            # 3. Betting Odds (With Fallback)
            status_box.write("Checking Lines...")
            betting_lines = get_betting_odds(f"{fname} {lname}", tname)

            # 4. Injuries
            status_box.write("Fetching Injuries...")
            inj_home = get_team_injuries(tid) if tid else "N/A"
            inj_opp = get_team_injuries(opp_id) if opp_id else "N/A"

            # 5. Stats (Last 7 Games + Strict DNP) + NEW: structured rows for DataFrame/chart
            status_box.write("Crunching stats...")
            past_games = get_team_schedule_before_today(tid, n_games=7)
            gids = [g["id"] for g in past_games]
            p_stats = get_stats_for_games(pid, gids)
            
            log_lines = []
            stats_rows = []

            for g in past_games:
                gid = g["id"]
                d = g["date"].split("T")[0]
                
                home = g.get("home_team", {})
                visitor = g.get("visitor_team", {})
                
                if home.get("id") == tid:
                    opp_abbr = visitor.get("abbreviation", "UNK")
                    loc = "vs"
                else:
                    opp_abbr = home.get("abbreviation", "UNK")
                    loc = "@"
                
                stat = next((s for s in p_stats if s["game"]["id"] == gid), None)
                
                               # STRICT DNP CHECK
                min_val = stat.get("min") if stat else None
                played = bool(
                    min_val
                    and str(min_val) not in ("0", "00:00", "")
                )

                if played:
                    fg = f"{stat['fg_pct']*100:.0f}%" if stat.get("fg_pct") else "0%"
                    fg3 = f"{stat.get('fg3m', 0)}/{stat.get('fg3a', 0)}"
                    line = (
                        f"MIN:{min_val} | PTS:{stat.get('pts',0)} "
                        f"REB:{stat.get('reb',0)} AST:{stat.get('ast',0)} | FG:{fg} 3PT:{fg3}"
                    )
                else:
                    line = "⛔ DNP (Did Not Play)"

                log_lines.append(f"[{d}] {loc} {opp_abbr} | {line}")

                # NEW FEATURE: collect structured stats for DataFrame/chart
                stats_rows.append(
                    {
                        "Date": d,
                        "Location": loc,
                        "Opponent": opp_abbr,
                        "MIN": min_val if played else 0,
                        "PTS": stat.get("pts", 0) if stat else 0,
                        "REB": stat.get("reb", 0) if stat else 0,
                        "AST": stat.get("ast", 0) if stat else 0,
                        "Is_DNP": not played,
                    }
                )
            
            final_log = "\n".join(log_lines)
            
            # 6. GPT Analysis
            status_box.write("Consulting Coach...")
            prompt = f"""
            Role: Expert Sports Bettor.
            Target: {fname} {lname} ({tname})
            Matchup: {opp_str}
            
            ODDS:
            {betting_lines}
            
            INJURIES:
            {tname}: {inj_home}
            {opp_name}: {inj_opp}
            
            RECENT FORM (Last 7 Games):
            {final_log}
            
            Tasks:
            1. **Line Value:** Compare stats to the Odds (if Player Props available).
            2. **Prediction:** Project Points/Rebounds/Assists.
            3. **Recommendation:** Suggest a bet (Prop or Moneyline).
            Rules:
            - Do NOT guarantee outcomes.
            - Use language like "lean", "edge", "high variance" instead of certainty.
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
                "context": prompt + "\n\nAnalysis:\n" + analysis,
                "stats_rows": stats_rows,
            }
            st.session_state.messages = [{"role": "assistant", "content": analysis}]
            status_box.update(label="Ready!", state="complete", expanded=False)
            st.rerun()
            
        except Exception as e:
            status_box.update(label="System Error", state="error")
            st.error(f"Error: {e}")

    # --- DISPLAY ---
    data = st.session_state.analysis_data
    
    if data:
        st.divider()
        # Safe Access to avoid KeyErrors
        p_label = data.get("player", "Unknown")
        m_label = data.get("matchup", "Unknown")
        d_label = data.get("date", "")
        
        st.markdown(f"### 📊 Report: {p_label} {m_label}")
        st.caption(f"Date: {d_label}")
        
        st.info(f"🎰 **FanDuel Odds:**\n\n{data.get('odds', 'No odds data')}")

        # NEW FEATURE: show recent stats table + chart
        stats_rows = data.get("stats_rows")
        if stats_rows:
            st.subheader("Recent Game Log (Last 7)")
            df_stats = pd.DataFrame(stats_rows)
            st.dataframe(df_stats, use_container_width=True)

            # Line chart for PTS / REB / AST (excluding DNP)
            try:
                df_played = df_stats[~df_stats["Is_DNP"]].copy()
                if not df_played.empty:
                    df_played.set_index("Date", inplace=True)
                    st.line_chart(df_played[["PTS", "REB", "AST"]])
            except Exception:
                # Fail silently if charting has any issue
                pass
        
        with st.expander("View Stats & Injuries", expanded=False):
            c1, c2 = st.columns(2)
            c1.warning(f"Home Injuries:\n{data.get('inj_home', 'N/A')}")
            c2.error(f"Away Injuries:\n{data.get('inj_opp', 'N/A')}")
            st.code(data.get("log", "No logs"))
            
        st.write("### 🧠 Betting Advice")
        st.write(data.get("analysis", "No analysis"))
        
        st.divider()
        # Chat
        for msg in st.session_state.messages:
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])
        
        if val := st.chat_input("Ask follow-up..."):
            st.session_state.messages.append({"role": 'user', "content": val})
            with st.chat_message("user"):
                st.markdown(val)
            with st.chat_message("assistant"):
                with st.spinner("..."):
                    ctx = data.get("context", "")
                    res = llm.invoke(f"CTX:\n{ctx}\nQ: {val}").content
                    st.markdown(res)
            st.session_state.messages.append({"role": "assistant", "content": res})

else:
    st.warning("⚠️ Keys missing! Check your secrets.toml or enter them in the sidebar.")
