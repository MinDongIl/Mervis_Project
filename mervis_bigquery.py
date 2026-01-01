from google.cloud import bigquery
from google.oauth2 import service_account
import os
import json
from datetime import datetime
import mervis_state

# 설정
KEY_PATH = "service_account.json"
DATASET_ID = "mervis_db"
TABLE_HISTORY = "trade_history"
TABLE_USER = "user_info"
TABLE_TICKERS = "ticker_universe"  # [NEW] 종목 관리 테이블

def get_client():
    if not os.path.exists(KEY_PATH):
        print(f" [BQ Error] 키 파일을 찾을 수 없습니다: {KEY_PATH}")
        return None
    credentials = service_account.Credentials.from_service_account_file(KEY_PATH)
    return bigquery.Client(credentials=credentials, project=credentials.project_id)

# --- [NEW] 종목 DB(Ticker Universe) 관련 기능 ---

# 0. DB 최신화 상태 점검 (Smart Auto-Run 용)
def check_db_freshness():
    """
    DB가 오늘 날짜로 업데이트되어 있는지 확인
    Return: True(최신임), False(구식임/업데이트 필요)
    """
    client = get_client()
    if not client: return False
    
    # 아무 종목이나 하나 찍어서 업데이트 날짜 확인
    query = f"""
        SELECT updated_at FROM `{client.project}.{DATASET_ID}.{TABLE_TICKERS}`
        LIMIT 1
    """
    try:
        results = list(client.query(query).result())
        if not results: return False # 데이터 없으면 업데이트 필요
        
        # 저장된 날짜 (Timestamp를 문자열로 변환하여 YYYY-MM-DD 비교)
        last_update = str(results[0].updated_at)[:10] 
        today = datetime.now().strftime("%Y-%m-%d")
        
        return last_update == today
    except:
        return False

# 1. DB에서 조건에 맞는 우량 종목 랜덤 추출
def get_tickers_from_db(limit=40, tags=[]):
    client = get_client()
    if not client: return []
    
    # [핵심] 거래량이 검증된(ACTIVE_HIGH, ACTIVE_MID) 종목만 가져옴 (잡주 제외)
    # 태그(섹터)가 있으면 해당 태그 위주로 검색
    if tags:
        tag_str = ", ".join([f"'{t}'" for t in tags])
        query = f"""
            SELECT ticker, sector FROM `{client.project}.{DATASET_ID}.{TABLE_TICKERS}`
            WHERE sector IN ({tag_str}) AND status IN ('ACTIVE_HIGH', 'ACTIVE_MID', 'ACTIVE')
            ORDER BY RAND() LIMIT {limit}
        """
    else:
        # 태그 없으면 전체 우량주 중에서 랜덤
        query = f"""
            SELECT ticker, sector FROM `{client.project}.{DATASET_ID}.{TABLE_TICKERS}`
            WHERE status IN ('ACTIVE_HIGH', 'ACTIVE_MID', 'ACTIVE')
            ORDER BY RAND() LIMIT {limit}
        """
        
    try:
        results = list(client.query(query).result())
        # kis_scan에서 사용할 형식으로 변환
        return [{"code": row.ticker, "tag": row.sector} for row in results]
    except Exception as e:
        # print(f" [BQ Error] 티커 조회 실패 (DB가 비어있을 수 있음): {e}")
        return []

# 2. 종목 리스트 DB에 저장 (초기화 및 업데이트용)
def seed_ticker_db(ticker_list):
    client = get_client()
    if not client: return
    
    table_ref = f"{client.project}.{DATASET_ID}.{TABLE_TICKERS}"
    
    # 스키마 정의 (status, fail_count 포함)
    schema = [
        bigquery.SchemaField("ticker", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("name", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("sector", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("status", "STRING", mode="NULLABLE"), # ACTIVE_HIGH, MID, BAD
        bigquery.SchemaField("fail_count", "INTEGER", mode="NULLABLE"),
        bigquery.SchemaField("updated_at", "TIMESTAMP", mode="NULLABLE"),
    ]
    
    # 테이블 생성 (없으면 생성)
    try:
        client.create_table(bigquery.Table(table_ref, schema=schema), exists_ok=True)
    except: pass
    
    rows = []
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    for item in ticker_list:
        rows.append({
            "ticker": item['code'],
            "name": item.get('name', ''),
            "sector": item.get('tag', 'Unknown'),
            "status": "ACTIVE", # 초기 상태
            "fail_count": 0,
            "updated_at": timestamp
        })
        
    if rows:
        errors = client.insert_rows_json(table_ref, rows)
        if not errors:
            print(f"[System] {len(rows)} tickers saved to BigQuery.")
        else:
            print(f"[Error] Failed to save tickers: {errors}")

# --- [기존 기능 유지] 매매 기록 및 프로필 ---

def save_log(ticker, mode, price, report, news_summary=""):
    client = get_client()
    if not client: return
    
    table_ref = f"{client.project}.{DATASET_ID}.{TABLE_HISTORY}"
    rows = [{
        "log_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "ticker": ticker, 
        "mode": mode,
        "price": price,
        "report": report, 
        "news_summary": news_summary,
        "strategy_result": "WAITING"
    }]
    client.insert_rows_json(table_ref, rows)

def get_recent_memory(ticker):
    client = get_client()
    if not client: return None
    
    current_mode = mervis_state.get_mode()
    
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