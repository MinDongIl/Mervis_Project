import FinanceDataReader as fdr
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
    if not os.path.exists(KEY_PATH):
        print(f"[Error] 키 파일 없음: {KEY_PATH}")
        return None
    credentials = service_account.Credentials.from_service_account_file(KEY_PATH)
    return bigquery.Client(credentials=credentials, project=credentials.project_id)

def get_massive_tickers():
    print("[System] 미국 3대 거래소(NASDAQ, NYSE, AMEX) 전 종목 수집 중...")
    
    # 1. 거래소별 전체 리스트 확보
    df_nasdaq = fdr.StockListing('NASDAQ')
    df_nyse = fdr.StockListing('NYSE')
    df_amex = fdr.StockListing('AMEX')
    
    print(f" - NASDAQ: {len(df_nasdaq)}개")
    print(f" - NYSE: {len(df_nyse)}개")
    print(f" - AMEX: {len(df_amex)}개")
    
    # 2. 통합 및 데이터 정제
    # 필요한 컬럼만 추출: Symbol(티커), Name(이름), Industry(산업/섹터)
    df_all = pd.concat([df_nasdaq, df_nyse, df_amex])
    
    # 중복 제거 (티커 기준)
    df_all = df_all.drop_duplicates(subset=['Symbol'])
    
    # 3. 1차 필터링 (쓰레기 데이터 제거)
    # - 티커에 숫자나 특수문자가 너무 많은 것 제외 (워런트, 우선주 등)
    # - 섹터 정보가 없는 것 제외
    filtered_list = []
    
    for _, row in df_all.iterrows():
        ticker = str(row['Symbol'])
        name = str(row['Name'])
        sector = str(row.get('Industry', row.get('Sector', 'Unknown')))
        
        # [필터] 티커가 5글자 이상이면 보통 워런트/우선주/스팩일 확률 높음 (일반 주식은 1~4글자)
        # 단, GOOGL 같은 5글자 우량주도 있으니 너무 엄격하게는 말고, 특수문자 포함 여부로 판단
        if len(ticker) > 5: continue 
        if "^" in ticker or "." in ticker: continue # BRK.B 같은건 BRK-B로 변환 필요하지만 일단 제외
        
        filtered_list.append({
            "ticker": ticker,
            "name": name,
            "sector": sector,
            "status": "ACTIVE",  # [핵심] 기본 상태 '활성'
            "fail_count": 0      # [핵심] 실패 횟수 0
        })
        
    print(f"[System] 정제 후 최종 유니버스: {len(filtered_list)}개 종목 준비 완료.")
    return filtered_list

def seed_db():
    client = get_client()
    if not client: return

    # 1. 데이터 가져오기
    tickers = get_massive_tickers()
    
    # 2. 테이블 스키마 정의 (진화형 DB 구조)
    table_ref = f"{client.project}.{DATASET_ID}.{TABLE_TICKERS}"
    schema = [
        bigquery.SchemaField("ticker", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("name", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("sector", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("status", "STRING", mode="NULLABLE"),     # ACTIVE, INACTIVE, BAD
        bigquery.SchemaField("fail_count", "INTEGER", mode="NULLABLE"), # API 실패 횟수
        bigquery.SchemaField("updated_at", "TIMESTAMP", mode="NULLABLE"),
    ]
    
    # 테이블 생성
    try:
        client.create_table(bigquery.Table(table_ref, schema=schema), exists_ok=True)
    except: pass

    # 3. 기존 리스트 초기화 (주의: trade_history는 건드리지 않음!)
    try:
        query = f"DELETE FROM `{table_ref}` WHERE true"
        client.query(query).result()
        print("[BQ] 기존 종목 리스트 초기화 완료 (분석 기록은 유지됨).")
    except: pass

    # 4. 데이터 삽입 (배치 처리)
    rows_to_insert = []
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    for item in tickers:
        rows_to_insert.append({
            "ticker": item['ticker'],
            "name": item['name'],
            "sector": item['sector'],
            "status": "ACTIVE",
            "fail_count": 0,
            "updated_at": timestamp
        })
    
    # 1000개씩 끊어서 삽입
    batch_size = 1000
    total_inserted = 0
    print(f"[BQ] 데이터 업로드 시작 (총 {len(rows_to_insert)}개)...")
    
    for i in range(0, len(rows_to_insert), batch_size):
        batch = rows_to_insert[i:i+batch_size]
        errors = client.insert_rows_json(table_ref, batch)
        if not errors:
            total_inserted += len(batch)
            print(f" - {total_inserted}개 저장 완료...")
        else:
            print(f" [Error] 배치 저장 실패: {errors}")

    print("\n[Complete] 3,000+ 종목 DB 구축 완료. 머비스의 시야가 확장되었습니다.")

if __name__ == "__main__":
    seed_db()