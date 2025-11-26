import streamlit as st
import requests
from langchain_openai import ChatOpenAI
import os
import pandas as pd
from datetime import datetime, timedelta, timezone
import time

# --- PAGE CONFIGURATION ---
st.set_page_config(page_title="NBA War Room (Ultimate)", page_icon="🏀", layout="wide")
st.title("🏀 NBA War Room (Ultimate Edition)")
st.markdown("Use Multi Agent AI NBA betting application")

# --- CONSTANTS & CONFIG ---
BDL_URL = "https://api.balldontlie.io/v1"
ODDS_URL = "https://api.the-odds-api.com/v4/sports/basketball_nba"
REQUEST_TIMEOUT = 15

# --- SESSION STATE SETUP ---
if "messages" not in st.session_state:
    st.session_state.messages = []
if "analysis_data" not in st.session_state:
    st.session_state.analysis_data = None

# --- SECURE AUTHENTICATION ---
def load_keys():
    keys = {}
    def get_key(secret_name, label):
        if secret_name in st.secrets:
            return st.secrets[secret_name]
        return st.sidebar.text_input(f"{label} Key", type="password")

    keys["bdl"] = get_key("BDL_API_KEY", "Sport Stats API")
    keys["odds"] = get_key("ODDS_API_KEY", "Betting API")
    keys["openai"] = get_key("OPENAI_API_KEY", "AI API")

    if keys["bdl"]: os.environ["BDL_API_KEY"] = keys["bdl"].strip()
    if keys["odds"]: os.environ["ODDS_API_KEY"] = keys["odds"].strip()
    if keys["openai"]: os.environ["OPENAI_API_KEY"] = keys["openai"].strip()
    return keys

with st.sidebar:
    st.header("⚙️ Settings")
    api_keys = load_keys()
    st.divider()
    if st.button("New Search / Clear"):
        st.session_state.analysis_data = None
        st.session_state.messages = []
        st.rerun()

# --- HELPERS ---
def get_bdl_headers():
    key = os.environ.get("BDL_API_KEY")
    return {"Authorization": key} if key else {}

def get_current_season() -> int:
    today = datetime.today()
    # If it's late in the year, it's the current year, else previous
    return today.year if today.month >= 10 else today.year - 1

def parse_minutes(min_str):
    if not min_str: return 0.0
    s = str(min_str)
    if s in ("0", "00:00", ""): return 0.0
    try:
        if ":" in s:
            m, sec = s.split(":")
            return int(m) + int(sec) / 60.0
        return float(s)
    except: return 0.0

def normalize_team_name(name: str) -> str:
    if not name: return ""
    return "".join(ch for ch in name.lower() if ch.isalnum())

def get_team_logo_url(team_abbr: str):
    if not team_abbr: return None
    abbr = team_abbr.upper()
    corrections = {"UTA": "utah", "NOP": "no", "NYK": "ny", "GSW": "gs", "SAS": "sa", "PHX": "phx", "WAS": "wsh"}
    espn_code = corrections.get(abbr, abbr.lower())
    return f"https://a.espncdn.com/i/teamlogos/nba/500/scoreboard/{espn_code}.png"

# --- CORE API FUNCTIONS ---

@st.cache_data(ttl=3600)
def get_player_info_smart(user_input):
    try:
        candidates = {}
        clean_input = user_input.lower().replace(" suns", "").replace(" phx", "").strip()
        
        # Search exact and parts
        queries = [clean_input]
        if " " in clean_input: queries.append(" ".join(clean_input.split()[::-1]))
        
        for q in queries:
            if len(q) < 3: continue
            r = requests.get(f"{BDL_URL}/players", headers=get_bdl_headers(), params={"search": q, "per_page": 100}, timeout=REQUEST_TIMEOUT)
            if r.status_code == 200:
                for p in r.json().get("data", []):
                    candidates[p["id"]] = p
        
        if not candidates: return None, "Player not found."
        
        # Scoring
        scored = []
        for p in candidates.values():
            score = difflib.SequenceMatcher(None, clean_input, f"{p['first_name']} {p['last_name']}".lower()).ratio()
            scored.append((score, p))
        
        scored.sort(key=lambda x: x[0], reverse=True)
        best = scored[0][1]
        return best, f"Found: {best['first_name']} {best['last_name']}"
    except Exception as e: return None, f"Error: {e}"

