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

# [수정] 개별 기억 조회 (안정성 강화 유지)
def get_recent_memory(ticker):
    client = get_client()
    if not client: return None
    
    query = f"""
        SELECT report, log_date FROM `{client.project}.{DATASET_ID}.{TABLE_HISTORY}`
        WHERE ticker = '{ticker}' ORDER BY log_date DESC LIMIT 1
    """
    try:
        results = list(client.query(query).result())
        if results: 
            date_str = str(results[0].log_date)
            return {"date": date_str, "report": results[0].report}
    except Exception as e:
        print(f" [BQ Error] 개별 기억 조회 실패 ({ticker}): {e}")
        return None
    return None

# [수정] 대화용 기억 인출 기능 (쿼리 논리 수정 및 전체 조회)
def get_analyzed_ticker_list(days=None):
    """
    분석된 기록이 있는 모든 종목들의 티커 리스트 반환.
    GROUP BY를 사용하여 중복을 제거하고, 최근 활동 순으로 정렬합니다.
    """
    client = get_client()
    if not client: return []
    
    # 수정된 쿼리: DISTINCT 대신 GROUP BY 사용
    # MAX(log_date)를 기준으로 정렬하여 가장 최근에 본 종목이 먼저 오도록 함
    # LIMIT 제거: 모든 종목 조회
    query = f"""
        SELECT ticker
        FROM `{client.project}.{DATASET_ID}.{TABLE_HISTORY}`
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
    
    errors = client.insert_rows_json(table_ref, rows)
    if not errors:
        pass 
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