import requests
import secret
import kis_auth
import mervis_state
import mervis_profile
import mervis_bigquery
from datetime import datetime, time
import pytz
import holidays

def is_market_open_check():
    try:
        ny_tz = pytz.timezone('US/Eastern')
        ny_now = datetime.now(ny_tz)
        today_date = ny_now.date()
        
        # 1. Weekend Check
        if ny_now.weekday() >= 5: 
            return False

        # 2. Holiday Check (using holidays library)
        nyse_holidays = holidays.NYSE(years=today_date.year)
        if today_date in nyse_holidays:
            return False

        # 3. Market Hours Check (09:30 ~ 16:00)
        curr = ny_now.time()
        return time(9, 30) <= curr <= time(16, 0)
    except Exception as e:
        print(f"[Check Error] {e}")
        return False

def _get_targets_from_bigquery():
    # Load user preference tags
    user_tags = mervis_profile.get_preference_tags()
    print(f"[Mervis] Fetching targets from DB based on: {user_tags}")
    
    # Fetch tickers from BigQuery
    db_targets = mervis_bigquery.get_tickers_from_db(limit=40, tags=user_tags)
    
    # Fallback if DB is empty
    if not db_targets:
        print("[Warning] DB is empty. Please run DB initialization script.")
        return [{"code": "AAPL", "tag": "Fallback"}, {"code": "TSLA", "tag": "Fallback"}]
        
    formatted_list = []
    for item in db_targets:
        formatted_list.append({
            "code": item['code'],
            "name": "Target",
            "price": 0, 
            "tag": item['tag']
        })
        
    return formatted_list

def get_dynamic_targets():
    is_open = is_market_open_check()
    status = "OPEN" if is_open else "CLOSED"
    mode = mervis_state.get_mode()
    
    ny_tz = pytz.timezone('US/Eastern')
    ny_now = datetime.now(ny_tz).strftime("%Y-%m-%d %H:%M")
    print(f"[Mervis] NY Time: {ny_now} | Market: {status} | Mode: {mode}")

    # Main Logic: Fetch from BigQuery Database
    print("[Mervis] Querying BigQuery for Analysis Targets...")
    final_list = _get_targets_from_bigquery()
    
    print(f"[Mervis] Target Selection Complete. Total {len(final_list)} stocks ready for analysis.")
    return final_list