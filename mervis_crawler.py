import time
import logging
import concurrent.futures
from datetime import datetime
from google.cloud import bigquery

# 사용자 모듈 임포트
import mervis_bigquery
import kis_chart
from modules import technical, fundamental, supply

# 로깅 설정
logging.basicConfig(
    filename='crawler.log', 
    level=logging.INFO, 
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

# --- 설정 ---
MAX_WORKERS = 5  # 동시에 일할 일꾼 수 (너무 높으면 API 차단됨, 5~8 권장)
BATCH_SIZE = 50  # DB에 한 번에 저장할 묶음 단위

def get_all_tickers():
    client = mervis_bigquery.get_client()
    if not client: return []
    query = f"SELECT ticker FROM `{client.project}.{mervis_bigquery.DATASET_ID}.{mervis_bigquery.TABLE_TICKERS}`"
    try:
        results = list(client.query(query).result())
        return [row.ticker for row in results]
    except Exception as e:
        print(f" [Crawler] 종목 리스트 로드 실패: {e}")
        return []

def process_single_stock(ticker):
    """
    개별 종목 하나를 분석해서 결과 데이터를 반환 (저장은 안 함)
    """
    try:
        # 1. 차트 데이터 (KIS)
        d_data = kis_chart.get_daily_chart(ticker)
        if not d_data or len(d_data) < 20:
            return None # 데이터 부족

        # 2. 분석 모듈 실행
        tech_data, _, _ = technical.analyze_technical_signals(d_data, [])
        supply_data, _, _ = supply.analyze_supply_structure(ticker)
        fund_data, _, _ = fundamental.analyze_fundamentals(ticker)

        # 3. 데이터 패키징 (저장하기 좋게 딕셔너리로 리턴)
        return {
            "ticker": ticker,
            "tech": tech_data,
            "fund": fund_data,
            "supply": supply_data
        }
    except Exception as e:
        logging.error(f"Error processing {ticker}: {e}")
        return None

def save_batch_features(batch_results):
    """
    수집된 결과 묶음을 DB에 한 번에 저장 (속도 향상)
    """
    if not batch_results: return
    
    # mervis_bigquery.save_daily_features 함수는 단건 저장용이므로,
    # 직접 insert_rows를 호출하는 것이 효율적이지만,
    # 코드 안전성을 위해 반복문으로 빠르게 호출 (네트워크 오버헤드는 병렬처리로 상쇄)
    
    for item in batch_results:
        mervis_bigquery.save_daily_features(
            item['ticker'], item['tech'], item['fund'], item['supply']
        )

def run_fast_crawler():
    start_time = time.time()
    print(f" [Crawler] 고속 모드 시작 (Workers: {MAX_WORKERS})")
    
    tickers = get_all_tickers()
    if not tickers: return

    total = len(tickers)
    print(f" [Crawler] 총 {total}개 종목 분석 시작...")
    
    processed_count = 0
    success_buffer = [] # DB 저장 대기열

    # 멀티스레딩으로 작업 분배
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        # 모든 종목에 대해 작업 예약
        future_to_ticker = {executor.submit(process_single_stock, t): t for t in tickers}
        
        for future in concurrent.futures.as_completed(future_to_ticker):
            ticker = future_to_ticker[future]
            try:
                result = future.result()
                processed_count += 1
                
                if result:
                    success_buffer.append(result)
                    print(f" [{processed_count}/{total}] {ticker} OK", end='\r')
                else:
                    # 실패 시 로그만 (화면 출력 X)
                    pass

                # 버퍼가 꽉 차면 DB 저장 (Batch flush)
                if len(success_buffer) >= BATCH_SIZE:
                    save_batch_features(success_buffer)
                    success_buffer = [] # 초기화
                    
            except Exception as e:
                logging.error(f"Worker Error {ticker}: {e}")

    # 남은 데이터 저장
    if success_buffer:
        save_batch_features(success_buffer)

    end_time = time.time()
    duration = (end_time - start_time) / 60
    print(f"\n [Crawler] 완료! 소요 시간: {duration:.1f}분")

if __name__ == "__main__":
    run_fast_crawler()