def get_team_injuries(team_id):
    try:
        resp = requests.get(f"{BDL_URL}/player_injuries", headers=get_bdl_headers(), params={"team_ids[]": str(team_id)}, timeout=REQUEST_TIMEOUT)
        data = resp.json().get("data", [])
        if not data: return "No active injuries."
        return "\n".join([f"- {i['player']['first_name']} {i['player']['last_name']}: {i['status']}" for i in data])
    except: return "Error fetching injuries."

def get_team_schedule_before_today(team_id, n_games=7):
    try:
        today = datetime.now().strftime("%Y-%m-%d")
        # Check CURRENT and PREVIOUS season to ensure we find games early in the year
        seasons = [get_current_season(), get_current_season()-1]
        
        resp = requests.get(
            f"{BDL_URL}/games", 
            headers=get_bdl_headers(), 
            params={
                "team_ids[]": str(team_id), 
                "seasons[]": seasons, 
                "end_date": today, 
                "per_page": 100, 
                "status": "Final"
            }, 
            timeout=REQUEST_TIMEOUT
        )
        data = resp.json().get("data", [])
        finished = [g for g in data if g["status"] == "Final"]
        finished.sort(key=lambda x: x["date"], reverse=True)
        return finished[:n_games]
    except: return []

def get_next_game_bdl(team_id):
    try:
        today = datetime.now().strftime("%Y-%m-%d")
        future = (datetime.now() + timedelta(days=14)).strftime("%Y-%m-%d")
        resp = requests.get(f"{BDL_URL}/games", headers=get_bdl_headers(), params={"team_ids[]": str(team_id), "seasons[]": str(get_current_season()), "start_date": today, "end_date": future, "per_page": 50}, timeout=REQUEST_TIMEOUT)
        data = resp.json().get("data", [])
        data.sort(key=lambda x: x["date"])
        
        for g in data:
            if g["status"] == "Final": continue
            home = g["home_team"]
            visitor = g["visitor_team"]
            if home["id"] == team_id:
                return (f"vs {visitor['full_name']}", g["date"].split("T")[0], visitor["id"], visitor["full_name"], visitor["abbreviation"], g["id"])
            else:
                return (f"@ {home['full_name']}", g["date"].split("T")[0], home["id"], home["full_name"], home["abbreviation"], g["id"])
        return (None,)*6
    except: return (None,)*6

def get_player_stats_for_games(player_id, game_ids):
    """
    BATCH FETCH: Fixes the Rate Limit / 'DNP' issue.
    Fetches all stats in ONE call instead of looping.
    """
    stats_by_game = {}
    if not game_ids: return stats_by_game

    try:
        # Send ALL game IDs and THIS player ID in one request
        str_gids = [str(g) for g in game_ids]
        resp = requests.get(
            f"{BDL_URL}/stats",
            headers=get_bdl_headers(),
            params={
                "game_ids[]": str_gids,
                "player_ids[]": [str(player_id)], # Filter by player
                "per_page": 100
            },
            timeout=REQUEST_TIMEOUT
        )
        
        if resp.status_code == 200:
            for s in resp.json().get("data", []):
                gid = s["game"]["id"]
                # Ensure strict string matching to avoid ID type bugs
                if str(s["player"]["id"]) == str(player_id):
                    stats_by_game[gid] = s
    except: pass
    return stats_by_game

