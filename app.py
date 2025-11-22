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
st.markdown("Use Multi Agent AI NBA betting application Written by Saeed Hojabr")

# --- SECURE AUTHENTICATION ---
def load_keys():
    keys = {}

    def get_key(secret_name, label):
        if secret_name in st.secrets:
            st.sidebar.success(f"✅ {label} Key Loaded")
            return st.secrets[secret_name]
        else:
            return st.sidebar.text_input(f"{label} Key", type="password")

    # 🔹 Generic labels instead of API brand names
    keys["bdl"] = get_key("BDL_API_KEY", "Sport Stats API")
    keys["odds"] = get_key("ODDS_API_KEY", "Betting API")
    keys["openai"] = get_key("OPENAI_API_KEY", "AI API")

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
REQUEST_TIMEOUT = 10  # seconds


def get_bdl_headers():
    """Return headers for BallDontLie requests (no Bearer prefix, per docs)."""
    key = os.environ.get("BDL_API_KEY")
    if not key:
        return {}
    return {"Authorization": key}


def get_current_season() -> int:
    """
    Compute current NBA season year (year the season starts).
    If month >= October, season is this year, else previous year.
    """
    today = datetime.today()
    return today.year if today.month >= 10 else today.year - 1


# --- TOOLS ---

def get_player_info_smart(user_input):
    """Smart Search V2: Handles typos (trigram-ish search) with basic error handling."""
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
                return None, f"Sport stats API error ({r.status_code}) while searching players."

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
            name = f"{p_obj.get('first_name', '')} {p_obj.get('last_name', '')}"
            status = i.get("status", "Unknown")
            note = i.get("note") or i.get("comment") or i.get("description") or "No details"
            reports.append(f"- **{name}**: {status} ({note})")
        return "\n".join(reports)
    except Exception as e:
        return f"Error fetching injuries: {e}"


def get_team_schedule_before_today(team_id, n_games: int = 7):
    """Fetches team's last n finished games (extended history) with error handling."""
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


