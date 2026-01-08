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
MAX_WORKERS = 10
BATCH_SIZE = 50   

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
    개별 종목 분석 (스마트 스킵 적용)
    """
    try:
        # 1. 차트 데이터 (KIS)
        d_data = kis_chart.get_daily_chart(ticker)
        
        # [데이터 부족 컷]
        if not d_data or len(d_data) < 20:
            return None 

        # 2. [스마트 스킵]
        latest = d_data[0]
        price = float(latest.get('clos') or latest.get('last') or 0)
        vol = float(latest.get('acml_vol') or latest.get('tvol') or 0)
        
        # 조건 A: 1달러 미만 스킵
        if price < 1.0: 
            return None 
            
        # 조건 B: 거래량 5만주 미만 스킵
        if vol < 50000:
            return None

        # 3. 기술적 분석
        tech_data, _, _ = technical.analyze_technical_signals(d_data, [])

        # 4. 수급/펀더멘털 분석
        supply_data, _, _ = supply.analyze_supply_structure(ticker)
        fund_data, _, _ = fundamental.analyze_fundamentals(ticker)

        # 5. 결과 패키징
        return {
            "ticker": ticker,
            "tech": tech_data,
            "fund": fund_data,
            "supply": supply_data
        }

    except Exception as e:
        return None

def save_batch_features(batch_results):
    """결과 묶음 DB 저장"""
    if not batch_results: return
    for item in batch_results:
        mervis_bigquery.save_daily_features(
            item['ticker'], item['tech'], item['fund'], item['supply']
        )

def run_fast_crawler():
    start_time = time.time()
    print(f" [Crawler] 스마트 고속 모드 시작 (Workers: {MAX_WORKERS})")
    print(" [Info] Ctrl+C를 누르면 즉시 중단됩니다.")
    
    tickers = get_all_tickers()
    if not tickers: return

    total = len(tickers)
    print(f" [Crawler] 총 {total}개 후보군 스캔 시작...")
    
    processed_count = 0
    saved_count = 0
    success_buffer = [] 

    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            # 모든 작업을 예약
            future_to_ticker = {executor.submit(process_single_stock, t): t for t in tickers}
            
            # 완료되는 순서대로 처리
            for future in concurrent.futures.as_completed(future_to_ticker):
                processed_count += 1
                try:
                    result = future.result()
                    
                    if result:
                        success_buffer.append(result)
                        saved_count += 1
                    
                    print(f" Progress: {processed_count}/{total} (Saved: {saved_count})", end='\r')

                    if len(success_buffer) >= BATCH_SIZE:
                        save_batch_features(success_buffer)
                        success_buffer = [] 
                        
                except Exception:
                    pass
    
    except KeyboardInterrupt:
        print("\n\n [Stop] 사용자 요청으로 크롤링을 중단합니다...")
        print(" [Info] 대기 중인 작업을 취소하고 종료합니다.")
        # executor는 with 블록을 빠져나가면서 자동으로 종료되지만, 
        # 즉시 종료를 위해 명시적으로 호출할 수도 있습니다.
        # (Python 3.9+ 에서는 cancel_futures=True 사용 가능)
        return

    # 남은 데이터 저장 (강제 종료가 아닐 때만)
    if success_buffer:
        save_batch_features(success_buffer)

    end_time = time.time()
    duration = (end_time - start_time) / 60
    print(f"\n [Crawler] 완료! 소요 시간: {duration:.1f}분 | 총 저장된 유의미한 종목: {saved_count}개")

if __name__ == "__main__":
    run_fast_crawler()