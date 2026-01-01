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
    # UPDATE가 안 되므로, 데이터를 꺼내서 메모리에서 수정한 뒤 다시 덮어씌워야 함
    print("[Step 1] BigQuery에서 기존 종목 정보 로딩 중...")
    query = f"SELECT ticker, name, sector FROM `{client.project}.{DATASET_ID}.{TABLE_TICKERS}`"
    results = list(client.query(query).result())
    
    # 빠른 검색을 위해 딕셔너리로 변환
    # { 'AAPL': {'name': 'Apple', 'sector': 'Tech'}, ... }
    ticker_info_map = {row.ticker: {'name': row.name, 'sector': row.sector} for row in results}
    all_tickers = list(ticker_info_map.keys())
    
    print(f"[Step 2] 총 {len(all_tickers)}개 종목 거래량 분석 시작 (yfinance)...")

    # 거래량 데이터 수집
    batch_size = 1000
    updates = {} # { 'AAPL': 'ACTIVE_HIGH', ... }

    for i in range(0, len(all_tickers), batch_size):
        batch = all_tickers[i:i+batch_size]
        batch_str = " ".join(batch)
        
        try:
            print(f" -> 배치 다운로드 중 ({i+1}~{min(i+batch_size, len(all_tickers))})...")
            # Rate Limit 방지를 위해 2초 대기
            time.sleep(2)
            
            data = yf.download(batch_str, period="5d", progress=False, threads=True)['Volume']
            
            # 단일 종목/다중 종목 처리
            if isinstance(data, pd.Series):
                 mean_vols = pd.DataFrame(data).mean()
            else:
                 mean_vols = data.mean()
            
            for ticker in batch:
                vol = 0
                if ticker in mean_vols and not pd.isna(mean_vols[ticker]):
                    vol = int(mean_vols[ticker])

                # 등급 산정
                status = "BAD"
                if vol >= 1000000: status = "ACTIVE_HIGH"
                elif vol >= 200000: status = "ACTIVE_MID"
                
                updates[ticker] = status
                
        except Exception as e:
            print(f" [Skip] 배치 에러 (일부 누락 가능): {e}")

    print("[Step 3] 최종 데이터 병합 및 DB 덮어쓰기 (Streaming Buffer 우회)...")
    
    # 최종 업로드할 데이터 리스트 생성
    rows_to_insert = []
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # HIGH, MID, BAD 카운팅
    count_summary = {"ACTIVE_HIGH": 0, "ACTIVE_MID": 0, "BAD": 0}
    
    for ticker in all_tickers:
        info = ticker_info_map.get(ticker, {})
        status = updates.get(ticker, "BAD") # 분석 안 됐으면 BAD 처리
        
        # 카운트 증가
        if status in count_summary: count_summary[status] += 1
        
        rows_to_insert.append({
            "ticker": ticker,
            "name": info.get('name', ''),
            "sector": info.get('sector', ''),
            "status": status,
            "fail_count": 0,
            "updated_at": timestamp # STRING 형태로 저장 (JSON 호환)
        })

    # BigQuery 테이블 덮어쓰기 (Write Truncate)
    # LoadJob을 사용하면 Buffer 락을 무시하고 교체 가능
    table_ref = f"{client.project}.{DATASET_ID}.{TABLE_TICKERS}"
    
    job_config = bigquery.LoadJobConfig(
        write_disposition="WRITE_TRUNCATE", # 기존 데이터 지우고 덮어쓰기
        schema=[
            bigquery.SchemaField("ticker", "STRING", mode="REQUIRED"),
            bigquery.SchemaField("name", "STRING", mode="NULLABLE"),
            bigquery.SchemaField("sector", "STRING", mode="NULLABLE"),
            bigquery.SchemaField("status", "STRING", mode="NULLABLE"),
            bigquery.SchemaField("fail_count", "INTEGER", mode="NULLABLE"),
            bigquery.SchemaField("updated_at", "STRING", mode="NULLABLE"),
        ]
    )

    try:
        job = client.load_table_from_json(rows_to_insert, table_ref, job_config=job_config)
        job.result() # 완료 대기
        
        print(f"\n[Complete] DB 업데이트 완료.")
        print(f" - HIGH (주도주): {count_summary['ACTIVE_HIGH']}개")
        print(f" - MID (일반): {count_summary['ACTIVE_MID']}개")
        print(f" - BAD (소외주): {count_summary['BAD']}개")
        
    except Exception as e:
        print(f"[Critical Error] DB 저장 실패: {e}")

if __name__ == "__main__":
    update_volume_tier()