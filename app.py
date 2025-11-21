import pandas as pd
import time
from nba_api.stats.endpoints import teaminfocommon

# 1. Setup Headers (CRITICAL)
# Without these, NBA.com will see you as a bot and block the connection.
custom_headers = {
    'Host': 'stats.nba.com',
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:126.0) Gecko/20100101 Firefox/126.0',
    'Accept': 'application/json, text/plain, */*',
    'Referer': 'https://stats.nba.com/',
    'Connection': 'keep-alive',
}

# 2. Define Team ID (1610612742 = Dallas Mavericks)
mavs_id = 1610612742

print(f"📡 Pinging NBA API for Team ID: {mavs_id}...")
start_time = time.time()

try:
    # 3. Call the Endpoint with Headers
    # We pass 'headers=custom_headers' to bypass the block
    # We set a timeout so it doesn't freeze forever if blocked
    dallas = teaminfocommon.TeamInfoCommon(
        team_id=mavs_id, 
        headers=custom_headers,
        timeout=10
    )
    
    # 4. Get the DataFrame
    # Your syntax was correct! .team_info_common.get_data_frame() works.
    df = dallas.team_info_common.get_data_frame()
    
    end_time = time.time()
    ping_ms = (end_time - start_time) * 1000

    # 5. Show Results
    print(f"✅ Success! Ping: {ping_ms:.2f}ms")
    print("--- Connection Result ---")
    print(df[['TEAM_NAME', 'TEAM_CITY', 'W', 'L', 'PCT']].to_string(index=False))

except Exception as e:
    print(f"❌ Connection Failed: {e}")