def compute_team_advanced_stats(team_id, games):
    """
    SAFE MATH FIX: Handles None values (nulls) from the API.
    """
    if not games: return {}
    
    # Fetch all stats for these games
    gids = [g["id"] for g in games]
    all_stats = []
    try:
        resp = requests.get(f"{BDL_URL}/stats", headers=get_bdl_headers(), params={"game_ids[]": gids, "per_page": 100}, timeout=REQUEST_TIMEOUT)
        all_stats = resp.json().get("data", [])
    except: pass

    if not all_stats: return {}

    # Aggregators
    totals = {"team_pts": 0, "team_poss": 0, "opp_pts": 0}
    
    # Process per game to calculate possessions
    game_map = {}
    for s in all_stats:
        gid = s["game"]["id"]
        tid = s["team"]["id"]
        if gid not in game_map: game_map[gid] = {team_id: {"fga":0, "oreb":0, "tov":0, "fta":0, "pts":0}, "opp": {"fga":0, "oreb":0, "tov":0, "fta":0, "pts":0}}
        
        # Target bucket (Team or Opponent)
        bucket = game_map[gid][team_id] if tid == team_id else game_map[gid]["opp"]
        
        # SAFE ADDITION: (val or 0) handles None
        bucket["fga"] += (s.get("fga") or 0)
        bucket["oreb"] += (s.get("oreb") or 0)
        bucket["tov"] += (s.get("turnover") or 0)
        bucket["fta"] += (s.get("fta") or 0)
        bucket["pts"] += (s.get("pts") or 0)

    for gid, data in game_map.items():
        t = data[team_id]
        o = data["opp"]
        # Possessions formula: 0.96 * (FGA + TOV + 0.44*FTA - OREB)
        t_poss = 0.96 * (t["fga"] + t["tov"] + 0.44*t["fta"] - t["oreb"])
        totals["team_pts"] += t["pts"]
        totals["opp_pts"] += o["pts"]
        totals["team_poss"] += t_poss

    if totals["team_poss"] == 0: return {}
    
    return {
        "off_rtg": 100 * totals["team_pts"] / totals["team_poss"],
        "def_rtg": 100 * totals["opp_pts"] / totals["team_poss"],
        "net_rtg": 100 * (totals["team_pts"] - totals["opp_pts"]) / totals["team_poss"],
        "games_used": len(games)
    }

def get_team_rotation(team_id, n_games=7):
    """Calculates rotation using safe math."""
    past_games = get_team_schedule_before_today(team_id, n_games)
    if not past_games: return [], 0
    
    gids = [g["id"] for g in past_games]
    try:
        resp = requests.get(f"{BDL_URL}/stats", headers=get_bdl_headers(), params={"game_ids[]": gids, "per_page": 100}, timeout=REQUEST_TIMEOUT)
        stats = resp.json().get("data", [])
    except: return [], 0

    agg = {}
    for s in stats:
        if s["team"]["id"] != team_id: continue
        pid = s["player"]["id"]
        if pid not in agg: agg[pid] = {"name": f"{s['player']['first_name']} {s['player']['last_name']}", "min": 0, "pts": 0, "gp": 0}
        
        m = parse_minutes(s.get("min"))
        if m > 0:
            agg[pid]["min"] += m
            agg[pid]["pts"] += (s.get("pts") or 0) # Safe math
            agg[pid]["gp"] += 1
            
    rows = []
    for p in agg.values():
        if p["gp"] > 0:
            rows.append({"Name": p["name"], "GP": p["gp"], "MIN": round(p["min"]/p["gp"],1), "PTS": round(p["pts"]/p["gp"],1)})
    
    rows.sort(key=lambda x: x["MIN"], reverse=True)
    return rows, len(past_games)

def get_betting_game_and_odds(player_name, team_name):
    api_key = os.environ.get("ODDS_API_KEY")
    if not api_key: return {"odds_text": "Missing Key", "tipoff_iso": None}
    
    try:
        # Fetch Games
        resp = requests.get(f"{ODDS_URL}/odds", params={"apiKey": api_key, "regions": "us", "markets": "h2h", "dateFormat": "iso"}, timeout=REQUEST_TIMEOUT)
        games = resp.json()
        if not isinstance(games, list): return {"odds_text": "No odds.", "tipoff_iso": None}
        
        # Find Matching Game
        target = normalize_team_name(team_name)
        now = datetime.now(timezone.utc)
        best_game = None
        
        for g in games:
            if target in normalize_team_name(g["home_team"]) or target in normalize_team_name(g["away_team"]):
                dt = datetime.fromisoformat(g["commence_time"].replace("Z", "+00:00"))
                if dt > now - timedelta(hours=12): # Include active games
                    if not best_game or dt < datetime.fromisoformat(best_game["commence_time"].replace("Z", "+00:00")):
                        best_game = g
        
        if not best_game: return {"odds_text": "No upcoming odds.", "tipoff_iso": None}
        
        # Fetch Props for that game
        gid = best_game["id"]
        props_text = []
        try:
            p_resp = requests.get(f"{ODDS_URL}/events/{gid}/odds", params={"apiKey": api_key, "regions": "us", "markets": "player_points,player_rebounds"}, timeout=REQUEST_TIMEOUT)
            if p_resp.status_code == 200:
                book = p_resp.json()["bookmakers"][0]
                p_last = player_name.split()[-1].lower()
                for m in book["markets"]:
                    for o in m["outcomes"]:
                        if p_last in o["description"].lower():
                            props_text.append(f"{m['key'].replace('player_','').title()}: {o['point']} ({o['price']})")
        except: pass
        
        return {"odds_text": "\n".join(props_text) or "Moneyline only.", "tipoff_iso": best_game["commence_time"]}
    except: return {"odds_text": "Error.", "tipoff_iso": None}

