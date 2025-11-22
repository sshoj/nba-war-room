import streamlit as st
import requests
from langchain_openai import ChatOpenAI
import os
import pandas as pd
from datetime import datetime, timedelta, timezone  # <--- Added timezone import
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
    Smart player search that prioritizes:
    1. Name match (fuzzy logic)
    2. Team match (if user includes 'Hornets', 'CHA', etc.)
    """
    try:
        # 1. Gather candidates by searching for every word in the input
        # (We keep this broad to ensure we catch the player even if the team is typed)
        words = user_input.split()
        candidates = {}
        search_terms = set()
        
        for w in words:
            if len(w) >= 3:
                search_terms.add(w)

        # If input is short (e.g. "Embiid"), ensure we search it
        if not search_terms and words:
            search_terms.add(words[0])

        for term in search_terms:
            try:
                r = requests.get(
                    url=f"{BDL_URL}/players",
                    headers=get_bdl_headers(),
                    params={"search": term, "per_page": 25}, # Increased page size
                    timeout=REQUEST_TIMEOUT,
                )
            except Exception as e:
                return None, f"Network error searching for player: {e}"

            if r.status_code != 200:
                return None, f"API Error {r.status_code}"

            data = r.json().get("data", [])
            for p in data:
                candidates[p["id"]] = p

        if not candidates:
            return None, f"Player '{user_input}' not found."

        # 2. Score the candidates based on Name Similarity AND Team Match
        scored_candidates = []
        user_input_norm = user_input.lower()
        
        for pid, p in candidates.items():
            fname = p.get('first_name', '')
            lname = p.get('last_name', '')
            full_name = f"{fname} {lname}"
            
            # Team info
            team = p.get('team', {})
            t_name = team.get('name', '').lower()       # e.g. hornets
            t_city = team.get('city', '').lower()       # e.g. charlotte
            t_abbr = team.get('abbreviation', '').lower() # e.g. cha
            
            # A. Calculate Name Score (0.0 to 1.0)
            # We strip the team name out of user input for the name comparison to be fair
            # (e.g. compare "Mark Williams" to "Mark Williams", ignoring "Hornets")
            input_name_only = user_input_norm.replace(t_name, "").replace(t_city, "").replace(t_abbr, "").strip()
            name_score = difflib.SequenceMatcher(None, input_name_only, full_name.lower()).ratio()
            
            # B. Calculate Team Bonus
            # If the user typed "Hornets", "CHA", or "Charlotte", give a massive bonus
            team_bonus = 0.0
            if (t_name in user_input_norm) or (t_city in user_input_norm) or (t_abbr in user_input_norm):
                team_bonus = 0.3  # huge boost to separate Mark from Marvin

            # Total Score
            final_score = name_score + team_bonus
            scored_candidates.append((final_score, p))

        # 3. Sort by highest score
        scored_candidates.sort(key=lambda x: x[0], reverse=True)

        if not scored_candidates:
             return None, "No close matches found."

        best_match = scored_candidates[0][1]
        best_name = f"{best_match['first_name']} {best_match['last_name']}"
        best_team = best_match['team']['full_name']
        
        return best_match, f"Found: **{best_name}** ({best_team})"

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

def get_betting_game_and_odds(player_name, team_name, bookmakers=None):
    """
    Canonical source of the upcoming game for this player/team.

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
            return {
                "odds_text": f"Error fetching games from Betting API (status {games_resp.status_code}): {msg}",
                "tipoff_iso": None,
                "home_team": None,
                "away_team": None,
            }

        games = games_resp.json()
        if not isinstance(games, list) or not games:
            return {
                "odds_text": "No betting lines available.",
                "tipoff_iso": None,
                "home_team": None,
                "away_team": None,
            }

        team_norm = normalize_team_name(team_name)
        # Pick nearest future event where team_name matches home or away
        best_game = None
        best_time = None

        # FIX: Make 'now' timezone-aware (UTC) to match API response
        now = datetime.now(timezone.utc)

        for g in games:
            ht = g.get("home_team") or ""
            at = g.get("away_team") or ""
            if team_norm not in normalize_team_name(ht) and team_norm not in normalize_team_name(at):
                continue

            ct = g.get("commence_time")
            if not ct:
                continue
            try:
                # ISO Format usually has Z or offset, making it aware.
                g_dt = datetime.fromisoformat(ct.replace("Z", "+00:00"))
            except Exception:
                continue

            if g_dt < now:
                # game already started / past – still could be relevant for props,
                # but for "upcoming game" UX we favor future or nearest-time.
                continue

            if best_time is None or g_dt < best_time:
                best_time = g_dt
                best_game = g

        # If nothing in future, fallback to ANY match (closest in time)
        if not best_game:
            for g in games:
                ht = g.get("home_team") or ""
                at = g.get("away_team") or ""
                if team_norm not in normalize_team_name(ht) and team_norm not in normalize_team_name(at):
                    continue
                ct = g.get("commence_time")
                if not ct:
                    continue
                try:
                    g_dt = datetime.fromisoformat(ct.replace("Z", "+00:00"))
                except Exception:
                    continue
                if best_time is None or g_dt < best_time:
                    best_time = g_dt
                    best_game = g

        if not best_game:
            return {
                "odds_text": f"No active betting lines found for {team_name}.",
                "tipoff_iso": None,
                "home_team": None,
                "away_team": None,
            }

        game_id = best_game.get("id")
        tipoff_iso = best_game.get("commence_time")
        home_team = best_game.get("home_team")
        away_team = best_game.get("away_team")

        # 2. Odds for that exact event
        params = {
            "apiKey": api_key,
            "regions": "us",
            "markets": "player_points,player_rebounds,player_assists,h2h",
        }
        if bookmakers:
            params["bookmakers"] = bookmakers

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
            return {
                "odds_text": f"Error fetching odds (status {odds_resp.status_code}): {msg}",
                "tipoff_iso": tipoff_iso,
                "home_team": home_team,
                "away_team": away_team,
            }

        data = odds_resp.json()
        bookmakers_list = data.get("bookmakers", [])
        if not bookmakers_list:
            return {
                "odds_text": "No odds available.",
                "tipoff_iso": tipoff_iso,
                "home_team": home_team,
                "away_team": away_team,
            }

        # Player props from preferred book
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

        # Moneyline from all books
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

        # 2. Betting Game (canonical next game) + Odds
        status_box.write("Finding betting event & lines...")
        betting = get_betting_game_and_odds(f"{fname} {lname}", tname)
        betting_lines = betting["odds_text"]
        tipoff_iso = betting["tipoff_iso"]
        odds_home = betting["home_team"]
        odds_away = betting["away_team"]

        # Derive matchup + date from Odds event
        matchup = "Unknown matchup"
        game_date_display = "Unknown date"
        opp_name = "Unknown opponent"

        if odds_home and odds_away:
            norm_team = normalize_team_name(tname)
            home_norm = normalize_team_name(odds_home)
            away_norm = normalize_team_name(odds_away)

            if norm_team in home_norm:
                opp_name = odds_away
                loc = "vs"
            elif norm_team in away_norm:
                opp_name = odds_home
                loc = "@"
            else:
                # fallback: assume home team is player's team
                opp_name = odds_away
                loc = "vs"

            matchup = f"{loc} {opp_name}"

        if tipoff_iso:
            try:
                tip_dt = datetime.fromisoformat(tipoff_iso.replace("Z", "+00:00"))
                game_date_display = tip_dt.date().isoformat()
            except Exception:
                pass

        # 3. Get opponent team info from BDL (for injuries, stats, rotation)
        opp_team_bdl = get_bdl_team_by_name(opp_name)
        opp_id = opp_team_bdl.get("id")
        opp_abbr = opp_team_bdl.get("abbreviation", "")
        opp_name_bdl = opp_team_bdl.get("full_name", opp_name)

        # 4. Injuries
        status_box.write("Fetching injuries...")
        inj_home = get_team_injuries(tid) if tid else "N/A"
        inj_opp = get_team_injuries(opp_id) if opp_id else "N/A"

        # 5. Home Team Stats (Last 7 Games + Strict DNP)
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
                opp_abbr_log = visitor.get("abbreviation", "UNK")
                loc = "vs"
            else:
                opp_abbr_log = home.get("abbreviation", "UNK")
                loc = "@"

            stat = next((s for s in p_stats if s["game"]["id"] == gid), None)

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

        # 6. Opponent team's last 7 results (from BDL)
        opp_results_rows = []
        if opp_id:
            opp_past_games = get_team_schedule_before_today(opp_id, n_games=7)
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
        run_btn = st.button("🚀 Run Analysis", type="primary", use_container_width=True)

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
                    # FIX: Make 'now' aware (UTC) to avoid comparison errors
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
            st.dataframe(df_rot, use_container_width=True)

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
            st.dataframe(df_opp_rot, use_container_width=True)

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
            st.dataframe(df_stats, use_container_width=True)

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
            st.dataframe(df_opp, use_container_width=True)

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
