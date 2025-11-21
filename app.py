import pandas as pd
from nba_api.stats.endpoints import teaminfocommon

# 1. Setup Headers (CRITICAL: Prevents "Connection Timed Out" or 403 Errors)
custom_headers = {
    'Host': 'stats.nba.com',
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:126.0) Gecko/20100101 Firefox/126.0',
    'Accept': 'application/json, text/plain, */*',
    'Referer': 'https://stats.nba.com/',
    'Connection': 'keep-alive',
}

# 2. Define the Team ID (1610612742 is correct for Dallas Mavericks)
mavs_id = 1610612742

try:
    print(f"🏀 Fetching info for Team ID: {mavs_id}...")
    
    # 3. Call the Endpoint with Headers
    # Note: We pass 'headers=custom_headers' to bypass the block
    mavs_info = teaminfocommon.TeamInfoCommon(
        team_id=mavs_id, 
        headers=custom_headers,
        timeout=10
    )
    
    # 4. Get the DataFrame
    # The standard method is .get_data_frames(), which returns a list. 
    # Index [0] is the main team info.
    df = mavs_info.get_data_frames()[0]
    
    # 5. Display Result
    print("✅ Success! Data Retrieved:")
    print(df[['TEAM_NAME', 'TEAM_CITY', 'W', 'L', 'PCT']].to_string(index=False))

except Exception as e:
    print(f"❌ Error: {e}")
