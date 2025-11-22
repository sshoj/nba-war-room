import streamlit as st
import requests
from langchain_openai import ChatOpenAI
import os
import pandas as pd
from datetime import datetime, timedelta, timezone  # <--- timezone import
import difflib

# --- PAGE CONFIGURATION ---
st.set_page_config(page_title="NBA War Room (Ultimate)", page_icon="🏀", layout="wide")
st.title("🏀 NBA War Room (Ultimate Edition)")
st.markdown("Use Multi Agent AI NBA betting application Written by Saeed Hojabr")

# --- CONSTANTS & CONFIG ---
BDL_URL = "https://api.balldontlie.io/v1"
ODDS_URL = "https://api.the-odds-api.com/v4/sports/basketball_nba"
REQUEST_TIMEOUT = 10  # seconds

# --- SESSION STATE SETUP ---
if "messages" not in st.session_state:
    st.session_state.messages = []
if "analysis_data" not in st.session_state:
    st.session_state.analysis_data = None

# --- SECURE AUTHENTICATION ---
def load_keys():
    """Load keys from Streamlit secrets or sidebar inputs."""
    keys = {}

    def get_key(secret_name: str, label: str):
        if secret_name in st.secrets:
            st.sidebar.success(f"✅ {label} Key Loaded")
            return st.secrets[secret_name]
        else:
            return st.sidebar.text_input(f"{label} Key", type="password")

    # Generic labels (no provider names)
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

with st.sidebar:
    st.header("⚙️ Settings")
    api_keys = load_keys()

    st.divider()
    if st.button("New Search / Clear"):
        st.session_state.analysis_data = None
        st.session_state.messages = []
        st.rerun()

# --- BASIC HELPERS ---

def get_bdl_headers():
    """Return headers for BallDontLie requests (no Bearer prefix)."""
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


def normalize_team_name(name: str) -> str:
    """Normalize team name for fuzzy matching (remove spaces/punct, lower)."""
    if not name:
        return ""
    return "".join(ch for ch in name.lower() if ch.isalnum())


def get_team_logo_url(team_abbr: str):
    """
    Maps API abbreviations to ESPN Logo URLs.
    Most are simple (BOS -> bos), but some need correction (UTA -> utah).
    """
    if not team_abbr:
        return None

    abbr = team_abbr.upper()

    # ESPN uses slightly different codes for a few teams
    corrections = {
        "UTA": "utah",  # Jazz
        "NOP": "no",    # Pelicans
        "NYK": "ny",    # Knicks
        "GSW": "gs",    # Warriors
        "SAS": "sa",    # Spurs
        "PHX": "phx",   # Suns
        "WAS": "wsh",   # Wizards
    }

    espn_code = corrections.get(abbr, abbr.lower())
    return f"https://a.espncdn.com/i/teamlogos/nba/500/scoreboard/{espn_code}.png"


# --- BALLDONTLIE TOOLS ---

def get_player_info_smart(user_input):
    """
    Smart player search:
    1. Tries exact phrase search first.
    2. If that fails, splits words to find partial matches.
    3. Scores candidates by name and team matches.
    """
    try:
        candidates = {}
        
        # Strip common team identifiers
        clean_input = user_input.lower()
        for ignore in [" hornets", " cha", " charlotte", " suns", " phx", " lakers", " lal"]:
            clean_input = clean_input.replace(ignore, "")
        clean_input = clean_input.strip()

        queries = [clean_input]
        
        # Flip "Last First" -> "First Last"
        if " " in clean_input:
            queries.append(" ".join(clean_input.split()[::-1]))

        # Also search individual words
        if len(clean_input.split()) > 1:
            queries.extend(clean_input.split())

        found_any = False
        
        for q in queries:
            if len(q) < 3:
                continue
                
            try:
                r = requests.get(
                    url=f"{BDL_URL}/players",
                    headers=get_bdl_headers(),
                    params={"search": q, "per_page": 100},
                    timeout=REQUEST_TIMEOUT,
                )
                if r.status_code == 200:
                    data = r.json().get("data", [])
                    for p in data:
                        candidates[p["id"]] = p
                        found_any = True
            except Exception:
                pass
            
            if found_any and q == clean_input:
                break

        if not candidates:
            return None, f"Player '{user_input}' not found."

        candidate_list = list(candidates.values())
        scored_results = []
        
        user_words = user_input.lower().split()

        for p in candidate_list:
            score = 0
            fname = p['first_name'].lower()
            lname = p['last_name'].lower()
            full_name = f"{fname} {lname}"
            
            team_name = p['team']['full_name'].lower()
            team_abbr = p['team']['abbreviation'].lower()

            # 1. Name similarity (0-100)
            sim = difflib.SequenceMatcher(None, clean_input, full_name).ratio()
            score += sim * 100

            # 2. Exact name bonus
            if clean_input == full_name:
                score += 50
            
            # 3. Team match bonus
            if any(t in user_input.lower() for t in [team_name, team_abbr]):
                score += 30

            scored_results.append((score, p))

        scored_results.sort(key=lambda x: x[0], reverse=True)
        
        best_match = scored_results[0][1]
        best_p_name = f"{best_match['first_name']} {best_match['last_name']}"
        best_p_team = best_match['team']['full_name']

        return best_match, f"Found: **{best_p_name}** ({best_p_team})"

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
    """Fetch team's last n finished games (extended history) with error handling."""
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