def get_betting_odds(player_name, team_name, bookmakers: str = None):
    """
    Fetches Betting Lines with error handling.

    - Uses /events to find the correct game by team name.
    - Uses /events/{id}/odds with markets=player_points,player_rebounds,player_assists,h2h.
    - Player props:
        - Taken from a single bookmaker (prefer FanDuel, else first).
    - Moneyline:
        - Collected from ALL bookmakers in the response (all betting choices).
    """
    api_key = os.environ.get("ODDS_API_KEY")
    if not api_key:
        return "Odds API Key missing."

    try:
        # 1. Get Games list (events)
        games_resp = requests.get(
            f"{ODDS_URL}/events",
            params={"apiKey": api_key},
            timeout=REQUEST_TIMEOUT,
        )

        if games_resp.status_code != 200:
            try:
                msg = games_resp.json().get("message", games_resp.text)
            except Exception:
                msg = games_resp.text
            return f"Error fetching games from Betting API (status {games_resp.status_code}): {msg}"

        games = games_resp.json()
        if not isinstance(games, list) or not games:
            return "No betting lines available."

        team_name_lower = team_name.lower()
        game_id = None

        for g in games:
            ht = g.get("home_team", "")
            at = g.get("away_team", "")
            if team_name_lower in ht.lower() or team_name_lower in at.lower():
                game_id = g.get("id")
                break

        if not game_id:
            return f"No active betting lines found for {team_name}."

        # 2. Get props + moneyline in ONE call
        params = {
            "apiKey": api_key,
            "regions": "us",
            "markets": "player_points,player_rebounds,player_assists,h2h",
        }
        if bookmakers:
            params["bookmakers"] = bookmakers  # e.g. "fanduel,draftkings,betmgm"

        odds_resp = requests.get(
            f"{ODDS_URL}/events/{game_id}/odds",
            params=params,
            timeout=REQUEST_TIMEOUT,
        )
        if odds_resp.status_code != 200:
            try:
                msg = odds_resp.json().get("message", odds_resp.text)
            except Exception:
                msg = odds_resp.text
            return f"Error fetching odds (status {odds_resp.status_code}): {msg}"

        data = odds_resp.json()
        bookmakers_list = data.get("bookmakers", [])
        if not bookmakers_list:
            return "No odds available."

        # --- Player Props from ONE bookmaker (prefer FanDuel, else first) ---
        props_lines = []
        props_bookmaker_title = None

        preferred_key = "fanduel"
        props_bookmaker = next(
            (b for b in bookmakers_list if b.get("key") == preferred_key),
            bookmakers_list[0],
        )

        if props_bookmaker:
            props_bookmaker_title = props_bookmaker.get("title") or props_bookmaker.get("key", "Book")
            p_last = player_name.split()[-1].lower()
            for market in props_bookmaker.get("markets", []):
                mkey = market.get("key", "")
                if not mkey.startswith("player_"):
                    continue
                market_name = mkey.replace("player_", "").title()
                for outcome in market.get("outcomes", []):
                    desc = outcome.get("description", "")
                    if p_last in desc.lower():
                        line = outcome.get("point", "N/A")
                        price = outcome.get("price", "N/A")
                        props_lines.append(f"**{market_name}**: {line} ({price})")

        # --- Moneyline from ALL bookmakers ---
        moneyline_lines = []
        for b in bookmakers_list:
            b_title = b.get("title") or b.get("key", "Book")
            h2h_market = next(
                (m for m in b.get("markets", []) if m.get("key") == "h2h"),
                None,
            )
            if not h2h_market:
                continue
            outcomes = h2h_market.get("outcomes", [])
            if len(outcomes) < 2:
                continue
            parts = [f"{o.get('name', 'Team')} ({o.get('price', 'N/A')})" for o in outcomes]
            ml_str = " vs ".join(parts)
            moneyline_lines.append(f"- **{b_title}**: {ml_str}")

        # --- Build final string for display ---
        sections = []

        if props_lines:
            label = f"**Player Props ({props_bookmaker_title})**" if props_bookmaker_title else "**Player Props**"
            sections.append(label + ":\n" + " | ".join(props_lines))

        if moneyline_lines:
            sections.append("**Game Moneyline (All Books):**\n" + "\n".join(moneyline_lines))

        if sections:
            return "\n\n".join(sections)

        return "No odds available."

    except Exception as e:
        return f"Error fetching odds: {e}"


def compute_team_form(past_games, team_id):
    """Compute simple PF/PA/net and record for last N games."""
    if not past_games:
        return {"pf": 0.0, "pa": 0.0, "net": 0.0, "wins": 0, "losses": 0, "games_used": 0}
    pf_total = 0
    pa_total = 0
    wins = 0
    losses = 0
    games_counted = 0

    for g in past_games:
        home = g.get("home_team", {})
        visitor = g.get("visitor_team", {})
        hs = g.get("home_team_score", 0)
        vs = g.get("visitor_team_score", 0)

        if home.get("id") == team_id:
            team_score = hs
            opp_score = vs
        elif visitor.get("id") == team_id:
            team_score = vs
            opp_score = hs
        else:
            continue  # should not happen

        pf_total += team_score
        pa_total += opp_score
        games_counted += 1
        if team_score > opp_score:
            wins += 1
        elif team_score < opp_score:
            losses += 1

    if games_counted == 0:
        return {"pf": 0.0, "pa": 0.0, "net": 0.0, "wins": 0, "losses": 0, "games_used": 0}

    pf = pf_total / games_counted
    pa = pa_total / games_counted
    net = pf - pa
    return {"pf": pf, "pa": pa, "net": net, "wins": wins, "losses": losses, "games_used": games_counted}


