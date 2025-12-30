from google.cloud import bigquery
from google.oauth2 import service_account
import os
import json
from datetime import datetime

# 설정
KEY_PATH = "service_account.json"
DATASET_ID = "mervis_db"
TABLE_HISTORY = "trade_history"
TABLE_USER = "user_info" # [NEW] 사용자 정보 테이블

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

# --- [NEW] 사용자 프로필 관련 ---
def save_profile(profile_data):
    """사용자 프로필(JSON)을 BigQuery에 저장"""
    client = get_client()
    if not client: return

    table_ref = f"{client.project}.{DATASET_ID}.{TABLE_USER}"
    
    # JSON 객체를 문자열로 변환하여 저장
    profile_str = json.dumps(profile_data, ensure_ascii=False)
    updated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    rows = [{"updated_at": updated_at, "profile_json": profile_str}]
    
    errors = client.insert_rows_json(table_ref, rows)
    if not errors:
        print(" [BQ] 사용자 프로필이 업데이트되었습니다.")
    else:
        print(f" [BQ Error] 프로필 저장 실패: {errors}")

def get_profile():
    """BigQuery에서 가장 최신 사용자 프로필을 로드"""
    client = get_client()
    if not client: return None
    
    query = f"""
        SELECT profile_json FROM `{client.project}.{DATASET_ID}.{TABLE_USER}`
        ORDER BY updated_at DESC LIMIT 1
    """
    try:
        results = list(client.query(query).result())
        if results:
            # 저장된 JSON 문자열을 다시 객체로 변환
            return json.loads(results[0].profile_json)
    except Exception as e:
        print(f" [BQ Error] 프로필 로드 실패: {e}")
        return None
    return None