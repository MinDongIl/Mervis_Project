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

def generate_search_keywords(sector, name):
    """
    [Smart Tagging] 섹터와 종목명을 분석하여 검색용 키워드(Tag) 자동 생성
    """
    keywords = []
    # 데이터가 없을 경우 방어 코드
    sec_str = str(sector).upper() if sector else ""
    name_str = str(name).upper() if name else ""

    # 1. 섹터 기반 매핑
    if "TECHNOLOGY" in sec_str or "IT " in sec_str or "SOFTWARE" in sec_str:
        keywords.extend(["TECH", "IT"])
    if "FINANCIAL" in sec_str or "BANK" in sec_str or "CAPITAL" in sec_str:
        keywords.extend(["FIN", "BANK"])
    if "HEALTH" in sec_str or "BIO" in sec_str or "PHARMA" in sec_str:
        keywords.extend(["BIO", "HEALTH", "MED"])
    if "CONSUMER" in sec_str or "RETAIL" in sec_str:
        keywords.extend(["CONSUMER", "RETAIL"])
    if "ENERGY" in sec_str or "OIL" in sec_str or "GAS" in sec_str:
        keywords.extend(["ENERGY", "OIL"])
    if "COMMUNICATION" in sec_str or "MEDIA" in sec_str:
        keywords.extend(["COM", "MEDIA"])
    if "SEMICONDUCTOR" in sec_str:
        keywords.extend(["SEMI", "CHIP", "TECH"])
    if "ETF" in sec_str:
        keywords.extend(["ETF"])

    # 2. 이름 기반 정밀 매핑
    if "SEMICONDUCTOR" in name_str or "DEVICES" in name_str:
        keywords.extend(["SEMI", "CHIP"])
    if "AIRLINES" in name_str or "AIR" in name_str:
        keywords.extend(["AIR", "TRAVEL"])
    if "MOTOR" in name_str or "AUTO" in name_str or "VEHICLE" in name_str:
        keywords.extend(["CAR", "EV", "AUTO"])
    if "COIN" in name_str or "BLOCKCHAIN" in name_str or "CRYPTO" in name_str:
        keywords.extend(["COIN", "CRYPTO"])
    if "AI " in name_str or "ROBOT" in name_str:
        keywords.extend(["AI", "ROBOT"])

    # 중복 제거 후 문자열 반환
    return ", ".join(list(set(keywords)))

def get_massive_tickers():
    print("[System] 미국 3대 거래소(NASDAQ, NYSE, AMEX) 전 종목 수집 중...")
    
    # 1. 거래소별 전체 리스트 확보
    try:
        df_nasdaq = fdr.StockListing('NASDAQ')
        df_nyse = fdr.StockListing('NYSE')
        df_amex = fdr.StockListing('AMEX')
    except Exception as e:
        print(f"[Critical Error] 데이터 수집 실패: {e}")
        return []
    
    print(f" - NASDAQ: {len(df_nasdaq)}개")
    print(f" - NYSE: {len(df_nyse)}개")
    print(f" - AMEX: {len(df_amex)}개")
    
    # 2. 통합 및 데이터 정제
    df_all = pd.concat([df_nasdaq, df_nyse, df_amex])
    
    # 중복 제거 (티커 기준)
    df_all = df_all.drop_duplicates(subset=['Symbol'])
    
    filtered_list = []
    
    print("[System] 데이터 정제 및 스마트 태그 생성 중...")

    for _, row in df_all.iterrows():
        ticker = str(row['Symbol'])
        name = str(row['Name'])
        # FinanceDataReader에서는 보통 'Industry'나 'Sector' 컬럼 사용
        sector = str(row.get('Industry', row.get('Sector', 'Unknown')))
        
        # [필터] 잡주 제거 (특수문자 포함, 5글자 초과 워런트 등)
        if len(ticker) > 5: continue 
        if "^" in ticker or "." in ticker: continue
        
        # [NEW] 키워드 생성
        keywords = generate_search_keywords(sector, name)
        
        filtered_list.append({
            "ticker": ticker,
            "name": name,
            "sector": sector,
            "keywords": keywords, # [NEW]
            "status": "BAD",      # 초기 상태는 '분석 전(BAD)'로 설정 -> 이후 update_volume_tier가 등급 매김
            "fail_count": 0,
            "change_rate": 0.0,
            "last_volume": 0
        })
        
    print(f"[System] 정제 후 최종 유니버스: {len(filtered_list)}개 종목 준비 완료.")
    return filtered_list

def seed_db():
    client = get_client()
    if not client: return

    # 1. 데이터 가져오기
    tickers = get_massive_tickers()
    if not tickers: return
    
    # 2. BigQuery 업로드 (Write Truncate 방식)
    table_ref = f"{client.project}.{DATASET_ID}.{TABLE_TICKERS}"
    
    # 스키마 정의 (keywords, change_rate, last_volume 포함)
    job_config = bigquery.LoadJobConfig(
        write_disposition="WRITE_TRUNCATE", # 기존 데이터 밀고 덮어쓰기
        schema=[
            bigquery.SchemaField("ticker", "STRING", mode="REQUIRED"),
            bigquery.SchemaField("name", "STRING", mode="NULLABLE"),
            bigquery.SchemaField("sector", "STRING", mode="NULLABLE"),
            bigquery.SchemaField("keywords", "STRING", mode="NULLABLE"), # [NEW]
            bigquery.SchemaField("status", "STRING", mode="NULLABLE"),
            bigquery.SchemaField("change_rate", "FLOAT", mode="NULLABLE"),
            bigquery.SchemaField("last_volume", "INTEGER", mode="NULLABLE"),
            bigquery.SchemaField("fail_count", "INTEGER", mode="NULLABLE"),
            bigquery.SchemaField("updated_at", "STRING", mode="NULLABLE"), # 호환성 위해 STRING
        ]
    )
    
    # 데이터 포맷팅 (Timestamp -> String)
    rows_to_insert = []
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    for item in tickers:
        item['updated_at'] = timestamp
        rows_to_insert.append(item)

    print(f"[BQ] BigQuery 전체 덮어쓰기 시작 (총 {len(rows_to_insert)}개)...")

    try:
        job = client.load_table_from_json(rows_to_insert, table_ref, job_config=job_config)
        job.result() # 완료 대기
        
        print("\n[Complete] 6,000+ 종목 DB 구축 및 키워드 생성 완료.")
        print(" -> 이제 'update_volume_tier.py'를 실행하여 거래량 분석을 수행하세요.")
        
    except Exception as e:
        print(f"[Error] DB 업로드 실패: {e}")

if __name__ == "__main__":
    seed_db()