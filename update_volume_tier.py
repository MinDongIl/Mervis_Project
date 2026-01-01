import yfinance as yf
from google.cloud import bigquery
from google.oauth2 import service_account
import os
import pandas as pd
from datetime import datetime
import time

# 설정
KEY_PATH = "service_account.json"
DATASET_ID = "mervis_db"
TABLE_TICKERS = "ticker_universe"

def get_client():
    if not os.path.exists(KEY_PATH): return None
    credentials = service_account.Credentials.from_service_account_file(KEY_PATH)
    return bigquery.Client(credentials=credentials, project=credentials.project_id)

def update_volume_tier():
    client = get_client()
    if not client: return

    # [Step 1] 기존 데이터(이름, 섹터 포함) 백업 로딩
    print("[Step 1] BigQuery에서 기존 종목 정보 로딩 중...")
    query = f"SELECT ticker, name, sector FROM `{client.project}.{DATASET_ID}.{TABLE_TICKERS}`"
    results = list(client.query(query).result())
    
    # 딕셔너리로 변환
    ticker_info_map = {row.ticker: {'name': row.name, 'sector': row.sector} for row in results}
    all_tickers = list(ticker_info_map.keys())
    
    print(f"[Step 2] 총 {len(all_tickers)}개 종목 정밀 분석 (거래량/등락률) 시작...")

    batch_size = 1000
    updates = {} 

    for i in range(0, len(all_tickers), batch_size):
        batch = all_tickers[i:i+batch_size]
        batch_str = " ".join(batch)
        
        try:
            print(f" -> 배치 다운로드 중 ({i+1}~{min(i+batch_size, len(all_tickers))})...")
            time.sleep(2) # Rate Limit 방지
            
            # 5일치 데이터 다운로드
            df = yf.download(batch_str, period="5d", progress=False, threads=True)
            
            # 데이터 분리 (Volume, Close)
            try:
                vol_df = df['Volume']
                close_df = df['Close']
            except KeyError:
                continue

            # 평균 거래량 계산 (등급 산정용)
            if isinstance(vol_df, pd.Series):
                 mean_vols = pd.DataFrame(vol_df).mean()
                 vol_data_raw = pd.DataFrame(vol_df)
                 close_data = pd.DataFrame(close_df)
            else:
                 mean_vols = vol_df.mean()
                 vol_data_raw = vol_df
                 close_data = close_df
            
            for ticker in batch:
                # 1. 거래량 분석 (등급 산정)
                avg_vol = 0
                if ticker in mean_vols and not pd.isna(mean_vols[ticker]):
                    avg_vol = int(mean_vols[ticker])

                # 등급 산정
                status = "BAD"
                if avg_vol >= 1000000: status = "ACTIVE_HIGH"
                elif avg_vol >= 200000: status = "ACTIVE_MID"
                
                # 2. 직전 장 거래량 추출 (Last Volume)
                last_vol = 0
                try:
                    if ticker in vol_data_raw:
                        vols = vol_data_raw[ticker].dropna()
                        if not vols.empty:
                            last_vol = int(vols.iloc[-1])
                except: pass

                # 3. 등락률 계산 (Change Rate)
                rate = 0.0
                try:
                    if ticker in close_data:
                        prices = close_data[ticker].dropna()
                        if len(prices) >= 2:
                            prev_close = prices.iloc[-2]
                            curr_close = prices.iloc[-1]
                            if prev_close > 0:
                                rate = ((curr_close - prev_close) / prev_close) * 100
                except: pass

                updates[ticker] = {
                    'status': status, 
                    'rate': round(rate, 2),
                    'last_vol': last_vol
                }
                
        except Exception as e:
            print(f" [Skip] 배치 에러: {e}")

    print("[Step 3] 최종 데이터 병합 및 DB 덮어쓰기 (Schema Update)...")
    
    rows_to_insert = []
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    count_summary = {"ACTIVE_HIGH": 0, "ACTIVE_MID": 0, "BAD": 0}
    
    for ticker in all_tickers:
        info = ticker_info_map.get(ticker, {})
        data = updates.get(ticker, {'status': 'BAD', 'rate': 0.0, 'last_vol': 0})
        
        status = data['status']
        rate = data['rate']
        last_vol = data['last_vol']
        
        if status in count_summary: count_summary[status] += 1
        
        rows_to_insert.append({
            "ticker": ticker,
            "name": info.get('name', ''),
            "sector": info.get('sector', ''),
            "status": status,
            "change_rate": rate,      # [NEW] 등락률
            "last_volume": last_vol,  # [NEW] 직전 장 거래량
            "fail_count": 0,
            "updated_at": timestamp
        })

    # BigQuery 테이블 덮어쓰기
    table_ref = f"{client.project}.{DATASET_ID}.{TABLE_TICKERS}"
    
    job_config = bigquery.LoadJobConfig(
        write_disposition="WRITE_TRUNCATE",
        schema=[
            bigquery.SchemaField("ticker", "STRING", mode="REQUIRED"),
            bigquery.SchemaField("name", "STRING", mode="NULLABLE"),
            bigquery.SchemaField("sector", "STRING", mode="NULLABLE"),
            bigquery.SchemaField("status", "STRING", mode="NULLABLE"),
            bigquery.SchemaField("change_rate", "FLOAT", mode="NULLABLE"), 
            bigquery.SchemaField("last_volume", "INTEGER", mode="NULLABLE"), # [NEW] 스키마 추가
            bigquery.SchemaField("fail_count", "INTEGER", mode="NULLABLE"),
            bigquery.SchemaField("updated_at", "STRING", mode="NULLABLE"),
        ]
    )

    try:
        job = client.load_table_from_json(rows_to_insert, table_ref, job_config=job_config)
        job.result()
        
        print(f"\n[Complete] DB 업데이트 완료 (등락률 + 최근 거래량).")
        print(f" - HIGH (주도주): {count_summary['ACTIVE_HIGH']}개")
        print(f" - MID (일반): {count_summary['ACTIVE_MID']}개")
        print(f" - BAD (소외주): {count_summary['BAD']}개")
        
    except Exception as e:
        print(f"[Critical Error] DB 저장 실패: {e}")

if __name__ == "__main__":
    update_volume_tier()