def get_next_game_bdl(team_id, days_ahead: int = 14):
    """
    Find the next NON-FINAL game for a team using BallDontLie schedule.

    Returns:
        (matchup_str, date_str, opp_team_id, opp_team_full_name, opp_team_abbr, game_id)
        or (None, None, None, None, None, None) if not found.
    """
    try:
        season = get_current_season()
        today = datetime.now().strftime("%Y-%m-%d")
        future = (datetime.now() + timedelta(days=days_ahead)).strftime("%Y-%m-%d")

        resp = requests.get(
            f"{BDL_URL}/games",
            headers=get_bdl_headers(),
            params={
                "team_ids[]": str(team_id),
                "seasons[]": str(season),
                "start_date": today,
                "end_date": future,
                "per_page": 50,
            },
            timeout=REQUEST_TIMEOUT,
        )
        if resp.status_code != 200:
            return None, None, None, None, None, None

        data = resp.json().get("data", [])
        if not data:
            return None, None, None, None, None, None

        # Sort upcoming games by date (soonest first)
        data.sort(key=lambda x: x["date"])

        for g in data:
            status = g.get("status", "")
            # Skip games that are already final; allow Scheduled / In Progress / etc.
            if status == "Final":
                continue

            home = g.get("home_team", {})
            visitor = g.get("visitor_team", {})

            if home.get("id") == team_id:
                loc = "vs"
                opp = visitor
            else:
                loc = "@"
                opp = home

            matchup_str = f"{loc} {opp.get('full_name', 'Unknown')}"
            date_str = g.get("date", "").split("T")[0]
            return (
                matchup_str,
                date_str,
                opp.get("id"),
                opp.get("full_name"),
                opp.get("abbreviation"),
                g.get("id"),
            )

        return None, None, None, None, None, None

    except Exception:
        return None, None, None, None, None, None
        
def get_player_stats_for_games(player_id, game_ids):
    """
    Robust way to get a player's stats for specific games.

    For each game_id:
      - fetch /stats?game_ids[]=gid&per_page=100
      - find the row where player.id == player_id
      - store it in a dict keyed by game_id

    Returns:
        { game_id: stat_row_dict, ... }
    """
    stats_by_game = {}
    if not game_ids:
        return stats_by_game

    for gid in game_ids:
        try:
            resp = requests.get(
                f"{BDL_URL}/stats",
                headers=get_bdl_headers(),
                params={"game_ids[]": str(gid), "per_page": 100},
                timeout=REQUEST_TIMEOUT,
            )
            if resp.status_code != 200:
                continue

            data = resp.json().get("data", [])
            if not isinstance(data, list):
                continue

            # Find this player's row in that game
            for s in data:
                player = s.get("player") or {}
                if player.get("id") == player_id:
                    stats_by_game[gid] = s
                    break  # done for this game

        except Exception:
            # If any single game fails, just skip it
            continue

    return stats_by_game



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


