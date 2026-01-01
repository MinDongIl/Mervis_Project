import yfinance as yf
from google.cloud import bigquery
from google.oauth2 import service_account
import os
import pandas as pd
from datetime import datetime

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

    print("[Step 1] BigQuery에서 전체 종목 리스트 로딩...")
    query = f"SELECT ticker FROM `{client.project}.{DATASET_ID}.{TABLE_TICKERS}`"
    results = list(client.query(query).result())
    all_tickers = [row.ticker for row in results]
    
    print(f"[Step 2] 총 {len(all_tickers)}개 종목 거래량 분석 시작 (yfinance)...")

    # yfinance의 멀티스레딩 기능을 사용하여 속도 극대화
    # 5일 평균 거래량을 가져와서 일시적인 노이즈 제거
    batch_size = 1000
    updates = []

    for i in range(0, len(all_tickers), batch_size):
        batch = all_tickers[i:i+batch_size]
        batch_str = " ".join(batch)
        
        try:
            print(f" -> 배치 다운로드 중 ({i}~{i+batch_size})...")
            # threads=True가 핵심 (병렬 다운로드)
            data = yf.download(batch_str, period="5d", progress=False, threads=True)['Volume']
            
            # 평균 거래량 계산
            mean_vols = data.mean()
            
            for ticker in batch:
                vol = 0
                if isinstance(mean_vols, pd.Series): # 여러 종목일 때
                    if ticker in mean_vols and not pd.isna(mean_vols[ticker]):
                        vol = int(mean_vols[ticker])
                elif isinstance(mean_vols, int) or isinstance(mean_vols, float): # 한 종목일 때
                    vol = int(mean_vols)

                # 등급 산정 (기준은 조정 가능)
                status = "BAD"
                if vol >= 1000000: status = "ACTIVE_HIGH" # 100만주 이상 (주도주)
                elif vol >= 200000: status = "ACTIVE_MID" # 20만주 이상 (양호)
                
                updates.append(f"('{ticker}', '{status}')")
                
        except Exception as e:
            print(f" [Skip] 배치 처리 중 에러: {e}")

    print("[Step 3] BigQuery 업데이트 쿼리 실행...")
    
    # BigQuery MERGE 문을 사용하여 한 번에 효율적으로 업데이트
    # (임시 테이블 생성 -> 병합 -> 삭제 방식이 가장 빠름)
    # 여기서는 코드를 간결하게 하기 위해 Case문 쿼리 생성 방식 사용
    
    # 업데이트할 내용이 너무 많으므로, 상태별로 나누어 쿼리 실행
    high_list = [u.split(",")[0] for u in updates if "ACTIVE_HIGH" in u]
    mid_list = [u.split(",")[0] for u in updates if "ACTIVE_MID" in u]
    bad_list = [u.split(",")[0] for u in updates if "BAD" in u]

    def run_update(ticker_list, status):
        if not ticker_list: return
        # 2000개씩 끊어서 업데이트
        chunk_size = 2000
        for k in range(0, len(ticker_list), chunk_size):
            chunk = ticker_list[k:k+chunk_size]
            t_str = ", ".join(chunk)
            query = f"""
                UPDATE `{client.project}.{DATASET_ID}.{TABLE_TICKERS}`
                SET status = '{status}', updated_at = '{datetime.now()}'
                WHERE ticker IN ({t_str})
            """
            client.query(query).result()
            print(f" -> {status} 등급 {len(chunk)}개 업데이트 완료.")

    run_update(high_list, "ACTIVE_HIGH")
    run_update(mid_list, "ACTIVE_MID")
    run_update(bad_list, "BAD")

    print(f"\n[Complete] 분석 완료.")
    print(f" - HIGH (주도주): {len(high_list)}개")
    print(f" - MID (일반): {len(mid_list)}개")
    print(f" - BAD (소외주): {len(bad_list)}개")

if __name__ == "__main__":
    update_volume_tier()