def parse_minutes(min_str):
    """Convert min field ('38' or '38:21') to float minutes."""
    if not min_str:
        return 0.0
    s = str(min_str)
    if s in ("0", "00:00", ""):
        return 0.0
    if ":" in s:
        try:
            m, sec = s.split(":")
            return int(m) + int(sec) / 60.0
        except Exception:
            try:
                return float(m)
            except Exception:
                return 0.0
    try:
        return float(s)
    except Exception:
        return 0.0


def get_team_players(team_id):
    """Fetch current roster (players + positions) for a team."""
    try:
        resp = requests.get(
            f"{BDL_URL}/players",
            headers=get_bdl_headers(),
            params={"team_ids[]": str(team_id), "per_page": 100},
            timeout=REQUEST_TIMEOUT,
        )
        if resp.status_code != 0 and resp.status_code != 200:
            return {}
        data = resp.json().get("data", [])
        players = {}
        for p in data:
            pid = p.get("id")
            players[pid] = {
                "name": f"{p.get('first_name', '')} {p.get('last_name', '')}".strip(),
                "position": p.get("position", ""),
            }
        return players
    except Exception:
        return {}


def get_team_rotation(team_id, n_games: int = 7):
    """
    Approximate rotation for a team:
    - Uses last n games' stats.
    - Aggregates minutes per player.
    - Labels top 5 by avg minutes as 'Starter', rest as 'Bench/Rotation'.
    - Uses both roster and stats to resolve actual player names/positions.
    - Returns (rows, total_team_games_used)
    """
    past_games = get_team_schedule_before_today(team_id, n_games=n_games)
    if not past_games:
        return [], 0

    total_games_used = len(past_games)
    game_ids = [g["id"] for g in past_games]
    try:
        url = f"{BDL_URL}/stats"
        params = {
            "game_ids[]": [str(g) for g in game_ids],
            "per_page": 100,
        }
        resp = requests.get(
            url,
            headers=get_bdl_headers(),
            params=params,
            timeout=REQUEST_TIMEOUT,
        )
        if resp.status_code != 200:
            return [], total_games_used
        stats = resp.json().get("data", [])
    except Exception:
        return [], total_games_used

    # Aggregate minutes for this team only
    per_player = {}
    # Also capture names/positions directly from stats (for players not on current roster)
    stats_players = {}

    for s in stats:
        team = s.get("team") or {}
        if team.get("id") != team_id:
            continue

        player = s.get("player") or {}
        pid = player.get("id")
        if not pid:
            continue

        # Save player info from stats
        if pid not in stats_players:
            stats_players[pid] = {
                "name": f"{player.get('first_name', '')} {player.get('last_name', '')}".strip(),
                "position": player.get("position", ""),
            }

        min_val = parse_minutes(s.get("min"))
        if pid not in per_player:
            per_player[pid] = {"total_min": 0.0, "games_played": 0}
        per_player[pid]["total_min"] += min_val
        if min_val > 0:
            per_player[pid]["games_played"] += 1

    if not per_player:
        return [], total_games_used

    # Roster also helps for current team position info
    roster = get_team_players(team_id)
    rows = []
    for pid, agg in per_player.items():
        gp = agg["games_played"] or 1
        avg_min = agg["total_min"] / gp

        info_roster = roster.get(pid, {})
        info_stats = stats_players.get(pid, {})

        name = (
            info_roster.get("name")
            or info_stats.get("name")
            or f"Player {pid}"
        )
        position = (
            info_roster.get("position")
            or info_stats.get("position")
            or ""
        )

        rows.append(
            {
                "Player ID": pid,
                "Name": name,
                "Pos": position,
                "GP (non-DNP)": agg["games_played"],
                "Avg MIN": round(avg_min, 1),
            }
        )

    # Sort by avg minutes
    rows.sort(key=lambda r: r["Avg MIN"], reverse=True)
    # Label roles
    for idx, r in enumerate(rows):
        r["Role"] = "Starter" if idx < 5 else "Bench/Rotation"
    return rows, total_games_used


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

    # ... (rest of your existing main logic + display logic stays the same)
