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

# [수정] 최근 기억 단일 조회 (에러 로그 추가)
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
            # log_date가 Timestamp 객체일 수도, String일 수도 있으므로 str()로 안전하게 변환
            date_str = str(results[0].log_date)
            return {"date": date_str, "report": results[0].report}
    except Exception as e:
        print(f" [BQ Error] 개별 기억 조회 실패 ({ticker}): {e}")
        return None
    return None

# [수정] 대화용 기억 인출 기능 (쿼리 단순화 및 안정화)
def get_analyzed_ticker_list(days=7):
    """
    최근 분석된 기록이 있는 종목들의 티커 리스트 반환.
    날짜 파싱 오류를 방지하기 위해 정렬(ORDER BY) 기반으로 최근 20개를 가져옵니다.
    """
    client = get_client()
    if not client: return []
    
    # 수정된 쿼리: 날짜 계산 대신 최근 로그 순으로 정렬하여 상위 20개 추출
    query = f"""
        SELECT DISTINCT ticker 
        FROM `{client.project}.{DATASET_ID}.{TABLE_HISTORY}`
        ORDER BY log_date DESC
        LIMIT 20
    """
    try:
        results = list(client.query(query).result())
        return [row.ticker for row in results]
    except Exception as e:
        # 오류 발생 시 콘솔에 원인 출력 (디버깅용)
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
        # 프로필 저장 성공 로그 (필요시 주석 처리 가능)
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