def compute_team_advanced_stats(team_id, games):
    """
    Compute advanced team metrics over a window of games.

    Inputs:
        team_id: int (BallDontLie team id)
        games:   list of game dicts (e.g. from get_team_schedule_before_today)

    Returns dict:
        {
          "games_used": int,
          "off_rtg": float,    # Off Rtg (points per 100 poss)
          "def_rtg": float,    # Def Rtg (points allowed per 100 poss)
          "net_rtg": float,    # Off - Def
          "pace": float,       # possessions per game (approx)

          "fg_pct": float,     # FG%
          "two_pct": float,    # 2P%
          "three_pct": float,  # 3P%
          "three_pa_rate": float,  # 3PA / FGA
          "ft_pct": float,     # FT%
          "ftr": float,        # FTA / FGA

          "orb_pct": float,    # offensive rebounding %
          "drb_pct": float,    # defensive rebounding %
          "reb_pg": float,     # total rebounds per game

          "tov_pg": float,     # turnovers per game
          "tov_pct": float,    # turnovers per possession
        }
    """
    empty = {
        "games_used": 0,
        "off_rtg": 0.0,
        "def_rtg": 0.0,
        "net_rtg": 0.0,
        "pace": 0.0,
        "fg_pct": 0.0,
        "two_pct": 0.0,
        "three_pct": 0.0,
        "three_pa_rate": 0.0,
        "ft_pct": 0.0,
        "ftr": 0.0,
        "orb_pct": 0.0,
        "drb_pct": 0.0,
        "reb_pg": 0.0,
        "tov_pg": 0.0,
        "tov_pct": 0.0,
    }

    if not games:
        return empty

    game_ids = [g.get("id") for g in games if g.get("id") is not None]
    if not game_ids:
        return empty

    # --- fetch ALL stats rows for these games (paginate) ---
    all_stats = []
    try:
        page = 1
        while True:
            params = {
                "game_ids[]": [str(gid) for gid in game_ids],
                "per_page": 100,
                "page": page,
            }
            resp = requests.get(
                f"{BDL_URL}/stats",
                headers=get_bdl_headers(),
                params=params,
                timeout=REQUEST_TIMEOUT,
            )
            if resp.status_code != 200:
                break
            batch = resp.json().get("data", [])
            if not batch:
                break
            all_stats.extend(batch)
            if len(batch) < 100:
                break
            page += 1
    except Exception:
        all_stats = []

    if not all_stats:
        return empty

    # --- aggregate per game: team vs opponent ---
    per_game = {}
    for s in all_stats:
        game = s.get("game") or {}
        gid = game.get("id")
        if gid not in game_ids:
            continue

        t = s.get("team") or {}
        side = "team" if t.get("id") == team_id else "opp"

        if gid not in per_game:
            per_game[gid] = {
                "team": {
                    "pts": 0, "fgm": 0, "fga": 0,
                    "fg3m": 0, "fg3a": 0,
                    "ftm": 0, "fta": 0,
                    "oreb": 0, "dreb": 0, "reb": 0,
                    "tov": 0,
                },
                "opp": {
                    "pts": 0, "fgm": 0, "fga": 0,
                    "fg3m": 0, "fg3a": 0,
                    "ftm": 0, "fta": 0,
                    "oreb": 0, "dreb": 0, "reb": 0,
                    "tov": 0,
                },
            }

        bucket = per_game[gid][side]
        bucket["pts"] += s.get("pts", 0)
        bucket["fgm"] += s.get("fgm", 0)
        bucket["fga"] += s.get("fga", 0)
        bucket["fg3m"] += s.get("fg3m", 0)
        bucket["fg3a"] += s.get("fg3a", 0)
        bucket["ftm"] += s.get("ftm", 0)
        bucket["fta"] += s.get("fta", 0)
        bucket["oreb"] += s.get("oreb", 0)
        bucket["dreb"] += s.get("dreb", 0)
        bucket["reb"] += s.get("reb", 0)
        bucket["tov"] += s.get("turnover", 0)

    # --- accumulate over games ---
    games_used = 0
    tot_team_pts = tot_opp_pts = 0.0
    tot_team_poss = tot_opp_poss = 0.0

    tot_fgm = tot_fga = 0.0
    tot_fg3m = tot_fg3a = 0.0
    tot_ftm = tot_fta = 0.0
    tot_oreb = tot_dreb = tot_reb = 0.0
    tot_opp_oreb = tot_opp_dreb = 0.0
    tot_tov = 0.0

    for gid in game_ids:
        rec = per_game.get(gid)
        if not rec:
            continue
        team = rec["team"]
        opp = rec["opp"]

        team_poss = (
            team["fga"]
            - team["oreb"]
            + team["tov"]
            + 0.44 * team["fta"]
        )
        opp_poss = (
            opp["fga"]
            - opp["oreb"]
            + opp["tov"]
            + 0.44 * opp["fta"]
        )

        tot_team_pts += team["pts"]
        tot_opp_pts += opp["pts"]
        tot_team_poss += team_poss
        tot_opp_poss += opp_poss

        tot_fgm += team["fgm"]
        tot_fga += team["fga"]
        tot_fg3m += team["fg3m"]
        tot_fg3a += team["fg3a"]
        tot_ftm += team["ftm"]
        tot_fta += team["fta"]
        tot_oreb += team["oreb"]
        tot_dreb += team["dreb"]
        tot_reb += team["reb"]
        tot_opp_oreb += opp["oreb"]
        tot_opp_dreb += opp["dreb"]
        tot_tov += team["tov"]

        games_used += 1

    if games_used == 0 or tot_team_poss <= 0:
        return empty

    off_rtg = 100.0 * tot_team_pts / tot_team_poss
    def_rtg = 100.0 * tot_opp_pts / tot_team_poss
    net_rtg = off_rtg - def_rtg

    pace = (tot_team_poss + tot_opp_poss) / (2.0 * games_used)

    fg_pct = tot_fgm / tot_fga if tot_fga > 0 else 0.0
    two_fgm = tot_fgm - tot_fg3m
    two_fga = tot_fga - tot_fg3a
    two_pct = two_fgm / two_fga if two_fga > 0 else 0.0
    three_pct = tot_fg3m / tot_fg3a if tot_fg3a > 0 else 0.0
    three_pa_rate = tot_fg3a / tot_fga if tot_fga > 0 else 0.0

    ft_pct = tot_ftm / tot_fta if tot_fta > 0 else 0.0
    ftr = tot_fta / tot_fga if tot_fga > 0 else 0.0

    orb_den = tot_oreb + tot_opp_dreb
    drb_den = tot_dreb + tot_opp_oreb
    orb_pct = tot_oreb / orb_den if orb_den > 0 else 0.0
    drb_pct = tot_dreb / drb_den if drb_den > 0 else 0.0
    reb_pg = tot_reb / games_used

    tov_pg = tot_tov / games_used
    tov_pct = tot_tov / tot_team_poss if tot_team_poss > 0 else 0.0

    return {
        "games_used": games_used,
        "off_rtg": off_rtg,
        "def_rtg": def_rtg,
        "net_rtg": net_rtg,
        "pace": pace,
        "fg_pct": fg_pct,
        "two_pct": two_pct,
        "three_pct": three_pct,
        "three_pa_rate": three_pa_rate,
        "ft_pct": ft_pct,
        "ftr": ftr,
        "orb_pct": orb_pct,
        "drb_pct": drb_pct,
        "reb_pg": reb_pg,
        "tov_pg": tov_pg,
        "tov_pct": tov_pct,
    }


def get_team_players(team_id):
    """Fetch current roster (players + positions) for a team."""
    try:
        resp = requests.get(
            f"{BDL_URL}/players",
            headers=get_bdl_headers(),
            params={"team_ids[]": str(team_id), "per_page": 100},
            timeout=REQUEST_TIMEOUT,
        )
        if resp.status_code != 200:
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


def get_bdl_team_by_name(name: str):
    """Given a plain team name (from Odds API), find the best-matching BallDontLie team."""
    try:
        resp = requests.get(
            f"{BDL_URL}/teams",
            headers=get_bdl_headers(),
            timeout=REQUEST_TIMEOUT,
        )
        if resp.status_code != 200:
            return {}
        data = resp.json().get("data", [])
        if not isinstance(data, list):
            data = []

        target = normalize_team_name(name)
        best = None
        best_score = 0.0
        for t in data:
            full_name = t.get("full_name", "")
            n = normalize_team_name(full_name)
            score = difflib.SequenceMatcher(a=target, b=n).ratio()
            if score > best_score:
                best_score = score
                best = t
        return best or {}
    except Exception:
        return {}


