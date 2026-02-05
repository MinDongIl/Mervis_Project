from google.cloud import bigquery
from google.oauth2 import service_account
import os
import json
import math
from datetime import datetime
from deep_translator import GoogleTranslator
import mervis_state

# BigQuery 상수
DATASET_ID = "mervis_db"
TABLE_HISTORY = "trade_history"
TABLE_USER = "user_info"
TABLE_TICKERS = "ticker_universe"
TABLE_BALANCE = "daily_balance"
TABLE_ANALYSIS = "stock_analysis"
TABLE_FEATURES = "daily_features"

def get_client():
    # 1. 로컬 개발 환경용: 파일이 존재하면 사용 (선택 사항)
    # 2. 클라우드 환경용: 파일이 없으면 ADC(Application Default Credentials) 사용
    try:
        if os.path.exists("service_account.json"):
            credentials = service_account.Credentials.from_service_account_file("service_account.json")
            return bigquery.Client(credentials=credentials, project=credentials.project_id)
        else:
            # GCP Secret Manager나 환경 변수에 의해 인증됨
            # 프로젝트 ID는 환경 변수 'GOOGLE_CLOUD_PROJECT'에서 자동으로 가져옴
            project_id = os.getenv("GCP_PROJECT_ID")
            return bigquery.Client(project=project_id)
    except Exception as e:
        print(f" [BQ Error] Failed to initialize BigQuery Client: {e}")
        return None

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

