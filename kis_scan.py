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
    # (이전 코드와 동일 - holidays 라이브러리 사용)
    try:
        ny_tz = pytz.timezone('US/Eastern')
        ny_now = datetime.now(ny_tz)
        today_date = ny_now.date()
        if ny_now.weekday() >= 5: return False
        nyse_holidays = holidays.NYSE(years=today_date.year)
        if today_date in nyse_holidays: return False
        curr = ny_now.time()
        return time(9, 30) <= curr <= time(16, 0)
    except: return False

def _get_targets_from_bigquery():
    # 1. 유저 프로필 키워드 로드
    user_tags = mervis_profile.get_preference_tags()
    print(f"[Mervis] Loading Top-Tier stocks based on: {user_tags}")
    
    # 2. BigQuery에서 '검증된(ACTIVE)' 종목만 인출
    # get_tickers_from_db 함수가 내부적으로 status 체크를 하도록 mervis_bigquery 수정됨
    db_targets = mervis_bigquery.get_tickers_from_db(limit=40, tags=user_tags)
    
    if not db_targets:
        print("[Warning] No active targets found in DB. Running emergency backup.")
        return [{"code": "AAPL", "tag": "Fallback"}, {"code": "NVDA", "tag": "Fallback"}]
        
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

    # [Fast Scan] DB에서 즉시 로딩
    print("[Mervis] Fast-Loading Target Universe from BigQuery...")
    final_list = _get_targets_from_bigquery()
    
    print(f"[Mervis] Target Selection Complete. {len(final_list)} stocks ready for Real-time Monitoring.")
    return final_list