def get_team_rotation(team_id, n_games: int = 7):
    """
    Approximate rotation for a team:
    - Uses last n games' stats.
    - Aggregates minutes + basic box for each player.
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

    # Aggregate minutes & stats for this team only
    per_player = {}
    stats_players = {}

    for s in stats:
        team = s.get("team") or {}
        if team.get("id") != team_id:
            continue

        player = s.get("player") or {}
        pid = player.get("id")
        if not pid:
            continue

        if pid not in stats_players:
            stats_players[pid] = {
                "name": f"{player.get('first_name', '')} {player.get('last_name', '')}".strip(),
                "position": player.get("position", ""),
            }

        min_val = parse_minutes(s.get("min"))
        pts = s.get("pts", 0)
        reb = s.get("reb", 0)
        ast = s.get("ast", 0)
        fg3m = s.get("fg3m", 0)

        if pid not in per_player:
            per_player[pid] = {
                "total_min": 0.0,
                "gp_non_dnp": 0,
                "total_pts": 0,
                "total_reb": 0,
                "total_ast": 0,
                "total_3pm": 0,
            }

        per_player[pid]["total_min"] += min_val
        per_player[pid]["total_pts"] += pts
        per_player[pid]["total_reb"] += reb
        per_player[pid]["total_ast"] += ast
        per_player[pid]["total_3pm"] += fg3m

        if min_val > 0:
            per_player[pid]["gp_non_dnp"] += 1

    if not per_player:
        return [], total_games_used

    roster = get_team_players(team_id)
    rows = []
    for pid, agg in per_player.items():
        gp = agg["gp_non_dnp"] or 1
        avg_min = agg["total_min"] / gp
        avg_pts = agg["total_pts"] / gp
        avg_reb = agg["total_reb"] / gp
        avg_ast = agg["total_ast"] / gp
        avg_3pm = agg["total_3pm"] / gp

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
                "GP (non-DNP)": agg["gp_non_dnp"],
                "Avg MIN": round(avg_min, 1),
                "Avg PTS": round(avg_pts, 1),
                "Avg REB": round(avg_reb, 1),
                "Avg AST": round(avg_ast, 1),
                "Avg 3PM": round(avg_3pm, 1),
            }
        )

    rows.sort(key=lambda r: r["Avg MIN"], reverse=True)
    for idx, r in enumerate(rows):
        r["Role"] = "Starter" if idx < 5 else "Bench/Rotation"
    return rows, total_games_used


# --- BETTING API TOOLS (NOW CANONICAL FOR NEXT GAME) ---

def get_betting_game_and_odds(player_name, team_name, bookmakers=None, debug: bool = False):
    """
    Canonical source of the upcoming game for this player/team.

    Flow:
      1) Use /odds with markets=h2h (featured markets only) to:
         - Find the correct event for the team
         - Get all moneyline prices from all books
      2) Use /events/{eventId}/odds with player_* markets to:
         - Get player props for that specific event

    Returns dict:
    {
      "odds_text": str,
      "tipoff_iso": str or None,
      "home_team": str or None,
      "away_team": str or None,
    }
    """
    api_key = os.environ.get("ODDS_API_KEY")
    if not api_key:
        return {
            "odds_text": "Betting API key missing.",
            "tipoff_iso": None,
            "home_team": None,
            "away_team": None,
        }

    try:
        # --- 1) GET GAME LINES (FEATURED MARKETS ONLY) ---
        # /odds only supports featured markets like h2h, spreads, totals.
        # Player props here would cause INVALID_MARKET (422).
        odds_resp = requests.get(
            f"{ODDS_URL}/odds",
            params={
                "apiKey": api_key,
                "regions": "us",         # adjust if you want multiple regions
                "markets": "h2h",        # moneyline only here to avoid 422
                "dateFormat": "iso",
            },
            timeout=REQUEST_TIMEOUT,
        )

        if odds_resp.status_code != 200:
            try:
                msg = odds_resp.json().get("message", odds_resp.text)
            except Exception:
                msg = odds_resp.text
            return {
                "odds_text": f"Error fetching games from Betting API (status {odds_resp.status_code}): {msg}",
                "tipoff_iso": None,
                "home_team": None,
                "away_team": None,
            }

        games = odds_resp.json()
        if debug:
            st.write("DEBUG – /odds events:", games)

        if not isinstance(games, list) or not games:
            return {
                "odds_text": "No betting lines available.",
                "tipoff_iso": None,
                "home_team": None,
                "away_team": None,
            }

        team_norm = normalize_team_name(team_name)
        best_future_game = None
        best_future_time = None
        closest_any_game = None
        closest_any_time = None

        now_utc = datetime.now(timezone.utc)

        # --- pick the nearest future event (or closest overall as fallback) ---
        for g in games:
            ht = g.get("home_team") or ""
            at = g.get("away_team") or ""

            if team_norm not in normalize_team_name(ht) and team_norm not in normalize_team_name(at):
                continue

            ct = g.get("commence_time")
            if not ct:
                continue

            try:
                dt = datetime.fromisoformat(ct.replace("Z", "+00:00"))
            except Exception:
                continue

            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)

            # Future game for that team
            if dt >= now_utc:
                if best_future_time is None or dt < best_future_time:
                    best_future_time = dt
                    best_future_game = g

            # Closest event regardless of past/future
            if closest_any_time is None or abs((dt - now_utc).total_seconds()) < abs((closest_any_time - now_utc).total_seconds()):
                closest_any_time = dt
                closest_any_game = g

        selected_game = best_future_game or closest_any_game
        tipoff_dt = best_future_time or closest_any_time

        if not selected_game:
            return {
                "odds_text": f"No active betting lines found for {team_name}.",
                "tipoff_iso": None,
                "home_team": None,
                "away_team": None,
            }

        game_id = selected_game.get("id")
        tipoff_iso = tipoff_dt.isoformat() if tipoff_dt else selected_game.get("commence_time")
        home_team = selected_game.get("home_team")
        away_team = selected_game.get("away_team")

        # --- game moneyline from ALL bookmakers (already in /odds response) ---
        bookmakers_list = selected_game.get("bookmakers", [])
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

            parts = [
                f"{o.get('name', 'Team')} ({o.get('price', 'N/A')})"
                for o in outcomes
            ]
            ml_str = " vs ".join(parts)
            moneyline_lines.append(f"- **{b_title}**: {ml_str}")

        # --- 2) PLAYER PROPS VIA /events/{id}/odds (non-featured markets allowed here) ---
        props_lines = []
        props_bookmaker_title = None

        try:
            props_params = {
                "apiKey": api_key,
                "regions": "us",
                "markets": "player_points,player_rebounds,player_assists",
                "dateFormat": "iso",
            }
            if bookmakers:
                props_params["bookmakers"] = bookmakers

            props_resp = requests.get(
                f"{ODDS_URL}/events/{game_id}/odds",
                params=props_params,
                timeout=REQUEST_TIMEOUT,
            )

            if props_resp.status_code == 200:
                props_data = props_resp.json()
                props_books = props_data.get("bookmakers", [])

                # Prefer FanDuel if available
                preferred_key = "fanduel"
                props_bookmaker = next(
                    (b for b in props_books if b.get("key") == preferred_key),
                    props_books[0] if props_books else None,
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

            # If 404 / 422 / etc on props, we just skip props and keep moneyline
        except Exception:
            # Silently ignore props errors; we still have game odds
            pass

        # --- build final text ---
        sections = []

        if props_lines:
            label = f"**Player Props ({props_bookmaker_title})**" if props_bookmaker_title else "**Player Props**"
            sections.append(label + ":\n" + " | ".join(props_lines))

        if moneyline_lines:
            sections.append("**Game Moneyline (All Books):**\n" + "\n".join(moneyline_lines))

        odds_text = "No odds available."
        if sections:
            odds_text = "\n\n".join(sections)

        return {
            "odds_text": odds_text,
            "tipoff_iso": tipoff_iso,
            "home_team": home_team,
            "away_team": away_team,
        }

    except Exception as e:
        return {
            "odds_text": f"Error fetching odds: {e}",
            "tipoff_iso": None,
            "home_team": None,
            "away_team": None,
        }



# --- CORE ANALYSIS PIPELINE ---

def run_analysis(player_input: str, llm: ChatOpenAI):
    """Execute the full pipeline once user hits the Run button."""
    status_box = st.status("🔍 Scouting in progress...", expanded=True)

    try:
        # 1. Player Info
        status_box.write("Finding player...")
        player_obj, msg = get_player_info_smart(player_input)
        if not player_obj:
            status_box.update(label="Player Not Found", state="error")
            st.error(msg)
            st.stop()

        pid = player_obj["id"]
        fname = player_obj["first_name"]
        lname = player_obj["last_name"]
        tid = player_obj["team"]["id"]
        tname = player_obj["team"]["full_name"]
        tabbr = player_obj["team"]["abbreviation"]
        st.success(msg)

        # 2. Next game from BallDontLie (primary schedule source)
        status_box.write("Finding next scheduled game...")
        matchup = "Unknown matchup"
        game_date_display = "Unknown date"
        opp_id = None
        opp_name_bdl = "Unknown opponent"
        opp_abbr = ""

        (
            bdl_matchup,
            bdl_date,
            bdl_opp_id,
            bdl_opp_name,
            bdl_opp_abbr,
            _,
        ) = get_next_game_bdl(tid, days_ahead=14)

        if bdl_matchup and bdl_date and bdl_opp_id:
            matchup = bdl_matchup
            game_date_display = bdl_date
            opp_id = bdl_opp_id
            if bdl_opp_name:
                opp_name_bdl = bdl_opp_name
            if bdl_opp_abbr:
                opp_abbr = bdl_opp_abbr

        # 3. Betting Game + Odds (may or may not align perfectly with BDL)
        status_box.write("Finding betting event & lines...")
        betting = get_betting_game_and_odds(f"{fname} {lname}", tname)
        betting_lines = betting["odds_text"]
        tipoff_iso = betting["tipoff_iso"]
        odds_home = betting["home_team"]
        odds_away = betting["away_team"]

        # If BDL couldn't find next game, try to infer matchup from Betting API
        if matchup == "Unknown matchup" and odds_home and odds_away:
            norm_team = normalize_team_name(tname)
            home_norm = normalize_team_name(odds_home)
            away_norm = normalize_team_name(odds_away)

            if norm_team in home_norm:
                opp_guess = odds_away
                loc = "vs"
            elif norm_team in away_norm:
                opp_guess = odds_home
                loc = "@"
            else:
                opp_guess = odds_away
                loc = "vs"

            matchup = f"{loc} {opp_guess}"

            # Map guessed opponent into BDL if we still don't have opp_id
            if not opp_id:
                opp_team_bdl = get_bdl_team_by_name(opp_guess)
                opp_id = opp_team_bdl.get("id")
                opp_abbr = opp_team_bdl.get("abbreviation", opp_abbr)
                opp_name_bdl = opp_team_bdl.get("full_name", opp_guess)

        # If Betting API has tipoff time and BDL didn't give a date, use betting date
        if tipoff_iso and game_date_display == "Unknown date":
            try:
                tip_dt = datetime.fromisoformat(tipoff_iso.replace("Z", "+00:00"))
                game_date_display = tip_dt.date().isoformat()
            except Exception:
                pass

        # 4. Injuries
        status_box.write("Fetching injuries...")
        inj_home = get_team_injuries(tid) if tid else "N/A"
        inj_opp = get_team_injuries(opp_id) if opp_id else "N/A"

        # 5. Home Team Stats (Last 7 Games + Strict DNP)
        status_box.write("Crunching stats...")
        past_games = get_team_schedule_before_today(tid, n_games=7)
        adv_home = compute_team_advanced_stats(tid, past_games)
        gids = [g["id"] for g in past_games]
        stats_by_game = get_player_stats_for_games(pid, gids)

        log_lines = []
stats_rows = []

for g in past_games:
    gid = g["id"]
    d = g["date"].split("T")[0]

    home = g.get("home_team", {})
    visitor = g.get("visitor_team", {})

    if home.get("id") == tid:
        opp_abbr_log = visitor.get("abbreviation", "UNK")
        loc = "vs"
    else:
        opp_abbr_log = home.get("abbreviation", "UNK")
        loc = "@"

    stat = stats_by_game.get(gid)

    # STRICT DNP CHECK
    min_val_raw = stat.get("min") if stat else None
    played = bool(
        min_val_raw
        and str(min_val_raw) not in ("0", "00:00", "")
    )

    if played:
        fg_pct = stat.get("fg_pct")
        fg = f"{fg_pct * 100:.0f}%" if fg_pct else "0%"
        fg3m = stat.get("fg3m", 0)
        fg3a = stat.get("fg3a", 0)
        fg3 = f"{fg3m}/{fg3a}"
        line = (
            f"MIN:{min_val_raw} | PTS:{stat.get('pts', 0)} "
            f"REB:{stat.get('reb', 0)} AST:{stat.get('ast', 0)} | FG:{fg} 3PT:{fg3}"
        )
    else:
        line = "⛔ DNP (Did Not Play)"

    log_lines.append(f"[{d}] {loc} {opp_abbr_log} | {line}")

    mins_numeric = parse_minutes(min_val_raw) if played else 0
    stats_rows.append(
        {
            "Date": d,
            "Location": loc,
            "Opponent": opp_abbr_log,
            "MIN": mins_numeric,
            "PTS": stat.get("pts", 0) if stat else 0,
            "REB": stat.get("reb", 0) if stat else 0,
            "AST": stat.get("ast", 0) if stat else 0,
            "3PM": stat.get("fg3m", 0) if stat else 0,
            "3PA": stat.get("fg3a", 0) if stat else 0,
            "Is_DNP": not played,
        }
    )


        final_log = "\n".join(log_lines)

        # 6. Opponent team's last 7 results (from BDL) + advanced stats
        opp_results_rows = []
        opp_past_games = []
        adv_opp = {}
        if opp_id:
            opp_past_games = get_team_schedule_before_today(opp_id, n_games=7)
            adv_opp = compute_team_advanced_stats(opp_id, opp_past_games)
            for g in opp_past_games:
                d = g["date"].split("T")[0]
                home = g.get("home_team", {})
                visitor = g.get("visitor_team", {})
                home_score = g.get("home_team_score", 0)
                visitor_score = g.get("visitor_team_score", 0)

                is_home = home.get("id") == opp_id
                loc = "vs" if is_home else "@"
                opp_team_obj = visitor if is_home else home
                opp_abbr_team = opp_team_obj.get("abbreviation", "UNK")

                if is_home:
                    team_score = home_score
                    opp_score = visitor_score
                else:
                    team_score = visitor_score
                    opp_score = home_score

                if team_score > opp_score:
                    result = "W"
                elif team_score < opp_score:
                    result = "L"
                else:
                    result = "T"

                opp_results_rows.append(
                    {
                        "Date": d,
                        "Location": loc,
                        "Opponent": opp_abbr_team,
                        "Team Score": team_score,
                        "Opponent Score": opp_score,
                        "Result": result,
                    }
                )

        # 7. Team form snapshot (strength/weakness proxy)
        team_form = compute_team_form(past_games, tid)

        # 8. Rotations
        rotation_rows, rotation_games_used = get_team_rotation(tid, n_games=7)
        opp_rotation_rows, opp_rotation_games_used = ([], 0)
        if opp_id:
            opp_rotation_rows, opp_rotation_games_used = get_team_rotation(opp_id, n_games=7)

        # 9. GPT Analysis
        status_box.write("Consulting AI coach...")
        prompt = f"""