def ensure_history_table_schema(client):
    # trade_history 테이블 스키마 보정
    table_id = f"{client.project}.{DATASET_ID}.{TABLE_HISTORY}"
    try:
        table = client.get_table(table_id)
        new_columns = [
            bigquery.SchemaField("action", "STRING", mode="NULLABLE"),
            bigquery.SchemaField("target_price", "FLOAT", mode="NULLABLE"),
            bigquery.SchemaField("cut_price", "FLOAT", mode="NULLABLE"),
            bigquery.SchemaField("result_status", "STRING", mode="NULLABLE"),
            bigquery.SchemaField("feedback", "STRING", mode="NULLABLE")
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
    except: pass

def save_log(ticker, mode, price, report, news_summary="", action="WAITING", target_price=0.0, cut_price=0.0):
    client = get_client()
    if not client: return
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
        bigquery.SchemaField("result_status", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("feedback", "STRING", mode="NULLABLE")
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
        "result_status": "PENDING",
        "feedback": None
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

def safe_float(val, default=0.0):
    # NaN 및 Infinity 값 처리
    try:
        f_val = float(val)
        if math.isnan(f_val) or math.isinf(f_val):
            return default
        return f_val
    except:
        return default

def ensure_daily_features_schema(client):
    # daily_features 테이블에 price 컬럼이 없으면 자동 추가
    table_id = f"{client.project}.{DATASET_ID}.{TABLE_FEATURES}"
    try:
        table = client.get_table(table_id)
        existing_fields = {f.name for f in table.schema}
        
        # 추가할 컬럼 정의
        new_columns = []
        if "price" not in existing_fields:
            new_columns.append(bigquery.SchemaField("price", "FLOAT", mode="NULLABLE"))
            
        if new_columns:
            original_schema = table.schema
            new_schema = original_schema[:] + new_columns
            table.schema = new_schema
            client.update_table(table, ["schema"])
            # print(" [Info] daily_features 테이블에 price 컬럼이 자동 추가되었습니다.")
    except: pass

def save_daily_features(ticker, price, tech_data, fund_data, supply_data):
    # ML 학습용 데이터 저장 (Schema Update Logic Included)
    client = get_client()
    if not client: return
    
    # 1. 스키마 보정
    ensure_daily_features_schema(client)
    
    table_ref = f"{client.project}.{DATASET_ID}.{TABLE_FEATURES}"
    
    # ML Feature Schema (참고용 - 실제 생성은 create_table이 수행)
    schema = [
        bigquery.SchemaField("date", "DATE", mode="REQUIRED"),
        bigquery.SchemaField("ticker", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("price", "FLOAT", mode="NULLABLE"),
        
        # Technical
        bigquery.SchemaField("rsi", "FLOAT", mode="NULLABLE"),
        bigquery.SchemaField("vwap_ratio", "FLOAT", mode="NULLABLE"), 
        bigquery.SchemaField("ma20_ratio", "FLOAT", mode="NULLABLE"), 
        bigquery.SchemaField("vol_ratio", "FLOAT", mode="NULLABLE"),
        
        # Fundamental
        bigquery.SchemaField("forward_pe", "FLOAT", mode="NULLABLE"),
        bigquery.SchemaField("target_upside", "FLOAT", mode="NULLABLE"),
        
        # Supply
        bigquery.SchemaField("inst_pct", "FLOAT", mode="NULLABLE"),
        bigquery.SchemaField("short_ratio", "FLOAT", mode="NULLABLE"),
        
        # Target (Label)
        bigquery.SchemaField("next_day_return", "FLOAT", mode="NULLABLE")
    ]
    
    try: client.create_table(bigquery.Table(table_ref, schema=schema), exists_ok=True)
    except: pass

    try:
        # 데이터 정제
        current_price = safe_float(price)
        rsi = tech_data.get('rsi', 0.0)
        vwap = tech_data.get('vwap', 0.0)
        
        if safe_float(vwap) == 0.0:
            vwap_ratio = 1.0
        else:
            vwap_ratio = current_price / vwap
            
        ma20_ratio = tech_data.get('ma20_ratio', 0.0)
        vol_ratio = tech_data.get('vol_ratio', 0.0)
        
        # Fundamental
        val = fund_data.get('valuation', {}) if fund_data else {}
        con = fund_data.get('consensus', {}) if fund_data else {}
        target_mean = con.get('target_mean', 0.0)
        
        if current_price == 0.0:
            target_upside = 0.0
        else:
            target_upside = (target_mean - current_price) / current_price if target_mean else 0.0
        
        today = datetime.now().strftime("%Y-%m-%d")
        
        rows = [{
            "date": today,
            "ticker": ticker,
            "price": current_price,
            "rsi": safe_float(rsi),
            "vwap_ratio": safe_float(vwap_ratio, 1.0),
            "ma20_ratio": safe_float(ma20_ratio, 0.0),
            "vol_ratio": safe_float(vol_ratio, 0.0),
            "forward_pe": safe_float(val.get('forward_pe', 0.0)),
            "target_upside": safe_float(target_upside, 0.0),
            "inst_pct": safe_float(supply_data.get('institution_pct', 0.0)),
            "short_ratio": safe_float(supply_data.get('short_ratio', 0.0)),
            "next_day_return": None 
        }]
        
        client.insert_rows_json(table_ref, rows)
    except Exception as e:
        print(f" [DB Feature Save Error] {ticker}: {e}")

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

def get_pending_trades():
    client = get_client()
    if not client: return []
    
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

def update_trade_feedback(ticker, log_date, feedback):
    client = get_client()
    if not client: return
    
    date_str = log_date.strftime('%Y-%m-%d %H:%M:%S')
    
    query = f"""
        UPDATE `{client.project}.{DATASET_ID}.{TABLE_HISTORY}`
        SET feedback = @feedback
        WHERE ticker = @ticker 
          AND CAST(log_date AS STRING) LIKE @date_pattern
    """
    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("feedback", "STRING", feedback),
            bigquery.ScalarQueryParameter("ticker", "STRING", ticker),
            bigquery.ScalarQueryParameter("date_pattern", "STRING", f"{date_str}%")
        ]
    )
    try:
        query_job = client.query(query, job_config=job_config)
        query_job.result()
    except Exception as e:
        print(f" [BQ Feedback Error] {ticker} 피드백 저장 실패: {e}")

def get_trades_needing_feedback():
    client = get_client()
    if not client: return []
    
    query = f"""
        SELECT ticker, mode, price, action, report, result_status, log_date
        FROM `{client.project}.{DATASET_ID}.{TABLE_HISTORY}`
        WHERE result_status IN ('WIN', 'LOSE')
          AND feedback IS NULL
        ORDER BY log_date DESC
        LIMIT 5
    """
    try:
        results = list(client.query(query).result())
        return [{
            "ticker": row.ticker,
            "mode": row.mode,
            "entry_price": row.price,
            "action": row.action,
            "report": row.report,
            "result": row.result_status,
            "date": row.log_date
        } for row in results]
    except: return []

def get_past_lessons(ticker, limit=5):
    client = get_client()
    if not client: return []
    
    query = f"""
        SELECT log_date, result_status, feedback
        FROM `{client.project}.{DATASET_ID}.{TABLE_HISTORY}`
        WHERE ticker = '{ticker}' 
          AND feedback IS NOT NULL
        ORDER BY log_date DESC LIMIT {limit}
    """
    try:
        results = list(client.query(query).result())
        return [{
            "date": str(row.log_date)[:10], 
            "result": row.result_status, 
            "feedback": row.feedback
        } for row in results]
    except: return []

def get_all_tickers_simple():
    """
    [GUI 검색용] 전체 종목 티커만 빠르게 로드
    """
    client = get_client()
    if not client: return []
    
    query = f"SELECT ticker FROM `{client.project}.{DATASET_ID}.{TABLE_TICKERS}` ORDER BY ticker"
    try:
        results = list(client.query(query).result())
        return [row.ticker for row in results]
    except Exception as e:
        print(f" [DB Error] 전체 티커 로드 실패: {e}")
        return []

def get_prediction(ticker):
    """
    [머신러닝] Boosted Tree 모델에게 '내일 수익률' 예측 요청 (ML.PREDICT 사용)
    """
    client = get_client()
    if not client: return None

    # 최신 데이터 1건을 가져와서 예측
    # ML.PREDICT는 회귀 모델의 경우 'predicted_정답컬럼명'으로 결과를 반환
    # 정답 컬럼은 predicted_next_day_return
    query = f"""
        SELECT
          predicted_next_day_return as predicted_return
        FROM
          ML.PREDICT(MODEL `{client.project}.{DATASET_ID}.return_forecast_model`, 
            (
              SELECT * FROM `{client.project}.{DATASET_ID}.{TABLE_FEATURES}`
              WHERE ticker = '{ticker}'
              ORDER BY date DESC
              LIMIT 1
            )
          )
    """
    try:
        results = list(client.query(query).result())
        if results:
            row = results[0]
            pred = float(row.predicted_return)
            # 회귀 모델은 구간 예측을 기본 제공하지 않으므로, 일단 예측값으로 통일
            return {
                "predicted_return": pred,
                "return_min": pred,
                "return_max": pred
            }
    except Exception as e:
        # print(f" [ML Error] {ticker} 예측 실패: {e}") 
        return None
    return None