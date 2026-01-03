from google.cloud import bigquery
from google.oauth2 import service_account
import os
import json
from datetime import datetime
from deep_translator import GoogleTranslator
import mervis_state

# [설정] BigQuery 상수
KEY_PATH = "service_account.json"
DATASET_ID = "mervis_db"
TABLE_HISTORY = "trade_history"
TABLE_USER = "user_info"
TABLE_TICKERS = "ticker_universe"
TABLE_BALANCE = "daily_balance"
TABLE_ANALYSIS = "stock_analysis" # [NEW] 기술적 분석 결과 저장용

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
    [Auto-Translation Search] 영문 태그 -> 한글 자동 번역 검색
    """
    client = get_client()
    if not client: return []
    
    results = []
    
    # [1차 시도] 태그 검색
    if tags:
        like_conditions = []
        translator = GoogleTranslator(source='auto', target='ko')
        
        for t in tags:
            origin_tag = t.strip()
            if not origin_tag: continue
            
            search_words = [origin_tag.upper()]
            try:
                translated = translator.translate(origin_tag)
                if translated and translated.upper() != origin_tag.upper():
                    search_words.append(translated)
            except: pass
            
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
            
    # [2차 시도] Fallback (검색 결과 없으면 랜덤 추천)
    if not results:
        final_mix = []
        try:
            # Core 종목
            query_core = f"""
                SELECT ticker, sector FROM `{client.project}.{DATASET_ID}.{TABLE_TICKERS}`
                WHERE status = 'ACTIVE_HIGH' ORDER BY RAND() LIMIT 30
            """
            final_mix.extend(list(client.query(query_core).result()))
        except: pass
        try:
            # 급등 종목 (Satellite)
            query_sat = f"""
                SELECT ticker, sector FROM `{client.project}.{DATASET_ID}.{TABLE_TICKERS}`
                WHERE status IN ('ACTIVE_HIGH', 'ACTIVE_MID') ORDER BY change_rate DESC LIMIT 10
            """
            final_mix.extend(list(client.query(query_sat).result()))
        except: pass
        results = final_mix

    if not results: return []
    return [{"code": row.ticker, "tag": row.sector} for row in results]

# --- 기록 저장 함수들 ---

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

def save_analysis_result(ticker, price, score, report):
    """
    [NEW] 기술적 분석 결과 저장 (Brain 모듈에서 호출)
    """
    client = get_client()
    if not client: return

    table_ref = f"{client.project}.{DATASET_ID}.{TABLE_ANALYSIS}"
    
    # 테이블 없으면 생성 (Schema: code, price, total_score, report, updated_at)
    schema = [
        bigquery.SchemaField("code", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("price", "FLOAT", mode="NULLABLE"),
        bigquery.SchemaField("total_score", "INTEGER", mode="NULLABLE"),
        bigquery.SchemaField("report", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("updated_at", "TIMESTAMP", mode="NULLABLE"),
    ]
    try: client.create_table(bigquery.Table(table_ref, schema=schema), exists_ok=True)
    except: pass

    rows = [{
        "code": ticker,
        "price": float(price),
        "total_score": int(score) if score else 0,
        "report": report,
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }]
    try: client.insert_rows_json(table_ref, rows)
    except Exception as e: print(f"[BQ Save Error] {e}")

def save_daily_balance(total_asset, cash, stock_val, pnl_daily):
    client = get_client()
    if not client: return
    table_ref = f"{client.project}.{DATASET_ID}.{TABLE_BALANCE}"
    
    schema = [
        bigquery.SchemaField("date", "DATE", mode="REQUIRED"),
        bigquery.SchemaField("total_asset", "FLOAT", mode="NULLABLE"),
        bigquery.SchemaField("cash", "FLOAT", mode="NULLABLE"),
        bigquery.SchemaField("stock_val", "FLOAT", mode="NULLABLE"),
        bigquery.SchemaField("pnl_daily", "FLOAT", mode="NULLABLE"),
    ]
    try: client.create_table(bigquery.Table(table_ref, schema=schema), exists_ok=True)
    except: pass

    today = datetime.now().strftime("%Y-%m-%d")
    rows = [{
        "date": today,
        "total_asset": float(total_asset),
        "cash": float(cash),
        "stock_val": float(stock_val),
        "pnl_daily": float(pnl_daily)
    }]
    try: client.insert_rows_json(table_ref, rows)
    except: pass

def save_profile(profile_data):
    client = get_client()
    if not client: return
    table_ref = f"{client.project}.{DATASET_ID}.{TABLE_USER}"
    rows = [{"updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "profile_json": json.dumps(profile_data, ensure_ascii=False)}]
    try: client.insert_rows_json(table_ref, rows)
    except: pass

# --- 데이터 조회 함수들 ---

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
    """
    [AI] '내가 아는 종목' 리스트 (히스토리 기반)
    """
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

def get_profile():
    client = get_client()
    if not client: return None
    query = f"SELECT profile_json FROM `{client.project}.{DATASET_ID}.{TABLE_USER}` ORDER BY updated_at DESC LIMIT 1"
    try:
        results = list(client.query(query).result())
        if results: return json.loads(results[0].profile_json)
    except: return None
    return None

def get_top_ranked_stocks(limit=5):
    """
    [AI용] 추천 종목 조회 (새 테이블이 없으면 과거 기록에서 조회)
    """
    client = get_client()
    if not client: return []

    results = []

    # 1. [우선순위] 최신 기술적 분석 테이블(stock_analysis) 조회
    try:
        query = f"""
            SELECT code, report, price, total_score, updated_at
            FROM `{client.project}.{DATASET_ID}.{TABLE_ANALYSIS}`
            ORDER BY updated_at DESC, total_score DESC
            LIMIT {limit}
        """
        query_job = client.query(query)
        rows = list(query_job.result())
        
        for row in rows:
            results.append({
                "code": row['code'],
                "price": row['price'],
                "report": row['report'],
                "total_score": row['total_score'],
                "date": str(row['updated_at'])
            })
            
    except Exception:
        # 테이블이 없거나 에러가 나면 무시하고 다음 단계(과거 기록)로 넘어감
        pass

    # 2. [비상대책] 새 테이블에 데이터가 없으면 'trade_history' 조회 (Fallback)
    if not results:
        print(" [System] 최신 분석 테이블이 비어있어, 과거 히스토리를 조회합니다.")
        try:
            # trade_history에서 가장 최근에 분석한 종목들 가져오기
            current_mode = mervis_state.get_mode()
            query_history = f"""
                SELECT ticker, report, price, log_date
                FROM `{client.project}.{DATASET_ID}.{TABLE_HISTORY}`
                WHERE mode = '{current_mode}'
                ORDER BY log_date DESC
                LIMIT {limit}
            """
            rows = list(client.query(query_history).result())
            
            for row in rows:
                results.append({
                    "code": row['ticker'],
                    "price": row['price'],
                    "report": row['report'],
                    "total_score": 0, # 과거 기록엔 점수가 없으므로 0 처리
                    "date": str(row['log_date'])
                })
        except Exception as e:
            print(f" [BQ Error] 과거 기록 조회 실패: {e}")

    return results