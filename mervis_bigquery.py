from google.cloud import bigquery
from google.oauth2 import service_account
import os
import json
from datetime import datetime
import mervis_state  # 모드 확인을 위해 추가

# 설정
KEY_PATH = "service_account.json"
DATASET_ID = "mervis_db"
TABLE_HISTORY = "trade_history"
TABLE_USER = "user_info" 

def get_client():
    if not os.path.exists(KEY_PATH):
        print(f" [BQ Error] 키 파일을 찾을 수 없습니다: {KEY_PATH}")
        return None
    credentials = service_account.Credentials.from_service_account_file(KEY_PATH)
    return bigquery.Client(credentials=credentials, project=credentials.project_id)

# --- [기존] 매매 기록 관련 ---
def save_log(ticker, mode, price, report, news_summary=""):
    client = get_client()
    if not client: return
    
    table_ref = f"{client.project}.{DATASET_ID}.{TABLE_HISTORY}"
    rows = [{
        "log_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "ticker": ticker, 
        "mode": mode,  # REAL 또는 MOCK 저장
        "price": price,
        "report": report, 
        "news_summary": news_summary,
        "strategy_result": "WAITING"
    }]
    client.insert_rows_json(table_ref, rows)

# [V12.1 수정] 현재 모드에 맞는 최근 기억 1개 조회
def get_recent_memory(ticker):
    client = get_client()
    if not client: return None
    
    current_mode = mervis_state.get_mode() # 현재 모드 (REAL/MOCK)
    
    query = f"""
        SELECT report, log_date FROM `{client.project}.{DATASET_ID}.{TABLE_HISTORY}`
        WHERE ticker = '{ticker}' AND mode = '{current_mode}' 
        ORDER BY log_date DESC LIMIT 1
    """
    try:
        results = list(client.query(query).result())
        if results: 
            date_str = str(results[0].log_date)
            return {"date": date_str, "report": results[0].report}
    except Exception as e:
        print(f" [BQ Error] 기억 조회 실패 ({ticker}/{current_mode}): {e}")
        return None
    return None

# [V12.1 추가] 현재 모드에 맞는 다중 기억 조회 (최근 3개)
def get_multi_memories(ticker, limit=3):
    client = get_client()
    if not client: return []
    
    current_mode = mervis_state.get_mode()
    
    query = f"""
        SELECT report, log_date, price FROM `{client.project}.{DATASET_ID}.{TABLE_HISTORY}`
        WHERE ticker = '{ticker}' AND mode = '{current_mode}' 
        ORDER BY log_date DESC LIMIT {limit}
    """
    try:
        results = list(client.query(query).result())
        return [{"date": str(row.log_date), "report": row.report, "price": row.price} for row in results]
    except Exception as e:
        print(f" [BQ Error] 다중 기억 조회 실패 ({ticker}/{current_mode}): {e}")
        return []

# [수정] 현재 모드에서 분석된 종목 리스트만 반환
def get_analyzed_ticker_list():
    client = get_client()
    if not client: return []
    
    current_mode = mervis_state.get_mode()
    
    query = f"""
        SELECT ticker
        FROM `{client.project}.{DATASET_ID}.{TABLE_HISTORY}`
        WHERE mode = '{current_mode}'
        GROUP BY ticker
        ORDER BY MAX(log_date) DESC
    """
    try:
        results = list(client.query(query).result())
        return [row.ticker for row in results]
    except Exception as e:
        print(f" [BQ Error] 종목 리스트 조회 실패: {e}")
        return []

# --- [기존] 사용자 프로필 관련 ---
def save_profile(profile_data):
    client = get_client()
    if not client: return
    table_ref = f"{client.project}.{DATASET_ID}.{TABLE_USER}"
    profile_str = json.dumps(profile_data, ensure_ascii=False)
    updated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    rows = [{"updated_at": updated_at, "profile_json": profile_str}]
    client.insert_rows_json(table_ref, rows)

def get_profile():
    client = get_client()
    if not client: return None
    query = f"""
        SELECT profile_json FROM `{client.project}.{DATASET_ID}.{TABLE_USER}`
        ORDER BY updated_at DESC LIMIT 1
    """
    try:
        results = list(client.query(query).result())
        if results:
            return json.loads(results[0].profile_json)
    except Exception as e:
        print(f" [BQ Error] 프로필 로드 실패: {e}")
        return None
    return None