Role: Expert Sports Bettor.
Target: {fname} {lname} ({tname})
Matchup: {matchup}
Game Date: {game_date_display}

ODDS:
{betting_lines}

INJURIES:
{tname}: {inj_home}
{opp_name_bdl}: {inj_opp}

RECENT FORM (Last 7 Team Games):
{final_log}

TEAM FORM (Last {team_form.get('games_used', 0)} Games):
- Avg Points For: {team_form.get('pf', 0):.1f}
- Avg Points Against: {team_form.get('pa', 0):.1f}
- Approx Net Rating: {team_form.get('net', 0):+.1f}
- Record: {team_form.get('wins', 0)}–{team_form.get('losses', 0)}

Tasks:
1. Line Value: Compare stats to the odds (if player props are available).
2. Prediction: Project points / rebounds / assists.
3. Recommendation: Suggest a lean (prop or moneyline) with risk language (edge, high variance).
4. Team View: Briefly describe this team's offensive and defensive strengths/weaknesses based on the form.

Rules:
- Do NOT guarantee outcomes.
- Do NOT claim certainty.
- Use terms like "lean", "slight edge", "volatile", "high variance".
"""
        analysis = llm.invoke(prompt).content

        # Save in session state
        st.session_state.analysis_data = {
            "player": f"{fname} {lname}",
            "team_name": tname,
            "team_abbr": tabbr,
            "matchup": matchup,
            "date": game_date_display,
            "odds": betting_lines,
            "log": final_log,
            "analysis": analysis,
            "inj_home": inj_home,
            "inj_opp": inj_opp,
            "context": prompt + "\n\nAnalysis:\n" + analysis,
            "stats_rows": stats_rows,
            "opp_results_rows": opp_results_rows,
            "opp_name": opp_name_bdl,
            "opp_abbr": opp_abbr,
            "team_form": team_form,
            "rotation_rows": rotation_rows,
            "rotation_games_used": rotation_games_used,
            "opp_rotation_rows": opp_rotation_rows,
            "opp_rotation_games_used": opp_rotation_games_used,
            "tipoff_iso": tipoff_iso,
            "adv_home": adv_home,
            "adv_opp": adv_opp,
        }
        st.session_state.messages = [{"role": "assistant", "content": analysis}]
        status_box.update(label="Ready!", state="complete", expanded=False)
        st.rerun()

    except Exception as e:
        status_box.update(label="System Error", state="error")
        st.error(f"Error: {e}")

# --- MAIN APP ENTRY ---

if api_keys.get("bdl") and api_keys.get("openai") and api_keys.get("odds"):

    llm = ChatOpenAI(model="gpt-4o", temperature=0.5, api_key=api_keys["openai"])

    col1, col2 = st.columns([3, 1])
    with col1:
        p_name = st.text_input("Player Name", "Devin Booker")
    with col2:
        st.write("")
        st.write("")
        run_btn = st.button("🚀 Run Analysis", type="primary", width="stretch")

    if run_btn:
        run_analysis(p_name, llm)

    data = st.session_state.analysis_data

    if data:
        st.divider()

        p_label = data.get("player", "Unknown")
        m_label = data.get("matchup", "Unknown")
        d_label = data.get("date", "")

        team_abbr = data.get("team_abbr")
        opp_abbr = data.get("opp_abbr")

        home_logo = get_team_logo_url(team_abbr)
        away_logo = get_team_logo_url(opp_abbr)

        # Header: logos + matchup + countdown
        logo_col1, mid_col, logo_col2 = st.columns([1, 3, 1])
        with logo_col1:
            if home_logo:
                st.image(home_logo, width=80)
            if team_abbr:
                st.caption(team_abbr)
        with mid_col:
            st.markdown(f"### 📊 Report: {p_label}  \n**Matchup:** {m_label}")
            st.caption(f"Date: {d_label}")

            tipoff_iso = data.get("tipoff_iso")
            if tipoff_iso:
                try:
                    tip_dt = datetime.fromisoformat(tipoff_iso.replace("Z", "+00:00"))
                    now = datetime.now(timezone.utc)
                    delta = tip_dt - now
                    secs = int(delta.total_seconds())
                    if secs > 0:
                        hours, rem = divmod(secs, 3600)
                        minutes, _ = divmod(rem, 60)
                        st.metric("Time to tipoff (approx)", f"{hours}h {minutes}m")
                    else:
                        st.metric("Time to tipoff (approx)", "Tipoff passed")
                except Exception:
                    pass
        with logo_col2:
            if away_logo:
                st.image(away_logo, width=80)
            if opp_abbr:
                st.caption(opp_abbr)

        st.info(f"🎰 **Market Odds:**\n\n{data.get('odds', 'No odds data')}")

        # Team Form metrics
        team_form = data.get("team_form") or {}
        if team_form:
            games_used = team_form.get("games_used", 0) or 0
            label_games = games_used if games_used > 0 else 7
            st.subheader(f"📈 Team Form (Last {label_games} Games)")
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Offense (PF)", f"{team_form.get('pf', 0):.1f} PPG")
            c2.metric("Defense (PA)", f"{team_form.get('pa', 0):.1f} PPG")
            c3.metric("Net Rating (approx)", f"{team_form.get('net', 0):+.1f}")
            c4.metric("Record", f"{team_form.get('wins', 0)}–{team_form.get('losses', 0)}")

        # Advanced team metrics (home + opponent)
        adv_home = data.get("adv_home") or {}
        adv_opp = data.get("adv_opp") or {}

        if (adv_home and adv_home.get("games_used", 0) > 0) or (adv_opp and adv_opp.get("games_used", 0) > 0):
            st.subheader("📊 Advanced Team Metrics (Recent Games)")
            col_home, col_opp = st.columns(2)

            if adv_home and adv_home.get("games_used", 0) > 0:
                with col_home:
                    st.markdown(f"**{data.get('team_name', 'Home Team')}**  \n_Games: {adv_home.get('games_used', 0)}_")
                    m1, m2, m3 = st.columns(3)
                    m1.metric("Off Rtg", f"{adv_home.get('off_rtg', 0):.1f}")
                    m2.metric("Def Rtg", f"{adv_home.get('def_rtg', 0):.1f}")
                    m3.metric("Net Rtg", f"{adv_home.get('net_rtg', 0):+.1f}")

                    m4, m5, m6 = st.columns(3)
                    m4.metric("Pace", f"{adv_home.get('pace', 0):.1f}")
                    m5.metric("FG%", f"{adv_home.get('fg_pct', 0)*100:.1f}%")
                    m6.metric("3P%", f"{adv_home.get('three_pct', 0)*100:.1f}%")

                    m7, m8, m9 = st.columns(3)
                    m7.metric("FT%", f"{adv_home.get('ft_pct', 0)*100:.1f}%")
                    m8.metric("3PA Rate", f"{adv_home.get('three_pa_rate', 0):.2f}")
                    m9.metric("FTr", f"{adv_home.get('ftr', 0):.2f}")

                    m10, m11, m12 = st.columns(3)
                    m10.metric("ORB%", f"{adv_home.get('orb_pct', 0)*100:.1f}%")
                    m11.metric("DRB%", f"{adv_home.get('drb_pct', 0)*100:.1f}%")
                    m12.metric("REB/G", f"{adv_home.get('reb_pg', 0):.1f}")

                    m13, m14 = st.columns(2)
                    m13.metric("TOV/G", f"{adv_home.get('tov_pg', 0):.1f}")
                    m14.metric("TOV%", f"{adv_home.get('tov_pct', 0)*100:.1f}%")

            if adv_opp and adv_opp.get("games_used", 0) > 0:
                with col_opp:
                    st.markdown(f"**{data.get('opp_name', 'Opponent Team')}**  \n_Games: {adv_opp.get('games_used', 0)}_")
                    m1, m2, m3 = st.columns(3)
                    m1.metric("Off Rtg", f"{adv_opp.get('off_rtg', 0):.1f}")
                    m2.metric("Def Rtg", f"{adv_opp.get('def_rtg', 0):.1f}")
                    m3.metric("Net Rtg", f"{adv_opp.get('net_rtg', 0):+.1f}")

                    m4, m5, m6 = st.columns(3)
                    m4.metric("Pace", f"{adv_opp.get('pace', 0):.1f}")
                    m5.metric("FG%", f"{adv_opp.get('fg_pct', 0)*100:.1f}%")
                    m6.metric("3P%", f"{adv_opp.get('three_pct', 0)*100:.1f}%")

                    m7, m8, m9 = st.columns(3)
                    m7.metric("FT%", f"{adv_opp.get('ft_pct', 0)*100:.1f}%")
                    m8.metric("3PA Rate", f"{adv_opp.get('three_pa_rate', 0):.2f}")
                    m9.metric("FTr", f"{adv_opp.get('ftr', 0):.2f}")

                    m10, m11, m12 = st.columns(3)
                    m10.metric("ORB%", f"{adv_opp.get('orb_pct', 0)*100:.1f}%")
                    m11.metric("DRB%", f"{adv_opp.get('drb_pct', 0)*100:.1f}%")
                    m12.metric("REB/G", f"{adv_opp.get('reb_pg', 0):.1f}")

                    m13, m14 = st.columns(2)
                    m13.metric("TOV/G", f"{adv_opp.get('tov_pg', 0):.1f}")
                    m14.metric("TOV%", f"{adv_opp.get('tov_pct', 0)*100:.1f}%")

        # Rotations
        rotation_rows = data.get("rotation_rows")
        rotation_games_used = data.get("rotation_games_used", 0)
        if rotation_rows:
            games_label = rotation_games_used if rotation_games_used else 7
            st.subheader(
                f"🧩 {data.get('team_name', 'Team')} Rotation & Stats "
                f"(Last {games_label} Team Games)"
            )
            df_rot = pd.DataFrame(rotation_rows)
            if "Player ID" in df_rot.columns:
                df_rot = df_rot.drop(columns=["Player ID"])
            st.dataframe(df_rot, width="stretch")
        opp_rotation_rows = data.get("opp_rotation_rows")
        opp_rotation_games_used = data.get("opp_rotation_games_used", 0)
        if opp_rotation_rows:
            games_label_opp = opp_rotation_games_used if opp_rotation_games_used else 7
            opp_name = data.get("opp_name", "Opponent Team")
            st.subheader(
                f"🧩 {opp_name} Rotation & Stats "
                f"(Last {games_label_opp} Team Games)"
            )
            df_opp_rot = pd.DataFrame(opp_rotation_rows)
            if "Player ID" in df_opp_rot.columns:
                df_opp_rot = df_opp_rot.drop(columns=["Player ID"])
            st.dataframe(df_opp_rot, width="stretch")

        # Player stats + KPIs
        stats_rows = data.get("stats_rows")
        if stats_rows:
            df_stats = pd.DataFrame(stats_rows)

            try:
                df_played = df_stats[~df_stats["Is_DNP"]].copy()
                if not df_played.empty:
                    avg_min = df_played["MIN"].mean()
                    avg_pts = df_played["PTS"].mean()
                    avg_reb = df_played["REB"].mean()
                    avg_ast = df_played["AST"].mean()
                    avg_3pm = df_played["3PM"].mean()

                    st.subheader(f"🎯 {p_label} – Key Averages (Last Games Played)")
                    kc1, kc2, kc3, kc4, kc5 = st.columns(5)
                    kc1.metric("MIN", f"{avg_min:.1f}")
                    kc2.metric("PTS", f"{avg_pts:.1f}")
                    kc3.metric("REB", f"{avg_reb:.1f}")
                    kc4.metric("AST", f"{avg_ast:.1f}")
                    kc5.metric("3PM", f"{avg_3pm:.1f}")
            except Exception:
                pass

            st.subheader(f"📜 {p_label} – Game Log (Last Team Games)")
            st.dataframe(df_stats, width="stretch")

            last_played = next((row for row in stats_rows if not row["Is_DNP"]), None)
            if last_played:
                st.subheader("🕒 Last Game Played (Most Recent Non-DNP)")
                st.table(
                    pd.DataFrame(
                        [
                            {
                                "Date": last_played["Date"],
                                "Location": last_played["Location"],
                                "Opponent": last_played["Opponent"],
                                "MIN": last_played["MIN"],
                                "PTS": last_played["PTS"],
                                "REB": last_played["REB"],
                                "AST": last_played["AST"],
                                "3PM": last_played["3PM"],
                                "3PA": last_played["3PA"],
                            }
                        ]
                    )
                )

            try:
                df_played_chart = df_stats[~df_stats["Is_DNP"]].copy()
                if not df_played_chart.empty:
                    df_played_chart.set_index("Date", inplace=True)
                    st.line_chart(df_played_chart[["PTS", "REB", "AST"]])
            except Exception:
                pass

        opp_rows = data.get("opp_results_rows")
        if opp_rows:
            opp_name = data.get("opp_name", "Opponent Team")
            st.subheader(f"📉 {opp_name} – Recent Results (Last Team Games)")
            df_opp = pd.DataFrame(opp_rows)
            st.dataframe(df_opp, width="stretch")

        with st.expander("View Raw Logs & Injuries", expanded=False):
            st.markdown(f"**Player:** {p_label}")
            st.markdown(f"**Matchup:** {m_label}")
            st.markdown(f"**Date:** {d_label}")

            c1, c2 = st.columns(2)
            c1.warning(f"Home Injuries:\n{data.get('inj_home', 'N/A')}")
            c2.error(f"Away Injuries:\n{data.get('inj_opp', 'N/A')}")

            st.markdown("**Raw Game Log (Last Team Games):**")
            st.code(data.get("log", "No logs"))

        st.write("### 🧠 Betting Advice")
        st.write(data.get("analysis", "No analysis"))

        st.divider()
        for msg in st.session_state.messages:
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])

        if val := st.chat_input("Ask follow-up..."):
            st.session_state.messages.append({"role": "user", "content": val})
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
