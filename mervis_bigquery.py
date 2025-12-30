from google.cloud import bigquery
from google.oauth2 import service_account
import os
import json
from datetime import datetime

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
        "ticker": ticker, "mode": mode, "price": price,
        "report": report, "news_summary": news_summary,
        "strategy_result": "WAITING"
    }]
    client.insert_rows_json(table_ref, rows)

def get_recent_memory(ticker):
    client = get_client()
    if not client: return None
    
    query = f"""
        SELECT report, log_date FROM `{client.project}.{DATASET_ID}.{TABLE_HISTORY}`
        WHERE ticker = '{ticker}' ORDER BY log_date DESC LIMIT 1
    """
    try:
        results = list(client.query(query).result())
        if results: return {"date": results[0].log_date.strftime("%Y-%m-%d %H:%M"), "report": results[0].report}
    except: return None

# --- [NEW] 대화용 기억 인출 기능 ---
def get_analyzed_ticker_list(days=7):
    """최근 N일 이내에 분석된 기록이 있는 종목들의 티커 리스트 반환"""
    client = get_client()
    if not client: return []
    
    query = f"""
        SELECT DISTINCT ticker 
        FROM `{client.project}.{DATASET_ID}.{TABLE_HISTORY}`
        WHERE PARSE_TIMESTAMP('%Y-%m-%d %H:%M:%S', log_date) >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL {days} DAY)
    """
    try:
        results = list(client.query(query).result())
        return [row.ticker for row in results]
    except:
        return []

# --- [기존] 사용자 프로필 관련 ---
def save_profile(profile_data):
    client = get_client()
    if not client: return

    table_ref = f"{client.project}.{DATASET_ID}.{TABLE_USER}"
    
    profile_str = json.dumps(profile_data, ensure_ascii=False)
    updated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    rows = [{"updated_at": updated_at, "profile_json": profile_str}]
    
    errors = client.insert_rows_json(table_ref, rows)
    if not errors:
        print(" [BQ] 사용자 프로필이 업데이트되었습니다.")
    else:
        print(f" [BQ Error] 프로필 저장 실패: {errors}")

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