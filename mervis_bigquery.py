from google.cloud import bigquery
from google.oauth2 import service_account
import os
import json
from datetime import datetime
from deep_translator import GoogleTranslator
import mervis_state

# 설정
KEY_PATH = "service_account.json"
DATASET_ID = "mervis_db"
TABLE_HISTORY = "trade_history"
TABLE_USER = "user_info"
TABLE_TICKERS = "ticker_universe"
TABLE_BALANCE = "daily_balance"

def get_client():
    if not os.path.exists(KEY_PATH):
        print(f" [BQ Error] 키 파일을 찾을 수 없습니다: {KEY_PATH}")
        return None
    credentials = service_account.Credentials.from_service_account_file(KEY_PATH)
    return bigquery.Client(credentials=credentials, project=credentials.project_id)

def check_db_freshness():
    client = get_client()
    if not client: return False
    query = f"SELECT updated_at FROM `{client.project}.{DATASET_ID}.{TABLE_TICKERS}` LIMIT 1"
    try:
        results = list(client.query(query).result())
        if not results: return False
        last_update = str(results[0].updated_at)[:10] 
        today = datetime.now().strftime("%Y-%m-%d")
        return last_update == today
    except: return False

def get_tickers_from_db(limit=40, tags=[]):
    """
    [Auto-Translation Search]
    사용자가 입력한 태그(영어)를 번역기로 한국어로 변환하여,
    DB 내의 영문/한글 키워드를 모두 검색합니다.
    """
    client = get_client()
    if not client: return []
    
    results = []
    
    # [1차 시도] 번역기 기반 확장 검색
    if tags:
        like_conditions = []
        translator = GoogleTranslator(source='auto', target='ko')
        
        for t in tags:
            origin_tag = t.strip()
            if not origin_tag: continue
            
            search_words = [origin_tag.upper()]
            
            # 번역 시도
            try:
                translated = translator.translate(origin_tag)
                if translated and translated.upper() != origin_tag.upper():
                    search_words.append(translated)
            except Exception as e:
                pass
            
            # OR 조건 생성
            sub_conds = [f"keywords LIKE '%{w}%'" for w in search_words]
            like_conditions.append(f"({' OR '.join(sub_conds)})")
        
        if like_conditions:
            final_where = " OR ".join(like_conditions)
            query = f"""
                SELECT ticker, sector FROM `{client.project}.{DATASET_ID}.{TABLE_TICKERS}`
                WHERE ({final_where}) 
                AND status IN ('ACTIVE_HIGH', 'ACTIVE_MID')
                ORDER BY RAND() LIMIT {limit}
            """
            try:
                results = list(client.query(query).result())
            except Exception as e:
                print(f" [DB Warning] 검색 에러: {e}")
            
    # [2차 시도] Fallback
    if not results:
        if tags: print(" [DB] 검색 결과 없음. Core(30)+Satellite(10) 전략으로 대체.")
        final_mix = []
        try:
            query_core = f"""
                SELECT ticker, sector FROM `{client.project}.{DATASET_ID}.{TABLE_TICKERS}`
                WHERE status = 'ACTIVE_HIGH' ORDER BY RAND() LIMIT 30
            """
            final_mix.extend(list(client.query(query_core).result()))
        except: pass
        try:
            query_sat = f"""
                SELECT ticker, sector FROM `{client.project}.{DATASET_ID}.{TABLE_TICKERS}`
                WHERE status IN ('ACTIVE_HIGH', 'ACTIVE_MID') ORDER BY change_rate DESC LIMIT 10
            """
            final_mix.extend(list(client.query(query_sat).result()))
        except: pass
        results = final_mix

    if not results: return []
    return [{"code": row.ticker, "tag": row.sector} for row in results]

# --- 매매 기록 및 프로필 (INSERT ONLY) ---

def save_log(ticker, mode, price, report, news_summary=""):
    client = get_client()
    if not client: return
    table_ref = f"{client.project}.{DATASET_ID}.{TABLE_HISTORY}"
    rows = [{
        "log_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "ticker": ticker, "mode": mode, "price": price,
        "report": report, "news_summary": news_summary, "strategy_result": "WAITING"
    }]
    try: client.insert_rows_json(table_ref, rows)
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
        if results: return {"date": str(results[0].log_date), "report": results[0].report}
    except: return None
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
    except: return []

def get_analyzed_ticker_list():
    client = get_client()
    if not client: return []
    current_mode = mervis_state.get_mode()
    query = f"""
        SELECT ticker FROM `{client.project}.{DATASET_ID}.{TABLE_HISTORY}`
        WHERE mode = '{current_mode}'
        GROUP BY ticker ORDER BY MAX(log_date) DESC
    """
    try:
        results = list(client.query(query).result())
        return [row.ticker for row in results]
    except: return []

def save_profile(profile_data):
    client = get_client()
    if not client: return
    table_ref = f"{client.project}.{DATASET_ID}.{TABLE_USER}"
    rows = [{"updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "profile_json": json.dumps(profile_data, ensure_ascii=False)}]
    try: client.insert_rows_json(table_ref, rows)
    except: pass

def get_profile():
    client = get_client()
    if not client: return None
    query = f"SELECT profile_json FROM `{client.project}.{DATASET_ID}.{TABLE_USER}` ORDER BY updated_at DESC LIMIT 1"
    try:
        results = list(client.query(query).result())
        if results: return json.loads(results[0].profile_json)
    except: return None
    return None

# --- 자산 관리 (Daily Balance) ---

def save_daily_balance(total_asset, cash, stock_val, pnl_daily):
    """
    매일의 자산 상태를 기록 (자동으로 테이블 생성)
    """
    client = get_client()
    if not client: return

    table_ref = f"{client.project}.{DATASET_ID}.{TABLE_BALANCE}"
    
    # 스키마 정의 (Date, Total, Cash, Stock, PnL)
    schema = [
        bigquery.SchemaField("date", "DATE", mode="REQUIRED"),
        bigquery.SchemaField("total_asset", "FLOAT", mode="NULLABLE"),
        bigquery.SchemaField("cash", "FLOAT", mode="NULLABLE"),
        bigquery.SchemaField("stock_val", "FLOAT", mode="NULLABLE"),
        bigquery.SchemaField("pnl_daily", "FLOAT", mode="NULLABLE"),
    ]
    
    # 테이블이 없으면 생성
    try:
        client.create_table(bigquery.Table(table_ref, schema=schema), exists_ok=True)
    except: pass

    # 오늘 날짜
    today = datetime.now().strftime("%Y-%m-%d")
    
    rows = [{
        "date": today,
        "total_asset": float(total_asset),
        "cash": float(cash),
        "stock_val": float(stock_val),
        "pnl_daily": float(pnl_daily)
    }]
    
    try:
        errors = client.insert_rows_json(table_ref, rows)
        if not errors:
            print(f" [BQ] 자산 기록 완료: Total ${total_asset} (PnL: {pnl_daily}%)")
        else:
            print(f" [BQ Error] 자산 기록 실패: {errors}")
    except Exception as e:
        print(f" [BQ Error] {e}")

def get_asset_trend(limit=30):
    """
    최근 자산 변동 추이를 가져옴 (차트 그리기용)
    """
    client = get_client()
    if not client: return []
    
    query = f"""
        SELECT date, total_asset, pnl_daily 
        FROM `{client.project}.{DATASET_ID}.{TABLE_BALANCE}`
        ORDER BY date ASC LIMIT {limit}
    """
    try:
        results = list(client.query(query).result())
        return [{"date": str(row.date), "total": row.total_asset, "pnl": row.pnl_daily} for row in results]
    except: return []