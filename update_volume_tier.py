import yfinance as yf
from google.cloud import bigquery
from google.oauth2 import service_account
import os
import pandas as pd
from datetime import datetime
import time
import re # 정규표현식 사용 (특수문자 제거용)

# 설정
KEY_PATH = "service_account.json"
DATASET_ID = "mervis_db"
TABLE_TICKERS = "ticker_universe"

def get_client():
    if not os.path.exists(KEY_PATH): return None
    credentials = service_account.Credentials.from_service_account_file(KEY_PATH)
    return bigquery.Client(credentials=credentials, project=credentials.project_id)

def generate_search_keywords(sector, name):
    """
    [Smart Tagging V2] 
    1. 하드코딩된 약어 매핑 (Smart)
    2. 섹터명을 단어 단위로 쪼개서 자동 등록 (Fallback) -> 빈칸 방지
    """
    keywords = set() # 중복 방지를 위해 set 사용
    
    sec_str = str(sector).upper() if sector else ""
    name_str = str(name).upper() if name else ""

    # --- 1. 스마트 약어 매핑 (우리가 아는 것들) ---
    if "TECHNOLOGY" in sec_str or "IT " in sec_str or "SOFTWARE" in sec_str:
        keywords.update(["TECH", "IT"])
    if "SEMICONDUCTOR" in sec_str or "반도체" in sec_str:
        keywords.update(["SEMI", "CHIP", "TECH"])
    if "FINANCIAL" in sec_str or "BANK" in sec_str or "금융" in sec_str:
        keywords.update(["FIN", "BANK"])
    if "HEALTH" in sec_str or "BIO" in sec_str or "PHARMA" in sec_str:
        keywords.update(["BIO", "HEALTH", "MED"])
    if "ENERGY" in sec_str or "OIL" in sec_str or "GAS" in sec_str:
        keywords.update(["ENERGY", "OIL"])
    if "CONSUMER" in sec_str or "RETAIL" in sec_str or "소비" in sec_str:
        keywords.update(["CONSUMER", "RETAIL"])
    if "COMMUNICATION" in sec_str or "MEDIA" in sec_str:
        keywords.update(["COM", "MEDIA"])
    if "AUTO" in sec_str or "VEHICLE" in sec_str or "자동차" in sec_str:
        keywords.update(["CAR", "EV", "AUTO"])
    if "CONSTRUCTION" in sec_str or "건설" in sec_str:
        keywords.update(["CONSTRUCT", "INFRA"])
    if "ETF" in sec_str:
        keywords.add("ETF")

    # --- 2. 이름 기반 보조 매핑 ---
    if "AIRLINES" in name_str or "AIR" in name_str:
        keywords.update(["AIR", "TRAVEL"])
    if "COIN" in name_str or "BLOCKCHAIN" in name_str or "CRYPTO" in name_str:
        keywords.update(["COIN", "CRYPTO"])
    if "AI " in name_str or "ROBOT" in name_str:
        keywords.update(["AI", "ROBOT"])

    # --- 3. [핵심] 자동 추출 (빈칸 방지 안전장치) ---
    stopwords = ["AND", "&", "OR", "OF", "THE", "SERVICES", "PRODUCTS", "INC", "LTD", "CORP", "HOLDINGS", "GROUP", "SOLUTIONS", "SYSTEMS"]
    
    clean_sec = re.sub(r'[^0-9a-zA-Z가-힣]', ' ', sec_str)
    
    for word in clean_sec.split():
        if len(word) >= 2 and word not in stopwords:
            keywords.add(word)

    return ", ".join(list(keywords))

