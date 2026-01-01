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
TABLE_TICKERS = "ticker_universe"

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

# 1. DB에서 조건에 맞는 종목 추출 (Core & Satellite 전략 적용)
def get_tickers_from_db(limit=40, tags=[]):
    """
    1차: 태그 검색 시도
    2차: 실패 시 Core(우량주 30) + Satellite(급등주 10) 혼합 전략 사용
    """
    client = get_client()
    if not client: return []
    
    results = []
    
    # [1차 시도] 태그(User Preference) 기반 검색
    if tags:
        tag_str = ", ".join([f"'{t}'" for t in tags])
        query = f"""
            SELECT ticker, sector FROM `{client.project}.{DATASET_ID}.{TABLE_TICKERS}`
            WHERE sector IN ({tag_str}) AND status IN ('ACTIVE_HIGH', 'ACTIVE_MID')
            ORDER BY RAND() LIMIT {limit}
        """
        try:
            results = list(client.query(query).result())
        except Exception as e:
            print(f" [DB Warning] 태그 검색 에러: {e}")
            
    # [2차 시도] 태그 검색 결과가 없거나 태그 미지정 시 -> Core & Satellite 전략
    if not results:
        if tags: 
            print(" [DB] 태그 매칭 종목 없음. 'Core(30) + Satellite(10)' 전략으로 선별합니다.")
            
        final_mix = []
        
        # 1. Core (30개): 거래량 터진 우량주 (ACTIVE_HIGH) 중 랜덤
        try:
            query_core = f"""
                SELECT ticker, sector FROM `{client.project}.{DATASET_ID}.{TABLE_TICKERS}`
                WHERE status = 'ACTIVE_HIGH'
                ORDER BY RAND() LIMIT 30
            """
            core_results = list(client.query(query_core).result())
            final_mix.extend(core_results)
        except: pass
        
        # 2. Satellite (10개): 전일 등락률(change_rate) 상위 Top 10 (급등주)
        # ACTIVE_MID 이상인 종목 중에서 선정하여 잡주 제외
        try:
            query_sat = f"""
                SELECT ticker, sector FROM `{client.project}.{DATASET_ID}.{TABLE_TICKERS}`
                WHERE status IN ('ACTIVE_HIGH', 'ACTIVE_MID')
                ORDER BY change_rate DESC LIMIT 10
            """
            sat_results = list(client.query(query_sat).result())
            final_mix.extend(sat_results)
        except: pass
        
        results = final_mix
        
    # 결과 변환
    if not results:
        return []

    return [{"code": row.ticker, "tag": row.sector} for row in results]

# 2. 종목 리스트 DB에 저장 (초기화 및 업데이트용)
def seed_ticker_db(ticker_list):
    client = get_client()
    if not client: return
    
    table_ref = f"{client.project}.{DATASET_ID}.{TABLE_TICKERS}"
    
    # 스키마 정의 (status, fail_count, change_rate, last_volume 포함)
    schema = [
        bigquery.SchemaField("ticker", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("name", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("sector", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("status", "STRING", mode="NULLABLE"), # ACTIVE_HIGH, MID, BAD
        bigquery.SchemaField("change_rate", "FLOAT", mode="NULLABLE"), # [NEW] 등락률
        bigquery.SchemaField("last_volume", "INTEGER", mode="NULLABLE"), # [NEW] 최근 거래량
        bigquery.SchemaField("fail_count", "INTEGER", mode="NULLABLE"),
        bigquery.SchemaField("updated_at", "STRING", mode="NULLABLE"), # TIMESTAMP -> STRING (호환성)
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
            "change_rate": 0.0,
            "last_volume": 0,
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
    try:
        client.insert_rows_json(table_ref, rows)
    except: pass

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
    try:
        client.insert_rows_json(table_ref, rows)
    except: pass

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