# --- MAIN LOGIC ---

def run_analysis(player_input, llm):
    status = st.status("🚀 Running Analysis...", expanded=True)
    
    try:
        # 1. Player
        status.write("Searching player...")
        p_obj, msg = get_player_info_smart(player_input)
        if not p_obj:
            status.update(label="Player Not Found", state="error"); st.stop()
        
        pid = p_obj["id"]
        tid = p_obj["team"]["id"]
        
        # 2. Schedule
        status.write("Checking schedule...")
        matchup, date, opp_id, opp_name, opp_abbr, gid = get_next_game_bdl(tid)
        
        # 3. Odds
        betting = get_betting_game_and_odds(p_obj["first_name"] + " " + p_obj["last_name"], p_obj["team"]["full_name"])
        
        # 4. Data
        status.write("Fetching stats (Batched)...")
        # Batch 1: Injuries
        inj_home = get_team_injuries(tid)
        
        # Batch 2: Stats
        past_games = get_team_schedule_before_today(tid, 7)
        gids = [g["id"] for g in past_games]
        
        # THIS IS THE FIX: Single API call for all 7 games
        stats_map = get_player_stats_for_games(pid, gids)
        
        # Advanced Stats (with Safe Math fix)
        adv_stats = compute_team_advanced_stats(tid, past_games)
        
        # Build UI Table
        rows = []
        log_text = []
        for g in past_games:
            s = stats_map.get(g["id"])
            played = s and parse_minutes(s.get("min")) > 0
            opp = g["visitor_team"]["abbreviation"] if g["home_team"]["id"] == tid else g["home_team"]["abbreviation"]
            
            if played:
                # Safe access to stats
                pts = s.get("pts") or 0
                reb = s.get("reb") or 0
                ast = s.get("ast") or 0
                rows.append({"Date": g["date"][:10], "Opp": opp, "MIN": parse_minutes(s["min"]), "PTS": pts, "REB": reb, "AST": ast})
                log_text.append(f"{g['date'][:10]} vs {opp}: {pts} pts")
            else:
                rows.append({"Date": g["date"][:10], "Opp": opp, "MIN": 0, "PTS": 0, "REB": 0, "AST": 0})

        # 5. AI
        status.write("Consulting GPT-4.1...")
        prompt = f"""
        Analyze {p_obj['first_name']} {p_obj['last_name']} ({p_obj['team']['abbreviation']}).
        Matchup: {matchup}
        Odds: {betting['odds_text']}
        
        Last 7 Games:
        {log_text}
        
        Team Advanced Stats (Last 7):
        Off Rtg: {adv_stats.get('off_rtg', 0):.1f}
        Def Rtg: {adv_stats.get('def_rtg', 0):.1f}
        
        Injuries: {inj_home}
        """
        analysis = llm.invoke(prompt).content
        
        st.session_state.analysis_data = {
            "player": p_obj, "rows": rows, "analysis": analysis, "odds": betting, "matchup": matchup
        }
        status.update(label="Done!", state="complete", expanded=False)
        st.rerun()
        
    except Exception as e:
        status.update(label="Error", state="error")
        st.error(f"Traceback: {e}")

# --- UI ---
if api_keys["bdl"] and api_keys["openai"]:
    llm = ChatOpenAI(model="gpt-4o", api_key=api_keys["openai"])
    
    col1, col2 = st.columns([3,1])
    p_input = col1.text_input("Player", "Devin Booker")
    if col2.button("Run Analysis", type="primary"):
        run_analysis(p_input, llm)
        
    data = st.session_state.analysis_data
    if data:
        st.header(f"{data['player']['first_name']} {data['player']['last_name']}")
        st.caption(f"Matchup: {data.get('matchup', 'Unknown')}")
        st.info(f"Odds: {data['odds']['odds_text']}")
        
        st.dataframe(pd.DataFrame(data["rows"]), use_container_width=True)
        st.write("### Analysis")
        st.write(data["analysis"])
else:
    st.warning("Enter API Keys")
