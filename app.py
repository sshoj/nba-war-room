def get_advanced_stats(player_id):
    """Fetches detailed stats with strict type handling"""
    try:
        url = f"{BASE_URL}/stats"
        # FIX: Explicitly cast integers to strings/lists to satisfy strict APIs
        params = {
            "seasons[]": ["2024", "2025"], # Check both seasons to be safe
            "player_ids[]": [str(player_id)], 
            "per_page": "10"
        }
        
        # 1. Make Request
        resp = requests.get(url, headers=get_headers(), params=params)
        
        # 2. Debugging Block (If it fails again, we will see WHY)
        if resp.status_code != 200:
            return f"API Error {resp.status_code}: {resp.text}"
            
        data = resp.json()['data']
        
        if not data: return "No games found for 2024-25 season."
        
        games_log = []
        for g in data:
            date = g['game']['date'].split("T")[0]
            
            # Determine opponent (Handle Home/Away)
            if g['game']['home_team']['id'] == g['team']['id']:
                opp = g['game']['visitor_team']['abbreviation']
                loc = "vs"
            else:
                opp = g['game']['home_team']['abbreviation']
                loc = "@"
            
            # Safe Percentage Handling
            fg_pct = f"{g['fg_pct'] * 100:.1f}%" if g['fg_pct'] else "0.0%"
            
            # The Deep Stat Line
            stat_line = (f"PTS:{g['pts']} REB:{g['reb']} AST:{g['ast']} "
                         f"STL:{g['stl']} BLK:{g['blk']} TO:{g['turnover']} "
                         f"FG:{fg_pct}")
            
            games_log.append(f"[{date} {loc} {opp}] {stat_line}")
            
        # Sort by date (Newest first)
        games_log.sort(reverse=True)
        return "\n".join(games_log[:5])
        
    except Exception as e:
        return f"System Error: {e}"
