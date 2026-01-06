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
TABLE_ANALYSIS = "stock_analysis"

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
    client = get_client()
    if not client: return []
    
    results = []
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
            
    if not results:
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

# --- 기록 저장 함수들 ---

def ensure_history_table_schema(client):
    """
    trade_history 테이블에 예측 데이터 컬럼이 없으면 추가
    """
    table_id = f"{client.project}.{DATASET_ID}.{TABLE_HISTORY}"
    try:
        table = client.get_table(table_id)
        
        new_columns = [
            bigquery.SchemaField("action", "STRING", mode="NULLABLE"),       # BUY/SELL/HOLD
            bigquery.SchemaField("target_price", "FLOAT", mode="NULLABLE"),  # 목표가
            bigquery.SchemaField("cut_price", "FLOAT", mode="NULLABLE"),     # 손절가
            bigquery.SchemaField("result_status", "STRING", mode="NULLABLE") # PENDING/WIN/LOSE
        ]
        
        existing_fields = {f.name for f in table.schema}
        added_fields = []
        
        for col in new_columns:
            if col.name not in existing_fields:
                added_fields.append(col)
        
        if added_fields:
            original_schema = table.schema
            new_schema = original_schema[:] + added_fields
            table.schema = new_schema
            client.update_table(table, ["schema"])
            # print(f" [DB] 테이블 스키마 업데이트 완료 ({len(added_fields)}개 컬럼 추가)")
            
    except Exception as e:
        pass

def save_log(ticker, mode, price, report, news_summary="", action="WAITING", target_price=0.0, cut_price=0.0):
    client = get_client()
    if not client: return
    
    # 스키마 확인 및 업데이트
    ensure_history_table_schema(client)
    
    table_ref = f"{client.project}.{DATASET_ID}.{TABLE_HISTORY}"
    
    schema = [
        bigquery.SchemaField("log_date", "TIMESTAMP", mode="REQUIRED"),
        bigquery.SchemaField("ticker", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("mode", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("price", "FLOAT", mode="REQUIRED"),
        bigquery.SchemaField("report", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("news_summary", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("strategy_result", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("action", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("target_price", "FLOAT", mode="NULLABLE"),
        bigquery.SchemaField("cut_price", "FLOAT", mode="NULLABLE"),
        bigquery.SchemaField("result_status", "STRING", mode="NULLABLE") 
    ]
    try: client.create_table(bigquery.Table(table_ref, schema=schema), exists_ok=True)
    except: pass

    rows = [{
        "log_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "ticker": ticker, 
        "mode": mode, 
        "price": price,
        "report": report, 
        "news_summary": news_summary, 
        "strategy_result": "WAITING",
        "action": action,
        "target_price": target_price,
        "cut_price": cut_price,
        "result_status": "PENDING"
    }]
    
    try: client.insert_rows_json(table_ref, rows)
    except Exception as e: print(f" [DB Save Error] {e}")

def save_analysis_result(ticker, price, score, report):
    client = get_client()
    if not client: return
    table_ref = f"{client.project}.{DATASET_ID}.{TABLE_ANALYSIS}"
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
        "date": today, "total_asset": float(total_asset),
        "cash": float(cash), "stock_val": float(stock_val),
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
    client = get_client()
    if not client: return []
    results = []
    try:
        query = f"""
            SELECT code, report, price, total_score, updated_at
            FROM `{client.project}.{DATASET_ID}.{TABLE_ANALYSIS}`
            ORDER BY updated_at DESC, total_score DESC LIMIT {limit}
        """
        rows = list(client.query(query).result())
        for row in rows:
            results.append({
                "code": row['code'], "price": row['price'],
                "report": row['report'], "total_score": row['total_score'],
                "date": str(row['updated_at'])
            })
    except: pass

    if not results:
        try:
            current_mode = mervis_state.get_mode()
            query_history = f"""
                SELECT ticker, report, price, log_date
                FROM `{client.project}.{DATASET_ID}.{TABLE_HISTORY}`
                WHERE mode = '{current_mode}'
                ORDER BY log_date DESC LIMIT {limit}
            """
            rows = list(client.query(query_history).result())
            for row in rows:
                results.append({
                    "code": row['ticker'], "price": row['price'],
                    "report": row['report'], "total_score": 0,
                    "date": str(row['log_date'])
                })
        except: pass
    return results

# --- [채점 시스템용 함수] ---

def get_pending_trades():
    client = get_client()
    if not client: return []
    
    # [수정] action 필터 확장 (BUY/SELL/HOLD/WAIT)
    # HOLD의 경우 target_price가 없을 수 있으므로 NULL 체크 제거
    query = f"""
        SELECT ticker, mode, price, action, target_price, cut_price, log_date
        FROM `{client.project}.{DATASET_ID}.{TABLE_HISTORY}`
        WHERE result_status = 'PENDING' 
          AND action IN ('BUY', 'SELL', 'HOLD', 'WAIT')
        ORDER BY log_date ASC
    """
    try:
        results = list(client.query(query).result())
        pending_list = []
        for row in results:
            pending_list.append({
                "ticker": row.ticker,
                "mode": row.mode,
                "entry_price": row.price,
                "action": row.action,
                "target": row.target_price if row.target_price is not None else 0.0,
                "cut": row.cut_price if row.cut_price is not None else 0.0,
                "date": row.log_date
            })
        return pending_list
    except Exception as e:
        print(f" [BQ Error] 대기중인 매매 조회 실패: {e}")
        return []

def update_trade_result(ticker, log_date, result_status):
    client = get_client()
    if not client: return
    
    date_str = log_date.strftime('%Y-%m-%d %H:%M:%S')
    
    query = f"""
        UPDATE `{client.project}.{DATASET_ID}.{TABLE_HISTORY}`
        SET result_status = '{result_status}'
        WHERE ticker = '{ticker}' 
          AND log_date = '{date_str}'
    """
    try:
        query_job = client.query(query)
        query_job.result()
    except Exception as e:
        print(f" [BQ Update Error] {ticker} 업데이트 실패: {e}")