# [수정] 함수 이름 변경 (update_volume_tier -> update_volume_data)
# main.py에서 호출하는 이름과 일치시킴
def update_volume_data():
    client = get_client()
    if not client: return

    # [Step 1] 기존 데이터 로딩
    print("[Step 1] BigQuery에서 기존 종목 정보 로딩 중...")
    query = f"SELECT ticker, name, sector FROM `{client.project}.{DATASET_ID}.{TABLE_TICKERS}`"
    results = list(client.query(query).result())
    
    ticker_info_map = {row.ticker: {'name': row.name, 'sector': row.sector} for row in results}
    all_tickers = list(ticker_info_map.keys())
    
    print(f"[Step 2] 총 {len(all_tickers)}개 종목 분석 시작...")

    batch_size = 1000
    updates = {} 

    for i in range(0, len(all_tickers), batch_size):
        batch = all_tickers[i:i+batch_size]
        batch_str = " ".join(batch)
        
        try:
            print(f" -> 배치 다운로드 중 ({i+1}~{min(i+batch_size, len(all_tickers))})...")
            time.sleep(2) 
            
            df = yf.download(batch_str, period="5d", progress=False, threads=True)
            
            try:
                vol_df = df['Volume']
                close_df = df['Close']
            except KeyError:
                continue

            if isinstance(vol_df, pd.Series):
                 mean_vols = pd.DataFrame(vol_df).mean()
                 vol_data_raw = pd.DataFrame(vol_df)
                 close_data = pd.DataFrame(close_df)
            else:
                 mean_vols = vol_df.mean()
                 vol_data_raw = vol_df
                 close_data = close_df
            
            for ticker in batch:
                avg_vol = 0
                if ticker in mean_vols and not pd.isna(mean_vols[ticker]):
                    avg_vol = int(mean_vols[ticker])

                status = "BAD"
                if avg_vol >= 1000000: status = "ACTIVE_HIGH"
                elif avg_vol >= 200000: status = "ACTIVE_MID"
                
                last_vol = 0
                try:
                    if ticker in vol_data_raw:
                        vols = vol_data_raw[ticker].dropna()
                        if not vols.empty: last_vol = int(vols.iloc[-1])
                except: pass

                rate = 0.0
                try:
                    if ticker in close_data:
                        prices = close_data[ticker].dropna()
                        if len(prices) >= 2:
                            prev = prices.iloc[-2]
                            curr = prices.iloc[-1]
                            if prev > 0: rate = ((curr - prev) / prev) * 100
                except: pass

                updates[ticker] = {'status': status, 'rate': round(rate, 2), 'last_vol': last_vol}
                
        except Exception as e:
            print(f" [Skip] 배치 에러: {e}")

    print("[Step 3] 최종 데이터 병합 및 DB 덮어쓰기...")
    
    rows_to_insert = []
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    count_summary = {"ACTIVE_HIGH": 0, "ACTIVE_MID": 0, "BAD": 0}
    
    for ticker in all_tickers:
        info = ticker_info_map.get(ticker, {})
        data = updates.get(ticker, {'status': 'BAD', 'rate': 0.0, 'last_vol': 0})
        
        status = data['status']
        if status in count_summary: count_summary[status] += 1
        
        # 키워드 생성 로직 적용
        sector = info.get('sector', '')
        name = info.get('name', '')
        keywords = generate_search_keywords(sector, name)
        
        rows_to_insert.append({
            "ticker": ticker,
            "name": name,
            "sector": sector,
            "keywords": keywords, 
            "status": status,
            "change_rate": data['rate'],
            "last_volume": data['last_vol'],
            "fail_count": 0,
            "updated_at": timestamp
        })

    table_ref = f"{client.project}.{DATASET_ID}.{TABLE_TICKERS}"
    
    job_config = bigquery.LoadJobConfig(
        write_disposition="WRITE_TRUNCATE",
        schema=[
            bigquery.SchemaField("ticker", "STRING", mode="REQUIRED"),
            bigquery.SchemaField("name", "STRING", mode="NULLABLE"),
            bigquery.SchemaField("sector", "STRING", mode="NULLABLE"),
            bigquery.SchemaField("keywords", "STRING", mode="NULLABLE"),
            bigquery.SchemaField("status", "STRING", mode="NULLABLE"),
            bigquery.SchemaField("change_rate", "FLOAT", mode="NULLABLE"), 
            bigquery.SchemaField("last_volume", "INTEGER", mode="NULLABLE"),
            bigquery.SchemaField("fail_count", "INTEGER", mode="NULLABLE"),
            bigquery.SchemaField("updated_at", "STRING", mode="NULLABLE"),
        ]
    )

    try:
        job = client.load_table_from_json(rows_to_insert, table_ref, job_config=job_config)
        job.result()
        print(f"\n[Complete] DB 업데이트 완료.")
        print(f" - HIGH: {count_summary['ACTIVE_HIGH']} / MID: {count_summary['ACTIVE_MID']} / BAD: {count_summary['BAD']}")
    except Exception as e:
        print(f"[Critical Error] DB 저장 실패: {e}")

if __name__ == "__main__":
    update_volume_data()